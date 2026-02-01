import uuid
import logging
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
    gt_t_tt, gt_tt, send_image_message, send_document
)
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handle_report_booking(whatsapp_number, user_id, supabase, user_data, message):
    state = user_data.get(whatsapp_number, {}).get("state", "IDLE")
    logger.info(f"Report-booking for {whatsapp_number}, state: {state}")

    language = "en"
    try:
        resp = supabase.table("whatsapp_users") \
            .select("language") \
            .eq("whatsapp_number", whatsapp_number.lstrip("+")) \
            .limit(1).execute()
        if resp.data:
            language = resp.data[0]["language"]
    except Exception as e:
        logger.error(f"Language fetch error: {e}")

    if state == "IDLE":
        user_data[whatsapp_number] = {
            "state": "SELECT_REPORT",
            "module": "checkup_result_booking",
            "language": language
        }
        try:
            resp = supabase.table("c_report_consult") \
                .select("*") \
                .eq("user_id", user_id) \
                .eq("is_deleted", False) \
                .eq("sent", True) \
                .execute()
            reports = resp.data
            if not reports:
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        "No pending reports found. Please book a checkup first.",
                        supabase)}}
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False

            rows = []
            cached_reports = []
            for i, r in enumerate(reports, 1):
                doc_resp = supabase.table("c_a_doctors") \
                    .select("name, clinic_id").eq("id", r["doctor_id"]).single().execute()
                doc = doc_resp.data or {}
                doctor_name = doc.get("name", "Unknown Doctor")
                clinic_name = "Unknown Clinic"
                clinic_id = doc.get("clinic_id")
                if clinic_id:
                    cli_resp = supabase.table("c_a_clinics") \
                        .select("name").eq("id", clinic_id).single().execute()
                    clinic_name = cli_resp.data.get("name", clinic_name) if cli_resp.data else clinic_name
                
                notif_trans = gt_tt(
                    whatsapp_number,
                    r.get("notification") or "Report Review",
                    supabase,
                    doctor_name=doctor_name
                )
                line = translate_template(
                    whatsapp_number,
                    "{} by {} in {}",
                    supabase
                ).format(notif_trans, doctor_name, clinic_name)
                rows.append({"id": r["id"], "title": f"Booking {i}"})
                cached_reports.append({
                    "id": r["id"],
                    "doctor_id": r["doctor_id"],
                    "doctor_name": doctor_name,
                    "clinic_id": clinic_id,
                    "clinic_name": clinic_name,
                    "original_notification": r.get("notification") or "Report Review",
                    "translated_notification": notif_trans,
                    "display": f"{notif_trans} with {doctor_name}",
                    "pdf_url": r.get("pdf_url")
                })
            body = translate_template(
                whatsapp_number,
                "Choose a report to book review:\n{}",
                supabase
            ).format("\n".join([f"{i}. {r['display']}" for i, r in enumerate(cached_reports, 1)]))
            send_whatsapp_message(
                whatsapp_number,
                "interactive",
                {
                    "interactive": {
                        "type": "list",
                        "header": {"type": "text", "text": translate_template(whatsapp_number, "Select Report", supabase)},
                        "body": {"text": body[:1020] + ("..." if len(body) > 1020 else "")},
                        "action": {
                            "button": translate_template(whatsapp_number, "Select Report", supabase),
                            "sections": [{"title": translate_template(whatsapp_number, "Your Reports", supabase), "rows": rows}]
                        }
                    }
                },
                supabase
            )
            user_data[whatsapp_number]["reports_list"] = cached_reports
            return False
        except Exception as e:
            logger.error(f"Report fetch error: {e}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Error loading reports.", supabase)}},
                supabase
            )
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False

    # -------------------------------------------------------------------------
    # SELECT_REPORT
    # -------------------------------------------------------------------------
    elif state == "SELECT_REPORT" and message.get("type") == "interactive" \
            and message["interactive"].get("type") == "list_reply":
        selected_id = message["interactive"]["list_reply"]["id"]
        report = next((r for r in user_data[whatsapp_number]["reports_list"] if r["id"] == selected_id), None)
        if not report:
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Invalid report selection.", supabase)}},
                supabase
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            send_interactive_menu(whatsapp_number, supabase)
            return False
        user_data[whatsapp_number].update({
            "selected_report": report,
            "state": "REPORT_OPTION_MENU"
        })
        send_whatsapp_message(
            whatsapp_number,
            "interactive",
            {
                "interactive": {
                    "type": "button",
                    "body": {"text": translate_template(
                        whatsapp_number,
                        "What would you like to do with this report?\n\n*{}*",
                        supabase
                    ).format(report["display"])},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": "request_pdf", "title": translate_template(whatsapp_number, "Request PDF", supabase)}},
                            {"type": "reply", "reply": {"id": "consultation", "title": translate_template(whatsapp_number, "Consultation", supabase)}}
                        ]
                    }
                }
            },
            supabase
        )
        return False

    # -------------------------------------------------------------------------
    # REPORT_OPTION_MENU
    # -------------------------------------------------------------------------
    elif state == "REPORT_OPTION_MENU" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        report = user_data[whatsapp_number].get("selected_report", {})
        if button_id == "request_pdf":
            return _handle_pdf_request(whatsapp_number, user_id, supabase, user_data, report)
        elif button_id == "consultation":
            return _start_consultation_booking(whatsapp_number, user_id, supabase, user_data, report)

    # -------------------------------------------------------------------------
    # PDF_REQUEST_MENU
    # -------------------------------------------------------------------------
    elif state == "PDF_REQUEST_MENU" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        if button_id == "consultation_after_pdf":
            report = user_data[whatsapp_number].get("selected_report", {})
            return _start_consultation_booking(whatsapp_number, user_id, supabase, user_data, report)
        elif button_id == "back_to_main":
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False

    # -------------------------------------------------------------------------
    # SELECT_DOCTOR
    # -------------------------------------------------------------------------
    elif state == "SELECT_DOCTOR" and message.get("type") == "interactive":
        sel = message["interactive"]["list_reply"]["id"]
        if sel == "any_doctor":
            user_data[whatsapp_number]["any_doctor"] = True
            user_data[whatsapp_number]["doctor_id"] = None
        else:
            user_data[whatsapp_number]["doctor_id"] = sel
            user_data[whatsapp_number]["any_doctor"] = False
        user_data[whatsapp_number]["state"] = "SELECT_DATE"
        get_calendar(whatsapp_number, user_id, supabase, user_data, "checkup_result_booking")
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
        handle_time_input(whatsapp_number, user_id, supabase, user_data, "checkup_result_booking", time_input)
        return False

    # -------------------------------------------------------------------------
    # CONFIRM_TIME (NEW)
    # -------------------------------------------------------------------------
    elif state == "CONFIRM_TIME" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        if button_id == "confirm_time":
            handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, "checkup_result_booking", confirmed=True, use_closest=False)
        elif button_id == "find_another_time":
            user_data[whatsapp_number].pop("parsed_time_input", None)
            user_data[whatsapp_number].pop("closest_available_time", None)
            user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
            select_period(whatsapp_number, user_id, supabase, user_data, "checkup_result_booking")
        return False

    # -------------------------------------------------------------------------
    # CONFIRM_CLOSEST_TIME (NEW)
    # -------------------------------------------------------------------------
    elif state == "CONFIRM_CLOSEST_TIME" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        if button_id == "accept_closest_time":
            handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, "checkup_result_booking", confirmed=True, use_closest=True)
        elif button_id == "find_another_time":
            user_data[whatsapp_number].pop("parsed_time_input", None)
            user_data[whatsapp_number].pop("closest_available_time", None)
            user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
            select_period(whatsapp_number, user_id, supabase, user_data, "checkup_result_booking")
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
            select_period(whatsapp_number, user_id, supabase, user_data, "checkup_result_booking")
        return False

    # -------------------------------------------------------------------------
    # AWAITING_FUTURE_DATE
    # -------------------------------------------------------------------------
    elif state == "AWAITING_FUTURE_DATE" and message.get("type") == "text":
        date_input = message["text"]["body"].strip()
        handle_future_date_input(whatsapp_number, user_id, supabase, user_data, "checkup_result_booking", date_input)
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
            handle_future_date_confirmation(whatsapp_number, user_id, supabase, user_data, "checkup_result_booking", confirmed=False)
        return False

    # -------------------------------------------------------------------------
    # SELECT_PERIOD (fallback)
    # -------------------------------------------------------------------------
    elif state == "SELECT_PERIOD" and message.get("type") == "interactive" \
            and message["interactive"].get("type") == "button_reply":
        user_data[whatsapp_number]["period"] = message["interactive"]["button_reply"]["id"]
        user_data[whatsapp_number]["state"] = "SELECT_HOUR"
        get_available_hours(whatsapp_number, user_id, supabase, user_data, "checkup_result_booking")
        return False

    elif state == "SELECT_HOUR" and message.get("type") == "interactive":
        user_data[whatsapp_number]["hour"] = message["interactive"]["list_reply"]["id"]
        user_data[whatsapp_number]["state"] = "SELECT_TIME_SLOT"
        get_time_slots(whatsapp_number, user_id, supabase, user_data, "checkup_result_booking")
        return False

    elif state == "SELECT_TIME_SLOT" and message.get("type") == "interactive":
        user_data[whatsapp_number]["time_slot"] = message["interactive"]["list_reply"]["id"]
        get_available_doctors(whatsapp_number, user_id, supabase, user_data, "checkup_result_booking")
        return False

    # -------------------------------------------------------------------------
    # CONFIRM_BOOKING
    # -------------------------------------------------------------------------
    elif state == "CONFIRM_BOOKING" and message.get("type") == "interactive":
        btn = message["interactive"]["button_reply"]["id"]
        if btn == "confirm_booking":
            pending_id = str(uuid.uuid4())
            report_type = "Report Review"
            doctor_name = user_data[whatsapp_number].get("selected_report", {}).get("doctor_name", "Doctor")
            details = f"{report_type} - {doctor_name}"
            if len(details) > 100:
                details = details[:97] + "..."
            
            booking_payload = {
                "id": pending_id,
                "user_id": user_id,
                "booking_type": "checkup",
                "details": details,
                "date": user_data[whatsapp_number]["date"],
                "time": user_data[whatsapp_number]["time_slot"],
                "duration_minutes": 30,
                "created_at": datetime.now().isoformat(),
                "notified_doctors": (
                    [user_data[whatsapp_number]["doctor_id"]]
                    if user_data[whatsapp_number].get("doctor_id")
                    else []
                )
            }
            if user_data[whatsapp_number].get("doctor_id"):
                booking_payload["doctor_id"] = user_data[whatsapp_number]["doctor_id"]
            try:
                supabase.table("c_s_pending_bookings").insert(booking_payload).execute()
                supabase.table("c_report_consult") \
                    .update({"is_deleted": True}) \
                    .eq("id", user_data[whatsapp_number]["report_id"]) \
                    .execute()
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": gt_tt(
                        whatsapp_number,
                        "Your report review booking is pending approval by the admin.",
                        supabase)}}
                )
                logger.info(f"Report booking {pending_id} saved successfully")
            except Exception as e:
                logger.error(f"Booking save error: {e}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        "Error saving booking. Please try again.",
                        supabase)}}
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return True
            
        elif btn == "edit_booking":
            # Handle edit booking
            show_edit_options(whatsapp_number, user_id, supabase, user_data, "checkup_result_booking")
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
            handle_edit_choice(whatsapp_number, user_id, supabase, user_data, "checkup_result_booking", edit_choice)
        return False

    # -------------------------------------------------------------------------
    # Default
    # -------------------------------------------------------------------------
    else:
        current_state = user_data[whatsapp_number].get("state")
        if current_state in ["AWAITING_FUTURE_DATE", "AWAITING_TIME_INPUT"]:
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

def _handle_pdf_request(whatsapp_number, user_id, supabase, user_data, report):
    if report.get("pdf_url"):
        pdf_sent = send_document(
            whatsapp_number,
            report["pdf_url"],
            caption=translate_template(whatsapp_number, "Your report PDF", supabase),
            filename=f"report_{report['id']}.pdf",
            supabase=supabase
        )
        if pdf_sent:
            message = translate_template(
                whatsapp_number,
                "Your report PDF has been sent. Would you like to book a consultation to discuss the results?",
                supabase
            )
        else:
            message = translate_template(
                whatsapp_number,
                "Failed to send PDF. Please try again later or book a consultation.",
                supabase
            )
    else:
        message = translate_template(
            whatsapp_number,
            "PDF report is not yet available. Would you like to book a consultation with the doctor?",
            supabase
        )
    user_data[whatsapp_number]["state"] = "PDF_REQUEST_MENU"
    send_whatsapp_message(
        whatsapp_number,
        "interactive",
        {
            "interactive": {
                "type": "button",
                "body": {"text": message},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "consultation_after_pdf", "title": translate_template(whatsapp_number, "Consultation", supabase)}},
                        {"type": "reply", "reply": {"id": "back_to_main", "title": translate_template(whatsapp_number, "Back to Main Menu", supabase)}}
                    ]
                }
            }
        },
        supabase
    )
    return False

def _start_consultation_booking(whatsapp_number, user_id, supabase, user_data, report):
    clinic_id = report.get("clinic_id")
    if not clinic_id and report.get("doctor_id"):
        try:
            doc_resp = supabase.table("c_a_doctors") \
                .select("clinic_id").eq("id", report["doctor_id"]).single().execute()
            if doc_resp.data:
                clinic_id = doc_resp.data.get("clinic_id")
        except Exception as e:
            logger.error(f"Error fetching doctor's clinic: {e}")
    if not clinic_id:
        clinic_id = "76d39438-a2c4-4e79-83e8-000000000000"
    
    user_data[whatsapp_number].update({
        "doctor_id": None,
        "clinic_id": clinic_id,
        "duration_minutes": 30,
        "service_id": None,
        "checkup_type": f"Report Review: {report['original_notification']}",
        "display_checkup_type": report["display"],
        "report_id": report["id"],
        "state": "SELECT_DOCTOR",
        "selected_report": report
    })
    get_doctors(whatsapp_number, user_id, supabase, user_data, "checkup_result_booking")
    return False