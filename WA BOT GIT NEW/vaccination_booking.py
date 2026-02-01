import uuid
import logging
from datetime import datetime
from calendar_utils import (
    get_doctors, get_calendar, select_period, get_available_hours, get_time_slots,
    get_available_doctors, get_service_duration,
    handle_cancel_booking, handle_future_date_input, handle_future_date_confirmation,
    # NEW: Time input functions
    handle_time_input, handle_time_confirmation, handle_retry_time_or_help,
    # NEW: Edit functions
    show_edit_options, handle_edit_choice
)
from utils import (
    send_whatsapp_message, send_interactive_menu, translate_template,
    gt_t_tt, gt_tt, send_image_message, gt_dt_tt
)
from clinicfd import handle_clinic_enquiries
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handle_vaccination(whatsapp_number, user_id, supabase, user_data, message):
    state = user_data.get(whatsapp_number, {}).get("state", "IDLE")
    logger.info(f"Handling vaccination for {whatsapp_number}, state: {state}")

    # Fetch user language
    language = "en"
    try:
        response = supabase.table("whatsapp_users") \
            .select("language") \
            .eq("whatsapp_number", whatsapp_number.lstrip("+")) \
            .limit(1).execute()
        if response.data:
            language = response.data[0]["language"]
    except Exception as e:
        logger.error(f"Error fetching language for {whatsapp_number}: {e}")

    # -------------------------------------------------------------------------
    # IDLE – Start flow: Show service details and ask for remarks
    # -------------------------------------------------------------------------
    if state == "IDLE":
        # Get clinic ID
        clinic_id = user_data[whatsapp_number].get("clinic_id")
        if not clinic_id:
            temp_data = user_data[whatsapp_number].get("temp_data", {})
            clinic_id = temp_data.get("clinic_id")
            
        if not clinic_id:
            try:
                user_db_data = supabase.table("whatsapp_users").select("temp_data").eq(
                    "whatsapp_number", whatsapp_number.lstrip("+")
                ).limit(1).execute()
                
                if user_db_data.data and user_db_data.data[0]:
                    temp_data = user_db_data.data[0].get("temp_data", {})
                    if temp_data:
                        clinic_id = temp_data.get("clinic_id")
            except Exception as e:
                logger.error(f"Error fetching clinic_id from database: {e}")
            
        if not clinic_id:
            clinic_id = "76d39438-a2c4-4e79-83e8-000000000000"
            logger.warning(f"No clinic_id found for {whatsapp_number}, using default: {clinic_id}")
        
        # Get service details
        service_id = user_data[whatsapp_number].get("service_id")
        service_name = user_data[whatsapp_number].get("service_name", "Vaccination")
        description = user_data[whatsapp_number].get("description", "")
        
        if not service_id:
            logger.error(f"No service_id found for {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "Error: No service selected. Please start over.",
                    supabase
                )}}
            )
            user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False
        
        # Store clinic_id
        user_data[whatsapp_number]["clinic_id"] = clinic_id
        logger.info(f"Using clinic_id: {clinic_id} for {whatsapp_number}, service: {service_name}")
        
        # Get category image for Vaccination
        category_image_url = None
        try:
            response = supabase.table("c_a_clinic_cat").select("image_url") \
                .eq("clinic_id", clinic_id).eq("category", "Vaccination").limit(1).execute()
            if response.data and response.data[0]["image_url"]:
                category_image_url = response.data[0]["image_url"]
                logger.info(f"Found category image for clinic {clinic_id}: {category_image_url}")
        except Exception as e:
            logger.error(f"Error fetching clinic category image: {e}")
        
        # Check temp_data for category image
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        if not category_image_url and temp_data.get("category_image_url"):
            category_image_url = temp_data["category_image_url"]
        
        # Send category image (Image Only)
        if category_image_url:
            send_image_message(whatsapp_number, category_image_url, supabase, 
                             translate_template(whatsapp_number, "Welcome to our clinic! Please select a booking option.", supabase))
            time.sleep(1)

        # Fetch service details from DB
        try:
            resp = supabase.table("c_a_clinic_service") \
                .select("duration_minutes, reminder_duration, reminder_remark, description, brochure_image_url, doctor_id") \
                .eq("id", service_id) \
                .eq("clinic_id", clinic_id) \
                .eq("is_active", True) \
                .maybe_single().execute()
            
            logger.info(f"Vaccination service details response for {service_id}: {resp.data}")
            
            if resp.data:
                duration = resp.data["duration_minutes"]
                reminder_duration = resp.data.get("reminder_duration")
                reminder_remark = resp.data.get("reminder_remark")
                doctor_id = resp.data.get("doctor_id")
                description = resp.data.get("description", "") or description
                brochure_image_url = resp.data.get("brochure_image_url")
                
                user_data[whatsapp_number]["service_doctor_id"] = doctor_id
                logger.info(f"Service {service_id} has assigned doctor: {doctor_id}")
            else:
                duration = 30
                reminder_duration = None
                reminder_remark = None
                doctor_id = None
                brochure_image_url = None
                logger.warning(f"No service details found for ID: {service_id} in clinic: {clinic_id}")
        except Exception as e:
            logger.error(f"Error fetching vaccination service details for {service_id}: {e}", exc_info=True)
            duration = 30
            reminder_duration = None
            reminder_remark = None
            doctor_id = None
            brochure_image_url = None

        # Store all data
        user_data[whatsapp_number] = {
            "state": "VACCINATION_REMARK_YES_NO",
            "module": "vaccination_booking",
            "language": language,
            "clinic_id": clinic_id,
            "service_id": service_id,
            "vaccine_type": service_name,
            "display_vaccine_type": service_name,
            "service_description": description.strip(),
            "duration_minutes": duration,
            "reminder_duration": reminder_duration,
            "reminder_remark": reminder_remark,
            "brochure_image_url": brochure_image_url
        }

        # Send brochure image if available
        sent = False
        if brochure_image_url:
            try:
                send_image_message(whatsapp_number, brochure_image_url, supabase)
                sent = True
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error sending brochure image: {e}")
                sent = False

        # Send description if available
        if description.strip():
            # Use gt_tt for service description since it's from database
            truncated_desc = gt_tt(whatsapp_number, description.strip(), supabase)
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": truncated_desc}},
                supabase
            )
            sent = True
            time.sleep(1)

        # Proceed to remark question
        # Use translate_template for base text, gt_tt for dynamic content
        prompt_text = translate_template(
            whatsapp_number,
            "Do you have any remarks for {} ({} min){}?", supabase
        ).format(
            gt_tt(whatsapp_number, service_name, supabase),  # Service name from DB
            duration,
            f" [{gt_dt_tt(whatsapp_number, description.strip(), supabase)}]" if description.strip() and not sent else ""
        )

        send_whatsapp_message(
            whatsapp_number,
            "interactive",
            {
                "interactive": {
                    "type": "button",
                    "body": {"text": prompt_text},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": "remark_yes", "title": translate_template(whatsapp_number, "Yes", supabase)}},
                            {"type": "reply", "reply": {"id": "remark_no", "title": translate_template(whatsapp_number, "No", supabase)}}
                        ]
                    }
                }
            },
            supabase
        )
        return False

    # -------------------------------------------------------------------------
    # VACCINATION_REMARK_YES_NO
    # -------------------------------------------------------------------------
    elif state == "VACCINATION_REMARK_YES_NO" and message.get("type") == "interactive":
        if message["interactive"]["button_reply"]["id"] == "remark_yes":
            user_data[whatsapp_number]["state"] = "VACCINATION_REMARK_INPUT"
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Please enter your remarks:", supabase)}},
                supabase
            )
        else:
            user_data[whatsapp_number]["details"] = user_data[whatsapp_number]["vaccine_type"]
            user_data[whatsapp_number]["state"] = "SELECT_DOCTOR"
            get_doctors(whatsapp_number, user_id, supabase, user_data, "vaccination_booking")
        return False

    # -------------------------------------------------------------------------
    # VACCINATION_REMARK_INPUT
    # -------------------------------------------------------------------------
    elif state == "VACCINATION_REMARK_INPUT" and message.get("type") == "text":
        remark = message["text"]["body"].strip()
        user_data[whatsapp_number]["details"] = f"{user_data[whatsapp_number]['vaccine_type']}: {remark}"
        user_data[whatsapp_number]["state"] = "SELECT_DOCTOR"
        get_doctors(whatsapp_number, user_id, supabase, user_data, "vaccination_booking")
        return False

    # -------------------------------------------------------------------------
    # SELECT_DOCTOR
    # -------------------------------------------------------------------------
    elif state == "SELECT_DOCTOR" and message.get("type") == "interactive" \
            and message["interactive"].get("type") == "list_reply":
        selected = message["interactive"]["list_reply"]["id"]
        if selected == "any_doctor":
            user_data[whatsapp_number]["any_doctor"] = True
            user_data[whatsapp_number]["doctor_id"] = None
        else:
            user_data[whatsapp_number]["doctor_id"] = selected
            user_data[whatsapp_number]["any_doctor"] = False
        
        if selected != "any_doctor":
            try:
                doctor_response = supabase.table("c_a_doctors").select("name").eq("id", selected).execute()
                if doctor_response.data:
                    user_data[whatsapp_number]["selected_doctor_name"] = doctor_response.data[0]["name"]
                    logger.info(f"User selected doctor: {doctor_response.data[0]['name']}")
            except Exception as e:
                logger.error(f"Error fetching doctor name: {e}")
        
        user_data[whatsapp_number]["state"] = "SELECT_DATE"
        get_calendar(whatsapp_number, user_id, supabase, user_data, "vaccination_booking")
        return False

    # -------------------------------------------------------------------------
    # SELECT_DATE
    # -------------------------------------------------------------------------
    elif state == "SELECT_DATE" and message.get("type") == "interactive":
        selected_date = message["interactive"]["list_reply"]["id"]
        
        if selected_date == "future_date":
            user_data[whatsapp_number]["state"] = "AWAITING_FUTURE_DATE"
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "Please enter your preferred date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:",
                    supabase
                )}}
            )
        else:
            user_data[whatsapp_number]["date"] = selected_date
            user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "Please enter your preferred time (e.g., 9:30, 2pm, 1430):",
                    supabase
                )}}
            )
        return False

    # -------------------------------------------------------------------------
    # AWAITING_TIME_INPUT (NEW)
    # -------------------------------------------------------------------------
    elif state == "AWAITING_TIME_INPUT" and message.get("type") == "text":
        time_input = message["text"]["body"].strip()
        handle_time_input(whatsapp_number, user_id, supabase, user_data, "vaccination_booking", time_input)
        return False

    # -------------------------------------------------------------------------
    # CONFIRM_TIME (NEW)
    # -------------------------------------------------------------------------
    elif state == "CONFIRM_TIME" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        if button_id == "confirm_time":
            handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, "vaccination_booking", confirmed=True, use_closest=False)
        elif button_id == "find_another_time":
            user_data[whatsapp_number].pop("parsed_time_input", None)
            user_data[whatsapp_number].pop("closest_available_time", None)
            user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
            select_period(whatsapp_number, user_id, supabase, user_data, "vaccination_booking")
        return False

    # -------------------------------------------------------------------------
    # CONFIRM_CLOSEST_TIME (NEW)
    # -------------------------------------------------------------------------
    elif state == "CONFIRM_CLOSEST_TIME" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        if button_id == "accept_closest_time":
            handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, "vaccination_booking", confirmed=True, use_closest=True)
        elif button_id == "find_another_time":
            user_data[whatsapp_number].pop("parsed_time_input", None)
            user_data[whatsapp_number].pop("closest_available_time", None)
            user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
            select_period(whatsapp_number, user_id, supabase, user_data, "vaccination_booking")
        return False

    # -------------------------------------------------------------------------
    # RETRY_TIME_OR_HELP (NEW)
    # -------------------------------------------------------------------------
    elif state == "RETRY_TIME_OR_HELP" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        if button_id == "try_again_time":
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
        elif button_id == "help_choose_time":
            user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
            select_period(whatsapp_number, user_id, supabase, user_data, "vaccination_booking")
        return False

    # -------------------------------------------------------------------------
    # AWAITING_FUTURE_DATE
    # -------------------------------------------------------------------------
    elif state == "AWAITING_FUTURE_DATE" and message.get("type") == "text":
        date_input = message["text"]["body"].strip()
        handle_future_date_input(whatsapp_number, user_id, supabase, user_data, "vaccination_booking", date_input)
        return False

    # -------------------------------------------------------------------------
    # CONFIRM_FUTURE_DATE
    # -------------------------------------------------------------------------
    elif state == "CONFIRM_FUTURE_DATE" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        if button_id == "confirm_future_date":
            date_obj = user_data[whatsapp_number].get("future_date_input")
            if date_obj:
                user_data[whatsapp_number]["date"] = date_obj.strftime("%Y-%m-%d")
                user_data[whatsapp_number].pop("future_date_input", None)
                user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        "Please enter your preferred time (e.g., 9:30, 2pm, 1430):",
                        supabase
                    )}}
                )
        elif button_id == "reject_future_date":
            handle_future_date_confirmation(whatsapp_number, user_id, supabase, user_data, "vaccination_booking", confirmed=False)
        return False

    # -------------------------------------------------------------------------
    # SELECT_PERIOD (fallback only)
    # -------------------------------------------------------------------------
    elif state == "SELECT_PERIOD" and message.get("type") == "interactive":
        user_data[whatsapp_number]["period"] = message["interactive"]["button_reply"]["id"]
        user_data[whatsapp_number]["state"] = "SELECT_HOUR"
        get_available_hours(whatsapp_number, user_id, supabase, user_data, "vaccination_booking")
        return False

    elif state == "SELECT_HOUR" and message.get("type") == "interactive":
        user_data[whatsapp_number]["hour"] = message["interactive"]["list_reply"]["id"]
        user_data[whatsapp_number]["state"] = "SELECT_TIME_SLOT"
        get_time_slots(whatsapp_number, user_id, supabase, user_data, "vaccination_booking")
        return False

    elif state == "SELECT_TIME_SLOT" and message.get("type") == "interactive":
        user_data[whatsapp_number]["time_slot"] = message["interactive"]["list_reply"]["id"]
        get_available_doctors(whatsapp_number, user_id, supabase, user_data, "vaccination_booking")
        return False

    # -------------------------------------------------------------------------
    # CONFIRM_BOOKING
    # -------------------------------------------------------------------------
    elif state == "CONFIRM_BOOKING" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]

        if button_id == "confirm_booking":
            vaccine_type = user_data[whatsapp_number]["vaccine_type"]
            doctor_id = user_data[whatsapp_number]["doctor_id"]
            date = user_data[whatsapp_number]["date"]
            time_slot = user_data[whatsapp_number]["time_slot"]
            duration_minutes = user_data[whatsapp_number]["duration_minutes"]
            reminder_duration = user_data[whatsapp_number].get("reminder_duration")
            reminder_remark = user_data[whatsapp_number].get("reminder_remark")
            details = user_data[whatsapp_number].get("details", vaccine_type)
            
            try:
                pending_id = str(uuid.uuid4())
                booking_data = {
                    "id": pending_id,
                    "user_id": user_id,
                    "doctor_id": doctor_id,
                    "booking_type": "vaccination",
                    "details": details,
                    "date": date,
                    "time": time_slot,
                    "duration_minutes": duration_minutes,
                    "reminder_duration": reminder_duration,
                    "reminder_remark": reminder_remark,
                    "created_at": datetime.now().isoformat(),
                    "notified_doctors": [doctor_id] if doctor_id else [],
                    "created_by": user_id,
                    "checkin": False
                }
                
                supabase.table("c_s_pending_bookings").insert(booking_data).execute()
                logger.info(f"Vaccination booking saved to pending: {pending_id} for {whatsapp_number}")
                
                # Build confirmation message with proper translation
                confirmation_parts = [
                    translate_template(whatsapp_number, "✅ Your vaccination booking has been submitted!\n\n", supabase),
                    translate_template(whatsapp_number, "Vaccine: ", supabase),
                    gt_tt(whatsapp_number, vaccine_type, supabase),
                    "\n",
                    translate_template(whatsapp_number, "Date: ", supabase),
                    date,
                    "\n",
                    translate_template(whatsapp_number, "Time: ", supabase),
                    time_slot,
                    "\n",
                    translate_template(whatsapp_number, "Duration: ", supabase),
                    str(duration_minutes),
                    translate_template(whatsapp_number, " minutes\n\n", supabase),
                    translate_template(whatsapp_number, "Booking is pending approval. You'll be notified once confirmed.\n", supabase),
                    translate_template(whatsapp_number, "Booking ID: ", supabase),
                    f"{pending_id[:8]}...",
                ]
                
                confirmation_message = "".join(confirmation_parts)
                
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": confirmation_message}},
                    supabase
                )
                
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return True
                
            except Exception as e:
                logger.error(f"Error saving vaccination booking for {whatsapp_number}: {e}", exc_info=True)
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        "Error saving vaccination booking. Please try again.", 
                        supabase
                    )}},
                    supabase
                )
                user_data[whatsapp_number]["state"] = "IDLE"
                user_data[whatsapp_number]["module"] = None
                send_interactive_menu(whatsapp_number, supabase)
                return False

        elif button_id == "edit_booking":
            # Handle edit booking
            show_edit_options(whatsapp_number, user_id, supabase, user_data, "vaccination_booking")
            return False
            
        elif button_id == "cancel_booking":
            return handle_cancel_booking(whatsapp_number, user_id, supabase, user_data)

    # -------------------------------------------------------------------------
    # EDIT_BOOKING (NEW)
    # -------------------------------------------------------------------------
    elif state == "EDIT_BOOKING" and message.get("type") == "interactive":
        # Handle edit choice selection
        if "list_reply" in message["interactive"]:
            edit_choice = message["interactive"]["list_reply"]["id"]
            handle_edit_choice(whatsapp_number, user_id, supabase, user_data, "vaccination_booking", edit_choice)
        return False

    # -------------------------------------------------------------------------
    # Default - Handle unexpected inputs
    # -------------------------------------------------------------------------
    else:
        current_state = user_data[whatsapp_number].get("state")
        if current_state in ["AWAITING_FUTURE_DATE", "VACCINATION_REMARK_INPUT", "AWAITING_TIME_INPUT"]:
            if current_state == "AWAITING_FUTURE_DATE":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        "Please enter your preferred date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:",
                        supabase
                    )}}
                )
            elif current_state == "VACCINATION_REMARK_INPUT":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Please enter your remarks:", supabase)}},
                    supabase
                )
            elif current_state == "AWAITING_TIME_INPUT":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        "Please enter your preferred time (e.g., 9:30, 2pm, 1430):",
                        supabase
                    )}}
                )
        else:
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Invalid input. Please use the buttons provided.", supabase)}}
            )
            
        return False

    return False