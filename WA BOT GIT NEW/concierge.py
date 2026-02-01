import logging
from sentence_transformers import SentenceTransformer
from supabase import Client
from utils import send_whatsapp_message, send_interactive_menu, translate_template, gt_tt
from google.cloud import translate_v2 as translate
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize SentenceTransformer model
model = SentenceTransformer('all-distilroberta-v1')

# Initialize Google Translate client
GOOGLE_KEY_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

if GOOGLE_KEY_PATH and os.path.exists(GOOGLE_KEY_PATH):
    try:
        from google.cloud import translate_v2 as translate
        translate_client = translate.Client.from_service_account_json(GOOGLE_KEY_PATH)
        logger.info(f"Google Translate client initialized with credentials from {GOOGLE_KEY_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize Google Translate client: {e}")
        translate_client = None
else:
    logger.warning("GOOGLE_APPLICATION_CREDENTIALS environment variable not set or file not found")
    logger.warning("Google Translate will use dictionary fallback only")
    translate_client = None

def translate_to_english(text: str) -> str:
    """Translate input text to English using Google Translate."""
    try:
        # Detect the language of the input text
        detection = translate_client.detect_language(text)
        detected_language = detection["language"]
        logger.info(f"Detected language: {detected_language} for input: {text}")

        # If the detected language is not English, translate to English
        if detected_language != "en":
            translation = translate_client.translate(
                text,
                target_language="en",
                source_language=detected_language
            )
            translated_text = translation["translatedText"]
            logger.info(f"Translated '{text}' ({detected_language}) to '{translated_text}' (en)")
            return translated_text
        return text
    except Exception as e:
        logger.error(f"Error translating text to English: {e}", exc_info=True)
        return text  # Fallback to original text if translation fails

def get_category_steps(whatsapp_number: str, category: str, supabase: Client) -> str:
    """Return step-by-step instructions for the matched category with translation."""
    # Define steps in English - they will be translated using translate_template
    steps_en = {
        "Notification": (
            "Steps for Notifications:\n"
            "1. Select Menu\n"
            "2. Select Notifications to view all notifications"
        ),
        "Change Language": (
            "Steps to Change Language:\n"
            "1. Select Menu\n"
            "2. Select Change Language\n"
            "3. Select preferred language"
        ),
        "General GP Visit": (
            "Steps for General GP Visit Booking:\n"
            "1. Select Menu\n"
            "2. Select Booking\n"
            "3. Select Booking Options\n"
            "4. Select General GP Options\n"
            "5. Type symptoms (e.g., Runny Nose)\n"
            "6. Select a doctor\n"
            "   a. If unsure, select Any Doctor\n"
            "7. Select a date\n"
            "8. Select an hour\n"
            "   a. Some slots may be unavailable, subject to doctor availability\n"
            "9. Click confirm and await approval\n"
            "10. Notification will be sent when doctor approves appointment - click on Menu -> Notification to view"
        ),
        "Health Check-Up and Tests": (
            "Steps for Check-Up and Test Booking:\n"
            "1. Select Menu\n"
            "2. Select Booking\n"
            "3. Select Booking Options\n"
            "4. Select Checkup & Test\n"
            "5. Select a checkup type (e.g., General Screening)\n"
            "6. Type remarks (e.g., For employment)\n"
            "7. Select a doctor\n"
            "   a. If unsure, select Any Doctor\n"
            "8. Select a date\n"
            "9. Select an hour\n"
            "   a. Some slots may be unavailable, subject to doctor availability\n"
            "10. Click confirm and await approval\n"
            "11. Notification will be sent when doctor approves appointment - click on Menu -> Notification to view"
        ),
        "Vaccination": (
            "Steps for Vaccination Booking:\n"
            "1. Select Menu\n"
            "2. Select Booking\n"
            "3. Select Booking Options\n"
            "4. Select Vaccination\n"
            "5. Select a Vaccination type (e.g., COVID Vaccine)\n"
            "6. Type remarks (e.g., Booster)\n"
            "7. Select a doctor\n"
            "   a. If unsure, select Any Doctor\n"
            "8. Select a date\n"
            "9. Select an hour\n"
            "   a. Some slots may be unavailable, subject to doctor availability\n"
            "10. Click confirm and await approval\n"
            "11. Notification will be sent when doctor approves appointment - click on Menu -> Notification to view"
        ),
        "Report Result Consultation": (
            "Steps for Report Result Consultation:\n"
            "1. Notification informs you that your test result has been released\n"
            "2. Click Menu\n"
            "3. Select Booking\n"
            "4. Select Report Result Booking\n"
            "5. Select Report (e.g., Booking 1) that appears\n"
            "6. Select Yes if you have any remarks for the doctor (e.g., Result is for university)\n"
            "7. Select date for consult\n"
            "8. Select time (hour)\n"
            "9. Select slot\n"
            "10. Click confirm and await approval\n"
            "11. Notification will be sent when doctor approves appointment - click on Menu -> Notification to view"
        ),
        "View Past Booking History": (
            "Steps to View Previous Booking Reports:\n"
            "1. Click Menu\n"
            "2. Select Booking\n"
            "3. Select View Past Consultations"
        ),
        "View Upcoming Bookings": (
            "Steps to View Upcoming Appointments:\n"
            "1. Click Menu\n"
            "2. Select Booking\n"
            "3. Select View Upcoming Bookings\n"
            "4. On the screen are Confirmed bookings and Pending Bookings\n"
            "   a. Confirmed bookings: doctor has approved and added to their calendar\n"
            "   b. Pending Bookings: awaiting doctor confirmation\n"
            "   Please allow 3 hours for doctor to confirm your booking."
        ),
        "Accept/Reject Reschedule": (
            "Steps to Accept or Reject Rescheduled Appointment:\n"
            "1. Select Menu\n"
            "2. Select Booking\n"
            "3. Select Reschedule Booking\n"
            "4. Select Choose Category\n"
            "5. Select Action Required\n"
            "6. Select the booking as required\n"
            "7. Click Accept if the timing is suitable\n"
            "   a. Booking is confirmed\n"
            "8. Click Decline if the timing is not suitable\n"
            "   a. Booking will be removed"
        ),
        "Reschedule Confirmed Booking - tgt": (
            "Steps to Reschedule a Confirmed Booking:\n"
            "1. Notification informs you that your test result has been released\n"
            "2. Select Menu\n"
            "3. Select Booking\n"
            "4. Select Reschedule\n"
            "5. Click Confirmed\n"
            "6. Select Booking you wish to reschedule\n"
            "7. Select Reschedule\n"
            "8. Select new date\n"
            "9. Select new time\n"
            "10. Await Doctor Approval"
        ),
        "Cancel Confirmed Booking - tgt": (
            "Steps to Cancel a Confirmed Booking:\n"
            "1. Notification informs you that your test result has been released\n"
            "2. Select Menu\n"
            "3. Select Booking\n"
            "4. Select Reschedule\n"
            "5. Click Confirmed\n"
            "6. Select Booking you wish to reschedule\n"
            "7. Select Cancel\n"
            "8. Your booking has been cancelled"
        ),
        "Reschedule/Cancel Pending Booking": (
            "Steps to Reschedule or Cancel a Pending Booking:\n"
            "1. Select Menu\n"
            "2. Select Booking\n"
            "3. Select Reschedule\n"
            "4. Click Pending\n"
            "5. Select Booking you wish to reschedule or cancel\n"
            "6. To Reschedule:\n"
            "   a. Select Reschedule\n"
            "   b. Select new date\n"
            "   c. Select new time\n"
            "   d. Await Doctor Approval\n"
            "7. To Cancel:\n"
            "   a. Select Cancel\n"
            "   b. Your booking has been cancelled"
        )
    }
    
    # Get the English steps
    english_steps = steps_en.get(category, "No specific steps available for this category.")
    
    # Translate the steps using translate_template
    translated_steps = translate_template(whatsapp_number, english_steps, supabase)
    
    return translated_steps

def query_concierge_vector(user_input: str, supabase: Client) -> str:
    """Transform user input to vector and find the closest matching category."""
    try:
        # Translate user input to English
        english_input = translate_to_english(user_input)
        
        # Generate embedding for the English input
        user_embedding = model.encode(english_input).tolist()
        
        # Query Supabase for the closest match using vector similarity (cosine similarity)
        response = supabase.rpc("match_concierge_vectors", {
            "query_embedding": user_embedding,
            "match_threshold": 0.3,
            "match_count": 3
        }).execute()
        
        if response.data and len(response.data) > 0:
            # Log all returned matches with their similarity scores
            for match in response.data:
                logger.info(f"Match: category={match['category']}, similarity={match['similarity']:.4f}, description={match['description'][:50]}...")
            matched_category = response.data[0]["category"]
            logger.info(f"Selected category: {matched_category} for input: {user_input} (translated: {english_input})")
            return matched_category
        else:
            logger.info(f"No match found for input: {user_input} (translated: {english_input}), defaulting to Live Agent")
            return "Live Agent"
    except Exception as e:
        logger.error(f"Error querying concierge vector: {e}", exc_info=True)
        return "Live Agent"

def handle_concierge_input(whatsapp_number: str, user_id: str, supabase: Client, user_data: dict, message: dict) -> bool:
    """Handle user input for concierge query and return the matched category with steps."""
    try:
        user_input = message["text"]["body"].strip()
        logger.info(f"Processing concierge input from {whatsapp_number}: {user_input}")
        
        # Query vector database
        matched_category = query_concierge_vector(user_input, supabase)
        
        # If matched category is not one of the valid categories, return to main menu
        valid_categories = {
            "Notification", "Change Language", "General GP Visit", "Health Check-Up and Tests",
            "Vaccination", "Report Result Consultation", "View Past Booking History",
            "View Upcoming Bookings", "Accept/Reject Reschedule",
            "Reschedule Confirmed Booking - tgt", "Cancel Confirmed Booking - tgt",
            "Reschedule/Cancel Pending Booking"
        }
        if matched_category not in valid_categories:
            response_text = gt_tt(whatsapp_number, "Please Talk to Clinic Frontdesk in Bookings > Clinic Enquiries", supabase)
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": response_text}},
                supabase
            )
            user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
            supabase.table("whatsapp_users").update({"state": "IDLE"}).eq("id", user_id).execute()
            send_interactive_menu(whatsapp_number, supabase)
            return False

        # Get step-by-step instructions for the matched category WITH TRANSLATION
        steps = get_category_steps(whatsapp_number, matched_category, supabase)
        
        # Translate the category name
        translated_category = translate_template(whatsapp_number, matched_category, supabase)
        
        # Create the FULL response text and then translate it
        full_response_en = f"Your query is related to: {matched_category}\n\n{steps}\n\nPlease select the appropriate option from the main menu to proceed."
        
        # Translate the entire response
        response_text = translate_template(whatsapp_number, full_response_en, supabase)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": response_text}},
            supabase
        )
        
        # Reset state and return to main menu
        user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
        try:
            supabase.table("whatsapp_users").update({
                "state": "IDLE"
            }).eq("id", user_id).execute()
            logger.info(f"Updated user state for {whatsapp_number} to IDLE")
        except Exception as e:
            logger.warning(f"Failed to update user state for {whatsapp_number}: {e}")
            # Continue without crashing, as state is updated in user_data
        send_interactive_menu(whatsapp_number, supabase)
        return True
    except Exception as e:
        logger.error(f"Error handling concierge input for {whatsapp_number}: {e}", exc_info=True)
        response_text = translate_template(
            whatsapp_number,
            "An error occurred. Please try again.",
            supabase
        )
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": response_text}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
        try:
            supabase.table("whatsapp_users").update({
                "state": "IDLE"
            }).eq("id", user_id).execute()
            logger.info(f"Updated user state for {whatsapp_number} to IDLE after error")
        except Exception as e:
            logger.warning(f"Failed to update user state after error for {whatsapp_number}: {e}")
        send_interactive_menu(whatsapp_number, supabase)
        return False

def send_concierge_prompt(whatsapp_number: str, supabase: Client) -> bool:
    """Send a prompt to the user to enter their query."""
    prompt_message = translate_template(
        whatsapp_number,
        "Please type what you need help with, and I'll guide you to the right option.",
        supabase
    )
    return send_whatsapp_message(
        whatsapp_number,
        "text",
        {"text": {"body": prompt_message}},
        supabase
    )