import asyncio
import logging
from datetime import datetime, timedelta
import pytz
from supabase import create_client, Client
from typing import Optional, Dict, Set, List, Tuple
import hashlib
import json

# ─── CONFIGURATION ─────────────────────────────────────
SUPABASE_URL = "https://umpbmweobqlowgavdydu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVtcGJtd2VvYnFsb3dnYXZkeWR1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUwMDM3MTIsImV4cCI6MjA4MDU3OTcxMn0.jUVCioepUoTbadeqykzPq_73WsCScAP8XrtqvOJFhR0"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
SINGAPORE_TZ = pytz.timezone("Asia/Singapore")

SLOT_MIN = 15
EARLY_MIN = 5
GRACE_MIN = 30
LATE_MIN = 60
EXPIRE_MIN = 90
DEFAULT_ETA = 30  # Default ETA if not specified (30 minutes)

POLLING_INTERVAL_SECONDS = 30  # Check for changes every 30 seconds
PERIODIC_UPDATE_MINUTES = 15  # Full queue update every 15 minutes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ClinicQueue")

# ─── STATE MANAGEMENT ──────────────────────────────────
last_patient_state: Dict[str, Dict] = {}  # Cache of tcm_patient_register rows {id: {fields}}

# ─── HELPER FUNCTIONS ──────────────────────────────────
def parse_time(dt: str) -> datetime:
    """Parse datetime string to Singapore timezone."""
    try:
        return datetime.fromisoformat(dt.replace('Z', '+00:00')).astimezone(SINGAPORE_TZ)
    except ValueError as e:
        logger.error(f"Failed to parse time {dt}: {e}")
        return datetime.now(SINGAPORE_TZ)

def parse_time_from_date_time(date_str: str, time_str: str) -> datetime:
    """Parse date and time strings into datetime object."""
    try:
        dt_str = f"{date_str}T{time_str}:00+08:00"
        return datetime.fromisoformat(dt_str).astimezone(SINGAPORE_TZ)
    except Exception as e:
        logger.error(f"Failed to parse date {date_str} time {time_str}: {e}")
        return datetime.now(SINGAPORE_TZ)

def get_status(now: datetime, booked: Optional[datetime]) -> str:
    """Determine patient status based on arrival time."""
    if not booked:
        return "walk-in"
    diff = (now - booked).total_seconds() / 60
    if diff < -EARLY_MIN: return "early"
    if -EARLY_MIN <= diff <= EARLY_MIN: return "on-time"
    if EARLY_MIN < diff <= GRACE_MIN: return "slightly late"
    if GRACE_MIN < diff <= LATE_MIN: return "late"
    return "expired"

def get_slot_time(current_time: datetime) -> datetime:
    """Round to the nearest 15-minute slot starting at 8:00 AM."""
    start_of_day = current_time.replace(hour=8, minute=0, second=0, microsecond=0)
    minutes_since_start = (current_time - start_of_day).total_seconds() / 60
    slot_number = int(minutes_since_start // 15)
    return start_of_day + timedelta(minutes=slot_number * 15)

def compute_row_hash(patient: Dict) -> str:
    """Compute a hash of key patient fields to detect changes."""
    fields = {
        'id': patient['id'],
        'doctor_id': patient.get('doctor_id'),
        'booked_time_slot': patient.get('booked_time_slot'),
        'status': patient.get('status'),
        'task': patient.get('task'),
        'case_id': patient.get('case_id'),
        'created_at': patient.get('created_at'),
        'eta': patient.get('eta')
    }
    return hashlib.md5(json.dumps(fields, sort_keys=True).encode()).hexdigest()

def get_patient_eta(patient: Dict) -> int:
    """Get ETA in minutes for a patient."""
    try:
        if patient.get('eta'):
            eta_str = patient['eta']
            # Remove any non-numeric characters except numbers
            eta_clean = ''.join(filter(str.isdigit, eta_str))
            if eta_clean:
                return int(eta_clean)
    except Exception as e:
        logger.error(f"Error parsing ETA for patient {patient.get('id')}: {e}")
    return DEFAULT_ETA

async def get_clinic_doctors_count(clinic_id: str) -> int:
    """Get the number of doctors in a clinic."""
    try:
        doctors_response = await asyncio.to_thread(
            supabase.table('tcm_a_doctors').select('id', count='exact')
            .eq('clinic_id', clinic_id).execute
        )
        return doctors_response.count or 0
    except Exception as e:
        logger.error(f"Error fetching doctors count for clinic {clinic_id}: {str(e)}")
        return 0

async def get_bookings_for_clinic(clinic_id: str, today: str) -> list:
    """Get all relevant bookings for a clinic on a specific date from tcm_s_bookings."""
    bookings = []
    try:
        # Get all bookings for this clinic on this date
        bookings_response = await asyncio.to_thread(
            supabase.table('tcm_s_bookings').select(
                'id, doctor_id, original_date, original_time, new_date, new_time, '
                'booking_type, status, whatsapp_users(user_name), duration_minutes'
            )
            .eq('clinic_id', clinic_id)
            .in_('status', ['confirmed', 'pending'])
            .execute
        )
        
        for booking in bookings_response.data or []:
            # Determine which date/time to use based on reschedule status
            if booking.get('new_date') and booking.get('new_time'):
                # Use rescheduled date/time
                actual_date = booking['new_date']
                actual_time = booking['new_time']
            else:
                # Use original date/time
                actual_date = booking['original_date']
                actual_time = booking['new_time'] if booking.get('new_time') else booking['original_time']
            
            # Check if this booking is for today
            if actual_date == today:
                bookings.append({
                    'id': booking['id'],
                    'doctor_id': booking['doctor_id'],
                    'date': actual_date,
                    'time': actual_time,
                    'booking_type': booking['booking_type'],
                    'status': booking['status'],
                    'user_name': booking['whatsapp_users']['user_name'] if booking.get('whatsapp_users') else 'Unknown',
                    'duration_minutes': booking.get('duration_minutes', DEFAULT_ETA)
                })
                
    except Exception as e:
        logger.error(f"Error fetching bookings for clinic {clinic_id}: {str(e)}")
    
    return bookings

def calculate_queue_position_with_eta(
    patients: List[Dict], 
    doctors_count: int, 
    now: datetime
) -> List[Tuple[Dict, int, datetime]]:
    """
    Calculate queue positions for clinics without doctor selection using ETA.
    This simulates multiple doctors working in parallel.
    """
    if doctors_count == 0:
        return []
    
    # Create doctor slots - each doctor has a list of available time slots
    doctors = [{'id': f'doc_{i}', 'next_available': now} for i in range(doctors_count)]
    
    # Group patients by status with priority order
    status_priority = {
        'slightly late': 1,
        'on-time': 2,
        'early': 3,
        'late': 4,
        'expired': 5,
        'walk-in': 6
    }
    
    # Group patients by status
    patients_by_status = {}
    for patient in patients:
        status = patient.get('status', 'walk-in')
        patients_by_status.setdefault(status, []).append(patient)
    
    # Sort each group by booked time (or arrival time for walk-ins)
    for status in patients_by_status:
        patients_by_status[status].sort(key=lambda p: p.get('booked_dt') or p.get('created_dt'))
    
    # Build patient list in priority order
    all_patients = []
    for status in sorted(patients_by_status.keys(), key=lambda s: status_priority.get(s, 99)):
        all_patients.extend(patients_by_status[status])
    
    # Calculate queue positions and estimated times
    queue_assignments = []
    
    # Process on-time patients first to ensure they get slots within first N positions
    on_time_patients = patients_by_status.get('on-time', [])
    slightly_late_patients = patients_by_status.get('slightly late', [])
    early_patients = patients_by_status.get('early', [])
    late_patients = patients_by_status.get('late', [])
    expired_patients = patients_by_status.get('expired', [])
    walk_in_patients = patients_by_status.get('walk-in', [])
    
    # First, assign slightly late patients to available doctors
    current_position = 1
    doctor_assignments = {}
    
    # Create a list of all patients in processing order
    patients_to_process = []
    
    # Add slightly late patients first (up to doctor count)
    for i, patient in enumerate(slightly_late_patients):
        if i < doctors_count:
            patients_to_process.append(patient)
    
    # Add on-time patients (they should be within first N positions)
    patients_to_process.extend(on_time_patients)
    
    # Add remaining slightly late patients
    for i, patient in enumerate(slightly_late_patients):
        if i >= doctors_count:
            patients_to_process.append(patient)
    
    # Add remaining patients in priority order
    patients_to_process.extend(early_patients)
    patients_to_process.extend(late_patients)
    patients_to_process.extend(expired_patients)
    patients_to_process.extend(walk_in_patients)
    
    # Track doctor availability
    doctor_availability = [now] * doctors_count
    
    for patient in patients_to_process:
        # Find the doctor who becomes available earliest
        earliest_doctor_idx = min(range(doctors_count), key=lambda i: doctor_availability[i])
        doctor_next_available = doctor_availability[earliest_doctor_idx]
        
        # Calculate estimated start time
        # For early patients, we might want to wait until their booked time
        if patient.get('status') == 'early' and patient.get('booked_dt'):
            booked_time = patient['booked_dt']
            if booked_time > doctor_next_available:
                estimated_start = booked_time
            else:
                estimated_start = doctor_next_available
        else:
            estimated_start = doctor_next_available
        
        # Update doctor's next available time
        eta_minutes = get_patient_eta(patient)
        doctor_availability[earliest_doctor_idx] = estimated_start + timedelta(minutes=eta_minutes)
        
        queue_assignments.append((patient, current_position, estimated_start))
        current_position += 1
    
    return queue_assignments

def calculate_queue_for_doctor_selection(
    patients: List[Dict],
    doctors: List[Dict],
    now: datetime,
    clinic_id: str
) -> List[Tuple[Dict, str, int, datetime]]:
    """
    Calculate queue for clinics WITH doctor selection.
    Returns list of (patient, doctor_id, queue_position, estimated_time)
    """
    queue_assignments = []
    
    # Group patients by doctor
    patients_by_doctor = {}
    for patient in patients:
        doctor_id = patient.get('doctor_id') or 'unassigned'
        patients_by_doctor.setdefault(doctor_id, []).append(patient)
    
    # Process each doctor's queue
    for doctor in doctors:
        doctor_id = doctor['id']
        if doctor_id in patients_by_doctor:
            doctor_patients = patients_by_doctor[doctor_id]
            
            # Sort patients by status and booked time
            doctor_patients.sort(key=lambda p: (
                p.get('status') != 'walk-in',  # Booked patients first
                p.get('booked_dt') or p.get('created_dt')
            ))
            
            # Calculate queue for this doctor
            current_time = now
            for i, patient in enumerate(doctor_patients):
                eta_minutes = get_patient_eta(patient)
                
                # For early patients, consider booked time
                if patient.get('status') == 'early' and patient.get('booked_dt'):
                    booked_time = patient['booked_dt']
                    if booked_time > current_time:
                        estimated_start = booked_time
                    else:
                        estimated_start = current_time
                else:
                    estimated_start = current_time
                
                queue_assignments.append((patient, doctor_id, i + 1, estimated_start))
                current_time = estimated_start + timedelta(minutes=eta_minutes)
    
    return queue_assignments

async def update_queue():
    """Main queue update function."""
    now = datetime.now(SINGAPORE_TZ)
    today = now.date().isoformat()
    logger.info(f"Starting queue update at {now}")

    try:
        clinics_response = await asyncio.to_thread(
            supabase.table('tcm_a_clinics').select('id, doctor_selection').execute
        )
        clinics = clinics_response.data or []
        if not clinics:
            logger.error(f"No clinics found at {now}")
            return
    except Exception as e:
        logger.error(f"Error fetching clinics: {str(e)}")
        return

    for clinic in clinics:
        clinic_id = clinic['id']
        doctor_selection = clinic.get('doctor_selection', True)
        
        logger.info(f"Processing clinic {clinic_id} with doctor_selection={doctor_selection}")

        try:
            patients_response = await asyncio.to_thread(
                supabase.table('tcm_patient_register').select(
                    'id, booked_time_slot, status, doctor_id, task, case_id, created_at, clinic_id, eta'
                )
                .eq('clinic_id', clinic_id)
                .neq('status', 'completed')
                .gte('created_at', f"{today}T00:00:00+08:00")
                .lte('created_at', f"{today}T23:59:59+08:00").execute
            )
            registered_patients = patients_response.data or []
            logger.info(f"Found {len(registered_patients)} registered patients for clinic {clinic_id}")
        except Exception as e:
            logger.error(f"Error fetching patients for clinic {clinic_id}: {str(e)}")
            continue

        # Fetch existing patient_queue entries to check coverage
        try:
            queue_response = await asyncio.to_thread(
                supabase.table('tcm_patient_queue').select(
                    'registration_id, queue_position, estimated_start_time, queue_type, tcm_patient_register(doctor_id, clinic_id)'
                )
                .eq('queue_type', 'confirmed')
                .gte('estimated_start_time', f"{today}T00:00:00+08:00")
                .lte('estimated_start_time', f"{today}T23:59:59+08:00").execute
            )
            # Filter for current clinic
            existing_queue_data = [
                q for q in (queue_response.data or []) 
                if q['tcm_patient_register']['clinic_id'] == clinic_id
            ]
            existing_queue_ids = {q['registration_id'] for q in existing_queue_data}
            logger.info(f"Found {len(existing_queue_ids)} confirmed queue entries for clinic {clinic_id}")
        except Exception as e:
            logger.error(f"Error fetching tcm_patient_queue for clinic {clinic_id}: {str(e)}")
            existing_queue_ids = set()

        # Process patients and calculate status
        processed_patients = []
        for patient in registered_patients:
            # Calculate status for each patient
            booked_dt = parse_time(patient['booked_time_slot']) if patient['booked_time_slot'] else parse_time(patient['created_at'])
            status = get_status(now, booked_dt)
            
            # Get ETA for the patient
            eta_minutes = get_patient_eta(patient)
            
            processed_patients.append({
                **patient,
                'booked_dt': booked_dt,
                'created_dt': parse_time(patient['created_at']),
                'status': status,
                'eta_minutes': eta_minutes
            })

        if doctor_selection:
            # Logic for clinics WITH doctor selection
            try:
                doctors_response = await asyncio.to_thread(
                    supabase.table('tcm_a_doctors').select('id').eq('clinic_id', clinic_id).execute
                )
                doctors = doctors_response.data or []
                if not doctors:
                    logger.warning(f"No doctors for clinic {clinic_id}")
                    continue
            except Exception as e:
                logger.error(f"Error fetching doctors for clinic {clinic_id}: {str(e)}")
                continue

            # Calculate queue for doctor selection
            queue_assignments = calculate_queue_for_doctor_selection(
                processed_patients, doctors, now, clinic_id
            )
            
            # Prepare queue updates
            queue_updates = []
            for patient, doctor_id, queue_position, estimated_time in queue_assignments:
                # Check if patient already has a queue entry
                if patient['id'] in existing_queue_ids:
                    # Update existing entry
                    queue_updates.append({
                        'registration_id': patient['id'],
                        'queue_position': queue_position,
                        'estimated_start_time': estimated_time.isoformat(),
                        'updated_at': now.isoformat(),
                        'queue_type': 'confirmed',
                        'doctor_id': doctor_id
                    })
                else:
                    # Create new entry
                    queue_updates.append({
                        'registration_id': patient['id'],
                        'queue_position': queue_position,
                        'estimated_start_time': estimated_time.isoformat(),
                        'updated_at': now.isoformat(),
                        'queue_type': 'confirmed',
                        'doctor_id': doctor_id
                    })
            
            # Also handle unassigned patients
            unassigned_patients = [p for p in processed_patients if not p.get('doctor_id')]
            if unassigned_patients:
                # Assign unassigned patients to the first available doctor
                for patient in unassigned_patients:
                    if len(doctors) > 0:
                        assigned_doctor = doctors[0]['id']
                        # Find earliest available time for this doctor
                        doctor_assignments = [qa for qa in queue_assignments if qa[1] == assigned_doctor]
                        if doctor_assignments:
                            last_assignment = max(doctor_assignments, key=lambda x: x[3])
                            estimated_time = last_assignment[3] + timedelta(minutes=patient['eta_minutes'])
                        else:
                            estimated_time = now
                        
                        queue_position = len([qa for qa in queue_assignments if qa[1] == assigned_doctor]) + 1
                        
                        queue_updates.append({
                            'registration_id': patient['id'],
                            'queue_position': queue_position,
                            'estimated_start_time': estimated_time.isoformat(),
                            'updated_at': now.isoformat(),
                            'queue_type': 'confirmed',
                            'doctor_id': assigned_doctor
                        })

            if queue_updates:
                try:
                    await asyncio.to_thread(
                        supabase.table('tcm_patient_queue').upsert(
                            queue_updates,
                            on_conflict='registration_id',
                            ignore_duplicates=False,
                            returning='minimal'
                        ).execute
                    )
                    logger.info(f"Updated queue for clinic {clinic_id} (with doctor selection): {len(queue_updates)} patients")
                except Exception as e:
                    logger.error(f"Failed to upsert queue for clinic {clinic_id}: {str(e)}")
            else:
                logger.info(f"No queue updates for clinic {clinic_id} (with doctor selection)")

        else:
            # NEW LOGIC for clinics WITHOUT doctor selection
            doctors_count = await get_clinic_doctors_count(clinic_id)
            logger.info(f"Clinic {clinic_id} has {doctors_count} doctors, doctor_selection is False")
            
            # Calculate queue positions using ETA
            queue_assignments = calculate_queue_position_with_eta(
                processed_patients, doctors_count, now
            )
            
            # Prepare queue updates
            queue_updates = []
            for patient, queue_position, estimated_time in queue_assignments:
                # Check if patient already has a queue entry
                if patient['id'] in existing_queue_ids:
                    # Update existing entry
                    queue_updates.append({
                        'registration_id': patient['id'],
                        'queue_position': queue_position,
                        'estimated_start_time': estimated_time.isoformat(),
                        'updated_at': now.isoformat(),
                        'queue_type': 'confirmed'
                    })
                else:
                    # Create new entry
                    queue_updates.append({
                        'registration_id': patient['id'],
                        'queue_position': queue_position,
                        'estimated_start_time': estimated_time.isoformat(),
                        'updated_at': now.isoformat(),
                        'queue_type': 'confirmed'
                    })
            
            if queue_updates:
                try:
                    await asyncio.to_thread(
                        supabase.table('tcm_patient_queue').upsert(
                            queue_updates,
                            on_conflict='registration_id',
                            ignore_duplicates=False,
                            returning='minimal'
                        ).execute
                    )
                    logger.info(f"Updated queue for clinic {clinic_id} (no doctor selection): {len(queue_updates)} patients")
                except Exception as e:
                    logger.error(f"Failed to upsert queue for clinic {clinic_id}: {str(e)}")
            else:
                logger.info(f"No queue updates for clinic {clinic_id} (no doctor selection)")

        # Ensure all patient_register rows have a patient_queue entry
        missing_queue_patients = [p for p in registered_patients if p['id'] not in existing_queue_ids]
        if missing_queue_patients:
            logger.info(f"Found {len(missing_queue_patients)} patients without queue entries in clinic {clinic_id}")
            
            # Process missing queue patients
            for patient_data in missing_queue_patients:
                patient = next((p for p in processed_patients if p['id'] == patient_data['id']), None)
                if not patient:
                    continue
                
                if doctor_selection:
                    # For clinics with doctor selection
                    if not patient.get('doctor_id') and doctors:
                        assigned_doctor = doctors[0]['id']
                        queue_updates = [{
                            'registration_id': patient['id'],
                            'queue_position': 1,
                            'estimated_start_time': now.isoformat(),
                            'updated_at': now.isoformat(),
                            'queue_type': 'confirmed',
                            'doctor_id': assigned_doctor
                        }]
                    elif patient.get('doctor_id'):
                        queue_updates = [{
                            'registration_id': patient['id'],
                            'queue_position': 1,
                            'estimated_start_time': now.isoformat(),
                            'updated_at': now.isoformat(),
                            'queue_type': 'confirmed',
                            'doctor_id': patient['doctor_id']
                        }]
                else:
                    # For clinics without doctor selection
                    queue_updates = [{
                        'registration_id': patient['id'],
                        'queue_position': 1,
                        'estimated_start_time': now.isoformat(),
                        'updated_at': now.isoformat(),
                        'queue_type': 'confirmed'
                    }]
                
                if queue_updates:
                    try:
                        await asyncio.to_thread(
                            supabase.table('tcm_patient_queue').upsert(
                                queue_updates,
                                on_conflict='registration_id',
                                ignore_duplicates=False,
                                returning='minimal'
                            ).execute
                        )
                        logger.info(f"Added missing queue entry for patient {patient['id']}")
                    except Exception as e:
                        logger.error(f"Failed to add queue entry for patient {patient['id']}: {str(e)}")

async def poll_patient_register() -> bool:
    """Poll tcm_patient_register for changes and trigger update_queue if needed."""
    global last_patient_state
    now = datetime.now(SINGAPORE_TZ)
    today = now.date().isoformat()
    try:
        patients_response = await asyncio.to_thread(
            supabase.table('tcm_patient_register').select(
                'id, booked_time_slot, status, doctor_id, task, case_id, created_at, clinic_id, eta'
            )
            .neq('status', 'completed')
            .gte('created_at', f"{today}T00:00:00+08:00")
            .lte('created_at', f"{today}T23:59:59+08:00").execute
        )
        current_patients = patients_response.data or []
        current_patient_ids = {p['id'] for p in current_patients}
        previous_patient_ids = set(last_patient_state.keys())

        # Compute hashes for current patients
        current_state = {p['id']: {'data': p, 'hash': compute_row_hash(p)} for p in current_patients}
        
        # Detect new or changed patients
        changed = False
        new_patients = current_patient_ids - previous_patient_ids
        if new_patients:
            logger.info(f"Detected {len(new_patients)} new patients: {new_patients}")
            changed = True

        modified_patients = {
            pid for pid in current_patient_ids & previous_patient_ids
            if current_state[pid]['hash'] != last_patient_state[pid]['hash']
        }
        if modified_patients:
            logger.info(f"Detected {len(modified_patients)} modified patients: {modified_patients}")
            changed = True

        # Update state
        last_patient_state = current_state

        if changed:
            logger.info(f"Changes detected, triggering queue update")
            await update_queue()
        else:
            logger.debug(f"No changes in tcm_patient_register")
        return changed
    except Exception as e:
        logger.error(f"Error polling tcm_patient_register: {str(e)}")
        return False

async def run_scheduler():
    """Main scheduler loop."""
    logger.info("Starting queue_main scheduler with polling")
    
    last_full_update = datetime.now(SINGAPORE_TZ)
    try:
        while True:
            try:
                # Poll for changes in tcm_patient_register
                await poll_patient_register()
                # Periodic full update every 15 minutes
                if (datetime.now(SINGAPORE_TZ) - last_full_update).total_seconds() >= PERIODIC_UPDATE_MINUTES * 60:
                    await update_queue()
                    last_full_update = datetime.now(SINGAPORE_TZ)
                    logger.info("Periodic queue update completed")
                await asyncio.sleep(POLLING_INTERVAL_SECONDS)
            except Exception as e:
                logger.error(f"Error in scheduler loop: {str(e)}")
                await asyncio.sleep(10)  # Short retry on error
    except KeyboardInterrupt:
        logger.info("Scheduler stopped")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run_scheduler())
    finally:
        loop.close()