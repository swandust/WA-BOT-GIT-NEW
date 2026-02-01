import logging
import uuid
import re
from datetime import datetime, timedelta
from utils import send_whatsapp_message, send_interactive_menu, translate_template, gt_tt, gt_t_tt, gt_dt_tt

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache for unavailable slots
unavailable_slots_cache = {}

# New time input parsing functions
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
            
            if length == 4:  # HHMM format
                hour = int(time_str[:2])
                minute = int(time_str[2:])
                
                # Validate
                if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                    return None
                
                return convert_12_to_24_hour(hour, minute, has_am, has_pm)
                
            elif length == 3:  # HMM format (e.g., "930" for 9:30)
                hour = int(time_str[0])
                minute = int(time_str[1:])
                
                # Validate minute
                if minute < 0 or minute > 59:
                    return None
                
                return convert_12_to_24_hour(hour, minute, has_am, has_pm)
                
            elif length == 2:  # HH format
                hour = int(time_str)
                minute = 0
                
                # Validate hour
                if hour < 0 or hour > 23:
                    return None
                
                return convert_12_to_24_hour(hour, minute, has_am, has_pm)
                
            elif length == 1:  # H format
                hour = int(time_str)
                minute = 0
                
                return convert_12_to_24_hour(hour, minute, has_am, has_pm)
        
        return None
        
    except Exception as e:
        logger.error(f"Error parsing time input '{time_str}': {str(e)}")
        return None

def convert_12_to_24_hour(hour, minute, has_am, has_pm):
    """Convert 12-hour format to 24-hour format."""
    # If no AM/PM specified, assume 24-hour format
    if not has_am and not has_pm:
        # If hour is 0-11 and we have no AM/PM, could be ambiguous
        # But we'll assume 24-hour format for consistency
        if hour == 12:
            hour = 12  # 12:00 in 24-hour is 12:00
        elif hour > 12 and hour <= 23:
            # Already in 24-hour format
            pass
        # hour 0-11 stays as is in 24-hour format
    
    # Handle AM
    elif has_am:
        if hour == 12:
            hour = 0  # 12 AM = 00
        elif hour > 12:
            return None  # Invalid for AM
        # hour 1-11 stays as is
    
    # Handle PM
    elif has_pm:
        if hour == 12:
            hour = 12  # 12 PM = 12
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
        logger.error(f"Error formatting time '{time_str}': {str(e)}")
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
        logger.error(f"Error rounding time '{time_str}': {str(e)}")
        return time_str

def find_closest_available_time(whatsapp_number, user_id, supabase, user_data, module_name, target_time_str):
    """Find the closest available time slot to the user's input time."""
    try:
        date = user_data[whatsapp_number]["date"]
        clinic_id = user_data[whatsapp_number].get("clinic_id", "76d39438-a2c4-4e79-83e8-000000000000")
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_any_doctor = user_data[whatsapp_number].get("any_doctor", False)
        duration = user_data[whatsapp_number].get("duration_minutes", 30)
        
        logger.info(f"Finding closest time to {target_time_str} for {whatsapp_number} on {date}")
        
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
        logger.error(f"Error finding closest time for {whatsapp_number}: {str(e)}")
        return None, None

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
            t = t[:5]  # keep only HH:MM
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
            is_available, _ = check_slot_availability(
                date, slot_str, clinic_id, doctor_id, is_any_doctor, duration, supabase
            )
            
            if is_available:
                all_slots.append(slot_str)
            
            current += timedelta(minutes=15)
        
        return all_slots
        
    except Exception as e:
        logger.error(f"Error getting all slots for {date}: {str(e)}")
        return []

def check_slot_availability(date, time_slot, clinic_id, doctor_id, is_any_doctor, duration, supabase):
    """Check if a specific time slot is available."""
    try:
        slot_time = datetime.strptime(f"{date} {time_slot}", "%Y-%m-%d %H:%M")
        slot_end = slot_time + timedelta(minutes=duration)
        
        # Check doctor unavailability
        if not is_any_doctor:
            unavailability = supabase.table("c_a_doctor_unavailability").select("start_time, end_time").eq("doctor_id", doctor_id).eq("date", date).execute().data
            for u in unavailability:
                u_start = datetime.strptime(f"{date} {u['start_time']}", "%Y-%m-%d %H:%M")
                u_end = datetime.strptime(f"{date} {u['end_time']}", "%Y-%m-%d %H:%M")
                if slot_time < u_end and slot_end > u_start:
                    return False, "doctor_unavailable"
        
        # Check existing bookings
        tables = ["c_s_checkup", "c_s_consultation", "c_s_vaccination", "c_s_pending_bookings"]
        for table in tables:
            if is_any_doctor:
                bookings = supabase.table(table).select("time, duration_minutes, doctor_id").eq("date", date).execute().data
            else:
                bookings = supabase.table(table).select("time, duration_minutes").eq("doctor_id", doctor_id).eq("date", date).execute().data
            
            for b in bookings:
                b_start = datetime.strptime(f"{date} {b['time']}", "%Y-%m-%d %H:%M")
                b_end = b_start + timedelta(minutes=b["duration_minutes"])
                if slot_time < b_end and slot_end > b_start:
                    return False, "slot_booked"
        
        # Check reschedule requests
        if is_any_doctor:
            reschedule_bookings = supabase.table("c_s_reschedule_requests").select("new_time, duration_minutes, doctor_id").eq("new_date", date).eq("status", "confirmed").execute().data
        else:
            reschedule_bookings = supabase.table("c_s_reschedule_requests").select("new_time, duration_minutes").eq("doctor_id", doctor_id).eq("new_date", date).eq("status", "confirmed").execute().data
        
        for r in reschedule_bookings:
            r_start = datetime.strptime(f"{date} {r['new_time']}", "%Y-%m-%d %H:%M")
            r_end = r_start + timedelta(minutes=r["duration_minutes"])
            if slot_time < r_end and slot_end > r_start:
                return False, "slot_booked"
        
        # For "any doctor", check if at least one doctor is available
        if is_any_doctor:
            doctors = supabase.table("c_a_doctors").select("id").eq("clinic_id", clinic_id).execute().data
            
            for doctor in doctors:
                # Check if this specific doctor is available
                is_available, _ = check_slot_availability(
                    date, time_slot, clinic_id, doctor["id"], False, duration, supabase
                )
                if is_available:
                    return True, "available"
            
            return False, "no_available_doctors"
        
        return True, "available"
        
    except Exception as e:
        logger.error(f"Error checking slot availability: {str(e)}")
        return False, "error"

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
                                {"type": "reply", "reply": {"id": "try_again_time", "title": gt_t_tt(whatsapp_number, "Try Again", supabase)}},
                                {"type": "reply", "reply": {"id": "help_choose_time", "title": gt_t_tt(whatsapp_number, "Help Me Choose", supabase)}}
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
        clinic_id = user_data[whatsapp_number].get("clinic_id", "76d39438-a2c4-4e79-83e8-000000000000")
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_any_doctor = user_data[whatsapp_number].get("any_doctor", False)
        duration = user_data[whatsapp_number].get("duration_minutes", 30)
        
        is_available, reason = check_slot_availability(
            date, rounded_time, clinic_id, doctor_id, is_any_doctor, duration, supabase
        )
        
        if is_available:
            # Time is available, store it and proceed to doctor selection/confirmation
            user_data[whatsapp_number]["time_slot"] = rounded_time
            
            # Ask for confirmation
            send_whatsapp_message(
                whatsapp_number,
                "interactive",
                {
                    "interactive": {
                        "type": "button",
                        "body": {"text": translate_template(
                            whatsapp_number,
                            f"Great! {formatted_display_time} is available. Is this the time you want?",
                            supabase
                        )},
                        "action": {
                            "buttons": [
                                {"type": "reply", "reply": {"id": "confirm_time", "title": gt_t_tt(whatsapp_number, "Yes", supabase)}},
                                {"type": "reply", "reply": {"id": "find_another_time", "title": gt_t_tt(whatsapp_number, "Find Another", supabase)}}
                            ]
                        }
                    }
                }
            )
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
                logger.info(f"Closest time found for {whatsapp_number}: {closest_slot} (original: {rounded_time}, diff: {minutes_diff}min)")
                
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
                                    {"type": "reply", "reply": {"id": "accept_closest_time", "title": gt_t_tt(whatsapp_number, "Yes", supabase)}},
                                    {"type": "reply", "reply": {"id": "find_another_time", "title": gt_t_tt(whatsapp_number, "Find Another", supabase)}}
                                ]
                            }
                        }
                    }
                )
                user_data[whatsapp_number]["state"] = "CONFIRM_CLOSEST_TIME"
                logger.info(f"Set state to CONFIRM_CLOSEST_TIME for {whatsapp_number}")
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
                                    {"type": "reply", "reply": {"id": "try_again_time", "title": gt_t_tt(whatsapp_number, "Try Another Time", supabase)}},
                                    {"type": "reply", "reply": {"id": "help_choose_time", "title": gt_t_tt(whatsapp_number, "Help Me Choose", supabase)}}
                                ]
                            }
                        }
                    }
                )
                user_data[whatsapp_number]["state"] = "RETRY_TIME_OR_HELP"
                
    except Exception as e:
        logger.error(f"Error handling time input for {whatsapp_number}: {str(e)}")
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing time. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"

# Modified version of get_doctors function that can be called after time selection
def get_doctors_for_confirmation(whatsapp_number, user_id, supabase, user_data, module_name):
    """Get doctors after time selection for confirmation."""
    try:
        # Similar to original get_doctors but for confirmation flow
        clinic_id = user_data[whatsapp_number].get("clinic_id", "76d39438-a2c4-4e79-83e8-000000000000")
        service_id = user_data[whatsapp_number].get("service_id")
        
        # Check if service has a specific doctor assigned
        specific_doctor_id = None
        service_has_doctor = False
        
        if service_id and service_id != "others":
            try:
                service_response = supabase.table("c_a_clinic_service") \
                    .select("doctor_id") \
                    .eq("id", service_id) \
                    .eq("clinic_id", clinic_id) \
                    .eq("is_active", True) \
                    .execute()
                
                if service_response.data:
                    doctor_id_from_service = service_response.data[0].get("doctor_id")
                    if doctor_id_from_service:
                        specific_doctor_id = doctor_id_from_service
                        service_has_doctor = True
                else:
                    service_has_doctor = False
            except Exception as e:
                logger.error(f"Error checking service doctor assignment: {e}")
                service_has_doctor = False
        
        # If service has a specific doctor assigned, ONLY show that doctor and "Any Doctor" option
        if service_has_doctor and specific_doctor_id:
            doctor_response = supabase.table("c_a_doctors") \
                .select("id, name") \
                .eq("id", specific_doctor_id) \
                .eq("clinic_id", clinic_id) \
                .execute()
            
            if doctor_response.data:
                doctor = doctor_response.data[0]
                # Keep doctor name in English (don't translate)
                doctor_list = [{
                    "id": str(doctor["id"]),
                    "title": doctor["name"][:21] + "..." if len(doctor["name"]) > 21 else doctor["name"]
                }]
            else:
                doctors = supabase.table("c_a_doctors").select("id, name").eq("clinic_id", clinic_id).execute().data
                if not doctors:
                    logger.error(f"No doctors found for clinic {clinic_id}")
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "No doctors available. Please contact support.", supabase)}}
                    )
                    user_data[whatsapp_number]["state"] = "IDLE"
                    user_data[whatsapp_number]["module"] = None
                    send_interactive_menu(whatsapp_number, supabase)
                    return
                
                doctor_list = [
                    {
                        "id": str(d["id"]),
                        # Keep doctor names in English
                        "title": d["name"][:21] + "..." if len(d["name"]) > 21 else d["name"]
                    }
                    for d in doctors
                ]
        else:
            doctors = supabase.table("c_a_doctors").select("id, name").eq("clinic_id", clinic_id).execute().data
            if not doctors:
                logger.error(f"No doctors found for clinic {clinic_id}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "No doctors available. Please contact support.", supabase)}}
                )
                user_data[whatsapp_number]["state"] = "IDLE"
                user_data[whatsapp_number]["module"] = None
                send_interactive_menu(whatsapp_number, supabase)
                return

            doctor_list = [
                {
                    "id": str(d["id"]),
                    # Keep doctor names in English
                    "title": d["name"][:21] + "..." if len(d["name"]) > 21 else d["name"]
                }
                for d in doctors
            ]
        
        # Always add "Any Doctor" option
        doctor_list.append({
            "id": "any_doctor",
            "title": gt_t_tt(whatsapp_number, "Any Doctor", supabase)
        })
        
        # Limit to 10 rows max
        doctor_list = doctor_list[:10]

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
                        "button": gt_t_tt(whatsapp_number, "Choose Doctor", supabase),
                        "sections": [{
                            "title": gt_t_tt(whatsapp_number, "Available Doctors", supabase),
                            "rows": doctor_list
                        }]
                    }
                }
            },
            supabase
        )
        
        if not result:
            logger.error(f"Failed to send doctor list to {whatsapp_number}")
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

    except Exception as e:
        logger.error(f"Error in get_doctors_for_confirmation for {whatsapp_number}: {str(e)}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, f"An error occurred while fetching doctors: {str(e)}. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "IDLE"
        user_data[whatsapp_number]["module"] = None
        send_interactive_menu(whatsapp_number, supabase)

def handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, module_name, confirmed=True, use_closest=False):
    """Handle confirmation of time selection."""
    try:
        logger.info(f"handle_time_confirmation called for {whatsapp_number}, confirmed={confirmed}, use_closest={use_closest}")
        logger.info(f"Current state: {user_data[whatsapp_number].get('state')}, module: {module_name}")
        logger.info(f"User data keys: {list(user_data[whatsapp_number].keys())}")
        
        if use_closest:
            # User accepted the closest available time
            closest_time = user_data[whatsapp_number].get("closest_available_time")
            logger.info(f"use_closest=True, closest_time from user_data: {closest_time}")
            
            if closest_time:
                user_data[whatsapp_number]["time_slot"] = closest_time
                logger.info(f"Set time_slot to: {closest_time}")
                
                # Clean up
                user_data[whatsapp_number].pop("parsed_time_input", None)
                user_data[whatsapp_number].pop("closest_available_time", None)
                
                # Check what we have in user_data
                doctor_id = user_data[whatsapp_number].get("doctor_id")
                any_doctor = user_data[whatsapp_number].get("any_doctor", False)
                logger.info(f"Doctor info - doctor_id: {doctor_id}, any_doctor: {any_doctor}")
                
                # Always proceed to booking confirmation since doctor is already selected
                # (as per workflow: doctor selection is step 1)
                logger.info(f"Proceeding to get_available_doctors for final confirmation")
                get_available_doctors(whatsapp_number, user_id, supabase, user_data, module_name)
            else:
                logger.error(f"No closest_available_time found for {whatsapp_number}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Time slot not found. Please try again.", supabase)}}
                )
                user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"
        
        elif confirmed:
            # User confirmed their selected time
            parsed_time = user_data[whatsapp_number].get("parsed_time_input")
            logger.info(f"confirmed=True, parsed_time from user_data: {parsed_time}")
            
            if parsed_time:
                user_data[whatsapp_number]["time_slot"] = parsed_time
                logger.info(f"Set time_slot to: {parsed_time}")
                
                # Clean up
                user_data[whatsapp_number].pop("parsed_time_input", None)
                user_data[whatsapp_number].pop("closest_available_time", None)
                
                # Always proceed to booking confirmation since doctor is already selected
                logger.info(f"Proceeding to get_available_doctors for final confirmation")
                get_available_doctors(whatsapp_number, user_id, supabase, user_data, module_name)
            else:
                logger.error(f"No parsed_time_input found for {whatsapp_number}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Time slot not found. Please try again.", supabase)}}
                )
                user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"
        
        else:
            # User wants to find another time
            logger.info(f"User wants to find another time for {whatsapp_number}")
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
        logger.error(f"Error handling time confirmation for {whatsapp_number}: {str(e)}", exc_info=True)
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
            # User wants help choosing (fall back to AM/PM selection)
            select_period(whatsapp_number, user_id, supabase, user_data, module_name)
            
    except Exception as e:
        logger.error(f"Error handling retry/help choice for {whatsapp_number}: {str(e)}")
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing choice. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"

# Original functions from the provided code
def get_doctors(whatsapp_number, user_id, supabase, user_data, module_name):
    """Generate a list of doctors with an 'Any Doctor' option for the selected clinic."""
    try:
        logger.info(f"Querying doctors for {whatsapp_number}")
        
        # Get clinic ID from user data
        clinic_id = user_data[whatsapp_number].get("clinic_id", "76d39438-a2c4-4e79-83e8-000000000000")
        user_data[whatsapp_number]["clinic_id"] = clinic_id
        
        # Get service ID to check if a specific doctor is assigned
        service_id = user_data[whatsapp_number].get("service_id")
        
        # Check if service has a specific doctor assigned in clinic_service table
        specific_doctor_id = None
        service_has_doctor = False
        
        if service_id and service_id != "others":
            try:
                service_response = supabase.table("c_a_clinic_service") \
                    .select("doctor_id") \
                    .eq("id", service_id) \
                    .eq("clinic_id", clinic_id) \
                    .eq("is_active", True) \
                    .execute()
                
                if service_response.data:
                    doctor_id_from_service = service_response.data[0].get("doctor_id")
                    # Check if doctor_id exists and is not null
                    if doctor_id_from_service:
                        specific_doctor_id = doctor_id_from_service
                        service_has_doctor = True
                        logger.info(f"Service {service_id} has assigned doctor {specific_doctor_id}")
                        # Store for potential later use
                        user_data[whatsapp_number]["service_doctor_id"] = specific_doctor_id
                    else:
                        service_has_doctor = False
                        logger.info(f"Service {service_id} has no assigned doctor (doctor_id is null)")
                else:
                    logger.info(f"Service {service_id} not found in c_a_clinic_service or not active")
                    service_has_doctor = False
            except Exception as e:
                logger.error(f"Error checking service doctor assignment: {e}")
                service_has_doctor = False
        else:
            logger.info(f"No service ID or 'others' selected, showing all doctors")
            service_has_doctor = False
        
        # If service has a specific doctor assigned, ONLY show that doctor and "Any Doctor" option
        if service_has_doctor and specific_doctor_id:
            logger.info(f"Service has assigned doctor {specific_doctor_id}, only showing that doctor")
            
            # Get the specific doctor's details
            doctor_response = supabase.table("c_a_doctors") \
                .select("id, name") \
                .eq("id", specific_doctor_id) \
                .eq("clinic_id", clinic_id) \
                .execute()
            
            if doctor_response.data:
                # Only show the assigned doctor
                doctor = doctor_response.data[0]
                # Keep doctor name in English
                doctor_list = [{
                    "id": str(doctor["id"]),
                    "title": doctor["name"][:21] + "..." if len(doctor["name"]) > 21 else doctor["name"]
                }]
            else:
                logger.warning(f"Assigned doctor {specific_doctor_id} not found, showing all doctors")
                # Fallback: get all doctors if assigned doctor not found
                doctors = supabase.table("c_a_doctors").select("id, name").eq("clinic_id", clinic_id).execute().data
                if not doctors:
                    logger.error(f"No doctors found for clinic {clinic_id}")
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "No doctors available. Please contact support.", supabase)}}
                    )
                    user_data[whatsapp_number]["state"] = "IDLE"
                    user_data[whatsapp_number]["module"] = None
                    send_interactive_menu(whatsapp_number, supabase)
                    return
                
                doctor_list = [
                    {
                        "id": str(d["id"]),
                        # Keep doctor names in English
                        "title": d["name"][:21] + "..." if len(d["name"]) > 21 else d["name"]
                    }
                    for d in doctors
                ]
        else:
            # No specific doctor assigned to service OR service not in c_a_clinic_service OR service_id is "others"
            # Show all doctors from the clinic
            logger.info(f"Service {service_id} has no assigned doctor (or 'others' selected), showing all doctors from clinic {clinic_id}")
            
            doctors = supabase.table("c_a_doctors").select("id, name").eq("clinic_id", clinic_id).execute().data
            logger.info(f"Doctors for clinic {clinic_id}: {doctors}")
            
            if not doctors:
                logger.error(f"No doctors found for clinic {clinic_id}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "No doctors available. Please contact support.", supabase)}}
                )
                user_data[whatsapp_number]["state"] = "IDLE"
                user_data[whatsapp_number]["module"] = None
                send_interactive_menu(whatsapp_number, supabase)
                return

            doctor_list = [
                {
                    "id": str(d["id"]),
                    # Keep doctor names in English
                    "title": d["name"][:21] + "..." if len(d["name"]) > 21 else d["name"]
                }
                for d in doctors
            ]
        
        # Always add "Any Doctor" option
        doctor_list.append({
            "id": "any_doctor",
            "title": gt_t_tt(whatsapp_number, "Any Doctor", supabase)
        })
        
        # Limit to 10 rows max (WhatsApp limit)
        doctor_list = doctor_list[:10]
        logger.info(f"Doctor list for {whatsapp_number}: {[d['title'] for d in doctor_list]}")

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
                        "button": gt_t_tt(whatsapp_number, "Choose Doctor", supabase),
                        "sections": [{
                            "title": gt_t_tt(whatsapp_number, "Available Doctors", supabase),
                            "rows": doctor_list
                        }]
                    }
                }
            },
            supabase
        )
        if not result:
            logger.error(f"Failed to send doctor list to {whatsapp_number}. Response: {result}")
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
        logger.info(f"Sent doctor list to {whatsapp_number}, module: {module_name}")

    except Exception as e:
        logger.error(f"Error in get_doctors for {whatsapp_number}: {str(e)}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, f"An error occurred while fetching doctors: {str(e)}. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "IDLE"
        user_data[whatsapp_number]["module"] = None
        send_interactive_menu(whatsapp_number, supabase)


def get_clinic_schedule(supabase, clinic_id, date):
    """Fetch clinic schedule for a given date including all breaks."""
    try:
        date_str = date.strftime("%Y-%m-%d")
        day_name = date.strftime("%A").lower()
        day_key = "public_holiday" if day_name == "public holiday" else day_name

        response = supabase.table("c_a_clinic_available_time").select("*").eq("clinic_id", clinic_id).execute()
        logger.info(f"Supabase response for clinic_id {clinic_id}: {response}")
        schedule = response.data[0] if response.data and len(response.data) > 0 else None

        if not schedule:
            logger.error(f"No schedule found for clinic_id: {clinic_id} on {date_str}")
            return None

        if schedule.get("holiday_self_declared") and date_str in schedule["holiday_self_declared"]:
            logger.info(f"Date {date_str} is a self-declared holiday for clinic_id: {clinic_id}")
            return None

        special_dates = schedule.get("special_dates", [])
        if special_dates is None:
            special_dates = []
        if isinstance(special_dates, str):
            import json
            special_dates = json.loads(special_dates)
        for sd in special_dates:
            if sd.get("date") == date_str:
                if not sd.get("start_time") or not sd.get("end_time"):
                    logger.info(f"Special date {date_str} has no valid hours (null start_time or end_time)")
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
            logger.info(f"Clinic is closed on {day_name} ({date_str}) due to null start_time or end_time")
            return None

        logger.info(f"Schedule for {day_name} ({date_str}): start={start_time}, end={end_time}, lunch={lunch_start}-{lunch_end}, dinner={dinner_start}-{dinner_end}, breaks={len(breaks)}")
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
        logger.error(f"Error fetching clinic schedule for {clinic_id} on {date_str}: {str(e)}", exc_info=True)
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
            year += 2000  # Assume 20xx for 2-digit years
            
        # Validate date
        if 1 <= month <= 12 and 1 <= day <= 31 and year >= 2024:
            date_obj = datetime(year, month, day)
            # Check if the date is valid (e.g., not Feb 30)
            if date_obj.day == day and date_obj.month == month and date_obj.year == year:
                return date_obj
                
    except Exception as e:
        logger.error(f"Error parsing date {date_str}: {str(e)}")
        
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

def check_date_availability(date_obj, clinic_id, doctor_id, is_any_doctor, supabase):
    """Check if a specific date is available for booking."""
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
            t = t[:5]  # keep only HH:MM
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
            doctors = supabase.table("c_a_doctors").select("id").eq("clinic_id", clinic_id).execute().data
            for slot_time, slot_str in time_slots:
                unavailability = supabase.table("c_a_doctor_unavailability").select("doctor_id, start_time, end_time").eq("date", date_str).execute().data
                unavailable_doctor_ids = {
                    u["doctor_id"] for u in unavailability
                    if datetime.strptime(f"{date_str} {u['start_time']}", "%Y-%m-%d %H:%M") <= slot_time < datetime.strptime(f"{date_str} {u['end_time']}", "%Y-%m-%d %H:%M")
                }
                booked_doctor_ids = set()
                # Check all booking tables including c_s_vaccination
                for table in ["c_s_checkup", "c_s_consultation", "c_s_vaccination", "c_s_pending_bookings"]:
                    bookings = supabase.table(table).select("doctor_id").eq("date", date_str).eq("time", slot_str).execute().data
                    booked_doctor_ids.update(b["doctor_id"] for b in bookings)
                reschedule_bookings = supabase.table("c_s_reschedule_requests").select("doctor_id").eq("new_date", date_str).eq("new_time", slot_str).eq("status", "confirmed").execute().data
                booked_doctor_ids.update(b["doctor_id"] for b in reschedule_bookings)
                if any(d["id"] not in unavailable_doctor_ids and d["id"] not in booked_doctor_ids for d in doctors):
                    return True, "available"
        else:
            for slot_time, slot_str in time_slots:
                unavailability = supabase.table("c_a_doctor_unavailability").select("start_time, end_time").eq("doctor_id", doctor_id).eq("date", date_str).execute().data
                is_unavailable = any(
                    datetime.strptime(f"{date_str} {u['start_time']}", "%Y-%m-%d %H:%M") <= slot_time < datetime.strptime(f"{date_str} {u['end_time']}", "%Y-%m-%d %H:%M")
                    for u in unavailability
                )
                if is_unavailable:
                    continue
                is_booked = False
                # Check all booking tables including c_s_vaccination
                for table in ["c_s_checkup", "c_s_consultation", "c_s_vaccination", "c_s_pending_bookings"]:
                    bookings = supabase.table(table).select("id").eq("doctor_id", doctor_id).eq("date", date_str).eq("time", slot_str).execute().data
                    if bookings:
                        is_booked = True
                        break
                reschedule_bookings = supabase.table("c_s_reschedule_requests").select("id").eq("doctor_id", doctor_id).eq("new_date", date_str).eq("new_time", slot_str).eq("status", "confirmed").execute().data
                if reschedule_bookings:
                    is_booked = True
                if not is_booked:
                    return True, "available"

        return False, "no_available_doctors"

    except Exception as e:
        logger.error(f"Error checking date availability: {str(e)}")
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
                            {"type": "reply", "reply": {"id": "confirm_future_date", "title": gt_t_tt(whatsapp_number, "Yes", supabase)}},
                            {"type": "reply", "reply": {"id": "reject_future_date", "title": gt_t_tt(whatsapp_number, "No", supabase)}}
                        ]
                    }
                }
            }
        )
        user_data[whatsapp_number]["state"] = "CONFIRM_FUTURE_DATE"

    except Exception as e:
        logger.error(f"Error handling future date input for {whatsapp_number}: {str(e)}")
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

        clinic_id = user_data[whatsapp_number].get("clinic_id", "76d39438-a2c4-4e79-83e8-000000000000")
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_any_doctor = user_data[whatsapp_number].get("any_doctor", False)

        # Check if the date is available
        is_available, reason = check_date_availability(date_obj, clinic_id, doctor_id, is_any_doctor, supabase)
        
        if is_available:
            # Date is available, proceed to next step
            user_data[whatsapp_number]["date"] = date_obj.strftime("%Y-%m-%d")
            user_data[whatsapp_number].pop("future_date_input", None)

            if module_name == "view_booking":
                # Reschedule flow continues with the standard period -> hour -> time slots path.
                user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
                select_period(whatsapp_number, user_id, supabase, user_data, module_name)
            else:
                # Default flow uses free-form time input.
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
            # Date not available, suggest nearest dates
            formatted_date_short = format_date_for_button(date_obj)
            nearest_dates = find_nearest_available_dates(date_obj, clinic_id, doctor_id, is_any_doctor, supabase)
            
            if nearest_dates:
                # Create buttons for nearest dates using DD/MM/YYYY format
                date_rows = []
                for i, near_date in enumerate(nearest_dates[:8]):  # Max 8 dates
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
                                "button": gt_t_tt(whatsapp_number, "Choose Date", supabase),
                                "sections": [{
                                    "title": gt_t_tt(whatsapp_number, "Available Dates", supabase),
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
        logger.error(f"Error handling future date confirmation for {whatsapp_number}: {str(e)}")
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
        clinic_id = user_data[whatsapp_number].get("clinic_id", "76d39438-a2c4-4e79-83e8-000000000000")
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_any_doctor = user_data[whatsapp_number].get("any_doctor", False)
        
        logger.info(f"Querying calendar for {whatsapp_number}, clinic_id: {clinic_id}, doctor_id: {doctor_id}, any_doctor: {is_any_doctor}, from {start_date} to {end_date}")

        available_dates = []
        for i in range(14):
            date = start_date + timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            # Use translate_template for day names
            day_name = date.strftime("%A")
            translated_day = translate_template(whatsapp_number, day_name, supabase)
            display_str = f"{date.strftime('%d-%m-%Y')} ({translated_day})"

            clinic_schedule = get_clinic_schedule(supabase, clinic_id, date)
            if not clinic_schedule:
                logger.info(f"Clinic is closed on {date_str}")
                continue

            try:
                start_time = datetime.strptime(f"{date_str} {clinic_schedule['start_time']}", "%Y-%m-%d %H:%M")
                logger.info(f"Parsed start_time {clinic_schedule['start_time']} for {date_str} with format %Y-%m-%d %H:%M")
            except ValueError:
                try:
                    start_time = datetime.strptime(f"{date_str} {clinic_schedule['start_time']}", "%Y-%m-%d %H:%M:%S")
                    logger.info(f"Parsed start_time {clinic_schedule['start_time']} for {date_str} with format %Y-%m-%d %H:%M:%S")
                except ValueError as e:
                    logger.error(f"Failed to parse start_time {clinic_schedule['start_time']} for {date_str}: {str(e)}")
                    continue

            try:
                end_time = datetime.strptime(f"{date_str} {clinic_schedule['end_time']}", "%Y-%m-%d %H:%M")
                logger.info(f"Parsed end_time {clinic_schedule['end_time']} for {date_str} with format %Y-%m-%d %H:%M")
            except ValueError:
                try:
                    end_time = datetime.strptime(f"{date_str} {clinic_schedule['end_time']}", "%Y-%m-%d %H:%M:%S")
                    logger.info(f"Parsed end_time {clinic_schedule['end_time']} for {date_str} with format %Y-%m-d %H:%M:%S")
                except ValueError as e:
                    logger.error(f"Failed to parse end_time {clinic_schedule['end_time']} for {date_str}: {str(e)}")
                    continue

            lunch_start = None
            if clinic_schedule["lunch_start"]:
                try:
                    lunch_start = datetime.strptime(f"{date_str} {clinic_schedule['lunch_start']}", "%Y-%m-%d %H:%M")
                    logger.info(f"Parsed lunch_start {clinic_schedule['lunch_start']} for {date_str} with format %Y-%m-%d %H:%M")
                except ValueError:
                    try:
                        lunch_start = datetime.strptime(f"{date_str} {clinic_schedule['lunch_start']}", "%Y-%m-%d %H:%M:%S")
                        logger.info(f"Parsed lunch_start {clinic_schedule['lunch_start']} for {date_str} with format %Y-%m-%d %H:%M:%S")
                    except ValueError as e:
                        logger.error(f"Failed to parse lunch_start {clinic_schedule['lunch_start']} for {date_str}: {str(e)}")
                        lunch_start = None

            lunch_end = None
            if clinic_schedule["lunch_end"]:
                try:
                    lunch_end = datetime.strptime(f"{date_str} {clinic_schedule['lunch_end']}", "%Y-%m-%d %H:%M")
                    logger.info(f"Parsed lunch_end {clinic_schedule['lunch_end']} for {date_str} with format %Y-%m-%d %H:%M")
                except ValueError:
                    try:
                        lunch_end = datetime.strptime(f"{date_str} {clinic_schedule['lunch_end']}", "%Y-%m-%d %H:%M:%S")
                        logger.info(f"Parsed lunch_end {clinic_schedule['lunch_end']} for {date_str} with format %Y-%m-%d %H:%M:%S")
                    except ValueError as e:
                        logger.error(f"Failed to parse lunch_end {clinic_schedule['lunch_end']} for {date_str}: {str(e)}")
                        lunch_end = None

            total_duration = end_time - start_time
            lunch_duration = (lunch_end - lunch_start) if lunch_start and lunch_end else timedelta(0)
            available_duration = total_duration - lunch_duration
            if available_duration <= timedelta(0):
                logger.info(f"No available time slots for {date_str}")
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
                logger.info(f"No available time slots for {date_str}")
                continue

            if is_any_doctor:
                doctors = supabase.table("c_a_doctors").select("id").eq("clinic_id", clinic_id).execute().data
                has_available_slot = False
                for slot_time, slot_str in time_slots:
                    unavailability = supabase.table("c_a_doctor_unavailability").select("doctor_id, start_time, end_time").eq("date", date_str).execute().data
                    unavailable_doctor_ids = {
                        u["doctor_id"] for u in unavailability
                        if datetime.strptime(f"{date_str} {u['start_time']}", "%Y-%m-%d %H:%M") <= slot_time < datetime.strptime(f"{date_str} {u['end_time']}", "%Y-%m-%d %H:%M")
                    }
                    booked_doctor_ids = set()
                    # Check all booking tables including c_s_vaccination
                    for table in ["c_s_checkup", "c_s_consultation", "c_s_vaccination", "c_s_pending_bookings"]:
                        bookings = supabase.table(table).select("doctor_id").eq("date", date_str).eq("time", slot_str).execute().data
                        booked_doctor_ids.update(b["doctor_id"] for b in bookings)
                    reschedule_bookings = supabase.table("c_s_reschedule_requests").select("doctor_id").eq("new_date", date_str).eq("new_time", slot_str).eq("status", "confirmed").execute().data
                    booked_doctor_ids.update(b["doctor_id"] for b in reschedule_bookings)
                    if any(d["id"] not in unavailable_doctor_ids and d["id"] not in booked_doctor_ids for d in doctors):
                        has_available_slot = True
                        break
                if has_available_slot:
                    available_dates.append({"id": date_str, "title": display_str})
            else:
                has_available_slot = False
                for slot_time, slot_str in time_slots:
                    unavailability = supabase.table("c_a_doctor_unavailability").select("start_time, end_time").eq("doctor_id", doctor_id).eq("date", date_str).execute().data
                    is_unavailable = any(
                        datetime.strptime(f"{date_str} {u['start_time']}", "%Y-%m-%d %H:%M") <= slot_time < datetime.strptime(f"{date_str} {u['end_time']}", "%Y-%m-%d %H:%M")
                        for u in unavailability
                    )
                    if is_unavailable:
                        continue
                    is_booked = False
                    # Check all booking tables including c_s_vaccination
                    for table in ["c_s_checkup", "c_s_consultation", "c_s_vaccination", "c_s_pending_bookings"]:
                        bookings = supabase.table(table).select("id").eq("doctor_id", doctor_id).eq("date", date_str).eq("time", slot_str).execute().data
                        if bookings:
                            is_booked = True
                            break
                    reschedule_bookings = supabase.table("c_s_reschedule_requests").select("id").eq("doctor_id", doctor_id).eq("new_date", date_str).eq("new_time", slot_str).eq("status", "confirmed").execute().data
                    if reschedule_bookings:
                        is_booked = True
                    if not is_booked:
                        has_available_slot = True
                        break
                if has_available_slot:
                    available_dates.append({"id": date_str, "title": display_str})

        # Add Future Date option - FIXED: Always reserve 1 slot for Future Date
        # Only show maximum 9 available dates to leave room for Future Date option
        display_dates = available_dates[:9]  # Take only first 9 available dates
        
        # Add Future Date option
        display_dates.append({
            "id": "future_date",
            "title": gt_t_tt(whatsapp_number, "📅 Future Date", supabase)
        })

        if not display_dates:
            logger.warning(f"No available dates for {whatsapp_number} from {start_date} to {end_date}")
            error_text = translate_template(
                whatsapp_number,
                "No available dates in the next 14 days. Please {}.",
                supabase
            ).format(
                gt_tt(whatsapp_number, "select another doctor", supabase) if not is_any_doctor else gt_tt(whatsapp_number, "try again later", supabase)
            )
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": error_text}}
            )
            if not is_any_doctor:
                user_data[whatsapp_number]["state"] = "SELECT_DOCTOR"
                get_doctors(whatsapp_number, user_id, supabase, user_data, module_name)
            else:
                user_data[whatsapp_number]["state"] = "IDLE"
                user_data[whatsapp_number]["module"] = None
                send_interactive_menu(whatsapp_number, supabase)
            return

        logger.info(f"Available dates for {whatsapp_number}: {[d['title'] for d in display_dates]}")

        result = send_whatsapp_message(
            whatsapp_number,
            "interactive",
            {
                "interactive": {
                    "type": "list",
                    "body": {"text": translate_template(whatsapp_number, "Select a date for your appointment:", supabase)},
                    "action": {
                        "button": gt_t_tt(whatsapp_number, "Choose Date", supabase),
                        "sections": [{
                            "title": gt_t_tt(whatsapp_number, "Available Dates", supabase),
                            "rows": display_dates  # Use display_dates instead of available_dates[:10]
                        }]
                    }
                }
            },
            supabase
        )
        if not result:
            logger.error(f"Failed to send calendar to {whatsapp_number}. Response: {result}")
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
        logger.info(f"Sent calendar to {whatsapp_number}, module: {module_name}")

    except Exception as e:
        logger.error(f"Error in get_calendar for {whatsapp_number}: {str(e)}", exc_info=True)
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
        clinic_id = user_data[whatsapp_number].get("clinic_id", "76d39438-a2c4-4e79-83e8-000000000000")
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_any_doctor = user_data[whatsapp_number].get("any_doctor", False)
        current_time = datetime.now()
        current_date = current_time.date()
        is_today = date == current_date.strftime("%Y-%m-%d")
        logger.info(f"Prompting period selection for {whatsapp_number}, clinic_id: {clinic_id}, doctor_id: {doctor_id}, any_doctor: {is_any_doctor}, on {date}, is_today: {is_today}")

        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        clinic_schedule = get_clinic_schedule(supabase, clinic_id, date_obj)
        if not clinic_schedule:
            logger.warning(f"No clinic schedule available for {whatsapp_number} on {date}")
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
            t = t[:5]  # keep only HH:MM
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
                        
                    if is_any_doctor:
                        doctors = supabase.table("c_a_doctors").select("id").eq("clinic_id", clinic_id).execute().data
                        unavailability = supabase.table("c_a_doctor_unavailability").select("doctor_id, start_time, end_time").eq("date", date).execute().data
                        unavailable_doctor_ids = {
                            u["doctor_id"] for u in unavailability
                            if datetime.strptime(f"{date} {u['start_time']}", "%Y-%m-%d %H:%M") <= slot_time < datetime.strptime(f"{date} {u['end_time']}", "%Y-%m-%d %H:%M")
                        }
                        booked_doctor_ids = set()
                        # Check all booking tables including c_s_vaccination
                        for table in ["c_s_checkup", "c_s_consultation", "c_s_vaccination", "c_s_pending_bookings"]:
                            bookings = supabase.table(table).select("doctor_id").eq("date", date).eq("time", slot_str).execute().data
                            booked_doctor_ids.update(b["doctor_id"] for b in bookings)
                        reschedule_bookings = supabase.table("c_s_reschedule_requests").select("doctor_id").eq("new_date", date).eq("new_time", slot_str).eq("status", "confirmed").execute().data
                        booked_doctor_ids.update(b["doctor_id"] for b in reschedule_bookings)
                        if any(d["id"] not in unavailable_doctor_ids and d["id"] not in booked_doctor_ids for d in doctors):
                            has_available_slot = True
                            break
                    else:
                        unavailability = supabase.table("c_a_doctor_unavailability").select("start_time, end_time").eq("doctor_id", doctor_id).eq("date", date).execute().data
                        is_unavailable = any(
                            datetime.strptime(f"{date} {u['start_time']}", "%Y-%m-%d %H:%M") <= slot_time < datetime.strptime(f"{date} {u['end_time']}", "%Y-%m-%d %H:%M")
                            for u in unavailability
                        )
                        if is_unavailable:
                            continue
                        is_booked = False
                        # Check all booking tables including c_s_vaccination
                        for table in ["c_s_checkup", "c_s_consultation", "c_s_vaccination", "c_s_pending_bookings"]:
                            bookings = supabase.table(table).select("id").eq("doctor_id", doctor_id).eq("date", date).eq("time", slot_str).execute().data
                            if bookings:
                                is_booked = True
                                break
                        reschedule_bookings = supabase.table("c_s_reschedule_requests").select("id").eq("doctor_id", doctor_id).eq("new_date", date).eq("new_time", slot_str).eq("status", "confirmed").execute().data
                        if reschedule_bookings:
                            is_booked = True
                        if not is_booked:
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
            logger.warning(f"No available hours for {whatsapp_number} on {date}")
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
            buttons.append({"type": "reply", "reply": {"id": "AM", "title": gt_t_tt(whatsapp_number, "AM", supabase)}})
        if pm_blocks:
            buttons.append({"type": "reply", "reply": {"id": "PM", "title": gt_t_tt(whatsapp_number, "PM", supabase)}})

        payload = {
            "interactive": {
                "type": "button",
                "body": {"text": gt_tt(whatsapp_number, "Select AM or PM for {}:", supabase).format(date)},
                "action": {
                    "buttons": buttons
                }
            }
        }
        result = send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
        if not result:
            logger.error(f"Failed to send period selection to {whatsapp_number}. Response: {result}")
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
        logger.info(f"Sent period selection to {whatsapp_number}, module: {module_name}")

    except Exception as e:
        logger.error(f"Error in select_period for {whatsapp_number}: {str(e)}", exc_info=True)
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
        clinic_id = user_data[whatsapp_number].get("clinic_id", "76d39438-a2c4-4e79-83e8-000000000000")
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_any_doctor = user_data[whatsapp_number].get("any_doctor", False)
        current_time = datetime.now()
        current_date = current_time.date()
        is_today = date == current_date.strftime("%Y-%m-%d")
        logger.info(f"Querying hours for {whatsapp_number}, clinic_id: {clinic_id}, doctor_id: {doctor_id}, any_doctor: {is_any_doctor}, period: {period}, on {date}, is_today: {is_today}")

        if period not in ["AM", "PM"]:
            logger.warning(f"Invalid period {period} for {whatsapp_number}")
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
            logger.warning(f"No available hours in {period} for {whatsapp_number} on {date}")
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
                "body": {"text": gt_tt(whatsapp_number, "Select an hour range for {}:", supabase).format(date)},
                "action": {
                    "button": gt_t_tt(whatsapp_number, "Choose Hour", supabase),
                    "sections": [{
                        "title": gt_t_tt(whatsapp_number, f"{period} Hours", supabase),
                        "rows": rows
                    }]
                }
            }
        }
        result = send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
        if not result:
            logger.error(f"Failed to send hour blocks to {whatsapp_number}. Response: {result}")
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
        logger.info(f"Sent hour blocks for {period} to {whatsapp_number}, module: {module_name}")

        # Clean up
        user_data[whatsapp_number].pop("period", None)
        user_data[whatsapp_number].pop("am_blocks", None)
        user_data[whatsapp_number].pop("pm_blocks", None)

    except Exception as e:
        logger.error(f"Error in get_available_hours for {whatsapp_number}: {str(e)}", exc_info=True)
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
        hour = user_data[whatsapp_number]["hour"]          # e.g. "09:00-10:45"
        clinic_id = user_data[whatsapp_number].get("clinic_id", "76d39438-a2c4-4e79-83e8-000000000000")
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_any_doctor = user_data[whatsapp_number].get("any_doctor", False)
        duration = user_data[whatsapp_number].get("duration_minutes", 30)   # <-- service duration

        logger.info(f"Duration blocking: {whatsapp_number} {duration}min on {date} block {hour}")

        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        clinic_schedule = get_clinic_schedule(supabase, clinic_id, date_obj)
        if not clinic_schedule:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, "No available time slots.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "SELECT_HOUR"
            return

        # ------------------------------------------------------------------ #
        # Helper – parse HH:MM (or HH:MM:SS) into full datetime for the day
        # ------------------------------------------------------------------ #
        def parse_time(t):
            if not t:
                return None
            t = t[:5]                     # keep only HH:MM
            return datetime.strptime(f"{date} {t}", "%Y-%m-%d %H:%M")

        clinic_start = parse_time(clinic_schedule["start_time"])
        clinic_end   = parse_time(clinic_schedule["end_time"])
        lunch_start  = parse_time(clinic_schedule["lunch_start"])
        lunch_end    = parse_time(clinic_schedule["lunch_end"])
        dinner_start = parse_time(clinic_schedule["dinner_start"])
        dinner_end   = parse_time(clinic_schedule["dinner_end"])
        
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

        # ------------------------------------------------------------------ #
        # Parse the selected 2-hour block (e.g. "09:00-10:45")
        # ------------------------------------------------------------------ #
        block_start_str, block_end_str = hour.split("-")
        block_start = parse_time(block_start_str)
        block_end   = parse_time(block_end_str) + timedelta(minutes=15)   # include last slot

        # ------------------------------------------------------------------ #
        # 1. Gather **all** blocked intervals (including their own duration)
        # ------------------------------------------------------------------ #
        def blocked_intervals(doctor_filter=None):
            blocked = []
            tables = ["c_s_checkup", "c_s_consultation", "c_s_vaccination", "c_s_pending_bookings"]

            for tbl in tables:
                q = supabase.table(tbl).select("time, duration_minutes, doctor_id") \
                                    .eq("date", date)
                if doctor_filter:
                    q = q.eq("doctor_id", doctor_filter)
                for b in q.execute().data:
                    s = parse_time(b["time"])
                    e = s + timedelta(minutes=b["duration_minutes"])
                    blocked.append((s, e, b["doctor_id"]))

            # reschedule_requests
            q = supabase.table("c_s_reschedule_requests") \
                        .select("new_time, duration_minutes, doctor_id") \
                        .eq("new_date", date).eq("status", "confirmed")
            for r in q.execute().data:
                s = parse_time(r["new_time"])
                e = s + timedelta(minutes=r["duration_minutes"])
                blocked.append((s, e, r["doctor_id"]))

            return blocked

        blocked = blocked_intervals() if is_any_doctor else blocked_intervals(doctor_id)

        # ------------------------------------------------------------------ #
        # 2. Walk through the block in 15-min steps and test the *full* duration
        # ------------------------------------------------------------------ #
        slots = []
        cur = block_start

        while cur < block_end:
            slot_str = cur.strftime("%H:%M")
            slot_end = cur + timedelta(minutes=duration)          # <-- end of *new* booking

            # ---- basic guards ------------------------------------------------
            if cur < datetime.now():                                     # past
                cur += timedelta(minutes=15); continue
            if slot_end > clinic_end:                                    # exceeds clinic close
                cur += timedelta(minutes=15); continue
            if is_during_breaks(cur):                                    # during any break
                cur += timedelta(minutes=15); continue

            # ---- overlap with any existing booking (full duration) ----------
            overlap = False
            for bs, be, _ in blocked:
                if cur < be and slot_end > bs:       # any intersection → blocked
                    overlap = True
                    break
            if overlap:
                cur += timedelta(minutes=15); continue

            # ---- doctor-specific unavailability (only when a doctor is fixed) --
            if not is_any_doctor:
                unavail = supabase.table("c_a_doctor_unavailability") \
                                 .select("start_time, end_time") \
                                 .eq("doctor_id", doctor_id).eq("date", date).execute().data
                for u in unavail:
                    us = parse_time(u["start_time"])
                    ue = parse_time(u["end_time"])
                    if cur < ue and slot_end > us:
                        overlap = True
                        break
                if overlap:
                    cur += timedelta(minutes=15); continue

            # ---- for "any doctor" we need at least ONE free doctor ----------
            if is_any_doctor:
                doctors = supabase.table("c_a_doctors").select("id").eq("clinic_id", clinic_id).execute().data
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

            # ---- slot is good ------------------------------------------------
            slots.append(slot_str)
            cur += timedelta(minutes=15)

        # ------------------------------------------------------------------ #
        # 3. No slots → fallback
        # ------------------------------------------------------------------ #
        if not slots:
            logger.warning(f"No {duration}min slots in block {hour} for {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, "No available time slots.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "SELECT_HOUR"
            get_available_hours(whatsapp_number, user_id, supabase, user_data, module_name)
            return

        # ------------------------------------------------------------------ #
        # 4. Send interactive list
        # ------------------------------------------------------------------ #
        payload = {
            "interactive": {
                "type": "list",
                "body": {"text": translate_template(
                    whatsapp_number,
                    "Select {}min slot for {} {}:", supabase
                ).format(duration, date, hour)},
                "action": {
                    "button": gt_t_tt(whatsapp_number, "Choose Slot", supabase),
                    "sections": [{
                        "title": gt_t_tt(whatsapp_number, "{}min Slots", supabase).format(duration),
                        "rows": [{"id": t, "title": t} for t in slots]
                    }]
                }
            }
        }
        send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)

        user_data[whatsapp_number]["state"] = "SELECT_TIME_SLOT"
        user_data[whatsapp_number]["module"] = module_name

    except Exception as e:
        logger.error(f"Slot error: {str(e)}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, "Error loading slots.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "IDLE"

def get_services_list(supabase, whatsapp_number, category, clinic_id):
    """Get services from clinic_service table for buttons."""
    try:
        response = supabase.table("c_a_clinic_service") \
            .select("id, service_name, description, brochure_image_url") \
            .eq("clinic_id", clinic_id) \
            .eq("category", category) \
            .eq("is_active", True) \
            .order("service_name") \
            .execute()
        
        services = response.data
        services_list = [
            {
                "id": s["id"], 
                # Use gt_t_tt for service names (they're from database)
                "title": gt_t_tt(whatsapp_number, s["service_name"], supabase),
                # Use gt_dt_tt for descriptions (72 char limit)
                "description": gt_dt_tt(whatsapp_number, s.get("description", ""), supabase),
                "brochure_image_url": s.get("brochure_image_url")
            } 
            for s in services
        ]
        services_list.append({
            "id": "others", 
            "title": gt_t_tt(whatsapp_number, "Others", supabase),
            "description": "",
            "brochure_image_url": None
        })
        return services_list[:10]
    except Exception as e:
        logger.error(f"Error getting services: {str(e)}")
        return []

def get_service_duration(supabase, service_id):
    """Get duration_minutes from clinic_service by ID."""
    try:
        if service_id == "others":
            return 30
        response = supabase.table("c_a_clinic_service").select("duration_minutes").eq("id", service_id).eq("is_active", True).execute()
        return response.data[0]["duration_minutes"] if response.data else 30
    except Exception as e:
        logger.error(f"Error getting duration for {service_id}: {str(e)}")
        return 30

def get_available_doctors(whatsapp_number, user_id, supabase, user_data, module_name):
    """Confirm the selected doctor or find the best fit doctor for the selected time slot."""
    try:
        date = user_data[whatsapp_number]["date"]
        time_slot = user_data[whatsapp_number]["time_slot"]
        clinic_id = user_data[whatsapp_number].get("clinic_id", "76d39438-a2c4-4e79-83e8-000000000000")
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_any_doctor = user_data[whatsapp_number].get("any_doctor", False)
        duration = user_data[whatsapp_number].get("duration_minutes", 30)
        
        logger.info(f"Confirming doctor for {whatsapp_number} on {date} at {time_slot}, clinic_id: {clinic_id}, doctor_id: {doctor_id}, any_doctor: {is_any_doctor}, module: {module_name}, duration: {duration}min")
        
        # If specific doctor was selected, just use that doctor
        if not is_any_doctor and doctor_id:
            # Doctor already selected from user selection
            doctor_response = supabase.table("c_a_doctors").select("name").eq("id", doctor_id).execute()
            # Keep doctor name in English (don't translate)
            doctor_name = doctor_response.data[0]["name"] if doctor_response.data else "Doctor"
        else:
            # "Any Doctor" was selected OR no specific doctor chosen
            # Need to find the best fit doctor
            
            # First, check if service has an assigned doctor that should take priority
            service_doctor_id = user_data[whatsapp_number].get("service_doctor_id")
            
            # Get all doctors from the clinic
            doctors = supabase.table("c_a_doctors").select("id, name").eq("clinic_id", clinic_id).execute().data
            
            if not doctors:
                logger.error(f"No doctors found for {whatsapp_number} in clinic {clinic_id}")
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
                # Keep doctor name in English
                d_name = doctor["name"]
                
                # Check if doctor is available at the selected time
                is_available, reason = check_doctor_availability_at_slot(d_id, date, time_slot, duration, supabase)
                
                if is_available:
                    # Get post-consult count (prefer doctors with fewer post-consult cases)
                    post_count_response = supabase.table("c_post_consult").select("id", count="exact").eq("doctor_id", d_id).eq("consult_date", date).execute()
                    post_count = post_count_response.count or 0
                    
                    # Get existing appointments count for this doctor on this day
                    # Check all booking tables including c_s_vaccination
                    total_appointments = 0
                    for table in ["c_s_checkup", "c_s_consultation", "c_s_vaccination", "c_s_pending_bookings"]:
                        appointments = supabase.table(table).select("id", count="exact").eq("doctor_id", d_id).eq("date", date).execute()
                        total_appointments += appointments.count or 0
                    
                    # Calculate a score (lower is better)
                    # Weights: post-consult cases weighted more heavily than total appointments
                    score = (post_count * 3) + (total_appointments * 1)
                    
                    # If this is the service-assigned doctor, give priority
                    priority_boost = 0
                    if service_doctor_id and d_id == service_doctor_id:
                        priority_boost = -50  # Negative to make score better (lower)
                        logger.info(f"Doctor {d_id} is service-assigned, giving priority boost")
                    
                    available_doctors_metrics.append({
                        "id": d_id,
                        "name": d_name,
                        "score": score + priority_boost,
                        "post_consult_count": post_count,
                        "total_appointments": total_appointments,
                        "is_service_assigned": (service_doctor_id and d_id == service_doctor_id)
                    })
            
            if not available_doctors_metrics:
                logger.warning(f"No doctors available for {whatsapp_number} on {date} at {time_slot}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "No doctors available for this time slot. Please select another.", supabase)}}
                )
                user_data[whatsapp_number]["state"] = "SELECT_TIME_SLOT"
                get_time_slots(whatsapp_number, user_id, supabase, user_data, module_name)
                return
            
            # Sort by score (lower is better)
            available_doctors_metrics.sort(key=lambda x: x["score"])
            
            # Select the doctor with the best (lowest) score
            selected_doctor = available_doctors_metrics[0]
            user_data[whatsapp_number]["doctor_id"] = selected_doctor["id"]
            # Keep doctor name in English
            doctor_name = selected_doctor["name"]
            
            logger.info(f"Selected best fit doctor {selected_doctor['id']} ({doctor_name}) for {whatsapp_number} at {time_slot}")
            logger.info(f"Selection metrics - Score: {selected_doctor['score']}, Post-consults: {selected_doctor['post_consult_count']}, Appointments: {selected_doctor['total_appointments']}")

        # Prepare confirmation message based on module type
        if module_name == "checkup_booking":
            service_type = "Checkup"
            details = user_data[whatsapp_number].get("details", user_data[whatsapp_number].get("checkup_type", "Checkup"))
        elif module_name == "vaccination_booking":
            service_type = "Vaccination"
            details = user_data[whatsapp_number].get("details", user_data[whatsapp_number].get("vaccine_type", "Vaccination"))
        elif module_name == "report_symptoms":
            service_type = "Consultation"
            details = user_data[whatsapp_number].get("symptoms", "General Consultation")
        elif module_name == "health_screening":
            service_type = "Health Screening"
            details = user_data[whatsapp_number].get("details", user_data[whatsapp_number].get("healthsp_type", "Health Screening"))
        else:
            service_type = "Appointment"
            details = "General"

        # Get reminder_remark and translate it using gt_tt
        reminder_remark = user_data[whatsapp_number].get("reminder_remark")
        translated_reminder = gt_tt(whatsapp_number, reminder_remark, supabase) if reminder_remark else None
        
        # Prepare confirmation template
        if reminder_remark:
            confirmation_template = "Confirm your booking:\n• Service: {}\n• Doctor: {}\n• Date: {}\n• Time: {}\n• Duration: {} min\n• Details: {}\n• Reminder: {}"
        else:
            confirmation_template = "Confirm your booking:\n• Service: {}\n• Doctor: {}\n• Date: {}\n• Time: {}\n• Duration: {} min\n• Details: {}"
        
        # Translate the details using gt_tt (dynamic content from database/user input)
        translated_details = gt_tt(whatsapp_number, details, supabase)
        display_details = translated_details[:50] + "..." if len(translated_details) > 50 else translated_details
        
        confirmation_text = translate_template(
            whatsapp_number,
            confirmation_template,
            supabase
        ).format(
            # Service type is static text, use translate_template
            translate_template(whatsapp_number, service_type, supabase),
            # Doctor name stays in English
            doctor_name,
            # Date and time stay in original format
            date,
            time_slot,
            duration,
            # Details are dynamic, already translated above
            display_details,
            # Reminder is dynamic, already translated above
            translated_reminder if reminder_remark else ""
        )
        
        # NEW: Show buttons with Confirm, Edit, Cancel
        send_whatsapp_message(
            whatsapp_number,
            "interactive",
            {
                "interactive": {
                    "type": "button",
                    "body": {"text": confirmation_text},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": "confirm_booking", "title": gt_t_tt(whatsapp_number, "Confirm", supabase)}},
                            {"type": "reply", "reply": {"id": "edit_booking", "title": gt_t_tt(whatsapp_number, "Edit", supabase)}},
                            {"type": "reply", "reply": {"id": "cancel_booking", "title": gt_t_tt(whatsapp_number, "Cancel", supabase)}}
                        ]
                    }
                }
            }
        )
        user_data[whatsapp_number]["state"] = "CONFIRM_BOOKING"
        
    except Exception as e:
        logger.error(f"Error in get_available_doctors for {whatsapp_number}: {str(e)}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "An error occurred while confirming the booking. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "IDLE"
        user_data[whatsapp_number]["module"] = None
        send_interactive_menu(whatsapp_number, supabase)

def show_edit_options(whatsapp_number, user_id, supabase, user_data, module_name):
    """Show edit options for the booking."""
    try:
        logger.info(f"Showing edit options for {whatsapp_number}, module: {module_name}")
        
        # Create edit options based on module
        edit_options = [
            {"id": "edit_time", "title": gt_t_tt(whatsapp_number, "Change Time", supabase)},
            {"id": "edit_date", "title": gt_t_tt(whatsapp_number, "Change Date", supabase)},
            {"id": "edit_doctor", "title": gt_t_tt(whatsapp_number, "Change Doctor", supabase)}
        ]
        
        # Add module-specific edit options
        if module_name == "checkup_booking":
            edit_options.append({"id": "edit_service", "title": gt_t_tt(whatsapp_number, "Change Service", supabase)})
        elif module_name == "vaccination_booking":
            edit_options.append({"id": "edit_vaccine", "title": gt_t_tt(whatsapp_number, "Change Vaccine", supabase)})
        elif module_name == "report_symptoms":
            edit_options.append({"id": "edit_symptoms", "title": gt_t_tt(whatsapp_number, "Change Symptoms", supabase)})
        elif module_name == "health_screening":
            edit_options.append({"id": "edit_screening", "title": gt_t_tt(whatsapp_number, "Change Screening", supabase)})
        
        send_whatsapp_message(
            whatsapp_number,
            "interactive",
            {
                "interactive": {
                    "type": "list",
                    "body": {"text": translate_template(whatsapp_number, "What would you like to edit?", supabase)},
                    "action": {
                        "button": gt_t_tt(whatsapp_number, "Edit Option", supabase),
                        "sections": [{
                            "title": gt_t_tt(whatsapp_number, "Edit Options", supabase),
                            "rows": edit_options[:10]  # Limit to 10 options
                        }]
                    }
                }
            }
        )
        user_data[whatsapp_number]["state"] = "EDIT_BOOKING"
        
    except Exception as e:
        logger.error(f"Error showing edit options for {whatsapp_number}: {str(e)}")
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error loading edit options. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "CONFIRM_BOOKING"

def handle_edit_choice(whatsapp_number, user_id, supabase, user_data, module_name, edit_choice):
    """Handle user's edit choice."""
    try:
        logger.info(f"Handling edit choice for {whatsapp_number}: {edit_choice}")
        
        if edit_choice == "edit_time":
            # Clear time slot and go back to time selection
            user_data[whatsapp_number].pop("time_slot", None)
            user_data[whatsapp_number].pop("parsed_time_input", None)
            user_data[whatsapp_number].pop("closest_available_time", None)
            
            # Ask for time input
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
            
            # Show doctors list
            get_doctors(whatsapp_number, user_id, supabase, user_data, module_name)
            
        elif edit_choice == "edit_service" and module_name == "checkup_booking":
            # Clear service selection and go back to service selection
            user_data[whatsapp_number].pop("service_id", None)
            user_data[whatsapp_number].pop("checkup_type", None)
            user_data[whatsapp_number].pop("details", None)
            user_data[whatsapp_number].pop("duration_minutes", None)
            
            # Need to go back to checkup type selection
            # This will be handled in app.py based on state and module
            user_data[whatsapp_number]["state"] = "SELECT_CHECKUP_TYPE"
            
        elif edit_choice == "edit_vaccine" and module_name == "vaccination_booking":
            # Clear vaccine selection
            user_data[whatsapp_number].pop("vaccine_type", None)
            user_data[whatsapp_number].pop("details", None)
            
            # Need to go back to vaccine type selection
            user_data[whatsapp_number]["state"] = "SELECT_VACCINE_TYPE"
            
        elif edit_choice == "edit_symptoms" and module_name == "report_symptoms":
            # Clear symptoms
            user_data[whatsapp_number].pop("symptoms", None)
            user_data[whatsapp_number].pop("details", None)
            
            # Ask for symptoms again
            user_data[whatsapp_number]["state"] = "AWAITING_SYMPTOMS"
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "Please describe your symptoms or health concerns:",
                    supabase
                )}}
            )
            
        elif edit_choice == "edit_screening" and module_name == "health_screening":
            # Clear health screening selection
            user_data[whatsapp_number].pop("healthsp_type", None)
            user_data[whatsapp_number].pop("details", None)
            
            # Need to go back to health screening type selection
            user_data[whatsapp_number]["state"] = "SELECT_HEALTHSP_TYPE"
            
        else:
            logger.warning(f"Invalid edit choice for {whatsapp_number}: {edit_choice}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Invalid edit option. Please try again.", supabase)}}
            )
            show_edit_options(whatsapp_number, user_id, supabase, user_data, module_name)
            
    except Exception as e:
        logger.error(f"Error handling edit choice for {whatsapp_number}: {str(e)}")
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing edit choice. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "CONFIRM_BOOKING"
        
def check_doctor_availability_at_slot(doctor_id, date, time_slot, duration, supabase):
    """Check if a specific doctor is available at a given time slot."""
    try:
        # Parse time
        slot_time = datetime.strptime(f"{date} {time_slot}", "%Y-%m-%d %H:%M")
        slot_end = slot_time + timedelta(minutes=duration)
        
        # Check unavailability
        unavailability = supabase.table("c_a_doctor_unavailability").select("start_time, end_time").eq("doctor_id", doctor_id).eq("date", date).execute().data
        for u in unavailability:
            u_start = datetime.strptime(f"{date} {u['start_time']}", "%Y-%m-%d %H:%M")
            u_end = datetime.strptime(f"{date} {u['end_time']}", "%Y-%m-%d %H:%M")
            if slot_time < u_end and slot_end > u_start:
                return False, "doctor_unavailable"
        
        # Check existing bookings
        tables = ["c_s_checkup", "c_s_consultation", "c_s_vaccination", "c_s_pending_bookings"]
        for table in tables:
            bookings = supabase.table(table).select("time, duration_minutes").eq("doctor_id", doctor_id).eq("date", date).execute().data
            for b in bookings:
                b_start = datetime.strptime(f"{date} {b['time']}", "%Y-%m-%d %H:%M")
                b_end = b_start + timedelta(minutes=b["duration_minutes"])
                if slot_time < b_end and slot_end > b_start:
                    return False, "slot_booked"
        
        # Check reschedule requests
        reschedule_bookings = supabase.table("c_s_reschedule_requests").select("new_time, duration_minutes").eq("doctor_id", doctor_id).eq("new_date", date).eq("status", "confirmed").execute().data
        for r in reschedule_bookings:
            r_start = datetime.strptime(f"{date} {r['new_time']}", "%Y-%m-%d %H:%M")
            r_end = r_start + timedelta(minutes=r["duration_minutes"])
            if slot_time < r_end and slot_end > r_start:
                return False, "slot_booked"
        
        return True, "available"
    
    except Exception as e:
        logger.error(f"Error checking doctor availability: {str(e)}")
        return False, "error"

def handle_confirm_booking(whatsapp_number, user_id, supabase, user_data, module_name):
    """Unified confirm-booking handler for all modules."""
    try:
        pending_id = str(uuid.uuid4())
        
        # Base fields that every pending booking needs
        booking_data = {
            "id": pending_id,
            "user_id": user_id,
            "doctor_id": user_data[whatsapp_number]["doctor_id"],
            "date": user_data[whatsapp_number]["date"],
            "time": user_data[whatsapp_number]["time_slot"],
            "duration_minutes": user_data[whatsapp_number].get("duration_minutes", 30),
            "created_at": datetime.now().isoformat(),
            "notified_doctors": []
        }

        # Module-specific fields
        if module_name == "checkup_booking":
            booking_data["booking_type"] = "checkup"
            service_name = user_data[whatsapp_number].get("checkup_type", "Checkup")
            reminder_remark = user_data[whatsapp_number].get("reminder_remark")
            
            if reminder_remark:
                booking_data["details"] = f"{service_name}, {reminder_remark}"
            else:
                booking_data["details"] = service_name
                
        elif module_name == "report_symptoms":
            booking_data["booking_type"] = "consultation"
            symptoms = user_data[whatsapp_number].get("symptoms", "General Consultation")
            reminder_remark = user_data[whatsapp_number].get("reminder_remark")
            
            if reminder_remark:
                booking_data["details"] = f"{symptoms}, {reminder_remark}"
            else:
                booking_data["details"] = symptoms
                
        elif module_name == "vaccination_booking":
            booking_data["booking_type"] = "vaccination"
            vaccine_type = user_data[whatsapp_number].get("vaccine_type", "Vaccination")
            reminder_remark = user_data[whatsapp_number].get("reminder_remark")
            
            # Store vaccine_type separately for vaccination bookings
            booking_data["vaccine_type"] = vaccine_type
            
            if reminder_remark:
                booking_data["details"] = f"{vaccine_type}, {reminder_remark}"
                booking_data["reminder_remark"] = reminder_remark
            else:
                booking_data["details"] = vaccine_type
                
        elif module_name == "health_screening":
            booking_data["booking_type"] = "checkup"
            health_screening_type = user_data[whatsapp_number].get("details", "Health Screening")
            reminder_remark = user_data[whatsapp_number].get("reminder_remark")
            
            if reminder_remark:
                booking_data["details"] = f"{health_screening_type}, {reminder_remark}"
            else:
                booking_data["details"] = health_screening_type
        else:
            logger.error(f"Invalid module_name {module_name}")
            raise ValueError("Unsupported module")

        # Add reminder duration if present
        if "reminder_duration" in user_data[whatsapp_number]:
            booking_data["reminder_duration"] = user_data[whatsapp_number]["reminder_duration"]
        
        logger.info(f"Inserting pending booking for {whatsapp_number}: {booking_data}")
        
        # Insert into pending_bookings
        try:
            response = supabase.table("c_s_pending_bookings").insert(booking_data).execute()
            logger.info(f"Supabase insert response: {response}")
        except Exception as e:
            logger.error(f"Failed to insert booking for {whatsapp_number}: {str(e)}")
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
            logger.error(f"Failed to insert booking for {whatsapp_number} - no data returned")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Failed to save booking. Please try again.", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            user_data[whatsapp_number]["module"] = None
            send_interactive_menu(whatsapp_number, supabase)
            return

        # Confirmation message - use appropriate template based on module
        confirmation_messages = {
            "checkup_booking": "Your checkup booking is pending approval by the admin.",
            "report_symptoms": "Your consultation booking is pending approval by the admin.",
            "vaccination_booking": "Your vaccination booking is pending approval by the admin.",
            "health_screening": "Your health screening booking is pending approval by the admin."
        }
        
        confirmation_message = confirmation_messages.get(module_name, "Your booking is pending approval by the admin.")

        result = send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, confirmation_message, supabase)}},
            supabase
        )
        if not result:
            logger.error(f"Failed to send confirmation to {whatsapp_number}")
            # Try to delete the pending booking if message failed
            try:
                supabase.table("c_s_pending_bookings").delete().eq("id", pending_id).execute()
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
        logger.info(f"Booking pending approval for {whatsapp_number}, ID: {pending_id}, type: {booking_data['booking_type']}")
        send_interactive_menu(whatsapp_number, supabase)

    except Exception as e:
        logger.error(f"Error in handle_confirm_booking for {whatsapp_number}: {str(e)}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, f"An error occurred while confirming the booking: {str(e)}. Please try again.", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "IDLE"
        user_data[whatsapp_number]["module"] = None
        send_interactive_menu(whatsapp_number, supabase)

def handle_cancel_booking(whatsapp_number, user_id, supabase, user_data):
    """Handle cancel booking - Clear booking data from user_data and reset state."""
    logger.info(f"👋 User {whatsapp_number} CANCELLED - CLEARING BOOKING DATA")
    
    # Clear booking-related data from user_data
    booking_keys = [
        "pending_id", "doctor_id", "date", "time_slot", "duration_minutes",
        "checkup_type", "display_checkup_type", "details", "vaccine_type",
        "display_vaccine_type", "vaccine_details", "symptoms", "reminder_remark",
        "any_doctor", "clinic_id", "future_date_input", "service_id",
        "service_doctor_id", "reminder_duration", "parsed_time_input",
        "closest_available_time"
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
        {"text": {"body": translate_template(whatsapp_number, "Booking has been cancelled.", supabase)}}
    )
    
    # Send interactive menu
    send_interactive_menu(whatsapp_number, supabase)
    return True