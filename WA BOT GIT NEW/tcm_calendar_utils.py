# tcm_calendar_utils.py - UPDATED WITH METHOD SELECTION, ADDRESS, AND PRIORITY HANDLING
import logging
import uuid
import re
import json
from datetime import datetime, timedelta
from utils import send_whatsapp_message, send_interactive_menu, translate_template, gt_tt, gt_t_tt

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache for unavailable slots
unavailable_slots_cache = {}

def get_clinic_doctor_selection(supabase, clinic_id):
    """Check if doctor selection is enabled for the clinic."""
    try:
        if not clinic_id:
            return False
        response = supabase.table("tcm_a_clinics") \
            .select("doctor_selection") \
            .eq("id", clinic_id) \
            .single() \
            .execute()
       
        if response.data:
            return response.data.get("doctor_selection", False)
        return False
    except Exception as e:
        logger.error(f"[TCM] Error fetching clinic doctor_selection: {str(e)}")
        return False

def get_service_assigned_doctors(supabase, service_id):
    """Get all assigned doctors for a service in priority order (id, 2, 3, 4, 5)."""
    try:
        if not service_id or service_id == "others":
            return [], None
        response = supabase.table("tcm_a_clinic_service") \
            .select("doctor_id, doctor2_id, doctor3_id, doctor4_id, doctor5_id, clinic_id") \
            .eq("id", service_id) \
            .single() \
            .execute()
       
        if response.data:
            doctors = []
            fields = ["doctor_id", "doctor2_id", "doctor3_id", "doctor4_id", "doctor5_id"]
            for field in fields:
                doctor_id = response.data.get(field)
                if doctor_id:
                    doctors.append(doctor_id)
            return doctors, response.data.get("clinic_id")
        return [], None
    except Exception as e:
        logger.error(f"[TCM] Error fetching service assigned doctors: {str(e)}")
        return [], None

def find_least_busy_available_doctor(clinic_id, date, time_slot, duration, supabase):
    """Find the least busy available doctor for a given time slot."""
    try:
        # Get all doctors in the clinic
        doctors = supabase.table("tcm_a_doctors").select("id, name").eq("clinic_id", clinic_id).execute().data
       
        if not doctors:
            logger.warning(f"[TCM] No doctors found for clinic {clinic_id}")
            return None, "no_doctors_in_clinic"
       
        # Find available doctors and their appointment counts
        available_doctors = []
       
        for doctor in doctors:
            doctor_id = doctor["id"]
           
            # Check if doctor is available at this slot
            is_available, reason = check_doctor_availability_at_slot(
                doctor_id, date, time_slot, duration, supabase
            )
           
            if is_available:
                # Count appointments for this doctor on this day
                appointments = supabase.table("tcm_s_bookings").select("id", count="exact") \
                    .eq("doctor_id", doctor_id) \
                    .eq("original_date", date) \
                    .in_("status", ["confirmed", "pending"]) \
                    .execute()
               
                count = appointments.count or 0
                available_doctors.append({
                    "id": doctor_id,
                    "name": doctor["name"],
                    "appointment_count": count
                })
       
        if not available_doctors:
            logger.warning(f"[TCM] No doctors available for {date} at {time_slot}")
            return None, "no_doctors_available"
       
        # Sort by appointment count (least busy first)
        available_doctors.sort(key=lambda x: x["appointment_count"])
       
        # Return the least busy available doctor
        selected_doctor = available_doctors[0]
        logger.info(f"[TCM] Selected least busy doctor {selected_doctor['id']} ({selected_doctor['name']}) with {selected_doctor['appointment_count']} appointments")
       
        return selected_doctor["id"], "available"
       
    except Exception as e:
        logger.error(f"[TCM] Error finding least busy doctor: {str(e)}")
        return None, "error"

def get_available_doctors_for_service(whatsapp_number, user_id, supabase, user_data, module_name):
    """Get available doctors for selection based on clinic's doctor_selection setting."""
    try:
        logger.info(f"[TCM] Getting available doctors for {whatsapp_number}")
       
        clinic_id = user_data[whatsapp_number].get("clinic_id")
        service_id = user_data[whatsapp_number].get("service_id")
       
        if not clinic_id:
            logger.error(f"[TCM] No clinic_id found for {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Clinic not selected. Please contact support.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            user_data[whatsapp_number]["module"] = None
            send_interactive_menu(whatsapp_number, supabase)
            return
       
        # Check clinic's doctor_selection setting
        doctor_selection_enabled = get_clinic_doctor_selection(supabase, clinic_id)
       
        if not doctor_selection_enabled:
            logger.info(f"[TCM] Doctor selection disabled for clinic {clinic_id}. Skipping doctor selection.")
            # Clear any user-selected doctor; assignment happens later.
            user_data[whatsapp_number]["doctor_id"] = None
            user_data[whatsapp_number]["any_doctor"] = False
            # Skip doctor selection and go directly to calendar
            get_calendar(whatsapp_number, user_id, supabase, user_data, module_name)
            return
       
        # Doctor selection is enabled - show available doctors
        doctor_list = []
       
        if service_id and service_id != "others":
            # Get assigned doctors for this service
            assigned_doctor_ids, _ = get_service_assigned_doctors(supabase, service_id)
           
            if assigned_doctor_ids:
                # Get details of assigned doctors
                doctor_response = supabase.table("tcm_a_doctors") \
                    .select("id, name") \
                    .in_("id", assigned_doctor_ids) \
                    .execute()
               
                for doctor in doctor_response.data:
                    # Use original doctor name (not translated)
                    doctor_name = doctor["name"]
                    doctor_list.append({
                        "id": str(doctor["id"]),
                        "title": gt_t_tt(whatsapp_number, doctor_name, supabase)[:21] + "..." if len(gt_t_tt(whatsapp_number, doctor_name, supabase)) > 21 else gt_t_tt(whatsapp_number, doctor_name, supabase)
                    })
            else:
                # No assigned doctors - show all clinic doctors
                logger.info(f"[TCM] Service {service_id} has no assigned doctors, showing all clinic doctors")
                doctors = supabase.table("tcm_a_doctors") \
                    .select("id, name") \
                    .eq("clinic_id", clinic_id) \
                    .execute().data
               
                for doctor in doctors:
                    # Use original doctor name (not translated)
                    doctor_name = doctor["name"]
                    doctor_list.append({
                        "id": str(doctor["id"]),
                        "title": gt_t_tt(whatsapp_number, doctor_name, supabase)[:21] + "..." if len(gt_t_tt(whatsapp_number, doctor_name, supabase)) > 21 else gt_t_tt(whatsapp_number, doctor_name, supabase)
                    })
        else:
            # "others" or no service selected - show all clinic doctors
            doctors = supabase.table("tcm_a_doctors") \
                .select("id, name") \
                .eq("clinic_id", clinic_id) \
                .execute().data
           
            for doctor in doctors:
                # Use original doctor name (not translated)
                doctor_name = doctor["name"]
                doctor_list.append({
                    "id": str(doctor["id"]),
                    "title": gt_t_tt(whatsapp_number, doctor_name, supabase)[:21] + "..." if len(gt_t_tt(whatsapp_number, doctor_name, supabase)) > 21 else gt_t_tt(whatsapp_number, doctor_name, supabase)
                })
       
        # Always add "Any Doctor" option
        doctor_list.append({
            "id": "any_doctor",
            "title": translate_template(whatsapp_number, "Any Doctor", supabase)
        })
       
        # Limit to 10 rows max
        doctor_list = doctor_list[:10]
        logger.info(f"[TCM] Doctor list for {whatsapp_number}: {[d['title'] for d in doctor_list]}")
        result = send_whatsapp_message(
            whatsapp_number,
            "interactive",
            {
                "interactive": {
                    "type": "list",
                    "body": {
                        "text": translate_template(
                            whatsapp_number,
                            "Select a doctor for your appointment or choose 'Any Doctor':",
                            supabase
                        )
                    },
                    "action": {
                        "button": translate_template(whatsapp_number, "Choose Doctor", supabase),
                        "sections": [{
                            "title": translate_template(whatsapp_number, "Available Doctors", supabase),
                            "rows": doctor_list
                        }]
                    }
                }
            },
            supabase
        )
        if not result:
            logger.error(f"[TCM] Failed to send doctor list to {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Unable to fetch doctors. Please try again.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            user_data[whatsapp_number]["module"] = None
            send_interactive_menu(whatsapp_number, supabase)
            return
        user_data[whatsapp_number]["state"] = "SELECT_DOCTOR"
        user_data[whatsapp_number]["module"] = module_name
        logger.info(f"[TCM] Sent doctor list to {whatsapp_number}, module: {module_name}")
    except Exception as e:
        logger.error(f"[TCM] Error in get_available_doctors_for_service for {whatsapp_number}: {str(e)}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, f"An error occurred while fetching doctors: {str(e)}. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "IDLE"
        user_data[whatsapp_number]["module"] = None
        send_interactive_menu(whatsapp_number, supabase)

# handle TCM repeated visits
def handle_tcm_repeated_visit_check(whatsapp_number, user_id, supabase, user_data, booking_id):
    """Check if a TCM booking is part of a repeated visit series."""
    try:
        # Query tcm_repeated_visit table
        repeated_visit = supabase.table("tcm_repeated_visit").select(
            "*"
        ).eq("booking_id", booking_id).execute().data
       
        if repeated_visit and len(repeated_visit) > 0:
            return {
                "is_repeated": True,
                "repeated_visit_uuid": repeated_visit[0].get("id"),
                "repeated_visit_data": repeated_visit[0]
            }
       
        return {"is_repeated": False}
       
    except Exception as e:
        logger.error(f"Error checking TCM repeated visit: {e}")
        return {"is_repeated": False}

def request_tcm_reschedule(booking_id, new_date, new_time, supabase):
    """Doctor requests reschedule for a TCM booking."""
    try:
        update_data = {
            "new_date": new_date,
            "new_time": new_time,
            "status": "reschedule_pending", # Set status for patient action
            "updated_at": datetime.now().isoformat()
        }
       
        response = supabase.table("tcm_s_bookings").update(update_data).eq("id", booking_id).execute()
        return True, "Reschedule requested successfully"
    except Exception as e:
        logger.error(f"Error requesting TCM reschedule: {e}")
        return False, str(e)

def get_clinic_schedule(supabase, clinic_id, date):
    """Fetch TCM clinic schedule for a given date including all breaks."""
    try:
        date_str = date.strftime("%Y-%m-%d")
        day_name = date.strftime("%A").lower()
        day_key = day_name
       
        response = supabase.table("tcm_a_clinic_available_time").select("*").eq("clinic_id", clinic_id).execute()
       
        if not response.data:
            logger.error(f"[TCM] No schedule found for clinic_id: {clinic_id}")
            return None
           
        schedule = response.data[0]
        # Check self-declared holidays
        holiday_self_declared = schedule.get("holiday_self_declared")
        if holiday_self_declared and isinstance(holiday_self_declared, list) and date_str in holiday_self_declared:
            logger.info(f"[TCM] Date {date_str} is a self-declared holiday for clinic_id: {clinic_id}")
            return None
        special_dates = schedule.get("special_dates", [])
        if special_dates is None:
            special_dates = []
        elif isinstance(special_dates, str):
            try:
                special_dates = json.loads(special_dates)
            except json.JSONDecodeError:
                special_dates = []
       
        # Check special dates
        for sd in special_dates:
            if sd.get("date") == date_str:
                if not sd.get("start_time") or not sd.get("end_time"):
                    logger.info(f"[TCM] Special date {date_str} has no valid hours (null start_time or end_time)")
                    return None
               
                # Extract all breaks for special date
                breaks = []
                for i in range(1, 6):
                    break_start = sd.get(f"break{i}_start")
                    break_end = sd.get(f"break{i}_end")
                    if break_start and break_end:
                        breaks.append({"start": break_start, "end": break_end})
               
                return {
                    "start_time": sd.get("start_time"),
                    "end_time": sd.get("end_time"),
                    "lunch_start": sd.get("lunch_start"),
                    "lunch_end": sd.get("lunch_end"),
                    "dinner_start": sd.get("dinner_start"),
                    "dinner_end": sd.get("dinner_end"),
                    "breaks": breaks
                }
        # Get regular schedule for the day
        start_time = schedule.get(f"{day_key}_start")
        end_time = schedule.get(f"{day_key}_end")
        lunch_start = schedule.get(f"{day_key}_lunch_start")
        lunch_end = schedule.get(f"{day_key}_lunch_end")
        dinner_start = schedule.get(f"{day_key}_dinner_start")
        dinner_end = schedule.get(f"{day_key}_dinner_end")
        # Extract all breaks for regular day
        breaks = []
        for i in range(1, 6):
            break_start = schedule.get(f"{day_key}_break{i}_start")
            break_end = schedule.get(f"{day_key}_break{i}_end")
            if break_start and break_end:
                breaks.append({"start": break_start, "end": break_end})
        if not start_time or not end_time:
            logger.info(f"[TCM] Clinic is closed on {day_name} ({date_str}) due to null start_time or end_time")
            return None
        logger.info(f"[TCM] Schedule for {day_name} ({date_str}): start={start_time}, end={end_time}, lunch={lunch_start}-{lunch_end}, dinner={dinner_start}-{dinner_end}, breaks={len(breaks)}")
        return {
            "start_time": start_time,
            "end_time": end_time,
            "lunch_start": lunch_start,
            "lunch_end": lunch_end,
            "dinner_start": dinner_start,
            "dinner_end": dinner_end,
            "breaks": breaks
        }
    except Exception as e:
        logger.error(f"[TCM] Error fetching clinic schedule for {clinic_id} on {date_str}: {str(e)}", exc_info=True)
        return None

def parse_date_input(date_str):
    """Parse date string in DD/MM/YYYY, DD-MM-YYYY, or DD MM YYYY format."""
    try:
        # Remove any extra spaces and replace common separators with /
        date_str = re.sub(r'[\s\-\.]', '/', date_str.strip())
       
        # Split by /
        parts = date_str.split('/')
        if len(parts) != 3:
            return None
           
        day, month, year = parts
       
        # Ensure all parts are numeric
        if not (day.isdigit() and month.isdigit() and year.isdigit()):
            return None
           
        day = int(day)
        month = int(month)
        year = int(year)
       
        # Handle 2-digit year
        if year < 100:
            year += 2000 # Assume 20xx for 2-digit years
           
        # Validate date
        if 1 <= month <= 12 and 1 <= day <= 31 and year >= 2024:
            date_obj = datetime(year, month, day)
            # Check if the date is valid (e.g., not Feb 30)
            if date_obj.day == day and date_obj.month == month and date_obj.year == year:
                return date_obj
               
    except Exception as e:
        logger.error(f"[TCM] Error parsing date {date_str}: {str(e)}")
       
    return None

def format_date_for_display(date_obj, whatsapp_number, supabase):
    """Format date for display with translated day name."""
    day_name = date_obj.strftime("%A")
    translated_day = translate_template(whatsapp_number, day_name, supabase)
    formatted_date = date_obj.strftime("%d %B %Y")
    return f"{formatted_date} ({translated_day})"

def format_date_for_button(date_obj):
    """Format date for button display (DD/MM/YYYY format)."""
    return date_obj.strftime("%d/%m/%Y")

def check_doctor_availability_at_slot(doctor_id, date, time_slot, duration, supabase):
    """Check if a specific doctor is available at a given time slot."""
    try:
        slot_time = datetime.strptime(f"{date} {time_slot}", "%Y-%m-%d %H:%M")
        slot_end = slot_time + timedelta(minutes=duration)
       
        # Check existing bookings in tcm_s_bookings - BOTH original and new times
        bookings = supabase.table("tcm_s_bookings").select(
            "original_time, new_time, duration_minutes, status"
        ).eq("doctor_id", doctor_id) \
         .eq("original_date", date) \
         .in_("status", ["confirmed", "pending"]) \
         .execute().data
       
        for b in bookings:
            # Check original time
            if b["original_time"]:
                b_start = datetime.strptime(f"{date} {b['original_time']}", "%Y-%m-%d %H:%M")
                b_end = b_start + timedelta(minutes=b["duration_minutes"])
                # Check if slot overlaps with this booking
                if slot_time < b_end and slot_end > b_start:
                    return False, "slot_booked"
           
            # Check new time for rescheduled appointments
            if b["new_time"]:
                r_start = datetime.strptime(f"{date} {b['new_time']}", "%Y-%m-%d %H:%M")
                r_end = r_start + timedelta(minutes=b["duration_minutes"])
                if slot_time < r_end and slot_end > r_start:
                    return False, "slot_booked"
       
        return True, "available"
   
    except Exception as e:
        logger.error(f"[TCM] Error checking doctor availability: {str(e)}")
        return False, "error"

def get_assigned_doctor_for_slot(service_id, date, time_slot, duration, supabase, clinic_id=None):
    """Find an available assigned doctor for a service at a given time slot with priority order.
    If no assigned doctors, check any available doctor in the clinic."""
    try:
        # If clinic_id is not provided, we need to get it from the service
        if not clinic_id:
            service_response = supabase.table("tcm_a_clinic_service") \
                .select("clinic_id") \
                .eq("id", service_id) \
                .single() \
                .execute()
           
            if service_response.data:
                clinic_id = service_response.data["clinic_id"]
            else:
                logger.error(f"[TCM] Could not find clinic_id for service {service_id}")
                return None, "service_not_found"
       
        # Get service details including all assigned doctors
        assigned_doctor_ids, service_clinic_id = get_service_assigned_doctors(supabase, service_id)
       
        if assigned_doctor_ids:
            logger.info(f"[TCM] Assigned doctors for service {service_id}: {assigned_doctor_ids}")
           
            # Check each doctor in priority order
            for doctor_id in assigned_doctor_ids:
                is_available, reason = check_doctor_availability_at_slot(
                    doctor_id, date, time_slot, duration, supabase
                )
                if is_available:
                    logger.info(f"[TCM] Doctor {doctor_id} is available for slot {time_slot}")
                    return doctor_id, "available"
                else:
                    logger.info(f"[TCM] Doctor {doctor_id} is NOT available for slot {time_slot}: {reason}")
           
            # No assigned doctors available
            logger.warning(f"[TCM] No assigned doctors available for service {service_id} at {time_slot}")
            return None, "all_doctors_booked"
        else:
            # No assigned doctors - check any available doctor in the clinic
            logger.info(f"[TCM] Service {service_id} has no assigned doctors. Checking any available doctor.")
            doctors = supabase.table("tcm_a_doctors").select("id").eq("clinic_id", clinic_id).execute().data
            if not doctors:
                logger.warning(f"[TCM] No doctors found for clinic {clinic_id}")
                return None, "no_doctors_in_clinic"
            for doctor in doctors:
                doctor_id = doctor["id"]
                is_available, reason = check_doctor_availability_at_slot(
                    doctor_id, date, time_slot, duration, supabase
                )
                if is_available:
                    return doctor_id, "available"
            return None, "all_doctors_booked"
       
    except Exception as e:
        logger.error(f"[TCM] Error finding assigned doctor: {str(e)}")
        return None, "error"

def check_date_availability(date_obj, clinic_id, doctor_id, is_any_doctor, supabase, service_id=None):
    """Check if a specific date is available for booking in TCM clinic."""
    try:
        date_str = date_obj.strftime("%Y-%m-%d")
       
        # Check clinic schedule
        clinic_schedule = get_clinic_schedule(supabase, clinic_id, date_obj)
        if not clinic_schedule:
            return False, "clinic_closed"
           
        # Parse clinic times
        def parse_time(t):
            if not t:
                return None
            if len(t) > 5:
                t = t[:5] # keep only HH:MM
            return datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %H:%M")
        start_time = parse_time(clinic_schedule["start_time"])
        end_time = parse_time(clinic_schedule["end_time"])
        lunch_start = parse_time(clinic_schedule["lunch_start"])
        lunch_end = parse_time(clinic_schedule["lunch_end"])
       
        # Check all breaks
        breaks = []
        for break_schedule in clinic_schedule.get("breaks", []):
            break_start = parse_time(break_schedule["start"])
            break_end = parse_time(break_schedule["end"])
            if break_start and break_end:
                breaks.append((break_start, break_end))
        def is_during_breaks(slot_time):
            if lunch_start and lunch_end and lunch_start <= slot_time < lunch_end:
                return True
            for break_start, break_end in breaks:
                if break_start <= slot_time < break_end:
                    return True
            return False
        # Generate time slots and check availability
        time_slots = []
        current_slot = start_time
        while current_slot < end_time:
            if is_during_breaks(current_slot):
                current_slot += timedelta(minutes=15)
                continue
            time_slots.append((current_slot, current_slot.strftime("%H:%M")))
            current_slot += timedelta(minutes=15)
        if not time_slots:
            return False, "no_slots"
        # Check doctor availability for at least one slot
        if is_any_doctor:
            doctors = supabase.table("tcm_a_doctors").select("id").eq("clinic_id", clinic_id).execute().data
            for slot_time, slot_str in time_slots:
                unavailable_doctor_ids = set()
               
                booked_doctor_ids = set()
                # Check tcm_s_bookings table for confirmed bookings
                bookings_query = supabase.table("tcm_s_bookings").select("doctor_id, original_time, new_time") \
                    .eq("original_date", date_str) \
                    .in_("status", ["confirmed", "pending"])
               
                # Only add doctor_id filter if it's not None and not "None"
                if doctor_id and doctor_id != "None":
                    bookings_query = bookings_query.eq("doctor_id", doctor_id)
               
                bookings = bookings_query.execute().data
               
                for booking in bookings:
                    # Check original time slot
                    if booking["original_time"] == slot_str:
                        booked_doctor_ids.add(booking["doctor_id"])
                    # Check new time slot for rescheduled appointments
                    if booking["new_time"] == slot_str:
                        booked_doctor_ids.add(booking["doctor_id"])
               
                if any(d["id"] not in unavailable_doctor_ids and d["id"] not in booked_doctor_ids for d in doctors):
                    return True, "available"
        else:
            for slot_time, slot_str in time_slots:
                # Check if specific doctor is booked
                is_booked = False
               
                # Check tcm_s_bookings table - FIXED: Only filter by doctor_id if it's not None
                if doctor_id and doctor_id != "None":
                    bookings = supabase.table("tcm_s_bookings").select("id, original_time, new_time") \
                        .eq("doctor_id", doctor_id) \
                        .eq("original_date", date_str) \
                        .in_("status", ["confirmed", "pending"]) \
                        .execute().data
                   
                    for booking in bookings:
                        if booking["original_time"] == slot_str or booking["new_time"] == slot_str:
                            is_booked = True
                            break
                else:
                    # If doctor_id is None, check if any bookings exist for this time slot
                    bookings = supabase.table("tcm_s_bookings").select("id, original_time, new_time") \
                        .eq("original_date", date_str) \
                        .in_("status", ["confirmed", "pending"]) \
                        .execute().data
                   
                    # If there are any bookings at this time, it's booked
                    for booking in bookings:
                        if booking["original_time"] == slot_str or booking["new_time"] == slot_str:
                            is_booked = True
                            break
               
                if not is_booked:
                    return True, "available"
        return False, "no_available_doctors"
    except Exception as e:
        logger.error(f"[TCM] Error checking date availability: {str(e)}", exc_info=True)
        return False, "error"

def find_nearest_available_dates(target_date, clinic_id, doctor_id, is_any_doctor, supabase, max_dates=8, search_range=30):
    """Find nearest available dates within search_range days from target_date."""
    available_dates = []
   
    # Search forward from target_date
    for days_after in range(0, search_range + 1):
        check_date = target_date + timedelta(days=days_after)
        is_available, reason = check_date_availability(check_date, clinic_id, doctor_id, is_any_doctor, supabase)
        if is_available:
            available_dates.append(check_date)
            if len(available_dates) >= max_dates:
                return available_dates
   
    # Search backward from target_date
    for days_before in range(1, search_range + 1):
        check_date = target_date - timedelta(days=days_before)
        is_available, reason = check_date_availability(check_date, clinic_id, doctor_id, is_any_doctor, supabase)
        if is_available:
            available_dates.append(check_date)
            if len(available_dates) >= max_dates:
                return available_dates
               
    return available_dates

def handle_future_date_input(whatsapp_number, user_id, supabase, user_data, module_name, date_input):
    """Handle future date input from user."""
    try:
        # Parse the date input
        date_obj = parse_date_input(date_input)
        if not date_obj:
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "Invalid date format. Please enter date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:",
                    supabase
                )}}
            )
            user_data[whatsapp_number]["state"] = "AWAITING_FUTURE_DATE"
            return
        # Check if date is in the past
        if date_obj.date() < datetime.now().date():
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "Please select a future date. Enter date as DD/MM/YYYY:",
                    supabase
                )}}
            )
            user_data[whatsapp_number]["state"] = "AWAITING_FUTURE_DATE"
            return
        # Store the parsed date and ask for confirmation
        user_data[whatsapp_number]["future_date_input"] = date_obj
        formatted_date = format_date_for_display(date_obj, whatsapp_number, supabase)
       
        send_whatsapp_message(
            whatsapp_number,
            "interactive",
            {
                "interactive": {
                    "type": "button",
                    "body": {"text": translate_template(
                        whatsapp_number,
                        f"Is this the correct date: {formatted_date}?",
                        supabase
                    )},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": "confirm_future_date", "title": translate_template(whatsapp_number, "Yes", supabase)}},
                            {"type": "reply", "reply": {"id": "reject_future_date", "title": translate_template(whatsapp_number, "No", supabase)}}
                        ]
                    }
                }
            }
        )
        user_data[whatsapp_number]["state"] = "CONFIRM_FUTURE_DATE"
    except Exception as e:
        logger.error(f"[TCM] Error handling future date input for {whatsapp_number}: {str(e)}")
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing date. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "AWAITING_FUTURE_DATE"

def handle_future_date_confirmation(whatsapp_number, user_id, supabase, user_data, module_name, confirmed=True):
    """Handle confirmation of future date."""
    try:
        if not confirmed:
            # User rejected the date, ask for new input
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "Please enter the date again as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:",
                    supabase
                )}}
            )
            user_data[whatsapp_number]["state"] = "AWAITING_FUTURE_DATE"
            user_data[whatsapp_number].pop("future_date_input", None)
            return
        date_obj = user_data[whatsapp_number].get("future_date_input")
        if not date_obj:
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Date not found. Please try again.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "AWAITING_FUTURE_DATE"
            return
        clinic_id = user_data[whatsapp_number].get("clinic_id")
        if not clinic_id:
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Clinic not selected. Please start over.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            user_data[whatsapp_number]["module"] = None
            send_interactive_menu(whatsapp_number, supabase)
            return
           
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_any_doctor = user_data[whatsapp_number].get("any_doctor", False)
        # Check clinic's doctor_selection setting
        doctor_selection_enabled = get_clinic_doctor_selection(supabase, clinic_id)
       
        logger.info(f"[TCM] Future date confirmation for {whatsapp_number}, doctor_selection_enabled: {doctor_selection_enabled}, doctor_id: {doctor_id}, is_any_doctor: {is_any_doctor}")
       
        # If doctor selection is disabled, we should use any doctor logic
        if not doctor_selection_enabled:
            is_any_doctor = True
            doctor_id = None
            logger.info(f"[TCM] Doctor selection disabled, using any doctor logic for {whatsapp_number}")
        # Check if the date is available
        is_available, reason = check_date_availability(date_obj, clinic_id, doctor_id, is_any_doctor, supabase)
       
        if is_available:
            # Date is available, proceed to period selection
            user_data[whatsapp_number]["date"] = date_obj.strftime("%Y-%m-%d")
            user_data[whatsapp_number].pop("future_date_input", None)
           
            # Check if we need to go to doctor selection or directly to period
            if doctor_selection_enabled and doctor_id is None and not is_any_doctor:
                # Need to select doctor first
                get_available_doctors_for_service(whatsapp_number, user_id, supabase, user_data, module_name)
            else:
                # Doctor already selected or doctor selection disabled, go directly to period
                select_period(whatsapp_number, user_id, supabase, user_data, module_name)
        else:
            # Date not available, suggest nearest dates
            formatted_date_short = format_date_for_button(date_obj)
            nearest_dates = find_nearest_available_dates(date_obj, clinic_id, doctor_id, is_any_doctor, supabase)
           
            if nearest_dates:
                # Create buttons for nearest dates using DD/MM/YYYY format
                date_rows = []
                for i, near_date in enumerate(nearest_dates[:8]): # Max 8 dates
                    formatted_near_date = format_date_for_button(near_date)
                    date_rows.append({
                        "id": near_date.strftime("%Y-%m-%d"),
                        "title": formatted_near_date
                    })
                # Send nearest dates as interactive list
                send_whatsapp_message(
                    whatsapp_number,
                    "interactive",
                    {
                        "interactive": {
                            "type": "list",
                            "body": {"text": translate_template(
                                whatsapp_number,
                                f"Selected date {formatted_date_short} is not available. Here are the nearest available dates:",
                                supabase
                            )},
                            "action": {
                                "button": translate_template(whatsapp_number, "Choose Date", supabase),
                                "sections": [{
                                    "title": translate_template(whatsapp_number, "Available Dates", supabase),
                                    "rows": date_rows
                                }]
                            }
                        }
                    }
                )
                user_data[whatsapp_number]["state"] = "SELECT_DATE"
            else:
                # No dates found at all
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        f"No available dates found near {formatted_date_short}. Please enter a different date as DD/MM/YYYY:",
                        supabase
                    )}}
                )
                user_data[whatsapp_number]["state"] = "AWAITING_FUTURE_DATE"
    except Exception as e:
        logger.error(f"[TCM] Error handling future date confirmation for {whatsapp_number}: {str(e)}")
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error confirming date. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "AWAITING_FUTURE_DATE"

def get_calendar(whatsapp_number, user_id, supabase, user_data, module_name):
    """Generate a list of available dates for the next 14 days with Future Date option."""
    try:
        today = datetime.today()
        start_date = today.date()
        end_date = start_date + timedelta(days=13)
       
        # Get clinic ID from user data
        clinic_id = user_data[whatsapp_number].get("clinic_id")
        if not clinic_id:
            logger.error(f"[TCM] No clinic_id found for {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Clinic not selected. Please start over.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            user_data[whatsapp_number]["module"] = None
            send_interactive_menu(whatsapp_number, supabase)
            return
           
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_any_doctor = user_data[whatsapp_number].get("any_doctor", False)
        service_id = user_data[whatsapp_number].get("service_id")
       
        # Check if doctor selection is enabled for the clinic
        doctor_selection_enabled = get_clinic_doctor_selection(supabase, clinic_id)
       
        logger.info(f"[TCM] Querying calendar for {whatsapp_number}, clinic_id: {clinic_id}, doctor_id: {doctor_id}, any_doctor: {is_any_doctor}, from {start_date} to {end_date}, doctor_selection_enabled: {doctor_selection_enabled}")
        available_dates = []
        for i in range(14):
            date = start_date + timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            day_name = date.strftime("%A")
            translated_day = translate_template(whatsapp_number, day_name, supabase)
            display_str = f"{date.strftime('%d-%m-%Y')} ({translated_day})"
            clinic_schedule = get_clinic_schedule(supabase, clinic_id, date)
            if not clinic_schedule:
                logger.info(f"[TCM] Clinic is closed on {date_str}")
                continue
            try:
                start_time = datetime.strptime(f"{date_str} {clinic_schedule['start_time']}", "%Y-%m-%d %H:%M")
            except ValueError:
                try:
                    start_time = datetime.strptime(f"{date_str} {clinic_schedule['start_time']}", "%Y-%m-%d %H:%M:%S")
                except ValueError as e:
                    logger.error(f"[TCM] Failed to parse start_time {clinic_schedule['start_time']} for {date_str}: {str(e)}")
                    continue
            try:
                end_time = datetime.strptime(f"{date_str} {clinic_schedule['end_time']}", "%Y-%m-%d %H:%M")
            except ValueError:
                try:
                    end_time = datetime.strptime(f"{date_str} {clinic_schedule['end_time']}", "%Y-%m-%d %H:%M:%S")
                except ValueError as e:
                    logger.error(f"[TCM] Failed to parse end_time {clinic_schedule['end_time']} for {date_str}: {str(e)}")
                    continue
            lunch_start = None
            if clinic_schedule["lunch_start"]:
                try:
                    lunch_start = datetime.strptime(f"{date_str} {clinic_schedule['lunch_start']}", "%Y-%m-%d %H:%M")
                except ValueError:
                    try:
                        lunch_start = datetime.strptime(f"{date_str} {clinic_schedule['lunch_start']}", "%Y-%m-%d %H:%M:%S")
                    except ValueError as e:
                        logger.error(f"[TCM] Failed to parse lunch_start {clinic_schedule['lunch_start']} for {date_str}: {str(e)}")
                        lunch_start = None
            lunch_end = None
            if clinic_schedule["lunch_end"]:
                try:
                    lunch_end = datetime.strptime(f"{date_str} {clinic_schedule['lunch_end']}", "%Y-%m-%d %H:%M")
                except ValueError:
                    try:
                        lunch_end = datetime.strptime(f"{date_str} {clinic_schedule['lunch_end']}", "%Y-%m-%d %H:%M:%S")
                    except ValueError as e:
                        logger.error(f"[TCM] Failed to parse lunch_end {clinic_schedule['lunch_end']} for {date_str}: {str(e)}")
                        lunch_end = None
            total_duration = end_time - start_time
            lunch_duration = (lunch_end - lunch_start) if lunch_start and lunch_end else timedelta(0)
            available_duration = total_duration - lunch_duration
            if available_duration <= timedelta(0):
                logger.info(f"[TCM] No available time slots for {date_str}")
                continue
            time_slots = []
            current_slot = start_time
            while current_slot < end_time:
                if lunch_start and lunch_end and lunch_start <= current_slot < lunch_end:
                    current_slot += timedelta(minutes=15)
                    continue
                time_slots.append((current_slot, current_slot.strftime("%H:%M")))
                current_slot += timedelta(minutes=15)
            if not time_slots:
                logger.info(f"[TCM] No available time slots for {date_str}")
                continue
            has_available_slot = False
           
            if doctor_selection_enabled:
                # Doctor selection is enabled - check based on selected doctor
                if is_any_doctor:
                    doctors = supabase.table("tcm_a_doctors").select("id").eq("clinic_id", clinic_id).execute().data
                    for slot_time, slot_str in time_slots:
                        unavailable_doctor_ids = set()
                       
                        booked_doctor_ids = set()
                        # Check tcm_s_bookings table
                        bookings = supabase.table("tcm_s_bookings").select("doctor_id, original_time, new_time") \
                            .eq("original_date", date_str) \
                            .in_("status", ["confirmed", "pending"]) \
                            .execute().data
                       
                        for booking in bookings:
                            if booking["original_time"] == slot_str or booking["new_time"] == slot_str:
                                booked_doctor_ids.add(booking["doctor_id"])
                       
                        if any(d["id"] not in unavailable_doctor_ids and d["id"] not in booked_doctor_ids for d in doctors):
                            has_available_slot = True
                            break
                else:
                    for slot_time, slot_str in time_slots:
                        is_booked = False
                       
                        # Check tcm_s_bookings table
                        bookings = supabase.table("tcm_s_bookings").select("id, original_time, new_time") \
                            .eq("doctor_id", doctor_id) \
                            .eq("original_date", date_str) \
                            .in_("status", ["confirmed", "pending"]) \
                            .execute().data
                       
                        for booking in bookings:
                            if booking["original_time"] == slot_str or booking["new_time"] == slot_str:
                                is_booked = True
                                break
                       
                        if not is_booked:
                            has_available_slot = True
                            break
            else:
                # Doctor selection is disabled - check if any doctor can be auto-assigned
                for slot_time, slot_str in time_slots:
                    assigned_doctor, reason = get_assigned_doctor_for_slot(
                        service_id, date_str, slot_str,
                        user_data[whatsapp_number].get("duration_minutes", 30),
                        supabase,
                        clinic_id
                    )
                    if assigned_doctor:
                        has_available_slot = True
                        break
           
            if has_available_slot:
                available_dates.append({"id": date_str, "title": display_str})
        # Add Future Date option
        display_dates = available_dates[:9] # Take only first 9 available dates
       
        # Add Future Date option
        display_dates.append({
            "id": "future_date",
            "title": translate_template(whatsapp_number, "📅 Future Date", supabase)
        })
        if not display_dates:
            logger.warning(f"[TCM] No available dates for {whatsapp_number} from {start_date} to {end_date}")
            error_text = translate_template(
                whatsapp_number,
                "No available dates in the next 14 days. Please {}.",
                supabase
            ).format(
                translate_template(whatsapp_number, "select another doctor", supabase) if not is_any_doctor else translate_template(whatsapp_number, "try again later", supabase)
            )
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": error_text}}
            )
            if not is_any_doctor and doctor_selection_enabled:
                user_data[whatsapp_number]["state"] = "SELECT_DOCTOR"
                get_available_doctors_for_service(whatsapp_number, user_id, supabase, user_data, module_name)
            else:
                user_data[whatsapp_number]["state"] = "IDLE"
                user_data[whatsapp_number]["module"] = None
                send_interactive_menu(whatsapp_number, supabase)
            return
        logger.info(f"[TCM] Available dates for {whatsapp_number}: {[d['title'] for d in display_dates]}")
        result = send_whatsapp_message(
            whatsapp_number,
            "interactive",
            {
                "interactive": {
                    "type": "list",
                    "body": {"text": translate_template(whatsapp_number, "Select a date for your appointment:", supabase)},
                    "action": {
                        "button": translate_template(whatsapp_number, "Choose Date", supabase),
                        "sections": [{
                            "title": translate_template(whatsapp_number, "Available Dates", supabase),
                            "rows": display_dates
                        }]
                    }
                }
            },
            supabase
        )
        if not result:
            logger.error(f"[TCM] Failed to send calendar to {whatsapp_number}. Response: {result}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Unable to fetch calendar. Please try again.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            user_data[whatsapp_number]["module"] = None
            send_interactive_menu(whatsapp_number, supabase)
            return
        user_data[whatsapp_number]["state"] = "SELECT_DATE"
        user_data[whatsapp_number]["module"] = module_name
        logger.info(f"[TCM] Sent calendar to {whatsapp_number}, module: {module_name}")
    except Exception as e:
        logger.error(f"[TCM] Error in get_calendar for {whatsapp_number}: {str(e)}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, f"An error occurred while fetching the calendar: {str(e)}. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "IDLE"
        user_data[whatsapp_number]["module"] = None
        send_interactive_menu(whatsapp_number, supabase)

def select_period(whatsapp_number, user_id, supabase, user_data, module_name):
    """Prompt user to select AM or PM for the appointment date considering all breaks."""
    try:
        date = user_data[whatsapp_number]["date"]
        clinic_id = user_data[whatsapp_number].get("clinic_id")
        if not clinic_id:
            logger.error(f"[TCM] No clinic_id found for {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Clinic not selected. Please start over.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            user_data[whatsapp_number]["module"] = None
            send_interactive_menu(whatsapp_number, supabase)
            return
           
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_any_doctor = user_data[whatsapp_number].get("any_doctor", False)
        service_id = user_data[whatsapp_number].get("service_id")
        current_time = datetime.now()
        current_date = current_time.date()
        is_today = date == current_date.strftime("%Y-%m-%d")
       
        # Check if doctor selection is enabled
        doctor_selection_enabled = get_clinic_doctor_selection(supabase, clinic_id)
       
        logger.info(f"[TCM] Prompting period selection for {whatsapp_number}, clinic_id: {clinic_id}, doctor_id: {doctor_id}, any_doctor: {is_any_doctor}, on {date}, is_today: {is_today}, doctor_selection_enabled: {doctor_selection_enabled}")
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        clinic_schedule = get_clinic_schedule(supabase, clinic_id, date_obj)
        if not clinic_schedule:
            logger.warning(f"[TCM] No clinic schedule available for {whatsapp_number} on {date}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "No available hours for this date. Please select another date.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "SELECT_DATE"
            get_calendar(whatsapp_number, user_id, supabase, user_data, module_name)
            return
        # Helper function to parse time
        def parse_time(t):
            if not t:
                return None
            if len(t) > 5:
                t = t[:5] # keep only HH:MM
            return datetime.strptime(f"{date} {t}", "%Y-%m-%d %H:%M")
        start_time = parse_time(clinic_schedule["start_time"])
        end_time = parse_time(clinic_schedule["end_time"])
        lunch_start = parse_time(clinic_schedule["lunch_start"])
        lunch_end = parse_time(clinic_schedule["lunch_end"])
        dinner_start = parse_time(clinic_schedule["dinner_start"])
        dinner_end = parse_time(clinic_schedule["dinner_end"])
       
        # Parse all breaks
        breaks = []
        for break_schedule in clinic_schedule.get("breaks", []):
            break_start = parse_time(break_schedule["start"])
            break_end = parse_time(break_schedule["end"])
            if break_start and break_end:
                breaks.append((break_start, break_end))
        # Check if time slot is during any break
        def is_during_breaks(slot_time):
            # Check lunch break
            if lunch_start and lunch_end and lunch_start <= slot_time < lunch_end:
                return True
            # Check dinner break
            if dinner_start and dinner_end and dinner_start <= slot_time < dinner_end:
                return True
            # Check additional breaks
            for break_start, break_end in breaks:
                if break_start <= slot_time < break_end:
                    return True
            return False
        # Calculate blocks
        current_block_start = start_time.replace(minute=0, second=0, microsecond=0)
        am_blocks = []
        pm_blocks = []
        while current_block_start < end_time:
            block_start = current_block_start
            block_end = block_start + timedelta(hours=2)
            if block_end > end_time:
                break
            last_slot_start = block_start + timedelta(hours=1, minutes=45)
            if last_slot_start >= end_time:
                break
            block_id = f"{block_start.strftime('%H:%M')}-{last_slot_start.strftime('%H:%M')}"
            has_available_slot = False
           
            for sub in range(2):
                sub_hour_start = block_start + timedelta(hours=sub)
                if sub_hour_start >= end_time:
                    break
                if is_today and sub_hour_start < current_time:
                    continue
                   
                for minute in [0, 15, 30, 45]:
                    slot_time = sub_hour_start + timedelta(minutes=minute)
                    slot_str = slot_time.strftime("%H:%M")
                   
                    if slot_time >= end_time:
                        continue
                    if is_today and slot_time < current_time:
                        continue
                    if is_during_breaks(slot_time):
                        continue
                    if slot_time < start_time:
                        continue
                       
                    if doctor_selection_enabled:
                        # Doctor selection enabled
                        if is_any_doctor:
                            doctors = supabase.table("tcm_a_doctors").select("id").eq("clinic_id", clinic_id).execute().data
                            # Skip unavailability check
                            unavailable_doctor_ids = set()
                           
                            booked_doctor_ids = set()
                            # Check tcm_s_bookings table
                            bookings = supabase.table("tcm_s_bookings").select("doctor_id, original_time, new_time") \
                                .eq("original_date", date) \
                                .in_("status", ["confirmed", "pending"]) \
                                .execute().data
                           
                            for booking in bookings:
                                if booking["original_time"] == slot_str or booking["new_time"] == slot_str:
                                    booked_doctor_ids.add(booking["doctor_id"])
                           
                            if any(d["id"] not in unavailable_doctor_ids and d["id"] not in booked_doctor_ids for d in doctors):
                                has_available_slot = True
                                break
                        else:
                            # Check if specific doctor is booked
                            is_booked = False
                           
                            # Check tcm_s_bookings table
                            bookings = supabase.table("tcm_s_bookings").select("id, original_time, new_time") \
                                .eq("doctor_id", doctor_id) \
                                .eq("original_date", date) \
                                .in_("status", ["confirmed", "pending"]) \
                                .execute().data
                           
                            for booking in bookings:
                                if booking["original_time"] == slot_str or booking["new_time"] == slot_str:
                                    is_booked = True
                                    break
                           
                            if not is_booked:
                                has_available_slot = True
                                break
                    else:
                        # Doctor selection disabled - check assigned doctors
                        if service_id and service_id != "others":
                            assigned_doctor, reason = get_assigned_doctor_for_slot(
                                service_id, date, slot_str,
                                user_data[whatsapp_number].get("duration_minutes", 30),
                                supabase,
                                clinic_id
                            )
                            if assigned_doctor:
                                has_available_slot = True
                                break
                        else:
                            # No specific service - slot is available
                            has_available_slot = True
                            break
                if has_available_slot:
                    break
                   
            if has_available_slot:
                block_hour = block_start.hour
                row = {"id": block_id, "title": block_id}
                if block_hour < 12:
                    am_blocks.append(row)
                else:
                    pm_blocks.append(row)
                   
            current_block_start += timedelta(hours=2)
        user_data[whatsapp_number]["am_blocks"] = am_blocks
        user_data[whatsapp_number]["pm_blocks"] = pm_blocks
        if not am_blocks and not pm_blocks:
            logger.warning(f"[TCM] No available hours for {whatsapp_number} on {date}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "No available hours for this date. Please select another date.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "SELECT_DATE"
            get_calendar(whatsapp_number, user_id, supabase, user_data, module_name)
            return
        buttons = []
        if am_blocks:
            buttons.append({"type": "reply", "reply": {"id": "AM", "title": translate_template(whatsapp_number, "AM", supabase)}})
        if pm_blocks:
            buttons.append({"type": "reply", "reply": {"id": "PM", "title": translate_template(whatsapp_number, "PM", supabase)}})
        payload = {
            "interactive": {
                "type": "button",
                "body": {"text": translate_template(whatsapp_number, "Select AM or PM for {}:", supabase).format(date)},
                "action": {
                    "buttons": buttons
                }
            }
        }
        result = send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
        if not result:
            logger.error(f"[TCM] Failed to send period selection to {whatsapp_number}. Response: {result}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Unable to fetch hours. Please try again.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            user_data[whatsapp_number]["module"] = None
            send_interactive_menu(whatsapp_number, supabase)
            return
        user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
        user_data[whatsapp_number]["module"] = module_name
        logger.info(f"[TCM] Sent period selection to {whatsapp_number}, module: {module_name}")
    except Exception as e:
        logger.error(f"[TCM] Error in select_period for {whatsapp_number}: {str(e)}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, f"An error occurred while fetching hours: {str(e)}. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "IDLE"
        user_data[whatsapp_number]["module"] = None
        send_interactive_menu(whatsapp_number, supabase)

def get_available_hours(whatsapp_number, user_id, supabase, user_data, module_name):
    """Generate a list of available hour blocks for the selected period."""
    try:
        date = user_data[whatsapp_number]["date"]
        period = user_data[whatsapp_number].get("period")
        clinic_id = user_data[whatsapp_number].get("clinic_id")
        if not clinic_id:
            logger.error(f"[TCM] No clinic_id found for {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Clinic not selected. Please start over.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            user_data[whatsapp_number]["module"] = None
            send_interactive_menu(whatsapp_number, supabase)
            return
           
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_any_doctor = user_data[whatsapp_number].get("any_doctor", False)
        service_id = user_data[whatsapp_number].get("service_id")
        current_time = datetime.now()
        current_date = current_time.date()
        is_today = date == current_date.strftime("%Y-%m-%d")
       
        # Check if doctor selection is enabled
        doctor_selection_enabled = get_clinic_doctor_selection(supabase, clinic_id)
       
        logger.info(f"[TCM] Querying hours for {whatsapp_number}, clinic_id: {clinic_id}, doctor_id: {doctor_id}, any_doctor: {is_any_doctor}, period: {period}, on {date}, is_today: {is_today}, doctor_selection_enabled: {doctor_selection_enabled}")
        if period not in ["AM", "PM"]:
            logger.warning(f"[TCM] Invalid period {period} for {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Invalid period selection. Please try again.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "SELECT_DATE"
            get_calendar(whatsapp_number, user_id, supabase, user_data, module_name)
            return
        # Retrieve stored blocks
        am_blocks = user_data[whatsapp_number].get("am_blocks", [])
        pm_blocks = user_data[whatsapp_number].get("pm_blocks", [])
        rows = am_blocks if period == "AM" else pm_blocks
        if not rows:
            logger.warning(f"[TCM] No available hours in {period} for {whatsapp_number} on {date}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "No available hours in this period. Please select another date.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "SELECT_DATE"
            get_calendar(whatsapp_number, user_id, supabase, user_data, module_name)
            return
        payload = {
            "interactive": {
                "type": "list",
                "body": {"text": translate_template(whatsapp_number, "Select an hour range for {}:", supabase).format(date)},
                "action": {
                    "button": translate_template(whatsapp_number, "Choose Hour", supabase),
                    "sections": [{
                        "title": translate_template(whatsapp_number, f"{period} Hours", supabase),
                        "rows": rows
                    }]
                }
            }
        }
        result = send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
        if not result:
            logger.error(f"[TCM] Failed to send hour blocks to {whatsapp_number}. Response: {result}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Unable to fetch hours. Please try again.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            user_data[whatsapp_number]["module"] = None
            send_interactive_menu(whatsapp_number, supabase)
            return
        user_data[whatsapp_number]["state"] = "SELECT_HOUR"
        user_data[whatsapp_number]["module"] = module_name
        logger.info(f"[TCM] Sent hour blocks for {period} to {whatsapp_number}, module: {module_name}")
        # Clean up
        user_data[whatsapp_number].pop("period", None)
        user_data[whatsapp_number].pop("am_blocks", None)
        user_data[whatsapp_number].pop("pm_blocks", None)
    except Exception as e:
        logger.error(f"[TCM] Error in get_available_hours for {whatsapp_number}: {str(e)}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, f"An error occurred while fetching hours: {str(e)}. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "IDLE"
        user_data[whatsapp_number]["module"] = None
        send_interactive_menu(whatsapp_number, supabase)

def get_time_slots(whatsapp_number, user_id, supabase, user_data, module_name):
    """Generate DURATION-BASED slots - BLOCKS existing bookings' FULL duration considering all breaks!"""
    try:
        date = user_data[whatsapp_number]["date"]
        hour = user_data[whatsapp_number]["hour"] # e.g. "09:00-10:45"
        clinic_id = user_data[whatsapp_number].get("clinic_id")
        if not clinic_id:
            logger.error(f"[TCM] No clinic_id found for {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Clinic not selected. Please start over.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            user_data[whatsapp_number]["module"] = None
            send_interactive_menu(whatsapp_number, supabase)
            return
           
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_any_doctor = user_data[whatsapp_number].get("any_doctor", False)
        service_id = user_data[whatsapp_number].get("service_id")
        duration = user_data[whatsapp_number].get("duration_minutes", 30) # <-- service duration
       
        # Check if doctor selection is enabled
        doctor_selection_enabled = get_clinic_doctor_selection(supabase, clinic_id)
        logger.info(f"[TCM] Duration blocking: {whatsapp_number} {duration}min on {date} block {hour}, doctor_selection_enabled: {doctor_selection_enabled}")
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        clinic_schedule = get_clinic_schedule(supabase, clinic_id, date_obj)
        if not clinic_schedule:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, "No available time slots.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "SELECT_HOUR"
            return
        # Helper – parse HH:MM (or HH:MM:SS) into full datetime for the day
        def parse_time(t):
            if not t:
                return None
            if len(t) > 5:
                t = t[:5] # keep only HH:MM
            return datetime.strptime(f"{date} {t}", "%Y-%m-%d %H:%M")
        clinic_start = parse_time(clinic_schedule["start_time"])
        clinic_end = parse_time(clinic_schedule["end_time"])
        lunch_start = parse_time(clinic_schedule["lunch_start"])
        lunch_end = parse_time(clinic_schedule["lunch_end"])
        dinner_start = parse_time(clinic_schedule["dinner_start"])
        dinner_end = parse_time(clinic_schedule["dinner_end"])
       
        # Parse all breaks
        breaks = []
        for break_schedule in clinic_schedule.get("breaks", []):
            break_start = parse_time(break_schedule["start"])
            break_end = parse_time(break_schedule["end"])
            if break_start and break_end:
                breaks.append((break_start, break_end))
        # Check if time slot is during any break
        def is_during_breaks(slot_time):
            # Check lunch break
            if lunch_start and lunch_end and lunch_start <= slot_time < lunch_end:
                return True
            # Check dinner break
            if dinner_start and dinner_end and dinner_start <= slot_time < dinner_end:
                return True
            # Check additional breaks
            for break_start, break_end in breaks:
                if break_start <= slot_time < break_end:
                    return True
            return False
        # Parse the selected 2-hour block (e.g. "09:00-10:45")
        block_start_str, block_end_str = hour.split("-")
        block_start = parse_time(block_start_str)
        block_end = parse_time(block_end_str) + timedelta(minutes=15) # include last slot
        # 1. Gather **all** blocked intervals (including their own duration)
        def blocked_intervals(doctor_filter=None):
            blocked = []
           
            # Query tcm_s_bookings (both confirmed and pending bookings)
            q = supabase.table("tcm_s_bookings").select(
                "original_time, new_time, duration_minutes, doctor_id, status"
            ).eq("original_date", date) \
             .in_("status", ["confirmed", "pending"])
           
            if doctor_filter:
                q = q.eq("doctor_id", doctor_filter)
           
            bookings = q.execute().data
           
            for b in bookings:
                # Check original time
                if b["original_time"]:
                    s = parse_time(b["original_time"])
                    e = s + timedelta(minutes=b["duration_minutes"])
                    blocked.append((s, e, b["doctor_id"]))
               
                # Check new time for rescheduled appointments
                if b["new_time"]:
                    s = parse_time(b["new_time"])
                    e = s + timedelta(minutes=b["duration_minutes"])
                    blocked.append((s, e, b["doctor_id"]))
   
            return blocked
        blocked = blocked_intervals() if is_any_doctor else blocked_intervals(doctor_id)
        # 2. Walk through the block in 15-min steps and test the *full* duration
        slots = []
        cur = block_start
        while cur < block_end:
            slot_str = cur.strftime("%H:%M")
            slot_end = cur + timedelta(minutes=duration) # <-- end of *new* booking
            # ---- basic guards ------------------------------------------------
            if cur < datetime.now(): # past
                cur += timedelta(minutes=15); continue
            if slot_end > clinic_end: # exceeds clinic close
                cur += timedelta(minutes=15); continue
            if is_during_breaks(cur): # during any break
                cur += timedelta(minutes=15); continue
            # ---- overlap with any existing booking (full duration) ----------
            overlap = False
            for bs, be, _ in blocked:
                if cur < be and slot_end > bs: # any intersection → blocked
                    overlap = True
                    break
            if overlap:
                cur += timedelta(minutes=15); continue
            if doctor_selection_enabled:
                # Doctor selection is enabled
                if is_any_doctor:
                    doctors = supabase.table("tcm_a_doctors").select("id").eq("clinic_id", clinic_id).execute().data
                    free = False
                    for d in doctors:
                        d_blocked = any(
                            cur < be and slot_end > bs and bd == d["id"]
                            for bs, be, bd in blocked
                        )
                        if not d_blocked:
                            free = True
                            break
                    if not free:
                        cur += timedelta(minutes=15); continue
                else:
                    # Check if specific doctor is booked
                    doctor_booked = any(
                        cur < be and slot_end > bs and bd == doctor_id
                        for bs, be, bd in blocked
                    )
                    if doctor_booked:
                        cur += timedelta(minutes=15); continue
            else:
                # Doctor selection is disabled - check assigned doctors
                if service_id and service_id != "others":
                    assigned_doctor, reason = get_assigned_doctor_for_slot(
                        service_id, date, slot_str, duration, supabase, clinic_id
                    )
                    if not assigned_doctor:
                        # No assigned doctor available for this slot
                        cur += timedelta(minutes=15); continue
                    else:
                        # Store the assigned doctor for this slot
                        if "assigned_doctors" not in user_data[whatsapp_number]:
                            user_data[whatsapp_number]["assigned_doctors"] = {}
                        user_data[whatsapp_number]["assigned_doctors"][slot_str] = assigned_doctor
            # ---- slot is good ------------------------------------------------
            slots.append(slot_str)
            cur += timedelta(minutes=15)
        # 3. No slots → fallback
        if not slots:
            logger.warning(f"[TCM] No {duration}min slots in block {hour} for {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, "No available time slots.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "SELECT_HOUR"
            get_available_hours(whatsapp_number, user_id, supabase, user_data, module_name)
            return
        # 4. Send interactive list
        payload = {
            "interactive": {
                "type": "list",
                "body": {"text": translate_template(
                    whatsapp_number,
                    "Select {}min slot for {} {}:",
                    supabase
                ).format(duration, date, hour)},
                "action": {
                    "button": translate_template(whatsapp_number, "Choose Slot", supabase),
                    "sections": [{
                        "title": translate_template(whatsapp_number, "{}min Slots", supabase).format(duration),
                        "rows": [{"id": t, "title": t} for t in slots]
                    }]
                }
            }
        }
        send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
        user_data[whatsapp_number]["state"] = "SELECT_TIME_SLOT"
        user_data[whatsapp_number]["module"] = module_name
    except Exception as e:
        logger.error(f"[TCM] Slot error: {str(e)}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, "Error loading slots.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "IDLE"

def get_available_doctors(whatsapp_number, user_id, supabase, user_data, module_name):
    """Confirm the selected doctor or find the best fit doctor for the selected time slot."""
    try:
        date = user_data[whatsapp_number]["date"]
        time_slot = user_data[whatsapp_number].get("time_slot")  # Could be None for non-priority methods
        clinic_id = user_data[whatsapp_number].get("clinic_id")
        if not clinic_id:
            logger.error(f"[TCM] No clinic_id found for {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Clinic not selected. Please start over.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            user_data[whatsapp_number]["module"] = None
            send_interactive_menu(whatsapp_number, supabase)
            return
           
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_any_doctor = user_data[whatsapp_number].get("any_doctor", False)
        service_id = user_data[whatsapp_number].get("service_id")
        duration = user_data[whatsapp_number].get("duration_minutes", 30)
        priority_required = user_data[whatsapp_number].get("priority_required", True)
       
        # Check if doctor selection is enabled
        doctor_selection_enabled = get_clinic_doctor_selection(supabase, clinic_id)
       
        logger.info(f"[TCM] Confirming doctor for {whatsapp_number} on {date} at {time_slot}, clinic_id: {clinic_id}, doctor_selection_enabled: {doctor_selection_enabled}, priority_required: {priority_required}")
       
        if doctor_selection_enabled:
            # Doctor selection is enabled - use selected doctor or find best fit
            if not is_any_doctor and doctor_id:
                # Doctor already selected from user selection
                # Check doctor availability
                if time_slot:
                    # Check specific time slot availability
                    is_available, reason = check_doctor_availability_at_slot(doctor_id, date, time_slot, duration, supabase)
                else:
                    # For non-priority, check if doctor is generally available on the date
                    date_obj = datetime.strptime(date, "%Y-%m-%d")
                    is_available, reason = check_date_availability(date_obj, clinic_id, doctor_id, False, supabase, service_id)
                
                if not is_available:
                    logger.warning(f"[TCM] Selected doctor {doctor_id} not available for {date} {'at ' + time_slot if time_slot else 'on the day'}")
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "Selected doctor not available for this date/time. Please select another.", supabase)}}
                    )
                    if time_slot:
                        user_data[whatsapp_number]["state"] = "SELECT_TIME_SLOT"
                        get_time_slots(whatsapp_number, user_id, supabase, user_data, module_name)
                    else:
                        user_data[whatsapp_number]["state"] = "SELECT_DATE"
                        get_calendar(whatsapp_number, user_id, supabase, user_data, module_name)
                    return
                
                doctor_response = supabase.table("tcm_a_doctors").select("name").eq("id", doctor_id).execute()
                doctor_name = doctor_response.data[0]["name"] if doctor_response.data else "Doctor"
            else:
                # "Any Doctor" was selected OR no specific doctor chosen
                # Need to find the best fit doctor
               
                # Get all doctors from the clinic
                doctors = supabase.table("tcm_a_doctors").select("id, name").eq("clinic_id", clinic_id).execute().data
               
                if not doctors:
                    logger.error(f"[TCM] No doctors found for {whatsapp_number} in clinic {clinic_id}")
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "No doctors available. Please try again later.", supabase)}}
                    )
                    user_data[whatsapp_number]["state"] = "IDLE"
                    user_data[whatsapp_number]["module"] = None
                    send_interactive_menu(whatsapp_number, supabase)
                    return
               
                # Find available doctors and collect their metrics
                available_doctors_metrics = []
               
                for doctor in doctors:
                    d_id = doctor["id"]
                    d_name = doctor["name"]
                   
                    # Check if doctor is available
                    if time_slot:
                        # Check specific time slot availability
                        is_available, reason = check_doctor_availability_at_slot(d_id, date, time_slot, duration, supabase)
                    else:
                        # For non-priority, check if doctor is generally available on the date
                        date_obj = datetime.strptime(date, "%Y-%m-%d")
                        is_available, reason = check_date_availability(date_obj, clinic_id, d_id, False, supabase, service_id)
                   
                    if is_available:
                        # Get existing appointments count for this doctor on this day
                        appointments = supabase.table("tcm_s_bookings").select("id", count="exact") \
                            .eq("doctor_id", d_id) \
                            .eq("original_date", date) \
                            .in_("status", ["confirmed", "pending"]) \
                            .execute()
                        total_appointments = appointments.count or 0
                       
                        # Calculate a score (lower is better) - prioritize doctors with fewer appointments
                        score = total_appointments * 10
                       
                        # Check if this doctor is assigned to the service
                        if service_id and service_id != "others":
                            assigned_doctors, _ = get_service_assigned_doctors(supabase, service_id)
                            if d_id in assigned_doctors:
                                score -= 50 # Priority boost for assigned doctors
                                logger.info(f"[TCM] Doctor {d_id} is service-assigned, giving priority boost")
                       
                        available_doctors_metrics.append({
                            "id": d_id,
                            "name": d_name,
                            "score": score,
                            "total_appointments": total_appointments,
                            "is_service_assigned": (service_id and service_id != "others" and d_id in assigned_doctors)
                        })
               
                if not available_doctors_metrics:
                    logger.warning(f"[TCM] No doctors available for {whatsapp_number} on {date} {'at ' + time_slot if time_slot else 'on the day'}")
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "No doctors available for this date/time. Please select another.", supabase)}}
                    )
                    if time_slot:
                        user_data[whatsapp_number]["state"] = "SELECT_TIME_SLOT"
                        get_time_slots(whatsapp_number, user_id, supabase, user_data, module_name)
                    else:
                        user_data[whatsapp_number]["state"] = "SELECT_DATE"
                        get_calendar(whatsapp_number, user_id, supabase, user_data, module_name)
                    return
               
                # Sort by score (lower is better)
                available_doctors_metrics.sort(key=lambda x: x["score"])
               
                # Select the doctor with the best (lowest) score
                selected_doctor = available_doctors_metrics[0]
                user_data[whatsapp_number]["doctor_id"] = selected_doctor["id"]
                doctor_name = selected_doctor["name"]
               
                logger.info(f"[TCM] Selected best fit doctor {selected_doctor['id']} ({doctor_name}) for {whatsapp_number} {'at ' + time_slot if time_slot else 'on ' + date}")
                logger.info(f"[TCM] Selection metrics - Score: {selected_doctor['score']}, Appointments: {selected_doctor['total_appointments']}, Assigned: {selected_doctor['is_service_assigned']}")
        else:
            # Doctor selection is disabled - use assigned doctor from service
            if service_id and service_id != "others":
                # Check if we already have an assigned doctor for this slot (from get_time_slots)
                assigned_doctors = user_data[whatsapp_number].get("assigned_doctors", {})
                assigned_doctor_id = assigned_doctors.get(time_slot) if time_slot else None
               
                if not assigned_doctor_id:
                    # Find an assigned doctor for this slot or date
                    if time_slot:
                        assigned_doctor_id, reason = get_assigned_doctor_for_slot(
                            service_id, date, time_slot, duration, supabase, clinic_id
                        )
                    else:
                        # For non-priority, find any assigned doctor available on the date
                        doctors = supabase.table("tcm_a_doctors").select("id").eq("clinic_id", clinic_id).execute().data
                        assigned_doctor_ids, _ = get_service_assigned_doctors(supabase, service_id)
                        
                        if assigned_doctor_ids:
                            # Check assigned doctors first
                            for d_id in assigned_doctor_ids:
                                date_obj = datetime.strptime(date, "%Y-%m-%d")
                                is_available, reason = check_date_availability(date_obj, clinic_id, d_id, False, supabase, service_id)
                                if is_available:
                                    assigned_doctor_id = d_id
                                    break
                        
                        if not assigned_doctor_id:
                            # If no assigned doctors available, check any doctor
                            for doctor in doctors:
                                d_id = doctor["id"]
                                date_obj = datetime.strptime(date, "%Y-%m-%d")
                                is_available, reason = check_date_availability(date_obj, clinic_id, d_id, False, supabase, service_id)
                                if is_available:
                                    assigned_doctor_id = d_id
                                    break
               
                if assigned_doctor_id:
                    # Don't show doctor name to patient when doctor selection is disabled
                    doctor_name = "Your assigned doctor" # Generic name
                    user_data[whatsapp_number]["doctor_id"] = assigned_doctor_id
                    logger.info(f"[TCM] Assigned doctor {assigned_doctor_id} for service {service_id} {'at ' + time_slot if time_slot else 'on ' + date} (hidden from patient)")
                else:
                    logger.error(f"[TCM] No assigned doctor available for service {service_id} {'at ' + time_slot if time_slot else 'on ' + date}")
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "No doctors available for this date/time. Please select another.", supabase)}}
                    )
                    if time_slot:
                        user_data[whatsapp_number]["state"] = "SELECT_TIME_SLOT"
                        get_time_slots(whatsapp_number, user_id, supabase, user_data, module_name)
                    else:
                        user_data[whatsapp_number]["state"] = "SELECT_DATE"
                        get_calendar(whatsapp_number, user_id, supabase, user_data, module_name)
                    return
            else:
                # No specific service - use any available doctor
                doctors = supabase.table("tcm_a_doctors").select("id, name").eq("clinic_id", clinic_id).execute().data
                if doctors:
                    # Find first available doctor
                    for doctor in doctors:
                        if time_slot:
                            is_available, reason = check_doctor_availability_at_slot(
                                doctor["id"], date, time_slot, duration, supabase
                            )
                        else:
                            date_obj = datetime.strptime(date, "%Y-%m-%d")
                            is_available, reason = check_date_availability(date_obj, clinic_id, doctor["id"], False, supabase, service_id)
                        
                        if is_available:
                            user_data[whatsapp_number]["doctor_id"] = doctor["id"]
                            doctor_name = doctor["name"]
                            logger.info(f"[TCM] Using available doctor {doctor['id']} for {whatsapp_number}")
                            break
                    else:
                        # No doctor available
                        logger.error(f"[TCM] No doctors available for {whatsapp_number} {'at ' + time_slot if time_slot else 'on ' + date}")
                        send_whatsapp_message(
                            whatsapp_number,
                            "text",
                            {"text": {"body": translate_template(whatsapp_number, "No doctors available for this date/time. Please select another.", supabase)}}
                        )
                        if time_slot:
                            user_data[whatsapp_number]["state"] = "SELECT_TIME_SLOT"
                            get_time_slots(whatsapp_number, user_id, supabase, user_data, module_name)
                        else:
                            user_data[whatsapp_number]["state"] = "SELECT_DATE"
                            get_calendar(whatsapp_number, user_id, supabase, user_data, module_name)
                        return
                else:
                    logger.error(f"[TCM] No doctors found for clinic {clinic_id}")
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "No doctors available. Please contact support.", supabase)}}
                    )
                    user_data[whatsapp_number]["state"] = "IDLE"
                    user_data[whatsapp_number]["module"] = None
                    send_interactive_menu(whatsapp_number, supabase)
                    return
        # Prepare confirmation message
        service_type = user_data[whatsapp_number].get("service_name", "TCM Service")
        details = user_data[whatsapp_number].get("details", service_type)
        # Get reminder_remark and translate it using gt_tt
        reminder_remark = user_data[whatsapp_number].get("reminder_remark")
        translated_reminder = gt_tt(whatsapp_number, reminder_remark, supabase) if reminder_remark else None
        
        # Get method name if exists
        method_name = user_data[whatsapp_number].get("method_name")
        
        # Get address if exists
        address = user_data[whatsapp_number].get("address")
       
        # Prepare confirmation template
        confirmation_lines = []
        confirmation_lines.append(translate_template(whatsapp_number, "Confirm your TCM booking:", supabase))
        confirmation_lines.append(translate_template(whatsapp_number, "• Service: {}", supabase).format(service_type))
        
        # Add method if exists
        if method_name:
            confirmation_lines.append(translate_template(whatsapp_number, "• Method: {}", supabase).format(method_name))
        
        # Add doctor information
        if doctor_selection_enabled:
            confirmation_lines.append(translate_template(whatsapp_number, "• Doctor: {}", supabase).format(doctor_name))
        else:
            confirmation_lines.append(translate_template(whatsapp_number, "• Doctor: Assigned by Clinic", supabase))
        
        confirmation_lines.append(translate_template(whatsapp_number, "• Date: {}", supabase).format(date))
        
        # Add time if exists (priority required)
        if time_slot:
            confirmation_lines.append(translate_template(whatsapp_number, "• Time: {}", supabase).format(time_slot))
        
        confirmation_lines.append(translate_template(whatsapp_number, "• Duration: {} min", supabase).format(duration))
        confirmation_lines.append(translate_template(whatsapp_number, "• Details: {}", supabase).format(details[:50] + "..." if len(details) > 50 else details))
        
        # Add address if exists
        if address:
            confirmation_lines.append(translate_template(whatsapp_number, "• Address: {}", supabase).format(address))
        
        # Add reminder if exists
        if reminder_remark:
            confirmation_lines.append(translate_template(whatsapp_number, "• Reminder: {}", supabase).format(translated_reminder))
        
        # Add non-priority note if applicable
        if not priority_required:
            non_priority_note = translate_template(
                whatsapp_number,
                "Due to the appointment method allowing for doctor flexibility, the doctor will contact you by 10 AM on the selected date. Note: Your booking may be rescheduled, and you may need to go to 'upcoming bookings' to accept or decline the suggested time after notification has been sent to you.",
                supabase
            )
            confirmation_lines.append("")
            confirmation_lines.append(non_priority_note)
       
        confirmation_text = "\n".join(confirmation_lines)
       
        send_whatsapp_message(
            whatsapp_number,
            "interactive",
            {
                "interactive": {
                    "type": "button",
                    "body": {"text": confirmation_text},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": "confirm_booking", "title": translate_template(whatsapp_number, "Confirm", supabase)}},
                            {"type": "reply", "reply": {"id": "edit_booking", "title": translate_template(whatsapp_number, "Edit", supabase)}},
                            {"type": "reply", "reply": {"id": "cancel_booking", "title": translate_template(whatsapp_number, "Cancel", supabase)}}
                        ]
                    }
                }
            }
        )
        user_data[whatsapp_number]["state"] = "CONFIRM_BOOKING"
       
    except Exception as e:
        logger.error(f"[TCM] Error in get_available_doctors for {whatsapp_number}: {str(e)}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "An error occurred while confirming the booking. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "IDLE"
        user_data[whatsapp_number]["module"] = None
        send_interactive_menu(whatsapp_number, supabase)

def handle_confirm_booking_tcm(whatsapp_number, user_id, supabase, user_data, module_name):
    """Confirm booking handler for TCM services - inserts into tcm_s_bookings."""
    try:
        booking_id = str(uuid.uuid4())
       
        # Base fields that every booking needs for TCM schema
        booking_data = {
            "id": booking_id,
            "user_id": user_id,
            "doctor_id": user_data[whatsapp_number]["doctor_id"],
            "booking_type": "consultation", # TCM uses 'consultation' type
            "original_date": user_data[whatsapp_number]["date"],
            "duration_minutes": user_data[whatsapp_number].get("duration_minutes", 30),
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "created_by": user_id,
            "checkin": False
        }
        
        # Add time if exists (could be None for non-priority methods)
        time_slot = user_data[whatsapp_number].get("time_slot")
        if time_slot:
            booking_data["original_time"] = time_slot
        
        # Add address if exists
        address = user_data[whatsapp_number].get("address")
        if address:
            booking_data["address"] = address
        
        # Add method_id if exists
        method_id = user_data[whatsapp_number].get("method_id")
        if method_id:
            booking_data["method_id"] = method_id
        
        # Service-specific fields
        service_id = user_data[whatsapp_number].get("service_id")
        service_name = user_data[whatsapp_number].get("service_name", "TCM Service")
        details = user_data[whatsapp_number].get("details", service_name)
        reminder_remark = user_data[whatsapp_number].get("reminder_remark")
       
        # Add service_id if available
        if service_id and service_id != "others":
            booking_data["service_id"] = service_id
       
        # Add details and reminder
        if reminder_remark:
            booking_data["details"] = f"{details}, {reminder_remark}"
            booking_data["reminder_remark"] = reminder_remark
        else:
            booking_data["details"] = details
       
        # Add reminder duration if present
        if "reminder_duration" in user_data[whatsapp_number]:
            reminder_duration = user_data[whatsapp_number]["reminder_duration"]
            # Check if reminder_duration is not None and is within valid range
            if reminder_duration is not None and 1 <= reminder_duration <= 24: # Validate range
                booking_data["reminder_duration"] = reminder_duration
       
        logger.info(f"[TCM] Inserting booking for {whatsapp_number} into tcm_s_bookings: {booking_data}")
       
        # Insert into tcm_s_bookings
        try:
            response = supabase.table("tcm_s_bookings").insert(booking_data).execute()
            logger.info(f"[TCM] Supabase insert response: {response}")
        except Exception as e:
            logger.error(f"[TCM] Failed to insert booking for {whatsapp_number}: {str(e)}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Failed to save booking. Please try again.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            user_data[whatsapp_number]["module"] = None
            send_interactive_menu(whatsapp_number, supabase)
            return
        if not response.data:
            logger.error(f"[TCM] Failed to insert booking for {whatsapp_number} - no data returned")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Failed to save booking. Please try again.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            user_data[whatsapp_number]["module"] = None
            send_interactive_menu(whatsapp_number, supabase)
            return
        # Confirmation message
        confirmation_lines = []
        confirmation_lines.append(translate_template(whatsapp_number, "✅ Your TCM booking has been submitted!", supabase))
        confirmation_lines.append(translate_template(whatsapp_number, "Service: {}", supabase).format(service_name))
        confirmation_lines.append(translate_template(whatsapp_number, "Date: {}", supabase).format(user_data[whatsapp_number]["date"]))
        
        if time_slot:
            confirmation_lines.append(translate_template(whatsapp_number, "Time: {}", supabase).format(time_slot))
        
        confirmation_lines.append(translate_template(whatsapp_number, "Duration: {} minutes", supabase).format(user_data[whatsapp_number].get('duration_minutes', 30)))
        
        # Add method if exists
        method_name = user_data[whatsapp_number].get("method_name")
        if method_name:
            confirmation_lines.append(translate_template(whatsapp_number, "Method: {}", supabase).format(method_name))
        
        # Add non-priority note if applicable
        priority_required = user_data[whatsapp_number].get("priority_required", True)
        if not priority_required:
            non_priority_note = translate_template(
                whatsapp_number,
                "Due to doctor flexibility, the doctor will contact you by 10 AM on the selected date. Your booking may be rescheduled - please check your upcoming bookings to accept or decline suggested times.",
                supabase
            )
            confirmation_lines.append("")
            confirmation_lines.append(non_priority_note)
        
        confirmation_lines.append(translate_template(whatsapp_number, "Booking is pending approval. You'll be notified once confirmed.", supabase))
        confirmation_lines.append(translate_template(whatsapp_number, "Booking ID: {}", supabase).format(booking_id[:8] + "..."))
        
        confirmation_message = "\n".join(confirmation_lines)
        
        result = send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": confirmation_message}},
            supabase
        )
        if not result:
            logger.error(f"[TCM] Failed to send confirmation to {whatsapp_number}")
            # Try to delete the booking if message failed
            try:
                supabase.table("tcm_s_bookings").delete().eq("id", booking_id).execute()
            except:
                pass
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Failed to send confirmation. Booking cancelled. Please try again.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            user_data[whatsapp_number]["module"] = None
            send_interactive_menu(whatsapp_number, supabase)
            return
        user_data[whatsapp_number]["state"] = "IDLE"
        user_data[whatsapp_number]["module"] = None
        logger.info(f"[TCM] Booking pending approval for {whatsapp_number}, ID: {booking_id}")
        send_interactive_menu(whatsapp_number, supabase)
    except Exception as e:
        logger.error(f"[TCM] Error in handle_confirm_booking_tcm for {whatsapp_number}: {str(e)}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, f"An error occurred while confirming the booking: {str(e)}. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "IDLE"
        user_data[whatsapp_number]["module"] = None
        send_interactive_menu(whatsapp_number, supabase)

def handle_cancel_booking_tcm(whatsapp_number, user_id, supabase, user_data):
    """Handle cancel booking - Clear booking data from user_data and reset state."""
    logger.info(f"[TCM] 👋 User {whatsapp_number} CANCELLED - CLEARING BOOKING DATA")
   
    # Clear booking-related data from user_data
    booking_keys = [
        "doctor_id", "date", "time_slot", "duration_minutes",
        "service_name", "details", "reminder_remark",
        "any_doctor", "clinic_id", "future_date_input", "service_id",
        "service_primary_doctor", "reminder_duration", "doctor_name",
        "assigned_doctors", "method_id", "method_name", "address",
        "address_required", "priority_required"
    ]
    for key in booking_keys:
        user_data[whatsapp_number].pop(key, None)
   
    # Reset user state
    user_data[whatsapp_number]["state"] = "IDLE"
    user_data[whatsapp_number]["module"] = None
   
    # Send confirmation message
    send_whatsapp_message(
        whatsapp_number,
        "text",
        {"text": {"body": translate_template(whatsapp_number, "The TCM booking is not placed", supabase)}}
    )
   
    # Send interactive menu
    send_interactive_menu(whatsapp_number, supabase)
    return True

# ================ EDIT BOOKING FUNCTIONALITY ================
def show_edit_options(whatsapp_number, user_id, supabase, user_data, module_name):
    """Show edit options for the booking."""
    try:
        logger.info(f"[TCM] Showing edit options for {whatsapp_number}, module: {module_name}")
       
        # Create edit options based on module
        edit_options = [
            {"id": "edit_time", "title": translate_template(whatsapp_number, "Change Time", supabase)},
            {"id": "edit_date", "title": translate_template(whatsapp_number, "Change Date", supabase)},
            {"id": "edit_doctor", "title": translate_template(whatsapp_number, "Change Doctor", supabase)}
        ]
       
        # Add module-specific edit options
        if module_name == "tcm_booking":
            edit_options.append({"id": "edit_service", "title": translate_template(whatsapp_number, "Change Service", supabase)})
       
        send_whatsapp_message(
            whatsapp_number,
            "interactive",
            {
                "interactive": {
                    "type": "list",
                    "body": {"text": translate_template(whatsapp_number, "What would you like to edit?", supabase)},
                    "action": {
                        "button": translate_template(whatsapp_number, "Edit Option", supabase),
                        "sections": [{
                            "title": translate_template(whatsapp_number, "Edit Options", supabase),
                            "rows": edit_options[:10] # Limit to 10 options
                        }]
                    }
                }
            }
        )
        user_data[whatsapp_number]["state"] = "EDIT_BOOKING"
       
    except Exception as e:
        logger.error(f"[TCM] Error showing edit options for {whatsapp_number}: {str(e)}")
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error loading edit options. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "CONFIRM_BOOKING"

def handle_edit_choice(whatsapp_number, user_id, supabase, user_data, module_name, edit_choice):
    """Handle user's edit choice."""
    try:
        logger.info(f"[TCM] Handling edit choice for {whatsapp_number}: {edit_choice}")
       
        if edit_choice == "edit_time":
            # Clear time slot and go back to time selection
            user_data[whatsapp_number].pop("time_slot", None)
            user_data[whatsapp_number].pop("parsed_time_input", None)
            user_data[whatsapp_number].pop("closest_available_time", None)
           
            # Check if doctor selection is enabled
            clinic_id = user_data[whatsapp_number].get("clinic_id")
            doctor_selection_enabled = get_clinic_doctor_selection(supabase, clinic_id)
           
            if doctor_selection_enabled:
                # Doctor selection enabled - ask for time input directly
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        "Please enter your preferred time (e.g., 9:30, 2pm, 1430):",
                        supabase
                    )}}
                )
                user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"
            else:
                # Doctor selection disabled - use the period/hour/slot flow
                user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
                select_period(whatsapp_number, user_id, supabase, user_data, module_name)
           
        elif edit_choice == "edit_date":
            # Clear date and time slot, go back to date selection
            user_data[whatsapp_number].pop("date", None)
            user_data[whatsapp_number].pop("time_slot", None)
            user_data[whatsapp_number].pop("parsed_time_input", None)
            user_data[whatsapp_number].pop("closest_available_time", None)
           
            # Show calendar
            get_calendar(whatsapp_number, user_id, supabase, user_data, module_name)
           
        elif edit_choice == "edit_doctor":
            # Clear doctor selection
            user_data[whatsapp_number].pop("doctor_id", None)
            user_data[whatsapp_number].pop("any_doctor", None)
           
            # Show doctors list (only if doctor selection is enabled)
            clinic_id = user_data[whatsapp_number].get("clinic_id")
            doctor_selection_enabled = get_clinic_doctor_selection(supabase, clinic_id)
           
            if doctor_selection_enabled:
                get_available_doctors_for_service(whatsapp_number, user_id, supabase, user_data, module_name)
            else:
                # Doctor selection disabled, can't edit doctor
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Doctor selection is not enabled for this clinic. Please contact the clinic directly for doctor changes.", supabase)}}
                )
                show_edit_options(whatsapp_number, user_id, supabase, user_data, module_name)
           
        elif edit_choice == "edit_service" and module_name == "tcm_booking":
            # Clear service selection and go back to service selection
            user_data[whatsapp_number].pop("service_id", None)
            user_data[whatsapp_number].pop("service_name", None)
            user_data[whatsapp_number].pop("details", None)
            user_data[whatsapp_number].pop("duration_minutes", None)
            user_data[whatsapp_number].pop("assigned_doctors", None)
           
            # Need to go back to service selection
            # This will be handled in app.py based on state and module
            user_data[whatsapp_number]["state"] = "SELECT_SERVICE"
           
        else:
            logger.warning(f"[TCM] Invalid edit choice for {whatsapp_number}: {edit_choice}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Invalid edit option. Please try again.", supabase)}}
            )
            show_edit_options(whatsapp_number, user_id, supabase, user_data, module_name)
           
    except Exception as e:
        logger.error(f"[TCM] Error handling edit choice for {whatsapp_number}: {str(e)}")
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing edit choice. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "CONFIRM_BOOKING"

# ================ TIME INPUT HANDLING FUNCTIONS ================
def parse_time_input(time_str):
    """Parse various time input formats and convert to HH:MM format (24-hour)."""
    try:
        if not time_str or not isinstance(time_str, str):
            return None
           
        # Remove whitespace and convert to lowercase
        time_str = time_str.strip().lower()
       
        # Remove any dots at the end
        time_str = time_str.rstrip('.')
       
        # Handle AM/PM variations
        has_am = False
        has_pm = False
       
        # Check for AM/PM indicators (more comprehensive)
        am_patterns = ['a.m.', 'a.m', 'am', 'a']
        pm_patterns = ['p.m.', 'p.m', 'pm', 'p']
       
        for pattern in am_patterns:
            if pattern in time_str:
                has_am = True
                time_str = time_str.replace(pattern, '')
                break
               
        if not has_am:
            for pattern in pm_patterns:
                if pattern in time_str:
                    has_pm = True
                    time_str = time_str.replace(pattern, '')
                    break
       
        # Remove all non-digit characters except colon and dot
        time_str = re.sub(r'[^0-9:.]', '', time_str)
       
        # If empty after cleaning, return None
        if not time_str:
            return None
       
        # Replace dots with colons for consistent parsing
        time_str = time_str.replace('.', ':')
       
        # Handle different formats
        # Case 1: Has colon separator (e.g., "9:30", "14:00")
        if ':' in time_str:
            parts = time_str.split(':')
            if len(parts) == 2:
                hour_str = parts[0]
                minute_str = parts[1]
               
                # Pad single digit hour
                if len(hour_str) == 1:
                    hour_str = '0' + hour_str
               
                # Pad minute if needed
                if len(minute_str) == 1:
                    minute_str = minute_str + '0'
                elif len(minute_str) > 2:
                    minute_str = minute_str[:2]
               
                hour = int(hour_str)
                minute = int(minute_str[:2])
               
                # Validate
                if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                    return None
               
                # Handle AM/PM conversion
                return convert_12_to_24_hour(hour, minute, has_am, has_pm)
       
        # Case 2: No separator (e.g., "0930", "1400", "9", "14")
        elif time_str.isdigit():
            length = len(time_str)
           
            if length == 4: # HHMM format
                hour = int(time_str[:2])
                minute = int(time_str[2:])
               
                # Validate
                if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                    return None
               
                return convert_12_to_24_hour(hour, minute, has_am, has_pm)
               
            elif length == 3: # HMM format (e.g., "930" for 9:30)
                hour = int(time_str[0])
                minute = int(time_str[1:])
               
                # Validate minute
                if minute < 0 or minute > 59:
                    return None
               
                return convert_12_to_24_hour(hour, minute, has_am, has_pm)
               
            elif length == 2: # HH format
                hour = int(time_str)
                minute = 0
               
                # Validate hour
                if hour < 0 or hour > 23:
                    return None
               
                return convert_12_to_24_hour(hour, minute, has_am, has_pm)
               
            elif length == 1: # H format
                hour = int(time_str)
                minute = 0
               
                return convert_12_to_24_hour(hour, minute, has_am, has_pm)
       
        return None
       
    except Exception as e:
        logger.error(f"[TCM] Error parsing time input '{time_str}': {str(e)}")
        return None

def convert_12_to_24_hour(hour, minute, has_am, has_pm):
    """Convert 12-hour format to 24-hour format."""
    # If no AM/PM specified, assume 24-hour format
    if not has_am and not has_pm:
        # If hour is 0-11 and we have no AM/PM, could be ambiguous
        # But we'll assume 24-hour format for consistency
        if hour == 12:
            hour = 12 # 12:00 in 24-hour is 12:00
        elif hour > 12 and hour <= 23:
            # Already in 24-hour format
            pass
        # hour 0-11 stays as is in 24-hour format
   
    # Handle AM
    elif has_am:
        if hour == 12:
            hour = 0 # 12 AM = 00
        elif hour > 12:
            return None # Invalid for AM
        # hour 1-11 stays as is
   
    # Handle PM
    elif has_pm:
        if hour == 12:
            hour = 12 # 12 PM = 12
        elif hour < 12:
            hour += 12
   
    return f"{hour:02d}:{minute:02d}"

def format_time_for_display(time_str):
    """Convert 24-hour time to 12-hour format with AM/PM."""
    try:
        if not time_str:
            return ""
       
        # Parse the time
        hour, minute = map(int, time_str.split(':'))
       
        # Convert to 12-hour format
        if hour == 0:
            return f"12:{minute:02d} AM"
        elif hour < 12:
            return f"{hour}:{minute:02d} AM"
        elif hour == 12:
            return f"12:{minute:02d} PM"
        else:
            return f"{hour-12}:{minute:02d} PM"
           
    except Exception as e:
        logger.error(f"[TCM] Error formatting time '{time_str}': {str(e)}")
        return time_str

def round_to_15_minutes(time_str):
    """Round time to nearest 15-minute interval."""
    try:
        hour, minute = map(int, time_str.split(':'))
       
        # Calculate remainder
        remainder = minute % 15
       
        if remainder == 0:
            # Already on 15-minute interval
            return f"{hour:02d}:{minute:02d}"
        elif remainder <= 7:
            # Round down
            minute = minute - remainder
        else:
            # Round up
            minute = minute + (15 - remainder)
            if minute >= 60:
                hour += 1
                minute = 0
                if hour >= 24:
                    hour = 0
       
        return f"{hour:02d}:{minute:02d}"
       
    except Exception as e:
        logger.error(f"[TCM] Error rounding time '{time_str}': {str(e)}")
        return time_str

def get_all_available_slots_for_day(date, clinic_id, doctor_id, is_any_doctor, duration, supabase):
    """Get all available 15-minute time slots for a specific day."""
    try:
        # Get clinic schedule
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        clinic_schedule = get_clinic_schedule(supabase, clinic_id, date_obj)
        if not clinic_schedule:
            return []
       
        # Helper function to parse time
        def parse_time(t):
            if not t:
                return None
            if len(t) > 5:
                t = t[:5] # keep only HH:MM
            return datetime.strptime(f"{date} {t}", "%Y-%m-%d %H:%M")
       
        clinic_start = parse_time(clinic_schedule["start_time"])
        clinic_end = parse_time(clinic_schedule["end_time"])
        lunch_start = parse_time(clinic_schedule["lunch_start"])
        lunch_end = parse_time(clinic_schedule["lunch_end"])
        dinner_start = parse_time(clinic_schedule["dinner_start"])
        dinner_end = parse_time(clinic_schedule["dinner_end"])
       
        # Parse all breaks
        breaks = []
        for break_schedule in clinic_schedule.get("breaks", []):
            break_start = parse_time(break_schedule["start"])
            break_end = parse_time(break_schedule["end"])
            if break_start and break_end:
                breaks.append((break_start, break_end))
       
        # Check if time slot is during any break
        def is_during_breaks(slot_time):
            # Check lunch break
            if lunch_start and lunch_end and lunch_start <= slot_time < lunch_end:
                return True
            # Check dinner break
            if dinner_start and dinner_end and dinner_start <= slot_time < dinner_end:
                return True
            # Check additional breaks
            for break_start, break_end in breaks:
                if break_start <= slot_time < break_end:
                    return True
            return False
       
        # Generate all possible 15-minute slots
        all_slots = []
        current = clinic_start
       
        while current < clinic_end:
            slot_str = current.strftime("%H:%M")
            slot_end = current + timedelta(minutes=duration)
           
            # Check if slot is valid
            if slot_end > clinic_end:
                current += timedelta(minutes=15)
                continue
           
            if is_during_breaks(current):
                current += timedelta(minutes=15)
                continue
           
            # Check availability for this slot
            is_available, _ = check_slot_availability_tcm(
                date, slot_str, clinic_id, doctor_id, is_any_doctor, duration, supabase
            )
           
            if is_available:
                all_slots.append(slot_str)
           
            current += timedelta(minutes=15)
       
        return all_slots
       
    except Exception as e:
        logger.error(f"[TCM] Error getting all slots for {date}: {str(e)}")
        return []

def check_slot_availability_tcm(date, time_slot, clinic_id, doctor_id, is_any_doctor, duration, supabase):
    """Check if a specific time slot is available for TCM."""
    try:
        slot_time = datetime.strptime(f"{date} {time_slot}", "%Y-%m-%d %H:%M")
        slot_end = slot_time + timedelta(minutes=duration)
       
        # Check clinic schedule
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        clinic_schedule = get_clinic_schedule(supabase, clinic_id, date_obj)
        if not clinic_schedule:
            return False, "clinic_closed"
       
        # Helper function to parse time
        def parse_time(t):
            if not t:
                return None
            if len(t) > 5:
                t = t[:5] # keep only HH:MM
            return datetime.strptime(f"{date} {t}", "%Y-%m-%d %H:%M")
       
        clinic_start = parse_time(clinic_schedule["start_time"])
        clinic_end = parse_time(clinic_schedule["end_time"])
        lunch_start = parse_time(clinic_schedule["lunch_start"])
        lunch_end = parse_time(clinic_schedule["lunch_end"])
        dinner_start = parse_time(clinic_schedule["dinner_start"])
        dinner_end = parse_time(clinic_schedule["dinner_end"])
       
        # Parse all breaks
        breaks = []
        for break_schedule in clinic_schedule.get("breaks", []):
            break_start = parse_time(break_schedule["start"])
            break_end = parse_time(break_schedule["end"])
            if break_start and break_end:
                breaks.append((break_start, break_end))
       
        # Check if time slot is during any break
        def is_during_breaks(slot_time):
            # Check lunch break
            if lunch_start and lunch_end and lunch_start <= slot_time < lunch_end:
                return True
            # Check dinner break
            if dinner_start and dinner_end and dinner_start <= slot_time < dinner_end:
                return True
            # Check additional breaks
            for break_start, break_end in breaks:
                if break_start <= slot_time < break_end:
                    return True
            return False
       
        # Check if slot is within clinic hours and not during breaks
        if slot_time < clinic_start or slot_end > clinic_end:
            return False, "outside_clinic_hours"
       
        if is_during_breaks(slot_time):
            return False, "during_break"
       
        # Check doctor availability
        if not is_any_doctor and doctor_id:
            # Check specific doctor
            is_available, reason = check_doctor_availability_at_slot(
                doctor_id, date, time_slot, duration, supabase
            )
            return is_available, reason
        else:
            # Check any doctor
            doctors = supabase.table("tcm_a_doctors").select("id").eq("clinic_id", clinic_id).execute().data
           
            for doctor in doctors:
                is_available, reason = check_doctor_availability_at_slot(
                    doctor["id"], date, time_slot, duration, supabase
                )
                if is_available:
                    return True, "available"
           
            return False, "no_available_doctors"
       
    except Exception as e:
        logger.error(f"[TCM] Error checking slot availability: {str(e)}")
        return False, "error"

def find_closest_available_time(whatsapp_number, user_id, supabase, user_data, module_name, target_time_str):
    """Find the closest available time slot to the user's input time."""
    try:
        date = user_data[whatsapp_number]["date"]
        clinic_id = user_data[whatsapp_number].get("clinic_id")
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_any_doctor = user_data[whatsapp_number].get("any_doctor", False)
        duration = user_data[whatsapp_number].get("duration_minutes", 30)
       
        logger.info(f"[TCM] Finding closest time to {target_time_str} for {whatsapp_number} on {date}")
       
        # Parse target time
        target_hour, target_minute = map(int, target_time_str.split(':'))
        target_datetime = datetime.strptime(f"{date} {target_time_str}", "%Y-%m-%d %H:%M")
       
        # Get clinic schedule
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        clinic_schedule = get_clinic_schedule(supabase, clinic_id, date_obj)
        if not clinic_schedule:
            return None, None
       
        # Get all available time slots for the day
        all_slots = get_all_available_slots_for_day(date, clinic_id, doctor_id, is_any_doctor, duration, supabase)
       
        if not all_slots:
            return None, None
       
        # Find closest slot
        closest_slot = None
        min_difference = timedelta.max
       
        for slot in all_slots:
            slot_datetime = datetime.strptime(f"{date} {slot}", "%Y-%m-%d %H:%M")
            difference = abs(slot_datetime - target_datetime)
           
            if difference < min_difference:
                min_difference = difference
                closest_slot = slot
       
        return closest_slot, min_difference
       
    except Exception as e:
        logger.error(f"[TCM] Error finding closest time for {whatsapp_number}: {str(e)}")
        return None, None

def handle_time_input(whatsapp_number, user_id, supabase, user_data, module_name, time_input):
    """Handle time input from user and find the closest available slot."""
    try:
        # Parse the time input
        parsed_time = parse_time_input(time_input)
       
        if not parsed_time:
            # Send error message and ask if they want to try again or get help
            send_whatsapp_message(
                whatsapp_number,
                "interactive",
                {
                    "interactive": {
                        "type": "button",
                        "body": {"text": translate_template(
                            whatsapp_number,
                            "I couldn't understand the time format. Please try entering the time again, or let me help you choose from available slots.",
                            supabase
                        )},
                        "action": {
                            "buttons": [
                                {"type": "reply", "reply": {"id": "try_again_time", "title": translate_template(whatsapp_number, "Try Again", supabase)}},
                                {"type": "reply", "reply": {"id": "help_choose_time", "title": translate_template(whatsapp_number, "Help Me Choose", supabase)}}
                            ]
                        }
                    }
                }
            )
            user_data[whatsapp_number]["state"] = "RETRY_TIME_OR_HELP"
            return
       
        # Round to nearest 15-minute interval
        rounded_time = round_to_15_minutes(parsed_time)
       
        # Store the parsed time
        user_data[whatsapp_number]["parsed_time_input"] = rounded_time
        formatted_display_time = format_time_for_display(rounded_time)
       
        # Check if the time is available
        date = user_data[whatsapp_number]["date"]
        clinic_id = user_data[whatsapp_number].get("clinic_id")
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_any_doctor = user_data[whatsapp_number].get("any_doctor", False)
        duration = user_data[whatsapp_number].get("duration_minutes", 30)
       
        # Check if doctor selection is enabled
        doctor_selection_enabled = get_clinic_doctor_selection(supabase, clinic_id)
       
        if doctor_selection_enabled:
            is_available, reason = check_slot_availability_tcm(
                date, rounded_time, clinic_id, doctor_id, is_any_doctor, duration, supabase
            )
        else:
            # Doctor selection disabled - check if any doctor can be assigned
            service_id = user_data[whatsapp_number].get("service_id")
            assigned_doctor, reason = get_assigned_doctor_for_slot(
                service_id, date, rounded_time, duration, supabase, clinic_id
            )
            is_available = assigned_doctor is not None
       
        if is_available:
            # Time is available, store it and proceed to confirmation
            user_data[whatsapp_number]["time_slot"] = rounded_time
            
            # 1. Get the translated shell from the dictionary (Static Key)
            shell = translate_template(whatsapp_number, "Great! {} is available. Is this the time you want?", supabase)
            
            # 2. Format it with the variable (Dynamic Data)
            final_text = shell.format(formatted_display_time)
            
            # 3. Build the payload
            payload = {
                "interactive": {
                    "type": "button",
                    "body": {"text": final_text},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": "confirm_time", "title": translate_template(whatsapp_number, "Yes", supabase)}},
                            {"type": "reply", "reply": {"id": "find_another_time", "title": translate_template(whatsapp_number, "Find Another", supabase)}}
                        ]
                    }
                }
            }
            send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
            user_data[whatsapp_number]["state"] = "CONFIRM_TIME"
           
        else:
            # Time not available, find closest available time
            closest_slot, difference = find_closest_available_time(
                whatsapp_number, user_id, supabase, user_data, module_name, rounded_time
            )
           
            if closest_slot:
                formatted_closest = format_time_for_display(closest_slot)
               
                # Calculate time difference in minutes
                minutes_diff = int(difference.total_seconds() / 60)
               
                # Store closest slot for potential use
                user_data[whatsapp_number]["closest_available_time"] = closest_slot
               
                # Log for debugging
                logger.info(f"[TCM] Closest time found for {whatsapp_number}: {closest_slot} (original: {rounded_time}, diff: {minutes_diff}min)")
               
                # Ask if they want the closest time
                if minutes_diff <= 30:
                    message = translate_template(
                        whatsapp_number,
                        f"Unfortunately {formatted_display_time} is not available. The closest available time is {formatted_closest} (just {minutes_diff} minutes difference). Would you like to book this instead?",
                        supabase
                    )
                else:
                    message = translate_template(
                        whatsapp_number,
                        f"Unfortunately {formatted_display_time} is not available. The closest available time is {formatted_closest}. Would you like to book this instead?",
                        supabase
                    )
               
                send_whatsapp_message(
                    whatsapp_number,
                    "interactive",
                    {
                        "interactive": {
                            "type": "button",
                            "body": {"text": message},
                            "action": {
                                "buttons": [
                                    {"type": "reply", "reply": {"id": "accept_closest_time", "title": translate_template(whatsapp_number, "Yes", supabase)}},
                                    {"type": "reply", "reply": {"id": "find_another_time", "title": translate_template(whatsapp_number, "Find Another", supabase)}}
                                ]
                            }
                        }
                    }
                )
                user_data[whatsapp_number]["state"] = "CONFIRM_CLOSEST_TIME"
                logger.info(f"[TCM] Set state to CONFIRM_CLOSEST_TIME for {whatsapp_number}")
            else:
                # No available slots at all
                send_whatsapp_message(
                    whatsapp_number,
                    "interactive",
                    {
                        "interactive": {
                            "type": "button",
                            "body": {"text": translate_template(
                                whatsapp_number,
                                f"No available slots near {formatted_display_time}. Would you like to try a different time or let me help you choose from available slots?",
                                supabase
                            )},
                            "action": {
                                "buttons": [
                                    {"type": "reply", "reply": {"id": "try_again_time", "title": translate_template(whatsapp_number, "Try Another Time", supabase)}},
                                    {"type": "reply", "reply": {"id": "help_choose_time", "title": translate_template(whatsapp_number, "Help Me Choose", supabase)}}
                                ]
                            }
                        }
                    }
                )
                user_data[whatsapp_number]["state"] = "RETRY_TIME_OR_HELP"
                       
    except Exception as e:
        logger.error(f"[TCM] Error handling time input for {whatsapp_number}: {str(e)}")
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing time. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"

def handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, module_name, confirmed=True, use_closest=False):
    """Handle confirmation of time selection."""
    try:
        logger.info(f"[TCM] handle_time_confirmation called for {whatsapp_number}, confirmed={confirmed}, use_closest={use_closest}")
        logger.info(f"[TCM] Current state: {user_data[whatsapp_number].get('state')}, module: {module_name}")
       
        if use_closest:
            # User accepted the closest available time
            closest_time = user_data[whatsapp_number].get("closest_available_time")
            logger.info(f"[TCM] use_closest=True, closest_time from user_data: {closest_time}")
           
            if closest_time:
                user_data[whatsapp_number]["time_slot"] = closest_time
                logger.info(f"[TCM] Set time_slot to: {closest_time}")
               
                # Clean up
                user_data[whatsapp_number].pop("parsed_time_input", None)
                user_data[whatsapp_number].pop("closest_available_time", None)
               
                # Proceed to booking confirmation
                get_available_doctors(whatsapp_number, user_id, supabase, user_data, module_name)
            else:
                logger.error(f"[TCM] No closest_available_time found for {whatsapp_number}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Time slot not found. Please try again.", supabase)}}
                )
                user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"
       
        elif confirmed:
            # User confirmed their selected time
            parsed_time = user_data[whatsapp_number].get("parsed_time_input")
            logger.info(f"[TCM] confirmed=True, parsed_time from user_data: {parsed_time}")
           
            if parsed_time:
                user_data[whatsapp_number]["time_slot"] = parsed_time
                logger.info(f"[TCM] Set time_slot to: {parsed_time}")
               
                # Clean up
                user_data[whatsapp_number].pop("parsed_time_input", None)
                user_data[whatsapp_number].pop("closest_available_time", None)
               
                # Proceed to booking confirmation
                get_available_doctors(whatsapp_number, user_id, supabase, user_data, module_name)
            else:
                logger.error(f"[TCM] No parsed_time_input found for {whatsapp_number}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Time slot not found. Please try again.", supabase)}}
                )
                user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"
       
        else:
            # User wants to find another time
            logger.info(f"[TCM] User wants to find another time for {whatsapp_number}")
            user_data[whatsapp_number].pop("parsed_time_input", None)
            user_data[whatsapp_number].pop("closest_available_time", None)
           
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "Please enter your preferred time (e.g., 9:30, 2pm, 1430):",
                    supabase
                )}}
            )
            user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"
           
    except Exception as e:
        logger.error(f"[TCM] Error handling time confirmation for {whatsapp_number}: {str(e)}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error confirming time. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"

def handle_retry_time_or_help(whatsapp_number, user_id, supabase, user_data, module_name, choice):
    """Handle user choice to retry time input or get help choosing."""
    try:
        if choice == "try_again_time":
            # User wants to try entering time again
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "Please enter your preferred time (e.g., 9:30, 2pm, 1430):",
                    supabase
                )}}
            )
            user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"
           
        elif choice == "help_choose_time":
            # User wants help choosing (fall back to period selection)
            select_period(whatsapp_number, user_id, supabase, user_data, module_name)
           
    except Exception as e:
        logger.error(f"[TCM] Error handling retry/help choice for {whatsapp_number}: {str(e)}")
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing choice. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"