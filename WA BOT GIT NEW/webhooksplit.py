from flask import Flask, request
import logging
import threading
import main
#import dr_main
import queue_main
# import auto_main
from datetime import datetime, timedelta
import pytz
# Add these imports at the top:
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Remove the hardcoded Supabase credentials if they exist in this file
app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Update the VERIFY_TOKEN line:
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "mysecretverifytoken123")

# Map phone_number_id to handler
ACCOUNT_MAP = {
    "784286534770982": main.handle_message,  # Patient/user account
}

# Start schedulers in threads
threading.Thread(target=main.run_scheduler, daemon=True).start()
#threading.Thread(target=dr_main.run_scheduler, daemon=True).start()
# threading.Thread(target=queue_main.run_scheduler, daemon=True).start()
# threading.Thread(target=auto_main.run_scheduler, daemon=True).start()

# ===== ADD IMPORTS FOR FOLLOW-UP HANDLING =====
import json
from supabase import create_client

# Initialize Supabase client for webhook use
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def detect_template_response_in_webhook(message_text: str, whatsapp_number: str) -> bool:
    """
    Detect follow-up template responses in webhook and save to database.
    """
    try:
        from afterservice import detect_and_save_template_response
        
        logger.info(f"Checking for template response in webhook: {message_text} from {whatsapp_number}")
        
        # Try to detect and save template response
        if detect_and_save_template_response(whatsapp_number, message_text, supabase):
            logger.info(f"✅ Template response detected and saved for {whatsapp_number}: {message_text}")
            return True
        else:
            logger.info(f"Not a template response: {message_text}")
            return False
            
    except Exception as e:
        logger.error(f"Error detecting template response in webhook: {e}")
        return False

def handle_followup_response_directly(whatsapp_number: str, button_id: str, supabase) -> bool:
    """
    Handle follow-up button response directly without going through main.py
    """
    try:
        logger.info(f"Handling follow-up response directly: {button_id} from {whatsapp_number}")
        
        # IMPORTANT: Import the function here to avoid circular imports
        from afterservice import handle_followup_response
        
        # Create a complete message structure for handle_followup_response
        message = {
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {
                    "id": button_id
                }
            }
        }
        
        # We need to get the user_id
        from utils import get_user_id
        user_id = get_user_id(supabase, whatsapp_number)
        
        if not user_id:
            logger.error(f"No user_id found for {whatsapp_number}")
            return False
        
        # IMPORTANT: Create a temporary user_data dict for this function
        user_data = {whatsapp_number: {"state": "IDLE", "processing": False, "module": None}}
        
        # Call the follow-up response handler directly
        result = handle_followup_response(whatsapp_number, user_id, supabase, user_data, message)
        
        if result:
            logger.info(f"✅ Follow-up response handled directly for {whatsapp_number}")
        else:
            logger.warning(f"⚠️ Follow-up response not handled for {whatsapp_number}")
            
        return result
        
    except Exception as e:
        logger.error(f"Error handling follow-up response directly: {e}")
        return False

def handle_notification_noted_directly(whatsapp_number: str, supabase) -> bool:
    """
    Handle notification noted button directly without going through main.py
    This prevents main menu from being sent after noted button
    """
    try:
        logger.info(f"Handling notification noted directly for {whatsapp_number}")
        
        # Mark notification as seen
        from notification import handle_notification_noted
        handle_notification_noted(whatsapp_number, supabase)
        
        # Send a simple acknowledgment message (not main menu)
        from utils import translate_template, send_whatsapp_message
        
        message = translate_template(whatsapp_number, "Thank you for acknowledging the notification. Let us know if you need any assistance.", supabase)
        
        content = {
            "text": {"body": message}
        }
        
        success = send_whatsapp_message(whatsapp_number, "text", content, supabase)
        
        if success:
            logger.info(f"✅ Notification noted handled directly for {whatsapp_number}")
            return True
        else:
            logger.error(f"❌ Failed to send acknowledgment for notification noted to {whatsapp_number}")
            return False
            
    except Exception as e:
        logger.error(f"Error handling notification noted directly: {e}")
        return False



# webhooksplit.py - UPDATED webhook handler

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Verification token mismatch", 403

    if request.method == "POST":
        data = request.get_json()
        logger.info(f"Received webhook payload: {data}")
        if not data or "entry" not in data:
            return "Invalid payload", 400

        try:
            value = data["entry"][0]["changes"][0]["value"]

            # --- Detect STATUS updates (read, delivered, sent) ---
            if "statuses" in value:
                status_info = value["statuses"][0]
                status = status_info.get("status")
                recipient = status_info.get("recipient_id")
                
                logger.info(f"Message status update: {status} for {recipient}")
                
                # Handle "read" status to update notification seen column
                if status == "read":
                    logger.info(f"📖 Message read by {recipient}")
                    try:
                        # Import the function to update notification seen status
                        from notification import update_notification_seen_status
                        
                        # Update notification seen status for this user
                        success = update_notification_seen_status(recipient, supabase)
                        if success:
                            logger.info(f"✅ Successfully updated notification seen status for {recipient}")
                        else:
                            logger.warning(f"⚠️ Failed to update notification seen status for {recipient}")
                    except Exception as e:
                        logger.error(f"❌ Error updating notification seen status: {e}", exc_info=True)
                    return "Read status processed", 200
                
                # --- Detect FAILED messages from WhatsApp ---
                if status == "failed":
                    errors = status_info.get("errors", [])
                    if errors:
                        code = errors[0].get("code")
                        if code == 131047:
                            logger.warning(f"⚠️ Message failed due to 24-hour rule for {recipient}")
                            from utils import handle_reengagement_error, send_template_for_notification
                            
                            # Try to find the original notification type for this recipient
                            try:
                                # Get the most recent notification (sent OR unsent) for this user to determine the type
                                # Look for notifications in the last 24 hours
                                twenty_four_hours_ago = (datetime.now(pytz.timezone("Asia/Kuala_Lumpur")) - timedelta(hours=24)).isoformat()
                                
                                response = supabase.table("c_notifications").select(
                                    "reminder_type"
                                ).eq("whatsapp_number", recipient.lstrip('+')).gte("time", twenty_four_hours_ago).order("time", desc=True).limit(1).execute()
                                
                                if response.data and response.data[0].get("reminder_type"):
                                    reminder_type = response.data[0]["reminder_type"]
                                    logger.info(f"📋 Found recent notification type: {reminder_type} for {recipient}")
                                    
                                    # Try to send the specific template for this notification type
                                    specific_success = send_template_for_notification(recipient, reminder_type, supabase)
                                    if specific_success:
                                        logger.info(f"✅ Specific template sent for {reminder_type} to {recipient}")
                                        return "Handled 24h reengagement with specific template", 200
                                    else:
                                        logger.warning(f"⚠️ Specific template failed, falling back to general template for {recipient}")
                                else:
                                    logger.info(f"ℹ️ No recent notifications found for {recipient}, using general template")
                                    
                            except Exception as e:
                                logger.error(f"Error finding notification type for {recipient}: {e}")
                            
                            # Fallback to general reengagement template
                            handle_reengagement_error(recipient, supabase)
                            return "Handled 24h reengagement", 200
                        else:
                            logger.warning(f"❌ Message failed for {recipient} with code {code}: {errors[0].get('message')}")
                return "Status processed", 200

            # --- Handle MESSAGES ---
            if "messages" in value:
                messages = value["messages"]
                contacts = value.get("contacts", [])
                
                if not messages:
                    logger.info("No messages in webhook")
                    return "No messages", 200
                
                whatsapp_number = messages[0]["from"]
                logger.info(f"Processing message from {whatsapp_number}")
                
                # ===== HANDLE TEMPLATE RESPONSES FIRST =====
                message_type = messages[0].get("type")
                
                # Handle button responses (interactive)
                if message_type == "interactive":
                    interactive_type = messages[0]["interactive"]["type"]
                    if interactive_type == "button_reply":
                        button_id = messages[0]["interactive"]["button_reply"]["id"]
                        
                        # Check if it's a follow-up response button
                        if button_id.startswith("followup_"):
                            logger.info(f"Follow-up button response detected: {button_id} from {whatsapp_number}")
                            
                            # Handle it directly instead of forwarding to main.py
                            if handle_followup_response_directly(whatsapp_number, button_id, supabase):
                                logger.info(f"✅ Follow-up button response handled directly")
                                return "Follow-up button processed", 200
                            else:
                                logger.error(f"Failed to handle follow-up button response")
                                return "Failed to handle follow-up", 500
                        
                        # Handle Dynamic Navigation Buttons (Groups A, B, and C)
                        elif button_id in ["notification_noted", "nav_notifications", "nav_view_booking", "nav_profile"]:
                            logger.info(f"Navigation button detected: {button_id} from {whatsapp_number}")
                            
                            from notification import handle_notification_noted, display_and_clear_notifications
                            from view_booking import handle_view_upcoming_booking
                            from utils import get_user_id
                            import main # Access the brain's memory

                            # 1. Silent DB Update (Marks as noted, but NO "Thank You" message)
                            handle_notification_noted(whatsapp_number, supabase, skip_ui=True)

                            # 2. Prime the state in main.py to prevent "Invalid Selection"
                            if whatsapp_number not in main.user_data:
                                main.user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}

                            # 3. Direct Routing & State Setting
                            if button_id == "nav_notifications":
                                main.user_data[whatsapp_number].update({"module": "notification", "state": "VIEWING"})
                                display_and_clear_notifications(supabase, whatsapp_number)
                                
                            elif button_id == "nav_view_booking":
                                u_id = get_user_id(supabase, whatsapp_number)
                                # Tell main.py we are now in the view_booking module
                                main.user_data[whatsapp_number].update({"module": "view_booking", "state": "VIEW_BOOKING_SUBMENU"})
                                handle_view_upcoming_booking(whatsapp_number, u_id, supabase, main.user_data)
                                
                            elif button_id == "nav_profile":
                                from individual import handle_individual_start
                                u_id = get_user_id(supabase, whatsapp_number)
                                main.user_data[whatsapp_number].update({"module": "individual", "state": "IDLE"})
                                handle_individual_start(whatsapp_number, u_id, supabase, main.user_data)
                            
                            elif button_id == "notification_noted":
                                # The only one that gets the "Thank you" and Main Menu
                                handle_notification_noted(whatsapp_number, supabase, skip_ui=False)
                            
                            return "Navigation processed", 200
                
                # Handle text messages (could be template responses)
                elif message_type == "text":
                    message_text = messages[0]["text"]["body"].strip()
                    logger.info(f"Text message received: {message_text} from {whatsapp_number}")
                    
                    # First try to detect if it's a follow-up template response
                    if detect_template_response_in_webhook(message_text, whatsapp_number):
                        logger.info(f"✅ Template response handled in webhook for {whatsapp_number}")
                        return "Template response processed", 200
                
                # For ALL messages (including those that weren't follow-up responses),
                # pass them to the main handler
                phone_number_id = value["metadata"]["phone_number_id"]
                handler = ACCOUNT_MAP.get(phone_number_id)
                if handler:
                    handler(value)
                    logger.info(f"Message forwarded to main handler")
                else:
                    logger.error(f"No handler for phone_number_id {phone_number_id}")
                    return "No handler", 404
                
                return "Message processed", 200

            # If we get here, it's not a status or message we recognize
            logger.warning(f"Unhandled webhook value type: {value.keys()}")
            return "Unhandled webhook type", 200

        except Exception as e:
            logger.error(f"Error processing webhook: {e}", exc_info=True)
            return f"Error: {str(e)}", 500

    return "Method not allowed", 405


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)