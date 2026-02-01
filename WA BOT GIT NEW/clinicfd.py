import logging
import numpy as np
from sentence_transformers import SentenceTransformer
from utils import send_whatsapp_message, gt_tt, gt_t_tt, send_interactive_menu, send_booking_submenu
from google.cloud import translate_v2 as translate
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load the sentence transformer model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Initialize Google Translate client
GOOGLE_KEY_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "translate-test-475614-bdbe71e8b47b.json")
try:
    translate_client = translate.Client.from_service_account_json(GOOGLE_KEY_PATH)
except Exception as e:
    logger.warning(f"Google Translate client failed to initialize: {e}. Falling back to no translation.")
    translate_client = None

def translate_to_english(text: str) -> str:
    """Translate non-English text to English before embedding."""
    if not translate_client or not text.strip():
        return text
    try:
        detection = translate_client.detect_language(text)
        lang = detection.get("language", "")
        if lang == "en":
            return text
        translation = translate_client.translate(text, target_language="en")
        translated = translation["translatedText"]
        logger.info(f"Translated '{text}' ({lang}) to '{translated}'")
        return translated
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        return text

class ClinicServiceMatcher:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.services = []
        self.service_vectors = {}  # service_id -> vector array
       
    def load_services(self):
        """Load all active services and their vectors from Supabase"""
        try:
            response = self.supabase.table('c_a_clinic_service') \
                .select('*') \
                .eq('is_active', True) \
                .execute()
           
            if response.data:
                self.services = response.data
                logger.info(f"Loaded {len(self.services)} active services")
            else:
                logger.warning("No services found")
                self.services = []
            
            service_ids = [s['id'] for s in self.services]
            if service_ids:
                vector_response = self.supabase.table('c_service_vectors') \
                    .select('service_id, vector') \
                    .in_('service_id', service_ids) \
                    .execute()
                
                if vector_response.data:
                    self.service_vectors = {v['service_id']: np.array(v['vector']) for v in vector_response.data}
                    logger.info(f"Loaded vectors for {len(self.service_vectors)} services")
                else:
                    logger.warning("No vectors found")
               
        except Exception as e:
            logger.error(f"Error loading services and vectors: {e}")
            self.services = []
            self.service_vectors = {}
   
    def find_matching_services(self, user_input, top_k=1, min_score=0.1, category=None):
        """Find matching services based on user input using vector search"""
        if not self.services:
            self.load_services()
       
        if not user_input.strip():
            return []
       
        # Translate input to English before encoding
        english_input = translate_to_english(user_input)
        query_vector = model.encode(english_input)
       
        filtered_services = [s for s in self.services if not category or s.get('category') == category]
        scored_services = []
       
        for service in filtered_services:
            service_id = service['id']
            if service_id not in self.service_vectors:
                continue
            
            service_vector = self.service_vectors[service_id]
            score = np.dot(query_vector, service_vector) / (np.linalg.norm(query_vector) * np.linalg.norm(service_vector))
           
            if score >= min_score:
                scored_services.append({
                    **service,
                    'similarity_score': score
                })
       
        scored_services.sort(key=lambda x: x['similarity_score'], reverse=True)
        return scored_services[:top_k]
   
    def format_results(self, matches, user_input, whatsapp_number, supabase):
        """Format results with FULL translation of ALL fields and perfect spacing"""
        if not matches:
            return gt_tt(whatsapp_number, "I couldn't find any services matching your needs. Please try describing your health concerns differently.", supabase)
       
        # Header
        header = gt_tt(whatsapp_number, '🔍 Here\'s the top matching service for "{}":\n\n', supabase).format(user_input)
        result = [header]
       
        for match in matches:
            # Translate ALL fields from Supabase
            service_name = gt_tt(whatsapp_number, match['service_name'], supabase)
            category = gt_tt(whatsapp_number, match['category'], supabase)
            duration_min = gt_tt(whatsapp_number, "minutes", supabase)
            desc = match.get('description')
            if desc:
                desc = gt_tt(whatsapp_number, desc, supabase)
                if len(desc) > 100:
                    desc = desc[:100] + '...'

            # Labels
            label_category = gt_tt(whatsapp_number, "Category:", supabase)
            label_duration = gt_tt(whatsapp_number, "Duration:", supabase)
            label_desc = gt_tt(whatsapp_number, "Description:", supabase) if desc else ""

            # Build with correct spacing
            result.append(f"**{service_name}**\n")
            result.append(f" Category: {category}\n")
            result.append(f" Duration: {match['duration_minutes']} {duration_min}\n")
            if desc:
                result.append(f" {desc}\n")
            result.append("\n")  # Extra line between services

        # Footer
        footer = gt_tt(whatsapp_number, "Reply with the number to get more details or book this service!", supabase)
        result.append(footer)
       
        return "".join(result)

# Global matcher instance
service_matcher = None

def initialize_matcher(supabase_client):
    """Initialize the service matcher (call this once at startup)"""
    global service_matcher
    logger.info("Initializing Clinic Service Matcher...")
    service_matcher = ClinicServiceMatcher(supabase_client)
    service_matcher.load_services()
    logger.info("Service matcher ready!")

def find_services(user_input, whatsapp_number, supabase, top_k=1, category=None):
    """Main function to find matching services"""
    try:
        if service_matcher is None:
            return gt_tt(whatsapp_number, "Service matcher is not initialized. Please try again later.", supabase)
       
        matches = service_matcher.find_matching_services(user_input, top_k, category=category)
        return service_matcher.format_results(matches, user_input, whatsapp_number, supabase)
   
    except Exception as e:
        return gt_tt(whatsapp_number, f"Sorry, I encountered an error while searching: {str(e)}", supabase)

def handle_clinic_enquiries(whatsapp_number: str, user_id: str, supabase, user_data: dict):
    """Handle clinic enquiries entry point"""
    try:
        # --- FIX STARTS HERE ---
        # 1. Get the clinic_id dynamically from user_data
        clinic_id = user_data[whatsapp_number].get("clinic_id")

        # 2. Safety check: If no clinic is selected (e.g. session restart), fallback to default or error
        if not clinic_id:
            logger.warning(f"No clinic_id in user_data for {whatsapp_number}, using default/fallback")
            # You can set a default here if you want, or show an error
            # For now, let's try to grab the default one from your previous logs if you want, 
            # OR just return an error asking them to select a clinic first.
            
            # Option A: Return error and send back to clinic selection
            msg = gt_tt(whatsapp_number, "Please select a clinic first from the main menu.", supabase)
            send_whatsapp_message(whatsapp_number, "text", {"text": {"body": msg}})
            from menu import send_clinic_selection_menu
            send_clinic_selection_menu(whatsapp_number, supabase)
            return

        # 3. Query using the DYNAMIC clinic_id
        response = supabase.table("c_a_clinics").select("phone_number, name").eq("id", clinic_id).limit(1).execute()
        # --- FIX ENDS HERE ---
      
        if not response.data:
            msg = gt_tt(whatsapp_number, "Sorry, clinic information is not available at the moment.", supabase)
            send_whatsapp_message(whatsapp_number, "text", {"text": {"body": msg}})
            user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return

        clinic = response.data[0]
        # Handle cases where phone number might be None
        raw_phone = clinic.get("phone_number", "")
        if raw_phone:
            clinic_phone = raw_phone.lstrip("+").strip()
            wa_link = f"https://wa.me/{clinic_phone}?text=Hi,+referred+from+AnyHealth"
        else:
            wa_link = "https://wa.me/" # Fallback if no phone number

        clinic_name = clinic["name"]
      
        header_text = gt_t_tt(whatsapp_number, "Clinic Enquiries", supabase)
        body_text = gt_tt(whatsapp_number, "How would you like to get assistance for {clinic_name}?", supabase).format(clinic_name=clinic_name)
        footer_text = gt_t_tt(whatsapp_number, "Choose an option below", supabase)
        button_ai_text = gt_t_tt(whatsapp_number, "AI Service Finder", supabase)
        button_frontdesk_text = gt_t_tt(whatsapp_number, "Talk to Front Desk", supabase)
        button_cancel_text = gt_t_tt(whatsapp_number, "Cancel", supabase)
      
        content = {
            "interactive": {
                "type": "button",
                "header": {"type": "text", "text": header_text},
                "body": {"text": body_text},
                "footer": {"text": footer_text},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "ai_service_finder", "title": button_ai_text}},
                        {"type": "reply", "reply": {"id": "contact_frontdesk", "title": button_frontdesk_text}},
                        {"type": "reply", "reply": {"id": "cancel_enquiry", "title": button_cancel_text}}
                    ]
                }
            }
        }
      
        success = send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
      
        if success:
            user_data[whatsapp_number] = {
                "state": "CLINIC_ENQUIRIES_CHOICE",
                "processing": False,
                "module": "clinic_enquiries",
                "wa_link": wa_link,
                "clinic_name": clinic_name,
                "clinic_id": clinic_id # Keep the ID in state
            }
        else:
            error_msg = gt_tt(whatsapp_number, "Error sending clinic information. Please try again.", supabase)
            send_whatsapp_message(whatsapp_number, "text", {"text": {"body": error_msg}})
            user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
            send_interactive_menu(whatsapp_number, supabase)
      
    except Exception as e:
        logger.error(f"Error handling clinic enquiries: {e}", exc_info=True)
        error_msg = gt_tt(whatsapp_number, "An error occurred. Please try again.", supabase)
        send_whatsapp_message(whatsapp_number, "text", {"text": {"body": error_msg}})
        user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
        send_interactive_menu(whatsapp_number, supabase)

def handle_ai_service_finder(whatsapp_number: str, user_id: str, supabase, user_data: dict):
    """Prompt user with perfect spacing — translate line-by-line"""
    try:
        # English source lines (exact spacing preserved)
        lines = [
            "AI Service Finder",
            "I can help you find the right medical services!",
            "",
            "Please describe:",
            "• What health concerns you have",
            "• What tests or checkups you need",
            "• Your health goals",
            "",
            "Examples:",
            "• “I need diabetes screening”",
            "• “Heart health checkup”",
            "• “Blood test and vaccination”",
            "• “Annual medical checkup”",
            "",
            "Type your health needs below:"
        ]

        # Translate each line separately
        translated_lines = [
            gt_tt(whatsapp_number, line, supabase) if line.strip() else ""
            for line in lines
        ]
        welcome_text = "\n".join(translated_lines)

        send_whatsapp_message(whatsapp_number, "text", {"text": {"body": welcome_text}})

        user_data[whatsapp_number] = {
            "state": "AI_SERVICE_FINDER_INPUT",
            "processing": False,
            "module": "clinic_enquiries",
            "clinic_name": user_data.get(whatsapp_number, {}).get("clinic_name", "the clinic"),
            "wa_link": user_data.get(whatsapp_number, {}).get("wa_link")
        }

        logger.info(f"AI Service Finder activated for {whatsapp_number}")

    except Exception as e:
        logger.error(f"Error in AI service finder: {e}")
        error_msg = gt_tt(whatsapp_number, "Sorry, I encountered an error. Please try again.", supabase)
        send_whatsapp_message(whatsapp_number, "text", {"text": {"body": error_msg}})
        user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
        send_interactive_menu(whatsapp_number, supabase)


def handle_ai_service_input(whatsapp_number: str, user_input: str, supabase, user_data: dict):
    """Process AI search input and show results + follow-up"""
    try:
        # Processing message
        processing_msg = gt_tt(whatsapp_number, "Searching for services matching your needs...", supabase)
        send_whatsapp_message(whatsapp_number, "text", {"text": {"body": processing_msg}})

        # Run search
        category = user_data.get(whatsapp_number, {}).get('enquiry_category')
        nlp_results = find_services(user_input, whatsapp_number, supabase, top_k=1, category=category)
        send_whatsapp_message(whatsapp_number, "text", {"text": {"body": nlp_results}})

        # Follow-up prompt — line-by-line translation
        followup_lines = [
            "What would you like to do next?",
            "",
            "• Search for other services",
            "• Talk to front desk for more details",
            "• Cancel"
        ]
        translated_followup = "\n".join(
            gt_tt(whatsapp_number, line, supabase) if line.strip() else ""
            for line in followup_lines
        )

        content = {
            "interactive": {
                "type": "button",
                "body": {"text": translated_followup},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "ai_search_again", "title": gt_t_tt(whatsapp_number, "Search Again", supabase)}},
                        {"type": "reply", "reply": {"id": "contact_frontdesk", "title": gt_t_tt(whatsapp_number, "Front Desk", supabase)}},
                        {"type": "reply", "reply": {"id": "cancel_enquiry", "title": gt_t_tt(whatsapp_number, "Cancel", supabase)}}
                    ]
                }
            }
        }

        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)

        user_data[whatsapp_number] = {
            "state": "AI_SERVICE_FOLLOWUP",
            "processing": False,
            "module": "clinic_enquiries",
            "last_search": user_input,
            "wa_link": user_data.get(whatsapp_number, {}).get("wa_link"),
            "clinic_name": user_data.get(whatsapp_number, {}).get("clinic_name")
        }

    except Exception as e:
        logger.error(f"Error in AI service input: {e}")
        error_msg = gt_tt(whatsapp_number, "Sorry, I encountered an error while searching. Please try again or contact our front desk.", supabase)
        send_whatsapp_message(whatsapp_number, "text", {"text": {"body": error_msg}})
        user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
        send_interactive_menu(whatsapp_number, supabase)

def handle_clinic_enquiries_response(whatsapp_number: str, response_id: str, user_id: str, supabase, user_data: dict):
    """Handle all button responses"""
    try:
        if response_id == "ai_service_finder":
            handle_ai_service_finder(whatsapp_number, user_id, supabase, user_data)
        elif response_id == "contact_frontdesk":
            clinic_name = user_data.get(whatsapp_number, {}).get("clinic_name", "our clinic")
            wa_link = user_data.get(whatsapp_number, {}).get("wa_link", "")
            if not wa_link:
                error_msg = gt_tt(whatsapp_number, "Sorry, front desk link is unavailable. Please try again.", supabase)
                send_whatsapp_message(whatsapp_number, "text", {"text": {"body": error_msg}})
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return
            frontdesk_text = gt_tt(whatsapp_number, "You've chosen to talk to our front desk. Click the link below to start a conversation with {clinic_name}:", supabase).format(clinic_name=clinic_name)
            send_whatsapp_message(whatsapp_number, "text", {"text": {"body": f"{frontdesk_text}\n\n{wa_link}"}})
            return_to_menu_text = gt_tt(whatsapp_number, "Returning to main menu...", supabase)
            send_whatsapp_message(whatsapp_number, "text", {"text": {"body": return_to_menu_text}})
            user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
            send_interactive_menu(whatsapp_number, supabase)
        elif response_id == "cancel_enquiry":
            cancel_text = gt_tt(whatsapp_number, "Clinic enquiry cancelled.", supabase)
            send_whatsapp_message(whatsapp_number, "text", {"text": {"body": cancel_text}})
            user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
            send_booking_submenu(whatsapp_number, supabase)
        elif response_id == "ai_search_again":
            handle_ai_service_finder(whatsapp_number, user_id, supabase, user_data)
        else:
            logger.warning(f"Unknown response ID: {response_id}")
            user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
            send_interactive_menu(whatsapp_number, supabase)
    except Exception as e:
        logger.error(f"Error in clinic enquiries response: {e}")
        error_msg = gt_tt(whatsapp_number, "An error occurred. Returning to main menu.", supabase)
        send_whatsapp_message(whatsapp_number, "text", {"text": {"body": error_msg}})
        user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
        send_interactive_menu(whatsapp_number, supabase)