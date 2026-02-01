# utils.py - COMPLETE VERSION WITH UPDATED TEMPLATE HANDLING
import logging
import requests
import json
from dotenv import load_dotenv
import os
from en_match import en_translate_template
from cn_match import cn_translate_template, cn_gt_tt, cn_gt_t_tt
from bm_match import bm_translate_template, bm_gt_tt, bm_gt_t_tt
from tm_match import tm_translate_template, tm_gt_tt, tm_gt_t_tt
import time
import math
import base64
import mimetypes


# Load environment variables
load_dotenv()
mimetypes.init()


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# WhatsApp Credentials
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
WHATSAPP_API_URL = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"

# Clinic location coordinates
CLINIC_LATITUDE = 2.9917412
CLINIC_LONGITUDE = 101.6156008
MAX_DISTANCE_KM = 20

# Global variables for rate limiting
_last_template_sent = {}
_last_reengagement_sent = {}
_last_notification_sent = {}  # Track when notifications were sent to prevent duplicates
_last_followup_sent = {}  # Separate tracking for follow-up messages

# ----------------------------------------------------------------
# NEW: Notification Badge Function
# ----------------------------------------------------------------
def get_notification_badge(supabase, whatsapp_number: str) -> str:
    """
    Get notification badge count for unseen notifications.
    Returns badge text like " (3)" or empty string.
    """
    try:
        whatsapp_number_norm = whatsapp_number.lstrip('+').strip()
        # Get user ID
        user_resp = supabase.table("whatsapp_users").select("id").eq("whatsapp_number", whatsapp_number_norm).single().execute()
        
        if user_resp.data:
            user_id = user_resp.data.get("id")
            # Count sent but unseen notifications
            count_resp = supabase.table("c_notifications").select("id", count="exact").eq("user_id", user_id).eq("sent", True).eq("seen", False).execute()
            count = count_resp.count or 0
            
            if count > 0:
                return f" ({count})"
                
    except Exception as e:
        logger.error(f"Error getting notification badge for {whatsapp_number}: {e}")
    
    return ""

# ----------------------------------------------------------------
# UPDATED: Follow-up Specific Notification Function
# ----------------------------------------------------------------
def send_followup_notification(to: str, message: str, supabase=None) -> bool:
    """
    SPECIFICALLY for follow-up messages from actual_followup table.
    Uses followup template (NOT general template).
    """
    logger.info(f"Starting follow-up notification for {to}")
    
    # Check if we've sent a similar follow-up recently (within 5 minutes)
    followup_key = f"followup_{to}_{message[:50]}"
    now = time.time()
    
    if followup_key in _last_followup_sent:
        last_sent = _last_followup_sent[followup_key]
        if now - last_sent < 300:  # 5 minutes cooldown
            logger.info(f"Skipping duplicate follow-up for {to}")
            return True
    
    # STEP 1: Try FREE interactive notification with Better/Same/Worsen buttons
    logger.info(f"Step 1: Trying FREE interactive with buttons")
    
    # Translate the message
    translated_message = gt_tt(to, message, supabase)
    
    # Get button titles based on user language
    language = get_user_language(supabase, to)
    button_texts = {
        "en": {"better": "Better", "same": "Same", "worsen": "Worsen"},
        "cn": {"better": "好转", "same": "没有变化", "worsen": "恶化"},
        "bm": {"better": "Lebih Baik", "same": "Sama", "worsen": "Bertambah Teruk"},
        "tm": {"better": "மேம்பட்டுள்ளது", "same": "அதேபோல உள்ளது", "worsen": "மோசமடைந்துள்ளது"}
    }
    
    # Get button titles for user's language
    btn_titles = button_texts.get(language, button_texts["en"])
    
    content = {
        "interactive": {
            "type": "button",
            "body": {"text": translated_message},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "followup_response_better", "title": btn_titles["better"]}},
                    {"type": "reply", "reply": {"id": "followup_response_same", "title": btn_titles["same"]}},
                    {"type": "reply", "reply": {"id": "followup_response_worsen", "title": btn_titles["worsen"]}}
                ]
            }
        }
    }
    
    if send_whatsapp_message(to, "interactive", content, supabase):
        logger.info(f"FREE interactive with buttons SUCCESS for {to}")
        _last_followup_sent[followup_key] = now
        return True
    
    # STEP 2: If free interactive fails, try FOLLOWUP TEMPLATE
    logger.info(f"Step 2: FREE failed, trying FOLLOWUP template")
    
    language = get_user_language(supabase, to)
    logger.info(f"User language: {language}")
    
    template_name = f"followup_{language}"
    logger.info(f"Template name to send: {template_name}")
    
    # Use send_template_message function with correct template name
    if send_template_message(to, template_name, supabase):
        logger.info(f"FOLLOWUP template SUCCESS for {to}")
        _last_followup_sent[followup_key] = now
        return True
    
    # STEP 3: ALL FAILED
    logger.error(f"All follow-up strategies FAILED for {to}")
    return False

# ----------------------------------------------------------------
# DISTANCE CALCULATION FUNCTIONS
# ----------------------------------------------------------------

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the distance between two points on Earth using Haversine formula.
    """
    try:
        # Convert decimal degrees to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        # Haversine formula
        dlon = lon2_rad - lon1_rad
        dlat = lat2_rad - lat1_rad
        a = math.sin(dlat/2)*2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)*2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        # Earth's radius in kilometers
        radius = 6371.0
        
        distance = radius * c
        return distance
        
    except Exception as e:
        logger.error(f"Error calculating distance: {e}", exc_info=True)
        return None

def calculate_road_distance(origin_lat, origin_lng, dest_lat, dest_lng):
    """
    Calculate road distance using Google Maps Distance Matrix API.
    """
    try:
        api_key = os.getenv("VITE_GOOGLE_MAPS_API_KEY")
        
        if not api_key or api_key == "your_google_maps_api_key_here":
            logger.warning("Google Maps API key not configured, using Haversine formula")
            return calculate_distance(origin_lat, origin_lng, dest_lat, dest_lng)
        
        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "origins": f"{origin_lat},{origin_lng}",
            "destinations": f"{dest_lat},{dest_lng}",
            "key": api_key,
            "units": "metric",
            "region": "my",  # Malaysia
            "mode": "driving"
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("status") == "OK" and data.get("rows"):
            element = data["rows"][0]["elements"][0]
            if element.get("status") == "OK":
                distance_meters = element["distance"]["value"]
                distance_km = distance_meters / 1000
                
                # Also get estimated duration if needed
                duration_seconds = element.get("duration", {}).get("value", 0)
                duration_minutes = duration_seconds / 60 if duration_seconds else 0
                
                logger.info(f"Road distance calculated: {distance_km:.2f} km, "
                           f"estimated travel time: {duration_minutes:.1f} minutes")
                
                return distance_km
        
        logger.warning(f"Google Maps API failed: {data.get('status', 'Unknown error')}")
        # Fallback to Haversine formula
        return calculate_distance(origin_lat, origin_lng, dest_lat, dest_lng)
        
    except requests.exceptions.Timeout:
        logger.error("Google Maps API timeout, using Haversine formula")
        return calculate_distance(origin_lat, origin_lng, dest_lat, dest_lng)
    except requests.exceptions.RequestException as e:
        logger.error(f"Google Maps API request error: {e}, using Haversine formula")
        return calculate_distance(origin_lat, origin_lng, dest_lat, dest_lng)
    except Exception as e:
        logger.error(f"Error calculating road distance: {e}, using Haversine formula", exc_info=True)
        return calculate_distance(origin_lat, origin_lng, dest_lat, dest_lng)

def check_distance_from_clinic(patient_lat, patient_lng):
    """
    Check if patient location is within service radius.
    """
    try:
        # Try road distance first
        distance_km = calculate_road_distance(
            CLINIC_LATITUDE, CLINIC_LONGITUDE,
            patient_lat, patient_lng
        )
        
        if distance_km is None:
            # Fallback to straight-line distance
            distance_km = calculate_distance(
                CLINIC_LATITUDE, CLINIC_LONGITUDE,
                patient_lat, patient_lng
            )
            distance_type = "straight-line"
        else:
            distance_type = "road"
        
        if distance_km is None:
            logger.error("Both distance calculation methods failed")
            return True, 0, "Distance calculation failed"
        
        # Check if within service radius
        is_within_radius = distance_km <= MAX_DISTANCE_KM
        
        if is_within_radius:
            message = f"Location is within service radius ({distance_km:.1f} km {distance_type} distance)"
        else:
            message = (f"Location is {distance_km:.1f} km away ({distance_type} distance), "
                      f"exceeds {MAX_DISTANCE_KM} km service radius")
        
        logger.info(f"Distance check: {message}")
        return is_within_radius, distance_km, message
        
    except Exception as e:
        logger.error(f"Error in distance check: {e}", exc_info=True)
        return True, 0, f"Distance check failed: {str(e)}"
    
# ----------------------------------------------------------------
# ROUTING: Lookup Clinic by Keyword
# ----------------------------------------------------------------

def lookup_clinic_by_keyword(supabase, keyword: str):
    """
    Look up clinic information by keyword from the anyhealth_clinic_url table.
    
    Args:
        supabase: Supabase client
        keyword: The keyword to search for (e.g., 'find_lophysio_tanjungtokong')
    
    Returns:
        A dictionary with clinic information (provider_cat, provider_id, etc.) or None if not found.
    """
    try:
        # Remove the 'find_' prefix
        if keyword.startswith('find_'):
            keyword = keyword[5:]  # Remove 'find_' prefix
            
        logger.info(f"Looking up clinic by keyword: {keyword}")
        
        response = supabase.table("anyhealth_clinic_url").select("*").eq("keywords", keyword).execute()
        
        if response.data and len(response.data) > 0:
            clinic_info = response.data[0]
            logger.info(f"Found clinic: {clinic_info}")
            return clinic_info
        else:
            logger.warning(f"No clinic found for keyword: {keyword}")
            return None
    except Exception as e:
        logger.error(f"Error looking up clinic by keyword {keyword}: {e}", exc_info=True)
        return None

# ----------------------------------------------------------------
# USER MANAGEMENT FUNCTIONS
# ----------------------------------------------------------------

def get_user_id(supabase, whatsapp_number: str) -> str:
    """Fetch user_id from whatsapp_users table based on whatsapp_number."""
    try:
        from_number_norm = whatsapp_number.lstrip("+").strip()
        number_variants = [from_number_norm, f"+{from_number_norm}"]
        logger.info(f"Fetching user_id for whatsapp_number: {number_variants}")
        response = supabase.table("whatsapp_users").select("id").in_("whatsapp_number", number_variants).limit(1).execute()
        if response.data:
            user_id = response.data[0]["id"]
            logger.info(f"Found user_id: {user_id} for whatsapp_number: {from_number_norm}")
            return user_id
        logger.warning(f"No user_id found for whatsapp_number: {from_number_norm}")
        return None
    except Exception as e:
        logger.error(f"Error fetching user_id for {whatsapp_number}: {e}", exc_info=True)
        return None

def get_user_language(supabase, whatsapp_number: str) -> str:
    """Fetch user's language preference."""
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

# ----------------------------------------------------------------
# TRANSLATION FUNCTIONS
# ----------------------------------------------------------------

def gt_tt(whatsapp_number: str, text: str, supabase=None, doctor_name: str = None) -> str:
    """
    Wrapper function to handle Google Translate for dynamic database fields.
    """
    try:
        if not supabase or not hasattr(supabase, 'table'):
            logger.warning(f"Supabase client not provided or invalid for {whatsapp_number}, returning original text")
            return text

        language = get_user_language(supabase, whatsapp_number)
        logger.debug(f"Language for {whatsapp_number}: {language}")

        translation_functions = {
            "en": lambda x, s=None, d=None: x,  # Return original text for English
            "bm": bm_gt_tt,
            "cn": cn_gt_tt,
            "tm": tm_gt_tt,
        }
        translate_func = translation_functions.get(language, lambda x, s=None, d=None: x)
        translated_text = translate_func(text, supabase, doctor_name)
        logger.debug(f"Translated '{text}' to '{translated_text}' for language: {language}")
        return translated_text
    except Exception as e:
        logger.error(f"Error in gt_tt for {whatsapp_number}: {e}, returning original text", exc_info=True)
        return text

def gt_t_tt(whatsapp_number: str, text: str, supabase=None, doctor_name: str = None) -> str:
    """
    Translate and truncate for buttons, titles, and row titles in WhatsApp.
    """
    try:
        if not supabase or not hasattr(supabase, 'table'):
            logger.warning(f"Supabase client not provided or invalid for {whatsapp_number}, returning original text")
            return text

        language = get_user_language(supabase, whatsapp_number)
        logger.debug(f"Language for {whatsapp_number}: {language}")

        translation_functions = {
            "en": lambda x, s=None, d=None: x,  # Return original text for English
            "bm": bm_gt_t_tt,
            "cn": cn_gt_t_tt,
            "tm": tm_gt_t_tt,
        }
        translate_func = translation_functions.get(language, lambda x, s=None, d=None: x)
        translated_text = translate_func(text, supabase, doctor_name)
        logger.debug(f"Translated and truncated '{text}' to '{translated_text}' for language: {language}")
        return translated_text
    except Exception as e:
        logger.error(f"Error in gt_t_tt for {whatsapp_number}: {e}, returning original text", exc_info=True)
        return text

def gt_dt_tt(whatsapp_number: str, text: str, supabase=None, doctor_name: str = None) -> str:
    """
    Translate and truncate for descriptions with 72 character limit.
    Similar to gt_t_tt but with 72 character limit.
    If text exceeds 72 characters, truncate at 69 and add "..."
    """
    try:
        if not supabase or not hasattr(supabase, 'table'):
            logger.warning(f"Supabase client not provided or invalid for {whatsapp_number}, returning original text")
            return text

        language = get_user_language(supabase, whatsapp_number)
        logger.debug(f"Language for {whatsapp_number}: {language}")

        # First translate the text using gt_tt (no truncation)
        translated_text = gt_tt(whatsapp_number, text, supabase, doctor_name)
        
        # Apply 72 character limit truncation
        if len(translated_text) > 72:
            # Truncate at 69 characters and add "..."
            truncated_text = translated_text[:69] + "..."
            logger.debug(f"Truncated description from {len(translated_text)} to 72 chars: '{truncated_text}'")
            return truncated_text
            
        return translated_text
    except Exception as e:
        logger.error(f"Error in gt_dt_tt for {whatsapp_number}: {e}, returning original text", exc_info=True)
        return text

def translate_template(whatsapp_number: str, text: str, supabase=None) -> str:
    """
    Select the appropriate translation function based on user's language.
    """
    try:
        if not supabase or not hasattr(supabase, 'table'):
            logger.warning(f"Supabase client not provided or invalid for {whatsapp_number}, defaulting to English translation")
            return en_translate_template(text)

        language = get_user_language(supabase, whatsapp_number)
        logger.debug(f"Language for {whatsapp_number}: {language}")

        translation_functions = {
            "en": en_translate_template,
            "bm": bm_translate_template,
            "cn": cn_translate_template,
            "tm": tm_translate_template,
        }
        translate_func = translation_functions.get(language, en_translate_template)
        translated_text = translate_func(text, supabase)
        logger.debug(f"Translated '{text}' to '{translated_text}' for language: {language}")
        return translated_text
    except Exception as e:
        logger.error(f"Error selecting translation for {whatsapp_number}: {e}, defaulting to English", exc_info=True)
        return en_translate_template(text)

# ----------------------------------------------------------------
# GEOCODING FUNCTION
# ----------------------------------------------------------------

def geocode_address(address: str) -> dict:
    """
    Convert address to latitude and longitude using Google Maps API.
    """
    try:
        if not address or address.lower() in ["none", "null", ""]:
            logger.warning("Empty address provided for geocoding")
            return None
            
        api_key = os.environ.get("VITE_GOOGLE_MAPS_API_KEY", "AIzaSyBz3OGVCWolHmNxz20SABVeCRuDNNBjC0I")
        
        if not api_key or api_key == "your_google_maps_api_key_here":
            logger.warning("Google Maps API key not configured")
            return None
        
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": address,
            "key": api_key,
            "region": "my",  # Malaysia
            "language": "en"
        }
        
        logger.info(f"Geocoding address: {address}")
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("status") == "OK" and data.get("results"):
            result = data["results"][0]
            location = result["geometry"]["location"]
            formatted_address = result.get("formatted_address", address)
            
            logger.info(f"Geocoding successful: {formatted_address} - Lat: {location['lat']}, Lng: {location['lng']}")
            
            return {
                "latitude": location["lat"],
                "longitude": location["lng"],
                "formatted_address": formatted_address
            }
        else:
            logger.warning(f"Geocoding failed for address: {address}. Status: {data.get('status')}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error(f"Geocoding timeout for address: {address}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Geocoding request error for address {address}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error in geocode_address for {address}: {e}")
        return None

# ---------------------------------------------------------------------
# UPDATED: send_notification_with_fallback - UPDATED FOR NEW REMINDER TYPES
# ---------------------------------------------------------------------
def send_notification_with_fallback(to: str, message: str, reminder_type: str, supabase=None) -> bool:
    """
    STRATEGY: Try FREE INTERACTIVE notification with header/footer/button first, 
    fall back to APPROPRIATE TEMPLATE based on reminder_type if it fails.
    
    Returns True if either method succeeds, False if both fail.
    
    UPDATED: Now handles dayc, weekc, customc, and a_day reminder types.
    """
    logger.info(f"Starting notification strategy for {to}, type: {reminder_type}")
    
    # Check if we've sent a similar notification recently (within 5 minutes)
    notification_key = f"notification_{to}_{message[:50]}"
    now = time.time()
    
    if notification_key in _last_notification_sent:
        last_sent = _last_notification_sent[notification_key]
        if now - last_sent < 300:  # 5 minutes cooldown
            logger.info(f"Skipping duplicate notification for {to} (sent recently)")
            return True
    
    # STEP 1: Try FREE INTERACTIVE notification with header/footer/button first
    logger.info(f"Step 1: Sending FREE INTERACTIVE notification to {to}")
    
    # Use gt_tt to translate the message based on user's language
    translated_message = gt_tt(to, message, supabase)
    logger.info(f"Translated message ({get_user_language(supabase, to)}): {translated_message[:100]}...")
    
    interactive_success = send_interactive_notification_with_header_footer_button(to, translated_message, supabase)
    
    if interactive_success:
        logger.info(f"FREE INTERACTIVE notification with header/footer/button strategy SUCCESS for {to}")
        _last_notification_sent[notification_key] = now
        return True
    
    # STEP 2: Interactive failed, try APPROPRIATE TEMPLATE fallback (paid)
    logger.info(f"Step 2: FREE INTERACTIVE failed for {to}, attempting TEMPLATE fallback...")
    
    # Get user's language for template selection
    language = get_user_language(supabase, to)
    
    # SELECT TEMPLATE BASED ON REMINDER_TYPE - UPDATED FOR NEW TYPES
    # We now have: dayc, weekc, customc, a_day
    if reminder_type in ["dayc", "weekc", "customc", "a_day"]:
        # Use specific template based on reminder type
        template_name = f"{reminder_type}_{language}"
    else:
        # Default to general template
        template_name = f"general_{language}"
        logger.warning(f"Unknown reminder_type '{reminder_type}', using general template")
    
    logger.info(f"Selected template: {template_name} for reminder_type: {reminder_type}, language: {language}")
    
    template_success = send_template_message(to, template_name, supabase)
    
    if template_success:
        logger.info(f"TEMPLATE fallback strategy SUCCESS for {to}")
        _last_notification_sent[notification_key] = now
        return True
    
    # STEP 3: All failed
    logger.error(f"All notification strategies FAILED for {to}.")
    return False

# ---------------------------------------------------------------------
# FUNCTION: send_interactive_notification_with_header_footer_button
# ---------------------------------------------------------------------
def send_interactive_notification_with_header_footer_button(to: str, message: str, supabase=None) -> bool:
    """
    Send an interactive notification with header, footer, and "Noted" button.
    Header: "AnyHealth - Clinic Appointment" (static)
    Body: {message} (already translated via gt_tt)
    Footer: "Stay Healthy, Effortlessly!" (static)
    Button: "Noted" (translated based on user language)
    """
    to = to.strip()
    if not to.startswith("+"):
        to = f"+{to}"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    
    # Define button text based on language
    language = get_user_language(supabase, to) if supabase else "en"
    button_texts = {
        "en": "Noted",
        "cn": "明白", 
        "bm": "Faham",
        "tm": "குறிப்பிட்டார்"
    }
    button_title = button_texts.get(language, "Noted")
    
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "header": {
                "type": "text",
                "text": "AnyHealth - Clinic Appointment"
            },
            "body": {
                "text": message
            },
            "footer": {
                "text": "Stay Healthy, Effortlessly!"
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "notification_noted",
                            "title": button_title
                        }
                    }
                ]
            }
        }
    }

    try:
        logger.info(f"Attempting FREE INTERACTIVE notification with header/footer/button to {to}")
        
        response = requests.post(WHATSAPP_API_URL, headers=headers, json=payload)
        
        # Check if request was successful
        if response.status_code == 200:
            logger.info(f"FREE INTERACTIVE notification with header/footer/button successfully sent to {to}.")
            return True
            
        # Handle API errors
        resp_json = response.json()
        if "error" in resp_json:
            err = resp_json["error"]
            code = err.get("code")
            msg = err.get("message", "").lower()
            if code == 131047 or "24 hours" in msg:
                logger.warning(f"24-hour window expired for {to}. Free interactive notification failed.")
                return False
            else:
                logger.error(f"WhatsApp API error: {err}")
                return False

        logger.error(f"Unexpected response for {to}: {response.status_code} -> {response.text}")
        return False

    except Exception as e:
        logger.error(f"Error sending free interactive notification to {to}: {e}", exc_info=True)
        return False

# ---------------------------------------------------------------------
# FUNCTION: send_free_notification
# ---------------------------------------------------------------------
def send_free_notification(to: str, message: str, supabase=None) -> bool:
    """
    Send a free text notification message to the user.
    Used for error messages, success messages, etc.
    """
    to = to.strip()
    if not to.startswith("+"):
        to = f"+{to}"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    # Use gt_tt for dynamic message content
    body_text = gt_tt(to, message, supabase)
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body_text},
    }

    try:
        logger.info(f"Attempting FREE TEXT notification to {to}: {body_text}")
        response = requests.post(WHATSAPP_API_URL, headers=headers, json=payload)
        resp_json = response.json()
        
        # --- Detect 24-hour rule violation ---
        if "error" in resp_json:
            err = resp_json["error"]
            code = err.get("code")
            msg = err.get("message", "").lower()
            if code == 131047 or "24 hours" in msg:
                logger.warning(f"24-hour window expired for {to}. Free text notification failed.")
                return False
            else:
                logger.error(f"WhatsApp API error: {err}")
                return False

        # --- Success path ---
        if response.status_code == 200:
            logger.info(f"FREE TEXT notification successfully sent to {to}.")
            return True

        logger.error(f"Unexpected response for {to}: {response.status_code} -> {response.text}")
        return False

    except Exception as e:
        logger.error(f"Error sending free text notification to {to}: {e}", exc_info=True)
        return False

# ---------------------------------------------------------------------
# FUNCTION: send_template_message
# ---------------------------------------------------------------------
def send_template_message(to: str, template_name: str, supabase=None) -> bool:
    """
    Send a WhatsApp template message to the specified number.
    Returns True if successful, False otherwise.
    """
    to = to.strip()
    if not to.startswith("+"):
        to = f"+{to}"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    
    # Get user's language
    language = get_user_language(supabase, to)
    
    # Check if template_name already contains a language suffix
    language_suffixes = ["en", "bm", "cn", "tm", "ms", "zh_CN", "ta"]
    
    # Check if template name ends with a known language suffix
    has_language_suffix = False
    for suffix in language_suffixes:
        if template_name.endswith(f"_{suffix}"):
            has_language_suffix = True
            break
    
    if not has_language_suffix:
        # No language suffix found, append user's language
        template_name = f"{template_name}_{language}"
    
    # Map language codes to WhatsApp language codes
    language_code_map = {
        "en": "en",
        "bm": "ms", 
        "cn": "zh_CN",
        "tm": "ta"
    }
    
    # Extract language code from template name for WhatsApp API
    template_language_code = "en"  # default
    
    # Try to extract language code from template name
    if '_' in template_name:
        extracted_lang = template_name.split('_')[-1]
        # Handle both short codes (en, bm, cn, tm) and WhatsApp codes (ms, zh_CN, ta)
        if extracted_lang in language_code_map:
            template_language_code = language_code_map[extracted_lang]
        elif extracted_lang in ["ms", "zh_CN", "ta"]:
            # Already a WhatsApp language code
            template_language_code = extracted_lang
        else:
            # Unknown code, use user's language
            template_language_code = language_code_map.get(language, "en")

    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_language_code},
        },
    }

    try:
        logger.info(f"Sending TEMPLATE to {to}: {template_name} with language {template_language_code}")
        response = requests.post(WHATSAPP_API_URL, json=data, headers=headers)
        resp_json = response.json()

        if response.status_code == 200 and "messages" in resp_json:
            logger.info(f"TEMPLATE successfully sent to {to}.")
            return True

        logger.error(f"Failed to send template message: {response.status_code} -> {resp_json}")
        return False
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending template message to {to}: {e}")
        if 'response' in locals():
            logger.error(f"Response content: {response.text}")
        return False

# ---------------------------------------------------------------------
# FUNCTION: send_whatsapp_message
# ---------------------------------------------------------------------
def send_whatsapp_message(to: str, message_type: str, content: dict, supabase=None) -> bool:
    """Send a WhatsApp message to the specified number with translated text."""
    to = to.strip()
    if not to.startswith("+"):
        to = f"+{to}"
    
    if message_type == "text":
        body_text = content.get("text", {}).get("body", "")
        # If the body already looks like a formatted confirmation (has \n and *), skip translate_template
        if "\n*" in body_text:
            content["text"]["body"] = body_text
        else:
            content["text"]["body"] = translate_template(to, body_text, supabase)
    
    elif message_type == "interactive":
        interactive = content.get("interactive", {})
        if interactive.get("header", {}).get("type") == "text":
            interactive["header"]["text"] = translate_template(to, interactive["header"].get("text", ""), supabase)
        body_text = interactive["body"].get("text", "")
        # Use gt_tt for body text in interactive messages (dynamic content)
        interactive["body"]["text"] = gt_tt(to, body_text, supabase)
        if interactive.get("footer"):
            interactive["footer"]["text"] = translate_template(to, interactive["footer"].get("text", ""), supabase)
        if interactive.get("action", {}).get("button"):
            # Use translate_template for menu buttons (static text)
            interactive["action"]["button"] = translate_template(to, interactive["action"].get("button", ""), supabase)
        
        # For sections and rows, we assume they are already translated
        # by the calling function
        for section in interactive.get("action", {}).get("sections", []):
            # Section titles are already translated in the calling function
            # Just ensure they don't exceed character limits
            section_title = section.get("title", "")
            if len(section_title) > 24:
                section["title"] = section_title[:21] + "..."
            
            for row in section.get("rows", []):
                # Row titles are already translated in the calling function
                # Just ensure they don't exceed character limits
                row_title = row.get("title", "")
                if len(row_title) > 24:
                    row["title"] = row_title[:21] + "..."
                
                if row.get("description"):
                    # Row descriptions are already translated in the calling function
                    # Just ensure they don't exceed character limits
                    row_description = row.get("description", "")
                    if len(row_description) > 72:
                        row["description"] = row_description[:69] + "..."
        
        if interactive.get("type") == "button":
            for button in interactive.get("action", {}).get("buttons", []):
                if button.get("type") == "reply" and button.get("reply", {}).get("title"):
                    # Button titles are already translated in the calling function
                    # Just ensure they don't exceed character limits
                    button_title = button["reply"].get("title", "")
                    if len(button_title) > 20:
                        button["reply"]["title"] = button_title[:17] + "..."
        content["interactive"] = interactive
    
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": message_type,
        **content
    }
    try:
        logger.info(f"Sending payload to {to}: {json.dumps(data, indent=2, ensure_ascii=False)}")
        response = requests.post(WHATSAPP_API_URL, json=data, headers=headers)
        response.raise_for_status()
        logger.info(f"Reply sent to {to}: {response.json()}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending message to {to}: {e}")
        if 'response' in locals():
            logger.error(f"Response content: {response.text}")
        return False

# ---------------------------------------------------------------------
# UPDATED: send_interactive_menu
# ---------------------------------------------------------------------
def send_interactive_menu(to: str, supabase=None) -> bool:
    """Send main menu with updated menu options."""
    to = to.strip()
    if not to.startswith("+"):
        to = f"+{to}"

    # Clear cache before sending main menu
    if supabase:
        clear_user_cache(to, supabase)

    # Get notification badge count
    notification_count = 0
    try:
        whatsapp_number_norm = to.lstrip('+').strip()
        user_resp = supabase.table("whatsapp_users").select("id").eq("whatsapp_number", whatsapp_number_norm).single().execute()
        if user_resp.data:
            user_id = user_resp.data.get("id")
            # Count sent notifications that are not prompted
            count_resp = supabase.table("c_notifications").select("id", count="exact").eq("user_id", user_id).eq("sent", True).eq("prompted", False).execute()
            notification_count = count_resp.count or 0
    except Exception as e:
        logger.error(f"Error getting notification count: {e}")

    # Build notification badge text
    notification_badge = f" ({notification_count})" if notification_count > 0 else ""

    # Fetch user's language
    language = get_user_language(supabase, to)

    # Hardcoded translations for the welcome text
    welcome_texts = {
        "en": "Welcome to AnyHealth!\n\nPlease choose an option below,\nor send 'Main Menu' to return to the main menu.\n\n_Select Service Booking to book clinic or ambulance services._",
        "bm": "Selamat datang ke AnyHealth!\n\nSila pilih pilihan di bawah,\natau hantar 'Main Menu' untuk kembali ke menu utama.\n\n_Pilih Perkhidmatan Tempahan untuk menempah perkhidmatan klinik atau ambulans._",
        "cn": "欢迎来到 AnyHealth！\n\n请选择下面的选项，\n或发送 'Main menu' 以返回主菜单。\n\n_选择服务预订以预订诊所或救护车服务。_",
        "tm": "ஏனிஹெல்துக்கு வரவேற்கிறோம்!\n\nகீழே உள்ள விருப்பங்களில் ஒன்றைத் தேர்ந்தெடுக்கவும்,\nஅல்லது முதன்மை மெனுவிற்குத் திரும்ப 'ஹாய்' அனுப்பவும்.\n\n_மருத்துவமனை அல்லது ஆம்புலன்ஸ் சேவைகளை முன்பதிவு செய்ய சேவை முன்பதிவைத் தேர்ந்தெடுக்கவும்._"
    }
    welcome_text = welcome_texts.get(language, welcome_texts["en"])

    # Build notification title with badge
    notification_title_base = translate_template(to, "🔔 Notification", supabase)
    notification_title = f"{notification_title_base}{notification_badge}"

    # MAIN MENU STRUCTURE
    content = {
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": translate_template(to, "AnyHealth Bot", supabase)},
            "body": {"text": welcome_text},
            "footer": {"text": translate_template(to, "Select an option to proceed", supabase)},
            "action": {
                "button": translate_template(to, "Menu", supabase),
                "sections": [{
                    "title": translate_template(to, "Main Options", supabase),
                    "rows": [
                        {"id": "notification", "title": notification_title},
                        {"id": "profile", "title": translate_template(to, "👤 Profile", supabase)},
                        {"id": "service_booking", "title": translate_template(to, "🏥 Service Booking", supabase)},
                        {"id": "upcoming_booking", "title": translate_template(to, "📅 Upcoming Booking", supabase)},
                        {"id": "help", "title": translate_template(to, "❓ Help", supabase)},
                        {"id": "languages", "title": translate_template(to, "🌐 Languages", supabase)}
                    ]
                }]
            }
        }
    }
    return send_whatsapp_message(to, "interactive", content, supabase)

# ---------------------------------------------------------------------
# UPDATED: send_booking_submenu
# ---------------------------------------------------------------------
def send_booking_submenu(to: str, supabase=None) -> bool:
    """Send booking submenu with Health Screening Plan added."""
    to = to.strip()
    if not to.startswith("+"):
        to = f"+{to}"

    content = {
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": translate_template(to, "AnyHealth Bot", supabase)},
            "body": {"text": translate_template(to, "Please choose a booking option:", supabase)},
            "footer": {"text": translate_template(to, "Select an option to proceed", supabase)},
            "action": {
                "button": translate_template(to, "Booking Options", supabase),
                "sections": [{
                    "title": translate_template(to, "Booking Services", supabase),
                    "rows": [
                        {"id": "clinic_enquiries", "title": translate_template(to, "📞 Clinic Enquiries", supabase)},
                        {"id": "symptoms_checker", "title": translate_template(to, "👨‍⚕️ General GP Visit", supabase)},
                        {"id": "checkup_booking", "title": translate_template(to, "🩺 Checkup & Test", supabase)},
                        {"id": "vaccination_booking", "title": translate_template(to, "💉 Vaccination", supabase)},
                        {"id": "back_button", "title": translate_template(to, "🔙 Back to Main Menu", supabase)}
                    ]
                }]
            }
        }
    }
    return send_whatsapp_message(to, "interactive", content, supabase)

# ---------------------------------------------------------------------
# REENGAGEMENT AND TEMPLATE HANDLING FUNCTIONS
# ---------------------------------------------------------------------

def handle_reengagement_error(recipient_id: str, supabase=None):
    """
    Called when WhatsApp error code 131047 (24-hour rule) occurs.
    Sends general template for reengagement (NOT followup).
    """
    now = time.time()
    last_sent = _last_reengagement_sent.get(recipient_id, 0)

    # prevent re-sending within 1 hour
    if now - last_sent < 3600:
        logger.info(f"Reengagement template for {recipient_id} skipped (sent recently).")
        return

    _last_reengagement_sent[recipient_id] = now
    logger.warning(f"24-hour session expired for {recipient_id}. Sending reengagement template...")

    try:
        # The recipient_id from webhook is just the number without country code
        if not recipient_id.startswith("+"):
            # Just add + to the existing number
            recipient_id = f"+{recipient_id}"
        
        # Get user's language to send appropriate template
        language = get_user_language(supabase, recipient_id)
        # Use GENERAL template for reengagement, NOT followup
        template_name = f"general_{language}"
        
        logger.info(f"Sending reengagement GENERAL template {template_name} to {recipient_id}")
        success = send_template_message(recipient_id, template_name, supabase)
        
        if success:
            logger.info(f"Reengagement GENERAL template successfully sent to {recipient_id}")
        else:
            logger.error(f"Failed to send reengagement GENERAL template to {recipient_id}")
    except Exception as e:
        logger.error(f"Failed to send reengagement GENERAL template to {recipient_id}: {e}", exc_info=True)

def send_template_for_notification(to: str, template_name: str, supabase=None) -> bool:
    """
    Force send a template message for a specific notification type.
    This is used when we detect 24-hour rule violations and want to send
    the appropriate template based on the original notification type.
    
    IMPORTANT FIX: If template_name doesn't have a language code, add it.
    """
    try:
        to = to.strip()
        if not to.startswith("+"):
            to = f"+{to}"
        
        # Get user's language
        language = get_user_language(supabase, to)
        
        # Check if template_name already has a language code
        if '_' in template_name:
            # Check if the last part is a valid language code
            last_part = template_name.split('_')[-1]
            valid_languages = ["en", "bm", "cn", "tm"]
            if last_part in valid_languages:
                # Template already has language code
                full_template_name = template_name
            else:
                # Append language code
                full_template_name = f"{template_name}_{language}"
        else:
            # No language code, append it
            full_template_name = f"{template_name}_{language}"
        
        logger.info(f"Sending template {full_template_name} to {to}")
        success = send_template_message(to, full_template_name, supabase)
        
        if success:
            logger.info(f"Template {full_template_name} successfully sent to {to}")
        else:
            logger.error(f"Failed to send template {full_template_name} to {to}")
            
        return success
        
    except Exception as e:
        logger.error(f"Error sending template for notification to {to}: {e}", exc_info=True)
        return False

# ---------------------------------------------------------------------
# STATE MANAGEMENT FUNCTIONS
# ---------------------------------------------------------------------

def send_main_menu_confirmation(whatsapp_number, supabase, user_data_dict):
    """Send button-based confirmation for main menu before returning to main menu."""
    try:
        # Store current state in temp_data for possible restoration
        module = user_data_dict.get("module")
        state = user_data_dict.get("state")
        
        logger.info(f"Sending main menu confirmation to {whatsapp_number}, module: {module}, state: {state}")
        
        # Store current state in temp_data in database
        try:
            whatsapp_number_norm = whatsapp_number.lstrip('+').strip()
            
            temp_data = {
                "previous_state": state,
                "previous_module": module,
                "restore_timestamp": time.time(),
                "clinic_id": user_data_dict.get("clinic_id"),
                "category_id": user_data_dict.get("category_id"),
                "service_id": user_data_dict.get("service_id"),
                "service_name": user_data_dict.get("service_name"),
                "tcm_type": user_data_dict.get("tcm_type"),
                "doctor_id": user_data_dict.get("doctor_id")
            }
            
            # Clean up any None values
            temp_data = {k: v for k, v in temp_data.items() if v is not None}
            
            supabase.table("whatsapp_users").update({
                "temp_data": temp_data
            }).eq("whatsapp_number", whatsapp_number_norm).execute()
            
        except Exception as e:
            logger.error(f"Error storing temp_data for main menu confirmation: {e}")
        
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
        
        return send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
        
    except Exception as e:
        logger.error(f"Error sending main menu confirmation: {e}")
        return False

def restore_previous_state(whatsapp_number, user_id, supabase, user_data):
    """Restore user's previous state after declining main menu."""
    try:
        whatsapp_number_norm = whatsapp_number.lstrip('+').strip()
        
        # Get stored temp_data
        user_db_data = supabase.table("whatsapp_users").select("temp_data").eq(
            "whatsapp_number", whatsapp_number_norm
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
                
                # Restore previous state and module to user_data
                user_data[whatsapp_number]["state"] = previous_state
                user_data[whatsapp_number]["module"] = previous_module
                
                # Restore other data if available
                for key in ["clinic_id", "category_id", "service_id", "service_name", "tcm_type", "doctor_id"]:
                    if key in temp_data:
                        user_data[whatsapp_number][key] = temp_data[key]
                
                # Clear temp_data
                supabase.table("whatsapp_users").update({
                    "temp_data": {}
                }).eq("whatsapp_number", whatsapp_number_norm).execute()
                
                logger.info(f"Restored state: {previous_state}, module: {previous_module} for {whatsapp_number}")
                
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

# ---------------------------------------------------------------------
# MEDIA AND FILE HANDLING FUNCTIONS
# ---------------------------------------------------------------------

def send_image_message(to: str, image_url: str, supabase=None, caption: str = None) -> bool:
    """Send image with optional caption."""
    to = to.strip()
    if not to.startswith("+"):
        to = f"+{to}"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    # Use provided caption (translated), else fallback
    if caption is not None:
        caption_text = gt_tt(to, caption, supabase)
    else:
        caption_text = gt_tt(to, "Welcome to our clinic! Please select a booking option.", supabase)

    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "image",
        "image": {
            "link": image_url,
            "caption": caption_text
        }
    }

    try:
        logger.info(f"Sending image with caption to {to}: {image_url}")
        response = requests.post(WHATSAPP_API_URL, json=data, headers=headers)
        response.raise_for_status()
        logger.info(f"Image sent to {to}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending image to {to}: {e}")
        if 'response' in locals():
            logger.error(f"Response: {response.text}")
        return False
    
def send_document(to: str, document_url: str, caption: str = None, filename: str = None, supabase=None) -> bool:
    """Send a PDF/document via WhatsApp."""
    to = to.strip()
    if not to.startswith("+"):
        to = f"+{to}"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    caption_text = translate_template(to, caption, supabase) if caption else ""

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "document",
        "document": {
            "link": document_url,
            "caption": caption_text
        }
    }
    if filename:
        payload["document"]["filename"] = filename

    try:
        logger.info(f"Sending document to {to}: {document_url}")
        response = requests.post(WHATSAPP_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        logger.info(f"Document sent to {to}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending document to {to}: {e}")
        if 'response' in locals():
            logger.error(f"Response content: {response.text}")
        return False

def send_non_emergency_menu_updated(to: str, supabase=None) -> bool:
    """Send non-emergency ambulance service menu with 4 options."""
    to = to.strip()
    if not to.startswith("+"):
        to = f"+{to}"

    content = {
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": translate_template(to, "🚑 Non-Emergency Ambulance", supabase)},
            "body": {"text": translate_template(to,
                "Please select the type of non-emergency transport you need:\n\n"
                "• Scheduled patient transport\n"
                "• Advance booking required (24 hours)\n"
                "• Professional medical team", supabase)},
            "footer": {"text": translate_template(to, "Choose an option below", supabase)},
            "action": {
                "button": translate_template(to, "Select Service", supabase),
                "sections": [{
                    "title": translate_template(to, "Available Services", supabase),
                    "rows": [
                        {"id": "advance_booking", "title": translate_template(to, "🏠 → 🏥 Home to Hosp", supabase)},
                        {"id": "homehome_transfer", "title": translate_template(to, "🏠 → 🏠 Home to Home", supabase)},
                        {"id": "discharge_service", "title": translate_template(to, "🏥 → 🏠 Hosp to Home", supabase)},
                        {"id": "hosphosp_transfer", "title": translate_template(to, "🏥 → 🏥 Hosp to Hosp", supabase)},
                        {"id": "back_to_main", "title": translate_template(to, "🔙 Back to Main Menu", supabase)}
                    ]
                }]
            }
        }
    }

    return send_whatsapp_message(to, "interactive", content, supabase)

def update_notification_seen_status(whatsapp_number: str, supabase=None):
    """
    Update seen status for notifications when a message is read.
    Called from webhook when status is "read".
    """
    try:
        from notification import update_notification_seen_status as update_seen
        return update_seen(whatsapp_number, supabase)
    except Exception as e:
        logger.error(f"Error in update_notification_seen_status: {e}", exc_info=True)
        return False

def send_location_request(to: str, supabase=None) -> bool:
    """Send a request for location sharing."""
    to = to.strip()
    if not to.startswith("+"):
        to = f"+{to}"
    
    content = {
        "interactive": {
            "type": "location_request_message",
            "body": {"text": translate_template(to, "Please share your current location:", supabase)},
            "action": {
                "name": "send_location"
            }
        }
    }
    
    return send_whatsapp_message(to, "interactive", content, supabase)

def download_whatsapp_media(media_id: str) -> bytes:
    """Download media file from WhatsApp API and return as bytes."""
    try:
        # Get WhatsApp access token from environment
        whatsapp_token = os.environ.get("WHATSAPP_TOKEN")
        if not whatsapp_token:
            logger.error("WhatsApp token not found in environment")
            return None
        
        # First, get the media URL from WhatsApp API
        media_url_response = requests.get(
            f"https://graph.facebook.com/v20.0/{media_id}",
            headers={"Authorization": f"Bearer {whatsapp_token}"},
            timeout=30
        )
        
        if media_url_response.status_code != 200:
            logger.error(f"Failed to get media URL: {media_url_response.text}")
            return None
        
        media_url_data = media_url_response.json()
        media_url = media_url_data.get("url")
        
        if not media_url:
            logger.error("No URL in media response")
            return None
        
        logger.info(f"Downloading media from: {media_url}")
        
        # Download the actual media file
        media_response = requests.get(
            media_url,
            headers={"Authorization": f"Bearer {whatsapp_token}"},
            timeout=60
        )
        
        if media_response.status_code != 200:
            logger.error(f"Failed to download media: {media_response.status_code} - {media_response.text[:200]}")
            return None
        
        # Return the file content as bytes
        content = media_response.content
        logger.info(f"Successfully downloaded media, size: {len(content)} bytes")
        
        return content
        
    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout downloading WhatsApp media {media_id}: {e}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error downloading WhatsApp media {media_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error downloading WhatsApp media {media_id}: {e}", exc_info=True)
        return None

def upload_to_supabase_storage(supabase, bucket_name: str, file_path: str, file_content: bytes, content_type: str = None) -> str:
    """Upload file to Supabase Storage and return public URL."""
    try:
        logger.info(f"Uploading to public bucket: {bucket_name}, path: {file_path}")
        
        # Upload file to Supabase storage with upsert flag
        response = supabase.storage.from_(bucket_name).upload(
            file_path,
            file_content,
            {
                "content-type": content_type or "application/octet-stream", 
                "upsert": "true",  # Allow overwriting
                "cache-control": "3600"  # Cache for 1 hour
            }
        )
        
        # For public buckets, get the public URL directly
        public_url = supabase.storage.from_(bucket_name).get_public_url(file_path)
        logger.info(f"Successfully uploaded. Public URL: {public_url}")
        
        return public_url
            
    except Exception as e:
        logger.error(f"Error uploading to Supabase storage: {e}", exc_info=True)
        return None

def get_file_extension_from_mime(mime_type: str) -> str:
    """Get file extension from MIME type."""
    mime_to_ext = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.ms-excel": ".xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    }
    return mime_to_ext.get(mime_type, ".bin")

# ---------------------------------------------------------------------
# NEW FUNCTION: clear_user_cache - CLEARS ALL USER CACHE
# ---------------------------------------------------------------------
def clear_user_cache(whatsapp_number: str, supabase) -> bool:
    """Clear user's cached state and data when returning to main menu.
    
    This function resets:
    - temp_data in database
    - state to IDLE
    - module to None
    - clinic_id and pending_module (for routing)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        whatsapp_number_norm = whatsapp_number.lstrip('+').strip()
        
        # Clear all cached data in database
        supabase.table("whatsapp_users").update({
            "temp_data": {},
            "state": "IDLE",
            "module": None
        }).eq("whatsapp_number", whatsapp_number_norm).execute()
        
        logger.info(f"Cleared all cache for {whatsapp_number}")
        return True
    except Exception as e:
        logger.error(f"Error clearing cache for {whatsapp_number}: {e}")
        return False