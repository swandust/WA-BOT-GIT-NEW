import uuid
import logging
import time
from datetime import datetime
from calendar_utils import (
    get_doctors, get_calendar, select_period, get_available_hours,
    get_time_slots, get_available_doctors, handle_cancel_booking,
    handle_future_date_input, handle_future_date_confirmation,
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handle_symptoms(whatsapp_number, user_id, supabase, user_data, message):
    state = user_data.get(whatsapp_number, {}).get("state", "IDLE")
    logger.info(f"Handling symptoms reporting for {whatsapp_number}, state: {state}")

    language = "en"
    try:
        resp = supabase.table("whatsapp_users") \
            .select("language") \
            .eq("whatsapp_number", whatsapp_number.lstrip("+")) \
            .limit(1).execute()
        if resp.data:
            language = resp.data[0]["language"]
    except Exception as e:
        logger.error(f"Error fetching language for {whatsapp_number}: {e}")

    if state == "IDLE":
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
            clinic_id = "aff725c1-c333-4039-bd2d-000000000000"
            logger.warning(f"No clinic_id found for {whatsapp_number}, using default: {clinic_id}")
        
        user_data[whatsapp_number]["clinic_id"] = clinic_id

        try:
            service_resp = supabase.table("c_a_clinic_service") \
                .select("id, service_name, description, duration_minutes, reminder_duration, reminder_remark") \
                .eq("clinic_id", clinic_id) \
                .eq("category", "General GP visit") \
                .eq("is_active", True) \
                .limit(1).execute()
            if service_resp.data:
                service = service_resp.data[0]
                user_data[whatsapp_number]["service_id"] = service["id"]
                user_data[whatsapp_number]["service_name"] = service["service_name"]
                user_data[whatsapp_number]["duration_minutes"] = service["duration_minutes"]
                user_data[whatsapp_number]["reminder_duration"] = service.get("reminder_duration")
                user_data[whatsapp_number]["reminder_remark"] = service.get("reminder_remark")
                description = service.get("description", "")
                logger.info(f"Found GP service for clinic {clinic_id}: {service['service_name']}")
            else:
                user_data[whatsapp_number]["service_id"] = str(uuid.uuid4())
                user_data[whatsapp_number]["service_name"] = "Describe your symptoms"
                user_data[whatsapp_number]["duration_minutes"] = 30
                user_data[whatsapp_number]["reminder_duration"] = None
                user_data[whatsapp_number]["reminder_remark"] = None
                description = ""
                logger.warning(f"No GP service found for clinic {clinic_id}, using defaults")
        except Exception as e:
            logger.error(f"Error fetching General GP service for clinic {clinic_id}: {e}")
            user_data[whatsapp_number]["service_id"] = str(uuid.uuid4())
            user_data[whatsapp_number]["service_name"] = "Describe your symptoms"
            user_data[whatsapp_number]["duration_minutes"] = 30
            user_data[whatsapp_number]["reminder_duration"] = None
            user_data[whatsapp_number]["reminder_remark"] = None
            description = ""

        category_image_url = None
        try:
            response = supabase.table("c_a_clinic_cat").select("image_url") \
                .eq("clinic_id", clinic_id).eq("category", "General GP visit").limit(1).execute()
            if response.data and response.data[0]["image_url"]:
                category_image_url = response.data[0]["image_url"]
                logger.info(f"Found category image for clinic {clinic_id}: {category_image_url}")
        except Exception as e:
            logger.error(f"Error fetching clinic category image: {e}")

        if category_image_url:
            send_image_message(whatsapp_number, category_image_url, supabase)
            time.sleep(1)

        if description.strip():
            truncated_desc = gt_tt(whatsapp_number, description.strip(), supabase)
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": truncated_desc}},
                supabase
            )
            time.sleep(1)

        user_data[whatsapp_number] = {
            "state": "SYMPTOMS_INPUT",
            "module": "report_symptoms",
            "language": language,
            "clinic_id": clinic_id,
            "service_id": user_data[whatsapp_number]["service_id"],
            "service_name": user_data[whatsapp_number]["service_name"],
            "duration_minutes": user_data[whatsapp_number]["duration_minutes"],
            "reminder_duration": user_data[whatsapp_number]["reminder_duration"],
            "reminder_remark": user_data[whatsapp_number]["reminder_remark"]
        }

        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Please describe your symptoms:", supabase)}},
            supabase
        )
        return False

    elif state == "SYMPTOMS_INPUT" and message.get("type") == "text":
        symptoms = message["text"]["body"].strip()
        user_data[whatsapp_number]["symptoms"] = symptoms
        user_data[whatsapp_number]["state"] = "SYMPTOMS_REMARK_YES_NO"
        prompt = translate_template(
            whatsapp_number,
            "Do you have any additional remarks about your symptoms?",
            supabase
        )
        send_whatsapp_message(
            whatsapp_number,
            "interactive",
            {
                "interactive": {
                    "type": "button",
                    "body": {"text": prompt},
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

    elif state == "SYMPTOMS_REMARK_YES_NO" and message.get("type") == "interactive":
        btn = message["interactive"]["button_reply"]["id"]
        if btn == "remark_yes":
            user_data[whatsapp_number]["state"] = "SYMPTOMS_REMARK_INPUT"
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Please enter your additional remarks:", supabase)}},
                supabase
            )
        else:
            user_data[whatsapp_number]["details"] = f"Symptoms: {user_data[whatsapp_number]['symptoms']}"
            user_data[whatsapp_number]["state"] = "SELECT_DOCTOR"
            get_doctors(whatsapp_number, user_id, supabase, user_data, "report_symptoms")
        return False

    elif state == "SYMPTOMS_REMARK_INPUT" and message.get("type") == "text":
        remark = message["text"]["body"].strip()
        symptoms = user_data[whatsapp_number]["symptoms"]
        details = f"Symptoms: {symptoms}\nRemarks: {remark}"
        user_data[whatsapp_number]["details"] = details
        user_data[whatsapp_number]["state"] = "SELECT_DOCTOR"
        get_doctors(whatsapp_number, user_id, supabase, user_data, "report_symptoms")
        return False

    elif state == "SELECT_DOCTOR" and message.get("type") == "interactive":
        sel = message["interactive"]["list_reply"]["id"]
        if sel == "any_doctor":
            user_data[whatsapp_number]["any_doctor"] = True
            user_data[whatsapp_number]["doctor_id"] = None
        else:
            user_data[whatsapp_number]["doctor_id"] = sel
            user_data[whatsapp_number]["any_doctor"] = False
        user_data[whatsapp_number]["state"] = "SELECT_DATE"
        get_calendar(whatsapp_number, user_id, supabase, user_data, "report_symptoms")
        return False

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
                )}},
                supabase
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
        handle_time_input(whatsapp_number, user_id, supabase, user_data, "report_symptoms", time_input)
        return False

    # -------------------------------------------------------------------------
    # CONFIRM_TIME (NEW)
    # -------------------------------------------------------------------------
    elif state == "CONFIRM_TIME" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        if button_id == "confirm_time":
            handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, "report_symptoms", confirmed=True, use_closest=False)
        elif button_id == "find_another_time":
            user_data[whatsapp_number].pop("parsed_time_input", None)
            user_data[whatsapp_number].pop("closest_available_time", None)
            user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
            select_period(whatsapp_number, user_id, supabase, user_data, "report_symptoms")
        return False

    # -------------------------------------------------------------------------
    # CONFIRM_CLOSEST_TIME (NEW)
    # -------------------------------------------------------------------------
    elif state == "CONFIRM_CLOSEST_TIME" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        if button_id == "accept_closest_time":
            handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, "report_symptoms", confirmed=True, use_closest=True)
        elif button_id == "find_another_time":
            user_data[whatsapp_number].pop("parsed_time_input", None)
            user_data[whatsapp_number].pop("closest_available_time", None)
            user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
            select_period(whatsapp_number, user_id, supabase, user_data, "report_symptoms")
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
            select_period(whatsapp_number, user_id, supabase, user_data, "report_symptoms")
        return False

    # -------------------------------------------------------------------------
    # AWAITING_FUTURE_DATE
    # -------------------------------------------------------------------------
    elif state == "AWAITING_FUTURE_DATE" and message.get("type") == "text":
        date_input = message["text"]["body"].strip()
        handle_future_date_input(whatsapp_number, user_id, supabase, user_data, "report_symptoms", date_input)
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
            handle_future_date_confirmation(whatsapp_number, user_id, supabase, user_data, "report_symptoms", confirmed=False)
        return False

    # -------------------------------------------------------------------------
    # SELECT_PERIOD (fallback)
    # -------------------------------------------------------------------------
    elif state == "SELECT_PERIOD" and message.get("type") == "interactive":
        user_data[whatsapp_number]["period"] = message["interactive"]["button_reply"]["id"]
        user_data[whatsapp_number]["state"] = "SELECT_HOUR"
        get_available_hours(whatsapp_number, user_id, supabase, user_data, "report_symptoms")
        return False

    elif state == "SELECT_HOUR" and message.get("type") == "interactive":
        user_data[whatsapp_number]["hour"] = message["interactive"]["list_reply"]["id"]
        user_data[whatsapp_number]["state"] = "SELECT_TIME_SLOT"
        get_time_slots(whatsapp_number, user_id, supabase, user_data, "report_symptoms")
        return False

    elif state == "SELECT_TIME_SLOT" and message.get("type") == "interactive":
        user_data[whatsapp_number]["time_slot"] = message["interactive"]["list_reply"]["id"]
        get_available_doctors(whatsapp_number, user_id, supabase, user_data, "report_symptoms")
        return False

    # -------------------------------------------------------------------------
    # CONFIRM_BOOKING
    # -------------------------------------------------------------------------
    elif state == "CONFIRM_BOOKING" and message.get("type") == "interactive":
        btn = message["interactive"]["button_reply"]["id"]
        if btn == "confirm_booking":
            pending_id = str(uuid.uuid4())
            doctor_id = user_data[whatsapp_number].get("doctor_id")
            booking = {
                "id": pending_id,
                "user_id": user_id,
                "doctor_id": doctor_id,
                "booking_type": "consultation",
                "details": user_data[whatsapp_number]["details"],
                "date": user_data[whatsapp_number]["date"],
                "time": user_data[whatsapp_number]["time_slot"],
                "duration_minutes": user_data[whatsapp_number]["duration_minutes"],
                "reminder_duration": user_data[whatsapp_number].get("reminder_duration"),
                "reminder_remark": user_data[whatsapp_number].get("reminder_remark"),
                "created_at": datetime.now().isoformat(),
                "notified_doctors": [doctor_id] if doctor_id else [],
                "created_by": user_id
            }
            try:
                supabase.table("c_s_pending_bookings").insert(booking).execute()
                logger.info(f"GP consultation booking {pending_id} saved to pending_bookings")
                
                doctor_name = "Any available doctor"
                if doctor_id:
                    try:
                        doctor_resp = supabase.table("c_a_doctors").select("name").eq("id", doctor_id).execute()
                        if doctor_resp.data:
                            doctor_name = doctor_resp.data[0]["name"]
                    except Exception as e:
                        logger.error(f"Error fetching doctor name: {e}")
                
                # Build confirmation message with translation
                confirmation_template = translate_template(
                    whatsapp_number,
                    "✅ Your GP consultation booking has been submitted!\n\n"
                    "Doctor: {doctor}\n"
                    "Date: {date}\n"
                    "Time: {time}\n"
                    "Duration: {duration} minutes\n"
                    "Symptoms: {symptoms}...\n\n"
                    "Booking is pending approval. You'll be notified once confirmed.\n"
                    "Booking ID: {booking_id}...",
                    supabase
                )
                
                confirmation_message = confirmation_template.format(
                    doctor=doctor_name,
                    date=user_data[whatsapp_number]['date'],
                    time=user_data[whatsapp_number]['time_slot'],
                    duration=user_data[whatsapp_number]['duration_minutes'],
                    symptoms=user_data[whatsapp_number]['symptoms'][:100],
                    booking_id=pending_id[:8]
                )
                
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": confirmation_message}},
                    supabase
                )
                
                try:
                    consultation_id = str(uuid.uuid4())
                    consultation_data = {
                        "id": consultation_id,
                        "user_id": user_id,
                        "doctor_id": doctor_id,
                        "symptoms": user_data[whatsapp_number]["symptoms"],
                        "date": user_data[whatsapp_number]["date"],
                        "time": user_data[whatsapp_number]["time_slot"],
                        "duration_minutes": user_data[whatsapp_number]["duration_minutes"],
                        "reminder_duration": user_data[whatsapp_number].get("reminder_duration"),
                        "reminder_remark": user_data[whatsapp_number].get("reminder_remark"),
                        "details": user_data[whatsapp_number]["details"],
                        "created_by": user_id,
                        "created_at": datetime.now().isoformat(),
                        "updated_at": datetime.now().isoformat()
                    }
                    supabase.table("c_s_consultation").insert(consultation_data).execute()
                    logger.info(f"Also saved to c_s_consultation table: {consultation_id}")
                except Exception as e:
                    logger.warning(f"Could not save to c_s_consultation table: {e}")
                
            except Exception as e:
                logger.error(f"Failed to save GP consultation booking: {e}")
                error_msg = translate_template(
                    whatsapp_number,
                    "Error saving booking. Please try again or contact clinic for assistance.",
                    supabase
                )
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": error_msg}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False
            
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return True
        elif btn == "edit_booking":
            # Handle edit booking
            show_edit_options(whatsapp_number, user_id, supabase, user_data, "report_symptoms")
            return False
        elif btn == "cancel_booking":
            return handle_cancel_booking(whatsapp_number, user_id, supabase, user_data)

    # -------------------------------------------------------------------------
    # EDIT_BOOKING (NEW)
    # -------------------------------------------------------------------------
    elif state == "EDIT_BOOKING" and message.get("type") == "interactive":
        # Handle edit choice selection
        if "list_reply" in message["interactive"]:
            edit_choice = message["interactive"]["list_reply"]["id"]
            handle_edit_choice(whatsapp_number, user_id, supabase, user_data, "report_symptoms", edit_choice)
        return False

    # -------------------------------------------------------------------------
    # Default
    # -------------------------------------------------------------------------
    else:
        current_state = user_data[whatsapp_number].get("state")
        if current_state in ["AWAITING_FUTURE_DATE", "SYMPTOMS_INPUT", "SYMPTOMS_REMARK_INPUT", "AWAITING_TIME_INPUT"]:
            if current_state == "AWAITING_FUTURE_DATE":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        "Please enter your preferred date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:",
                        supabase
                    )}},
                    supabase
                )
            elif current_state == "SYMPTOMS_INPUT":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Please describe your symptoms:", supabase)}},
                    supabase
                )
            elif current_state == "SYMPTOMS_REMARK_INPUT":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Please enter your additional remarks:", supabase)}},
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
                {"text": {"body": translate_template(whatsapp_number, "Invalid input. Please use the buttons provided.", supabase)}},
                supabase
            )
        return False

    return False