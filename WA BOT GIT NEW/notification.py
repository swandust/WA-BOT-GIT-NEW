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
                        logger.info(translate_template("+1234567890", "Notification already sent for user {user_id}, case {case_id}, type {reminder_type}. Skipping.", supabase).format(
                            user_id=user_id, case_id=case_id, reminder_type=reminder_type))
                        return {"data": [{"id": existing["id"]}]}
                    else:
                        logger.info(translate_template("+1234567890", "Notification exists but not sent. Will send: user {user_id}, case {case_id}, type {reminder_type}", supabase).format(
                            user_id=user_id, case_id=case_id, reminder_type=reminder_type))
                        return {"data": [{"id": existing["id"]}]}
        except Exception as check_error:
            logger.warning(translate_template("+1234567890", "Error checking existing notification: {check_error}", supabase).format(check_error=str(check_error)))
        
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

        logger.info(translate_template("+1234567890", "Inserting notification: user_id={user_id}, case_id={case_id}, reminder_type={reminder_type}, provider_cat={provider_cat}, clinic_id={clinic_id}", supabase).format(
            user_id=user_id, case_id=case_id, reminder_type=reminder_type, provider_cat=provider_cat, clinic_id=clinic_id))

        response = supabase.table("c_notifications").insert(data).execute()
        logger.info(translate_template("+1234567890", "Successfully inserted notification for user {user_id}, case {case_id}, type {reminder_type}", supabase).format(
            user_id=user_id, case_id=case_id, reminder_type=reminder_type))
        return response

    except Exception as e:
        if "unique_notification" in str(e).lower() or "duplicate key" in str(e).lower() or "409" in str(e):
            logger.debug(translate_template("+1234567890", "Duplicate notification skipped (user {user_id}, case {case_id}, type {reminder_type})", supabase).format(
                user_id=user_id, case_id=case_id, reminder_type=reminder_type))
            return {"data": [{"id": "duplicate_" + str(uuid.uuid4())}]}
        else:
            logger.error(translate_template("+1234567890", "Error inserting notification for user {user_id}, case {case_id}: {error}", supabase).format(
                user_id=user_id, case_id=case_id, error=str(e)), exc_info=True)
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
        logger.error(translate_template("+1234567890", "Error getting clinic_id for booking: {error}", supabase).format(error=str(e)))
    
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
            
            logger.info(translate_template("+1234567890", "Found {count} new bookings in c_s_checkup", supabase).format(count=len(checkup_resp.data or [])))
            
            for booking in checkup_resp.data or []:
                try:
                    user_id = booking["user_id"]
                    repeated_visit_uuid = booking.get("repeated_visit_uuid")
                    
                    # Get user's WhatsApp number
                    user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", user_id).execute()
                    if not user_resp.data:
                        logger.error(translate_template("+1234567890", "No user found for user_id {user_id}", supabase).format(user_id=user_id))
                        continue
                        
                    whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                    if not whatsapp_number:
                        logger.error(translate_template("+1234567890", "No WhatsApp number for user_id {user_id}", supabase).format(user_id=user_id))
                        continue
                    
                    # Get clinic_id for clinic booking
                    clinic_id = get_clinic_id_for_booking(booking, "clinic")
                    
                    # Check if notification already exists for this booking
                    existing = supabase.table("c_notifications").select("id").eq("user_id", user_id).eq("case_id", booking["id"]).eq("reminder_type", "confirm").execute()
                    if existing.data:
                        logger.info(translate_template(whatsapp_number, "Notification already exists for booking {booking_id}. Skipping.", supabase).format(booking_id=booking['id']))
                        continue
                    
                    # Single booking - create individual notification
                    booking_date = booking.get("date")
                    booking_time = booking.get("time")
                    
                    # Get booking details
                    details = booking.get("details", "Checkup")
                    template = "Your checkup booking is confirmed on {date} at {time}."
                    notification_msg = gt_tt(whatsapp_number, template, supabase).format(
                        date=booking_date,
                        time=booking_time
                    )
                    
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
                    logger.info(translate_template(whatsapp_number, "Created single checkup notification for {whatsapp_number}, booking {booking_id}", supabase).format(
                        whatsapp_number=whatsapp_number, booking_id=booking['id']))
                        
                except Exception as e:
                    logger.error(translate_template("+1234567890", "Error processing checkup booking {booking_id}: {error}", supabase).format(
                        booking_id=booking.get('id'), error=str(e)), exc_info=True)
                    continue
                    
        except Exception as e:
            logger.error(translate_template("+1234567890", "Error fetching from c_s_checkup: {error}", supabase).format(error=str(e)), exc_info=True)
        
        # Check consultation bookings - UPDATED with doctor_id
        try:
            consultation_resp = supabase.table("c_s_consultation").select(
                "id, user_id, date, time, details, repeated_visit_uuid, created_at, doctor_id"
            ).gte("created_at", one_hour_ago).execute()
            
            logger.info(translate_template("+1234567890", "Found {count} new bookings in c_s_consultation", supabase).format(count=len(consultation_resp.data or [])))
            
            for booking in consultation_resp.data or []:
                try:
                    user_id = booking["user_id"]
                    repeated_visit_uuid = booking.get("repeated_visit_uuid")
                    
                    # Get user's WhatsApp number
                    user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", user_id).execute()
                    if not user_resp.data:
                        logger.error(translate_template("+1234567890", "No user found for user_id {user_id}", supabase).format(user_id=user_id))
                        continue
                        
                    whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                    if not whatsapp_number:
                        logger.error(translate_template("+1234567890", "No WhatsApp number for user_id {user_id}", supabase).format(user_id=user_id))
                        continue
                    
                    # Get clinic_id for clinic booking
                    clinic_id = get_clinic_id_for_booking(booking, "clinic")
                    
                    # Check if notification already exists for this booking
                    existing = supabase.table("c_notifications").select("id").eq("user_id", user_id).eq("case_id", booking["id"]).eq("reminder_type", "confirm").execute()
                    if existing.data:
                        logger.info(translate_template(whatsapp_number, "Notification already exists for booking {booking_id}. Skipping.", supabase).format(booking_id=booking['id']))
                        continue
                    
                    # Single booking - create individual notification
                    booking_date = booking.get("date")
                    booking_time = booking.get("time")
                    
                    # Get booking details
                    details = booking.get("details", "Consultation")
                    template = "Your consultation booking is confirmed on {date} at {time}."
                    notification_msg = gt_tt(whatsapp_number, template, supabase).format(
                        date=booking_date,
                        time=booking_time
                    )
                    
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
                    logger.info(translate_template(whatsapp_number, "Created single consultation notification for {whatsapp_number}, booking {booking_id}", supabase).format(
                        whatsapp_number=whatsapp_number, booking_id=booking['id']))
                        
                except Exception as e:
                    logger.error(translate_template("+1234567890", "Error processing consultation booking {booking_id}: {error}", supabase).format(
                        booking_id=booking.get('id'), error=str(e)), exc_info=True)
                    continue
                    
        except Exception as e:
            logger.error(translate_template("+1234567890", "Error fetching from c_s_consultation: {error}", supabase).format(error=str(e)), exc_info=True)
        
        # Check vaccination bookings (USING vaccine_type INSTEAD OF details) - UPDATED with doctor_id
        try:
            vaccination_resp = supabase.table("c_s_vaccination").select(
                "id, user_id, date, time, vaccine_type, repeated_visit_uuid, created_at, doctor_id"
            ).gte("created_at", one_hour_ago).execute()
            
            logger.info(translate_template("+1234567890", "Found {count} new bookings in c_s_vaccination", supabase).format(count=len(vaccination_resp.data or [])))
            
            for booking in vaccination_resp.data or []:
                try:
                    user_id = booking["user_id"]
                    repeated_visit_uuid = booking.get("repeated_visit_uuid")
                    
                    # Get user's WhatsApp number
                    user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", user_id).execute()
                    if not user_resp.data:
                        logger.error(translate_template("+1234567890", "No user found for user_id {user_id}", supabase).format(user_id=user_id))
                        continue
                        
                    whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                    if not whatsapp_number:
                        logger.error(translate_template("+1234567890", "No WhatsApp number for user_id {user_id}", supabase).format(user_id=user_id))
                        continue
                    
                    # Get clinic_id for clinic booking
                    clinic_id = get_clinic_id_for_booking(booking, "clinic")
                    
                    # Check if notification already exists for this booking
                    existing = supabase.table("c_notifications").select("id").eq("user_id", user_id).eq("case_id", booking["id"]).eq("reminder_type", "confirm").execute()
                    if existing.data:
                        logger.info(translate_template(whatsapp_number, "Notification already exists for booking {booking_id}. Skipping.", supabase).format(booking_id=booking['id']))
                        continue
                    
                    # Single booking - create individual notification
                    booking_date = booking.get("date")
                    booking_time = booking.get("time")
                    
                    # Get booking details - USE vaccine_type FOR VACCINATION
                    details = booking.get("vaccine_type", "Vaccination")
                    translated_vaccine = gt_tt(whatsapp_number, details, supabase)
                    template = "Your vaccination booking for {vaccine_type} is confirmed on {date} at {time}."
                    notification_msg = gt_tt(whatsapp_number, template, supabase).format(
                        vaccine_type=translated_vaccine,
                        date=booking_date,
                        time=booking_time
                    )
                    
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
                    logger.info(translate_template(whatsapp_number, "Created single vaccination notification for {whatsapp_number}, booking {booking_id}", supabase).format(
                        whatsapp_number=whatsapp_number, booking_id=booking['id']))
                        
                except Exception as e:
                    logger.error(translate_template("+1234567890", "Error processing vaccination booking {booking_id}: {error}", supabase).format(
                        booking_id=booking.get('id'), error=str(e)), exc_info=True)
                    continue
                    
        except Exception as e:
            logger.error(translate_template("+1234567890", "Error fetching from c_s_vaccination: {error}", supabase).format(error=str(e)), exc_info=True)

        # Check TCM bookings
        try:
            tcm_resp = supabase.table("tcm_s_bookings").select(
                "id, user_id, original_date, original_time, new_date, new_time, booking_type, details, repeated_visit_uuid, created_at, status, doctor_id"
            ).gte("created_at", one_hour_ago).eq("status", "confirmed").execute()
            
            logger.info(translate_template("+1234567890", "Found {count} new TCM bookings", supabase).format(count=len(tcm_resp.data or [])))
            
            for booking in tcm_resp.data or []:
                try:
                    user_id = booking["user_id"]
                    repeated_visit_uuid = booking.get("repeated_visit_uuid")
                    
                    # Get user's WhatsApp number
                    user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", user_id).execute()
                    if not user_resp.data:
                        logger.error(translate_template("+1234567890", "No user found for user_id {user_id}", supabase).format(user_id=user_id))
                        continue
                        
                    whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                    if not whatsapp_number:
                        logger.error(translate_template("+1234567890", "No WhatsApp number for user_id {user_id}", supabase).format(user_id=user_id))
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
                        logger.error(translate_template("+1234567890", "Error getting clinic_id for TCM booking: {error}", supabase).format(error=str(clinic_err)))
                    
                    # Check if notification already exists for this booking
                    case_id_to_check = repeated_visit_uuid if repeated_visit_uuid else booking["id"]
                    
                    existing = supabase.table("c_notifications").select("id").eq("user_id", user_id).eq("case_id", case_id_to_check).eq("reminder_type", "confirm").execute()
                    if existing.data:
                        logger.info(translate_template(whatsapp_number, "Notification already exists for TCM booking {booking_id}. Skipping.", supabase).format(booking_id=booking['id']))
                        continue
                    
                    # Get appointment date and time (use new if available, otherwise original)
                    booking_date = booking.get("new_date") or booking.get("original_date")
                    booking_time = booking.get("new_time") or booking.get("original_time")
                    
                    # Single booking - create individual notification
                    details = booking.get("details", "TCM Consultation")
                    booking_type = booking.get("booking_type", "consultation")
                    translated_type = gt_tt(whatsapp_number, booking_type, supabase)
                    template = "Your TCM {booking_type} booking is confirmed on {date} at {time}."
                    notification_msg = gt_tt(whatsapp_number, template, supabase).format(
                        booking_type=translated_type,
                        date=booking_date,
                        time=booking_time
                    )
                    
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
                    logger.info(translate_template(whatsapp_number, "Created single TCM notification for {whatsapp_number}, booking {booking_id}", supabase).format(
                        whatsapp_number=whatsapp_number, booking_id=booking['id']))
                        
                except Exception as e:
                    logger.error(translate_template("+1234567890", "Error processing TCM booking {booking_id}: {error}", supabase).format(
                        booking_id=booking.get('id'), error=str(e)), exc_info=True)
                    continue
                    
        except Exception as e:
            logger.error(translate_template("+1234567890", "Error fetching from tcm_s_bookings: {error}", supabase).format(error=str(e)), exc_info=True)
    except Exception as e:
        logger.error(translate_template("+1234567890", "Error fetching from tcm_s_bookings: {error}", supabase).format(error=str(e)), exc_info=True)

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
                
                logger.info(translate_template("+1234567890", "Found {count} new bookings in {table_name}", supabase).format(
                    count=len(resp.data or []), table_name=table_name))
                
                for booking in resp.data or []:
                    try:
                        whatsapp_number = booking.get("whatsapp_number", "").lstrip('+')
                        if not whatsapp_number:
                            continue
                        
                        # Get user ID from whatsapp_users table
                        user_resp = supabase.table("whatsapp_users").select("id").eq("whatsapp_number", whatsapp_number).execute()
                        if not user_resp.data:
                            logger.error(translate_template(whatsapp_number, "No user found for WhatsApp number {whatsapp_number}", supabase).format(
                                whatsapp_number=whatsapp_number))
                            continue
                        
                        user_id = user_resp.data[0]["id"]
                        case_id = booking["id"]
                        
                        # Check if notification already exists
                        existing = supabase.table("c_notifications").select("id").eq("user_id", user_id).eq("case_id", case_id).eq("reminder_type", "a_day").execute()
                        if existing.data:
                            logger.info(translate_template(whatsapp_number, "Notification already exists for ambulance booking {case_id}. Skipping.", supabase).format(
                                case_id=case_id))
                            continue
                        
                        # Create notification message
                        patient_name = booking.get("patient_name", "Patient")
                        scheduled_date = booking.get("scheduled_date", "N/A")
                        scheduled_time = booking.get("scheduled_time", "N/A")
                        
                        notification_msg = gt_tt(whatsapp_number, f"Your {service_type} for {patient_name} is scheduled on ", supabase) + f"{scheduled_date} at {scheduled_time}."
                        
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
                        logger.info(translate_template(whatsapp_number, "Created a_day notification for {whatsapp_number}, booking {case_id}", supabase).format(
                            whatsapp_number=whatsapp_number, case_id=case_id))
                        
                    except Exception as e:
                        logger.error(translate_template("+1234567890", "Error processing ambulance booking {booking_id} from {table_name}: {error}", supabase).format(
                            booking_id=booking.get('id'), table_name=table_name, error=str(e)), exc_info=True)
                        continue
                        
            except Exception as e:
                logger.error(translate_template("+1234567890", "Error fetching from {table_name}: {error}", supabase).format(
                    table_name=table_name, error=str(e)), exc_info=True)
                continue
                
    except Exception as e:
        logger.error(translate_template("+1234567890", "Error in check_and_send_ambulance_notifications: {error}", supabase).format(error=str(e)), exc_info=True)

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
            
            logger.info(translate_template("+1234567890", "Found {count} TCM bookings from last 24 hours", supabase).format(
                count=len(tcm_resp.data or [])))
            
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
                        logger.error(translate_template("+1234567890", "Error getting clinic_id for TCM booking: {error}", supabase).format(error=str(clinic_err)))
                    
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
                    logger.info(translate_template(whatsapp_number, "Created immediate TCM notification for {whatsapp_number}, booking {booking_id}", supabase).format(
                        whatsapp_number=whatsapp_number, booking_id=booking['id']))
                        
                except Exception as e:
                    logger.error(translate_template("+1234567890", "Error processing immediate TCM booking {booking_id}: {error}", supabase).format(
                        booking_id=booking.get('id'), error=str(e)))
                    continue
                    
        except Exception as e:
            logger.error(translate_template("+1234567890", "Error in immediate TCM confirmations: {error}", supabase).format(error=str(e)))
            
        # Also check ambulance bookings from last 24 hours
        logger.info(translate_template("+1234567890", "=== Running immediate ambulance notifications ===", supabase))
        check_and_send_ambulance_notifications(supabase)
            
    except Exception as e:
        logger.error(translate_template("+1234567890", "Error in send_immediate_booking_confirmations: {error}", supabase).format(error=str(e)), exc_info=True)

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
            
            logger.info(translate_template("+1234567890", "Found {count} total unsent notifications to process (last 24 hours)", supabase).format(
                count=len(resp.data or [])))
            
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
                        logger.debug(translate_template("+1234567890", "Skipping notification {notification_id} - processed recently", supabase).format(
                            notification_id=notification_id))
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
                    logger.warning(translate_template("+1234567890", "No notifications were marked for processing (already being processed?)", supabase))
                    return
                    
            except Exception as e:
                logger.error(translate_template("+1234567890", "Error marking notifications for processing: {error}", supabase).format(error=str(e)))
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
                    logger.debug(translate_template("+1234567890", "Throttling notification for {wnum} - last sent {time_diff:.1f}s ago", supabase).format(
                        wnum=wnum, time_diff=now - last_time))
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
                logger.info(translate_template("+1234567890", "Processing notification {notification_id} for {wnum}, type: {reminder_type}, provider_cat: {provider_cat}, clinic_id: {clinic_id}", supabase).format(
                    notification_id=notification_id, wnum=wnum, reminder_type=reminder_type, provider_cat=provider_cat, clinic_id=clinic_id))
                
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
                        logger.info(translate_template("+1234567890", "Successfully sent notification {notification_id} for {wnum} with reminder_type: {reminder_type}", supabase).format(
                            notification_id=notification_id, wnum=wnum, reminder_type=reminder_type))
                    else:
                        logger.error(translate_template("+1234567890", "Failed to send notification {notification_id} to {wnum} (all methods failed)", supabase).format(
                            notification_id=notification_id, wnum=wnum))
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
                    logger.error(translate_template("+1234567890", "Error sending notification {notification_id} to {wnum}: {error}", supabase).format(
                        notification_id=notification_id, wnum=wnum, error=str(e)), exc_info=True)
                    # Mark as not sent for retry
                    try:
                        supabase.table("c_notifications").update({
                            "sent": False
                        }).eq("id", notification_id).execute()
                    except:
                        pass
                    processed_notification_ids[notification_id] = now

    except Exception as e:
        logger.error(translate_template("+1234567890", "Error in process_notifications: {error}", supabase).format(error=str(e)), exc_info=True)
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
                logger.warning(translate_template(whatsapp_number, "No user found for {whatsapp_number}", supabase).format(whatsapp_number=whatsapp_number))
                return False
        
        user_id = user_resp.data.get("id")
        
        # Update all notifications for this user that are sent but not seen
        update_result = supabase.table("c_notifications").update({
            "seen": True
        }).eq("user_id", user_id).eq("sent", True).eq("seen", False).execute()
        
        if update_result.data:
            logger.info(translate_template("+1234567890", "Updated seen status for {count} notifications for user {user_id}", supabase).format(
                count=len(update_result.data), user_id=user_id))
            return True
        else:
            logger.info(translate_template("+1234567890", "No notifications to mark as seen for user {user_id}", supabase).format(user_id=user_id))
            return False
            
    except Exception as e:
        logger.error(translate_template("+1234567890", "Error updating notification seen status for {whatsapp_number}: {error}", supabase).format(
            whatsapp_number=whatsapp_number, error=str(e)), exc_info=True)
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
        logger.error(translate_template("+1234567890", "Error handling notification noted: {error}", supabase).format(error=str(e)))
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
                logger.warning(translate_template("+1234567890", "Error parsing notification time {time}: {error}", supabase).format(
                    time=t, error=str(e)))
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
                logger.info(translate_template("+1234567890", "Marked {count} notifications as prompted for user {user_id}", supabase).format(
                    count=len(notification_ids), user_id=user_id))
            else:
                logger.error(translate_template("+1234567890", "Failed to mark notifications as prompted for user {user_id}", supabase).format(
                    user_id=user_id))

        # Send confirmation message
        send_free_notification(whatsapp_number, translate_template(whatsapp_number, "{count} notification(s) displayed!", supabase).format(
            count=len(message_parts)), supabase)
        send_interactive_menu(whatsapp_number, supabase)

    except Exception as e:
        logger.error(translate_template("+1234567890", "Error in display_and_clear_notifications for {whatsapp_number}: {error}", supabase).format(
            whatsapp_number=whatsapp_number, error=str(e)), exc_info=True)
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
        logger.error(translate_template("+1234567890", "Error fetching language for {whatsapp_number}: {error}", supabase).format(
            whatsapp_number=whatsapp_number, error=str(e)))
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
    
    logger.info(translate_template("+1234567890", "Checking for time-based reminders...", supabase))

    # Check checkup bookings (weekc AND dayc REMINDERS)
    try:
        checkup_resp = supabase.table("c_s_checkup").select(
            "id, user_id, date, time, details, reminder_duration, reminder_remark, repeated_visit_uuid, doctor_id"
        ).gte("date", now.date().isoformat()).execute()
        
        logger.info(translate_template("+1234567890", "Fetched {count} bookings from c_s_checkup", supabase).format(
            count=len(checkup_resp.data or [])))
        
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
                        user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", booking["user_id"]).execute()
                        if user_resp.data:
                            whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                            if whatsapp_number:
                                translated_details = gt_tt(whatsapp_number, details, supabase)
                                if reminder_type == "weekc":
                                    time_desc_source = "1 week"
                                elif reminder_type == "dayc":
                                    time_desc_source = "1 day"
                                else:
                                    time_desc_source = f"{hours} hours"
                                
                                translated_time_desc = gt_tt(whatsapp_number, time_desc_source, supabase)
                                template = "Reminder: Your {details} is in {time_desc}"
                                notification_msg = gt_tt(whatsapp_number, template, supabase).format(
                                    details=translated_details,
                                    time_desc=translated_time_desc
                                )
                                
                                if remark:
                                    notification_msg += gt_tt(whatsapp_number, f" - {remark}", supabase)
                                
                                case_id = booking["id"]
                                
                                # Check if this reminder already exists and was sent
                                existing = supabase.table("c_notifications").select("id, sent").eq("user_id", booking["user_id"]).eq("case_id", case_id).eq("reminder_type", reminder_type).execute()
                                if existing.data:
                                    # Check if already sent
                                    for exist in existing.data:
                                        if exist.get("sent") == True:
                                            logger.info(translate_template("+1234567890", "Reminder already sent for booking {booking_id}, type {reminder_type}. Skipping.", supabase).format(
                                                booking_id=booking['id'], reminder_type=reminder_type))
                                            continue
                                        else:
                                            # Update existing unsent reminder
                                            logger.info(translate_template("+1234567890", "Updating existing unsent reminder for booking {booking_id}", supabase).format(
                                                booking_id=booking['id']))
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
                                        logger.info(translate_template("+1234567890", "Created {reminder_type} reminder for {whatsapp_number}", supabase).format(
                                            reminder_type=reminder_type, whatsapp_number=whatsapp_number))
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
                                        logger.info(translate_template("+1234567890", "Created {reminder_type} reminder for {whatsapp_number}", supabase).format(
                                            reminder_type=reminder_type, whatsapp_number=whatsapp_number))
                        
                        break  # Only create one reminder per booking

                # Check custom reminder (reminder_duration from booking) - now customc
                reminder_duration = booking.get("reminder_duration")
                if reminder_duration is not None:
                    target_time = booking_dt - timedelta(hours=reminder_duration)
                    diff_seconds = abs((now - target_time).total_seconds())
                    
                    if diff_seconds <= TOLERANCE_SECONDS:
                        user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", booking["user_id"]).execute()
                        if user_resp.data:
                            whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                            if whatsapp_number:
                                translated_details = gt_tt(whatsapp_number, details, supabase)
                                template = "Custom reminder: Your {details} is in {reminder_duration} hours"
                                notification_msg = gt_tt(whatsapp_number, template, supabase).format(
                                    details=translated_details,
                                    reminder_duration=reminder_duration
                                )
                                
                                if remark:
                                    notification_msg += gt_tt(whatsapp_number, f" - {remark}", supabase)
                                
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
                                logger.info(translate_template("+1234567890", "Created customc reminder for {whatsapp_number}", supabase).format(
                                    whatsapp_number=whatsapp_number))

            except Exception as e:
                logger.error(translate_template("+1234567890", "Error processing checkup booking {booking_id}: {error}", supabase).format(
                    booking_id=booking.get('id'), error=str(e)), exc_info=True)
                continue
                
    except Exception as e:
        logger.error(translate_template("+1234567890", "Failed to fetch c_s_checkup: {error}", supabase).format(error=str(e)), exc_info=True)

    # Check consultation bookings (weekc AND dayc REMINDERS)
    try:
        consultation_resp = supabase.table("c_s_consultation").select(
            "id, user_id, date, time, details, reminder_duration, reminder_remark, repeated_visit_uuid, doctor_id"
        ).gte("date", now.date().isoformat()).execute()
        
        logger.info(translate_template("+1234567890", "Fetched {count} bookings from c_s_consultation", supabase).format(
            count=len(consultation_resp.data or [])))
        
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
                        user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", booking["user_id"]).execute()
                        if user_resp.data:
                            whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                            if whatsapp_number:
                                translated_details = gt_tt(whatsapp_number, details, supabase)
                                if reminder_type == "weekc":
                                    time_desc_source = "1 week"
                                elif reminder_type == "dayc":
                                    time_desc_source = "1 day"
                                else:
                                    time_desc_source = f"{hours} hours"
                                
                                translated_time_desc = gt_tt(whatsapp_number, time_desc_source, supabase)
                                template = "Reminder: Your {details} is in {time_desc}"
                                notification_msg = gt_tt(whatsapp_number, template, supabase).format(
                                    details=translated_details,
                                    time_desc=translated_time_desc
                                )
                                
                                if remark:
                                    notification_msg += gt_tt(whatsapp_number, f" - {remark}", supabase)
                                
                                case_id = booking["id"]
                                
                                # Check if this reminder already exists and was sent
                                existing = supabase.table("c_notifications").select("id, sent").eq("user_id", booking["user_id"]).eq("case_id", case_id).eq("reminder_type", reminder_type).execute()
                                if existing.data:
                                    # Check if already sent
                                    for exist in existing.data:
                                        if exist.get("sent") == True:
                                            logger.info(translate_template("+1234567890", "Reminder already sent for booking {booking_id}, type {reminder_type}. Skipping.", supabase).format(
                                                booking_id=booking['id'], reminder_type=reminder_type))
                                            continue
                                        else:
                                            # Update existing unsent reminder
                                            logger.info(translate_template("+1234567890", "Updating existing unsent reminder for booking {booking_id}", supabase).format(
                                                booking_id=booking['id']))
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
                                        logger.info(translate_template("+1234567890", "Created {reminder_type} reminder for {whatsapp_number}", supabase).format(
                                            reminder_type=reminder_type, whatsapp_number=whatsapp_number))
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
                                        logger.info(translate_template("+1234567890", "Created {reminder_type} reminder for {whatsapp_number}", supabase).format(
                                            reminder_type=reminder_type, whatsapp_number=whatsapp_number))
                        
                        break  # Only create one reminder per booking

                # Check custom reminder (reminder_duration from booking) - now customc
                reminder_duration = booking.get("reminder_duration")
                if reminder_duration is not None:
                    target_time = booking_dt - timedelta(hours=reminder_duration)
                    diff_seconds = abs((now - target_time).total_seconds())
                    
                    if diff_seconds <= TOLERANCE_SECONDS:
                        user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", booking["user_id"]).execute()
                        if user_resp.data:
                            whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                            if whatsapp_number:
                                translated_details = gt_tt(whatsapp_number, details, supabase)
                                template = "Custom reminder: Your {details} is in {reminder_duration} hours"
                                notification_msg = gt_tt(whatsapp_number, template, supabase).format(
                                    details=translated_details,
                                    reminder_duration=reminder_duration
                                )
                                
                                if remark:
                                    notification_msg += gt_tt(whatsapp_number, f" - {remark}", supabase)
                                
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
                                logger.info(translate_template("+1234567890", "Created customc reminder for {whatsapp_number}", supabase).format(
                                    whatsapp_number=whatsapp_number))

            except Exception as e:
                logger.error(translate_template("+1234567890", "Error processing consultation booking {booking_id}: {error}", supabase).format(
                    booking_id=booking.get('id'), error=str(e)), exc_info=True)
                continue
                
    except Exception as e:
        logger.error(translate_template("+1234567890", "Failed to fetch c_s_consultation: {error}", supabase).format(error=str(e)), exc_info=True)

    # Check vaccination bookings (weekc AND dayc REMINDERS)
    try:
        vaccination_resp = supabase.table("c_s_vaccination").select(
            "id, user_id, date, time, vaccine_type, reminder_duration, reminder_remark, repeated_visit_uuid, doctor_id"
        ).gte("date", now.date().isoformat()).execute()
        
        logger.info(translate_template("+1234567890", "Fetched {count} bookings from c_s_vaccination", supabase).format(
            count=len(vaccination_resp.data or [])))
        
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
                        user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", booking["user_id"]).execute()
                        if user_resp.data:
                            whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                            if whatsapp_number:
                                translated_details = gt_tt(whatsapp_number, details, supabase)
                                if reminder_type == "weekc":
                                    time_desc_source = "1 week"
                                elif reminder_type == "dayc":
                                    time_desc_source = "1 day"
                                else:
                                    time_desc_source = f"{hours} hours"
                                
                                translated_time_desc = gt_tt(whatsapp_number, time_desc_source, supabase)
                                template = "Reminder: Your {details} is in {time_desc}"
                                notification_msg = gt_tt(whatsapp_number, template, supabase).format(
                                    details=translated_details,
                                    time_desc=translated_time_desc
                                )
                                
                                if remark:
                                    notification_msg += gt_tt(whatsapp_number, f" - {remark}", supabase)
                                
                                case_id = booking["id"]
                                
                                # Check if this reminder already exists and was sent
                                existing = supabase.table("c_notifications").select("id, sent").eq("user_id", booking["user_id"]).eq("case_id", case_id).eq("reminder_type", reminder_type).execute()
                                if existing.data:
                                    # Check if already sent
                                    for exist in existing.data:
                                        if exist.get("sent") == True:
                                            logger.info(translate_template("+1234567890", "Reminder already sent for booking {booking_id}, type {reminder_type}. Skipping.", supabase).format(
                                                booking_id=booking['id'], reminder_type=reminder_type))
                                            continue
                                        else:
                                            # Update existing unsent reminder
                                            logger.info(translate_template("+1234567890", "Updating existing unsent reminder for booking {booking_id}", supabase).format(
                                                booking_id=booking['id']))
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
                                        logger.info(translate_template("+1234567890", "Created {reminder_type} reminder for {whatsapp_number}", supabase).format(
                                            reminder_type=reminder_type, whatsapp_number=whatsapp_number))
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
                                        logger.info(translate_template("+1234567890", "Created {reminder_type} reminder for {whatsapp_number}", supabase).format(
                                            reminder_type=reminder_type, whatsapp_number=whatsapp_number))
                        
                        break  # Only create one reminder per booking

                # Check custom reminder (reminder_duration from booking) - now customc
                reminder_duration = booking.get("reminder_duration")
                if reminder_duration is not None:
                    target_time = booking_dt - timedelta(hours=reminder_duration)
                    diff_seconds = abs((now - target_time).total_seconds())
                    
                    if diff_seconds <= TOLERANCE_SECONDS:
                        user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", booking["user_id"]).execute()
                        if user_resp.data:
                            whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                            if whatsapp_number:
                                translated_details = gt_tt(whatsapp_number, details, supabase)
                                template = "Custom reminder: Your {details} is in {reminder_duration} hours"
                                notification_msg = gt_tt(whatsapp_number, template, supabase).format(
                                    details=translated_details,
                                    reminder_duration=reminder_duration
                                )
                                
                                if remark:
                                    notification_msg += gt_tt(whatsapp_number, f" - {remark}", supabase)
                                
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
                                logger.info(translate_template("+1234567890", "Created customc reminder for {whatsapp_number}", supabase).format(
                                    whatsapp_number=whatsapp_number))

            except Exception as e:
                logger.error(translate_template("+1234567890", "Error processing vaccination booking {booking_id}: {error}", supabase).format(
                    booking_id=booking.get('id'), error=str(e)), exc_info=True)
                continue
                
    except Exception as e:
        logger.error(translate_template("+1234567890", "Failed to fetch c_s_vaccination: {error}", supabase).format(error=str(e)), exc_info=True)

    # Check TCM bookings (weekc AND dayc REMINDERS)
    try:
        tcm_resp = supabase.table("tcm_s_bookings").select(
            "id, user_id, original_date, original_time, new_date, new_time, booking_type, details, reminder_duration, reminder_remark, repeated_visit_uuid, status, doctor_id"
        ).eq("status", "confirmed").execute()
        
        logger.info(translate_template("+1234567890", "Fetched {count} TCM bookings", supabase).format(count=len(tcm_resp.data or [])))
        
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
                    logger.error(translate_template("+1234567890", "Error getting clinic_id for TCM reminder: {error}", supabase).format(error=str(clinic_err)))

                # Check standard time-based reminders (weekc and dayc)
                time_reminders = [
                    ("weekc", 168),  # 1 week = 168 hours
                    ("dayc", 24),    # 1 day = 24 hours
                ]
                
                for reminder_type, hours in time_reminders:
                    target_time = booking_dt - timedelta(hours=hours)
                    diff_seconds = abs((now - target_time).total_seconds())
                    
                    if diff_seconds <= TOLERANCE_SECONDS:
                        user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", booking["user_id"]).execute()
                        if user_resp.data:
                            whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                            if whatsapp_number:
                                translated_booking_type = gt_tt(whatsapp_number, booking_type, supabase)
                                if reminder_type == "weekc":
                                    time_desc_source = "1 week"
                                elif reminder_type == "dayc":
                                    time_desc_source = "1 day"
                                else:
                                    time_desc_source = f"{hours} hours"
                                
                                translated_time_desc = gt_tt(whatsapp_number, time_desc_source, supabase)
                                template = "Reminder: Your TCM {booking_type} is in {time_desc}"
                                notification_msg = gt_tt(whatsapp_number, template, supabase).format(
                                    booking_type=translated_booking_type,
                                    time_desc=translated_time_desc
                                )
                                
                                if remark:
                                    notification_msg += gt_tt(whatsapp_number, f" - {remark}", supabase)
                                
                                case_id = booking["id"]
                                
                                # Check if this reminder already exists and was sent
                                existing = supabase.table("c_notifications").select("id, sent").eq("user_id", booking["user_id"]).eq("case_id", case_id).eq("reminder_type", reminder_type).execute()
                                if existing.data:
                                    # Check if already sent
                                    for exist in existing.data:
                                        if exist.get("sent") == True:
                                            logger.info(translate_template("+1234567890", "TCM reminder already sent for booking {booking_id}, type {reminder_type}. Skipping.", supabase).format(
                                                booking_id=booking['id'], reminder_type=reminder_type))
                                            continue
                                        else:
                                            # Update existing unsent reminder
                                            logger.info(translate_template("+1234567890", "Updating existing unsent TCM reminder for booking {booking_id}", supabase).format(
                                                booking_id=booking['id']))
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
                                        logger.info(translate_template("+1234567890", "Created TCM {reminder_type} reminder for {whatsapp_number}", supabase).format(
                                            reminder_type=reminder_type, whatsapp_number=whatsapp_number))
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
                                        logger.info(translate_template("+1234567890", "Created TCM {reminder_type} reminder for {whatsapp_number}", supabase).format(
                                            reminder_type=reminder_type, whatsapp_number=whatsapp_number))
                        
                        break  # Only create one reminder per booking

                # Check custom reminder (reminder_duration from booking) - now customc
                reminder_duration = booking.get("reminder_duration")
                if reminder_duration is not None:
                    target_time = booking_dt - timedelta(hours=reminder_duration)
                    diff_seconds = abs((now - target_time).total_seconds())
                    
                    if diff_seconds <= TOLERANCE_SECONDS:
                        user_resp = supabase.table("whatsapp_users").select("whatsapp_number").eq("id", booking["user_id"]).execute()
                        if user_resp.data:
                            whatsapp_number = user_resp.data[0].get("whatsapp_number", "").lstrip('+')
                            if whatsapp_number:
                                translated_booking_type = gt_tt(whatsapp_number, booking_type, supabase)
                                template = "Custom reminder: Your TCM {booking_type} is in {reminder_duration} hours"
                                notification_msg = gt_tt(whatsapp_number, template, supabase).format(
                                    booking_type=translated_booking_type,
                                    reminder_duration=reminder_duration
                                )
                                
                                if remark:
                                    notification_msg += gt_tt(whatsapp_number, f" - {remark}", supabase)
                                
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
                                logger.info(translate_template("+1234567890", "Created TCM customc reminder for {whatsapp_number}", supabase).format(
                                    whatsapp_number=whatsapp_number))

            except Exception as e:
                logger.error(translate_template("+1234567890", "Error processing TCM booking {booking_id}: {error}", supabase).format(
                    booking_id=booking.get('id'), error=str(e)), exc_info=True)
                continue
                
    except Exception as e:
        logger.error(translate_template("+1234567890", "Failed to fetch tcm_s_bookings: {error}", supabase).format(error=str(e)), exc_info=True)

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
    
    logger.info(translate_template("+1234567890", "Checking for ambulance reminders (a_day)...", supabase))

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
            
            logger.info(translate_template("+1234567890", "Fetched {count} bookings from {table_name}", supabase).format(
                count=len(resp.data or []), table_name=table_name))
            
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
                                    logger.info(translate_template("+1234567890", "Ambulance a_day reminder already sent for {case_id}. Skipping.", supabase).format(case_id=case_id))
                                    continue
                                else:
                                    # Update existing unsent reminder
                                    patient_name = booking.get("patient_name", "Patient")
                                    scheduled_time_str = scheduled_dt.strftime("%H:%M")
                                    translated_service = gt_tt(whatsapp_number, service_type, supabase)
                                    template = "Reminder: Your {service_type} for {patient_name} is scheduled tomorrow at {time}."
                                    notification_msg = gt_tt(whatsapp_number, template, supabase).format(
                                        service_type=translated_service,
                                        patient_name=patient_name,
                                        time=scheduled_time_str
                                    )
                                    
                                    supabase.table("c_notifications").update({
                                        "notification": notification_msg,
                                        "time": datetime.now(MALAYSIA_TZ).isoformat(),
                                        "provider_cat": "ambulance",
                                        "clinic_id": None
                                    }).eq("id", exist["id"]).execute()
                                    logger.info(translate_template("+1234567890", "Updated a_day reminder for ambulance booking {case_id}", supabase).format(case_id=case_id))
                                    break
                            else:
                                # Insert new reminder
                                patient_name = booking.get("patient_name", "Patient")
                                scheduled_time_str = scheduled_dt.strftime("%H:%M")
                                translated_service = gt_tt(whatsapp_number, service_type, supabase)
                                template = "Reminder: Your {service_type} for {patient_name} is scheduled tomorrow at {time}."
                                notification_msg = gt_tt(whatsapp_number, template, supabase).format(
                                    service_type=translated_service,
                                    patient_name=patient_name,
                                    time=scheduled_time_str
                                )
                                
                                insert_notification(
                                    whatsapp_number=whatsapp_number,
                                    case_id=case_id,
                                    message=notification_msg,
                                    user_id=user_id,
                                    reminder_type="a_day",
                                    provider_cat="ambulance",
                                    clinic_id=None
                                )
                                logger.info(translate_template("+1234567890", "Created a_day reminder for {whatsapp_number}, ambulance booking {case_id}", supabase).format(
                                    whatsapp_number=whatsapp_number, case_id=case_id))
                        else:
                            # Insert new reminder
                            patient_name = booking.get("patient_name", "Patient")
                            scheduled_time_str = scheduled_dt.strftime("%H:%M")
                            translated_service = gt_tt(whatsapp_number, service_type, supabase)
                            template = "Reminder: Your {service_type} for {patient_name} is scheduled tomorrow at {time}."
                            notification_msg = gt_tt(whatsapp_number, template, supabase).format(
                                service_type=translated_service,
                                patient_name=patient_name,
                                time=scheduled_time_str
                            )
                            
                            insert_notification(
                                whatsapp_number=whatsapp_number,
                                case_id=case_id,
                                message=notification_msg,
                                user_id=user_id,
                                reminder_type="a_day",
                                provider_cat="ambulance",
                                clinic_id=None
                            )
                            logger.info(translate_template("+1234567890", "Created a_day reminder for {whatsapp_number}, ambulance booking {case_id}", supabase).format(
                                whatsapp_number=whatsapp_number, case_id=case_id))
                            
                except Exception as e:
                    logger.error(translate_template("+1234567890", "Error processing ambulance booking {booking_id} from {table_name}: {error}", supabase).format(
                        booking_id=booking.get('id'), table_name=table_name, error=str(e)), exc_info=True)
                    continue
                    
        except Exception as e:
            logger.error(translate_template("+1234567890", "Failed to fetch from {table_name}: {error}", supabase).format(
                table_name=table_name, error=str(e)), exc_info=True)
            continue
