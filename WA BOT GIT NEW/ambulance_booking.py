# ambulance_booking.py - COMPLETE VERSION WITH FIXED TRANSLATION FORMATTING
import logging
import uuid
import time
import json
import os
import base64
import mimetypes
import re  # Added for regex pattern matching
from datetime import datetime, timedelta
from utils import (
    send_whatsapp_message, 
    gt_tt,
    gt_t_tt,
    gt_dt_tt,
    calculate_distance,
    download_whatsapp_media,
    upload_to_supabase_storage,
    get_file_extension_from_mime,
    geocode_address,
    send_location_request,
    translate_template  # Added for static text translation
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Define the sequence of questions for ambulance booking (Home to Hospital) - REMOVED AGE, ADDED RETURN SERVICE
BOOKING_QUESTIONS = [
    {
        "key": "patient_name",
        "question": "1. Patient full name",
        "example": "Example: Ahmad bin Abdullah",
        "state": "BOOKING_PATIENT_NAME"
    },
    {
        "key": "patient_ic",
        "question": "2. Patient IC number",
        "example": "Example: 801212-14-5678",
        "state": "BOOKING_PATIENT_IC",
        "validation": "ic"  # Add validation type
    },
    {
        "key": "patient_phone",
        "question": "3. Patient phone number",
        "example": "Example: 012-3456789",
        "state": "BOOKING_PATIENT_PHONE"
    },
    {
        "key": "emergency_name",
        "question": "4. Emergency contact name",
        "example": "Example: Siti binti Mohamad",
        "state": "BOOKING_EMERGENCY_NAME"
    },
    {
        "key": "emergency_phone",
        "question": "5. Emergency contact phone",
        "example": "Example: 019-8765432",
        "state": "BOOKING_EMERGENCY_PHONE"
    }
]

# Default provider ID - use this UUID for all bookings
DEFAULT_PROVIDER_ID = "11111111-1111-1111-1111-111111111111"

# Define 2-hour time slots
TIME_SLOTS = {
    "AM": [
        {"id": "am_0000_0145", "label": "12:00 AM - 01:45 AM", "start_hour": 0, "end_hour": 1},
        {"id": "am_0200_0345", "label": "02:00 AM - 03:45 AM", "start_hour": 2, "end_hour": 3},
        {"id": "am_0400_0545", "label": "04:00 AM - 05:45 AM", "start_hour": 4, "end_hour": 5},
        {"id": "am_0600_0745", "label": "06:00 AM - 07:45 AM", "start_hour": 6, "end_hour": 7},
        {"id": "am_0800_0945", "label": "08:00 AM - 09:45 AM", "start_hour": 8, "end_hour": 9},
        {"id": "am_1000_1145", "label": "10:00 AM - 11:45 AM", "start_hour": 10, "end_hour": 11}
    ],
    "PM": [
        {"id": "pm_1200_1345", "label": "12:00 PM - 01:45 PM", "start_hour": 12, "end_hour": 13},
        {"id": "pm_1400_1545", "label": "02:00 PM - 03:45 PM", "start_hour": 14, "end_hour": 15},
        {"id": "pm_1600_1745", "label": "04:00 PM - 05:45 PM", "start_hour": 16, "end_hour": 17},
        {"id": "pm_1800_1945", "label": "06:00 PM - 07:45 PM", "start_hour": 18, "end_hour": 19},
        {"id": "pm_2000_2145", "label": "08:00 PM - 09:45 PM", "start_hour": 20, "end_hour": 21},
        {"id": "pm_2200_2345", "label": "10:00 PM - 11:45 PM", "start_hour": 22, "end_hour": 23}
    ]
}

def normalize_phone(phone: str) -> str:
    """Remove non-digit characters."""
    if not phone:
        return ""
    return "".join(filter(str.isdigit, phone))

def format_ic_number(ic_input: str) -> str:
    """
    Format IC number to 12 digits without separators.
    Accepts formats like: 801212-14-5678, 801212145678, 801212 14 5678
    Returns: 12-digit string or None if invalid
    """
    if not ic_input:
        return None
    
    # Remove all non-digit characters
    digits_only = re.sub(r'\D', '', ic_input)
    
    # Check if we have exactly 12 digits
    if len(digits_only) != 12:
        return None
    
    return digits_only

def validate_ic_number(ic_input: str) -> bool:
    """
    Validate IC number format.
    Returns True if valid 12-digit IC (after removing non-digits), False otherwise.
    """
    digits_only = re.sub(r'\D', '', ic_input)
    return len(digits_only) == 12

def get_or_create_ids(supabase, whatsapp_number: str, user_name: str, patient_name: str, patient_ic: str):
    """
    Logic matches React 'getOrCreateWhatsappUserAndPatient':
    1. Find or Create WhatsApp User
    2. Find or Create Patient (linked to WA User)
    """
    try:
        # 1. Normalize inputs
        # Remove + from whatsapp usually standardizes it for DB
        normalized_wa = normalize_phone(whatsapp_number)
        clean_ic = format_ic_number(patient_ic)  # Use the new formatting function
        
        wa_uuid = None
        patient_uuid = None

        # ---------------------------------------------------------
        # Step A: Get or Create WhatsApp User
        # ---------------------------------------------------------
        # Try to find existing user
        response = supabase.table("whatsapp_users").select("id").eq("whatsapp_number", normalized_wa).execute()
        
        if response.data and len(response.data) > 0:
            wa_uuid = response.data[0]['id']
        else:
            # Create new user
            new_user_data = {
                "whatsapp_number": normalized_wa,
                "user_name": user_name or "Unknown", # Use WhatsApp profile name or Patient Name
                "language": "en",
                "module": "ambulance_booking",
                "state": "IDLE"
            }
            res = supabase.table("whatsapp_users").insert(new_user_data).execute()
            if res.data:
                wa_uuid = res.data[0]['id']

        if not wa_uuid:
            logger.error("Failed to generate WhatsApp User ID")
            return None, None

        # ---------------------------------------------------------
        # Step B: Get or Create Patient ID
        # ---------------------------------------------------------
        # Try to find by IC
        if clean_ic:
            pat_res = supabase.table("patient_id").select("id").eq("ic_passport", clean_ic).execute()
            
            if pat_res.data and len(pat_res.data) > 0:
                patient_uuid = pat_res.data[0]['id']
                
                # Update the link to this WhatsApp user
                supabase.table("patient_id").update({
                    "wa_user_id": wa_uuid,
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }).eq("id", patient_uuid).execute()
            else:
                # Create new patient with IC
                new_pat_data = {
                    "patient_name": patient_name,
                    "ic_passport": clean_ic,
                    "nationality": "Malaysian", # Default as per React logic
                    "wa_user_id": wa_uuid
                }
                res = supabase.table("patient_id").insert(new_pat_data).execute()
                if res.data:
                    patient_uuid = res.data[0]['id']
        else:
            # No IC provided? Create new patient entry without IC
            new_pat_data = {
                "patient_name": patient_name,
                "ic_passport": None,
                "wa_user_id": wa_uuid
            }
            res = supabase.table("patient_id").insert(new_pat_data).execute()
            if res.data:
                patient_uuid = res.data[0]['id']

        return wa_uuid, patient_uuid

    except Exception as e:
        logger.error(f"Error in get_or_create_ids: {e}", exc_info=True)
        return None, None

def handle_booking_start(whatsapp_number: str, user_id: str, supabase, user_data: dict):
    """Start the ambulance booking process (Home to Hospital)."""
    try:
        logger.info(f"Starting ambulance booking (Home to Hospital) for {whatsapp_number}")
        
        # Generate booking ID
        booking_id = f"BKG{int(time.time()) % 1000000:06d}"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Store initial data
        user_data[whatsapp_number]["temp_data"] = {
            "booking_id": booking_id,
            "service_type": "home_to_hosp",
            "answers": {},
            "current_question_index": 0,
            "start_time": current_time,
            "schedule_data": {},  # Store date and time selection data
            "attachments": [],    # Store attachment URLs
            "remarks": "",        # Store additional remarks
            "return_service": False  # Store return service preference as boolean
        }
        user_data[whatsapp_number]["state"] = "BOOKING_STARTED"
        
        # Build confirmation text line by line
        confirmation_lines = [
            "📅 *AMBULANCE SERVICE: HOME TO HOSPITAL*",
            "",
            f"Booking ID: {booking_id}",
            f"Time: {current_time}",
            "",
            "This service helps patients travel from home to hospital for appointments.",
            "",
            "We'll collect information for your ambulance booking.",
            "Please answer the following questions one by one.",
            "",
            "*IMPORTANT:*",
            "• Please provide accurate information",
            "• For addresses, include full address with postcode",
            "• After answering all questions, you can upload documents/attachments",
            "",
            "---",
            "*QUESTIONS TO FOLLOW:*",
            "1. Patient full name",
            "2. Patient IC number",
            "3. Patient phone number",
            "4. Emergency contact name",
            "5. Emergency contact phone",
            "6. Pickup address (with location sharing option)",
            "7. Hospital name (we'll find the address automatically)",
            "*After these questions, we'll ask for attachments and schedule pickup.*",
            "",
            "You can cancel anytime by typing 'cancel'."
        ]
        
        # Translate each line separately
        translated_lines = []
        for line in confirmation_lines:
            if line.startswith("Booking ID:") or line.startswith("Time:") or line.startswith("📅") or "cancel" in line.lower():
                translated_lines.append(line)
            elif line.strip():
                translated_lines.append(translate_template(whatsapp_number, line, supabase))
            else:
                translated_lines.append(line)
        
        confirmation_text = "\n".join(translated_lines)
        
        # Send confirmation message
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": confirmation_text}},
            supabase
        )
        
        # Wait a moment before sending first question
        time.sleep(1)
        
        # Send first question
        send_next_booking_question(whatsapp_number, user_data, supabase)
        
        return False
        
    except Exception as e:
        logger.error(f"Error starting ambulance booking for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error starting booking. Please try again.", supabase)}},
            supabase
        )
        return False

def send_next_booking_question(whatsapp_number: str, user_data: dict, supabase):
    """Send the next question in the sequence."""
    try:
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        current_index = temp_data.get("current_question_index", 0)
        
        if current_index < len(BOOKING_QUESTIONS):
            question_data = BOOKING_QUESTIONS[current_index]
            
            # Build question with example separately
            question_line = translate_template(whatsapp_number, question_data["question"], supabase)
            example_line = translate_template(whatsapp_number, question_data["example"], supabase)
            question_text = f"{question_line}\n{example_line}"
            
            # Send the question
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": question_text}},
                supabase
            )
            
            # Update state
            user_data[whatsapp_number]["state"] = question_data["state"]
        else:
            # All questions answered, ask for pickup address with location option
            ask_pickup_address_option(whatsapp_number, user_data, supabase)
            
    except Exception as e:
        logger.error(f"Error sending next question to {whatsapp_number}: {e}", exc_info=True)

def ask_pickup_address_option(whatsapp_number: str, user_data: dict, supabase):
    """Ask for pickup address with option to share location or type manually."""
    try:
        # Build body text line by line
        body_lines = [
            "6. *Pickup address (Home address)*",
            "",
            "How would you like to provide your pickup address?",
            "",
            "• *Share Location:* Send your current location (recommended)",
            "• *Type Address:* Enter your full address manually",
            "",
            "Example of manual address:",
            "No 12, Jalan Merdeka, Taman Tun Dr Ismail, 60000 Kuala Lumpur"
        ]
        
        # Translate each line
        translated_body_lines = [translate_template(whatsapp_number, line, supabase) for line in body_lines]
        body_text = "\n".join(translated_body_lines)
        
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "📍 Pickup Address", supabase)
                },
                "body": {
                    "text": body_text
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "pickup_share_location",
                                "title": translate_template(whatsapp_number, "📍 Share Location", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "pickup_type_address",
                                "title": translate_template(whatsapp_number, "📝 Type Address", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "BOOKING_PICKUP_ADDRESS_OPTION"
        
    except Exception as e:
        logger.error(f"Error asking pickup address option for {whatsapp_number}: {e}", exc_info=True)

def ask_pickup_address_text(whatsapp_number: str, user_data: dict, supabase):
    """Ask user to type pickup address manually."""
    try:
        # Build message line by line
        message_lines = [
            "Please type your full pickup address:",
            "",
            "Example:",
            "No 12, Jalan Merdeka, Taman Tun Dr Ismail, 60000 Kuala Lumpur",
            "",
            "Include:",
            "• House/building number",
            "• Street name",
            "• Area/Taman",
            "• Postcode and City",
            "• State"
        ]
        
        # Translate each line
        translated_lines = [translate_template(whatsapp_number, line, supabase) for line in message_lines]
        message_text = "\n".join(translated_lines)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": message_text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "BOOKING_PICKUP_ADDRESS_TEXT"
        
    except Exception as e:
        logger.error(f"Error asking pickup address text for {whatsapp_number}: {e}", exc_info=True)

def confirm_pickup_address(whatsapp_number: str, user_data: dict, supabase, address: str, latitude: float = None, longitude: float = None):
    """Ask user to confirm the geocoded pickup address."""
    try:
        # Store the original address and coordinates
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        temp_data["answers"]["pickup_address_original"] = address
        temp_data["answers"]["pickup_latitude"] = latitude
        temp_data["answers"]["pickup_longitude"] = longitude
        
        # Try to geocode the address for better formatting
        try:
            geocoded = geocode_address(address)
            if geocoded and geocoded.get("formatted_address"):
                formatted_address = geocoded.get("formatted_address")
                temp_data["answers"]["pickup_address_formatted"] = formatted_address
                temp_data["answers"]["pickup_latitude"] = geocoded.get("latitude", latitude)
                temp_data["answers"]["pickup_longitude"] = geocoded.get("longitude", longitude)
                
                # Use formatted address for confirmation
                display_address = formatted_address
            else:
                display_address = address
        except Exception as e:
            logger.error(f"Error geocoding pickup address: {e}")
            display_address = address
        
        user_data[whatsapp_number]["temp_data"] = temp_data
        
        # Build confirmation message
        if len(display_address) > 200:
            display_address = display_address[:200] + "..."
        
        confirmation_lines = [
            "We found this address:",
            "",
            display_address,
            "",
            "Is this your correct pickup address?"
        ]
        
        translated_lines = [translate_template(whatsapp_number, line, supabase) for line in confirmation_lines]
        confirmation_text = "\n".join(translated_lines)
        
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "📍 Pickup Address Found", supabase)
                },
                "body": {
                    "text": confirmation_text
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "pickup_address_yes",
                                "title": translate_template(whatsapp_number, "✅ Yes, Correct", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "pickup_address_edit",
                                "title": translate_template(whatsapp_number, "✏️ Edit Address", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "BOOKING_PICKUP_ADDRESS_CONFIRM"
        
    except Exception as e:
        logger.error(f"Error confirming pickup address for {whatsapp_number}: {e}", exc_info=True)
        # If confirmation fails, proceed with the original address
        temp_data["answers"]["pickup_address"] = address
        ask_hospital_name(whatsapp_number, user_data, supabase)

def ask_hospital_name(whatsapp_number: str, user_data: dict, supabase):
    """Ask for hospital name."""
    try:
        # Build message line by line
        message_lines = [
            "7. *Hospital name*",
            "",
            "Please type the name of the hospital:",
            "",
            "Examples:",
            "• Hospital Kuala Lumpur",
            "• Sunway Medical Centre",
            "• Pantai Hospital Kuala Lumpur",
            "• University Malaya Medical Centre",
            "",
            "We'll automatically find the address for you."
        ]
        
        # Translate each line
        translated_lines = [translate_template(whatsapp_number, line, supabase) for line in message_lines]
        message_text = "\n".join(translated_lines)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": message_text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "BOOKING_HOSPITAL_NAME"
        
    except Exception as e:
        logger.error(f"Error asking hospital name for {whatsapp_number}: {e}", exc_info=True)

def confirm_hospital_address(whatsapp_number: str, user_data: dict, supabase, hospital_name: str, hospital_address: str):
    """Ask user to confirm the automatically found hospital address."""
    try:
        # Build confirmation message
        confirmation_lines = [
            f"We found this address for *{hospital_name}*:",
            "",
            hospital_address,
            "",
            "Is this the correct hospital address?"
        ]
        
        translated_lines = [translate_template(whatsapp_number, line, supabase) for line in confirmation_lines]
        confirmation_text = "\n".join(translated_lines)
        
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "🏥 Hospital Address Found", supabase)
                },
                "body": {
                    "text": confirmation_text
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "hospital_address_yes",
                                "title": translate_template(whatsapp_number, "✅ Yes, Correct", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "hospital_address_no",
                                "title": translate_template(whatsapp_number, "❌ No, Different", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "BOOKING_HOSPITAL_ADDRESS_CONFIRM"
        
    except Exception as e:
        logger.error(f"Error confirming hospital address for {whatsapp_number}: {e}", exc_info=True)

def ask_hospital_address_manual(whatsapp_number: str, user_data: dict, supabase):
    """Ask user to type hospital address manually."""
    try:
        # Build message line by line
        message_lines = [
            "Please type the hospital address manually:",
            "",
            "Example:",
            "Jalan Pahang, 53000 Kuala Lumpur, Wilayah Persekutuan Kuala Lumpur",
            "",
            "Include full address with postcode and state."
        ]
        
        # Translate each line
        translated_lines = [translate_template(whatsapp_number, line, supabase) for line in message_lines]
        message_text = "\n".join(translated_lines)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": message_text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "BOOKING_HOSPITAL_ADDRESS_MANUAL"
        
    except Exception as e:
        logger.error(f"Error asking hospital address manual for {whatsapp_number}: {e}", exc_info=True)

def ask_for_attachments(whatsapp_number: str, user_data: dict, supabase):
    """Ask user to upload attachments."""
    try:
        # Build body text line by line
        body_lines = [
            "You can upload attachments (photos/documents) related to this booking.",
            "",
            "Examples:",
            "• Medical reports",
            "• Prescriptions",
            "• Doctor's referral letters",
            "• Insurance documents",
            "",
            "You can upload multiple attachments. When done, click 'Next'."
        ]
        
        # Translate each line
        translated_body_lines = [translate_template(whatsapp_number, line, supabase) for line in body_lines]
        body_text = "\n".join(translated_body_lines)
        
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "📎 Attachments", supabase)
                },
                "body": {
                    "text": body_text
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "booking_attach_next",
                                "title": translate_template(whatsapp_number, "Next", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "booking_attach_skip",
                                "title": translate_template(whatsapp_number, "Skip", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "BOOKING_ATTACHMENTS"
        
    except Exception as e:
        logger.error(f"Error asking for attachments for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error asking for attachments. Please try again.", supabase)}},
            supabase
        )

def ask_remarks(whatsapp_number: str, user_data: dict, supabase):
    """Ask for additional remarks with skip option."""
    try:
        # Build body text line by line
        body_lines = [
            "Do you have any additional remarks or special instructions?",
            "",
            "Examples:",
            "• Specific route preferences",
            "• Special medical equipment needed",
            "• Additional patient information",
            "",
            "You can add remarks or skip to continue."
        ]
        
        # Translate each line
        translated_body_lines = [translate_template(whatsapp_number, line, supabase) for line in body_lines]
        body_text = "\n".join(translated_body_lines)
        
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "📝 Remarks", supabase)
                },
                "body": {
                    "text": body_text
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "booking_remarks_add",
                                "title": translate_template(whatsapp_number, "Add Remarks", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "booking_remarks_skip",
                                "title": translate_template(whatsapp_number, "Skip", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "BOOKING_REMARKS"
        
    except Exception as e:
        logger.error(f"Error asking for remarks for {whatsapp_number}: {e}", exc_info=True)

def ask_remarks_text(whatsapp_number: str, user_data: dict, supabase):
    """Ask user to type remarks."""
    try:
        # Build message line by line
        message_lines = [
            "Please type your remarks or special instructions:",
            "",
            "Examples:",
            "• Patient needs wheelchair assistance",
            "• Please use back entrance",
            "• Patient is fasting",
            "• Special handling requirements"
        ]
        
        # Translate each line
        translated_lines = [translate_template(whatsapp_number, line, supabase) for line in message_lines]
        message_text = "\n".join(translated_lines)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": message_text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "BOOKING_REMARKS_TEXT"
        
    except Exception as e:
        logger.error(f"Error asking remarks text for {whatsapp_number}: {e}", exc_info=True)

def ask_return_service(whatsapp_number: str, user_data: dict, supabase):
    """Ask if user needs return service."""
    try:
        # Build body text line by line
        body_lines = [
            "Do you need return service (from hospital back to home)?",
            "",
            "This is for scheduling a return trip on the same day after the hospital appointment."
        ]
        
        # Translate each line
        translated_body_lines = [translate_template(whatsapp_number, line, supabase) for line in body_lines]
        body_text = "\n".join(translated_body_lines)
        
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "🔄 Return Service", supabase)
                },
                "body": {
                    "text": body_text
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "return_service_yes",
                                "title": translate_template(whatsapp_number, "✅ Yes", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "return_service_no",
                                "title": translate_template(whatsapp_number, "❌ No", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "BOOKING_RETURN_SERVICE"
        
    except Exception as e:
        logger.error(f"Error asking return service for {whatsapp_number}: {e}", exc_info=True)

def handle_booking_response(whatsapp_number: str, user_id: str, supabase, user_data: dict, message):
    """Handle user's response during ambulance booking."""
    try:
        # Check for cancellation
        if message.get("type") == "text":
            user_text = message["text"]["body"].strip().lower()
            if user_text == "cancel":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Ambulance booking cancelled. Returning to main menu.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                from utils import send_interactive_menu
                send_interactive_menu(whatsapp_number, supabase)
                return True
        
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        current_state = user_data[whatsapp_number].get("state", "")
        
        # Handle pickup address option
        if current_state == "BOOKING_PICKUP_ADDRESS_OPTION":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "pickup_share_location":
                    # Build location request message
                    location_lines = [
                        "Please share your location using the button below:",
                        "",
                        "1. Tap the location icon 📍",
                        "2. Select 'Share Location'",
                        "3. Choose 'Send your current location'"
                    ]
                    
                    translated_lines = [translate_template(whatsapp_number, line, supabase) for line in location_lines]
                    location_text = "\n".join(translated_lines)
                    
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": location_text}},
                        supabase
                    )
                    time.sleep(1)
                    send_location_request(whatsapp_number, supabase)
                    user_data[whatsapp_number]["state"] = "BOOKING_PICKUP_ADDRESS_LOCATION"
                    
                elif button_id == "pickup_type_address":
                    # Ask for manual address input
                    ask_pickup_address_text(whatsapp_number, user_data, supabase)
            return False
        
        # Handle location sharing for pickup address
        elif current_state == "BOOKING_PICKUP_ADDRESS_LOCATION":
            if message.get("type") == "location":
                location = message["location"]
                latitude = location.get("latitude")
                longitude = location.get("longitude")
                address = location.get("name", location.get("address", "Location shared"))
                
                # Geocode to get full address if needed
                if address == "Location shared" or not address:
                    try:
                        geocoded = geocode_address(f"{latitude},{longitude}")
                        if geocoded:
                            address = geocoded.get("formatted_address", "Location shared")
                    except Exception as e:
                        logger.error(f"Error geocoding location: {e}")
                
                # Ask for confirmation of the pickup address
                confirm_pickup_address(whatsapp_number, user_data, supabase, address, latitude, longitude)
            elif message.get("type") == "text":
                # User might have typed address instead
                address = message["text"]["body"].strip()
                if address:
                    # Ask for confirmation of the typed address
                    confirm_pickup_address(whatsapp_number, user_data, supabase, address)
            return False
        
        # Handle manual pickup address input
        elif current_state == "BOOKING_PICKUP_ADDRESS_TEXT":
            if message.get("type") == "text":
                address = message["text"]["body"].strip()
                if address:
                    # Ask for confirmation of the typed address
                    confirm_pickup_address(whatsapp_number, user_data, supabase, address)
            return False
        
        # Handle pickup address confirmation
        elif current_state == "BOOKING_PICKUP_ADDRESS_CONFIRM":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "pickup_address_yes":
                    # Use the formatted address if available, otherwise use original
                    formatted_address = temp_data["answers"].get("pickup_address_formatted")
                    final_address = formatted_address if formatted_address else temp_data["answers"].get("pickup_address_original", "")
                    
                    temp_data["answers"]["pickup_address"] = final_address
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Build confirmation message
                    if len(final_address) > 100:
                        address_display = final_address[:100] + "..."
                    else:
                        address_display = final_address
                    
                    confirmation_lines = [
                        "✅ *Pickup address confirmed!*",
                        "",
                        f"Address: {address_display}",
                        "",
                        "Now let's proceed to hospital details."
                    ]
                    
                    translated_lines = [translate_template(whatsapp_number, line, supabase) for line in confirmation_lines]
                    confirmation_text = "\n".join(translated_lines)
                    
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": confirmation_text}},
                        supabase
                    )
                    time.sleep(1)
                    ask_hospital_name(whatsapp_number, user_data, supabase)
                    
                elif button_id == "pickup_address_edit":
                    # Build edit request message
                    edit_lines = [
                        "Please type the corrected pickup address:",
                        "",
                        "Example:",
                        "No 12, Jalan Merdeka, Taman Tun Dr Ismail, 60000 Kuala Lumpur"
                    ]
                    
                    translated_lines = [translate_template(whatsapp_number, line, supabase) for line in edit_lines]
                    edit_text = "\n".join(translated_lines)
                    
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": edit_text}},
                        supabase
                    )
                    user_data[whatsapp_number]["state"] = "BOOKING_PICKUP_ADDRESS_EDIT"
            return False
        
        # Handle pickup address edit
        elif current_state == "BOOKING_PICKUP_ADDRESS_EDIT":
            if message.get("type") == "text":
                address = message["text"]["body"].strip()
                if address:
                    # Ask for confirmation of the edited address
                    confirm_pickup_address(whatsapp_number, user_data, supabase, address)
            return False
        
        # Handle hospital name input
        elif current_state == "BOOKING_HOSPITAL_NAME":
            if message.get("type") == "text":
                hospital_name = message["text"]["body"].strip()
                if hospital_name:
                    temp_data["answers"]["hospital_name"] = hospital_name
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Build searching message
                    search_lines = [
                        f"🔍 Searching for *{hospital_name}*..."
                    ]
                    
                    translated_lines = [translate_template(whatsapp_number, line, supabase) for line in search_lines]
                    search_text = "\n".join(translated_lines)
                    
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": search_text}},
                        supabase
                    )
                    
                    # Try to geocode hospital name
                    try:
                        geocoded = geocode_address(hospital_name)
                        
                        if geocoded and geocoded.get("formatted_address"):
                            hospital_address = geocoded.get("formatted_address")
                            temp_data["answers"]["hospital_address_geocoded"] = hospital_address
                            temp_data["answers"]["hospital_latitude"] = geocoded.get("latitude")
                            temp_data["answers"]["hospital_longitude"] = geocoded.get("longitude")
                            user_data[whatsapp_number]["temp_data"] = temp_data
                            
                            # Ask for confirmation
                            time.sleep(1)
                            confirm_hospital_address(whatsapp_number, user_data, supabase, hospital_name, hospital_address)
                        else:
                            # Could not find address, ask for manual input
                            not_found_lines = [
                                f"❌ Could not find address for *{hospital_name}*",
                                "",
                                "Please provide the address manually."
                            ]
                            
                            translated_lines = [translate_template(whatsapp_number, line, supabase) for line in not_found_lines]
                            not_found_text = "\n".join(translated_lines)
                            
                            send_whatsapp_message(
                                whatsapp_number,
                                "text",
                                {"text": {"body": not_found_text}},
                                supabase
                            )
                            ask_hospital_address_manual(whatsapp_number, user_data, supabase)
                    except Exception as e:
                        logger.error(f"Error geocoding hospital name: {e}")
                        # Ask for manual input
                        ask_hospital_address_manual(whatsapp_number, user_data, supabase)
            return False
        
        # Handle hospital address confirmation
        elif current_state == "BOOKING_HOSPITAL_ADDRESS_CONFIRM":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "hospital_address_yes":
                    # Use the geocoded address
                    temp_data["answers"]["hospital_address"] = temp_data["answers"].get("hospital_address_geocoded", "")
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Proceed to attachments
                    ask_for_attachments(whatsapp_number, user_data, supabase)
                    
                elif button_id == "hospital_address_no":
                    # Ask for manual input
                    ask_hospital_address_manual(whatsapp_number, user_data, supabase)
            return False
        
        # Handle manual hospital address input
        elif current_state == "BOOKING_HOSPITAL_ADDRESS_MANUAL":
            if message.get("type") == "text":
                hospital_address = message["text"]["body"].strip()
                if hospital_address:
                    temp_data["answers"]["hospital_address"] = hospital_address
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Proceed to attachments
                    ask_for_attachments(whatsapp_number, user_data, supabase)
            return False
        
        # Handle attachment states
        elif current_state == "BOOKING_ATTACHMENTS":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "booking_attach_next":
                    # Move to remarks
                    ask_remarks(whatsapp_number, user_data, supabase)
                elif button_id == "booking_attach_skip":
                    # Skip attachments, move to remarks
                    temp_data["attachments"] = []
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    ask_remarks(whatsapp_number, user_data, supabase)
            elif message.get("type") in ["image", "document"]:
                # Handle attachment upload
                handle_attachment(whatsapp_number, user_data, supabase, message)
            return False
        
        # Handle remarks option
        elif current_state == "BOOKING_REMARKS":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "booking_remarks_add":
                    ask_remarks_text(whatsapp_number, user_data, supabase)
                elif button_id == "booking_remarks_skip":
                    temp_data["remarks"] = ""
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    ask_return_service(whatsapp_number, user_data, supabase)
            return False
        
        # Handle remarks text input
        elif current_state == "BOOKING_REMARKS_TEXT":
            if message.get("type") == "text":
                remarks_text = message["text"]["body"].strip()
                if remarks_text:
                    temp_data["remarks"] = remarks_text
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                ask_return_service(whatsapp_number, user_data, supabase)
            return False
        
        # Handle return service
        elif current_state == "BOOKING_RETURN_SERVICE":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "return_service_yes":
                    temp_data["return_service"] = True
                    
                    # Build confirmation message
                    return_lines = [
                        "✅ *Return service added*",
                        "",
                        "We'll schedule both trips (to hospital and return).",
                        "Our team will coordinate the return timing with you."
                    ]
                    
                    translated_lines = [translate_template(whatsapp_number, line, supabase) for line in return_lines]
                    return_text = "\n".join(translated_lines)
                    
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": return_text}},
                        supabase
                    )
                else:
                    temp_data["return_service"] = False
                
                user_data[whatsapp_number]["temp_data"] = temp_data
                
                # Wait a moment before scheduling
                time.sleep(2)
                
                # Ask for schedule date
                ask_schedule_date(whatsapp_number, user_data, supabase, "pickup")
            return False
        
        # Handle schedule date and time states
        elif current_state == "BOOKING_SCHEDULE_DATE":
            handle_schedule_date_response(whatsapp_number, user_data, supabase, message)
        elif current_state == "BOOKING_SCHEDULE_DATE_OTHER":
            handle_date_other_response(whatsapp_number, user_data, supabase, message)
        elif current_state == "BOOKING_SCHEDULE_AMPM":
            handle_ampm_response(whatsapp_number, user_data, supabase, message)
        elif current_state == "BOOKING_SCHEDULE_TIMESLOT":
            handle_timeslot_response(whatsapp_number, user_data, supabase, message)
        elif current_state == "BOOKING_SCHEDULE_INTERVAL":
            handle_interval_response(whatsapp_number, user_data, supabase, message)
        else:
            # Handle regular question responses with validation
            current_index = temp_data.get("current_question_index", 0)
            
            if current_index < len(BOOKING_QUESTIONS):
                question_data = BOOKING_QUESTIONS[current_index]
                answer_key = question_data["key"]
                answer = message["text"]["body"].strip() if message.get("type") == "text" else ""
                
                # Validate answer
                if not answer:
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "Please provide a valid answer.", supabase)}},
                        supabase
                    )
                    return False
                
                # Special validation for IC number
                if answer_key == "patient_ic":
                    if not validate_ic_number(answer):
                        # Build error message line by line
                        error_lines = [
                            "❌ *Invalid IC number format*",
                            "",
                            "IC must be 12 digits.",
                            "Accepted formats:",
                            "• 801212-14-5678",
                            "• 801212145678",
                            "• 801212 14 5678",
                            "",
                            "Please re-enter the patient's IC number:"
                        ]
                        
                        translated_lines = [translate_template(whatsapp_number, line, supabase) for line in error_lines]
                        error_text = "\n".join(translated_lines)
                        
                        send_whatsapp_message(
                            whatsapp_number,
                            "text",
                            {"text": {"body": error_text}},
                            supabase
                        )
                        return False
                    
                    # Format the IC to 12 digits without separators
                    answer = format_ic_number(answer)
                
                # Store answer
                temp_data["answers"][answer_key] = answer
                temp_data["current_question_index"] = current_index + 1
                user_data[whatsapp_number]["temp_data"] = temp_data
                
                # Send next question or ask for pickup address
                send_next_booking_question(whatsapp_number, user_data, supabase)
            else:
                # All questions answered, ask for pickup address with location option
                ask_pickup_address_option(whatsapp_number, user_data, supabase)
                
        return False
        
    except Exception as e:
        logger.error(f"Error handling booking response for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing your answer. Please try again.", supabase)}},
            supabase
        )
        return False

def handle_attachment(whatsapp_number: str, user_data: dict, supabase, message):
    """Handle attachment upload and save to Supabase bucket."""
    try:
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        attachments = temp_data.get("attachments", [])
        booking_id = temp_data.get("booking_id", "")
        
        # Get WhatsApp media ID and metadata
        media_id = None
        file_name = None
        mime_type = None
        caption = None
        
        if message.get("type") == "image":
            media_id = message["image"]["id"]
            mime_type = message["image"].get("mime_type", "image/jpeg")
            caption = message["image"].get("caption")
            file_extension = get_file_extension_from_mime(mime_type) or ".jpg"
            file_name = f"image_{int(time.time())}{file_extension}"
            
        elif message.get("type") == "document":
            media_id = message["document"]["id"]
            mime_type = message["document"].get("mime_type", "application/octet-stream")
            file_name = message["document"].get("filename", f"document_{int(time.time())}")
            
        else:
            # Build unsupported file type message
            error_lines = [
                "❌ Unsupported file type.",
                "Please send images (JPEG, PNG) or documents (PDF, DOC) only."
            ]
            
            translated_lines = [translate_template(whatsapp_number, line, supabase) for line in error_lines]
            error_text = "\n".join(translated_lines)
            
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": error_text}},
                supabase
            )
            return
        
        if not media_id:
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Error: Could not get file information. Please try again.", supabase)}},
                supabase
            )
            return
        
        # Download the media from WhatsApp
        try:
            logger.info(f"Downloading media {media_id} for booking {booking_id}")
            file_content = download_whatsapp_media(media_id)
            
            if not file_content:
                logger.error("Failed to download media from WhatsApp")
                
                # Build download error message
                error_lines = [
                    "❌ Failed to download file from WhatsApp.",
                    "Please try sending the file again."
                ]
                
                translated_lines = [translate_template(whatsapp_number, line, supabase) for line in error_lines]
                error_text = "\n".join(translated_lines)
                
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": error_text}},
                    supabase
                )
                return
            
            # Generate unique filename with booking ID
            unique_id = str(uuid.uuid4())[:8]
            safe_booking_id = booking_id.replace("/", "_").replace("\\", "_")
            final_file_name = f"{safe_booking_id}_{unique_id}_{file_name}"
            
            # Create folder structure: bookings/{booking_id}/{filename}
            bucket_path = f"bookings/{booking_id}/{final_file_name}"
            
            logger.info(f"Uploading to Supabase bucket: {bucket_path}")
            
            # Upload file to Supabase storage
            public_url = upload_to_supabase_storage(
                supabase, 
                'attachments', 
                bucket_path, 
                file_content, 
                mime_type
            )
            
            if not public_url:
                raise Exception("Failed to upload to Supabase storage")
            
            # Store attachment info
            attachment_info = {
                "type": "image" if message.get("type") == "image" else "document",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "filename": final_file_name,
                "original_filename": file_name,
                "mime_type": mime_type,
                "url": public_url,
                "storage_path": bucket_path,
                "caption": caption,
                "size_bytes": len(file_content)
            }
            
            attachments.append(attachment_info)
            temp_data["attachments"] = attachments
            user_data[whatsapp_number]["temp_data"] = temp_data
            
            # Build confirmation message
            file_size_mb = len(file_content) / (1024 * 1024)
            confirmation_lines = [
                "✅ *Attachment successfully saved!*",
                "",
                f"• File: {file_name[:40]}...",
                f"• Type: {attachment_info['type'].title()}",
                f"• Size: {file_size_mb:.2f} MB",
                f"• Total attachments: {len(attachments)}",
                "",
                "You can send more attachments or click 'Next' to continue."
            ]
            
            translated_lines = [translate_template(whatsapp_number, line, supabase) for line in confirmation_lines]
            confirmation_text = "\n".join(translated_lines)
            
            content = {
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": confirmation_text
                    },
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "booking_attach_next",
                                    "title": translate_template(whatsapp_number, "Next", supabase)
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "booking_attach_skip",
                                    "title": translate_template(whatsapp_number, "Skip", supabase)
                                }
                            }
                        ]
                    }
                }
            }
            
            send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
            
        except Exception as download_error:
            logger.error(f"Error downloading/uploading attachment for {whatsapp_number}: {download_error}", exc_info=True)
            
            # Build error message
            error_lines = [
                "❌ Failed to save attachment.",
                "Please try again or click 'Skip' to continue without attachments."
            ]
            
            translated_lines = [translate_template(whatsapp_number, line, supabase) for line in error_lines]
            error_text = "\n".join(translated_lines)
            
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": error_text}},
                supabase
            )
        
    except Exception as e:
        logger.error(f"Error handling attachment for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing attachment. Please try again.", supabase)}},
            supabase
        )

def ask_schedule_date(whatsapp_number: str, user_data: dict, supabase, schedule_type: str = "pickup"):
    """Ask for schedule date with interactive buttons."""
    try:
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        # Format dates for display
        today_str = today.strftime("%d/%m/%Y")
        tomorrow_str = tomorrow.strftime("%d/%m/%Y")
        
        schedule_text = "pickup" if schedule_type == "pickup" else "transfer"
        
        # Build body text line by line
        body_lines = [
            f"Please select the {schedule_text} date:",
            "",
            f"*Today:* {today_str}",
            f"*Tomorrow:* {tomorrow_str}",
            "",
            "If you need another date, select 'Others' and enter DD/MM/YYYY format."
        ]
        
        translated_body_lines = [translate_template(whatsapp_number, line, supabase) for line in body_lines]
        body_text = "\n".join(translated_body_lines)
        
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, f"📅 Select {schedule_text.title()} Date", supabase)
                },
                "body": {
                    "text": body_text
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "booking_date_today",
                                "title": translate_template(whatsapp_number, "Today", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "booking_date_tomorrow",
                                "title": translate_template(whatsapp_number, "Tomorrow", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "booking_date_other",
                                "title": translate_template(whatsapp_number, "Others", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "BOOKING_SCHEDULE_DATE"
        
    except Exception as e:
        logger.error(f"Error asking schedule date for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error scheduling date. Please try again.", supabase)}},
            supabase
        )

def ask_schedule_ampm(whatsapp_number: str, user_data: dict, supabase):
    """Ask for AM or PM selection."""
    try:
        content = {
            "interactive": {
                "type": "button",
                "body": {
                    "text": translate_template(whatsapp_number, "Please select AM or PM for the pickup time:", supabase)
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "booking_ampm_am",
                                "title": translate_template(whatsapp_number, "AM (12am - 11:45am)", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "booking_ampm_pm",
                                "title": translate_template(whatsapp_number, "PM (12pm - 11:45pm)", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "BOOKING_SCHEDULE_AMPM"
        
    except Exception as e:
        logger.error(f"Error asking AM/PM for {whatsapp_number}: {e}", exc_info=True)

def ask_schedule_timeslot(whatsapp_number: str, user_data: dict, supabase, period: str):
    """Ask for 2-hour time slot selection."""
    try:
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        schedule_data = temp_data.get("schedule_data", {})
        
        # Get time slots for the selected period
        slots = TIME_SLOTS.get(period, [])
        
        # Create sections with rows for time slot selection
        sections = []
        rows = []
        
        for i, slot in enumerate(slots):
            rows.append({
                "id": f"booking_slot_{slot['id']}",
                "title": slot["label"]
            })
            
            # Split into multiple sections to avoid exceeding row limit
            if (i + 1) % 3 == 0 or i == len(slots) - 1:
                sections.append({
                    "title": f"{period} Time Slots",
                    "rows": rows.copy()
                })
                rows = []
        
        # If only one section, remove the title to save space
        if len(sections) == 1:
            sections[0]["title"] = ""
        
        # Build body text line by line
        body_lines = [
            f"Please select a 2-hour time slot for pickup:",
            f"Selected Date: {schedule_data.get('date_display', 'N/A')}",
            f"Period: {period}",
            "",
            "After selecting a slot, you'll choose the exact 15-minute interval."
        ]
        
        translated_body_lines = [translate_template(whatsapp_number, line, supabase) for line in body_lines]
        body_text = "\n".join(translated_body_lines)
        
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, f"⏰ Select 2-Hour Slot ({period})", supabase)
                },
                "body": {
                    "text": body_text
                },
                "action": {
                    "button": translate_template(whatsapp_number, "Select Time Slot", supabase),
                    "sections": sections
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "BOOKING_SCHEDULE_TIMESLOT"
        
    except Exception as e:
        logger.error(f"Error asking time slot for {whatsapp_number}: {e}", exc_info=True)

def ask_schedule_minute(whatsapp_number: str, user_data: dict, supabase):
    """Ask for 15-minute interval selection within the chosen 2-hour slot."""
    try:
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        schedule_data = temp_data.get("schedule_data", {})
        
        # Get selected slot info
        slot_id = schedule_data.get("slot_id", "")
        period = schedule_data.get("period", "")
        
        # Parse start hour from slot ID
        slot_info = None
        for slot in TIME_SLOTS.get(period, []):
            if slot["id"] in slot_id:
                slot_info = slot
                break
        
        if not slot_info:
            logger.error(f"Could not find slot info for {slot_id}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Error selecting time. Please try again.", supabase)}},
                supabase
            )
            ask_schedule_ampm(whatsapp_number, user_data, supabase)
            return
        
        start_hour = slot_info["start_hour"]
        
        # Generate 15-minute intervals for this 2-hour slot
        intervals = []
        for hour_offset in range(2):  # 2 hours
            current_hour = start_hour + hour_offset
            for minute in [0, 15, 30, 45]:
                # Only include up to 01:45 for first hour, 03:45 for second hour, etc.
                if hour_offset == 1 and minute == 45:
                    continue  # Skip 45th minute of second hour
                
                # Format time
                display_hour = current_hour % 12
                if display_hour == 0:
                    display_hour = 12
                
                ampm = "AM" if current_hour < 12 else "PM"
                if period == "AM" and current_hour >= 12:
                    ampm = "PM"  # Edge case for 12:00 AM - 01:45 AM slot
                
                time_str = f"{display_hour}:{minute:02d} {ampm}"
                interval_id = f"{current_hour:02d}{minute:02d}"
                
                intervals.append({
                    "id": f"booking_interval_{interval_id}",
                    "title": time_str,
                    "hour": current_hour,
                    "minute": minute
                })
        
        # Create sections with rows for minute selection
        sections = []
        rows = []
        
        for i, interval in enumerate(intervals):
            rows.append({
                "id": interval["id"],
                "title": interval["title"]
            })
            
            # Split into multiple sections to avoid exceeding row limit
            if (i + 1) % 4 == 0 or i == len(intervals) - 1:
                sections.append({
                    "title": f"{slot_info['label']}",
                    "rows": rows.copy()
                })
                rows = []
        
        # If only one section, remove the title to save space
        if len(sections) == 1:
            sections[0]["title"] = ""
        
        # Build body text line by line
        body_lines = [
            f"Please select the exact pickup time:",
            f"Selected Date: {schedule_data.get('date_display', 'N/A')}",
            f"Selected Slot: {slot_info['label']}",
            "",
            "Choose your preferred 15-minute interval within this slot."
        ]
        
        translated_body_lines = [translate_template(whatsapp_number, line, supabase) for line in body_lines]
        body_text = "\n".join(translated_body_lines)
        
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "⏱️ Select 15-Minute Interval", supabase)
                },
                "body": {
                    "text": body_text
                },
                "action": {
                    "button": translate_template(whatsapp_number, "Select Time", supabase),
                    "sections": sections
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "BOOKING_SCHEDULE_INTERVAL"
        
    except Exception as e:
        logger.error(f"Error asking minute interval for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error selecting time interval. Please try again.", supabase)}},
            supabase
        )

def handle_schedule_date_response(whatsapp_number: str, user_data: dict, supabase, message):
    """Handle date selection response."""
    try:
        if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
            button_id = message["interactive"]["button_reply"]["id"]
            
            today = datetime.now().date()
            
            if button_id == "booking_date_today":
                selected_date = today
            elif button_id == "booking_date_tomorrow":
                selected_date = today + timedelta(days=1)
            elif button_id == "booking_date_other":
                # Build custom date request message
                date_lines = [
                    "Please enter the pickup date in DD/MM/YYYY format:",
                    "Example: 25/12/2024"
                ]
                
                translated_lines = [translate_template(whatsapp_number, line, supabase) for line in date_lines]
                date_text = "\n".join(translated_lines)
                
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": date_text}},
                    supabase
                )
                user_data[whatsapp_number]["state"] = "BOOKING_SCHEDULE_DATE_OTHER"
                return
            else:
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Invalid selection. Please try again.", supabase)}},
                    supabase
                )
                ask_schedule_date(whatsapp_number, user_data, supabase, "pickup")
                return
            
            # Store date and ask for AM/PM
            temp_data = user_data[whatsapp_number].get("temp_data", {})
            schedule_data = temp_data.get("schedule_data", {})
            schedule_data["date"] = selected_date.strftime("%Y-%m-%d")
            schedule_data["date_display"] = selected_date.strftime("%d/%m/%Y")
            temp_data["schedule_data"] = schedule_data
            user_data[whatsapp_number]["temp_data"] = temp_data
            
            # Ask for AM/PM
            ask_schedule_ampm(whatsapp_number, user_data, supabase)
            
    except Exception as e:
        logger.error(f"Error handling schedule date response for {whatsapp_number}: {e}", exc_info=True)

def handle_date_other_response(whatsapp_number: str, user_data: dict, supabase, message):
    """Handle custom date input response."""
    try:
        if message.get("type") == "text":
            date_str = message["text"]["body"].strip()
            
            # Validate date format DD/MM/YYYY
            try:
                selected_date = datetime.strptime(date_str, "%d/%m/%Y").date()
                today = datetime.now().date()
                
                # Check if date is in the past
                if selected_date < today:
                    # Build past date error message
                    error_lines = [
                        "Date cannot be in the past.",
                        "Please enter a future date in DD/MM/YYYY format."
                    ]
                    
                    translated_lines = [translate_template(whatsapp_number, line, supabase) for line in error_lines]
                    error_text = "\n".join(translated_lines)
                    
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": error_text}},
                        supabase
                    )
                    return
                
                # Store date and ask for AM/PM
                temp_data = user_data[whatsapp_number].get("temp_data", {})
                schedule_data = temp_data.get("schedule_data", {})
                schedule_data["date"] = selected_date.strftime("%Y-%m-%d")
                schedule_data["date_display"] = selected_date.strftime("%d/%m/%Y")
                temp_data["schedule_data"] = schedule_data
                user_data[whatsapp_number]["temp_data"] = temp_data
                
                # Ask for AM/PM
                ask_schedule_ampm(whatsapp_number, user_data, supabase)
                
            except ValueError:
                # Build invalid format error message
                error_lines = [
                    "Invalid date format.",
                    "Please enter date in DD/MM/YYYY format.",
                    "Example: 25/12/2024"
                ]
                
                translated_lines = [translate_template(whatsapp_number, line, supabase) for line in error_lines]
                error_text = "\n".join(translated_lines)
                
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": error_text}},
                    supabase
                )
                
    except Exception as e:
        logger.error(f"Error handling date other response for {whatsapp_number}: {e}", exc_info=True)

def handle_ampm_response(whatsapp_number: str, user_data: dict, supabase, message):
    """Handle AM/PM selection response."""
    try:
        if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
            button_id = message["interactive"]["button_reply"]["id"]
            
            period = "AM" if button_id == "booking_ampm_am" else "PM"
            
            # Store period selection
            temp_data = user_data[whatsapp_number].get("temp_data", {})
            schedule_data = temp_data.get("schedule_data", {})
            schedule_data["period"] = period
            temp_data["schedule_data"] = schedule_data
            user_data[whatsapp_number]["temp_data"] = temp_data
            
            # Ask for time slot selection
            ask_schedule_timeslot(whatsapp_number, user_data, supabase, period)
            
    except Exception as e:
        logger.error(f"Error handling AM/PM response for {whatsapp_number}: {e}", exc_info=True)

def handle_timeslot_response(whatsapp_number: str, user_data: dict, supabase, message):
    """Handle 2-hour time slot selection response."""
    try:
        if message.get("type") == "interactive" and message["interactive"].get("type") == "list_reply":
            list_id = message["interactive"]["list_reply"]["id"]
            
            # Extract slot ID from list_id (format: booking_slot_{slot_id})
            parts = list_id.split("_")
            if len(parts) >= 3:
                slot_id = "_".join(parts[2:])  # Get the rest after "booking_slot_"
                
                # Store slot selection
                temp_data = user_data[whatsapp_number].get("temp_data", {})
                schedule_data = temp_data.get("schedule_data", {})
                schedule_data["slot_id"] = slot_id
                temp_data["schedule_data"] = schedule_data
                user_data[whatsapp_number]["temp_data"] = temp_data
                
                # Ask for 15-minute interval selection
                ask_schedule_minute(whatsapp_number, user_data, supabase)
            else:
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Invalid selection. Please try again.", supabase)}},
                    supabase
                )
                # Go back to AM/PM selection
                period = schedule_data.get("period", "AM")
                ask_schedule_timeslot(whatsapp_number, user_data, supabase, period)
                
    except Exception as e:
        logger.error(f"Error handling time slot response for {whatsapp_number}: {e}", exc_info=True)

def handle_interval_response(whatsapp_number: str, user_data: dict, supabase, message):
    """Handle 15-minute interval selection response and submit booking."""
    try:
        if message.get("type") == "interactive" and message["interactive"].get("type") == "list_reply":
            list_id = message["interactive"]["list_reply"]["id"]
            
            # Extract interval from list_id (format: booking_interval_{HHMM})
            parts = list_id.split("_")
            if len(parts) >= 3:
                interval_str = parts[2]  # Format: HHMM
                
                # Parse hour and minute
                hour = int(interval_str[:2])
                minute = int(interval_str[2:])
                
                # Store interval selection
                temp_data = user_data[whatsapp_number].get("temp_data", {})
                schedule_data = temp_data.get("schedule_data", {})
                schedule_data["hour"] = hour
                schedule_data["minute"] = minute
                temp_data["schedule_data"] = schedule_data
                user_data[whatsapp_number]["temp_data"] = temp_data
                
                # Submit the booking
                submit_booking(whatsapp_number, user_data, supabase)
            else:
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Invalid selection. Please try again.", supabase)}},
                    supabase
                )
                ask_schedule_minute(whatsapp_number, user_data, supabase)
                
    except Exception as e:
        logger.error(f"Error handling interval response for {whatsapp_number}: {e}", exc_info=True)

def submit_booking(whatsapp_number: str, user_data: dict, supabase):
    """Submit the ambulance booking to database (a_s_hometohosp table)."""
    try:
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        answers = temp_data.get("answers", {})
        schedule_data = temp_data.get("schedule_data", {})
        attachments = temp_data.get("attachments", [])
        remarks = temp_data.get("remarks", "")
        return_service = temp_data.get("return_service", False)
        
        # Get addresses
        pickup_address = answers.get("pickup_address", "")
        hospital_name = answers.get("hospital_name", "")
        hospital_address = answers.get("hospital_address", "")
        
        # Geocode addresses if not already geocoded
        pickup_latitude = answers.get("pickup_latitude")
        pickup_longitude = answers.get("pickup_longitude")
        
        if not pickup_latitude or not pickup_longitude:
            pickup_geocode = geocode_address(pickup_address) if pickup_address else None
            if pickup_geocode:
                pickup_latitude = pickup_geocode.get("latitude")
                pickup_longitude = pickup_geocode.get("longitude")
        
        hospital_latitude = answers.get("hospital_latitude")
        hospital_longitude = answers.get("hospital_longitude")
        
        if not hospital_latitude or not hospital_longitude:
            hospital_geocode = geocode_address(hospital_address) if hospital_address else None
            if hospital_geocode:
                hospital_latitude = hospital_geocode.get("latitude")
                hospital_longitude = hospital_geocode.get("longitude")
        
        # Calculate distance
        distance_km = None
        if pickup_latitude and pickup_longitude and hospital_latitude and hospital_longitude:
            distance_km = calculate_distance(
                pickup_latitude, pickup_longitude,
                hospital_latitude, hospital_longitude
            )
        
        # Parse schedule
        scheduled_date = schedule_data.get("date")
        hour = schedule_data.get("hour", 12)
        minute = schedule_data.get("minute", 0)
        scheduled_time = f"{hour:02d}:{minute:02d}:00"
        
        # AM/PM Display logic
        ampm = "AM" if hour < 12 else "PM"
        display_hour = hour % 12
        if display_hour == 0: display_hour = 12

        # Prepare attachments as JSON array of attachment objects
        attachment_list = []
        if attachments:
            for att in attachments:
                attachment_info = {
                    "type": att.get("type", "unknown"),
                    "filename": att.get("original_filename", "unknown"),
                    "url": att.get("url", ""),
                    "uploaded_at": att.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    "mime_type": att.get("mime_type", "")
                }
                attachment_list.append(attachment_info)

        patient_name = answers.get("patient_name", "")
        patient_ic = answers.get("patient_ic", "")
        
        # We use patient_name as user_name fallback
        wa_uuid, patient_uuid = get_or_create_ids(
            supabase, 
            whatsapp_number, 
            patient_name, # user_name
            patient_name, # patient_name
            patient_ic
        )
        
        # --- UPDATED DATA OBJECT ---
        booking_data = {
            "booking_id": temp_data.get("booking_id", ""),
            "whatsapp_number": whatsapp_number.lstrip("+"),
            "service_type": "home_to_hosp",
            "patient_name": answers.get("patient_name", ""),
            "patient_age": None,  # Age removed as requested
            "patient_ic": answers.get("patient_ic", ""),
            "patient_phone": answers.get("patient_phone", ""),
            "emergency_name": answers.get("emergency_name", ""),
            "emergency_phone": answers.get("emergency_phone", ""),
            "pickup_address": pickup_address,
            "pickup_latitude": pickup_latitude,
            "pickup_longitude": pickup_longitude,
            "hospital_name": hospital_name,
            "hospital_address": hospital_address,
            "hospital_latitude": hospital_latitude,
            "hospital_longitude": hospital_longitude,
            # Mapping appointment_date to string format for display
            "appointment_date": schedule_data.get("date_display", ""), 
            "appointment_time": f"{display_hour}:{minute:02d} {ampm}",
            # Columns added in SQL Step 1
            "attachments": json.dumps(attachment_list) if attachment_list else None,
            "remarks": remarks,
            "return_service": "yes" if return_service else "no",
            "return": return_service,  # Boolean column
            "status": "pending",
            # FIX: Use default provider ID
            "provider_id": DEFAULT_PROVIDER_ID,
            "distance_km": distance_km,
            "dispatched_status": "scheduled",
            "scheduled_date": scheduled_date,
            "scheduled_time": scheduled_time,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "whatsapp_id": wa_uuid,
            "patient_id": patient_uuid
        }
        
        # Save to database
        response = supabase.table("a_s_hometohosp").insert(booking_data).execute()
        
        if response.data:
            logger.info(f"Ambulance booking saved for {whatsapp_number}: {temp_data.get('booking_id')}")
            
            # Build summary text line by line
            distance_info = ""
            if distance_km is not None:
                distance_info = f"\n*Estimated Distance:* {distance_km:.1f} km\n"
            
            # Format scheduled time for display
            scheduled_display = f"{schedule_data.get('date_display', 'N/A')} at {display_hour}:{minute:02d} {ampm}"
            
            # Attachment info
            attachment_info = ""
            if attachments:
                attachment_info = f"\n*Attachments:* {len(attachments)} file(s) uploaded"
            
            # Remarks info
            remarks_info = ""
            if remarks:
                remarks_info = f"\n*Remarks:* {remarks[:50]}..."
            
            # Return service info
            return_info = ""
            if return_service:
                return_info = f"\n*Return Service:* ✅ Yes (will be scheduled with you)"
            
            # Build summary lines
            summary_lines = [
                "✅ *AMBULANCE BOOKING CONFIRMED*",
                "",
                f"Booking ID: {temp_data.get('booking_id')}",
                f"Patient: {answers.get('patient_name', 'N/A')}",
                f"Hospital: {hospital_name}",
                f"Pickup: {scheduled_display}",
                f"From: {pickup_address[:50]}...",
                distance_info,
                attachment_info,
                remarks_info,
                return_info,
                "",
                "Your booking has been received. Our team will contact you within 24 hours to confirm details.",
                "",
                "*Next Steps:*",
                "1. Team will verify details",
                "2. You'll receive confirmation call",
                "3. Payment details will be shared",
                "",
                "Thank you for using AnyHealth Ambulance Service! 🚑"
            ]
            
            # Remove empty lines and translate
            summary_lines = [line for line in summary_lines if line.strip()]
            translated_lines = []
            for line in summary_lines:
                if line.startswith("Booking ID:") or line.startswith("Patient:") or line.startswith("Hospital:") or line.startswith("Pickup:") or line.startswith("From:") or line.startswith("✅ *AMBULANCE BOOKING CONFIRMED*"):
                    translated_lines.append(line)
                elif "*Estimated Distance:*" in line or "*Attachments:*" in line or "*Remarks:*" in line or "*Return Service:*" in line:
                    # Keep these lines as is since they contain dynamic data
                    translated_lines.append(line)
                elif line.strip():
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
                else:
                    translated_lines.append(line)
            
            summary_text = "\n".join(translated_lines)
            
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": summary_text}},
                supabase
            )
            
            # Reset user data
            user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
            
            # Return to main menu after delay
            time.sleep(2)
            from utils import send_interactive_menu
            send_interactive_menu(whatsapp_number, supabase)
            
            return True
        else:
            logger.error(f"Failed to save booking: {response}")
            raise Exception("Failed to save booking to database")
            
    except Exception as e:
        logger.error(f"Error submitting ambulance booking for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error submitting booking. Please try again.", supabase)}},
            supabase
        )
        return False