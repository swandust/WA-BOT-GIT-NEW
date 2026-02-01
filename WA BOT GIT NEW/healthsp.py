# healthsp.py - UPDATED VERSION WITH CORRECT TRANSLATION FUNCTIONS
import uuid
import logging
import time
from datetime import datetime

from calendar_utils import (
    get_doctors, get_calendar, select_period, get_available_hours,
    get_time_slots, get_available_doctors, get_service_duration,
    handle_cancel_booking, handle_future_date_input, handle_future_date_confirmation,
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

def handle_healthsp(whatsapp_number, user_id, supabase, user_data, message):
    state = user_data.get(whatsapp_number, {}).get("state", "IDLE")
    logger.info(f"Handling health screening for {whatsapp_number}, state: {state}")

    # ------------------------------------------------------------------
    # 1. FETCH USER LANGUAGE
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 2. IDLE → show category image + service list
    # ------------------------------------------------------------------
    if state == "IDLE":
        # Get clinic ID from user data
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
        
        # Store clinic_id in user_data
        user_data[whatsapp_number]["clinic_id"] = clinic_id
        
        # Get service details
        service_id = user_data[whatsapp_number].get("service_id")
        service_name = user_data[whatsapp_number].get("service_name", "Health Screening")
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
        
        logger.info(f"Using clinic_id: {clinic_id} for {whatsapp_number} - Health Screening, service: {service_name}")
        
        # Fetch health screening service details from DB
        try:
            service_resp = supabase.table("c_a_clinic_service") \
                .select("duration_minutes, reminder_duration, reminder_remark, description, brochure_image_url, doctor_id") \
                .eq("id", service_id) \
                .eq("clinic_id", clinic_id) \
                .eq("is_active", True) \
                .maybe_single().execute()
            
            if service_resp.data:
                duration = service_resp.data.get("duration_minutes", 30)
                reminder_dur = service_resp.data.get("reminder_duration")
                reminder_rem = service_resp.data.get("reminder_remark")
                doctor_id = service_resp.data.get("doctor_id")
                db_description = service_resp.data.get("description", "")
                if db_description:
                    description = db_description
                brochure = service_resp.data.get("brochure_image_url")
                
                logger.info(f"Found health screening service {service_id} for clinic {clinic_id}")
            else:
                # Try without clinic_id as fallback
                fallback_resp = supabase.table("c_a_clinic_service") \
                    .select("duration_minutes, reminder_duration, reminder_remark, description, brochure_image_url, doctor_id") \
                    .eq("id", service_id) \
                    .eq("is_active", True) \
                    .maybe_single().execute()
                
                if fallback_resp.data:
                    duration = fallback_resp.data.get("duration_minutes", 30)
                    reminder_dur = fallback_resp.data.get("reminder_duration")
                    reminder_rem = fallback_resp.data.get("reminder_remark")
                    doctor_id = fallback_resp.data.get("doctor_id")
                    db_description = fallback_resp.data.get("description", "")
                    if db_description:
                        description = db_description
                    brochure = fallback_resp.data.get("brochure_image_url")
                    logger.info(f"Found health screening service {service_id} (without clinic filter)")
                else:
                    duration = 30
                    reminder_dur = None
                    reminder_rem = None
                    doctor_id = None
                    brochure = None
                    logger.warning(f"No service details found for ID: {service_id}")
                    
        except Exception as e:
            logger.error(f"Error fetching health screening service details: {e}")
            duration = 30
            reminder_dur = None
            reminder_rem = None
            doctor_id = None
            brochure = None

        # Store all data
        user_data[whatsapp_number] = {
            "state": "HEALTHSP_REMARK_YES_NO",
            "module": "health_screening",
            "language": language,
            "clinic_id": clinic_id,
            "service_id": service_id,
            "healthsp_type": service_name,
            "display_healthsp_type": service_name,
            "service_description": description.strip(),
            "duration_minutes": duration,
            "reminder_duration": reminder_dur,
            "reminder_remark": reminder_rem,
            "brochure_image_url": brochure
        }

        # Send brochure image if available (Image Only)
        sent = False
        if brochure:
            send_image_message(whatsapp_number, brochure, supabase)
            sent = True
            time.sleep(1)
        
        # Send description separately (Description Only)
        if description.strip():
            # Use gt_dt_tt for description (72 char limit)
            truncated_desc = gt_dt_tt(whatsapp_number, description.strip(), supabase)
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": truncated_desc}},
                supabase
            )
            sent = True
            time.sleep(1)

        # Ask for remarks
        prompt = gt_tt(
            whatsapp_number,
            "Do you have any remarks for {} ({} min){}?", supabase
        ).format(service_name, duration,
                 f" [{gt_dt_tt(whatsapp_number, description.strip(), supabase)}]" if description.strip() and not sent else "")
        
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

    # ------------------------------------------------------------------
    # 3. REMARK YES/NO
    # ------------------------------------------------------------------
    elif state == "HEALTHSP_REMARK_YES_NO" and message.get("type") == "interactive":
        btn = message["interactive"]["button_reply"]["id"]
        if btn == "remark_yes":
            user_data[whatsapp_number]["state"] = "HEALTHSP_REMARK_INPUT"
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Please enter your remarks:", supabase)}},
                supabase
            )
        else:
            # No remark → store the plan name as details
            user_data[whatsapp_number]["details"] = user_data[whatsapp_number]["healthsp_type"]
            user_data[whatsapp_number]["state"] = "SELECT_DOCTOR"
            get_doctors(whatsapp_number, user_id, supabase, user_data, "health_screening")
        return False

    # ------------------------------------------------------------------
    # 4. REMARK INPUT
    # ------------------------------------------------------------------
    elif state == "HEALTHSP_REMARK_INPUT" and message.get("type") == "text":
        remark = message["text"]["body"].strip()
        details = f"{user_data[whatsapp_number]['healthsp_type']}: {remark}"
        user_data[whatsapp_number]["details"] = details
        user_data[whatsapp_number]["state"] = "SELECT_DOCTOR"
        get_doctors(whatsapp_number, user_id, supabase, user_data, "health_screening")
        return False

    # ------------------------------------------------------------------
    # 5. CALENDAR FLOW
    # ------------------------------------------------------------------
    elif state == "SELECT_DOCTOR" and message.get("type") == "interactive":
        sel = message["interactive"]["list_reply"]["id"]
        if sel == "any_doctor":
            user_data[whatsapp_number]["any_doctor"] = True
            user_data[whatsapp_number]["doctor_id"] = None
        else:
            user_data[whatsapp_number]["doctor_id"] = sel
            user_data[whatsapp_number]["any_doctor"] = False
        user_data[whatsapp_number]["state"] = "SELECT_DATE"
        get_calendar(whatsapp_number, user_id, supabase, user_data, "health_screening")
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
            user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"  # NEW FLOW
            
            # Ask for preferred time input
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "Please enter your preferred time (e.g., 9:30, 2pm, 1430):",
                    supabase
                )}},
                supabase
            )
        return False

    elif state == "AWAITING_FUTURE_DATE" and message.get("type") == "text":
        date_input = message["text"]["body"].strip()
        handle_future_date_input(whatsapp_number, user_id, supabase, user_data, "health_screening", date_input)
        return False

    elif state == "CONFIRM_FUTURE_DATE" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        if button_id == "confirm_future_date":
            handle_future_date_confirmation(whatsapp_number, user_id, supabase, user_data, "health_screening", confirmed=True)
        elif button_id == "reject_future_date":
            handle_future_date_confirmation(whatsapp_number, user_id, supabase, user_data, "health_screening", confirmed=False)
        return False

        # ------------------------------------------------------------------
    # NEW: TIME INPUT FLOW STATES (for health screening)
    # ------------------------------------------------------------------
    elif state == "AWAITING_TIME_INPUT" and message.get("type") == "text":
        time_input = message["text"]["body"].strip()
        handle_time_input(whatsapp_number, user_id, supabase, user_data, "health_screening", time_input)
        return False

    elif state == "CONFIRM_TIME" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        if button_id == "confirm_time":
            handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, "health_screening", confirmed=True)
        elif button_id == "find_another_time":
            handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, "health_screening", confirmed=False)
        return False

    elif state == "CONFIRM_CLOSEST_TIME" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        if button_id == "accept_closest_time":
            handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, "health_screening", confirmed=True, use_closest=True)
        elif button_id == "find_another_time":
            handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, "health_screening", confirmed=False)
        return False

    elif state == "RETRY_TIME_OR_HELP" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        handle_retry_time_or_help(whatsapp_number, user_id, supabase, user_data, "health_screening", button_id)
        return False

    # ------------------------------------------------------------------
    # 6. CONFIRM BOOKING - Save to pending_bookings (same as healthsp.py)
    # ------------------------------------------------------------------
    elif state == "CONFIRM_BOOKING" and message.get("type") == "interactive":
        btn = message["interactive"]["button_reply"]["id"]
        if btn == "confirm_booking":
            pending_id = str(uuid.uuid4())
            booking = {
                "id": pending_id,
                "user_id": user_id,
                "doctor_id": user_data[whatsapp_number].get("doctor_id"),
                "booking_type": "checkup",  # health screening uses checkup type
                "details": user_data[whatsapp_number]["details"],
                "date": user_data[whatsapp_number]["date"],
                "time": user_data[whatsapp_number]["time_slot"],
                "duration_minutes": user_data[whatsapp_number]["duration_minutes"],
                "reminder_duration": user_data[whatsapp_number].get("reminder_duration"),
                "reminder_remark": user_data[whatsapp_number].get("reminder_remark"),
                "created_at": datetime.now().isoformat(),
                "notified_doctors": [user_data[whatsapp_number]["doctor_id"]]
                if user_data[whatsapp_number].get("doctor_id") else [],
                "created_by": user_id,
                "checkin": False
                # DO NOT include service_id or clinic_id
            }

            try:
                supabase.table("c_s_pending_bookings").insert(booking).execute()
                logger.info(f"Health screening booking {pending_id} saved. Details: {booking['details']}")
                
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": gt_tt(whatsapp_number,
                                             "✅ Your health screening booking has been submitted!\n\n"
                                             f"Service: {user_data[whatsapp_number]['healthsp_type']}\n"
                                             f"Date: {user_data[whatsapp_number]['date']}\n"
                                             f"Time: {user_data[whatsapp_number]['time_slot']}\n"
                                             f"Duration: {user_data[whatsapp_number]['duration_minutes']} minutes\n\n"
                                             "Booking is pending approval. You'll be notified once confirmed.\n"
                                             f"Booking ID: {pending_id[:8]}...", supabase)}},
                    supabase
                )
                
            except Exception as e:
                logger.error(f"Failed to save health screening booking: {e}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number,
                                             "Error saving booking. Please try again.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number]["state"] = "IDLE"
                user_data[whatsapp_number]["module"] = None
                send_interactive_menu(whatsapp_number, supabase)
                return False

            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return True

        elif btn == "edit_booking":
            # Handle edit booking
            show_edit_options(whatsapp_number, user_id, supabase, user_data, "health_screening")
            return False
            
        elif btn == "cancel_booking":
            return handle_cancel_booking(whatsapp_number, user_id, supabase, user_data)

    # ------------------------------------------------------------------
    # EDIT_BOOKING (NEW)
    # ------------------------------------------------------------------
    elif state == "EDIT_BOOKING" and message.get("type") == "interactive":
        # Handle edit choice selection
        if "list_reply" in message["interactive"]:
            edit_choice = message["interactive"]["list_reply"]["id"]
            handle_edit_choice(whatsapp_number, user_id, supabase, user_data, "health_screening", edit_choice)
        return False

    # ------------------------------------------------------------------
    # 7. FALLBACK
    # ------------------------------------------------------------------
    else:
        current_state = user_data[whatsapp_number].get("state")
        if current_state in ["AWAITING_FUTURE_DATE", "HEALTHSP_REMARK_INPUT", "AWAITING_TIME_INPUT"]:
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
            elif current_state == "HEALTHSP_REMARK_INPUT":
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
                    )}},
                    supabase
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