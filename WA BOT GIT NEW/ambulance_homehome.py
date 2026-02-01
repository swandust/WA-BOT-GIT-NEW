import logging
import uuid
import time
import json
import re  # Added for regex pattern matching
from datetime import datetime, timedelta
from utils import (
    send_whatsapp_message,
    gt_tt,
    gt_t_tt,
    gt_dt_tt,
    calculate_distance,
    geocode_address,
    download_whatsapp_media,
    upload_to_supabase_storage,
    get_file_extension_from_mime,
    send_location_request,
    translate_template
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define the sequence of questions for home to home transfer - REMOVED AGE
HOMEHOME_QUESTIONS = [
    {
        "key": "patient_name",
        "question": "1. Patient full name\nExample: Ahmad bin Abdullah",
        "state": "HOMEHOME_PATIENT_NAME"
    },
    {
        "key": "patient_ic",
        "question": "2. Patient IC number\nExample: 801212-14-5678",
        "state": "HOMEHOME_PATIENT_IC",
        "validation": "ic"  # Add validation type
    },
    {
        "key": "patient_phone",
        "question": "3. Patient phone number\nExample: 012-3456789",
        "state": "HOMEHOME_PATIENT_PHONE"
    },
    {
        "key": "emergency_name",
        "question": "4. Emergency contact name at pickup location\nExample: Siti binti Mohamad",
        "state": "HOMEHOME_EMERGENCY_NAME"
    },
    {
        "key": "emergency_phone",
        "question": "5. Emergency contact phone at pickup location\nExample: 019-8765432",
        "state": "HOMEHOME_EMERGENCY_PHONE"
    }
]

# Fixed provider ID from the database
DEFAULT_PROVIDER_ID = "aff725c1-c333-4039-bd2d-000000000000"

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

def handle_homehome_start(whatsapp_number: str, user_id: str, supabase, user_data: dict):
    """Start the home to home transfer process."""
    try:
        logger.info(f"Starting home to home transfer for {whatsapp_number}")
        
        # Generate transfer ID
        transfer_id = f"HMH{int(time.time()) % 1000000:06d}"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Store initial data
        user_data[whatsapp_number]["temp_data"] = {
            "transfer_id": transfer_id,
            "service_type": "home_to_home",
            "answers": {},
            "current_question_index": 0,
            "start_time": current_time,
            "schedule_data": {},  # Store date and time selection data
            "attachments": [],    # Store attachment URLs
            "remarks": "",        # Store additional remarks
            "dest_emergency_name": "",  # Destination emergency contact name
            "dest_emergency_phone": "", # Destination emergency contact phone
            "has_dest_emergency": False # Whether destination emergency contact is provided
        }
        user_data[whatsapp_number]["state"] = "HOMEHOME_STARTED"
        
        # Send confirmation and first question
        # Split the long text into multiple parts for better translation
        confirmation_text_parts = [
            translate_template(whatsapp_number, "🏠 *AMBULANCE SERVICE: HOME TO HOME TRANSFER*", supabase),
            "\n\n",
            gt_tt(whatsapp_number, f"Transfer ID: {transfer_id}\n", supabase),
            gt_tt(whatsapp_number, f"Time: {current_time}\n\n", supabase),
            translate_template(whatsapp_number, "This service helps transfer patients between homes (e.g., moving to family home).", supabase),
            "\n\n",
            translate_template(whatsapp_number, "We'll collect information for your home-to-home transfer.", supabase),
            "\n",
            translate_template(whatsapp_number, "Please answer the following questions one by one.", supabase),
            "\n\n",
            translate_template(whatsapp_number, "*IMPORTANT:*", supabase),
            "\n",
            translate_template(whatsapp_number, "• Provide accurate addresses for both locations", supabase),
            "\n",
            translate_template(whatsapp_number, "• Ensure patient is stable for transfer", supabase),
            "\n",
            translate_template(whatsapp_number, "• Have all necessary medical equipment ready", supabase),
            "\n",
            translate_template(whatsapp_number, "• Coordinate with family members at both locations", supabase),
            "\n\n",
            "---",
            "\n",
            translate_template(whatsapp_number, "*QUESTIONS TO FOLLOW:*", supabase),
            "\n",
            translate_template(whatsapp_number, "1. Patient full name", supabase),
            "\n",
            translate_template(whatsapp_number, "2. Patient IC number", supabase),
            "\n",
            translate_template(whatsapp_number, "3. Patient phone number", supabase),
            "\n",
            translate_template(whatsapp_number, "4. Emergency contact at pickup location", supabase),
            "\n",
            translate_template(whatsapp_number, "5. Emergency contact phone at pickup location", supabase),
            "\n",
            translate_template(whatsapp_number, "6. Current address (Pickup) with location sharing option", supabase),
            "\n",
            translate_template(whatsapp_number, "7. Destination address (manual input)", supabase),
            "\n",
            translate_template(whatsapp_number, "8. Reason for transfer", supabase),
            "\n",
            translate_template(whatsapp_number, "9. Medical condition", supabase),
            "\n",
            translate_template(whatsapp_number, "*After these questions, we'll ask for destination emergency contact, attachments, and schedule.*", supabase),
            "\n\n",
            translate_template(whatsapp_number, "You can cancel anytime by typing 'cancel'.", supabase)
        ]
        
        confirmation_text = "".join(confirmation_text_parts)
        
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
        send_next_homehome_question(whatsapp_number, user_data, supabase)
        
        return False
        
    except Exception as e:
        logger.error(f"Error starting home to home transfer for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error starting transfer request. Please try again.", supabase)}},
            supabase
        )
        return False

def send_next_homehome_question(whatsapp_number: str, user_data: dict, supabase):
    """Send the next question in the sequence."""
    try:
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        current_index = temp_data.get("current_question_index", 0)
        
        if current_index < len(HOMEHOME_QUESTIONS):
            question_data = HOMEHOME_QUESTIONS[current_index]
            # Translate each line separately to maintain proper formatting
            question_lines = question_data["question"].split('\n')
            translated_lines = [translate_template(whatsapp_number, line, supabase) for line in question_lines]
            question_text = '\n'.join(translated_lines)
            
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
            # All basic questions answered, ask for pickup address with location option
            ask_pickup_address_option(whatsapp_number, user_data, supabase)
            
    except Exception as e:
        logger.error(f"Error sending next question to {whatsapp_number}: {e}", exc_info=True)

def ask_pickup_address_option(whatsapp_number: str, user_data: dict, supabase):
    """Ask for pickup address with option to share location or type manually."""
    try:
        # Build the body text by parts
        body_parts = [
            translate_template(whatsapp_number, "6. *Current address (Pickup)*", supabase),
            "\n\n",
            translate_template(whatsapp_number, "How would you like to provide your current address?", supabase),
            "\n\n",
            translate_template(whatsapp_number, "• *Share Location:* Send your current location (recommended)", supabase),
            "\n",
            translate_template(whatsapp_number, "• *Type Address:* Enter your full address manually", supabase),
            "\n\n",
            translate_template(whatsapp_number, "Example of manual address:", supabase),
            "\n",
            "No 12, Jalan Merdeka, Taman Tun Dr Ismail, 60000 Kuala Lumpur"
        ]
        
        body_text = "".join(body_parts)
        
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "📍 Current Address (Pickup)", supabase)
                },
                "body": {
                    "text": body_text
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "homehome_pickup_share_location",
                                "title": translate_template(whatsapp_number, "📍 Share Location", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "homehome_pickup_type_address",
                                "title": translate_template(whatsapp_number, "📝 Type Address", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "HOMEHOME_PICKUP_ADDRESS_OPTION"
        
    except Exception as e:
        logger.error(f"Error asking pickup address option for {whatsapp_number}: {e}", exc_info=True)

def ask_pickup_address_text(whatsapp_number: str, user_data: dict, supabase):
    """Ask user to type pickup address manually."""
    try:
        # Build the text by parts
        text_parts = [
            translate_template(whatsapp_number, "Please type your full current address:", supabase),
            "\n\n",
            translate_template(whatsapp_number, "Example:", supabase),
            "\n",
            "No 12, Jalan Merdeka, Taman Tun Dr Ismail, 60000 Kuala Lumpur",
            "\n\n",
            translate_template(whatsapp_number, "Include:", supabase),
            "\n",
            translate_template(whatsapp_number, "• House/building number", supabase),
            "\n",
            translate_template(whatsapp_number, "• Street name", supabase),
            "\n",
            translate_template(whatsapp_number, "• Area/Taman", supabase),
            "\n",
            translate_template(whatsapp_number, "• Postcode and City", supabase),
            "\n",
            translate_template(whatsapp_number, "• State", supabase)
        ]
        
        text = "".join(text_parts)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "HOMEHOME_PICKUP_ADDRESS_TEXT"
        
    except Exception as e:
        logger.error(f"Error asking pickup address text for {whatsapp_number}: {e}", exc_info=True)

def confirm_pickup_address(whatsapp_number: str, user_data: dict, supabase, address: str, latitude: float = None, longitude: float = None):
    """Ask user to confirm the geocoded pickup address."""
    try:
        # Store the original address and coordinates
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        temp_data["answers"]["from_address_original"] = address
        temp_data["answers"]["from_latitude"] = latitude
        temp_data["answers"]["from_longitude"] = longitude
        
        # Try to geocode the address for better formatting
        try:
            geocoded = geocode_address(address)
            if geocoded and geocoded.get("formatted_address"):
                formatted_address = geocoded.get("formatted_address")
                temp_data["answers"]["from_address_formatted"] = formatted_address
                temp_data["answers"]["from_latitude"] = geocoded.get("latitude", latitude)
                temp_data["answers"]["from_longitude"] = geocoded.get("longitude", longitude)
                
                # Use formatted address for confirmation
                display_address = formatted_address
            else:
                display_address = address
        except Exception as e:
            logger.error(f"Error geocoding pickup address: {e}")
            display_address = address
        
        user_data[whatsapp_number]["temp_data"] = temp_data
        
        # Build the body text
        body_parts = [
            translate_template(whatsapp_number, "We found this address:", supabase),
            "\n\n",
            gt_tt(whatsapp_number, f"{display_address[:200]}\n\n", supabase),
            translate_template(whatsapp_number, "Is this your correct pickup address?", supabase)
        ]
        
        body_text = "".join(body_parts)
        
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "📍 Pickup Address Found", supabase)
                },
                "body": {
                    "text": body_text
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
        user_data[whatsapp_number]["state"] = "HOMEHOME_PICKUP_ADDRESS_CONFIRM"
        
    except Exception as e:
        logger.error(f"Error confirming pickup address for {whatsapp_number}: {e}", exc_info=True)
        # If confirmation fails, proceed with the original address
        temp_data["answers"]["from_address"] = address
        ask_destination_address(whatsapp_number, user_data, supabase)

def ask_destination_address(whatsapp_number: str, user_data: dict, supabase):
    """Ask for destination address."""
    try:
        # Build the text by parts
        text_parts = [
            translate_template(whatsapp_number, "7. *Destination address*", supabase),
            "\n\n",
            translate_template(whatsapp_number, "Please type the full destination address:", supabase),
            "\n\n",
            translate_template(whatsapp_number, "Example:", supabase),
            "\n",
            "No 23, Jalan Bukit Bintang, Taman Maluri, 55100 Kuala Lumpur",
            "\n\n",
            translate_template(whatsapp_number, "Include:", supabase),
            "\n",
            translate_template(whatsapp_number, "• House/building number", supabase),
            "\n",
            translate_template(whatsapp_number, "• Street name", supabase),
            "\n",
            translate_template(whatsapp_number, "• Area/Taman", supabase),
            "\n",
            translate_template(whatsapp_number, "• Postcode and City", supabase),
            "\n",
            translate_template(whatsapp_number, "• State", supabase)
        ]
        
        text = "".join(text_parts)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "HOMEHOME_TO_ADDRESS"
        
    except Exception as e:
        logger.error(f"Error asking destination address for {whatsapp_number}: {e}", exc_info=True)

def confirm_destination_address(whatsapp_number: str, user_data: dict, supabase, address: str):
    """Ask user to confirm the geocoded destination address."""
    try:
        # Store the original address
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        temp_data["answers"]["to_address_original"] = address
        
        # Try to geocode the address for better formatting
        try:
            geocoded = geocode_address(address)
            if geocoded and geocoded.get("formatted_address"):
                formatted_address = geocoded.get("formatted_address")
                temp_data["answers"]["to_address_formatted"] = formatted_address
                temp_data["answers"]["to_latitude"] = geocoded.get("latitude")
                temp_data["answers"]["to_longitude"] = geocoded.get("longitude")
                
                # Use formatted address for confirmation
                display_address = formatted_address
            else:
                display_address = address
        except Exception as e:
            logger.error(f"Error geocoding destination address: {e}")
            display_address = address
        
        user_data[whatsapp_number]["temp_data"] = temp_data
        
        # Build the body text
        body_parts = [
            translate_template(whatsapp_number, "We found this address:", supabase),
            "\n\n",
            gt_tt(whatsapp_number, f"{display_address[:200]}\n\n", supabase),
            translate_template(whatsapp_number, "Is this your correct destination address?", supabase)
        ]
        
        body_text = "".join(body_parts)
        
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "📍 Destination Address Found", supabase)
                },
                "body": {
                    "text": body_text
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "destination_address_yes",
                                "title": translate_template(whatsapp_number, "✅ Yes, Correct", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "destination_address_edit",
                                "title": translate_template(whatsapp_number, "✏️ Edit Address", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "HOMEHOME_TO_ADDRESS_CONFIRM"
        
    except Exception as e:
        logger.error(f"Error confirming destination address for {whatsapp_number}: {e}", exc_info=True)
        # If confirmation fails, proceed with the original address
        temp_data["answers"]["to_address"] = address
        ask_transfer_reason(whatsapp_number, user_data, supabase)

def ask_transfer_reason(whatsapp_number: str, user_data: dict, supabase):
    """Ask for reason for transfer."""
    try:
        # Build the text by parts
        text_parts = [
            translate_template(whatsapp_number, "8. *Reason for transfer*", supabase),
            "\n\n",
            translate_template(whatsapp_number, "Please explain why you need this home-to-home transfer:", supabase),
            "\n\n",
            translate_template(whatsapp_number, "Examples:", supabase),
            "\n",
            translate_template(whatsapp_number, "• Moving to family home for care", supabase),
            "\n",
            translate_template(whatsapp_number, "• Returning from temporary stay", supabase),
            "\n",
            translate_template(whatsapp_number, "• Home modification needed", supabase),
            "\n",
            translate_template(whatsapp_number, "• Closer to medical facilities", supabase),
            "\n",
            translate_template(whatsapp_number, "• Change of residence", supabase)
        ]
        
        text = "".join(text_parts)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "HOMEHOME_TRANSFER_REASON"
        
    except Exception as e:
        logger.error(f"Error asking transfer reason for {whatsapp_number}: {e}", exc_info=True)

def ask_medical_condition(whatsapp_number: str, user_data: dict, supabase):
    """Ask for medical condition."""
    try:
        # Build the text by parts
        text_parts = [
            translate_template(whatsapp_number, "9. *Medical condition*", supabase),
            "\n\n",
            translate_template(whatsapp_number, "Please describe the patient's current medical condition:", supabase),
            "\n\n",
            translate_template(whatsapp_number, "Examples:", supabase),
            "\n",
            translate_template(whatsapp_number, "• Post-stroke recovery", supabase),
            "\n",
            translate_template(whatsapp_number, "• Mobility limited", supabase),
            "\n",
            translate_template(whatsapp_number, "• Requires oxygen therapy", supabase),
            "\n",
            translate_template(whatsapp_number, "• Stable condition for transfer", supabase),
            "\n",
            translate_template(whatsapp_number, "• Recent surgery", supabase)
        ]
        
        text = "".join(text_parts)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "HOMEHOME_MEDICAL_CONDITION"
        
    except Exception as e:
        logger.error(f"Error asking medical condition for {whatsapp_number}: {e}", exc_info=True)

def ask_destination_emergency_contact(whatsapp_number: str, user_data: dict, supabase):
    """Ask if user wants to provide destination emergency contact."""
    try:
        # Build the body text
        body_parts = [
            translate_template(whatsapp_number, "Would you like to provide an emergency contact at the destination?", supabase),
            "\n\n",
            translate_template(whatsapp_number, "This is optional but recommended for better coordination at the destination location.", supabase)
        ]
        
        body_text = "".join(body_parts)
        
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "📱 Destination Emergency Contact", supabase)
                },
                "body": {
                    "text": body_text
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "dest_emergency_yes",
                                "title": translate_template(whatsapp_number, "✅ Yes", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "dest_emergency_no",
                                "title": translate_template(whatsapp_number, "❌ No", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "HOMEHOME_DEST_EMERGENCY_OPTION"
        
    except Exception as e:
        logger.error(f"Error asking destination emergency contact option for {whatsapp_number}: {e}", exc_info=True)

def ask_destination_emergency_name(whatsapp_number: str, user_data: dict, supabase):
    """Ask for destination emergency contact name."""
    try:
        # Build the text
        text_parts = [
            translate_template(whatsapp_number, "Please provide the emergency contact name at the destination:", supabase),
            "\n\n",
            translate_template(whatsapp_number, "Example: Rahman bin Ali or Aishah binti Hassan", supabase)
        ]
        
        text = "".join(text_parts)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "HOMEHOME_DEST_EMERGENCY_NAME"
        
    except Exception as e:
        logger.error(f"Error asking destination emergency name for {whatsapp_number}: {e}", exc_info=True)

def ask_destination_emergency_phone(whatsapp_number: str, user_data: dict, supabase):
    """Ask for destination emergency contact phone."""
    try:
        # Build the text
        text_parts = [
            translate_template(whatsapp_number, "Please provide the emergency contact phone at the destination:", supabase),
            "\n\n",
            translate_template(whatsapp_number, "Example: 012-3456789 or 019-8765432", supabase)
        ]
        
        text = "".join(text_parts)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "HOMEHOME_DEST_EMERGENCY_PHONE"
        
    except Exception as e:
        logger.error(f"Error asking destination emergency phone for {whatsapp_number}: {e}", exc_info=True)

def ask_for_attachments(whatsapp_number: str, user_data: dict, supabase):
    """Ask user to upload attachments."""
    try:
        # Build the body text by parts
        body_parts = [
            translate_template(whatsapp_number, "You can upload attachments (photos/documents) related to this transfer.", supabase),
            "\n\n",
            translate_template(whatsapp_number, "Examples:", supabase),
            "\n",
            translate_template(whatsapp_number, "• Medical reports", supabase),
            "\n",
            translate_template(whatsapp_number, "• Doctor's clearance for transfer", supabase),
            "\n",
            translate_template(whatsapp_number, "• Insurance documents", supabase),
            "\n",
            translate_template(whatsapp_number, "• Prescriptions", supabase),
            "\n\n",
            translate_template(whatsapp_number, "You can upload multiple attachments. When done, click 'Next'.", supabase)
        ]
        
        body_text = "".join(body_parts)
        
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
                                "id": "homehome_attach_next",
                                "title": translate_template(whatsapp_number, "Next", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "homehome_attach_skip",
                                "title": translate_template(whatsapp_number, "Skip", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "HOMEHOME_ATTACHMENTS"
        
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
        # Build the body text by parts
        body_parts = [
            translate_template(whatsapp_number, "Do you have any additional remarks or special instructions?", supabase),
            "\n\n",
            translate_template(whatsapp_number, "Examples:", supabase),
            "\n",
            translate_template(whatsapp_number, "• Specific route preferences", supabase),
            "\n",
            translate_template(whatsapp_number, "• Special medical equipment needed", supabase),
            "\n",
            translate_template(whatsapp_number, "• Time constraints", supabase),
            "\n",
            translate_template(whatsapp_number, "• Additional patient information", supabase),
            "\n\n",
            translate_template(whatsapp_number, "You can add remarks or skip to continue.", supabase)
        ]
        
        body_text = "".join(body_parts)
        
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
                                "id": "homehome_remarks_add",
                                "title": translate_template(whatsapp_number, "Add Remarks", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "homehome_remarks_skip",
                                "title": translate_template(whatsapp_number, "Skip", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "HOMEHOME_REMARKS"
        
    except Exception as e:
        logger.error(f"Error asking for remarks for {whatsapp_number}: {e}", exc_info=True)

def ask_remarks_text(whatsapp_number: str, user_data: dict, supabase):
    """Ask user to type remarks."""
    try:
        # Build the text by parts
        text_parts = [
            translate_template(whatsapp_number, "Please type your remarks or special instructions:", supabase),
            "\n\n",
            translate_template(whatsapp_number, "Examples:", supabase),
            "\n",
            translate_template(whatsapp_number, "• Patient needs wheelchair assistance", supabase),
            "\n",
            translate_template(whatsapp_number, "• Please use back entrance", supabase),
            "\n",
            translate_template(whatsapp_number, "• Patient is fasting", supabase),
            "\n",
            translate_template(whatsapp_number, "• Special handling requirements", supabase)
        ]
        
        text = "".join(text_parts)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "HOMEHOME_REMARKS_TEXT"
        
    except Exception as e:
        logger.error(f"Error asking remarks text for {whatsapp_number}: {e}", exc_info=True)

def ask_schedule_date(whatsapp_number: str, user_data: dict, supabase, schedule_type: str = "transfer"):
    """Ask for schedule date with interactive buttons."""
    try:
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        # Format dates for display
        today_str = today.strftime("%d/%m/%Y")
        tomorrow_str = tomorrow.strftime("%d/%m/%Y")
        
        schedule_text = "transfer" if schedule_type == "transfer" else "pickup"
        
        # Build the body text by parts
        body_parts = [
            gt_tt(whatsapp_number, f"Please select the {schedule_text} date:", supabase),
            "\n\n",
            gt_tt(whatsapp_number, f"*Today:* {today_str}\n", supabase),
            gt_tt(whatsapp_number, f"*Tomorrow:* {tomorrow_str}\n\n", supabase),
            translate_template(whatsapp_number, "If you need another date, select 'Others' and enter DD/MM/YYYY format.", supabase)
        ]
        
        body_text = "".join(body_parts)
        
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
                                "id": "homehome_date_today",
                                "title": translate_template(whatsapp_number, "Today", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "homehome_date_tomorrow",
                                "title": translate_template(whatsapp_number, "Tomorrow", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "homehome_date_other",
                                "title": translate_template(whatsapp_number, "Others", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "HOMEHOME_SCHEDULE_DATE"
        
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
                    "text": translate_template(whatsapp_number, "Please select AM or PM for the transfer time:", supabase)
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "homehome_ampm_am",
                                "title": translate_template(whatsapp_number, "AM (12am - 11:45am)", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "homehome_ampm_pm",
                                "title": translate_template(whatsapp_number, "PM (12pm - 11:45pm)", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "HOMEHOME_SCHEDULE_AMPM"
        
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
                "id": f"homehome_slot_{slot['id']}",
                "title": gt_t_tt(whatsapp_number, slot["label"], supabase)  # Use gt_t_tt for time slot labels
            })
            
            # Split into multiple sections to avoid exceeding row limit
            if (i + 1) % 3 == 0 or i == len(slots) - 1:
                sections.append({
                    "title": translate_template(whatsapp_number, f"{period} Time Slots", supabase),
                    "rows": rows.copy()
                })
                rows = []
        
        # If only one section, remove the title to save space
        if len(sections) == 1:
            sections[0]["title"] = ""
        
        # Build the body text by parts
        body_parts = [
            translate_template(whatsapp_number, "Please select a 2-hour time slot for transfer:", supabase),
            "\n",
            gt_tt(whatsapp_number, f"Selected Date: {schedule_data.get('date_display', 'N/A')}\n", supabase),
            gt_tt(whatsapp_number, f"Period: {period}\n\n", supabase),
            translate_template(whatsapp_number, "After selecting a slot, you'll choose the exact 15-minute interval.", supabase)
        ]
        
        body_text = "".join(body_parts)
        
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
        user_data[whatsapp_number]["state"] = "HOMEHOME_SCHEDULE_TIMESLOT"
        
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
                    "id": f"homehome_interval_{interval_id}",
                    "title": gt_t_tt(whatsapp_number, time_str, supabase),  # Use gt_t_tt for time strings
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
                    "title": gt_t_tt(whatsapp_number, slot_info['label'], supabase),  # Use gt_t_tt for slot label
                    "rows": rows.copy()
                })
                rows = []
        
        # If only one section, remove the title to save space
        if len(sections) == 1:
            sections[0]["title"] = ""
        
        # Build the body text by parts
        body_parts = [
            translate_template(whatsapp_number, "Please select the exact transfer time:", supabase),
            "\n",
            gt_tt(whatsapp_number, f"Selected Date: {schedule_data.get('date_display', 'N/A')}\n", supabase),
            gt_tt(whatsapp_number, f"Selected Slot: {slot_info['label']}\n\n", supabase),
            translate_template(whatsapp_number, "Choose your preferred 15-minute interval within this slot.", supabase)
        ]
        
        body_text = "".join(body_parts)
        
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
        user_data[whatsapp_number]["state"] = "HOMEHOME_SCHEDULE_INTERVAL"
        
    except Exception as e:
        logger.error(f"Error asking minute interval for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error selecting time interval. Please try again.", supabase)}},
            supabase
        )

def handle_homehome_response(whatsapp_number: str, user_id: str, supabase, user_data: dict, message):
    """Handle user's response during home to home transfer."""
    try:
        # Check for cancellation
        if message.get("type") == "text":
            user_text = message["text"]["body"].strip().lower()
            if user_text == "cancel":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Home transfer cancelled. Returning to main menu.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                from utils import send_interactive_menu
                send_interactive_menu(whatsapp_number, supabase)
                return True
        
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        current_state = user_data[whatsapp_number].get("state", "")
        
        # Handle pickup address option
        if current_state == "HOMEHOME_PICKUP_ADDRESS_OPTION":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "homehome_pickup_share_location":
                    # Build the location instruction text by parts
                    instruction_parts = [
                        translate_template(whatsapp_number, "Please share your current location using the button below:", supabase),
                        "\n\n",
                        translate_template(whatsapp_number, "1. Tap the location icon 📍", supabase),
                        "\n",
                        translate_template(whatsapp_number, "2. Select 'Share Location'", supabase),
                        "\n",
                        translate_template(whatsapp_number, "3. Choose 'Send your current location'", supabase)
                    ]
                    
                    instruction_text = "".join(instruction_parts)
                    
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": instruction_text}},
                        supabase
                    )
                    time.sleep(1)
                    send_location_request(whatsapp_number, supabase)
                    user_data[whatsapp_number]["state"] = "HOMEHOME_PICKUP_ADDRESS_LOCATION"
                    
                elif button_id == "homehome_pickup_type_address":
                    # Ask for manual address input
                    ask_pickup_address_text(whatsapp_number, user_data, supabase)
            return False
        
        # Handle location sharing for pickup address
        elif current_state == "HOMEHOME_PICKUP_ADDRESS_LOCATION":
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
        elif current_state == "HOMEHOME_PICKUP_ADDRESS_TEXT":
            if message.get("type") == "text":
                address = message["text"]["body"].strip()
                if address:
                    # Ask for confirmation of the typed address
                    confirm_pickup_address(whatsapp_number, user_data, supabase, address)
            return False
        
        # Handle pickup address confirmation
        elif current_state == "HOMEHOME_PICKUP_ADDRESS_CONFIRM":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "pickup_address_yes":
                    # Use the formatted address if available, otherwise use original
                    formatted_address = temp_data["answers"].get("from_address_formatted")
                    final_address = formatted_address if formatted_address else temp_data["answers"].get("from_address_original", "")
                    
                    temp_data["answers"]["from_address"] = final_address
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Build confirmation message by parts
                    confirm_parts = [
                        translate_template(whatsapp_number, "✅ *Pickup address confirmed!*", supabase),
                        "\n\n",
                        gt_tt(whatsapp_number, f"Address: {final_address[:100]}...\n\n", supabase),
                        translate_template(whatsapp_number, "Now let's proceed to destination address.", supabase)
                    ]
                    
                    confirm_text = "".join(confirm_parts)
                    
                    # Proceed to destination address
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": confirm_text}},
                        supabase
                    )
                    time.sleep(1)
                    ask_destination_address(whatsapp_number, user_data, supabase)
                    
                elif button_id == "pickup_address_edit":
                    # Build edit instruction text by parts
                    edit_parts = [
                        translate_template(whatsapp_number, "Please type the corrected pickup address:", supabase),
                        "\n\n",
                        translate_template(whatsapp_number, "Example:", supabase),
                        "\n",
                        "No 12, Jalan Merdeka, Taman Tun Dr Ismail, 60000 Kuala Lumpur"
                    ]
                    
                    edit_text = "".join(edit_parts)
                    
                    # Ask user to edit the address
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": edit_text}},
                        supabase
                    )
                    user_data[whatsapp_number]["state"] = "HOMEHOME_PICKUP_ADDRESS_EDIT"
            return False
        
        # Handle pickup address edit
        elif current_state == "HOMEHOME_PICKUP_ADDRESS_EDIT":
            if message.get("type") == "text":
                address = message["text"]["body"].strip()
                if address:
                    # Ask for confirmation of the edited address
                    confirm_pickup_address(whatsapp_number, user_data, supabase, address)
            return False
        
        # Handle destination address input
        elif current_state == "HOMEHOME_TO_ADDRESS":
            if message.get("type") == "text":
                address = message["text"]["body"].strip()
                if address:
                    # Ask for confirmation of the destination address
                    confirm_destination_address(whatsapp_number, user_data, supabase, address)
            return False
        
        # Handle destination address confirmation
        elif current_state == "HOMEHOME_TO_ADDRESS_CONFIRM":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "destination_address_yes":
                    # Use the formatted address if available, otherwise use original
                    formatted_address = temp_data["answers"].get("to_address_formatted")
                    final_address = formatted_address if formatted_address else temp_data["answers"].get("to_address_original", "")
                    
                    temp_data["answers"]["to_address"] = final_address
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Build confirmation message by parts
                    confirm_parts = [
                        translate_template(whatsapp_number, "✅ *Destination address confirmed!*", supabase),
                        "\n\n",
                        gt_tt(whatsapp_number, f"Address: {final_address[:100]}...\n\n", supabase),
                        translate_template(whatsapp_number, "Now let's proceed to the reason for transfer.", supabase)
                    ]
                    
                    confirm_text = "".join(confirm_parts)
                    
                    # Proceed to transfer reason
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": confirm_text}},
                        supabase
                    )
                    time.sleep(1)
                    ask_transfer_reason(whatsapp_number, user_data, supabase)
                    
                elif button_id == "destination_address_edit":
                    # Build edit instruction text by parts
                    edit_parts = [
                        translate_template(whatsapp_number, "Please type the corrected destination address:", supabase),
                        "\n\n",
                        translate_template(whatsapp_number, "Example:", supabase),
                        "\n",
                        "No 23, Jalan Bukit Bintang, Taman Maluri, 55100 Kuala Lumpur"
                    ]
                    
                    edit_text = "".join(edit_parts)
                    
                    # Ask user to edit the address
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": edit_text}},
                        supabase
                    )
                    user_data[whatsapp_number]["state"] = "HOMEHOME_TO_ADDRESS_EDIT"
            return False
        
        # Handle destination address edit
        elif current_state == "HOMEHOME_TO_ADDRESS_EDIT":
            if message.get("type") == "text":
                address = message["text"]["body"].strip()
                if address:
                    # Ask for confirmation of the edited address
                    confirm_destination_address(whatsapp_number, user_data, supabase, address)
            return False
        
        # Handle transfer reason
        elif current_state == "HOMEHOME_TRANSFER_REASON":
            if message.get("type") == "text":
                reason = message["text"]["body"].strip()
                if reason:
                    temp_data["answers"]["transfer_reason"] = reason
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Ask for medical condition
                    ask_medical_condition(whatsapp_number, user_data, supabase)
            return False
        
        # Handle medical condition
        elif current_state == "HOMEHOME_MEDICAL_CONDITION":
            if message.get("type") == "text":
                condition = message["text"]["body"].strip()
                if condition:
                    temp_data["answers"]["medical_condition"] = condition
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Ask for destination emergency contact
                    ask_destination_emergency_contact(whatsapp_number, user_data, supabase)
            return False
        
        # Handle destination emergency contact option
        elif current_state == "HOMEHOME_DEST_EMERGENCY_OPTION":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "dest_emergency_yes":
                    temp_data["has_dest_emergency"] = True
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Ask for destination emergency name
                    ask_destination_emergency_name(whatsapp_number, user_data, supabase)
                else:
                    temp_data["has_dest_emergency"] = False
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Skip to attachments
                    ask_for_attachments(whatsapp_number, user_data, supabase)
            return False
        
        # Handle destination emergency name
        elif current_state == "HOMEHOME_DEST_EMERGENCY_NAME":
            if message.get("type") == "text":
                name = message["text"]["body"].strip()
                if name:
                    temp_data["dest_emergency_name"] = name
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Ask for destination emergency phone
                    ask_destination_emergency_phone(whatsapp_number, user_data, supabase)
            return False
        
        # Handle destination emergency phone
        elif current_state == "HOMEHOME_DEST_EMERGENCY_PHONE":
            if message.get("type") == "text":
                phone = message["text"]["body"].strip()
                if phone:
                    temp_data["dest_emergency_phone"] = phone
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Proceed to attachments
                    ask_for_attachments(whatsapp_number, user_data, supabase)
            return False
        
        # Handle attachment states
        elif current_state == "HOMEHOME_ATTACHMENTS":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "homehome_attach_next":
                    # Move to remarks
                    ask_remarks(whatsapp_number, user_data, supabase)
                elif button_id == "homehome_attach_skip":
                    # Skip attachments, move to remarks
                    temp_data["attachments"] = []
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    ask_remarks(whatsapp_number, user_data, supabase)
            elif message.get("type") in ["image", "document"]:
                # Handle attachment upload
                handle_attachment(whatsapp_number, user_data, supabase, message)
            return False
        
        # Handle remarks option
        elif current_state == "HOMEHOME_REMARKS":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "homehome_remarks_add":
                    ask_remarks_text(whatsapp_number, user_data, supabase)
                elif button_id == "homehome_remarks_skip":
                    temp_data["remarks"] = ""
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Proceed to schedule date
                    ask_schedule_date(whatsapp_number, user_data, supabase, "transfer")
            return False
        
        # Handle remarks text input
        elif current_state == "HOMEHOME_REMARKS_TEXT":
            if message.get("type") == "text":
                remarks_text = message["text"]["body"].strip()
                if remarks_text:
                    temp_data["remarks"] = remarks_text
                    user_data[whatsapp_number]["temp_data"] = temp_data
                
                # Proceed to schedule date
                ask_schedule_date(whatsapp_number, user_data, supabase, "transfer")
            return False
        
        # Handle schedule date and time states
        elif current_state == "HOMEHOME_SCHEDULE_DATE":
            handle_schedule_date_response(whatsapp_number, user_data, supabase, message)
        elif current_state == "HOMEHOME_SCHEDULE_DATE_OTHER":
            handle_date_other_response(whatsapp_number, user_data, supabase, message)
        elif current_state == "HOMEHOME_SCHEDULE_AMPM":
            handle_ampm_response(whatsapp_number, user_data, supabase, message)
        elif current_state == "HOMEHOME_SCHEDULE_TIMESLOT":
            handle_timeslot_response(whatsapp_number, user_data, supabase, message)
        elif current_state == "HOMEHOME_SCHEDULE_INTERVAL":
            handle_interval_response(whatsapp_number, user_data, supabase, message)
        else:
            # Handle regular question responses with validation
            current_index = temp_data.get("current_question_index", 0)
            
            if current_index < len(HOMEHOME_QUESTIONS):
                question_data = HOMEHOME_QUESTIONS[current_index]
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
                        # Build invalid IC message by parts
                        invalid_parts = [
                            translate_template(whatsapp_number, "❌ *Invalid IC number format*", supabase),
                            "\n\n",
                            translate_template(whatsapp_number, "IC must be 12 digits.", supabase),
                            "\n",
                            translate_template(whatsapp_number, "Accepted formats:", supabase),
                            "\n",
                            translate_template(whatsapp_number, "• 801212-14-5678", supabase),
                            "\n",
                            translate_template(whatsapp_number, "• 801212145678", supabase),
                            "\n",
                            translate_template(whatsapp_number, "• 801212 14 5678", supabase),
                            "\n\n",
                            translate_template(whatsapp_number, "Please re-enter the patient's IC number:", supabase)
                        ]
                        
                        invalid_text = "".join(invalid_parts)
                        
                        send_whatsapp_message(
                            whatsapp_number,
                            "text",
                            {"text": {"body": invalid_text}},
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
                send_next_homehome_question(whatsapp_number, user_data, supabase)
            else:
                # All basic questions answered, ask for pickup address with location option
                ask_pickup_address_option(whatsapp_number, user_data, supabase)
                
        return False
        
    except Exception as e:
        logger.error(f"Error handling homehome response for {whatsapp_number}: {e}", exc_info=True)
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
        transfer_id = temp_data.get("transfer_id", "")
        
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
            # Unsupported attachment type
            # Build unsupported message by parts
            unsupported_parts = [
                translate_template(whatsapp_number, "❌ Unsupported file type.", supabase),
                "\n",
                translate_template(whatsapp_number, "Please send images (JPEG, PNG) or documents (PDF, DOC) only.", supabase)
            ]
            
            unsupported_text = "".join(unsupported_parts)
            
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": unsupported_text}},
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
            logger.info(f"Downloading media {media_id} for transfer {transfer_id}")
            file_content = download_whatsapp_media(media_id)
            
            if not file_content:
                logger.error("Failed to download media from WhatsApp")
                # Build download failed message by parts
                failed_parts = [
                    translate_template(whatsapp_number, "❌ Failed to download file from WhatsApp.", supabase),
                    "\n",
                    translate_template(whatsapp_number, "Please try sending the file again.", supabase)
                ]
                
                failed_text = "".join(failed_parts)
                
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": failed_text}},
                    supabase
                )
                return
            
            # Generate unique filename with transfer ID
            unique_id = str(uuid.uuid4())[:8]
            safe_transfer_id = transfer_id.replace("/", "_").replace("\\", "_")
            final_file_name = f"{safe_transfer_id}_{unique_id}_{file_name}"
            
            # Create folder structure: transfers/{transfer_id}/{filename}
            bucket_path = f"transfers/{transfer_id}/{final_file_name}"
            
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
            
            # Send confirmation with Next button
            file_size_mb = len(file_content) / (1024 * 1024)
            
            # Build confirmation message by parts
            confirm_parts = [
                translate_template(whatsapp_number, "✅ *Attachment successfully saved!*", supabase),
                "\n\n",
                gt_tt(whatsapp_number, f"• File: {file_name[:40]}...\n", supabase),
                gt_tt(whatsapp_number, f"• Type: {attachment_info['type'].title()}\n", supabase),
                gt_tt(whatsapp_number, f"• Size: {file_size_mb:.2f} MB\n", supabase),
                gt_tt(whatsapp_number, f"• Total attachments: {len(attachments)}\n\n", supabase),
                translate_template(whatsapp_number, "You can send more attachments or click 'Next' to continue.", supabase)
            ]
            
            confirm_text = "".join(confirm_parts)
            
            # Create interactive message with Next button
            content = {
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": confirm_text
                    },
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "homehome_attach_next",
                                    "title": translate_template(whatsapp_number, "Next", supabase)
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "homehome_attach_skip",
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
            # Build error message by parts
            error_parts = [
                translate_template(whatsapp_number, "❌ Failed to save attachment.", supabase),
                "\n",
                translate_template(whatsapp_number, "Please try again or click 'Skip' to continue without attachments.", supabase)
            ]
            
            error_text = "".join(error_parts)
            
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

def handle_schedule_date_response(whatsapp_number: str, user_data: dict, supabase, message):
    """Handle date selection response."""
    try:
        if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
            button_id = message["interactive"]["button_reply"]["id"]
            
            today = datetime.now().date()
            
            if button_id == "homehome_date_today":
                selected_date = today
            elif button_id == "homehome_date_tomorrow":
                selected_date = today + timedelta(days=1)
            elif button_id == "homehome_date_other":
                # Build custom date instruction by parts
                instruction_parts = [
                    translate_template(whatsapp_number, "Please enter the transfer date in DD/MM/YYYY format:", supabase),
                    "\n",
                    translate_template(whatsapp_number, "Example: 25/12/2024", supabase)
                ]
                
                instruction_text = "".join(instruction_parts)
                
                # Ask for custom date input
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": instruction_text}},
                    supabase
                )
                user_data[whatsapp_number]["state"] = "HOMEHOME_SCHEDULE_DATE_OTHER"
                return
            else:
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Invalid selection. Please try again.", supabase)}},
                    supabase
                )
                ask_schedule_date(whatsapp_number, user_data, supabase, "transfer")
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
                    # Build past date error message by parts
                    error_parts = [
                        translate_template(whatsapp_number, "Date cannot be in the past.", supabase),
                        "\n",
                        translate_template(whatsapp_number, "Please enter a future date in DD/MM/YYYY format.", supabase)
                    ]
                    
                    error_text = "".join(error_parts)
                    
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
                # Build invalid format error message by parts
                error_parts = [
                    translate_template(whatsapp_number, "Invalid date format.", supabase),
                    "\n",
                    translate_template(whatsapp_number, "Please enter date in DD/MM/YYYY format.", supabase),
                    "\n",
                    translate_template(whatsapp_number, "Example: 25/12/2024", supabase)
                ]
                
                error_text = "".join(error_parts)
                
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
            
            period = "AM" if button_id == "homehome_ampm_am" else "PM"
            
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
            
            # Extract slot ID from list_id (format: homehome_slot_{slot_id})
            parts = list_id.split("_")
            if len(parts) >= 3:
                slot_id = "_".join(parts[2:])  # Get the rest after "homehome_slot_"
                
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
    """Handle 15-minute interval selection response and submit transfer."""
    try:
        if message.get("type") == "interactive" and message["interactive"].get("type") == "list_reply":
            list_id = message["interactive"]["list_reply"]["id"]
            
            # Extract interval from list_id (format: homehome_interval_{HHMM})
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
                
                # Submit the transfer
                submit_homehome_transfer(whatsapp_number, user_data, supabase)
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

def submit_homehome_transfer(whatsapp_number: str, user_data: dict, supabase):
    """Submit the home to home transfer to database (a_s_hometohome table)."""
    try:
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        answers = temp_data.get("answers", {})
        schedule_data = temp_data.get("schedule_data", {})
        attachments = temp_data.get("attachments", [])
        remarks = temp_data.get("remarks", "")
        
        # Get addresses
        from_address = answers.get("from_address", "")
        to_address = answers.get("to_address", "")
        
        # Get coordinates if available
        from_latitude = answers.get("from_latitude")
        from_longitude = answers.get("from_longitude")
        to_latitude = None
        to_longitude = None
        
        # Geocode addresses if not already geocoded
        if not from_latitude or not from_longitude:
            from_geocode = geocode_address(from_address) if from_address else None
            if from_geocode:
                from_latitude = from_geocode.get("latitude")
                from_longitude = from_geocode.get("longitude")
        
        # Geocode destination address
        to_geocode = geocode_address(to_address) if to_address else None
        if to_geocode:
            to_latitude = to_geocode.get("latitude")
            to_longitude = to_geocode.get("longitude")
        
        # Calculate distance if we have coordinates
        distance_km = None
        if from_latitude and from_longitude and to_latitude and to_longitude:
            distance_km = calculate_distance(
                from_latitude,
                from_longitude,
                to_latitude,
                to_longitude
            )
            logger.info(f"Distance calculated for home transfer: {distance_km:.2f} km")
        
        # Use the fixed provider ID
        provider_id = DEFAULT_PROVIDER_ID
        
        # Parse schedule data
        scheduled_date = schedule_data.get("date")
        hour = schedule_data.get("hour", 12)
        minute = schedule_data.get("minute", 0)
        
        # Format time in TIME format (HH:MM:SS)
        scheduled_time = f"{hour:02d}:{minute:02d}:00"
        
        # Determine AM/PM for display
        ampm = "AM" if hour < 12 else "PM"
        display_hour = hour % 12
        if display_hour == 0:
            display_hour = 12
        
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
        
        # Prepare transfer data for a_s_hometohome table
        transfer_data = {
            "id": str(uuid.uuid4()),
            "transfer_id": temp_data.get("transfer_id", ""),
            "whatsapp_number": whatsapp_number.lstrip("+"),
            "patient_name": answers.get("patient_name", ""),
            "patient_age": None,  # Age removed as requested
            "patient_ic": answers.get("patient_ic", ""),
            "patient_phone": answers.get("patient_phone", ""),
            "emergency_name": answers.get("emergency_name", ""),
            "emergency_phone": answers.get("emergency_phone", ""),
            "dest_emergency_name": temp_data.get("dest_emergency_name", ""),
            "dest_emergency_phone": temp_data.get("dest_emergency_phone", ""),
            "from_address": from_address,
            "from_latitude": from_latitude,
            "from_longitude": from_longitude,
            "to_address": to_address,
            "to_latitude": to_latitude,
            "to_longitude": to_longitude,
            "transfer_reason": answers.get("transfer_reason", ""),
            "medical_condition": answers.get("medical_condition", ""),
            "special_requirements": "",  # Empty as per request
            "mobility_assistance": "",   # Empty as per request
            "remarks": remarks,
            "status": "pending",
            "provider_id": provider_id,
            "distance_km": distance_km,
            "dispatched_status": "scheduled",
            "scheduled_date": scheduled_date,
            "scheduled_time": scheduled_time,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Add attachments as JSON if attachments exist
        if attachment_list:
            transfer_data["attachments"] = json.dumps(attachment_list)
            # Also store in medical_files for backward compatibility
            transfer_data["medical_files"] = json.dumps(attachment_list)
        
        # Log the data being saved
        logger.info(f"Saving home to home transfer data for {whatsapp_number} to a_s_hometohome table")
        logger.info(f"Scheduled for: {scheduled_date} at {scheduled_time}")
        logger.info(f"Using provider ID: {provider_id}")
        
        # Save to database
        response = supabase.table("a_s_hometohome").insert(transfer_data).execute()
        
        if response.data:
            logger.info(f"Home to home transfer saved for {whatsapp_number}: {temp_data.get('transfer_id')}")
            
            # Prepare confirmation message parts
            summary_parts = [
                translate_template(whatsapp_number, "✅ *HOME TO HOME TRANSFER CONFIRMED*", supabase),
                "\n\n",
                gt_tt(whatsapp_number, f"Transfer ID: {temp_data.get('transfer_id')}\n", supabase),
                gt_tt(whatsapp_number, f"Patient: {answers.get('patient_name', 'N/A')}\n", supabase),
                gt_tt(whatsapp_number, f"From: {from_address[:50]}...\n", supabase),
                gt_tt(whatsapp_number, f"To: {to_address[:50]}...\n", supabase),
                gt_tt(whatsapp_number, f"Scheduled: {schedule_data.get('date_display', 'N/A')} at {display_hour}:{minute:02d} {ampm}\n", supabase),
                gt_tt(whatsapp_number, f"Reason: {answers.get('transfer_reason', 'N/A')[:50]}...\n", supabase)
            ]
            
            # Add distance info if available
            if distance_km is not None:
                summary_parts.append(gt_tt(whatsapp_number, f"Estimated Distance: {distance_km:.1f} km\n", supabase))
            
            # Add attachment info
            if attachments:
                summary_parts.append(gt_tt(whatsapp_number, f"Attachments: {len(attachments)} file(s) uploaded\n", supabase))
            
            # Add remarks info
            if remarks:
                summary_parts.append(gt_tt(whatsapp_number, f"Remarks: {remarks[:50]}...\n", supabase))
            
            # Add destination emergency contact info
            if temp_data.get("has_dest_emergency"):
                summary_parts.append(gt_tt(whatsapp_number, f"Destination Emergency Contact: {temp_data.get('dest_emergency_name', 'N/A')} ({temp_data.get('dest_emergency_phone', 'N/A')})\n", supabase))
            
            # Add closing text
            summary_parts.extend([
                "\n",
                translate_template(whatsapp_number, "Your home-to-home transfer request has been received.", supabase),
                "\n",
                translate_template(whatsapp_number, "Our team will contact you to arrange details.", supabase),
                "\n\n",
                translate_template(whatsapp_number, "*Next Steps:*", supabase),
                "\n",
                translate_template(whatsapp_number, "1. Team will verify details", supabase),
                "\n",
                translate_template(whatsapp_number, "2. You'll receive confirmation call", supabase),
                "\n",
                translate_template(whatsapp_number, "3. Transfer schedule will be arranged", supabase),
                "\n\n",
                translate_template(whatsapp_number, "Thank you for using AnyHealth Ambulance Service! 🚑", supabase)
            ])
            
            summary_text = "".join(summary_parts)
            
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
            logger.error(f"Failed to save home transfer: {response}")
            raise Exception("Failed to save home transfer to database")
            
    except Exception as e:
        logger.error(f"Error submitting home transfer for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error submitting transfer request. Please try again.", supabase)}},
            supabase
        )
        return False