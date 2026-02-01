# main.py - UPDATED WITH FIX FOR VIEW_BOOKING FUTURE DATE HANDLING AND LOCATION FIX
import uuid
import threading
import time
import logging
from supabase import create_client, Client
import schedule
from utils import get_user_id, send_whatsapp_message, send_interactive_menu, translate_template, gt_t_tt, gt_tt, get_user_language, lookup_clinic_by_keyword
from notification import process_notifications, check_and_send_reminder_notifications, display_and_clear_notifications, handle_notification_noted, check_and_send_booking_confirmations, send_immediate_booking_confirmations
from menu import handle_menu_selection
from report_symptoms import handle_symptoms
from checkup_booking import handle_checkup
from ReportBooking import handle_report_booking
from vaccination_booking import handle_vaccination
from view_booking import handle_view_upcoming_booking, handle_view_booking
from post_report import handle_verification_response, handle_request_report
from calendar_utils import handle_cancel_booking
from concierge import handle_concierge_input
from clinicfd import handle_clinic_enquiries, handle_ai_service_input, initialize_matcher
from healthsp import handle_healthsp
from afterservice import (
    check_and_send_followup_messages,
    handle_followup_response,
    handle_symptom_tracker_response,
    handle_symptom_tracker_selection,
    test_immediate_followup_all,
    detect_and_save_template_response
)


# ===== AMBULANCE MODULE IMPORTS =====
from ambulance_booking import handle_booking_response, handle_booking_start
from ambulance_homehome import handle_homehome_response, handle_homehome_start


# ===== ADD TCM SERVICE IMPORT =====
from tcm_service import handle_tcm_service


# ===== ADD INDIVIDUAL MODULE IMPORT =====
from individual import handle_individual_response, handle_individual_start


import os
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
import pytz


# Load environment variables
load_dotenv()


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


scheduler_lock = threading.Lock()


# Replace the hardcoded Supabase credentials:
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# Initialize the NLP matcher after Supabase client is created
initialize_matcher(supabase)


# User data store for conversation state
user_data = {}


# ===== UPDATED MAIN_MENU_IDS WITH NEW STRUCTURE =====
MAIN_MENU_IDS = [
    "notification", "profile", "service_booking", "upcoming_booking",
    "help", "languages"
]


def handle_status_update(value):
    """Handle status updates from WhatsApp webhook."""
    try:
        statuses = value.get("statuses", [])
        if not statuses:
            return
       
        for status in statuses:
            recipient_id = status.get("recipient_id")
            status_type = status.get("status")
            message_id = status.get("id")
           
            logger.info(f"Message status update: {status_type} for {recipient_id}")
           
            # Handle failed status due to 24-hour rule
            if status_type == "failed":
                errors = status.get("errors", [])
                for error in errors:
                    error_code = error.get("code")
                   
                    # 131047 = 24-hour rule violation
                    if error_code == 131047:
                        logger.warning(f"⚠️ Message failed due to 24-hour rule for {recipient_id}")
                       
                        # Check if this is a follow-up message by checking the database
                        try:
                            # Check if this user has an active follow-up in either table
                            whatsapp_number_norm = recipient_id.lstrip('+')
                           
                            # Check c_followup table
                            c_followup = supabase.table("c_followup").select("*")\
                                .eq("whatsapp_number", whatsapp_number_norm)\
                                .eq("followup", True)\
                                .execute()
                           
                            # Check actual_followup table  
                            actual_followup = supabase.table("actual_followup").select("*")\
                                .eq("whatsapp_number", whatsapp_number_norm)\
                                .eq("followup", True)\
                                .execute()
                           
                            if c_followup.data or actual_followup.data:
                                # This is a follow-up message that failed - send followup template
                                logger.info(f"📋 Detected failed follow-up message for {recipient_id}")
                               
                                # Get user's language
                                language = get_user_language(supabase, recipient_id)
                               
                                # Send followup template (NOT general template!)
                                template_name = f"followup_{language}"
                                logger.info(f"🚨 Sending followup template {template_name} to {recipient_id}")
                               
                                from utils import send_template_message
                                success = send_template_message(recipient_id, template_name, supabase)
                               
                                if success:
                                    logger.info(f"✅ Followup template successfully sent to {recipient_id}")
                                else:
                                    logger.error(f"❌ Failed to send followup template to {recipient_id}")
                            else:
                                # Not a follow-up - handle as regular notification
                                logger.info(f"📋 Checking for recent notifications for {recipient_id}")
                               
                                # Try to find the original notification type for this recipient
                                # Look for notifications in the last 24 hours
                                twenty_four_hours_ago = (datetime.now(pytz.timezone("Asia/Kuala_Lumpur")) - timedelta(hours=24)).isoformat()
                               
                                response = supabase.table("c_notifications").select(
                                    "reminder_type"
                                ).eq("whatsapp_number", whatsapp_number_norm).gte("time", twenty_four_hours_ago).order("time", desc=True).limit(1).execute()
                               
                                if response.data and response.data[0].get("reminder_type"):
                                    reminder_type = response.data[0]["reminder_type"]
                                    logger.info(f"📋 Found recent notification type: {reminder_type} for {recipient_id}")
                                   
                                    # Get user's language
                                    language = get_user_language(supabase, recipient_id)
                                   
                                    # Send appropriate template
                                    if reminder_type in ["general", "day", "week", "hour", "custom", "report"]:
                                        template_name = f"{reminder_type}_{language}"
                                    else:
                                        template_name = f"general_{language}"
                                   
                                    logger.info(f"🚨 Sending template {template_name} to {recipient_id}")
                                   
                                    from utils import send_template_message
                                    success = send_template_message(recipient_id, template_name, supabase)
                                   
                                    if success:
                                        logger.info(f"✅ Template {template_name} successfully sent to {recipient_id}")
                                    else:
                                        logger.error(f"❌ Failed to send template {template_name} to {recipient_id}")
                                else:
                                    logger.info(f"ℹ️ No recent notifications found for {recipient_id}, using general template")
                                   
                                    # Fallback to general template
                                    from utils import handle_reengagement_error
                                    handle_reengagement_error(recipient_id, supabase)
                                   
                        except Exception as e:
                            logger.error(f"Error handling 24-hour rule for {recipient_id}: {e}", exc_info=True)
                            # Fallback: send general template
                            try:
                                from utils import handle_reengagement_error
                                handle_reengagement_error(recipient_id, supabase)
                            except Exception as fallback_e:
                                logger.error(f"Even fallback failed for {recipient_id}: {fallback_e}")
                   
                    # 131049 = ecosystem engagement issue
                    elif error_code == 131049:
                        logger.warning(f"❌ Message failed for {recipient_id} with code 131049: {error.get('message')}")
                        # Don't retry this error - it's a WhatsApp policy violation
                       
    except Exception as e:
        logger.error(f"Error in handle_status_update: {e}", exc_info=True)


def send_language_selection_menu(whatsapp_number: str, supabase: Client) -> bool:
    """Send a language selection menu to the user."""
    logger.info(f"Sending language selection menu to {whatsapp_number}")
    content = {
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": translate_template(whatsapp_number, "AnyHealth Bot", supabase)},
            "body": {"text": translate_template(whatsapp_number, "Please select your preferred language:", supabase)},
            "footer": {"text": translate_template(whatsapp_number, "Choose a language to proceed", supabase)},
            "action": {
                "button": translate_template(whatsapp_number, "Select Language", supabase),
                "sections": [
                    {
                        "title": translate_template(whatsapp_number, "Languages", supabase),
                        "rows": [
                            {"id": "lang_en", "title": translate_template(whatsapp_number, "English", supabase)},
                            {"id": "lang_bm", "title": translate_template(whatsapp_number, "Bahasa Malaysia", supabase)},
                            {"id": "lang_cn", "title": translate_template(whatsapp_number, "中文", supabase)},
                            {"id": "lang_tm", "title": translate_template(whatsapp_number, "தமிழ்", supabase)},
                            {"id": "back_button", "title": translate_template(whatsapp_number, "🔙 Back to Main Menu", supabase)}
                        ]
                    }
                ]
            }
        }
    }
    success = send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
    logger.info(f"Language selection menu sent to {whatsapp_number}: Success={success}")
    return success


def send_main_menu_confirmation(whatsapp_number, supabase, user_data):
    """Send button-based confirmation for main menu."""
    try:
        # Store current state in temp_data for possible restoration
        module = user_data.get("module")
        state = user_data.get("state")
       
        logger.info(f"Sending main menu confirmation to {whatsapp_number}, module: {module}, state: {state}")
       
        # Store current state in temp_data
        try:
            supabase.table("whatsapp_users").update({
                "temp_data": {
                    "previous_state": state,
                    "previous_module": module,
                    "restore_timestamp": time.time()
                }
            }).eq("whatsapp_number", whatsapp_number.lstrip("+")).execute()
        except Exception as e:
            logger.error(f"Error storing temp_data: {e}")
       
        # Send button-based confirmation
        payload = {
            "messaging_product": "whatsapp",
            "to": whatsapp_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": translate_template(
                        whatsapp_number,
                        "⚠️ *Main Menu Confirmation*\n\n"
                        "Are you sure you want to go back to the main menu?\n"
                        "This will cancel your current action.",
                        supabase
                    )
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "confirm_main_menu",
                                "title": translate_template(whatsapp_number, "✅ Yes", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "cancel_main_menu",
                                "title": translate_template(whatsapp_number, "❌ No", supabase)
                            }
                        }
                    ]
                }
            }
        }
       
        send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
        return True
       
    except Exception as e:
        logger.error(f"Error sending main menu confirmation: {e}")
        return False


def restore_previous_state(whatsapp_number, user_id, supabase, user_data):
    """Restore user's previous state after declining main menu."""
    try:
        # Get stored temp_data
        user_db_data = supabase.table("whatsapp_users").select("temp_data").eq(
            "whatsapp_number", whatsapp_number.lstrip("+")
        ).limit(1).execute()
       
        if user_db_data.data and user_db_data.data[0]:
            temp_data = user_db_data.data[0].get("temp_data", {})
            if temp_data and "previous_state" in temp_data and "previous_module" in temp_data:
                previous_state = temp_data["previous_state"]
                previous_module = temp_data["previous_module"]
               
                # Check if temp_data is too old (more than 5 minutes)
                restore_timestamp = temp_data.get("restore_timestamp", 0)
                if time.time() - restore_timestamp > 300:  # 5 minutes
                    logger.info(f"Temp data too old for {whatsapp_number}, going to main menu")
                    user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "Session expired. Returning to main menu.", supabase)}}
                    )
                    send_interactive_menu(whatsapp_number, supabase)
                    return False
               
                # Restore previous state
                user_data[whatsapp_number]["state"] = previous_state
                user_data[whatsapp_number]["module"] = previous_module
               
                # Clear temp_data
                supabase.table("whatsapp_users").update({
                    "temp_data": {}
                }).eq("whatsapp_number", whatsapp_number.lstrip("+")).execute()
               
                logger.info(f"Restored state: {previous_state}, module: {previous_module}")
               
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Continuing with your previous action.", supabase)}}
                )
                return True
       
        # If restoration fails
        logger.info(f"Could not restore previous state for {whatsapp_number}")
        user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Could not restore previous action. Returning to main menu.", supabase)}}
        )
        send_interactive_menu(whatsapp_number, supabase)
        return False
       
    except Exception as e:
        logger.error(f"Error restoring previous state: {e}")
        return False


def handle_message(value):
    """Handle incoming webhook messages."""
    logger.info(f"Received webhook message: {value}")
    messages = value.get("messages", [])
    contacts = value.get("contacts", [])

    if not messages:
        logger.info("No messages received")
        return

    whatsapp_number = messages[0]["from"]
    user_name = contacts[0]["profile"]["name"] if contacts else "Unknown"
    logger.info(f"Processing message from whatsapp_number: {whatsapp_number}, user_name: {user_name}")

    # Fetch or create user_id
    user_id = get_user_id(supabase, whatsapp_number)
    if not user_id:
        logger.warning(f"No user_id found for {whatsapp_number}. Generating temporary UUID.")
        user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, whatsapp_number))
        try:
            supabase.table("whatsapp_users").upsert(
                {
                    "id": user_id,
                    "whatsapp_number": whatsapp_number,
                    "user_name": user_name,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "language": "en"
                }
            ).execute()
            logger.info(f"Stored/updated user: {whatsapp_number}, {user_name}")
            user_data[whatsapp_number] = {"state": "SELECT_LANGUAGE", "processing": False, "module": None}
            send_language_selection_menu(whatsapp_number, supabase)
            return
        except Exception as e:
            logger.error(f"Error storing user {whatsapp_number}: {e}", exc_info=True)
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Error registering user. Please try again.", supabase)}}
            )
            return

    if whatsapp_number not in user_data:
        user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}

    if user_data[whatsapp_number].get("processing"):
        logger.info(f"Skipping message for {whatsapp_number} due to ongoing processing")
        return

    logger.info(f"Current state for {whatsapp_number}: {user_data[whatsapp_number]}")
    message = messages[0]
    user_data[whatsapp_number]["processing"] = True

    try:
        module = user_data[whatsapp_number].get("module")
        state = user_data[whatsapp_number].get("state")
        booking_submitted = False
        pending_id = None

        # ===== HANDLE MAIN MENU TRIGGER DETECTION (AT THE VERY BEGINNING) =====
        if message["type"] == "text":
            user_text = message["text"]["body"].strip()
            user_text_lower = user_text.lower()
           
            # Check for main menu keywords
            main_menu_keywords = ["main menu", "main", "menu", "home", "start over", "reset", "back", "cancel"]
            is_main_menu_trigger = any(keyword in user_text_lower for keyword in main_menu_keywords)
           
            # Also check exact matches for common triggers
            exact_triggers = ["hi", "hello", "menu", "back", "cancel", "start"]
            is_exact_trigger = user_text_lower in exact_triggers
           
            if is_main_menu_trigger or is_exact_trigger:
                logger.info(f"User {whatsapp_number} typed '{user_text}' - checking if we need confirmation")
               
                # If user is idle or has no active module, just show main menu
                if not module or module == "main_menu" or state == "IDLE":
                    logger.info(f"User {whatsapp_number} is idle - sending main menu directly")
                    send_interactive_menu(whatsapp_number, supabase)
                    user_data[whatsapp_number]["state"] = "IDLE"
                    user_data[whatsapp_number]["processing"] = False
                    return
                else:
                    # User is in an active module - ask for confirmation via buttons
                    logger.info(f"User {whatsapp_number} triggered main menu while in module {module}, state {state}")
                   
                    # Send button-based confirmation
                    send_main_menu_confirmation(whatsapp_number, supabase, user_data[whatsapp_number])
                    user_data[whatsapp_number]["processing"] = False
                    return

        # ===== HANDLE MAIN MENU CONFIRMATION BUTTONS =====
        if message["type"] == "interactive" and message["interactive"].get("type") == "button_reply":
            button_id = message["interactive"]["button_reply"]["id"]
           
            if button_id == "confirm_main_menu":
                # User confirms - go to main menu
                logger.info(f"User {whatsapp_number} confirmed main menu via button")
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Returning to main menu.", supabase)}}
                )
                send_interactive_menu(whatsapp_number, supabase)
                user_data[whatsapp_number]["processing"] = False
                return
               
            elif button_id == "cancel_main_menu":
                # User cancels - restore previous state
                logger.info(f"User {whatsapp_number} cancelled main menu via button")
                restore_previous_state(whatsapp_number, user_id, supabase, user_data)
                user_data[whatsapp_number]["processing"] = False
                return

        # ===== HANDLE NOTIFICATION NOTED BUTTON =====
        if message["type"] == "interactive" and message["interactive"].get("type") == "button_reply":
            button_id = message["interactive"]["button_reply"]["id"]
            if button_id == "notification_noted":
                # Handle notification noted
                handle_notification_noted(whatsapp_number, supabase)
                user_data[whatsapp_number]["processing"] = False
                return

        # ===== HANDLE FOLLOW-UP RESPONSES (BUTTON CLICKS) =====
        if message["type"] == "interactive" and message["interactive"].get("type") == "button_reply":
            button_id = message["interactive"]["button_reply"]["id"]
            if button_id.startswith("followup_"):
                handle_followup_response(whatsapp_number, user_id, supabase, user_data, message)
                user_data[whatsapp_number]["processing"] = False
                return

        # ===== NEW: HANDLE FOLLOW-UP TEMPLATE RESPONSES (TEXT) =====
        if message["type"] == "text":
            message_text = message["text"]["body"].strip()
            # Try to detect if this is a follow-up template response
            if detect_and_save_template_response(whatsapp_number, message_text, supabase):
                logger.info(f"Follow-up template response detected for {whatsapp_number}: {message_text}")
                user_data[whatsapp_number]["processing"] = False
                return

        # ===== HANDLE SYMPTOM TRACKER RESPONSES =====
        if module == "symptom_tracker":
            handle_symptom_tracker_response(whatsapp_number, user_id, supabase, user_data, message)
            user_data[whatsapp_number]["processing"] = False
            return

        # ===== HANDLE LOCATION MESSAGES - UPDATED TO FIX TCM SERVICE =====
        if message["type"] == "location":
            logger.info(f"Received location message from {whatsapp_number}")
            
            # Check which module is active and route accordingly
            if module == "tcm_service":
                # Directly route to TCM service handler for location
                result = handle_tcm_service(whatsapp_number, user_id, supabase, user_data, message)
                if result is True:
                    user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                user_data[whatsapp_number]["processing"] = False
                return
            elif module == "ambulance_booking" and state == "BOOKING_PICKUP_ADDRESS_LOCATION":
                # Pass to menu handler which will route to ambulance_booking
                result = handle_menu_selection(whatsapp_number, user_id, supabase, user_data, message)
                if result is True:
                    user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                user_data[whatsapp_number]["processing"] = False
                return
            elif module in ["ambulance_booking", "ambulance_homehome"]:
                # Pass to appropriate handler via menu
                result = handle_menu_selection(whatsapp_number, user_id, supabase, user_data, message)
                if result is True:
                    user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                user_data[whatsapp_number]["processing"] = False
                return
            
            # If location is not expected in this context, send a message
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Please use the menu buttons provided for selection.", supabase)}}
            )
            user_data[whatsapp_number]["processing"] = False
            return

        # ===== HANDLE INDIVIDUAL MODULE RESPONSES =====
        if module in ["individual", "individual_med_rout"]:
            logger.info(f"Message for individual module or med routine module")
            result = handle_individual_response(whatsapp_number, user_id, supabase, user_data, message)
            if result is True:
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
            user_data[whatsapp_number]["processing"] = False
            return

        # ===== HANDLE CLINIC BOOKING CONFIRMATION BUTTONS =====
        if message["type"] == "interactive" and message["interactive"].get("type") == "button_reply":
            button_id = message["interactive"]["button_reply"]["id"]
           
            # Handle booking confirmation for clinics
            if button_id.startswith("book_at_"):
                clinic_id = button_id.replace("book_at_", "")
                destination_mod = user_data[whatsapp_number].get("pending_booking_destination", "tcm_service")
               
                logger.info(f"User {whatsapp_number} wants to book at clinic {clinic_id}, destination: {destination_mod}")
               
                # Clear pending booking data
                if "pending_booking_clinic" in user_data[whatsapp_number]:
                    del user_data[whatsapp_number]["pending_booking_clinic"]
                if "pending_booking_destination" in user_data[whatsapp_number]:
                    del user_data[whatsapp_number]["pending_booking_destination"]
               
                # Set up user data for TCM service flow
                user_data[whatsapp_number].update({
                    "module": destination_mod,
                    "clinic_id": clinic_id,
                    "clinic_info_displayed": False,  # Reset this flag
                    "processing": False
                })
               
                try:
                    if destination_mod == "tcm_service":
                        # Set state to trigger TCM flow
                        user_data[whatsapp_number]["state"] = "TCM_CLINIC_INFO_DISPLAY"
                        # Call tcm_service with a special trigger
                        handle_tcm_service(whatsapp_number, user_id, supabase, user_data, {"type": "routing_trigger"})
                    else:
                        user_data[whatsapp_number]["state"] = "IDLE"
                        handle_checkup(whatsapp_number, user_id, supabase, user_data, {"type": "routing_trigger"})
                except Exception as e:
                    logger.error(f"Error handling booking for clinic {clinic_id}: {e}", exc_info=True)
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "An error occurred while setting up your booking. Please try again.", supabase)}}
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                return
               
            elif button_id == "no_booking":
                logger.info(f"User {whatsapp_number} chose not to book")
                # Clear pending booking data
                if "pending_booking_clinic" in user_data[whatsapp_number]:
                    del user_data[whatsapp_number]["pending_booking_clinic"]
                if "pending_booking_destination" in user_data[whatsapp_number]:
                    del user_data[whatsapp_number]["pending_booking_destination"]
               
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Returning to main menu.", supabase)}}
                )
                send_interactive_menu(whatsapp_number, supabase)
                user_data[whatsapp_number]["processing"] = False
                return

        # ===== HANDLE AMBULANCE MODULE RESPONSES =====
        if module in ["ambulance_booking", "ambulance_homehome"]:
            logger.info(f"Message for ambulance module {module}")

            if module == "ambulance_booking":
                result = handle_booking_response(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "ambulance_homehome":
                result = handle_homehome_response(whatsapp_number, user_id, supabase, user_data, message)

            if result is True:
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
            user_data[whatsapp_number]["processing"] = False
            return

        # ===== HANDLE TCM SERVICE RESPONSES (EXCEPT LOCATION - ALREADY HANDLED ABOVE) =====
        if module == "tcm_service":
            logger.info(f"Message for TCM service module")
            result = handle_tcm_service(whatsapp_number, user_id, supabase, user_data, message)
            if result is True:
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
            user_data[whatsapp_number]["processing"] = False
            return

        # Handle back button in language selection
        if state == "SELECT_LANGUAGE" and message["type"] == "interactive" and message["interactive"].get("type") == "list_reply":
            lang_id = message["interactive"]["list_reply"]["id"]
           
            # Handle back button
            if lang_id == "back_button":
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Returning to main menu.", supabase)}}
                )
                send_interactive_menu(whatsapp_number, supabase)
                return
           
            lang_map = {
                "lang_en": "en",
                "lang_bm": "bm",
                "lang_cn": "cn",
                "lang_tm": "tm"
            }
            selected_language = lang_map.get(lang_id, "en")
            try:
                supabase.table("whatsapp_users").update(
                    {"language": selected_language}
                ).eq("id", user_id).execute()
                logger.info(f"Updated language for {whatsapp_number} to {selected_language}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": gt_tt(whatsapp_number, "Language set to {}.", supabase).format(selected_language)}}
                )
                # Check if there was a clinic routing waiting for a language choice
                pending = user_data[whatsapp_number].get("pending_module")
                if pending:
                    user_data[whatsapp_number].update({"state": "IDLE", "module": pending})
                    user_data[whatsapp_number].pop("pending_module", None) # Clear the flag
                   
                    if pending == "tcm_service":
                        handle_tcm_service(whatsapp_number, user_id, supabase, user_data, {"type": "routing_trigger"})
                    else:
                        handle_checkup(whatsapp_number, user_id, supabase, user_data, {"type": "routing_trigger"})
                    return

                # Otherwise, just go to main menu
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return
           
            except Exception as e:
                logger.error(f"Error updating language for {whatsapp_number}: {e}", exc_info=True)
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Error setting language. Please try again.", supabase)}}
                )
                user_data[whatsapp_number] = {"state": "SELECT_LANGUAGE", "processing": False, "module": None}
                send_language_selection_menu(whatsapp_number, supabase)
                return

        # ===== CRITICAL FIX: HANDLE VIEW_BOOKING FUTURE DATE TEXT INPUT =====
        if module == "view_booking" and state == "AWAITING_FUTURE_DATE" and message["type"] == "text":
            logger.info(f"Processing future date input for view_booking module: {whatsapp_number}")
            # Route directly to handle_view_booking
            result = handle_view_booking(whatsapp_number, user_id, supabase, user_data, message)
            if result is True:
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
            user_data[whatsapp_number]["processing"] = False
            return

        # ===== HANDLE TEXT MESSAGES WITH MAIN MENU KEYWORDS (SECOND CHECK) =====
        if message["type"] == "text":
            user_text = message["text"]["body"].strip()
            user_text_lower = user_text.lower()
           
            # Check again for main menu keywords in any position in the text
            main_menu_keywords = ["main menu", "menu", "home", "start over", "reset", "back to main"]
            is_main_menu_request = any(keyword in user_text_lower for keyword in main_menu_keywords)
           
            # Check exact matches for common triggers
            exact_triggers = ["hi", "hello", "menu", "back", "cancel", "start"]
            is_exact_trigger = user_text_lower in exact_triggers
           
            if is_main_menu_request or is_exact_trigger:
                logger.info(f"User {whatsapp_number} typed main menu keyword: '{user_text}'")
               
                # If user is idle or has no active module, just show main menu
                if not module or module == "main_menu" or state == "IDLE":
                    logger.info(f"User {whatsapp_number} is idle - sending main menu directly")
                    send_interactive_menu(whatsapp_number, supabase)
                    user_data[whatsapp_number]["state"] = "IDLE"
                    user_data[whatsapp_number]["processing"] = False
                    return
                else:
                    # User is in an active module - ask for confirmation via buttons
                    logger.info(f"User {whatsapp_number} requested main menu while in module {module}")
                   
                    # Send button-based confirmation
                    send_main_menu_confirmation(whatsapp_number, supabase, user_data[whatsapp_number])
                    user_data[whatsapp_number]["processing"] = False
                    return

            # ===== NEW ROUTING INTERCEPTOR =====
            if user_text_lower.startswith("find_"):
                from utils import lookup_clinic_by_keyword
                clinic_info = lookup_clinic_by_keyword(supabase, user_text_lower)
               
                if clinic_info:
                    # Get the clinic ID from the URL lookup
                    clinic_id = clinic_info['provider_id']
                   
                    # Fetch clinic details from tcm_a_clinics table
                    try:
                        clinic_details = supabase.table("tcm_a_clinics").select(
                            "name, address, image_url, phone_number"
                        ).eq("id", clinic_id).execute()
                       
                        if clinic_details.data and len(clinic_details.data) > 0:
                            clinic_data = clinic_details.data[0]
                           
                            # Send clinic image if available
                            if clinic_data.get('image_url'):
                                image_payload = {
                                    "messaging_product": "whatsapp",
                                    "to": whatsapp_number,
                                    "type": "image",
                                    "image": {
                                        "link": clinic_data['image_url']
                                    }
                                }
                                send_whatsapp_message(whatsapp_number, "image", image_payload, supabase)
                           
                            # Send clinic details message
                            address_label = translate_template(whatsapp_number, "Address:", supabase)
                            phone_label = translate_template(whatsapp_number, "Phone:", supabase)
                           
                            clinic_message = gt_tt(whatsapp_number, f"""
🏥 *{clinic_data.get('name', 'Clinic')}*

📍 *{address_label}*
{clinic_data.get('address', 'Not available')}

📞 *{phone_label}* {clinic_data.get('phone_number', 'Not available')}
                            """.strip(), supabase)
                           
                            text_payload = {
                                "messaging_product": "whatsapp",
                                "to": whatsapp_number,
                                "type": "text",
                                "text": {
                                    "body": clinic_message
                                }
                            }
                            send_whatsapp_message(whatsapp_number, "text", text_payload, supabase)
                           
                            # Store clinic ID for potential booking
                            user_data[whatsapp_number]["clinic_id"] = clinic_id
                           
                            # Check if we should route to booking module
                            cat = clinic_info['provider_cat'].upper()
                            destination_mod = "tcm_service" if "TCM" in cat else "checkup_booking"
                           
                            # Ask if user wants to book an appointment
                            booking_prompt = translate_template(whatsapp_number, "Would you like to book an appointment at this clinic?", supabase)
                            booking_payload = {
                                "messaging_product": "whatsapp",
                                "to": whatsapp_number,
                                "type": "interactive",
                                "interactive": {
                                    "type": "button",
                                    "body": {
                                        "text": booking_prompt
                                    },
                                    "action": {
                                        "buttons": [
                                            {
                                                "type": "reply",
                                                "reply": {
                                                    "id": f"book_at_{clinic_id}",
                                                    "title": translate_template(whatsapp_number, "✅ Yes, Book", supabase)
                                                }
                                            },
                                            {
                                                "type": "reply",
                                                "reply": {
                                                    "id": "no_booking",
                                                    "title": translate_template(whatsapp_number, "❌ No, Just Browsing", supabase)
                                                }
                                            }
                                        ]
                                    }
                                }
                            }
                            send_whatsapp_message(whatsapp_number, "interactive", booking_payload, supabase)
                           
                            # Store booking intent in user data
                            user_data[whatsapp_number]["pending_booking_clinic"] = clinic_id
                            user_data[whatsapp_number]["pending_booking_destination"] = destination_mod
                           
                        else:
                            # Clinic not found in tcm_a_clinics
                            send_whatsapp_message(
                                whatsapp_number,
                                "text",
                                {"text": {"body": gt_tt(whatsapp_number, "Clinic information not found. Please try again.", supabase)}}
                            )
                           
                    except Exception as e:
                        logger.error(f"Error fetching clinic details: {e}")
                        send_whatsapp_message(
                            whatsapp_number,
                            "text",
                            {"text": {"body": gt_tt(whatsapp_number, "Error retrieving clinic information. Please try again.", supabase)}}
                        )
                else:
                    # No clinic found for the keyword
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": gt_tt(whatsapp_number, "No clinic found with that keyword. Please try a different search.", supabase)}}
                    )
               
                user_data[whatsapp_number]["processing"] = False
                return
            # ===== END ROUTING INTERCEPTOR =====
           
            # Handle "verified:" messages
            if user_text.startswith("verified:"):
                verified_success = handle_verification_response(whatsapp_number, user_id, supabase, user_data, user_text=message["text"]["body"].strip())
                if not verified_success:
                    user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                return
               
            elif state == "CONCIERGE" and module == "concierge":
                handle_concierge_input(whatsapp_number, user_id, supabase, user_data, message)
                return
               
            else:
                result = None
                expecting_interactive = False
               
                # Define states that expect button input only
                BUTTON_ONLY_STATES = [
                    "CHECKUP_TYPE", "VACCINE_TYPE", "CHECKUP_REMARK_YES_NO", "VACCINE_REMARK_YES_NO",
                    "SELECT_DOCTOR", "SELECT_DATE", "SELECT_HOUR", "SELECT_TIME_SLOT",
                    "VIEW_BOOKING_SUBMENU", "CHANGE_LANGUAGE", "CONCIERGE",
                    "CLINIC_ENQUIRIES_CHOICE", "AI_SERVICE_FOLLOWUP",
                    "SELECT_REPORT", "REPORT_REMARK_YES_NO", "REPORT_REMARK_INPUT",
                    "HEALTHSP_TYPE", "HEALTHSP_REMARK_YES_NO",
                    "AWAITING_FOLLOWUP_REMARKS_INTENT",
                    "AWAITING_SYMPTOM_ENTRY_SELECTION", "AWAITING_SYMPTOM_STATUS", "AWAITING_SYMPTOM_REMARKS_INTENT",
                    "BOOKING_MOBILITY", "BOOKING_ATTACHMENTS", "BOOKING_REMARKS", "BOOKING_RETURN_SERVICE",
                    "BOOKING_SCHEDULE_DATE", "BOOKING_SCHEDULE_AMPM", "BOOKING_SCHEDULE_TIMESLOT", "BOOKING_SCHEDULE_INTERVAL",
                    "VIEW_BOOKING_SUBMENU", "SELECT_BOOKING_FOR_RESCHEDULE",
                    "TCM_TYPE_SELECTION", "TCM_CLINIC_SELECTION", "TCM_CATEGORY_SELECTION", 
                    "TCM_SERVICE_SELECTION", "TCM_REMARK_YES_NO", "SELECT_DOCTOR", 
                    "SELECT_DATE", "SELECT_PERIOD", "SELECT_HOUR", "SELECT_TIME_SLOT", 
                    "CONFIRM_BOOKING", "CONFIRM_FUTURE_DATE",
                    "INDIVIDUAL_TYPE_SELECTION", "INDIVIDUAL_REMARK_YES_NO"
                ]
               
                # Define states that expect TEXT input
                TEXT_INPUT_STATES = [
                    # Health screening text input states
                    "HEALTHSP_SPECIFY", "HEALTHSP_REMARK_INPUT",
                    # Other text input states
                    "SYMPTOMS_INPUT", "CONCIERGE_INPUT", "AI_SERVICE_FINDER_INPUT",
                    # Follow-up remarks state
                    "AWAITING_FOLLOWUP_DETAILED_REMARKS",
                    # Symptom tracker text input
                    "AWAITING_SYMPTOM_DETAILS",
                    # Ambulance booking text input states
                    "BOOKING_PATIENT_NAME", "BOOKING_PATIENT_IC", "BOOKING_PATIENT_PHONE",
                    "BOOKING_EMERGENCY_NAME", "BOOKING_EMERGENCY_PHONE", "BOOKING_PICKUP_ADDRESS_TEXT",
                    "BOOKING_HOSPITAL_NAME", "BOOKING_HOSPITAL_ADDRESS_MANUAL", "BOOKING_REMARKS_TEXT",
                    "BOOKING_SCHEDULE_DATE_OTHER",
                    # TCM service text input states
                    "TCM_REMARK_INPUT",
                    # Individual service text input states
                    "INDIVIDUAL_REMARK_INPUT",
                    "AWAITING_FUTURE_DATE", "AWAITING_TIME_INPUT",
                ]
               
                # ===== HANDLE OTHER MODULES =====
                if module:
                    # If in a button-only state and user sends text, check for main menu keywords
                    if state in BUTTON_ONLY_STATES:
                        # Check if text contains main menu keywords
                        main_menu_keywords = ["main menu", "menu", "home", "start over", "reset", "back to main"]
                        has_main_menu_keyword = any(keyword in user_text_lower for keyword in main_menu_keywords)
                       
                        if has_main_menu_keyword:
                            logger.info(f"User {whatsapp_number} sent main menu keyword in button-only state: {state}")
                            send_main_menu_confirmation(whatsapp_number, supabase, user_data[whatsapp_number])
                            user_data[whatsapp_number]["processing"] = False
                            return
                        else:
                            logger.info(f"User {whatsapp_number} sent text in button-only state: {state}")
                            send_whatsapp_message(
                                whatsapp_number,
                                "text",
                                {"text": {"body": translate_template(whatsapp_number, "Please use the menu buttons provided for selection.", supabase)}}
                            )
                            user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                            send_interactive_menu(whatsapp_number, supabase)
                            return
                   
                    # If in a text-input state, process the text
                    if state in TEXT_INPUT_STATES:
                        logger.info(f"User {whatsapp_number} sent text in text-input state: {state}")
                        if module == "health_screening":
                            result = handle_healthsp(whatsapp_number, user_id, supabase, user_data, message)
                        elif module == "report_symptoms":
                            result = handle_symptoms(whatsapp_number, user_id, supabase, user_data, message)
                        elif module == "checkup_booking":
                            result = handle_checkup(whatsapp_number, user_id, supabase, user_data, message)
                        elif module == "vaccination_booking":
                            result = handle_vaccination(whatsapp_number, user_id, supabase, user_data, message)
                        elif module == "checkup_result_booking":
                            result = handle_report_booking(whatsapp_number, user_id, supabase, user_data, message)
                        elif module == "clinic_enquiries":
                            if state == "AI_SERVICE_FINDER_INPUT":
                                handle_ai_service_input(whatsapp_number, user_text, supabase, user_data)
                            else:
                                send_whatsapp_message(
                                    whatsapp_number,
                                    "text",
                                    {"text": {"body": translate_template(whatsapp_number, "Invalid input. Returning to main menu.", supabase)}}
                                )
                                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                                send_interactive_menu(whatsapp_number, supabase)
                        elif module == "symptom_tracker" and state == "AWAITING_SYMPTOM_ENTRY_SELECTION":
                            # This will be handled by the symptom tracker handler above
                            pass
                        elif module == "tcm_service":
                            result = handle_tcm_service(whatsapp_number, user_id, supabase, user_data, message)
                        elif module == "ambulance_booking":
                            result = handle_booking_response(whatsapp_number, user_id, supabase, user_data, message)
                        elif module == "ambulance_homehome":
                            result = handle_homehome_response(whatsapp_number, user_id, supabase, user_data, message)
                        elif module in ["individual", "individual_med_rout"]:
                            result = handle_individual_response(whatsapp_number, user_id, supabase, user_data, message)
                        else:
                            # Default handling for other modules
                            if module == "report_symptoms":
                                result = handle_symptoms(whatsapp_number, user_id, supabase, user_data, message)
                            elif module == "checkup_booking":
                                result = handle_checkup(whatsapp_number, user_id, supabase, user_data, message)
                            elif module == "vaccination_booking":
                                result = handle_vaccination(whatsapp_number, user_id, supabase, user_data, message)
                            elif module == "checkup_result_booking":
                                result = handle_report_booking(whatsapp_number, user_id, supabase, user_data, message)
                            elif module == "health_screening":
                                result = handle_healthsp(whatsapp_number, user_id, supabase, user_data, message)
                            elif module == "symptom_tracker":
                                result = handle_symptom_tracker_response(whatsapp_number, user_id, supabase, user_data, message)
                   
                    # Handle interactive-only states
                    elif state in ["SELECT_DOCTOR", "SELECT_DATE", "SELECT_HOUR", "SELECT_TIME_SLOT", "TCM_TYPE_SELECTION", "INDIVIDUAL_TYPE_SELECTION"]:
                        expecting_interactive = True
                   
                    # Default module handling for other states
                    else:
                        if module == "report_symptoms":
                            result = handle_symptoms(whatsapp_number, user_id, supabase, user_data, message)
                        elif module == "checkup_booking":
                            result = handle_checkup(whatsapp_number, user_id, supabase, user_data, message)
                        elif module == "vaccination_booking":
                            result = handle_vaccination(whatsapp_number, user_id, supabase, user_data, message)
                        elif module == "checkup_result_booking":
                            result = handle_report_booking(whatsapp_number, user_id, supabase, user_data, message)
                        elif module == "health_screening":
                            result = handle_healthsp(whatsapp_number, user_id, supabase, user_data, message)
                        elif module == "symptom_tracker":
                            result = handle_symptom_tracker_response(whatsapp_number, user_id, supabase, user_data, message)
                        elif module == "view_booking":
                            result = handle_view_booking(whatsapp_number, user_id, supabase, user_data, message)
                        elif module == "change_language":
                            expecting_interactive = True
                        elif module == "clinic_enquiries":
                            send_whatsapp_message(
                                whatsapp_number,
                                "text",
                                {"text": {"body": translate_template(whatsapp_number, "Invalid input. Returning to main menu.", supabase)}}
                            )
                            user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                            send_interactive_menu(whatsapp_number, supabase)
                        elif module == "tcm_service":
                            result = handle_tcm_service(whatsapp_number, user_id, supabase, user_data, message)
                        elif module == "ambulance_booking":
                            result = handle_booking_response(whatsapp_number, user_id, supabase, user_data, message)
                        elif module == "ambulance_homehome":
                            result = handle_homehome_response(whatsapp_number, user_id, supabase, user_data, message)
                        elif module in ["individual", "individual_med_rout"]:
                            result = handle_individual_response(whatsapp_number, user_id, supabase, user_data, message)
                        else:
                            send_whatsapp_message(
                                whatsapp_number,
                                "text",
                                {"text": {"body": translate_template(whatsapp_number, "Invalid input. Returning to main menu.", supabase)}}
                            )
                            user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                            send_interactive_menu(whatsapp_number, supabase)
                else:
                    # No active module, show main menu
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "Please select an option from the menu.", supabase)}}
                    )
                    send_interactive_menu(whatsapp_number, supabase)

                if expecting_interactive:
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "Please use the menu buttons provided for selection.", supabase)}}
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return

                # Process result if available
                if result is not None:
                    booking_submitted = bool(result)
                    if isinstance(result, tuple) and len(result) == 2:
                        booking_submitted, pending_id = result
                return

        elif message["type"] == "interactive":
            # Handle menu selections
            result = handle_menu_selection(whatsapp_number, user_id, supabase, user_data, message)
            booking_submitted = bool(result) if result is not None else False
            if isinstance(result, tuple) and len(result) == 2:
                booking_submitted, pending_id = result

        else:
            # Handle other message types (image, video, document, audio) via menu
            result = handle_menu_selection(whatsapp_number, user_id, supabase, user_data, message)
            booking_submitted = bool(result) if result is not None else False
            if isinstance(result, tuple) and len(result) == 2:
                booking_submitted, pending_id = result

        if booking_submitted and pending_id:
            try:
                logger.info(f"Booking submitted for {whatsapp_number}, pending_id: {pending_id}. Awaiting scheduler for notification.")
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                send_interactive_menu(whatsapp_number, supabase)
            except Exception as e:
                logger.error(f"Error post-booking for {whatsapp_number}: {e}", exc_info=True)
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "An error occurred. Please try again.", supabase)}}
                )
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                send_interactive_menu(whatsapp_number, supabase)

    except Exception as e:
        logger.error(f"Error processing message for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "An error occurred. Please try again.", supabase)}}
        )
        user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
        send_interactive_menu(whatsapp_number, supabase)

    finally:
        user_data[whatsapp_number]["processing"] = False


# ===== SCHEDULER FUNCTIONS =====
def safe_process_notifications():
    """Process notifications with proper locking and rate limiting."""
    with scheduler_lock:
        logger.info("=== Running notification processing ===")
        try:
            process_notifications(supabase)
            check_and_send_reminder_notifications(supabase)
            check_and_send_booking_confirmations(supabase)
        except Exception as e:
            logger.error(f"Error in safe_process_notifications: {e}", exc_info=True)


def safe_check_followups():
    """Prevent concurrent execution of follow-up checks."""
    with scheduler_lock:
        logger.info("=== Running follow-up check ===")
        check_and_send_followup_messages(supabase)


def run_scheduler():
    """Run scheduled tasks for notifications and follow-ups."""
    logger.info("Starting scheduler...")
   
    schedule.every(5).minutes.do(safe_process_notifications)
    schedule.every(1).minutes.do(safe_check_followups)

    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error in scheduler: {e}", exc_info=True)
            time.sleep(1)


# Start the scheduler in a separate thread
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()
logger.info("Scheduler thread started")


def test_immediate_followup():
    """
    TEST FUNCTION: Send follow-up messages to ALL follow-ups immediately.
    Call this function to test the follow-up system.
    """
    logger.info("=== STARTING IMMEDIATE FOLLOW-UP TEST ===")
    count = test_immediate_followup_all(supabase)
    logger.info(f"=== IMMEDIATE FOLLOW-UP TEST COMPLETE: Sent {count} messages ===")
    return count


if __name__ == "__main__":
    logger.info("WhatsApp Bot Server Started")
   
    # Test booking confirmations immediately
    send_immediate_booking_confirmations()
   
    # Uncomment the line below to send immediate follow-up messages when the server starts
    # test_immediate_followup()
   
    while True:
        time.sleep(1)