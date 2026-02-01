import logging
from datetime import datetime, timedelta
import pytz
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from utils import send_free_notification, send_interactive_menu, translate_template, gt_t_tt, gt_tt, send_whatsapp_message, send_notification_with_fallback, send_template_for_notification
from supabase import create_client, Client
import httpx
import uuid
from collections import defaultdict
import threading
import traceback
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Timezone
MALAYSIA_TZ = pytz.timezone("Asia/Kuala_Lumpur")

# Replace the hardcoded Supabase credentials:
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Global variables for rate limiting and spam prevention
notification_lock = threading.Lock()
last_notification_time = {}
processed_notification_ids = {}  # Track {notification_id: timestamp}

# -------------------------
# Insert notification helper - UPDATED
# -------------------------
def insert_notification(whatsapp_number, case_id, message, user_id, reminder_type="confirm", provider_cat=None, clinic_id=None):
    """
    Insert a notification row with proper reminder_type, provider_cat, and clinic_id.
    """
    try:
        # Ensure reminder_type is never None
        if reminder_type is None:
            reminder_type = "confirm"
            
        # Check if notification already exists
        try:
            existing_check = supabase.table("c_notifications").select("id, sent").eq("user_id", user_id).eq("case_id", case_id).eq("reminder_type", reminder_type).execute()
            if existing_check.data:
                for existing in existing_check.data:
                    if existing.get("sent") == True:
                        logger.info(f"Notification already sent for user {user_id}, case {case_id}, type {reminder_type}. Skipping.")
                        return {"data": [{"id": existing["id"]}]}
                    else:
                        logger.info(f"Notification exists but not sent. Will send: user {user_id}, case {case_id}, type {reminder_type}")
                        return {"data": [{"id": existing["id"]}]}
        except Exception as check_error:
            logger.warning(f"Error checking existing notification: {check_error}")
        
        # If no duplicate found, proceed with insertion
        data = {
            "id": str(uuid.uuid4()),
            "whatsapp_number": whatsapp_number,
            "case_id": case_id,
            "notification": message,
            "user_id": user_id,
            "sent": False,
            "prompted": False,
            "seen": False,
            "noted": False,
            "time": datetime.now(MALAYSIA_TZ).isoformat(),
            "reminder_type": reminder_type,
            "provider_cat": provider_cat,
            "clinic_id": clinic_id
        }

        logger.info(f"Inserting notification: user_id={user_id}, case_id={case_id}, reminder_type={reminder_type}, provider_cat={provider_cat}, clinic_id={clinic_id}")

        response = supabase.table("c_notifications").insert(data).execute()
        logger.info(f"Successfully inserted notification for user {user_id}, case {case_id}, type {reminder_type}")
        return response

    except Exception as e:
        if "unique_notification" in str(e).lower() or "duplicate key" in str(e).lower() or "409" in str(e):
            logger.debug(f"Duplicate notification skipped (user {user_id}, case {case_id}, type {reminder_type})")
            return {"data": [{"id": "duplicate_" + str(uuid.uuid4())}]}
        else:
            logger.error(f"Error inserting notification for user {user_id}, case {case_id}: {e}", exc_info=True)
        return None

def get_clinic_id_for_booking(booking, provider_cat):
    """
    Get clinic_id for a booking based on provider category.
    For TCM: Get clinic_id from tcm_a_doctors via doctor_id
    For Clinic: Get clinic_id from c_a_doctors via doctor_id
    """
    clinic_id = None
    try:
        doctor_id = booking.get("doctor_id")
        if not doctor_id:
            return None
            
        if provider_cat == "tcm":
            # Get doctor's clinic from tcm_a_doctors
            doctor_resp = supabase.table("tcm_a_doctors").select("clinic_id").eq("id", doctor_id).execute()
            if doctor_resp.data and doctor_resp.data[0].get("clinic_id"):
                clinic_id = doctor_resp.data[0]["clinic_id"]
                
        elif provider_cat == "clinic":
            # Get doctor's clinic from c_a_doctors
            doctor_resp = supabase.table("c_a_doctors").select("clinic_id").eq("id", doctor_id).execute()
            if doctor_resp.data and doctor_resp.data[0].get("clinic_id"):
                clinic_id = doctor_resp.data[0]["clinic_id"]
                
    except Exception as e:
        logger.error(f"Error getting clinic_id for booking: {e}")
    
    return clinic_id

# -------------------------
# Check and send booking confirmations (UPDATED FOR VACCINATION TABLE + TCM)
# -------------------------
def check_and_send_booking_confirmations(supabase):
    """
    Check for new bookings in checkup, consultation, vaccination, and TCM tables
    and send confirmation notifications.
    Handles both single bookings and repeated visits.
    """
    try:
        logger.info(translate_template("+1234567890", "Checking for new bookings to send confirmations...", supabase))
        
        now = datetime.now(MALAYSIA_TZ)
        one_hour_ago = (now - timedelta(hours=1)).isoformat()
        
        # Check checkup bookings - UPDATED with doctor_id
        try:
            checkup_resp = supabase.table("c_s_checkup").select(
                "id, user_id, date, time, details, repeated_visit_uuid, created_at, doctor_id"
            ).gte("created_at", one_hour_ago).execute()
            
            logger.info(translate_template("+1234567890", f"Found {len(checkup_resp.data or [])} new bookings in c_s_checkup", supabase))
            
            for booking in checkup_resp.data or []:
                try:
                    user_id = booking["user_id"]
                    repeated_visit_uuid = booking.get("repeated_visit_uuid")
                    
                    # Get user's WhatsApp number
                    user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", user_id).execute()
                    if not user_resp.data:
                        logger.error(translate_template("+1234567890", f"No user found for user_id {user_id}", supabase))
                        continue
                        
                    whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                    if not whatsapp_number:
                        logger.error(translate_template("+1234567890", f"No WhatsApp number for user_id {user_id}", supabase))
                        continue
                    
                    # Get clinic_id for clinic booking
                    clinic_id = get_clinic_id_for_booking(booking, "clinic")
                    
                    # Check if notification already exists for this booking
                    existing = supabase.table("c_notifications").select("id").eq("user_id", user_id).eq("case_id", booking["id"]).eq("reminder_type", "confirm").execute()
                    if existing.data:
                        logger.info(translate_template(whatsapp_number, f"Notification already exists for booking {booking['id']}. Skipping.", supabase))
                        continue
                    
                    # Single booking - create individual notification
                    booking_date = booking.get("date")
                    booking_time = booking.get("time")
                    
                    # Get booking details
                    details = booking.get("details", "Checkup")
                    notification_msg = gt_tt(whatsapp_number, f"Your checkup booking is confirmed on ", supabase) + f"{booking_date} at {booking_time}."
                    
                    # Insert single booking notification
                    insert_notification(
                        whatsapp_number=whatsapp_number,
                        case_id=booking["id"],
                        message=notification_msg,
                        user_id=user_id,
                        reminder_type="confirm",
                        provider_cat="clinic",
                        clinic_id=clinic_id
                    )
                    logger.info(translate_template(whatsapp_number, f"Created single checkup notification for {whatsapp_number}, booking {booking['id']}", supabase))
                        
                except Exception as e:
                    logger.error(translate_template("+1234567890", f"Error processing checkup booking {booking.get('id')}: {e}", supabase), exc_info=True)
                    continue
                    
        except Exception as e:
            logger.error(translate_template("+1234567890", f"Error fetching from c_s_checkup: {e}", supabase), exc_info=True)
        
        # Check consultation bookings - UPDATED with doctor_id
        try:
            consultation_resp = supabase.table("c_s_consultation").select(
                "id, user_id, date, time, details, repeated_visit_uuid, created_at, doctor_id"
            ).gte("created_at", one_hour_ago).execute()
            
            logger.info(translate_template("+1234567890", f"Found {len(consultation_resp.data or [])} new bookings in c_s_consultation", supabase))
            
            for booking in consultation_resp.data or []:
                try:
                    user_id = booking["user_id"]
                    repeated_visit_uuid = booking.get("repeated_visit_uuid")
                    
                    # Get user's WhatsApp number
                    user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", user_id).execute()
                    if not user_resp.data:
                        logger.error(translate_template("+1234567890", f"No user found for user_id {user_id}", supabase))
                        continue
                        
                    whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                    if not whatsapp_number:
                        logger.error(translate_template("+1234567890", f"No WhatsApp number for user_id {user_id}", supabase))
                        continue
                    
                    # Get clinic_id for clinic booking
                    clinic_id = get_clinic_id_for_booking(booking, "clinic")
                    
                    # Check if notification already exists for this booking
                    existing = supabase.table("c_notifications").select("id").eq("user_id", user_id).eq("case_id", booking["id"]).eq("reminder_type", "confirm").execute()
                    if existing.data:
                        logger.info(translate_template(whatsapp_number, f"Notification already exists for booking {booking['id']}. Skipping.", supabase))
                        continue
                    
                    # Single booking - create individual notification
                    booking_date = booking.get("date")
                    booking_time = booking.get("time")
                    
                    # Get booking details
                    details = booking.get("details", "Consultation")
                    notification_msg = gt_tt(whatsapp_number, f"Your consultation booking is confirmed on ", supabase) + f"{booking_date} at {booking_time}."
                    
                    # Insert single booking notification
                    insert_notification(
                        whatsapp_number=whatsapp_number,
                        case_id=booking["id"],
                        message=notification_msg,
                        user_id=user_id,
                        reminder_type="confirm",
                        provider_cat="clinic",
                        clinic_id=clinic_id
                    )
                    logger.info(translate_template(whatsapp_number, f"Created single consultation notification for {whatsapp_number}, booking {booking['id']}", supabase))
                        
                except Exception as e:
                    logger.error(translate_template("+1234567890", f"Error processing consultation booking {booking.get('id')}: {e}", supabase), exc_info=True)
                    continue
                    
        except Exception as e:
            logger.error(translate_template("+1234567890", f"Error fetching from c_s_consultation: {e}", supabase), exc_info=True)
        
        # Check vaccination bookings (USING vaccine_type INSTEAD OF details) - UPDATED with doctor_id
        try:
            vaccination_resp = supabase.table("c_s_vaccination").select(
                "id, user_id, date, time, vaccine_type, repeated_visit_uuid, created_at, doctor_id"
            ).gte("created_at", one_hour_ago).execute()
            
            logger.info(translate_template("+1234567890", f"Found {len(vaccination_resp.data or [])} new bookings in c_s_vaccination", supabase))
            
            for booking in vaccination_resp.data or []:
                try:
                    user_id = booking["user_id"]
                    repeated_visit_uuid = booking.get("repeated_visit_uuid")
                    
                    # Get user's WhatsApp number
                    user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", user_id).execute()
                    if not user_resp.data:
                        logger.error(translate_template("+1234567890", f"No user found for user_id {user_id}", supabase))
                        continue
                        
                    whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                    if not whatsapp_number:
                        logger.error(translate_template("+1234567890", f"No WhatsApp number for user_id {user_id}", supabase))
                        continue
                    
                    # Get clinic_id for clinic booking
                    clinic_id = get_clinic_id_for_booking(booking, "clinic")
                    
                    # Check if notification already exists for this booking
                    existing = supabase.table("c_notifications").select("id").eq("user_id", user_id).eq("case_id", booking["id"]).eq("reminder_type", "confirm").execute()
                    if existing.data:
                        logger.info(translate_template(whatsapp_number, f"Notification already exists for booking {booking['id']}. Skipping.", supabase))
                        continue
                    
                    # Single booking - create individual notification
                    booking_date = booking.get("date")
                    booking_time = booking.get("time")
                    
                    # Get booking details - USE vaccine_type FOR VACCINATION
                    details = booking.get("vaccine_type", "Vaccination")
                    notification_msg = gt_tt(whatsapp_number, f"Your vaccination booking for {details} is confirmed on ", supabase) + f"{booking_date} at {booking_time}."
                    
                    # Insert single booking notification
                    insert_notification(
                        whatsapp_number=whatsapp_number,
                        case_id=booking["id"],
                        message=notification_msg,
                        user_id=user_id,
                        reminder_type="confirm",
                        provider_cat="clinic",
                        clinic_id=clinic_id
                    )
                    logger.info(translate_template(whatsapp_number, f"Created single vaccination notification for {whatsapp_number}, booking {booking['id']}", supabase))
                        
                except Exception as e:
                    logger.error(translate_template("+1234567890", f"Error processing vaccination booking {booking.get('id')}: {e}", supabase), exc_info=True)
                    continue
                    
        except Exception as e:
            logger.error(translate_template("+1234567890", f"Error fetching from c_s_vaccination: {e}", supabase), exc_info=True)

        # Check TCM bookings
        try:
            tcm_resp = supabase.table("tcm_s_bookings").select(
                "id, user_id, original_date, original_time, new_date, new_time, booking_type, details, repeated_visit_uuid, created_at, status, doctor_id"
            ).gte("created_at", one_hour_ago).eq("status", "confirmed").execute()
            
            logger.info(translate_template("+1234567890", f"Found {len(tcm_resp.data or [])} new TCM bookings", supabase))
            
            for booking in tcm_resp.data or []:
                try:
                    user_id = booking["user_id"]
                    repeated_visit_uuid = booking.get("repeated_visit_uuid")
                    
                    # Get user's WhatsApp number
                    user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", user_id).execute()
                    if not user_resp.data:
                        logger.error(translate_template("+1234567890", f"No user found for user_id {user_id}", supabase))
                        continue
                        
                    whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                    if not whatsapp_number:
                        logger.error(translate_template("+1234567890", f"No WhatsApp number for user_id {user_id}", supabase))
                        continue
                    
                    # Get clinic_id for TCM booking (from doctor to clinic relationship)
                    clinic_id = None
                    try:
                        # Get doctor's clinic
                        if booking.get("doctor_id"):
                            doctor_resp = supabase.table("tcm_a_doctors").select("clinic_id").eq("id", booking["doctor_id"]).execute()
                            if doctor_resp.data and doctor_resp.data[0].get("clinic_id"):
                                clinic_id = doctor_resp.data[0]["clinic_id"]
                    except Exception as clinic_err:
                        logger.error(f"Error getting clinic_id for TCM booking: {clinic_err}")
                    
                    # Check if notification already exists for this booking
                    case_id_to_check = repeated_visit_uuid if repeated_visit_uuid else booking["id"]
                    
                    existing = supabase.table("c_notifications").select("id").eq("user_id", user_id).eq("case_id", case_id_to_check).eq("reminder_type", "confirm").execute()
                    if existing.data:
                        logger.info(translate_template(whatsapp_number, f"Notification already exists for TCM booking {booking['id']}. Skipping.", supabase))
                        continue
                    
                    # Get appointment date and time (use new if available, otherwise original)
                    booking_date = booking.get("new_date") or booking.get("original_date")
                    booking_time = booking.get("new_time") or booking.get("original_time")
                    
                    # Single booking - create individual notification
                    details = booking.get("details", "TCM Consultation")
                    booking_type = booking.get("booking_type", "consultation")
                    notification_msg = gt_tt(whatsapp_number, f"Your TCM {booking_type} booking is confirmed on ", supabase) + f"{booking_date} at {booking_time}."
                    
                    # Insert single booking notification
                    insert_notification(
                        whatsapp_number=whatsapp_number,
                        case_id=booking["id"],
                        message=notification_msg,
                        user_id=user_id,
                        reminder_type="confirm",
                        provider_cat="tcm",
                        clinic_id=clinic_id
                    )
                    logger.info(translate_template(whatsapp_number, f"Created single TCM notification for {whatsapp_number}, booking {booking['id']}", supabase))
                        
                except Exception as e:
                    logger.error(translate_template("+1234567890", f"Error processing TCM booking {booking.get('id')}: {e}", supabase), exc_info=True)
                    continue
                    
        except Exception as e:
            logger.error(translate_template("+1234567890", f"Error fetching from tcm_s_bookings: {e}", supabase), exc_info=True)
    except Exception as e:
        logger.error(translate_template("+1234567890", f"Error fetching from tcm_s_bookings: {e}", supabase), exc_info=True)

# -------------------------
# NEW: Check and send ambulance notifications for a_day reminder_type
# -------------------------
def check_and_send_ambulance_notifications(supabase):
    """
    Check for new ambulance bookings in the 4 tables (hometohome, hometohosp, hosptohome, hosptohosp)
    and send notifications with reminder_type = "a_day"
    """
    try:
        logger.info(translate_template("+1234567890", "Checking for new ambulance bookings to send notifications...", supabase))
        
        now = datetime.now(MALAYSIA_TZ)
        one_hour_ago = (now - timedelta(hours=1)).isoformat()
        
        # List of ambulance tables to check
        ambulance_tables = [
            ("a_s_hometohome", "Home to Home Transfer"),
            ("a_s_hometohosp", "Home to Hospital Transfer"),
            ("a_s_hosptohome", "Hospital to Home Discharge"),
            ("a_s_hosptohosp", "Hospital to Hospital Transfer")
        ]
        
        for table_name, service_type in ambulance_tables:
            try:
                # Get new bookings from the last hour
                resp = supabase.table(table_name).select(
                    "id, whatsapp_number, patient_name, scheduled_date, scheduled_time, provider_id, created_at"
                ).gte("created_at", one_hour_ago).execute()
                
                logger.info(translate_template("+1234567890", f"Found {len(resp.data or [])} new bookings in {table_name}", supabase))
                
                for booking in resp.data or []:
                    try:
                        whatsapp_number = booking.get("whatsapp_number", "").lstrip('+')
                        if not whatsapp_number:
                            continue
                        
                        # Get user ID from whatsapp_users table
                        user_resp = supabase.table("whatsapp_users").select("id").eq("whatsapp_number", whatsapp_number).execute()
                        if not user_resp.data:
                            logger.error(translate_template(whatsapp_number, f"No user found for WhatsApp number {whatsapp_number}", supabase))
                            continue
                        
                        user_id = user_resp.data[0]["id"]
                        case_id = booking["id"]
                        
                        # Check if notification already exists
                        existing = supabase.table("c_notifications").select("id").eq("user_id", user_id).eq("case_id", case_id).eq("reminder_type", "a_day").execute()
                        if existing.data:
                            logger.info(translate_template(whatsapp_number, f"Notification already exists for ambulance booking {case_id}. Skipping.", supabase))
                            continue
                        
                        # Create notification message
                        patient_name = booking.get("patient_name", "Patient")
                        scheduled_date = booking.get("scheduled_date", "N/A")
                        scheduled_time = booking.get("scheduled_time", "N/A")
                        
                        notification_msg = f"Your {service_type} for {patient_name} is scheduled on {scheduled_date} at {scheduled_time}."
                        
                        # Insert notification with a_day reminder_type
                        insert_notification(
                            whatsapp_number=whatsapp_number,
                            case_id=case_id,
                            message=notification_msg,
                            user_id=user_id,
                            reminder_type="a_day",
                            provider_cat="ambulance",
                            clinic_id=None
                        )
                        logger.info(translate_template(whatsapp_number, f"Created a_day notification for {whatsapp_number}, booking {case_id}", supabase))
                        
                    except Exception as e:
                        logger.error(translate_template("+1234567890", f"Error processing ambulance booking {booking.get('id')} from {table_name}: {e}", supabase), exc_info=True)
                        continue
                        
            except Exception as e:
                logger.error(translate_template("+1234567890", f"Error fetching from {table_name}: {e}", supabase), exc_info=True)
                continue
                
    except Exception as e:
        logger.error(translate_template("+1234567890", f"Error in check_and_send_ambulance_notifications: {e}", supabase), exc_info=True)

# -------------------------
# Immediate booking confirmations (for startup)
# -------------------------
def send_immediate_booking_confirmations():
    """
    Send booking confirmations immediately when server starts.
    Checks for bookings from the last 24 hours.
    """
    try:
        logger.info(translate_template("+1234567890", "=== Running immediate booking confirmations ===", supabase))
        check_and_send_booking_confirmations(supabase)
        
        # Also check TCM bookings from last 24 hours
        try:
            twenty_four_hours_ago = (datetime.now(MALAYSIA_TZ) - timedelta(hours=24)).isoformat()
            tcm_resp = supabase.table("tcm_s_bookings").select(
                "id, user_id, original_date, original_time, new_date, new_time, booking_type, details, repeated_visit_uuid, created_at, status, doctor_id"
            ).gte("created_at", twenty_four_hours_ago).eq("status", "confirmed").execute()
            
            logger.info(translate_template("+1234567890", f"Found {len(tcm_resp.data or [])} TCM bookings from last 24 hours", supabase))
            
            for booking in tcm_resp.data or []:
                try:
                    user_id = booking["user_id"]
                    
                    # Get user's WhatsApp number
                    user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", user_id).execute()
                    if not user_resp.data:
                        continue
                        
                    whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                    if not whatsapp_number:
                        continue
                    
                    # Get clinic_id for TCM booking
                    clinic_id = None
                    try:
                        if booking.get("doctor_id"):
                            doctor_resp = supabase.table("tcm_a_doctors").select("clinic_id").eq("id", booking["doctor_id"]).execute()
                            if doctor_resp.data and doctor_resp.data[0].get("clinic_id"):
                                clinic_id = doctor_resp.data[0]["clinic_id"]
                    except Exception as clinic_err:
                        logger.error(f"Error getting clinic_id for TCM booking: {clinic_err}")
                    
                    # Check if notification already exists for this booking
                    existing = supabase.table("c_notifications").select("id").eq("user_id", user_id).eq("case_id", booking["id"]).eq("reminder_type", "confirm").execute()
                    if existing.data:
                        continue
                    
                    # Get appointment date and time
                    booking_date = booking.get("new_date") or booking.get("original_date")
                    booking_time = booking.get("new_time") or booking.get("original_time")
                    booking_type = booking.get("booking_type", "consultation")
                    
                    # Create notification message
                    notification_msg = gt_tt(whatsapp_number, f"Your TCM {booking_type} booking is confirmed on ", supabase) + f"{booking_date} at {booking_time}."
                    
                    # Insert single booking notification
                    insert_notification(
                        whatsapp_number=whatsapp_number,
                        case_id=booking["id"],
                        message=notification_msg,
                        user_id=user_id,
                        reminder_type="confirm",
                        provider_cat="tcm",
                        clinic_id=clinic_id
                    )
                    logger.info(translate_template(whatsapp_number, f"Created immediate TCM notification for {whatsapp_number}, booking {booking['id']}", supabase))
                        
                except Exception as e:
                    logger.error(translate_template("+1234567890", f"Error processing immediate TCM booking {booking.get('id')}: {e}", supabase))
                    continue
                    
        except Exception as e:
            logger.error(translate_template("+1234567890", f"Error in immediate TCM confirmations: {e}", supabase))
            
        # Also check ambulance bookings from last 24 hours
        logger.info(translate_template("+1234567890", "=== Running immediate ambulance notifications ===", supabase))
        check_and_send_ambulance_notifications(supabase)
            
    except Exception as e:
        logger.error(translate_template("+1234567890", f"Error in send_immediate_booking_confirmations: {e}", supabase), exc_info=True)

# notification.py - UPDATED process_notifications function

def process_notifications(supabase):
    """
    Send WhatsApp messages for notifications using the free-first, template-fallback strategy.
    """
    try:
        # Get all unsent notifications from the last 24 hours only
        twenty_four_hours_ago = (datetime.now(MALAYSIA_TZ) - timedelta(hours=24)).isoformat()
        
        with notification_lock:
            # Get notifications that are not sent and not currently being processed
            resp = supabase.table("c_notifications").select(
                "id, user_id, whatsapp_number, notification, time, reminder_type, case_id, sent, provider_cat, clinic_id"
            ).eq("sent", False).gte("time", twenty_four_hours_ago).order("time", desc=True).limit(50).execute()
            
            logger.info(f"Found {len(resp.data or [])} total unsent notifications to process (last 24 hours)")
            
            if not resp.data:
                return

            now = datetime.now().timestamp()
            
            # Track which notifications we're processing in this batch
            processing_ids = []
            for row in resp.data:
                notification_id = row['id']
                wnum = row.get("whatsapp_number")
                
                if not wnum:
                    continue

                # Skip if processed recently (within last 5 minutes)
                if notification_id in processed_notification_ids:
                    last_processed = processed_notification_ids[notification_id]
                    if now - last_processed < 300:  # 5 minutes cooldown
                        logger.debug(f"Skipping notification {notification_id} - processed recently")
                        continue
                
                # Add to processing batch
                processing_ids.append(notification_id)
            
            if not processing_ids:
                return
            
            # Now mark these notifications as being processed (atomic update)
            try:
                mark_result = supabase.table("c_notifications").update({
                    "sent": True  # Mark as sent immediately to prevent other processes from picking it up
                }).in_("id", processing_ids).eq("sent", False).execute()
                
                if not mark_result.data:
                    logger.warning("No notifications were marked for processing (already being processed?)")
                    return
                    
            except Exception as e:
                logger.error(f"Error marking notifications for processing: {e}")
                return
            
            # Now process each marked notification
            for row in resp.data:
                notification_id = row['id']
                if notification_id not in processing_ids:
                    continue
                    
                wnum = row.get("whatsapp_number")
                if not wnum:
                    continue

                # Apply rate limiting per user
                last_time = last_notification_time.get(wnum, 0)
                if now - last_time < 300:  # 300 seconds = 5 minutes throttle per user
                    logger.debug(f"Throttling notification for {wnum} - last sent {now - last_time:.1f}s ago")
                    # Unmark this notification since we're skipping it
                    try:
                        supabase.table("c_notifications").update({
                            "sent": False
                        }).eq("id", notification_id).execute()
                    except:
                        pass
                    continue
                
                last_notification_time[wnum] = now

                notification_message = row['notification']
                reminder_type = row.get('reminder_type', 'general')
                provider_cat = row.get('provider_cat')
                clinic_id = row.get('clinic_id')
                
                # LOG THE FIELDS TO SEE WHAT WE HAVE
                logger.info(f"Processing notification {notification_id} for {wnum}, type: {reminder_type}, provider_cat: {provider_cat}, clinic_id: {clinic_id}")
                
                try:
                    # Use the proper strategy: interactive notification with header/footer/button first, template fallback
                    # PASS THE ACTUAL reminder_type FROM DATABASE ROW
                    success = send_notification_with_fallback(
                        to=wnum,
                        message=notification_message,
                        reminder_type=reminder_type,  # PASSING THE ACTUAL reminder_type
                        supabase=supabase
                    )
                    
                    if success:
                        # Already marked as sent above, just update the timestamp
                        processed_notification_ids[notification_id] = now
                        logger.info(f"Successfully sent notification {notification_id} for {wnum} with reminder_type: {reminder_type}")
                    else:
                        logger.error(f"Failed to send notification {notification_id} to {wnum} (all methods failed)")
                        # Mark as not sent so it can be retried
                        try:
                            supabase.table("c_notifications").update({
                                "sent": False
                            }).eq("id", notification_id).execute()
                        except:
                            pass
                        # Still track as processed to avoid immediate retry
                        processed_notification_ids[notification_id] = now
                        
                except Exception as e:
                    logger.error(f"Error sending notification {notification_id} to {wnum}: {e}", exc_info=True)
                    # Mark as not sent for retry
                    try:
                        supabase.table("c_notifications").update({
                            "sent": False
                        }).eq("id", notification_id).execute()
                    except:
                        pass
                    processed_notification_ids[notification_id] = now

    except Exception as e:
        logger.error(f"Error in process_notifications: {e}", exc_info=True)
# -------------------------
# Update notification seen status
# -------------------------
def update_notification_seen_status(whatsapp_number: str, supabase=None):
    """
    Update seen status for notifications when a message is read.
    Called from webhook when status is "read".
    """
    try:
        whatsapp_number_norm = whatsapp_number.lstrip('+').strip()
        
        # Get user ID
        user_resp = supabase.table("whatsapp_users").select("id").eq("whatsapp_number", whatsapp_number_norm).single().execute()
        if not user_resp.data:
            # Try with + prefix
            user_resp = supabase.table("whatsapp_users").select("id").eq("whatsapp_number", f"+{whatsapp_number_norm}").single().execute()
            if not user_resp.data:
                logger.warning(f"No user found for {whatsapp_number}")
                return False
        
        user_id = user_resp.data.get("id")
        
        # Update all notifications for this user that are sent but not seen
        update_result = supabase.table("c_notifications").update({
            "seen": True
        }).eq("user_id", user_id).eq("sent", True).eq("seen", False).execute()
        
        if update_result.data:
            logger.info(f"Updated seen status for {len(update_result.data)} notifications for user {user_id}")
            return True
        else:
            logger.info(f"No notifications to mark as seen for user {user_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error updating notification seen status for {whatsapp_number}: {e}", exc_info=True)
        return False

# -------------------------
# Handle "Noted" button click
# -------------------------
def handle_notification_noted(whatsapp_number: str, supabase=None, skip_ui=False):
    """
    Marks all notifications for the user as noted.
    If skip_ui is True, it updates the DB without sending messages to the user.
    """
    try:
        whatsapp_number_norm = whatsapp_number.lstrip('+').strip()
        user_resp = supabase.table("whatsapp_users").select("id").eq("whatsapp_number", whatsapp_number_norm).single().execute()
        if not user_resp.data:
            return False
        
        user_id = user_resp.data.get("id")
        # Update database
        supabase.table("c_notifications").update({"noted": True}).eq("user_id", user_id).execute()
        
        # Only send UI responses if NOT skipping
        if not skip_ui:
            from utils import translate_template, send_free_notification, send_interactive_menu
            send_free_notification(whatsapp_number, translate_template(whatsapp_number, "Thank you for acknowledging!", supabase), supabase)
            send_interactive_menu(whatsapp_number, supabase)
        return True
    except Exception as e:
        logger.error(f"Error handling notification noted: {e}")
        return False
# -------------------------
# Display and clear notifications
# -------------------------
def display_and_clear_notifications(supabase, whatsapp_number: str):
    """
    Show all notifications to the user.
    This is ONLY called when user manually clicks the notification button.
    Marks notifications as prompted when displayed.
    Uses the interactive notification with header/footer/button format.
    """
    try:
        whatsapp_number_norm = whatsapp_number.lstrip('+').strip()
        user_resp = supabase.table("whatsapp_users").select("id, language").eq("whatsapp_number", whatsapp_number_norm).single().execute()
        if not user_resp.data:
            # Try with + prefix
            user_resp = supabase.table("whatsapp_users").select("id, language").eq("whatsapp_number", f"+{whatsapp_number_norm}").single().execute()
            if not user_resp.data:
                send_free_notification(whatsapp_number, translate_template(whatsapp_number, "Error: User not found.", supabase), supabase)
                send_interactive_menu(whatsapp_number, supabase)
                return

        user_id = user_resp.data.get("id")
        user_language = user_resp.data.get("language")

        # Get sent notifications that are not prompted (haven't been displayed in notification button)
        resp = supabase.table("c_notifications").select("*").eq("user_id", user_id).eq("sent", True).eq("prompted", False).order("time", desc=True).execute()
        notifications = resp.data or []

        if not notifications:
            # Use the interactive notification format even for "no notifications" message
            from utils import send_interactive_notification_with_header_footer_button
            success = send_interactive_notification_with_header_footer_button(
                whatsapp_number, 
                translate_template(whatsapp_number, "No new notifications found.", supabase), 
                "customc", # Routes them to 'Notification' view if they click the button
                supabase
            )
            
            if not success:
                send_free_notification(whatsapp_number, translate_template(whatsapp_number, "No new notifications found.", supabase), supabase)
            
            send_interactive_menu(whatsapp_number, supabase)
            return

        # Build messages with translations
        message_parts = []
        notification_ids = []  # Track all notification IDs to mark as prompted
        
        for n in notifications:
            t = n.get("time")
            time_obj = datetime.now(pytz.utc)
            try:
                if isinstance(t, str):
                    time_obj = datetime.fromisoformat(t.replace("Z", "+00:00"))
                elif isinstance(t, datetime):
                    time_obj = t
            except Exception as e:
                logger.warning(f"Error parsing notification time {t}: {e}")
                pass

            time_str = time_obj.astimezone(MALAYSIA_TZ).strftime("%Y-%m-%d %H:%M")
            
            # Get notification text
            notification_text = n.get("notification") or "N/A"
            
            message_parts.append(f"[{time_str}] {notification_text}")
            notification_ids.append(n.get("id"))  # Add to list of IDs to mark as prompted

        # Join notifications with double newlines
        full_message = "\n\n".join(message_parts)

        # Change the last argument to "customc" so the button says "Notification" (Group A)
        from utils import send_interactive_notification_with_header_footer_button
        success = send_interactive_notification_with_header_footer_button(
            whatsapp_number, 
            full_message, 
            "customc", # This triggers Group A button in utils.py
            supabase
        )
        
        if not success:
            # Fallback to simple text message
            send_free_notification(whatsapp_number, full_message, supabase)

        # Mark ALL displayed notifications as prompted (so they won't display again)
        if notification_ids:
            update_result = supabase.table("c_notifications").update({
                "prompted": True
            }).in_("id", notification_ids).execute()
            
            if update_result.data:
                logger.info(f"Marked {len(notification_ids)} notifications as prompted for user {user_id}")
            else:
                logger.error(f"Failed to mark notifications as prompted for user {user_id}")

        # Send confirmation message
        send_free_notification(whatsapp_number, translate_template(whatsapp_number, f"{len(message_parts)} notification(s) displayed!", supabase), supabase)
        send_interactive_menu(whatsapp_number, supabase)

    except Exception as e:
        logger.error(f"Error in display_and_clear_notifications for {whatsapp_number}: {e}", exc_info=True)
        send_free_notification(whatsapp_number, translate_template(whatsapp_number, "Error displaying notifications. Please try again.", supabase), supabase)
        send_interactive_menu(whatsapp_number, supabase)

# -------------------------
# Helper function to get user language
# -------------------------
def get_user_language(supabase, whatsapp_number: str) -> str:
    """Get user's language preference from database."""
    try:
        from_number_norm = whatsapp_number.lstrip("+").strip()
        number_variants = [from_number_norm, f"+{from_number_norm}"]
        response = supabase.table("whatsapp_users").select("language").in_("whatsapp_number", number_variants).limit(1).execute()
        if response.data:
            return response.data[0]["language"]
        return "en"
    except Exception as e:
        logger.error(f"Error fetching language for {whatsapp_number}: {e}")
        return "en"

# -------------------------
# Reminder scheduler (UPDATED FOR dayc, weekc, customc REMINDER TYPES + AMBULANCE a_day)
# -------------------------
def check_and_send_reminder_notifications(supabase):
    """
    Generate reminders at 1 week and 1 day before bookings.
    Sets appropriate reminder_type based on timing.
    """
    now = datetime.now(MALAYSIA_TZ)
    TOLERANCE_SECONDS = 120  # 2 minute window
    
    logger.info("Checking for time-based reminders...")

    # Check checkup bookings (weekc AND dayc REMINDERS)
    try:
        checkup_resp = supabase.table("c_s_checkup").select(
            "id, user_id, date, time, details, reminder_duration, reminder_remark, repeated_visit_uuid, doctor_id"
        ).gte("date", now.date().isoformat()).execute()
        
        logger.info(f"Fetched {len(checkup_resp.data or [])} bookings from c_s_checkup")
        
        for booking in checkup_resp.data or []:
            try:
                booking_time = (booking.get("time") or "00:00").zfill(5)
                booking_date = booking.get("date")
                if not booking_date:
                    continue
                    
                # Create booking datetime
                booking_dt = MALAYSIA_TZ.localize(
                    datetime.strptime(f"{booking_date} {booking_time}", "%Y-%m-%d %H:%M")
                )
                
                if booking_dt <= now:
                    continue

                # Determine booking details
                details = booking.get("details", "Appointment")
                remark = str(booking.get("reminder_remark") or "").strip()
                repeated_visit_uuid = booking.get("repeated_visit_uuid")
                
                # Get clinic_id for clinic booking
                clinic_id = get_clinic_id_for_booking(booking, "clinic")

                # Check standard time-based reminders (weekc and dayc)
                time_reminders = [
                    ("weekc", 168),  # 1 week = 168 hours
                    ("dayc", 24),    # 1 day = 24 hours
                ]
                
                for reminder_type, hours in time_reminders:
                    target_time = booking_dt - timedelta(hours=hours)
                    diff_seconds = abs((now - target_time).total_seconds())
                    
                    if diff_seconds <= TOLERANCE_SECONDS:
                        # Create appropriate message based on reminder type
                        if reminder_type == "weekc":
                            time_desc = gt_tt("+1234567890", "1 week", supabase)
                        elif reminder_type == "dayc":
                            time_desc = gt_tt("+1234567890", "1 day", supabase)
                        else:
                            time_desc = gt_tt("+1234567890", f"{hours} hours", supabase)
                        
                        # Single booking
                        notification_msg = gt_tt("+1234567890", f"Reminder: Your {details} is in ", supabase) + f"{time_desc}"
                        
                        if remark:
                            notification_msg += gt_tt("+1234567890", f" - {remark}", supabase)
                        
                        # Get user's WhatsApp number
                        user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", booking["user_id"]).execute()
                        if user_resp.data:
                            whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                            if whatsapp_number:
                                case_id = booking["id"]
                                
                                # Check if this reminder already exists and was sent
                                existing = supabase.table("c_notifications").select("id, sent").eq("user_id", booking["user_id"]).eq("case_id", case_id).eq("reminder_type", reminder_type).execute()
                                if existing.data:
                                    # Check if already sent
                                    for exist in existing.data:
                                        if exist.get("sent") == True:
                                            logger.info(f"Reminder already sent for booking {booking['id']}, type {reminder_type}. Skipping.")
                                            continue
                                        else:
                                            # Update existing unsent reminder
                                            logger.info(f"Updating existing unsent reminder for booking {booking['id']}")
                                            supabase.table("c_notifications").update({
                                                "notification": notification_msg,
                                                "time": datetime.now(MALAYSIA_TZ).isoformat(),
                                                "provider_cat": "clinic",
                                                "clinic_id": clinic_id
                                            }).eq("id", exist["id"]).execute()
                                            break
                                    else:
                                        # Insert new reminder
                                        insert_notification(
                                            whatsapp_number=whatsapp_number,
                                            case_id=case_id,
                                            message=notification_msg,
                                            user_id=booking["user_id"],
                                            reminder_type=reminder_type,
                                            provider_cat="clinic",
                                            clinic_id=clinic_id
                                        )
                                        logger.info(f"Created {reminder_type} reminder for {whatsapp_number}")
                                else:
                                    # Insert new reminder
                                    insert_notification(
                                        whatsapp_number=whatsapp_number,
                                        case_id=case_id,
                                        message=notification_msg,
                                        user_id=booking["user_id"],
                                        reminder_type=reminder_type,
                                        provider_cat="clinic",
                                        clinic_id=clinic_id
                                    )
                                    logger.info(f"Created {reminder_type} reminder for {whatsapp_number}")
                        
                        break  # Only create one reminder per booking

                # Check custom reminder (reminder_duration from booking) - now customc
                reminder_duration = booking.get("reminder_duration")
                if reminder_duration is not None:
                    target_time = booking_dt - timedelta(hours=reminder_duration)
                    diff_seconds = abs((now - target_time).total_seconds())
                    
                    if diff_seconds <= TOLERANCE_SECONDS:
                        # Single booking
                        notification_msg = gt_tt("+1234567890", f"Custom reminder: Your {details} is in ", supabase) + f"{reminder_duration} " + gt_tt("+1234567890", "hours", supabase)
                        
                        if remark:
                            notification_msg += gt_tt("+1234567890", f" - {remark}", supabase)
                        
                        # Get user's WhatsApp number
                        user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", booking["user_id"]).execute()
                        if user_resp.data:
                            whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                            if whatsapp_number:
                                case_id = booking["id"]
                                
                                # Insert with customc reminder_type
                                insert_notification(
                                    whatsapp_number=whatsapp_number,
                                    case_id=case_id,
                                    message=notification_msg,
                                    user_id=booking["user_id"],
                                    reminder_type="customc",
                                    provider_cat="clinic",
                                    clinic_id=clinic_id
                                )
                                logger.info(f"Created customc reminder for {whatsapp_number}")

            except Exception as e:
                logger.error(f"Error processing checkup booking {booking.get('id')}: {e}", exc_info=True)
                continue
                
    except Exception as e:
        logger.error(f"Failed to fetch c_s_checkup: {e}", exc_info=True)

    # Check consultation bookings (weekc AND dayc REMINDERS)
    try:
        consultation_resp = supabase.table("c_s_consultation").select(
            "id, user_id, date, time, details, reminder_duration, reminder_remark, repeated_visit_uuid, doctor_id"
        ).gte("date", now.date().isoformat()).execute()
        
        logger.info(f"Fetched {len(consultation_resp.data or [])} bookings from c_s_consultation")
        
        for booking in consultation_resp.data or []:
            try:
                booking_time = (booking.get("time") or "00:00").zfill(5)
                booking_date = booking.get("date")
                if not booking_date:
                    continue
                    
                # Create booking datetime
                booking_dt = MALAYSIA_TZ.localize(
                    datetime.strptime(f"{booking_date} {booking_time}", "%Y-%m-%d %H:%M")
                )
                
                if booking_dt <= now:
                    continue

                # Determine booking details
                details = booking.get("details", "Appointment")
                remark = str(booking.get("reminder_remark") or "").strip()
                repeated_visit_uuid = booking.get("repeated_visit_uuid")
                
                # Get clinic_id for clinic booking
                clinic_id = get_clinic_id_for_booking(booking, "clinic")

                # Check standard time-based reminders (weekc and dayc)
                time_reminders = [
                    ("weekc", 168),  # 1 week = 168 hours
                    ("dayc", 24),    # 1 day = 24 hours
                ]
                
                for reminder_type, hours in time_reminders:
                    target_time = booking_dt - timedelta(hours=hours)
                    diff_seconds = abs((now - target_time).total_seconds())
                    
                    if diff_seconds <= TOLERANCE_SECONDS:
                        # Create appropriate message based on reminder type
                        if reminder_type == "weekc":
                            time_desc = gt_tt("+1234567890", "1 week", supabase)
                        elif reminder_type == "dayc":
                            time_desc = gt_tt("+1234567890", "1 day", supabase)
                        else:
                            time_desc = gt_tt("+1234567890", f"{hours} hours", supabase)
                        
                        # Single booking
                        notification_msg = gt_tt("+1234567890", f"Reminder: Your {details} is in ", supabase) + f"{time_desc}"
                        
                        if remark:
                            notification_msg += gt_tt("+1234567890", f" - {remark}", supabase)
                        
                        # Get user's WhatsApp number
                        user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", booking["user_id"]).execute()
                        if user_resp.data:
                            whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                            if whatsapp_number:
                                case_id = booking["id"]
                                
                                # Check if this reminder already exists and was sent
                                existing = supabase.table("c_notifications").select("id, sent").eq("user_id", booking["user_id"]).eq("case_id", case_id).eq("reminder_type", reminder_type).execute()
                                if existing.data:
                                    # Check if already sent
                                    for exist in existing.data:
                                        if exist.get("sent") == True:
                                            logger.info(f"Reminder already sent for booking {booking['id']}, type {reminder_type}. Skipping.")
                                            continue
                                        else:
                                            # Update existing unsent reminder
                                            logger.info(f"Updating existing unsent reminder for booking {booking['id']}")
                                            supabase.table("c_notifications").update({
                                                "notification": notification_msg,
                                                "time": datetime.now(MALAYSIA_TZ).isoformat(),
                                                "provider_cat": "clinic",
                                                "clinic_id": clinic_id
                                            }).eq("id", exist["id"]).execute()
                                            break
                                    else:
                                        # Insert new reminder
                                        insert_notification(
                                            whatsapp_number=whatsapp_number,
                                            case_id=case_id,
                                            message=notification_msg,
                                            user_id=booking["user_id"],
                                            reminder_type=reminder_type,
                                            provider_cat="clinic",
                                            clinic_id=clinic_id
                                        )
                                        logger.info(f"Created {reminder_type} reminder for {whatsapp_number}")
                                else:
                                    # Insert new reminder
                                        insert_notification(
                                            whatsapp_number=whatsapp_number,
                                            case_id=case_id,
                                            message=notification_msg,
                                            user_id=booking["user_id"],
                                            reminder_type=reminder_type,
                                            provider_cat="clinic",
                                            clinic_id=clinic_id
                                        )
                                        logger.info(f"Created {reminder_type} reminder for {whatsapp_number}")
                        
                        break  # Only create one reminder per booking

                # Check custom reminder (reminder_duration from booking) - now customc
                reminder_duration = booking.get("reminder_duration")
                if reminder_duration is not None:
                    target_time = booking_dt - timedelta(hours=reminder_duration)
                    diff_seconds = abs((now - target_time).total_seconds())
                    
                    if diff_seconds <= TOLERANCE_SECONDS:
                        # Single booking
                        notification_msg = gt_tt("+1234567890", f"Custom reminder: Your {details} is in ", supabase) + f"{reminder_duration} " + gt_tt("+1234567890", "hours", supabase)
                        
                        if remark:
                            notification_msg += gt_tt("+1234567890", f" - {remark}", supabase)
                        
                        # Get user's WhatsApp number
                        user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", booking["user_id"]).execute()
                        if user_resp.data:
                            whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                            if whatsapp_number:
                                case_id = booking["id"]
                                
                                # Insert with customc reminder_type
                                insert_notification(
                                    whatsapp_number=whatsapp_number,
                                    case_id=case_id,
                                    message=notification_msg,
                                    user_id=booking["user_id"],
                                    reminder_type="customc",
                                    provider_cat="clinic",
                                    clinic_id=clinic_id
                                )
                                logger.info(f"Created customc reminder for {whatsapp_number}")

            except Exception as e:
                logger.error(f"Error processing consultation booking {booking.get('id')}: {e}", exc_info=True)
                continue
                
    except Exception as e:
        logger.error(f"Failed to fetch c_s_consultation: {e}", exc_info=True)

    # Check vaccination bookings (weekc AND dayc REMINDERS)
    try:
        vaccination_resp = supabase.table("c_s_vaccination").select(
            "id, user_id, date, time, vaccine_type, reminder_duration, reminder_remark, repeated_visit_uuid, doctor_id"
        ).gte("date", now.date().isoformat()).execute()
        
        logger.info(f"Fetched {len(vaccination_resp.data or [])} bookings from c_s_vaccination")
        
        for booking in vaccination_resp.data or []:
            try:
                booking_time = (booking.get("time") or "00:00").zfill(5)
                booking_date = booking.get("date")
                if not booking_date:
                    continue
                    
                # Create booking datetime
                booking_dt = MALAYSIA_TZ.localize(
                    datetime.strptime(f"{booking_date} {booking_time}", "%Y-%m-%d %H:%M")
                )
                
                if booking_dt <= now:
                    continue

                # Determine booking details - USE vaccine_type FOR VACCINATION
                details = booking.get("vaccine_type", "Vaccination")
                remark = str(booking.get("reminder_remark") or "").strip()
                repeated_visit_uuid = booking.get("repeated_visit_uuid")
                
                # Get clinic_id for clinic booking
                clinic_id = get_clinic_id_for_booking(booking, "clinic")

                # Check standard time-based reminders (weekc and dayc)
                time_reminders = [
                    ("weekc", 168),  # 1 week = 168 hours
                    ("dayc", 24),    # 1 day = 24 hours
                ]
                
                for reminder_type, hours in time_reminders:
                    target_time = booking_dt - timedelta(hours=hours)
                    diff_seconds = abs((now - target_time).total_seconds())
                    
                    if diff_seconds <= TOLERANCE_SECONDS:
                        # Create appropriate message based on reminder type
                        if reminder_type == "weekc":
                            time_desc = gt_tt("+1234567890", "1 week", supabase)
                        elif reminder_type == "dayc":
                            time_desc = gt_tt("+1234567890", "1 day", supabase)
                        else:
                            time_desc = gt_tt("+1234567890", f"{hours} hours", supabase)
                        
                        # Single booking
                        notification_msg = gt_tt("+1234567890", f"Reminder: Your {details} is in ", supabase) + f"{time_desc}"
                        
                        if remark:
                            notification_msg += gt_tt("+1234567890", f" - {remark}", supabase)
                        
                        # Get user's WhatsApp number
                        user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", booking["user_id"]).execute()
                        if user_resp.data:
                            whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                            if whatsapp_number:
                                case_id = booking["id"]
                                
                                # Check if this reminder already exists and was sent
                                existing = supabase.table("c_notifications").select("id, sent").eq("user_id", booking["user_id"]).eq("case_id", case_id).eq("reminder_type", reminder_type).execute()
                                if existing.data:
                                    # Check if already sent
                                    for exist in existing.data:
                                        if exist.get("sent") == True:
                                            logger.info(f"Reminder already sent for booking {booking['id']}, type {reminder_type}. Skipping.")
                                            continue
                                        else:
                                            # Update existing unsent reminder
                                            logger.info(f"Updating existing unsent reminder for booking {booking['id']}")
                                            supabase.table("c_notifications").update({
                                                "notification": notification_msg,
                                                "time": datetime.now(MALAYSIA_TZ).isoformat(),
                                                "provider_cat": "clinic",
                                                "clinic_id": clinic_id
                                            }).eq("id", exist["id"]).execute()
                                            break
                                    else:
                                        # Insert new reminder
                                        insert_notification(
                                            whatsapp_number=whatsapp_number,
                                            case_id=case_id,
                                            message=notification_msg,
                                            user_id=booking["user_id"],
                                            reminder_type=reminder_type,
                                            provider_cat="clinic",
                                            clinic_id=clinic_id
                                        )
                                        logger.info(f"Created {reminder_type} reminder for {whatsapp_number}")
                                else:
                                    # Insert new reminder
                                        insert_notification(
                                            whatsapp_number=whatsapp_number,
                                            case_id=case_id,
                                            message=notification_msg,
                                            user_id=booking["user_id"],
                                            reminder_type=reminder_type,
                                            provider_cat="clinic",
                                            clinic_id=clinic_id
                                        )
                                        logger.info(f"Created {reminder_type} reminder for {whatsapp_number}")
                        
                        break  # Only create one reminder per booking

                # Check custom reminder (reminder_duration from booking) - now customc
                reminder_duration = booking.get("reminder_duration")
                if reminder_duration is not None:
                    target_time = booking_dt - timedelta(hours=reminder_duration)
                    diff_seconds = abs((now - target_time).total_seconds())
                    
                    if diff_seconds <= TOLERANCE_SECONDS:
                        # Single booking
                        notification_msg = gt_tt("+1234567890", f"Custom reminder: Your {details} is in ", supabase) + f"{reminder_duration} " + gt_tt("+1234567890", "hours", supabase)
                        
                        if remark:
                            notification_msg += gt_tt("+1234567890", f" - {remark}", supabase)
                        
                        # Get user's WhatsApp number
                        user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", booking["user_id"]).execute()
                        if user_resp.data:
                            whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                            if whatsapp_number:
                                case_id = booking["id"]
                                
                                # Insert with customc reminder_type
                                insert_notification(
                                    whatsapp_number=whatsapp_number,
                                    case_id=case_id,
                                    message=notification_msg,
                                    user_id=booking["user_id"],
                                    reminder_type="customc",
                                    provider_cat="clinic",
                                    clinic_id=clinic_id
                                )
                                logger.info(f"Created customc reminder for {whatsapp_number}")

            except Exception as e:
                logger.error(f"Error processing vaccination booking {booking.get('id')}: {e}", exc_info=True)
                continue
                
    except Exception as e:
        logger.error(f"Failed to fetch c_s_vaccination: {e}", exc_info=True)

    # Check TCM bookings (weekc AND dayc REMINDERS)
    try:
        tcm_resp = supabase.table("tcm_s_bookings").select(
            "id, user_id, original_date, original_time, new_date, new_time, booking_type, details, reminder_duration, reminder_remark, repeated_visit_uuid, status, doctor_id"
        ).eq("status", "confirmed").execute()
        
        logger.info(f"Fetched {len(tcm_resp.data or [])} TCM bookings")
        
        for booking in tcm_resp.data or []:
            try:
                # Get appointment date and time (use new if available, otherwise original)
                booking_date = booking.get("new_date") or booking.get("original_date")
                booking_time = booking.get("new_time") or booking.get("original_time")
                
                if not booking_date or not booking_time:
                    continue
                    
                # Create booking datetime
                booking_dt = MALAYSIA_TZ.localize(
                    datetime.strptime(f"{booking_date} {booking_time}", "%Y-%m-%d %H:%M")
                )
                
                if booking_dt <= now:
                    continue

                # Determine booking details
                details = booking.get("details", "TCM Appointment")
                booking_type = booking.get("booking_type", "consultation")
                remark = str(booking.get("reminder_remark") or "").strip()
                repeated_visit_uuid = booking.get("repeated_visit_uuid")
                
                # Get clinic_id for TCM booking
                clinic_id = None
                try:
                    if booking.get("doctor_id"):
                        doctor_resp = supabase.table("tcm_a_doctors").select("clinic_id").eq("id", booking["doctor_id"]).execute()
                        if doctor_resp.data and doctor_resp.data[0].get("clinic_id"):
                            clinic_id = doctor_resp.data[0]["clinic_id"]
                except Exception as clinic_err:
                    logger.error(f"Error getting clinic_id for TCM reminder: {clinic_err}")

                # Check standard time-based reminders (weekc and dayc)
                time_reminders = [
                    ("weekc", 168),  # 1 week = 168 hours
                    ("dayc", 24),    # 1 day = 24 hours
                ]
                
                for reminder_type, hours in time_reminders:
                    target_time = booking_dt - timedelta(hours=hours)
                    diff_seconds = abs((now - target_time).total_seconds())
                    
                    if diff_seconds <= TOLERANCE_SECONDS:
                        # Create appropriate message based on reminder type
                        if reminder_type == "weekc":
                            time_desc = gt_tt("+1234567890", "1 week", supabase)
                        elif reminder_type == "dayc":
                            time_desc = gt_tt("+1234567890", "1 day", supabase)
                        else:
                            time_desc = gt_tt("+1234567890", f"{hours} hours", supabase)
                        
                        # Single booking
                        notification_msg = gt_tt("+1234567890", f"Reminder: Your TCM {booking_type} is in ", supabase) + f"{time_desc}"
                        
                        if remark:
                            notification_msg += gt_tt("+1234567890", f" - {remark}", supabase)
                        
                        # Get user's WhatsApp number
                        user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", booking["user_id"]).execute()
                        if user_resp.data:
                            whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                            if whatsapp_number:
                                case_id = booking["id"]
                                
                                # Check if this reminder already exists and was sent
                                existing = supabase.table("c_notifications").select("id, sent").eq("user_id", booking["user_id"]).eq("case_id", case_id).eq("reminder_type", reminder_type).execute()
                                if existing.data:
                                    # Check if already sent
                                    for exist in existing.data:
                                        if exist.get("sent") == True:
                                            logger.info(f"TCM reminder already sent for booking {booking['id']}, type {reminder_type}. Skipping.")
                                            continue
                                        else:
                                            # Update existing unsent reminder
                                            logger.info(f"Updating existing unsent TCM reminder for booking {booking['id']}")
                                            supabase.table("c_notifications").update({
                                                "notification": notification_msg,
                                                "time": datetime.now(MALAYSIA_TZ).isoformat(),
                                                "provider_cat": "tcm",
                                                "clinic_id": clinic_id
                                            }).eq("id", exist["id"]).execute()
                                            break
                                    else:
                                        # Insert new reminder
                                        insert_notification(
                                            whatsapp_number=whatsapp_number,
                                            case_id=case_id,
                                            message=notification_msg,
                                            user_id=booking["user_id"],
                                            reminder_type=reminder_type,
                                            provider_cat="tcm",
                                            clinic_id=clinic_id
                                        )
                                        logger.info(f"Created TCM {reminder_type} reminder for {whatsapp_number}")
                                else:
                                    # Insert new reminder
                                        insert_notification(
                                            whatsapp_number=whatsapp_number,
                                            case_id=case_id,
                                            message=notification_msg,
                                            user_id=booking["user_id"],
                                            reminder_type=reminder_type,
                                            provider_cat="tcm",
                                            clinic_id=clinic_id
                                        )
                                        logger.info(f"Created TCM {reminder_type} reminder for {whatsapp_number}")
                        
                        break  # Only create one reminder per booking

                # Check custom reminder (reminder_duration from booking) - now customc
                reminder_duration = booking.get("reminder_duration")
                if reminder_duration is not None:
                    target_time = booking_dt - timedelta(hours=reminder_duration)
                    diff_seconds = abs((now - target_time).total_seconds())
                    
                    if diff_seconds <= TOLERANCE_SECONDS:
                        # Single booking
                        notification_msg = gt_tt("+1234567890", f"Custom reminder: Your TCM {booking_type} is in ", supabase) + f"{reminder_duration} " + gt_tt("+1234567890", "hours", supabase)
                        
                        if remark:
                            notification_msg += gt_tt("+1234567890", f" - {remark}", supabase)
                        
                        # Get user's WhatsApp number
                        user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", booking["user_id"]).execute()
                        if user_resp.data:
                            whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                            if whatsapp_number:
                                case_id = booking["id"]
                                
                                # Insert with customc reminder_type
                                insert_notification(
                                    whatsapp_number=whatsapp_number,
                                    case_id=case_id,
                                    message=notification_msg,
                                    user_id=booking["user_id"],
                                    reminder_type="customc",
                                    provider_cat="tcm",
                                    clinic_id=clinic_id
                                )
                                logger.info(f"Created TCM customc reminder for {whatsapp_number}")

            except Exception as e:
                logger.error(f"Error processing TCM booking {booking.get('id')}: {e}", exc_info=True)
                continue
                
    except Exception as e:
        logger.error(f"Failed to fetch tcm_s_bookings: {e}", exc_info=True)

# -------------------------
# NEW: Check ambulance bookings for a_day reminders
# -------------------------
def check_and_send_ambulance_reminders(supabase):
    """
    Generate reminders 1 day before ambulance bookings.
    Sets reminder_type = a_day for the 4 ambulance tables.
    """
    now = datetime.now(MALAYSIA_TZ)
    TOLERANCE_SECONDS = 120  # 2 minute window
    
    logger.info("Checking for ambulance reminders (a_day)...")

    # List of ambulance tables to check
    ambulance_tables = [
        ("a_s_hometohome", "Home to Home Transfer"),
        ("a_s_hometohosp", "Home to Hospital Transfer"),
        ("a_s_hosptohome", "Hospital to Home Discharge"),
        ("a_s_hosptohosp", "Hospital to Hospital Transfer")
    ]
    
    for table_name, service_type in ambulance_tables:
        try:
            # Get bookings with scheduled_date in the future
            resp = supabase.table(table_name).select(
                "id, whatsapp_number, patient_name, scheduled_date, scheduled_time, provider_id"
            ).gte("scheduled_date", now.date().isoformat()).execute()
            
            logger.info(f"Fetched {len(resp.data or [])} bookings from {table_name}")
            
            for booking in resp.data or []:
                try:
                    scheduled_date = booking.get("scheduled_date")
                    scheduled_time = booking.get("scheduled_time", "00:00:00")
                    
                    if not scheduled_date:
                        continue
                        
                    # Create scheduled datetime
                    scheduled_dt = MALAYSIA_TZ.localize(
                        datetime.strptime(f"{scheduled_date} {scheduled_time}", "%Y-%m-%d %H:%M:%S")
                    )
                    
                    if scheduled_dt <= now:
                        continue
                    
                    whatsapp_number = booking.get("whatsapp_number", "").lstrip('+')
                    if not whatsapp_number:
                        continue
                    
                    # Get user ID
                    user_resp = supabase.table("whatsapp_users").select("id").eq("whatsapp_number", whatsapp_number).execute()
                    if not user_resp.data:
                        continue
                    
                    user_id = user_resp.data[0]["id"]
                    case_id = booking["id"]
                    
                    # Calculate 1 day before reminder
                    reminder_time = scheduled_dt - timedelta(days=1)
                    diff_seconds = abs((now - reminder_time).total_seconds())
                    
                    if diff_seconds <= TOLERANCE_SECONDS:
                        # Check if reminder already exists
                        existing = supabase.table("c_notifications").select("id, sent").eq("user_id", user_id).eq("case_id", case_id).eq("reminder_type", "a_day").execute()
                        if existing.data:
                            for exist in existing.data:
                                if exist.get("sent") == True:
                                    logger.info(f"Ambulance a_day reminder already sent for {case_id}. Skipping.")
                                    continue
                                else:
                                    # Update existing unsent reminder
                                    patient_name = booking.get("patient_name", "Patient")
                                    scheduled_str = scheduled_dt.strftime("%Y-%m-%d %H:%M")
                                    notification_msg = f"Reminder: Your {service_type} for {patient_name} is scheduled tomorrow at {scheduled_str}."
                                    
                                    supabase.table("c_notifications").update({
                                        "notification": notification_msg,
                                        "time": datetime.now(MALAYSIA_TZ).isoformat(),
                                        "provider_cat": "ambulance",
                                        "clinic_id": None
                                    }).eq("id", exist["id"]).execute()
                                    logger.info(f"Updated a_day reminder for ambulance booking {case_id}")
                                    break
                            else:
                                # Insert new reminder
                                patient_name = booking.get("patient_name", "Patient")
                                scheduled_str = scheduled_dt.strftime("%Y-%m-%d %H:%M")
                                notification_msg = f"Reminder: Your {service_type} for {patient_name} is scheduled tomorrow at {scheduled_str}."
                                
                                insert_notification(
                                    whatsapp_number=whatsapp_number,
                                    case_id=case_id,
                                    message=notification_msg,
                                    user_id=user_id,
                                    reminder_type="a_day",
                                    provider_cat="ambulance",
                                    clinic_id=None
                                )
                                logger.info(f"Created a_day reminder for {whatsapp_number}, ambulance booking {case_id}")
                        else:
                            # Insert new reminder
                            patient_name = booking.get("patient_name", "Patient")
                            scheduled_str = scheduled_dt.strftime("%Y-%m-%d %H:%M")
                            notification_msg = f"Reminder: Your {service_type} for {patient_name} is scheduled tomorrow at {scheduled_str}."
                            
                            insert_notification(
                                whatsapp_number=whatsapp_number,
                                case_id=case_id,
                                message=notification_msg,
                                user_id=user_id,
                                reminder_type="a_day",
                                provider_cat="ambulance",
                                clinic_id=None
                            )
                            logger.info(f"Created a_day reminder for {whatsapp_number}, ambulance booking {case_id}")
                            
                except Exception as e:
                    logger.error(f"Error processing ambulance booking {booking.get('id')} from {table_name}: {e}", exc_info=True)
                    continue
                    
        except Exception as e:
            logger.error(f"Failed to fetch from {table_name}: {e}", exc_info=True)
            continue