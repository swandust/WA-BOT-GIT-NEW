import logging
from datetime import datetime, timedelta, timezone
from utils import send_whatsapp_message, send_interactive_menu, translate_template, gt_tt

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handle_request_report(whatsapp_number, user_id, supabase, user_data, list_reply_id):
    """Handle the report request flow for a past consultation."""
    try:
        # Normalize whatsapp_number
        from_number_norm = whatsapp_number.lstrip("+").strip()
        number_variants = [from_number_norm, f"+{from_number_norm}"]
        logger.info(f"Processing report request for whatsapp_number: {number_variants}")

        # Extract consultation ID from list_reply_id
        try:
            parts = list_reply_id.split('_')
            if len(parts) != 5 or parts[0] != 'request' or parts[1] != 'report' or parts[2] != 'con' or parts[4] != 'con':
                logger.error(f"Invalid list_reply_id format: {list_reply_id}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Invalid selection. Please try again.", supabase)}}
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False
            consult_id = parts[3]
            logger.info(f"Processing report request for consult_id: {consult_id}")
        except Exception as e:
            logger.error(f"Error parsing list_reply_id {list_reply_id}: {e}", exc_info=True)
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Error processing your selection. Please try again.", supabase)}}
            )
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False

        # Fetch consultation details using whatsapp_number
        try:
            consultation = supabase.table("c_post_consult").select(
                "id, doctor_id, patient_name, patient_id, consult_date, diagnosis"
            ).eq("id", consult_id).in_("whatsapp_number", number_variants).single().execute().data
            logger.info(f"Found consultation: {consultation}")
        except Exception as e:
            logger.error(f"Error fetching consultation {consult_id}: {e}", exc_info=True)
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Error fetching consultation details. Please try again.", supabase)}}
            )
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False

        if not consultation:
            logger.warning(f"No consultation found for id: {consult_id} and whatsapp_number: {number_variants}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Consultation not found or not associated with this number. Please try again.", supabase)}}
            )
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False

        # Generate case_id (same as consult_id to link with post_consult.id)
        case_id = consult_id
        logger.info(f"Using case_id: {case_id} for consultation {consult_id}")

        # Insert into report_gen with a default report value
        try:
            # Check if report_gen record exists to avoid duplicates
            existing_report = supabase.table("c_report_gen").select("case_id").eq("case_id", case_id).execute().data
            if not existing_report:
                supabase.table("c_report_gen").insert({
                    "case_id": case_id,
                    "checkbox_list": "pending",
                    "created_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
                    "report": "",  # Default empty string to satisfy NOT NULL constraint
                    "referral_letter_generated": False
                }).execute()
                logger.info(f"Inserted report request into report_gen for case_id: {case_id}")
            else:
                logger.info(f"Report_gen record already exists for case_id: {case_id}")
        except Exception as e:
            logger.error(f"Error inserting into report_gen for case_id {case_id}: {e}", exc_info=True)
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Error generating report request. Please try again.", supabase)}}
            )
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False

        # Check for existing report_send_wait record
        try:
            existing_wait = supabase.table("c_report_send_wait").select("status").eq("case_id", case_id).single().execute().data
            if existing_wait:
                if existing_wait["status"] == 1:
                    # Update status to 2 after sending verification message
                    supabase.table("c_report_send_wait").update({
                        "status": 2
                    }).eq("case_id", case_id).execute()
                    logger.info(f"Updated report_send_wait to status 2 for case_id: {case_id}")
                else:
                    logger.info(f"Report_send_wait for case_id {case_id} already has status: {existing_wait['status']}")
            else:
                # Insert new record with status 1
                supabase.table("c_report_send_wait").insert({
                    "case_id": case_id,
                    "status": 1
                }).execute()
                logger.info(f"Inserted into report_send_wait with status 1 for case_id: {case_id}")
        except Exception as e:
            logger.error(f"Error processing report_send_wait for case_id {case_id}: {e}", exc_info=True)
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Error processing report request. Please try again.", supabase)}}
            )
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False

        # Send verification message
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Please enter the patient's IC in the format 'verified:<IC>', e.g., verified:123456789011", supabase)}}
        )
        user_data[whatsapp_number]["state"] = "AWAITING_VERIFICATION"
        user_data[whatsapp_number]["list_reply_id"] = list_reply_id
        return False

    except Exception as e:
        logger.error(f"Unexpected error in handle_request_report for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "An unexpected error occurred while processing your report request. Please try again.", supabase)}}
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def handle_verification_response(whatsapp_number, user_id, supabase, user_data, button_id=None, user_text=None):
    """Handle verification response for report requests."""
    try:
        if button_id == "request_report":
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Please enter the patient's IC in the format 'verified:<IC>', e.g., verified:123456789011", supabase)}}
            )
            user_data[whatsapp_number]["state"] = "AWAITING_VERIFICATION"
            return False

        if user_text and user_text.lower().startswith("verified:"):
            ic_number = user_text[len("verified:"):].strip()
            # Normalize whatsapp_number
            from_number_norm = whatsapp_number.lstrip("+").strip()
            number_variants = [from_number_norm, f"+{from_number_norm}"]
            logger.info(f"Processing IC verification: {ic_number} for whatsapp_number: {number_variants}")

            # Check if awaiting verification for a report request
            if user_data[whatsapp_number].get("state") == "AWAITING_VERIFICATION" and user_data[whatsapp_number].get("list_reply_id"):
                list_reply_id = user_data[whatsapp_number]["list_reply_id"]
                parts = list_reply_id.split('_')
                if len(parts) != 5 or parts[0] != 'request' or parts[1] != 'report' or parts[2] != 'con' or parts[4] != 'con':
                    logger.error(f"Invalid list_reply_id format: {list_reply_id}")
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "Invalid selection. Please try again.", supabase)}}
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return False
                consult_id = parts[3]

                # Fetch consultation details to verify IC
                try:
                    consultation = supabase.table("c_post_consult").select(
                        "patient_id, consult_date, diagnosis"
                    ).eq("id", consult_id).in_("whatsapp_number", number_variants).single().execute().data
                    if not consultation:
                        logger.warning(f"No consultation found for id: {consult_id} and whatsapp_number: {number_variants}")
                        send_whatsapp_message(
                            whatsapp_number,
                            "text",
                            {"text": {"body": translate_template(whatsapp_number, "Consultation not found or not associated with this number. Please try again.", supabase)}}
                        )
                        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                        send_interactive_menu(whatsapp_number, supabase)
                        return False
                except Exception as e:
                    logger.error(f"Error fetching consultation {consult_id}: {e}", exc_info=True)
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "Error fetching consultation details. Please try again.", supabase)}}
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return False

                # Verify IC
                if consultation["patient_id"] != ic_number:
                    logger.warning(f"IC verification failed for {whatsapp_number}: {ic_number} does not match {consultation['patient_id']}")
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "IC verification failed. Please enter the correct patient IC.", supabase)}}
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return False

                # Fetch the most recent report_gen record to handle duplicates
                try:
                    report_gen_records = supabase.table("c_report_gen").select(
                        "case_id, report, referral_letter_generated, checkbox_list"
                    ).eq("case_id", consult_id).order("created_at", desc=True).limit(1).execute().data
                    if not report_gen_records:
                        logger.warning(f"No report_gen entry found for case_id: {consult_id}")
                        send_whatsapp_message(
                            whatsapp_number,
                            "text",
                            {"text": {"body": translate_template(whatsapp_number, "No report request found. Please try again.", supabase)}}
                        )
                        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                        send_interactive_menu(whatsapp_number, supabase)
                        return False
                    report_gen = report_gen_records[0]
                    case_id = report_gen["case_id"]
                except Exception as e:
                    logger.error(f"Error fetching report_gen for case_id {consult_id}: {e}", exc_info=True)
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "Error processing report request. Please try again.", supabase)}}
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return False

                # Fetch report_send_wait to verify status
                try:
                    send_wait = supabase.table("c_report_send_wait").select("case_id, status").eq("case_id", case_id).single().execute().data
                    if not send_wait or send_wait["status"] != 2:
                        logger.warning(f"Invalid report_send_wait status for case_id: {case_id}, status: {send_wait.get('status') if send_wait else 'not found'}")
                        send_whatsapp_message(
                            whatsapp_number,
                            "text",
                            {"text": {"body": translate_template(whatsapp_number, "Invalid report request status. Please try again.", supabase)}}
                        )
                        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                        send_interactive_menu(whatsapp_number, supabase)
                        return False
                except Exception as e:
                    logger.error(f"Error fetching report_send_wait for case_id {case_id}: {e}", exc_info=True)
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "Error processing report request. Please try again.", supabase)}}
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return False

                # Insert into report_verified with case_id and status from report_send_wait
                try:
                    # Check for existing report_verified record to avoid duplicates
                    existing_verified = supabase.table("c_report_verified").select("case_id").eq("case_id", case_id).execute().data
                    if existing_verified:
                        logger.info(f"Report_verified record already exists for case_id: {case_id}")
                    else:
                        supabase.table("c_report_verified").insert({
                            "case_id": send_wait["case_id"],
                            "status": send_wait["status"]
                        }).execute()
                        logger.info(f"Inserted into report_verified with case_id: {case_id}, status: {send_wait['status']}")
                except Exception as e:
                    logger.error(f"Error inserting into report_verified for case_id {case_id}: {e}", exc_info=True)
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "Error processing verification. Please try again.", supabase)}}
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return False

                # Send the report immediately if available
                if report_gen["report"]:
                    try:
                        consult_datetime = datetime.fromisoformat(consultation['consult_date'].replace("Z", "+00:00")) + timedelta(hours=8)
                        referral_message = translate_template(
                            whatsapp_number,
                            "A referral letter has been generated. Please contact your healthcare provider for details." if report_gen["referral_letter_generated"] else "No referral required.",
                            supabase
                        )
                        message = translate_template(
                            whatsapp_number,
                            "IC verified. Report for consultation on {} (Diagnosis: {}):\n{}\n\n{}",
                            supabase
                        ).format(
                            consult_datetime.strftime('%Y-%m-%d %H:%M'),
                            gt_tt(whatsapp_number, consultation['diagnosis'] or 'N/A', supabase),
                            gt_tt(whatsapp_number, report_gen['report'] or 'N/A', supabase),
                            referral_message
                        )
                        send_whatsapp_message(
                            whatsapp_number,
                            "text",
                            {"text": {"body": message}}
                        )
                        logger.info(f"Sent report for case_id: {case_id}")
                    except Exception as e:
                        logger.error(f"Error sending report for case_id {case_id}: {e}", exc_info=True)
                        send_whatsapp_message(
                            whatsapp_number,
                            "text",
                            {"text": {"body": translate_template(whatsapp_number, "IC verified, but error sending report. Please try again.", supabase)}}
                        )
                        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                        send_interactive_menu(whatsapp_number, supabase)
                        return False
                else:
                    # No report available yet
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "IC verified, but the report is not yet available. You will be notified when ready.", supabase)}}
                    )

                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return True

            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "IC verified successfully, but no report request pending. Please select a consultation.", supabase)}}
            )
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False
        else:
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Invalid verification format. Please use 'verified:<IC>'.", supabase)}}
            )
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False
    except Exception as e:
        logger.error(f"Error in handle_verification_response for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing verification. Please try again.", supabase)}}
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False