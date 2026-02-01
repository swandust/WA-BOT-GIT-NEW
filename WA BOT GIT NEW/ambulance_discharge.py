# ambulance_discharge.py - UPDATED VERSION WITH CORRECT TRANSLATION FUNCTIONS
import logging
import uuid
import time
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

# Define the sequence of questions for ambulance discharge with examples
# FIXED: Split questions into separate lines to avoid translation spacing issues
DISCHARGE_QUESTIONS = [
    {
        "key": "patient_name",
        "question": "1. Patient name\nExample: Siti binti Mohamad",
        "state": "DISCHARGE_PATIENT_NAME",
        "parts": [
            "1. Patient name",
            "Example: Siti binti Mohamad"
        ]
    },
    {
        "key": "patient_ic",
        "question": "2. Patient IC number\nExample: 560505-08-1234",
        "state": "DISCHARGE_PATIENT_IC",
        "validation": "ic",
        "parts": [
            "2. Patient IC number",
            "Example: 560505-08-1234"
        ]
    },
    {
        "key": "patient_phone",
        "question": "3. Patient phone number\nExample: 013-4567890",
        "state": "DISCHARGE_PATIENT_PHONE",
        "parts": [
            "3. Patient phone number",
            "Example: 013-4567890"
        ]
    },
    {
        "key": "emergency_name",
        "question": "4. Emergency contact name\nExample: Ali bin Abdullah",
        "state": "DISCHARGE_EMERGENCY_NAME",
        "parts": [
            "4. Emergency contact name",
            "Example: Ali bin Abdullah"
        ]
    },
    {
        "key": "emergency_phone",
        "question": "5. Emergency contact phone\nExample: 017-8901234",
        "state": "DISCHARGE_EMERGENCY_PHONE",
        "parts": [
            "5. Emergency contact phone",
            "Example: 017-8901234"
        ]
    },
    {
        "key": "hospital_name",
        "question": "6. Hospital name\nExample: Hospital Serdang or KPJ Selangor",
        "state": "DISCHARGE_HOSPITAL_NAME",
        "parts": [
            "6. Hospital name",
            "Example: Hospital Serdang or KPJ Selangor"
        ]
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
    Accepts formats like: 560505-08-1234, 560505081234, 560505 08 1234
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

def handle_discharge_start(whatsapp_number: str, user_id: str, supabase, user_data: dict):
    """Start the ambulance discharge process (Hospital to Home)."""
    try:
        logger.info(f"Starting ambulance discharge for {whatsapp_number}")
        
        # Generate discharge ID
        discharge_id = f"DCH{int(time.time()) % 1000000:06d}"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Store initial data
        user_data[whatsapp_number]["temp_data"] = {
            "discharge_id": discharge_id,
            "service_type": "hosp_to_home",
            "answers": {},
            "current_question_index": 0,
            "start_time": current_time,
            "schedule_data": {},  # Store date and time selection data
            "attachments": [],    # Store attachment URLs
            "remarks": ""         # Store additional remarks
        }
        user_data[whatsapp_number]["state"] = "DISCHARGE_STARTED"
        
        # Send confirmation and first question
        # FIXED: Split confirmation text into parts to avoid translation spacing issues
        confirmation_parts = [
            "🏥 *AMBULANCE SERVICE: HOSPITAL TO HOME*",
            f"Request ID: {discharge_id}",
            f"Time: {current_time}",
            "",
            "This service helps transport patients from hospital to home after discharge.",
            "",
            "We'll collect information for your discharge transport.",
            "Please answer the following questions one by one.",
            "",
            "*IMPORTANT:*",
            "• Ensure discharge date/time is confirmed with hospital",
            "• For addresses, include full address with postcode",
            "• Provide accurate contact information",
            "",
            "---",
            "*QUESTIONS TO FOLLOW:*",
            "1. Patient name",
            "2. Patient IC number",
            "3. Patient phone number",
            "4. Emergency contact name",
            "5. Emergency contact phone",
            "6. Hospital name (we'll find the address automatically)",
            "7. Ward number and level number",
            "8. Home location (with location sharing option)",
            "*After these questions, we'll ask for attachments, remarks, and schedule discharge.*",
            "",
            "You can cancel anytime by typing 'cancel'."
        ]
        
        confirmation_text = "\n".join(confirmation_parts)
        
        # Send confirmation message using gt_tt for dynamic content with IDs
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": gt_tt(whatsapp_number, confirmation_text, supabase)}},
            supabase
        )
        
        # Wait a moment before sending first question
        time.sleep(1)
        
        # Send first question
        send_next_discharge_question(whatsapp_number, user_data, supabase)
        
        return False
        
    except Exception as e:
        logger.error(f"Error starting ambulance discharge for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error starting discharge request. Please try again.", supabase)}},
            supabase
        )
        return False

def send_next_discharge_question(whatsapp_number: str, user_data: dict, supabase):
    """Send the next question in the sequence."""
    try:
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        current_index = temp_data.get("current_question_index", 0)
        
        if current_index < len(DISCHARGE_QUESTIONS):
            question_data = DISCHARGE_QUESTIONS[current_index]
            
            # FIXED: Translate each part separately and join with newlines
            question_lines = []
            for part in question_data.get("parts", [question_data["question"]]):
                translated_part = translate_template(whatsapp_number, part, supabase)
                question_lines.append(translated_part)
            
            question_text = "\n".join(question_lines)
            
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
            # All basic questions answered, ask for ward number
            ask_ward_number(whatsapp_number, user_data, supabase)
            
    except Exception as e:
        logger.error(f"Error sending next question to {whatsapp_number}: {e}", exc_info=True)

def ask_ward_number(whatsapp_number: str, user_data: dict, supabase):
    """Ask for ward number and level number."""
    try:
        # FIXED: Split ward number question into parts
        ward_parts = [
            "7. *Ward number and level number*",
            "",
            "Please provide the ward and bed number:",
            "",
            "Examples:",
            "• Ward 5A, Bed 12",
            "• ICU Bed 3",
            "• Ward 10, Level 3, Bed 8",
            "• Emergency Department, Bed 5"
        ]
        
        ward_text = "\n".join([translate_template(whatsapp_number, part, supabase) for part in ward_parts])
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": ward_text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "DISCHARGE_WARD_NUMBER"
        
    except Exception as e:
        logger.error(f"Error asking ward number for {whatsapp_number}: {e}", exc_info=True)

def ask_home_location_option(whatsapp_number: str, user_data: dict, supabase):
    """Ask for home location with option to share location or type manually."""
    try:
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "📍 Home Address", supabase)
                },
                "body": {
                    "text": gt_tt(whatsapp_number,  # Keep gt_tt for dynamic formatting
                        "8. *Home address*\n\n"
                        "How would you like to provide your home address?\n\n"
                        "• *Share Location:* Send your home location (recommended)\n"
                        "• *Type Address:* Enter your full address manually\n\n"
                        "Example of manual address:\n"
                        "No 23, Jalan Bukit Bintang, Taman Maluri, 55100 Kuala Lumpur", 
                        supabase)
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "home_share_location",
                                "title": translate_template(whatsapp_number, "📍 Share Location", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "home_type_address",
                                "title": translate_template(whatsapp_number, "📝 Type Address", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "DISCHARGE_HOME_LOCATION_OPTION"
        
    except Exception as e:
        logger.error(f"Error asking home location option for {whatsapp_number}: {e}", exc_info=True)

def ask_home_address_text(whatsapp_number: str, user_data: dict, supabase):
    """Ask user to type home address manually."""
    try:
        # FIXED: Split address text into parts
        address_parts = [
            "Please type your full home address:",
            "",
            "Example:",
            "No 23, Jalan Bukit Bintang, Taman Maluri, 55100 Kuala Lumpur",
            "",
            "Include:",
            "• House/building number",
            "• Street name",
            "• Area/Taman",
            "• Postcode and City",
            "• State"
        ]
        
        address_text = "\n".join([translate_template(whatsapp_number, part, supabase) for part in address_parts])
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": address_text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "DISCHARGE_HOME_ADDRESS_TEXT"
        
    except Exception as e:
        logger.error(f"Error asking home address text for {whatsapp_number}: {e}", exc_info=True)

def confirm_hospital_address(whatsapp_number: str, user_data: dict, supabase, hospital_name: str, hospital_address: str):
    """Ask user to confirm the automatically found hospital address."""
    try:
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "🏥 Hospital Address Found", supabase)
                },
                "body": {
                    "text": gt_tt(whatsapp_number,  # Keep gt_tt for dynamic content
                        f"We found this address for *{hospital_name}*:\n\n"
                        f"{hospital_address}\n\n"
                        f"Is this the correct hospital address?", 
                        supabase)
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
        user_data[whatsapp_number]["state"] = "DISCHARGE_HOSPITAL_ADDRESS_CONFIRM"
        
    except Exception as e:
        logger.error(f"Error confirming hospital address for {whatsapp_number}: {e}", exc_info=True)

def ask_hospital_address_manual(whatsapp_number: str, user_data: dict, supabase):
    """Ask user to type hospital address manually."""
    try:
        # FIXED: Split hospital address text into parts
        hospital_parts = [
            "Please type the hospital address manually:",
            "",
            "Example:",
            "Jalan Pahang, 53000 Kuala Lumpur, Wilayah Persekutuan Kuala Lumpur",
            "",
            "Include full address with postcode and state."
        ]
        
        hospital_text = "\n".join([translate_template(whatsapp_number, part, supabase) for part in hospital_parts])
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": hospital_text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "DISCHARGE_HOSPITAL_ADDRESS_MANUAL"
        
    except Exception as e:
        logger.error(f"Error asking hospital address manual for {whatsapp_number}: {e}", exc_info=True)

def confirm_home_address(whatsapp_number: str, user_data: dict, supabase, address: str, latitude: float = None, longitude: float = None):
    """Ask user to confirm the geocoded home address."""
    try:
        # Store the original address and coordinates
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        temp_data["answers"]["home_address_original"] = address
        temp_data["answers"]["home_latitude"] = latitude
        temp_data["answers"]["home_longitude"] = longitude
        
        # Try to geocode the address for better formatting
        try:
            geocoded = geocode_address(address)
            if geocoded and geocoded.get("formatted_address"):
                formatted_address = geocoded.get("formatted_address")
                temp_data["answers"]["home_address_formatted"] = formatted_address
                temp_data["answers"]["home_latitude"] = geocoded.get("latitude", latitude)
                temp_data["answers"]["home_longitude"] = geocoded.get("longitude", longitude)
                
                # Use formatted address for confirmation
                display_address = formatted_address
            else:
                display_address = address
        except Exception as e:
            logger.error(f"Error geocoding home address: {e}")
            display_address = address
        
        user_data[whatsapp_number]["temp_data"] = temp_data
        
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "📍 Home Address Found", supabase)
                },
                "body": {
                    "text": gt_tt(whatsapp_number,  # Keep gt_tt for dynamic content
                        f"We found this address:\n\n"
                        f"{display_address[:200]}\n\n"
                        f"Is this your correct home address?", 
                        supabase)
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "home_address_yes",
                                "title": translate_template(whatsapp_number, "✅ Yes, Correct", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "home_address_edit",
                                "title": translate_template(whatsapp_number, "✏️ Edit Address", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "DISCHARGE_HOME_ADDRESS_CONFIRM"
        
    except Exception as e:
        logger.error(f"Error confirming home address for {whatsapp_number}: {e}", exc_info=True)
        # If confirmation fails, proceed with the original address
        temp_data["answers"]["home_address"] = address
        ask_for_attachments(whatsapp_number, user_data, supabase)

def ask_for_attachments(whatsapp_number: str, user_data: dict, supabase):
    """Ask user to upload attachments."""
    try:
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "📎 Attachments", supabase)
                },
                "body": {
                    "text": translate_template(whatsapp_number,  # Changed to translate_template for hardcoded text
                        "You can upload attachments (photos/documents) related to this discharge.\n\n"
                        "Examples:\n"
                        "• Medical reports\n"
                        "• Discharge summary\n"
                        "• Doctor's referral letters\n"
                        "• Insurance documents\n\n"
                        "You can upload multiple attachments. When done, click 'Next'.", 
                        supabase)
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "discharge_attach_next",
                                "title": translate_template(whatsapp_number, "Next", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "discharge_attach_skip",
                                "title": translate_template(whatsapp_number, "Skip", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "DISCHARGE_ATTACHMENTS"
        
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
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "📝 Remarks", supabase)
                },
                "body": {
                    "text": translate_template(whatsapp_number,  # Changed to translate_template for hardcoded text
                        "Do you have any additional remarks or special instructions?\n\n"
                        "Examples:\n"
                        "• Specific route preferences\n"
                        "• Special medical equipment needed\n"
                        "• Time constraints\n"
                        "• Additional patient information\n\n"
                        "You can add remarks or skip to continue.", 
                        supabase)
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "discharge_remarks_add",
                                "title": translate_template(whatsapp_number, "Add Remarks", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "discharge_remarks_skip",
                                "title": translate_template(whatsapp_number, "Skip", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "DISCHARGE_REMARKS"
        
    except Exception as e:
        logger.error(f"Error asking for remarks for {whatsapp_number}: {e}", exc_info=True)

def ask_remarks_text(whatsapp_number: str, user_data: dict, supabase):
    """Ask user to type remarks."""
    try:
        # FIXED: Split remarks text into parts
        remarks_parts = [
            "Please type your remarks or special instructions:",
            "",
            "Examples:",
            "• Patient needs wheelchair assistance",
            "• Please use back entrance",
            "• Patient is fasting",
            "• Special handling requirements"
        ]
        
        remarks_text = "\n".join([translate_template(whatsapp_number, part, supabase) for part in remarks_parts])
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": remarks_text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "DISCHARGE_REMARKS_TEXT"
        
    except Exception as e:
        logger.error(f"Error asking remarks text for {whatsapp_number}: {e}", exc_info=True)

def ask_schedule_date(whatsapp_number: str, user_data: dict, supabase, schedule_type: str = "discharge"):
    """Ask for schedule date with interactive buttons."""
    try:
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        # Format dates for display
        today_str = today.strftime("%d/%m/%Y")
        tomorrow_str = tomorrow.strftime("%d/%m/%Y")
        
        schedule_text = "discharge" if schedule_type == "discharge" else "transfer"
        
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, f"📅 Select {schedule_text.title()} Date", supabase)
                },
                "body": {
                    "text": gt_tt(whatsapp_number,  # Keep gt_tt for dynamic content
                        f"Please select the {schedule_text} date:\n\n"
                        f"*Today:* {today_str}\n"
                        f"*Tomorrow:* {tomorrow_str}\n\n"
                        f"If you need another date, select 'Others' and enter DD/MM/YYYY format.", 
                        supabase)
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "discharge_date_today",
                                "title": translate_template(whatsapp_number, "Today", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "discharge_date_tomorrow",
                                "title": translate_template(whatsapp_number, "Tomorrow", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "discharge_date_other",
                                "title": translate_template(whatsapp_number, "Others", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "DISCHARGE_SCHEDULE_DATE"
        
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
                    "text": translate_template(whatsapp_number, "Please select AM or PM for the discharge time:", supabase)
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "discharge_ampm_am",
                                "title": translate_template(whatsapp_number, "AM (12am - 11:45am)", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "discharge_ampm_pm",
                                "title": translate_template(whatsapp_number, "PM (12pm - 11:45pm)", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "DISCHARGE_SCHEDULE_AMPM"
        
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
                "id": f"discharge_slot_{slot['id']}",
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
        
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, f"⏰ Select 2-Hour Slot ({period})", supabase)
                },
                "body": {
                    "text": gt_tt(whatsapp_number,  # Keep gt_tt for dynamic content
                        f"Please select a 2-hour time slot for discharge:\n"
                        f"Selected Date: {schedule_data.get('date_display', 'N/A')}\n"
                        f"Period: {period}\n\n"
                        f"After selecting a slot, you'll choose the exact 15-minute interval.", 
                        supabase)
                },
                "action": {
                    "button": translate_template(whatsapp_number, "Select Time Slot", supabase),
                    "sections": sections
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "DISCHARGE_SCHEDULE_TIMESLOT"
        
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
                    "id": f"discharge_interval_{interval_id}",
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
        
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "⏱️ Select 15-Minute Interval", supabase)
                },
                "body": {
                    "text": gt_tt(whatsapp_number,  # Keep gt_tt for dynamic content
                        f"Please select the exact discharge time:\n"
                        f"Selected Date: {schedule_data.get('date_display', 'N/A')}\n"
                        f"Selected Slot: {slot_info['label']}\n\n"
                        f"Choose your preferred 15-minute interval within this slot.", 
                        supabase)
                },
                "action": {
                    "button": translate_template(whatsapp_number, "Select Time", supabase),
                    "sections": sections
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "DISCHARGE_SCHEDULE_INTERVAL"
        
    except Exception as e:
        logger.error(f"Error asking minute interval for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error selecting time interval. Please try again.", supabase)}},
            supabase
        )

def handle_discharge_response(whatsapp_number: str, user_id: str, supabase, user_data: dict, message):
    """Handle user's response during ambulance discharge."""
    try:
        # Check for cancellation
        if message.get("type") == "text":
            user_text = message["text"]["body"].strip().lower()
            if user_text == "cancel":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Discharge request cancelled. Returning to main menu.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                from utils import send_interactive_menu
                send_interactive_menu(whatsapp_number, supabase)
                return True
        
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        current_state = user_data[whatsapp_number].get("state", "")
        
        # Handle home location option
        if current_state == "DISCHARGE_HOME_LOCATION_OPTION":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "home_share_location":
                    # Send location request
                    # FIXED: Split location request text into parts
                    location_parts = [
                        "Please share your home location using the button below:",
                        "",
                        "1. Tap the location icon 📍",
                        "2. Select 'Share Location'",
                        "3. Choose 'Send your current location'"
                    ]
                    
                    location_text = "\n".join([translate_template(whatsapp_number, part, supabase) for part in location_parts])
                    
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": location_text}},
                        supabase
                    )
                    time.sleep(1)
                    send_location_request(whatsapp_number, supabase)
                    user_data[whatsapp_number]["state"] = "DISCHARGE_HOME_ADDRESS_LOCATION"
                    
                elif button_id == "home_type_address":
                    # Ask for manual address input
                    ask_home_address_text(whatsapp_number, user_data, supabase)
            return False
        
        # Handle location sharing for home address
        elif current_state == "DISCHARGE_HOME_ADDRESS_LOCATION":
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
                
                # Ask for confirmation of the home address
                confirm_home_address(whatsapp_number, user_data, supabase, address, latitude, longitude)
            elif message.get("type") == "text":
                # User might have typed address instead
                address = message["text"]["body"].strip()
                if address:
                    # Ask for confirmation of the typed address
                    confirm_home_address(whatsapp_number, user_data, supabase, address)
            return False
        
        # Handle manual home address input
        elif current_state == "DISCHARGE_HOME_ADDRESS_TEXT":
            if message.get("type") == "text":
                address = message["text"]["body"].strip()
                if address:
                    # Ask for confirmation of the typed address
                    confirm_home_address(whatsapp_number, user_data, supabase, address)
            return False
        
        # Handle home address confirmation
        elif current_state == "DISCHARGE_HOME_ADDRESS_CONFIRM":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "home_address_yes":
                    # Use the formatted address if available, otherwise use original
                    formatted_address = temp_data["answers"].get("home_address_formatted")
                    final_address = formatted_address if formatted_address else temp_data["answers"].get("home_address_original", "")
                    
                    temp_data["answers"]["home_address"] = final_address
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Proceed to attachments
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": gt_tt(whatsapp_number, 
                            f"✅ *Home address confirmed!*\n\n"
                            f"Address: {final_address[:100]}...\n\n"
                            f"Now let's proceed to attachments.", supabase)}},
                        supabase
                    )
                    time.sleep(1)
                    ask_for_attachments(whatsapp_number, user_data, supabase)
                    
                elif button_id == "home_address_edit":
                    # Ask user to edit the address
                    # FIXED: Split edit address text into parts
                    edit_parts = [
                        "Please type the corrected home address:",
                        "",
                        "Example:",
                        "No 23, Jalan Bukit Bintang, Taman Maluri, 55100 Kuala Lumpur"
                    ]
                    
                    edit_text = "\n".join([translate_template(whatsapp_number, part, supabase) for part in edit_parts])
                    
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": edit_text}},
                        supabase
                    )
                    user_data[whatsapp_number]["state"] = "DISCHARGE_HOME_ADDRESS_EDIT"
            return False
        
        # Handle home address edit
        elif current_state == "DISCHARGE_HOME_ADDRESS_EDIT":
            if message.get("type") == "text":
                address = message["text"]["body"].strip()
                if address:
                    # Ask for confirmation of the edited address
                    confirm_home_address(whatsapp_number, user_data, supabase, address)
            return False
        
        # Handle hospital name input
        elif current_state == "DISCHARGE_HOSPITAL_NAME":
            if message.get("type") == "text":
                hospital_name = message["text"]["body"].strip()
                if hospital_name:
                    temp_data["answers"]["hospital_name"] = hospital_name
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Try to geocode hospital name
                    try:
                        send_whatsapp_message(
                            whatsapp_number,
                            "text",
                            {"text": {"body": gt_tt(whatsapp_number, 
                                f"🔍 Searching for *{hospital_name}*...", supabase)}},
                            supabase
                        )
                        
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
                            send_whatsapp_message(
                                whatsapp_number,
                                "text",
                                {"text": {"body": gt_tt(whatsapp_number, 
                                    f"❌ Could not find address for *{hospital_name}*\n\n"
                                    f"Please provide the address manually.", supabase)}},
                                supabase
                            )
                            ask_hospital_address_manual(whatsapp_number, user_data, supabase)
                    except Exception as e:
                        logger.error(f"Error geocoding hospital name: {e}")
                        # Ask for manual input
                        ask_hospital_address_manual(whatsapp_number, user_data, supabase)
            return False
        
        # Handle hospital address confirmation
        elif current_state == "DISCHARGE_HOSPITAL_ADDRESS_CONFIRM":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "hospital_address_yes":
                    # Use the geocoded address
                    temp_data["answers"]["hospital_address"] = temp_data["answers"].get("hospital_address_geocoded", "")
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Ask for ward number
                    ask_ward_number(whatsapp_number, user_data, supabase)
                    
                elif button_id == "hospital_address_no":
                    # Ask for manual input
                    ask_hospital_address_manual(whatsapp_number, user_data, supabase)
            return False
        
        # Handle manual hospital address input
        elif current_state == "DISCHARGE_HOSPITAL_ADDRESS_MANUAL":
            if message.get("type") == "text":
                hospital_address = message["text"]["body"].strip()
                if hospital_address:
                    temp_data["answers"]["hospital_address"] = hospital_address
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Ask for ward number
                    ask_ward_number(whatsapp_number, user_data, supabase)
            return False
        
        # Handle ward number input
        elif current_state == "DISCHARGE_WARD_NUMBER":
            if message.get("type") == "text":
                ward_number = message["text"]["body"].strip()
                if ward_number:
                    temp_data["answers"]["ward_number"] = ward_number
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Ask for home location
                    ask_home_location_option(whatsapp_number, user_data, supabase)
            return False
        
        # Handle attachment states
        elif current_state == "DISCHARGE_ATTACHMENTS":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "discharge_attach_next":
                    # Move to remarks
                    ask_remarks(whatsapp_number, user_data, supabase)
                elif button_id == "discharge_attach_skip":
                    # Skip attachments, move to remarks
                    temp_data["attachments"] = []
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    ask_remarks(whatsapp_number, user_data, supabase)
            elif message.get("type") in ["image", "document"]:
                # Handle attachment upload
                handle_attachment(whatsapp_number, user_data, supabase, message)
            return False
        
        # Handle remarks option
        elif current_state == "DISCHARGE_REMARKS":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "discharge_remarks_add":
                    ask_remarks_text(whatsapp_number, user_data, supabase)
                elif button_id == "discharge_remarks_skip":
                    temp_data["remarks"] = ""
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    # Proceed to schedule date
                    ask_schedule_date(whatsapp_number, user_data, supabase, "discharge")
            return False
        
        # Handle remarks text input
        elif current_state == "DISCHARGE_REMARKS_TEXT":
            if message.get("type") == "text":
                remarks_text = message["text"]["body"].strip()
                if remarks_text:
                    temp_data["remarks"] = remarks_text
                    user_data[whatsapp_number]["temp_data"] = temp_data
                
                # Proceed to schedule date
                ask_schedule_date(whatsapp_number, user_data, supabase, "discharge")
            return False
        
        # Handle schedule date and time states
        elif current_state == "DISCHARGE_SCHEDULE_DATE":
            handle_schedule_date_response(whatsapp_number, user_data, supabase, message)
        elif current_state == "DISCHARGE_SCHEDULE_DATE_OTHER":
            handle_date_other_response(whatsapp_number, user_data, supabase, message)
        elif current_state == "DISCHARGE_SCHEDULE_AMPM":
            handle_ampm_response(whatsapp_number, user_data, supabase, message)
        elif current_state == "DISCHARGE_SCHEDULE_TIMESLOT":
            handle_timeslot_response(whatsapp_number, user_data, supabase, message)
        elif current_state == "DISCHARGE_SCHEDULE_INTERVAL":
            handle_interval_response(whatsapp_number, user_data, supabase, message)
        else:
            # Handle regular question responses with validation
            current_index = temp_data.get("current_question_index", 0)
            
            if current_index < len(DISCHARGE_QUESTIONS):
                question_data = DISCHARGE_QUESTIONS[current_index]
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
                        # FIXED: Split IC validation error into parts
                        ic_error_parts = [
                            "❌ *Invalid IC number format*",
                            "",
                            "IC must be 12 digits.",
                            "Accepted formats:",
                            "• 560505-08-1234",
                            "• 560505081234",
                            "• 560505 08 1234",
                            "",
                            "Please re-enter the patient's IC number:"
                        ]
                        
                        ic_error_text = "\n".join([translate_template(whatsapp_number, part, supabase) for part in ic_error_parts])
                        
                        send_whatsapp_message(
                            whatsapp_number,
                            "text",
                            {"text": {"body": ic_error_text}},
                            supabase
                        )
                        return False
                    
                    # Format the IC to 12 digits without separators
                    answer = format_ic_number(answer)
                
                # Store answer
                temp_data["answers"][answer_key] = answer
                temp_data["current_question_index"] = current_index + 1
                user_data[whatsapp_number]["temp_data"] = temp_data
                
                # Send next question or ask for ward number
                send_next_discharge_question(whatsapp_number, user_data, supabase)
            else:
                # All basic questions answered, ask for ward number
                ask_ward_number(whatsapp_number, user_data, supabase)
                
        return False
        
    except Exception as e:
        logger.error(f"Error handling discharge response for {whatsapp_number}: {e}", exc_info=True)
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
        discharge_id = temp_data.get("discharge_id", "")
        
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
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "❌ Unsupported file type. Please send images (JPEG, PNG) or documents (PDF, DOC) only.", supabase)}},
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
            logger.info(f"Downloading media {media_id} for discharge {discharge_id}")
            file_content = download_whatsapp_media(media_id)
            
            if not file_content:
                logger.error("Failed to download media from WhatsApp")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        "❌ Failed to download file from WhatsApp. Please try sending the file again.", supabase)}},
                    supabase
                )
                return
            
            # Generate unique filename with discharge ID
            unique_id = str(uuid.uuid4())[:8]
            safe_discharge_id = discharge_id.replace("/", "_").replace("\\", "_")
            final_file_name = f"{safe_discharge_id}_{unique_id}_{file_name}"
            
            # Create folder structure: discharges/{discharge_id}/{filename}
            bucket_path = f"discharges/{discharge_id}/{final_file_name}"
            
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
            
            # Create interactive message with Next button
            content = {
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": gt_tt(whatsapp_number, 
                            f"✅ *Attachment successfully saved!*\n\n"
                            f"• File: {file_name[:40]}...\n"
                            f"• Type: {attachment_info['type'].title()}\n"
                            f"• Size: {file_size_mb:.2f} MB\n"
                            f"• Total attachments: {len(attachments)}\n\n"
                            f"You can send more attachments or click 'Next' to continue.", supabase)
                    },
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "discharge_attach_next",
                                    "title": translate_template(whatsapp_number, "Next", supabase)
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "discharge_attach_skip",
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
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "❌ Failed to save attachment. Please try again or click 'Skip' to continue without attachments.", supabase)}},
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
            
            if button_id == "discharge_date_today":
                selected_date = today
            elif button_id == "discharge_date_tomorrow":
                selected_date = today + timedelta(days=1)
            elif button_id == "discharge_date_other":
                # Ask for custom date input
                # FIXED: Split date input text into parts
                date_parts = [
                    "Please enter the discharge date in DD/MM/YYYY format:",
                    "Example: 25/12/2024"
                ]
                
                date_text = "\n".join([translate_template(whatsapp_number, part, supabase) for part in date_parts])
                
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": date_text}},
                    supabase
                )
                user_data[whatsapp_number]["state"] = "DISCHARGE_SCHEDULE_DATE_OTHER"
                return
            else:
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Invalid selection. Please try again.", supabase)}},
                    supabase
                )
                ask_schedule_date(whatsapp_number, user_data, supabase, "discharge")
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
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, 
                            "Date cannot be in the past. Please enter a future date in DD/MM/YYYY format.", supabase)}},
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
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        "Invalid date format. Please enter date in DD/MM/YYYY format.\n"
                        "Example: 25/12/2024", supabase)}},
                    supabase
                )
                
    except Exception as e:
        logger.error(f"Error handling date other response for {whatsapp_number}: {e}", exc_info=True)

def handle_ampm_response(whatsapp_number: str, user_data: dict, supabase, message):
    """Handle AM/PM selection response."""
    try:
        if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
            button_id = message["interactive"]["button_reply"]["id"]
            
            period = "AM" if button_id == "discharge_ampm_am" else "PM"
            
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
            
            # Extract slot ID from list_id (format: discharge_slot_{slot_id})
            parts = list_id.split("_")
            if len(parts) >= 3:
                slot_id = "_".join(parts[2:])  # Get the rest after "discharge_slot_"
                
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
    """Handle 15-minute interval selection response and submit discharge."""
    try:
        if message.get("type") == "interactive" and message["interactive"].get("type") == "list_reply":
            list_id = message["interactive"]["list_reply"]["id"]
            
            # Extract interval from list_id (format: discharge_interval_{HHMM})
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
                
                # Submit the discharge
                submit_discharge(whatsapp_number, user_data, supabase)
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

def submit_discharge(whatsapp_number: str, user_data: dict, supabase):
    """Submit the ambulance discharge request to database (a_s_hosptohome table)."""
    try:
        import json  # Import json for attachments serialization
        
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        answers = temp_data.get("answers", {})
        schedule_data = temp_data.get("schedule_data", {})
        attachments = temp_data.get("attachments", [])
        remarks = temp_data.get("remarks", "")
        
        # Geocode home address and hospital address
        home_address = answers.get("home_address", "")
        hospital_name = answers.get("hospital_name", "")
        hospital_address = answers.get("hospital_address", "")
        
        home_geocode = geocode_address(home_address) if home_address else None
        hospital_geocode = geocode_address(hospital_name) if hospital_name else None
        
        # If we have hospital address but no geocode, try with the address
        if hospital_address and not hospital_geocode:
            hospital_geocode = geocode_address(hospital_address)
        
        # Calculate distance if we have coordinates
        distance_km = None
        if home_geocode and home_geocode.get("latitude") and home_geocode.get("longitude") and \
           hospital_geocode and hospital_geocode.get("latitude") and hospital_geocode.get("longitude"):
            distance_km = calculate_distance(
                hospital_geocode.get("latitude"),
                hospital_geocode.get("longitude"),
                home_geocode.get("latitude"),
                home_geocode.get("longitude")
            )
            logger.info(f"Distance calculated for discharge: {distance_km:.2f} km")
        
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
        
        # Prepare discharge data for a_s_hosptohome table
        discharge_data = {
            "id": str(uuid.uuid4()),
            "discharge_id": temp_data.get("discharge_id", ""),
            "whatsapp_number": whatsapp_number.lstrip("+"),
            "service_type": "hosp_to_home",
            "patient_name": answers.get("patient_name", ""),
            "patient_age": None,  # Age removed as requested
            "patient_ic": answers.get("patient_ic", ""),
            "patient_phone": answers.get("patient_phone", ""),
            "emergency_name": answers.get("emergency_name", ""),
            "emergency_phone": answers.get("emergency_phone", ""),
            "hospital_name": answers.get("hospital_name", ""),
            "hospital_address": hospital_address,
            "hospital_latitude": hospital_geocode.get("latitude") if hospital_geocode else None,
            "hospital_longitude": hospital_geocode.get("longitude") if hospital_geocode else None,
            "ward_number": answers.get("ward_number", ""),
            "discharge_date": schedule_data.get("date_display", ""),  # Keep for backward compatibility
            "discharge_time": f"{display_hour}:{minute:02d} {ampm}",  # Keep for backward compatibility
            "home_address": answers.get("home_address", ""),
            "home_latitude": home_geocode.get("latitude") if home_geocode else None,
            "home_longitude": home_geocode.get("longitude") if home_geocode else None,
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
            discharge_data["attachments"] = json.dumps(attachment_list)
        
        # Log the data being saved
        logger.info(f"Saving discharge data for {whatsapp_number} to a_s_hosptohome table")
        logger.info(f"Scheduled for: {scheduled_date} at {scheduled_time}")
        logger.info(f"Using provider ID: {provider_id}")
        
        # Save to database
        response = supabase.table("a_s_hosptohome").insert(discharge_data).execute()
        
        if response.data:
            logger.info(f"Ambulance discharge saved for {whatsapp_number}: {temp_data.get('discharge_id')}")
            
            # Prepare confirmation message
            distance_info = ""
            if distance_km is not None:
                distance_info = f"\n*Estimated Distance:* {distance_km:.1f} km\n"
            
            # Attachment info
            attachment_info = ""
            if attachments:
                attachment_info = f"\n*Attachments:* {len(attachments)} file(s) uploaded"
            
            # Remarks info
            remarks_info = ""
            if remarks:
                remarks_info = f"\n*Remarks:* {remarks[:50]}..."
            
            # Format scheduled time for display
            scheduled_display = f"{schedule_data.get('date_display', 'N/A')} at {display_hour}:{minute:02d} {ampm}"
            
            # FIXED: Split summary text into parts for better translation
            summary_parts = [
                "✅ *DISCHARGE TRANSPORT CONFIRMED*",
                f"Request ID: {temp_data.get('discharge_id')}",
                f"Patient: {answers.get('patient_name', 'N/A')}",
                f"Hospital: {answers.get('hospital_name', 'N/A')}",
                f"Discharge: {scheduled_display}",
                f"Destination: {answers.get('home_address', 'N/A')[:50]}...",
                f"Ward: {answers.get('ward_number', 'N/A')}",
                f"{distance_info}",
                f"{attachment_info}",
                f"{remarks_info}",
                "",
                "Your discharge transport request has been received. Our team will contact you to confirm details.",
                "",
                "*Next Steps:*",
                "1. Team will coordinate with hospital",
                "2. You'll receive confirmation call",
                "3. Ambulance will arrive 30 minutes before discharge",
                "",
                "Thank you for using AnyHealth Ambulance Service! 🚑"
            ]
            
            # Filter out empty strings and join
            summary_lines = [line for line in summary_parts if line]
            summary_text = "\n".join(summary_lines)
            
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": gt_tt(whatsapp_number, summary_text, supabase)}},
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
            logger.error(f"Failed to save discharge: {response}")
            raise Exception("Failed to save discharge to database")
            
    except Exception as e:
        logger.error(f"Error submitting ambulance discharge for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error submitting discharge request. Please try again.", supabase)}},
            supabase
        )
        return False