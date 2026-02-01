# afterservice.py - UPDATED WITH PROPER TRANSLATION FUNCTIONS
import logging
import os
import re
from datetime import datetime, timedelta, timezone
import pytz
from dotenv import load_dotenv
from supabase import create_client, Client

# Import ONLY follow-up related utils
from utils import (
    send_whatsapp_message,
    gt_tt,
    get_user_language,
    send_followup_notification,
    translate_template  # Added for hardcoded text
)

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Timezone
MALAYSIA_TZ = pytz.timezone("Asia/Kuala_Lumpur")

# Initialize Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Tables for follow-ups
TABLES = {
    'clinics': 'c_followup',
    'tcm': 'actual_followup'
}

# ============================================================================
# CORE FOLLOW-UP LOGIC - COMPLETE VERSION
# ============================================================================

def process_new_followup_entries(supabase: Client):
    """
    First follow-up sent 1 day after created_at (for testing).
    """
    total_sent = 0
    
    # Calculate cutoff time: entries older than 1 day (for testing)
    one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    
    for key, table in TABLES.items():
        try:
            # Get entries that are:
            # 1. Not yet processed (followup=False, followup_count=0)
            # 2. Created at least 1 day ago
            rows = supabase.table(table).select("*")\
                .eq("followup", False)\
                .eq("followup_count", 0)\
                .lt("created_at", one_day_ago.isoformat())\
                .execute().data
            
            logger.info(f"🔍 Found {len(rows)} entries in {table} ready for first follow-up (1 day old)")
            
            for entry in rows:
                # Use ONLY send_followup_notification
                # Use gt_tt for dynamic content (name)
                base_message = translate_template(
                    entry['whatsapp_number'], 
                    "Hi {name},\n\nHow are you feeling after your recent visit?", 
                    supabase
                )
                msg = base_message.format(name=entry['name'])
                
                if send_followup_notification(entry['whatsapp_number'], msg, supabase):
                    # Mark as Active (followup=True) and Count=1
                    supabase.table(table).update({
                        "followup": True,
                        "followup_count": 1,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }).eq("id", entry['id']).execute()
                    total_sent += 1
                    logger.info(f"✅ Sent first follow-up to {entry['name']} ({table})")
                else:
                    logger.error(f"❌ Failed to send follow-up to {entry['name']} ({table})")

        except Exception as e:
            logger.error(f"Error processing new entries in {table}: {e}")
    return total_sent

def auto_initiate_followups(supabase: Client):
    """
    System checks 1 day later for auto-initiated follow-ups.
    """
    try:
        # Check bookings older than 1 day but within last 2 days
        one_day_ago = (datetime.now() - timedelta(days=1)).isoformat()
        two_days_ago = (datetime.now() - timedelta(days=2)).isoformat()
        
        booking_tables = ['c_s_vaccination', 'c_s_checkup', 'c_s_consultation']
        
        for b_table in booking_tables:
            # Find Checked In bookings older than 1 day
            bookings = supabase.table(b_table)\
                .select("*")\
                .eq("checkin", "true")\
                .lt("date", one_day_ago)\
                .gt("date", two_days_ago)\
                .execute().data
            
            logger.info(f"🔍 Checking {b_table} for auto-initiated follow-ups")
                
            for booking in bookings:
                user_id = booking['user_id']
                
                # Check if already in c_followup (avoid duplicates)
                exists = supabase.table("c_followup").select("id").eq("user_id", user_id).execute().data
                if not exists:
                    # Get user details
                    user = supabase.table("whatsapp_users").select("*").eq("id", user_id).single().execute().data
                    if user:
                        # Use gt_tt for dynamic content (user name)
                        base_message = translate_template(
                            user['whatsapp_number'],
                            "Hi {name},\n\nIt's been a day since your visit. How are you feeling?",
                            supabase
                        )
                        msg = base_message.format(name=user['user_name'])
                        
                        if send_followup_notification(user['whatsapp_number'], msg, supabase):
                            # Insert into c_followup as Active (Count 1)
                            supabase.table("c_followup").insert({
                                "name": user['user_name'],
                                "whatsapp_number": user['whatsapp_number'],
                                "user_id": user_id,
                                "followup": True,
                                "followup_count": 1,
                                "provider_cat": 'c',
                                "created_at": datetime.now(timezone.utc).isoformat(),
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            }).execute()
                            
                            # Mark Booking as Done in original table
                            supabase.table(b_table).update({"checkin": "done"}).eq("id", booking['id']).execute()
                            logger.info(f"✅ Auto-sent follow-up to {user['user_name']}")

    except Exception as e:
        logger.error(f"Error in auto_initiate_followups: {e}")

def check_and_send_scheduled_followups(supabase: Client):
    """
    Checks for users who responded 'Same' or 'Worsen' to the first message (Count 1).
    If 7 days have passed since their response, send the second check-in.
    """
    for key, table in TABLES.items():
        try:
            # 1. Select entries where:
            # - Followup is active (True)
            # - We are at step 1 (followup_count = 1)
            # - The user actually responded (response is not null)
            rows = supabase.table(table).select("*")\
                .eq("followup", True)\
                .eq("followup_count", 1)\
                .neq("response", "Better")\
                .execute().data # We filter out 'Better' because we don't followup on that

            logger.info(f"🔍 Checking {len(rows)} active entries in {table} for 1-week followup")

            for entry in rows:
                # 2. Check time difference
                updated_at_str = entry.get('updated_at')
                if not updated_at_str: continue
                
                # Parse date safely
                try:
                    clean_date_str = updated_at_str.replace('Z', '+00:00')
                    updated_at = datetime.fromisoformat(clean_date_str)
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

                now = datetime.now(timezone.utc)
                days_diff = (now - updated_at).total_seconds() / 86400  # Convert to days

                # 3. IF 7 days HAVE PASSED -> SEND MESSAGE
                if days_diff >= 7:
                    # Use gt_tt for dynamic content (name)
                    base_message = translate_template(
                        entry['whatsapp_number'],
                        "Hi {name},\n\nChecking in again 1 week later. How is your condition now?",
                        supabase
                    )
                    msg = base_message.format(name=entry['name'])
                    
                    if send_followup_notification(entry['whatsapp_number'], msg, supabase):
                        
                        # CRITICAL STEP: Increment Count to 2
                        # We keep followup=True because we are waiting for their Second Response
                        supabase.table(table).update({
                            "followup_count": 2, 
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }).eq("id", entry['id']).execute()
                        
                        logger.info(f"✅ Sent 1-week follow-up to {entry['name']} (Moved to Count 2)")

        except Exception as e:
            logger.error(f"Error in scheduled followups {table}: {e}")

def detect_and_save_template_response(whatsapp_number: str, message_text: str, supabase: Client) -> bool:
    """
    Detect template responses and save to follow-up table.
    Now handles both first response AND 1 week follow-up response.
    """
    try:
        # Define response keywords
        response_keywords = {
            "Better": ["better", "lebih baik", "好转", "மேம்பட்டுள்ளது"],
            "Same": ["same", "sama", "没有变化", "அதேபோல உள்ளது"],
            "Worsen": ["worsen", "bertambah teruk", "恶化", "மோசமடைந்துள்ளது"]
        }
        
        # Clean the message text
        message_lower = message_text.strip().lower()
        logger.info(f"🔍 Checking template response for {whatsapp_number}: '{message_text}'")
        
        # Check for each response type
        for status_text, keywords in response_keywords.items():
            for keyword in keywords:
                keyword_lower = keyword.lower()
                
                # Use regex for exact word matching
                pattern = rf'\b{re.escape(keyword_lower)}\b'
                if re.search(pattern, message_lower):
                    logger.info(f"✅ Matched keyword '{keyword}' for status '{status_text}'")
                    
                    # Find the active follow-up entry
                    entry = None
                    active_table = None
                    
                    for key, table in TABLES.items():
                        try:
                            # Try with number variants - USE .in_() instead of .eq()
                            whatsapp_number_clean = whatsapp_number.lstrip('+')
                            number_variants = [whatsapp_number_clean, f"+{whatsapp_number_clean}"]
                            
                            res = supabase.table(table).select("*")\
                                .eq("followup", True)\
                                .or_(f"whatsapp_number.eq.{number_variants[0]},whatsapp_number.eq.{number_variants[1]}")\
                                .execute().data
                            
                            if res:
                                entry = res[0]
                                active_table = table
                                logger.info(f"Found active follow-up in {active_table} for {whatsapp_number}")
                                break
                        except Exception as e:
                            logger.error(f"Error searching in {table}: {e}")
                            continue
                    
                    if not entry:
                        logger.warning(f"No active follow-up found for {whatsapp_number} for template response.")
                        return False
                    
                    # Determine the status for logic
                    status = status_text.lower()
                    current_count = entry.get('followup_count', 0)
                    
                    updates = {
                        "response": status_text,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                    
                    # LOGIC BASED ON WHICH FOLLOW-UP THIS IS:
                    # count == 1: First follow-up response
                    # count == 2: 1-week follow-up response
                    
                    if current_count == 1:
                        # FIRST FOLLOW-UP RESPONSE
                        if status == "better":
                            updates["followup"] = False
                            reply_text = translate_template(whatsapp_number, "Glad to hear you are better! Take care.", supabase)
                        else:  # same or worsen
                            updates["followup"] = True  # Keep active for 5-min followup
                            reply_text = translate_template(whatsapp_number, "Noted. We will check on you again in 1 week. If urgent, please visit the clinic.", supabase)
                    
                    elif current_count == 2:
                        # 1-WEEK FOLLOW-UP RESPONSE
                        if status == "better":
                            updates["followup"] = False
                            reply_text = translate_template(whatsapp_number, "Thanks, glad to hear you are better!", supabase)
                        elif status == "same":
                            updates["followup"] = False
                            reply_text = translate_template(whatsapp_number, "Ok, please contact the clinic if you need assistance.", supabase)
                        elif status == "worsen":
                            updates["followup"] = False
                            reply_text = translate_template(whatsapp_number, "The clinic will contact you. If urgent, please call the clinic.", supabase)
                    
                    else:
                        # Shouldn't happen, but just in case
                        updates["followup"] = False
                        reply_text = translate_template(whatsapp_number, "Thank you for your response.", supabase)
                    
                    # Update the database
                    try:
                        supabase.table(active_table).update(updates).eq("id", entry['id']).execute()
                        logger.info(f"✅ Updated follow-up response from template for {whatsapp_number}: {status_text} (count={current_count})")
                        
                        # Send acknowledgement
                        send_whatsapp_message(entry['whatsapp_number'], "text", {"text": {"body": reply_text}}, supabase)
                        return True
                    except Exception as e:
                        logger.error(f"Error updating database: {e}")
                        return False
        
        logger.info(f"No template response match found for: '{message_text}'")
        return False
        
    except Exception as e:
        logger.error(f"Error detecting template response: {e}")
        return False

def handle_followup_response(whatsapp_number: str, user_id: str, supabase: Client, user_data: dict, message):
    try:
        # --- [Validation & extraction code same as before] ---
        if message.get("type") != "interactive": return False
        btn_id = message["interactive"]["button_reply"]["id"]
        
        status = ""
        status_text = ""
        if "better" in btn_id: status, status_text = "better", "Better"
        elif "same" in btn_id: status, status_text = "same", "Same"
        elif "worsen" in btn_id: status, status_text = "worsen", "Worsen"
        else: return False

        whatsapp_number_clean = whatsapp_number.lstrip('+')
        number_variants = [whatsapp_number_clean, f"+{whatsapp_number_clean}"]

        # --- FIND ENTRY (Active or Recent Closed) ---
        active_table = None
        found_entries = []
        is_active_session = False
        
        # 1. Try finding ACTIVE first
        for key, table in TABLES.items():
            res = supabase.table(table).select("*").in_("whatsapp_number", number_variants).eq("followup", True).execute().data
            if res:
                active_table = table; found_entries = res; is_active_session = True; break

        # 2. If no active, find CLOSED (Double click prevention)
        if not found_entries:
            for key, table in TABLES.items():
                res = supabase.table(table).select("*").in_("whatsapp_number", number_variants).eq("followup", False).order("updated_at", desc=True).limit(1).execute().data
                if res:
                    active_table = table; found_entries = res; is_active_session = False; break

        if not found_entries: return False

        # --- ACTIVE LOGIC ---
        entry = found_entries[0] # Take the first match
        entry_id = entry['id']
        current_count = entry.get('followup_count', 0)
        
        updates = {
            "response": status_text,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        reply_text = ""

        # =========================================================
        # LOGIC FOR COUNT 1 (First Response)
        # =========================================================
        if current_count == 1:
            if status == "better":
                # Case: Better on first try -> Close immediately
                updates["followup"] = False
                reply_text = translate_template(whatsapp_number, "Glad to hear you are better! Take care.", supabase)
            else:
                # Case: Same/Worsen -> Keep Open, Schedule 1-week check
                updates["followup"] = True 
                reply_text = translate_template(whatsapp_number, "Noted. We will check on you again in 1 week. If urgent, please visit the clinic.", supabase)

        # =========================================================
        # LOGIC FOR COUNT 2 (Second Response - After 1 week)
        # =========================================================
        elif current_count == 2:
            # Whatever they say now, we CLOSE the ticket (followup=False)
            updates["followup"] = False 
            
            if status == "better":
                reply_text = translate_template(whatsapp_number, "Thanks, glad to hear you are better!", supabase)
            elif status == "same":
                reply_text = translate_template(whatsapp_number, "Ok, please contact the clinic if you need assistance.", supabase)
            elif status == "worsen":
                reply_text = translate_template(whatsapp_number, "The clinic will contact you. If urgent, please call the clinic.", supabase)

        # Safety Fallback
        else:
            updates["followup"] = False
            reply_text = translate_template(whatsapp_number, "Thank you for your response.", supabase)

        # --- EXECUTE UPDATE ---
        supabase.table(active_table).update(updates).eq("id", entry_id).execute()
        
        # Send the specific reply
        send_whatsapp_message(whatsapp_number, "text", {"text": {"body": reply_text}}, supabase)
        
        return True

    except Exception as e:
        logger.error(f"Response handle error: {e}")
        return False
    
def check_and_send_followup_messages(supabase: Client):
    """
    Main Wrapper called by scheduler/cron
    """
    logger.info("🚀 Running Followup Service...")
    count1 = process_new_followup_entries(supabase)      # 1. Manual: After 1 day
    count2 = auto_initiate_followups(supabase)           # 2. Auto 1-day
    check_and_send_scheduled_followups(supabase)         # 3. Scheduled 1-week
    logger.info(f"✅ Followup Service Complete")
    return count1

def test_immediate_followup_all(supabase: Client):
    """TEST FUNCTION"""
    logger.info("=== STARTING IMMEDIATE FOLLOW-UP TEST ===")
    count = check_and_send_followup_messages(supabase)
    logger.info(f"=== TEST COMPLETE: Sent {count} messages ===")
    return count

# Aliases
send_immediate_followup_to_all = test_immediate_followup_all

# ============================================================================
# SYMPTOM TRACKER FUNCTIONS (Legacy - Keep only if needed)
# ============================================================================

def handle_symptom_tracker_selection(whatsapp_number: str, user_id: str, supabase: Client, user_data: dict):
    try:
        from_number_norm = whatsapp_number.lstrip("+").strip()
        number_variants = [from_number_norm, f"+{from_number_norm}"]
        
        entries = supabase.table("followuptable").select(
            "id, consult_date, diagnosis, doctor_name, patient_name"
        ).in_("whatsapp_number", number_variants).order("consult_date", desc=True).execute()
        
        if not entries.data:
            # Use translate_template for hardcoded string
            send_whatsapp_message(whatsapp_number, "text", {
                "text": {"body": translate_template(whatsapp_number, "You don't have any follow-up entries to track symptoms for.", supabase)}
            })
            user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
            # Note: send_interactive_menu removed - it's in utils
            return False
        
        rows = []
        for entry in entries.data:
            consult_date = entry['consult_date']
            if consult_date.endswith('Z'):
                consult_date = datetime.fromisoformat(consult_date.replace('Z', '+00:00'))
            else:
                consult_date = datetime.fromisoformat(consult_date)
            
            date_str = consult_date.strftime("%Y-%m-%d")
            # Use gt_tt for dynamic content (diagnosis), keep patient name in English
            diagnosis = gt_tt(whatsapp_number, entry['diagnosis'][:30], supabase) if entry['diagnosis'] else ""
            patient_name = entry['patient_name'][:15] if entry['patient_name'] else "Patient"
            
            rows.append({
                "id": f"symptom_entry_{entry['id']}",
                "title": f"{date_str} - {diagnosis}",
                "description": f"{patient_name}"
            })
        
        content = {
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": translate_template(whatsapp_number, "Symptom Tracker", supabase)},
                "body": {"text": translate_template(whatsapp_number, "Select the follow-up entry you want to update symptoms for:", supabase)},
                "footer": {"text": translate_template(whatsapp_number, "Track your recovery progress", supabase)},
                "action": {
                    "button": translate_template(whatsapp_number, "Select Entry", supabase),
                    "sections": [{
                        "title": translate_template(whatsapp_number, "Your Follow-up Entries", supabase), 
                        "rows": rows
                    }]
                }
            }
        }
        
        user_data[whatsapp_number]["state"] = "AWAITING_SYMPTOM_ENTRY_SELECTION"
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        return True
        
    except Exception as e:
        logger.error(f"Error handling symptom tracker selection: {e}")
        return False

def handle_symptom_tracker_response(whatsapp_number: str, user_id: str, supabase: Client, user_data: dict, message):
    try:
        state = user_data[whatsapp_number].get("state")
        
        if state == "AWAITING_SYMPTOM_ENTRY_SELECTION":
            if message["type"] == "interactive" and message["interactive"].get("type") == "list_reply":
                list_id = message["interactive"]["list_reply"]["id"]
                if list_id.startswith("symptom_entry_"):
                    entry_id = list_id.replace("symptom_entry_", "")
                    user_data[whatsapp_number]["temp_data"] = {"entry_id": entry_id}
                    user_data[whatsapp_number]["state"] = "AWAITING_SYMPTOM_STATUS"
                    send_symptom_status_question(whatsapp_number, entry_id, supabase)
                    return True
        
        elif state == "AWAITING_SYMPTOM_STATUS":
            if message["type"] == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                if button_id.startswith("symptom_status_"):
                    parts = button_id.split("_")
                    if len(parts) >= 4:
                        entry_id = parts[3]
                        status = parts[2]
                        
                        entry_data = supabase.table("followuptable").select("rec_status, consecutive_better_count").eq("id", entry_id).single().execute()
                        consecutive_better = entry_data.data.get('consecutive_better_count', 0) if entry_data.data else 0
                        
                        if status == 'better':
                            new_consecutive = consecutive_better + 1 if entry_data.data.get('rec_status') == 'better' else 1
                        else:
                            new_consecutive = 0
                        
                        updates = {
                            "rec_status": status,
                            "last_response_time": datetime.now(timezone.utc).isoformat(),
                            "consecutive_better_count": new_consecutive,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }
                        if status == 'fully recovered': updates['followup_count'] = 4
                        
                        supabase.table("followuptable").update(updates).eq("id", entry_id).execute()
                        send_symptom_tracking_confirmation(whatsapp_number, supabase)
                        user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                        return True
        return False
    except Exception as e:
        logger.error(f"Error handling symptom tracker response: {e}")
        return False

def send_symptom_status_question(whatsapp_number: str, entry_id: str, supabase: Client):
    try:
        entry_data = supabase.table("followuptable").select("diagnosis, patient_name").eq("id", entry_id).execute()
        if entry_data.data:
            # Use gt_tt for dynamic content (diagnosis), keep patient name in English
            base_message = translate_template(
                whatsapp_number, 
                "Hi {patient_name}, how are you feeling regarding your {diagnosis}?", 
                supabase
            )
            message_body = base_message.format(
                patient_name=entry_data.data[0]['patient_name'],
                diagnosis=gt_tt(whatsapp_number, entry_data.data[0]['diagnosis'], supabase)
            )
        else:
            message_body = translate_template(whatsapp_number, "How are you feeling today?", supabase)
    
        # Use the new followup notification function
        send_followup_notification(whatsapp_number, message_body, supabase)
    except Exception as e:
        logger.error(f"Error sending symptom status question: {e}")

def send_symptom_tracking_confirmation(whatsapp_number: str, supabase: Client):
    # Use translate_template for hardcoded string
    confirmation_message = translate_template(
        whatsapp_number, 
        "Thank you for updating your symptoms. Your doctor will see this information.", 
        supabase
    )
    send_whatsapp_message(whatsapp_number, "text", {"text": {"body": confirmation_message}}, supabase)