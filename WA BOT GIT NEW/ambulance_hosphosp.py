import logging
import uuid
import time
import json
import re
from datetime import datetime, timedelta
from utils import (
    send_whatsapp_message,
    gt_tt,
    gt_t_tt,
    calculate_distance,
    geocode_address,
    download_whatsapp_media,
    upload_to_supabase_storage,
    get_file_extension_from_mime,
    translate_template  # Added for static template translations
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define the sequence of questions for hospital to hospital transfer
HOSPHOSP_QUESTIONS = [
    {
        "key": "patient_name",
        "question": "1. Patient name\nExample: Ahmad bin Abdullah",
        "state": "HOSPHOSP_PATIENT_NAME"
    },
    {
        "key": "patient_ic",
        "question": "2. Patient IC number\nExample: 801212-14-5678",
        "state": "HOSPHOSP_PATIENT_IC",
        "validation": "ic"
    },
    {
        "key": "patient_phone",
        "question": "3. Patient phone number\nExample: 012-3456789",
        "state": "HOSPHOSP_PATIENT_PHONE"
    },
    {
        "key": "emergency_name",
        "question": "4. Emergency contact name\nExample: Siti binti Mohamad",
        "state": "HOSPHOSP_EMERGENCY_NAME"
    },
    {
        "key": "emergency_phone",
        "question": "5. Emergency contact phone\nExample: 019-8765432",
        "state": "HOSPHOSP_EMERGENCY_PHONE"
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
    """Format IC number to 12 digits without separators."""
    if not ic_input:
        return None
    
    digits_only = re.sub(r'\D', '', ic_input)
    
    if len(digits_only) != 12:
        return None
    
    return digits_only

def validate_ic_number(ic_input: str) -> bool:
    """Validate IC number format."""
    digits_only = re.sub(r'\D', '', ic_input)
    return len(digits_only) == 12

def format_translated_text(whatsapp_number: str, text: str, supabase, use_template: bool = False) -> str:
    """Format text with proper line breaks after translation.
    
    Args:
        whatsapp_number: User's WhatsApp number
        text: Original text with \n for line breaks
        supabase: Supabase client
        use_template: If True, use translate_template, else use gt_tt for dynamic content
    
    Returns:
        Formatted text with proper line breaks
    """
    try:
        # Split by lines, translate each line individually
        lines = text.split('\n')
        translated_lines = []
        
        for line in lines:
            if line.strip():  # Only translate non-empty lines
                if use_template:
                    translated_line = translate_template(whatsapp_number, line, supabase)
                else:
                    translated_line = gt_tt(whatsapp_number, line, supabase)
                translated_lines.append(translated_line)
            else:
                translated_lines.append("")  # Keep empty lines for spacing
        
        # Join with newlines to maintain original structure
        return '\n'.join(translated_lines)
        
    except Exception as e:
        logger.error(f"Error formatting translated text: {e}")
        # Fallback to simple translation
        if use_template:
            return translate_template(whatsapp_number, text, supabase)
        else:
            return gt_tt(whatsapp_number, text, supabase)

def handle_hosphosp_start(whatsapp_number: str, user_id: str, supabase, user_data: dict):
    """Start the hospital to hospital transfer process."""
    try:
        logger.info(f"Starting hospital to hospital transfer for {whatsapp_number}")
        
        # Generate transfer ID
        transfer_id = f"HTH{int(time.time()) % 1000000:06d}"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Store initial data
        user_data[whatsapp_number]["temp_data"] = {
            "transfer_id": transfer_id,
            "service_type": "hosp_to_hosp",
            "answers": {},
            "current_question_index": 0,
            "start_time": current_time,
            "schedule_data": {},
            "attachments": [],
            "remarks": "",
        }
        user_data[whatsapp_number]["state"] = "HOSPHOSP_STARTED"
        
        # Build confirmation text with proper line formatting
        confirmation_parts = [
            "🏥 *AMBULANCE SERVICE: HOSPITAL TO HOSPITAL TRANSFER*",
            "",
            f"Transfer ID: {transfer_id}",
            f"Time: {current_time}",
            "",
            "This service helps transfer patients between hospitals for specialized care.",
            "",
            "We'll collect information for your inter-hospital transfer.",
            "Please answer the following questions one by one.",
            "",
            "*IMPORTANT:*",
            "• Ensure both hospitals are aware of the transfer",
            "• Provide accurate hospital names", 
            "• We'll automatically find hospital addresses",
            "• Have medical files ready for transfer",
            "",
            "---",
            "*QUESTIONS TO FOLLOW:*",
            "1. Patient name",
            "2. Patient IC number", 
            "3. Patient phone number",
            "4. Emergency contact name",
            "5. Emergency contact phone",
            "6. Current hospital name (we'll find the address)",
            "7. Ward number and level (e.g., Ward 5A, Level 3)",
            "8. Destination hospital name (we'll find the address)",
            "*After these questions, you can upload attachments, add remarks, and schedule the transfer.*",
            "",
            "You can cancel anytime by typing 'cancel'."
        ]
        
        # Translate each line separately and join
        translated_lines = []
        for line in confirmation_parts:
            if line.strip():
                if any(word in line for word in ["*", "•", "---", "ID:", "Time:"]):
                    # Use gt_tt for dynamic content (IDs, times)
                    translated_lines.append(gt_tt(whatsapp_number, line, supabase))
                else:
                    # Use translate_template for static text
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
            else:
                translated_lines.append("")  # Keep empty lines
        
        confirmation_text = '\n'.join(translated_lines)
        
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
        send_next_hosphosp_question(whatsapp_number, user_data, supabase)
        
        return False
        
    except Exception as e:
        logger.error(f"Error starting hospital to hospital transfer for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error starting transfer request. Please try again.", supabase)}},
            supabase
        )
        return False

def send_next_hosphosp_question(whatsapp_number: str, user_data: dict, supabase):
    """Send the next question in the sequence with proper formatting."""
    try:
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        current_index = temp_data.get("current_question_index", 0)
        
        if current_index < len(HOSPHOSP_QUESTIONS):
            question_data = HOSPHOSP_QUESTIONS[current_index]
            
            # Format the question with proper line breaks
            question_text = format_translated_text(
                whatsapp_number, 
                question_data["question"], 
                supabase,
                use_template=True  # Use translate_template for questions since they are hardcoded
            )
            
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
            # All basic questions answered, ask for current hospital name
            ask_from_hospital_name(whatsapp_number, user_data, supabase)
            
    except Exception as e:
        logger.error(f"Error sending next question to {whatsapp_number}: {e}", exc_info=True)

def ask_from_hospital_name(whatsapp_number: str, user_data: dict, supabase):
    """Ask for current hospital name with proper formatting."""
    try:
        # Build the message with separate lines
        message_parts = [
            "6. *Current hospital name*",
            "",
            "Please type the name of the current hospital:",
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
        translated_lines = []
        for line in message_parts:
            if line.strip():
                if "Examples:" in line or "•" in line:
                    # Use translate_template for example lists (hardcoded)
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
                else:
                    # Use translate_template for static text
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
            else:
                translated_lines.append("")
        
        message_text = '\n'.join(translated_lines)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": message_text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "HOSPHOSP_FROM_HOSPITAL_NAME"
        
    except Exception as e:
        logger.error(f"Error asking current hospital name for {whatsapp_number}: {e}", exc_info=True)

def confirm_from_hospital_address(whatsapp_number: str, user_data: dict, supabase, hospital_name: str, hospital_address: str):
    """Ask user to confirm the automatically found current hospital address."""
    try:
        # Build the message body with proper formatting
        body_parts = [
            f"We found this address for *{hospital_name}*:",
            "",
            hospital_address,
            "",
            "Is this the correct hospital address?"
        ]
        
        # Translate each line separately
        translated_lines = []
        for line in body_parts:
            if line.strip():
                if hospital_name in line or hospital_address in line:
                    # Keep hospital name and address as is (they should be in English)
                    translated_lines.append(line)
                else:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
            else:
                translated_lines.append("")
        
        body_text = '\n'.join(translated_lines)
        
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "🏥 Current Hospital Address Found", supabase)
                },
                "body": {
                    "text": body_text
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "from_hospital_address_yes",
                                "title": translate_template(whatsapp_number, "✅ Yes, Correct", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "from_hospital_address_no",
                                "title": translate_template(whatsapp_number, "❌ No, Different", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "HOSPHOSP_FROM_HOSPITAL_ADDRESS_CONFIRM"
        
    except Exception as e:
        logger.error(f"Error confirming current hospital address for {whatsapp_number}: {e}", exc_info=True)

def ask_from_hospital_address_manual(whatsapp_number: str, user_data: dict, supabase):
    """Ask user to type current hospital address manually."""
    try:
        message_parts = [
            "Please type the current hospital address manually:",
            "",
            "Example:",
            "Jalan Pahang, 53000 Kuala Lumpur, Wilayah Persekutuan Kuala Lumpur",
            "",
            "Include full address with postcode and state."
        ]
        
        translated_lines = []
        for line in message_parts:
            if line.strip():
                if "Example:" in line or "Jalan Pahang" in line:
                    # Use translate_template for example addresses (hardcoded)
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
                else:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
            else:
                translated_lines.append("")
        
        message_text = '\n'.join(translated_lines)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": message_text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "HOSPHOSP_FROM_HOSPITAL_ADDRESS_MANUAL"
        
    except Exception as e:
        logger.error(f"Error asking current hospital address manual for {whatsapp_number}: {e}", exc_info=True)

def ask_from_ward_number(whatsapp_number: str, user_data: dict, supabase):
    """Ask for ward number and level number."""
    try:
        message_parts = [
            "7. *Ward number and level*",
            "",
            "Please provide the ward number and level:",
            "",
            "Examples:",
            "• Ward 5A, Level 3",
            "• ICU, Level 5", 
            "• Ward 3B, Ground Floor",
            "• Private Suite, Level 2",
            "",
            "Enter both ward and level together."
        ]
        
        translated_lines = []
        for line in message_parts:
            if line.strip():
                if "Examples:" in line or "•" in line:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
                else:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
            else:
                translated_lines.append("")
        
        message_text = '\n'.join(translated_lines)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": message_text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "HOSPHOSP_FROM_WARD_NUMBER"
        
    except Exception as e:
        logger.error(f"Error asking ward number for {whatsapp_number}: {e}", exc_info=True)

def ask_to_hospital_name(whatsapp_number: str, user_data: dict, supabase):
    """Ask for destination hospital name."""
    try:
        message_parts = [
            "8. *Destination hospital name*",
            "",
            "Please type the name of the destination hospital:",
            "",
            "Examples:",
            "• Hospital Kuala Lumpur",
            "• Sunway Medical Centre", 
            "• Pantai Hospital Kuala Lumpur",
            "• University Malaya Medical Centre",
            "",
            "We'll automatically find the address for you."
        ]
        
        translated_lines = []
        for line in message_parts:
            if line.strip():
                if "Examples:" in line or "•" in line:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
                else:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
            else:
                translated_lines.append("")
        
        message_text = '\n'.join(translated_lines)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": message_text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "HOSPHOSP_TO_HOSPITAL_NAME"
        
    except Exception as e:
        logger.error(f"Error asking destination hospital name for {whatsapp_number}: {e}", exc_info=True)

def confirm_to_hospital_address(whatsapp_number: str, user_data: dict, supabase, hospital_name: str, hospital_address: str):
    """Ask user to confirm the automatically found destination hospital address."""
    try:
        body_parts = [
            f"We found this address for *{hospital_name}*:",
            "",
            hospital_address,
            "",
            "Is this the correct hospital address?"
        ]
        
        translated_lines = []
        for line in body_parts:
            if line.strip():
                if hospital_name in line or hospital_address in line:
                    translated_lines.append(line)
                else:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
            else:
                translated_lines.append("")
        
        body_text = '\n'.join(translated_lines)
        
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "🏥 Destination Hospital Address Found", supabase)
                },
                "body": {
                    "text": body_text
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "to_hospital_address_yes",
                                "title": translate_template(whatsapp_number, "✅ Yes, Correct", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "to_hospital_address_no",
                                "title": translate_template(whatsapp_number, "❌ No, Different", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "HOSPHOSP_TO_HOSPITAL_ADDRESS_CONFIRM"
        
    except Exception as e:
        logger.error(f"Error confirming destination hospital address for {whatsapp_number}: {e}", exc_info=True)

def ask_to_hospital_address_manual(whatsapp_number: str, user_data: dict, supabase):
    """Ask user to type destination hospital address manually."""
    try:
        message_parts = [
            "Please type the destination hospital address manually:",
            "",
            "Example:",
            "Jalan Pahang, 53000 Kuala Lumpur, Wilayah Persekutuan Kuala Lumpur",
            "",
            "Include full address with postcode and state."
        ]
        
        translated_lines = []
        for line in message_parts:
            if line.strip():
                if "Example:" in line or "Jalan Pahang" in line:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
                else:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
            else:
                translated_lines.append("")
        
        message_text = '\n'.join(translated_lines)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": message_text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "HOSPHOSP_TO_HOSPITAL_ADDRESS_MANUAL"
        
    except Exception as e:
        logger.error(f"Error asking destination hospital address manual for {whatsapp_number}: {e}", exc_info=True)

def ask_for_attachments(whatsapp_number: str, user_data: dict, supabase):
    """Ask user to upload attachments."""
    try:
        body_parts = [
            "You can upload attachments (photos/documents) related to this transfer.",
            "",
            "Examples:",
            "• Medical reports",
            "• Doctor's referral letters", 
            "• Insurance documents",
            "• Transfer forms",
            "",
            "You can upload multiple attachments. When done, click 'Next'."
        ]
        
        translated_lines = []
        for line in body_parts:
            if line.strip():
                if "Examples:" in line or "•" in line:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
                else:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
            else:
                translated_lines.append("")
        
        body_text = '\n'.join(translated_lines)
        
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
                                "id": "hosphosp_attach_next",
                                "title": translate_template(whatsapp_number, "Next", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "hosphosp_attach_skip",
                                "title": translate_template(whatsapp_number, "Skip", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "HOSPHOSP_ATTACHMENTS"
        
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
        body_parts = [
            "Do you have any additional remarks or special instructions?",
            "",
            "Examples:",
            "• Specific medical equipment needed",
            "• Time constraints for transfer",
            "• Special handling requirements", 
            "• Additional patient information",
            "",
            "You can add remarks or skip to continue."
        ]
        
        translated_lines = []
        for line in body_parts:
            if line.strip():
                if "Examples:" in line or "•" in line:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
                else:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
            else:
                translated_lines.append("")
        
        body_text = '\n'.join(translated_lines)
        
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
                                "id": "hosphosp_remarks_add",
                                "title": translate_template(whatsapp_number, "Add Remarks", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "hosphosp_remarks_skip",
                                "title": translate_template(whatsapp_number, "Skip", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "HOSPHOSP_REMARKS"
        
    except Exception as e:
        logger.error(f"Error asking for remarks for {whatsapp_number}: {e}", exc_info=True)

def ask_remarks_text(whatsapp_number: str, user_data: dict, supabase):
    """Ask user to type remarks."""
    try:
        message_parts = [
            "Please type your remarks or special instructions:",
            "",
            "Examples:",
            "• Patient requires ventilator during transfer",
            "• Specific route preferred",
            "• Need ambulance with ICU facilities", 
            "• Coordination with specific hospital staff"
        ]
        
        translated_lines = []
        for line in message_parts:
            if line.strip():
                if "Examples:" in line or "•" in line:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
                else:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
            else:
                translated_lines.append("")
        
        message_text = '\n'.join(translated_lines)
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": message_text}},
            supabase
        )
        user_data[whatsapp_number]["state"] = "HOSPHOSP_REMARKS_TEXT"
        
    except Exception as e:
        logger.error(f"Error asking remarks text for {whatsapp_number}: {e}", exc_info=True)

def ask_schedule_date(whatsapp_number: str, user_data: dict, supabase):
    """Ask for transfer date with interactive buttons."""
    try:
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        # Format dates for display
        today_str = today.strftime("%d/%m/%Y")
        tomorrow_str = tomorrow.strftime("%d/%m/%Y")
        
        body_parts = [
            f"Please select the transfer date:",
            "",
            f"*Today:* {today_str}",
            f"*Tomorrow:* {tomorrow_str}",
            "",
            "If you need another date, select 'Others' and enter DD/MM/YYYY format."
        ]
        
        translated_lines = []
        for line in body_parts:
            if line.strip():
                if "Today:" in line or "Tomorrow:" in line:
                    # Keep date format as is, only translate the label
                    if "*Today:*" in line:
                        translated_line = translate_template(whatsapp_number, "*Today:*", supabase) + f" {today_str}"
                    elif "*Tomorrow:*" in line:
                        translated_line = translate_template(whatsapp_number, "*Tomorrow:*", supabase) + f" {tomorrow_str}"
                    else:
                        translated_line = translate_template(whatsapp_number, line, supabase)
                    translated_lines.append(translated_line)
                else:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
            else:
                translated_lines.append("")
        
        body_text = '\n'.join(translated_lines)
        
        content = {
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "📅 Select Transfer Date", supabase)
                },
                "body": {
                    "text": body_text
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "hosphosp_date_today",
                                "title": translate_template(whatsapp_number, "Today", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "hosphosp_date_tomorrow",
                                "title": translate_template(whatsapp_number, "Tomorrow", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "hosphosp_date_other",
                                "title": translate_template(whatsapp_number, "Others", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "HOSPHOSP_SCHEDULE_DATE"
        
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
        body_text = translate_template(whatsapp_number, "Please select AM or PM for the transfer time:", supabase)
        
        content = {
            "interactive": {
                "type": "button",
                "body": {
                    "text": body_text
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "hosphosp_ampm_am",
                                "title": translate_template(whatsapp_number, "AM (12am - 11:45am)", supabase)
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "hosphosp_ampm_pm",
                                "title": translate_template(whatsapp_number, "PM (12pm - 11:45pm)", supabase)
                            }
                        }
                    ]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "HOSPHOSP_SCHEDULE_AMPM"
        
    except Exception as e:
        logger.error(f"Error asking AM/PM for {whatsapp_number}: {e}", exc_info=True)

def ask_schedule_timeslot(whatsapp_number: str, user_data: dict, supabase, period: str):
    """Ask for 2-hour time slot selection."""
    try:
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        schedule_data = temp_data.get("schedule_data", {})
        
        # Get time slots for the selected period
        slots = TIME_SLOTS.get(period, [])
        
        # Translate slot labels
        for slot in slots:
            slot["translated_label"] = gt_tt(whatsapp_number, slot["label"], supabase)  # Use gt_tt for dynamic content
        
        # Create sections with rows for time slot selection
        sections = []
        rows = []
        
        for i, slot in enumerate(slots):
            rows.append({
                "id": f"hosphosp_slot_{slot['id']}",
                "title": slot["translated_label"]
            })
            
            if (i + 1) % 3 == 0 or i == len(slots) - 1:
                sections.append({
                    "title": gt_tt(whatsapp_number, f"{period} Time Slots", supabase),  # Use gt_tt for dynamic section title
                    "rows": rows.copy()
                })
                rows = []
        
        # If only one section, remove the title to save space
        if len(sections) == 1:
            sections[0]["title"] = ""
        
        body_parts = [
            f"Please select a 2-hour time slot for the transfer:",
            f"Selected Date: {schedule_data.get('date_display', 'N/A')}",
            f"Period: {period}",
            "",
            "After selecting a slot, you'll choose the exact 15-minute interval."
        ]
        
        translated_lines = []
        for line in body_parts:
            if line.strip():
                if "Selected Date:" in line or "Period:" in line:
                    # Keep the data, translate the label
                    if "Selected Date:" in line:
                        translated_line = translate_template(whatsapp_number, "Selected Date:", supabase) + f" {schedule_data.get('date_display', 'N/A')}"
                    elif "Period:" in line:
                        translated_line = translate_template(whatsapp_number, "Period:", supabase) + f" {period}"
                    else:
                        translated_line = translate_template(whatsapp_number, line, supabase)
                    translated_lines.append(translated_line)
                else:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
            else:
                translated_lines.append("")
        
        body_text = '\n'.join(translated_lines)
        
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
        user_data[whatsapp_number]["state"] = "HOSPHOSP_SCHEDULE_TIMESLOT"
        
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
        
        # Find the slot label
        slot_label = ""
        for slot in TIME_SLOTS.get(period, []):
            if slot["id"] in slot_id:
                slot_label = slot["label"]
                break
        
        # Generate 15-minute intervals
        intervals = []
        start_hour = 0
        for slot in TIME_SLOTS.get(period, []):
            if slot["id"] in slot_id:
                start_hour = slot["start_hour"]
                break
        
        for hour_offset in range(2):
            current_hour = start_hour + hour_offset
            for minute in [0, 15, 30, 45]:
                if hour_offset == 1 and minute == 45:
                    continue
                
                display_hour = current_hour % 12
                if display_hour == 0:
                    display_hour = 12
                
                ampm = "AM" if current_hour < 12 else "PM"
                if period == "AM" and current_hour >= 12:
                    ampm = "PM"
                
                time_str = f"{display_hour}:{minute:02d} {ampm}"
                interval_id = f"{current_hour:02d}{minute:02d}"
                
                intervals.append({
                    "id": f"hosphosp_interval_{interval_id}",
                    "title": time_str,
                    "hour": current_hour,
                    "minute": minute
                })
        
        # Create sections with rows
        sections = []
        rows = []
        
        for i, interval in enumerate(intervals):
            rows.append({
                "id": interval["id"],
                "title": interval["title"]
            })
            
            if (i + 1) % 4 == 0 or i == len(intervals) - 1:
                sections.append({
                    "title": gt_tt(whatsapp_number, slot_label, supabase),  # Use gt_tt for dynamic slot label
                    "rows": rows.copy()
                })
                rows = []
        
        if len(sections) == 1:
            sections[0]["title"] = ""
        
        body_parts = [
            f"Please select the exact time for the transfer:",
            f"Selected Date: {schedule_data.get('date_display', 'N/A')}",
            f"Selected Slot: {slot_label}",
            "",
            "Choose your preferred 15-minute interval within this slot."
        ]
        
        translated_lines = []
        for line in body_parts:
            if line.strip():
                if "Selected Date:" in line or "Selected Slot:" in line:
                    if "Selected Date:" in line:
                        translated_line = translate_template(whatsapp_number, "Selected Date:", supabase) + f" {schedule_data.get('date_display', 'N/A')}"
                    elif "Selected Slot:" in line:
                        translated_line = translate_template(whatsapp_number, "Selected Slot:", supabase) + f" {slot_label}"
                    else:
                        translated_line = translate_template(whatsapp_number, line, supabase)
                    translated_lines.append(translated_line)
                else:
                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
            else:
                translated_lines.append("")
        
        body_text = '\n'.join(translated_lines)
        
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
        user_data[whatsapp_number]["state"] = "HOSPHOSP_SCHEDULE_INTERVAL"
        
    except Exception as e:
        logger.error(f"Error asking minute interval for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error selecting time interval. Please try again.", supabase)}},
            supabase
        )

def handle_hosphosp_response(whatsapp_number: str, user_id: str, supabase, user_data: dict, message):
    """Handle user's response during hospital to hospital transfer."""
    try:
        # Check for cancellation
        if message.get("type") == "text":
            user_text = message["text"]["body"].strip().lower()
            if user_text == "cancel":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Hospital transfer cancelled. Returning to main menu.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                from utils import send_interactive_menu
                send_interactive_menu(whatsapp_number, supabase)
                return True
        
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        current_state = user_data[whatsapp_number].get("state", "")
        
        # Handle current hospital name input
        if current_state == "HOSPHOSP_FROM_HOSPITAL_NAME":
            if message.get("type") == "text":
                hospital_name = message["text"]["body"].strip()
                if hospital_name:
                    temp_data["answers"]["from_hospital_name"] = hospital_name
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    try:
                        send_whatsapp_message(
                            whatsapp_number,
                            "text",
                            {"text": {"body": gt_tt(
                                whatsapp_number,
                                f"🔍 Searching for *{hospital_name}*...",
                                supabase
                            )}},
                            supabase
                        )
                        
                        geocoded = geocode_address(hospital_name)
                        
                        if geocoded and geocoded.get("formatted_address"):
                            hospital_address = geocoded.get("formatted_address")
                            temp_data["answers"]["from_hospital_address_geocoded"] = hospital_address
                            temp_data["answers"]["from_hospital_latitude"] = geocoded.get("latitude")
                            temp_data["answers"]["from_hospital_longitude"] = geocoded.get("longitude")
                            user_data[whatsapp_number]["temp_data"] = temp_data
                            
                            time.sleep(1)
                            confirm_from_hospital_address(whatsapp_number, user_data, supabase, hospital_name, hospital_address)
                        else:
                            send_whatsapp_message(
                                whatsapp_number,
                                "text",
                                {"text": {"body": translate_template(
                                    whatsapp_number,
                                    "Could not find address for this hospital. Please provide the address manually.",
                                    supabase
                                )}},
                                supabase
                            )
                            ask_from_hospital_address_manual(whatsapp_number, user_data, supabase)
                    except Exception as e:
                        logger.error(f"Error geocoding hospital name: {e}")
                        ask_from_hospital_address_manual(whatsapp_number, user_data, supabase)
            return False
        
        # Handle current hospital address confirmation
        elif current_state == "HOSPHOSP_FROM_HOSPITAL_ADDRESS_CONFIRM":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "from_hospital_address_yes":
                    temp_data["answers"]["from_hospital_address"] = temp_data["answers"].get("from_hospital_address_geocoded", "")
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    ask_from_ward_number(whatsapp_number, user_data, supabase)
                elif button_id == "from_hospital_address_no":
                    ask_from_hospital_address_manual(whatsapp_number, user_data, supabase)
            return False
        
        # Handle manual current hospital address input
        elif current_state == "HOSPHOSP_FROM_HOSPITAL_ADDRESS_MANUAL":
            if message.get("type") == "text":
                hospital_address = message["text"]["body"].strip()
                if hospital_address:
                    temp_data["answers"]["from_hospital_address"] = hospital_address
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    ask_from_ward_number(whatsapp_number, user_data, supabase)
            return False
        
        # Handle ward number input
        elif current_state == "HOSPHOSP_FROM_WARD_NUMBER":
            if message.get("type") == "text":
                ward_number = message["text"]["body"].strip()
                if ward_number:
                    temp_data["answers"]["from_ward_number"] = ward_number
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    ask_to_hospital_name(whatsapp_number, user_data, supabase)
            return False
        
        # Handle destination hospital name input
        elif current_state == "HOSPHOSP_TO_HOSPITAL_NAME":
            if message.get("type") == "text":
                hospital_name = message["text"]["body"].strip()
                if hospital_name:
                    temp_data["answers"]["to_hospital_name"] = hospital_name
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    
                    try:
                        send_whatsapp_message(
                            whatsapp_number,
                            "text",
                            {"text": {"body": gt_tt(
                                whatsapp_number,
                                f"🔍 Searching for *{hospital_name}*...",
                                supabase
                            )}},
                            supabase
                        )
                        
                        geocoded = geocode_address(hospital_name)
                        
                        if geocoded and geocoded.get("formatted_address"):
                            hospital_address = geocoded.get("formatted_address")
                            temp_data["answers"]["to_hospital_address_geocoded"] = hospital_address
                            temp_data["answers"]["to_hospital_latitude"] = geocoded.get("latitude")
                            temp_data["answers"]["to_hospital_longitude"] = geocoded.get("longitude")
                            user_data[whatsapp_number]["temp_data"] = temp_data
                            
                            time.sleep(1)
                            confirm_to_hospital_address(whatsapp_number, user_data, supabase, hospital_name, hospital_address)
                        else:
                            send_whatsapp_message(
                                whatsapp_number,
                                "text",
                                {"text": {"body": translate_template(
                                    whatsapp_number,
                                    "Could not find address for this hospital. Please provide the address manually.",
                                    supabase
                                )}},
                                supabase
                            )
                            ask_to_hospital_address_manual(whatsapp_number, user_data, supabase)
                    except Exception as e:
                        logger.error(f"Error geocoding hospital name: {e}")
                        ask_to_hospital_address_manual(whatsapp_number, user_data, supabase)
            return False
        
        # Handle destination hospital address confirmation
        elif current_state == "HOSPHOSP_TO_HOSPITAL_ADDRESS_CONFIRM":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "to_hospital_address_yes":
                    temp_data["answers"]["to_hospital_address"] = temp_data["answers"].get("to_hospital_address_geocoded", "")
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    ask_for_attachments(whatsapp_number, user_data, supabase)
                elif button_id == "to_hospital_address_no":
                    ask_to_hospital_address_manual(whatsapp_number, user_data, supabase)
            return False
        
        # Handle manual destination hospital address input
        elif current_state == "HOSPHOSP_TO_HOSPITAL_ADDRESS_MANUAL":
            if message.get("type") == "text":
                hospital_address = message["text"]["body"].strip()
                if hospital_address:
                    temp_data["answers"]["to_hospital_address"] = hospital_address
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    ask_for_attachments(whatsapp_number, user_data, supabase)
            return False
        
        # Handle attachment states
        elif current_state == "HOSPHOSP_ATTACHMENTS":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "hosphosp_attach_next":
                    ask_remarks(whatsapp_number, user_data, supabase)
                elif button_id == "hosphosp_attach_skip":
                    temp_data["attachments"] = []
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    ask_remarks(whatsapp_number, user_data, supabase)
            elif message.get("type") in ["image", "document"]:
                handle_attachment(whatsapp_number, user_data, supabase, message)
            return False
        
        # Handle remarks option
        elif current_state == "HOSPHOSP_REMARKS":
            if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "hosphosp_remarks_add":
                    ask_remarks_text(whatsapp_number, user_data, supabase)
                elif button_id == "hosphosp_remarks_skip":
                    temp_data["remarks"] = ""
                    user_data[whatsapp_number]["temp_data"] = temp_data
                    ask_schedule_date(whatsapp_number, user_data, supabase)
            return False
        
        # Handle remarks text input
        elif current_state == "HOSPHOSP_REMARKS_TEXT":
            if message.get("type") == "text":
                remarks_text = message["text"]["body"].strip()
                if remarks_text:
                    temp_data["remarks"] = remarks_text
                    user_data[whatsapp_number]["temp_data"] = temp_data
                ask_schedule_date(whatsapp_number, user_data, supabase)
            return False
        
        # Handle schedule date and time states
        elif current_state == "HOSPHOSP_SCHEDULE_DATE":
            handle_schedule_date_response(whatsapp_number, user_data, supabase, message)
        elif current_state == "HOSPHOSP_SCHEDULE_DATE_OTHER":
            handle_date_other_response(whatsapp_number, user_data, supabase, message)
        elif current_state == "HOSPHOSP_SCHEDULE_AMPM":
            handle_ampm_response(whatsapp_number, user_data, supabase, message)
        elif current_state == "HOSPHOSP_SCHEDULE_TIMESLOT":
            handle_timeslot_response(whatsapp_number, user_data, supabase, message)
        elif current_state == "HOSPHOSP_SCHEDULE_INTERVAL":
            handle_interval_response(whatsapp_number, user_data, supabase, message)
        
        # Handle regular question responses with validation
        else:
            current_index = temp_data.get("current_question_index", 0)
            
            if current_index < len(HOSPHOSP_QUESTIONS):
                question_data = HOSPHOSP_QUESTIONS[current_index]
                answer_key = question_data["key"]
                answer = message["text"]["body"].strip() if message.get("type") == "text" else ""
                
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
                        error_parts = [
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
                        
                        translated_lines = []
                        for line in error_parts:
                            if line.strip():
                                if "•" in line or "❌" in line:
                                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
                                else:
                                    translated_lines.append(translate_template(whatsapp_number, line, supabase))
                            else:
                                translated_lines.append("")
                        
                        error_text = '\n'.join(translated_lines)
                        
                        send_whatsapp_message(
                            whatsapp_number,
                            "text",
                            {"text": {"body": error_text}},
                            supabase
                        )
                        return False
                    
                    answer = format_ic_number(answer)
                
                # Store answer
                temp_data["answers"][answer_key] = answer
                temp_data["current_question_index"] = current_index + 1
                user_data[whatsapp_number]["temp_data"] = temp_data
                
                send_next_hosphosp_question(whatsapp_number, user_data, supabase)
            else:
                ask_from_hospital_name(whatsapp_number, user_data, supabase)
                
        return False
        
    except Exception as e:
        logger.error(f"Error handling hosphosp response for {whatsapp_number}: {e}", exc_info=True)
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
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Unsupported file type. Please send images (JPEG, PNG) or documents (PDF, DOC) only.", supabase)}},
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
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        "Failed to download file from WhatsApp. Please try sending the file again.", supabase)}},
                    supabase
                )
                return
            
            # Generate unique filename
            unique_id = str(uuid.uuid4())[:8]
            safe_transfer_id = transfer_id.replace("/", "_").replace("\\", "_")
            final_file_name = f"{safe_transfer_id}_{unique_id}_{file_name}"
            
            # Create folder structure
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
            
            # Create message parts
            message_parts = [
                f"✅ *Attachment successfully saved!*",
                "",
                f"• File: {file_name[:40]}...",
                f"• Type: {attachment_info['type'].title()}",
                f"• Size: {file_size_mb:.2f} MB",
                f"• Total attachments: {len(attachments)}",
                "",
                "You can send more attachments or click 'Next' to continue."
            ]
            
            translated_lines = []
            for line in message_parts:
                if line.strip():
                    if "•" in line or "✅" in line:
                        translated_lines.append(translate_template(whatsapp_number, line, supabase))
                    else:
                        translated_lines.append(translate_template(whatsapp_number, line, supabase))
                else:
                    translated_lines.append("")
            
            body_text = '\n'.join(translated_lines)
            
            content = {
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": body_text
                    },
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "hosphosp_attach_next",
                                    "title": translate_template(whatsapp_number, "Next", supabase)
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "hosphosp_attach_skip",
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
                    "Failed to save attachment. Please try again or click 'Skip' to continue without attachments.", supabase)}},
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
            
            if button_id == "hosphosp_date_today":
                selected_date = today
            elif button_id == "hosphosp_date_tomorrow":
                selected_date = today + timedelta(days=1)
            elif button_id == "hosphosp_date_other":
                # Ask for custom date input
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        "Please enter the transfer date in DD/MM/YYYY format:\nExample: 25/12/2024",
                        supabase
                    )}},
                    supabase
                )
                user_data[whatsapp_number]["state"] = "HOSPHOSP_SCHEDULE_DATE_OTHER"
                return
            else:
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Invalid selection. Please try again.", supabase)}},
                    supabase
                )
                ask_schedule_date(whatsapp_number, user_data, supabase)
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
                        {"text": {"body": translate_template(
                            whatsapp_number,
                            "Date cannot be in the past. Please enter a future date in DD/MM/YYYY format.",
                            supabase
                        )}},
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
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        "Invalid date format. Please enter date in DD/MM/YYYY format.\nExample: 25/12/2024",
                        supabase
                    )}},
                    supabase
                )
                
    except Exception as e:
        logger.error(f"Error handling date other response for {whatsapp_number}: {e}", exc_info=True)

def handle_ampm_response(whatsapp_number: str, user_data: dict, supabase, message):
    """Handle AM/PM selection response."""
    try:
        if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
            button_id = message["interactive"]["button_reply"]["id"]
            
            period = "AM" if button_id == "hosphosp_ampm_am" else "PM"
            
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
            
            # Extract slot ID
            parts = list_id.split("_")
            if len(parts) >= 3:
                slot_id = "_".join(parts[2:])
                
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
                period = schedule_data.get("period", "AM")
                ask_schedule_timeslot(whatsapp_number, user_data, supabase, period)
                
    except Exception as e:
        logger.error(f"Error handling time slot response for {whatsapp_number}: {e}", exc_info=True)

def handle_interval_response(whatsapp_number: str, user_data: dict, supabase, message):
    """Handle 15-minute interval selection response and submit transfer."""
    try:
        if message.get("type") == "interactive" and message["interactive"].get("type") == "list_reply":
            list_id = message["interactive"]["list_reply"]["id"]
            
            # Extract interval
            parts = list_id.split("_")
            if len(parts) >= 3:
                interval_str = parts[2]
                
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
                submit_hosphosp_transfer(whatsapp_number, user_data, supabase)
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

def submit_hosphosp_transfer(whatsapp_number: str, user_data: dict, supabase):
    """Submit the hospital to hospital transfer to database (a_s_hosptohosp table)."""
    try:
        temp_data = user_data[whatsapp_number].get("temp_data", {})
        answers = temp_data.get("answers", {})
        schedule_data = temp_data.get("schedule_data", {})
        attachments = temp_data.get("attachments", [])
        remarks = temp_data.get("remarks", "")
        
        # Get hospital addresses
        from_hospital_name = answers.get("from_hospital_name", "")
        from_hospital_address = answers.get("from_hospital_address", "")
        to_hospital_name = answers.get("to_hospital_name", "")
        to_hospital_address = answers.get("to_hospital_address", "")
        
        # Get coordinates if available
        from_hospital_latitude = answers.get("from_hospital_latitude")
        from_hospital_longitude = answers.get("from_hospital_longitude")
        to_hospital_latitude = answers.get("to_hospital_latitude")
        to_hospital_longitude = answers.get("to_hospital_longitude")
        
        # Geocode addresses if not already geocoded
        if not from_hospital_latitude or not from_hospital_longitude:
            from_geocode = geocode_address(from_hospital_address) if from_hospital_address else None
            if from_geocode:
                from_hospital_latitude = from_geocode.get("latitude")
                from_hospital_longitude = from_geocode.get("longitude")
        
        if not to_hospital_latitude or not to_hospital_longitude:
            to_geocode = geocode_address(to_hospital_address) if to_hospital_address else None
            if to_geocode:
                to_hospital_latitude = to_geocode.get("latitude")
                to_hospital_longitude = to_geocode.get("longitude")
        
        # Calculate distance if we have coordinates
        distance_km = None
        if from_hospital_latitude and from_hospital_longitude and to_hospital_latitude and to_hospital_longitude:
            distance_km = calculate_distance(
                from_hospital_latitude,
                from_hospital_longitude,
                to_hospital_latitude,
                to_hospital_longitude
            )
            logger.info(f"Distance calculated for hospital transfer: {distance_km:.2f} km")
        
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
        
        # Prepare attachments as JSON array
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
        
        # Prepare transfer data
        transfer_data = {
            "id": str(uuid.uuid4()),
            "transfer_id": temp_data.get("transfer_id", ""),
            "whatsapp_number": whatsapp_number.lstrip("+"),
            "patient_name": answers.get("patient_name", ""),
            "patient_age": None,
            "patient_ic": answers.get("patient_ic", ""),
            "patient_phone": answers.get("patient_phone", ""),
            "emergency_name": answers.get("emergency_name", ""),
            "emergency_phone": answers.get("emergency_phone", ""),
            "from_hospital_name": from_hospital_name,
            "from_hospital_address": from_hospital_address,
            "from_ward_number": answers.get("from_ward_number", ""),
            "from_hospital_latitude": from_hospital_latitude,
            "from_hospital_longitude": from_hospital_longitude,
            "to_hospital_name": to_hospital_name,
            "to_hospital_address": to_hospital_address,
            "to_ward_number": "",
            "to_hospital_latitude": to_hospital_latitude,
            "to_hospital_longitude": to_hospital_longitude,
            "transfer_reason": "",
            "special_requirements": remarks,
            "doctor_name": "",
            "doctor_contact": "",
            "status": "pending",
            "provider_id": provider_id,
            "distance_km": distance_km,
            "dispatched_status": "scheduled",
            "scheduled_date": scheduled_date,
            "scheduled_time": scheduled_time,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Add attachments as JSON array if attachments exist
        if attachment_list:
            transfer_data["medical_files"] = json.dumps(attachment_list)
        
        # Log the data being saved
        logger.info(f"Saving hospital transfer data for {whatsapp_number} to a_s_hosptohosp table")
        logger.info(f"Scheduled for: {scheduled_date} at {scheduled_time}")
        logger.info(f"Using provider ID: {provider_id}")
        
        # Save to database
        response = supabase.table("a_s_hosptohosp").insert(transfer_data).execute()
        
        if response.data:
            logger.info(f"Hospital to hospital transfer saved for {whatsapp_number}: {temp_data.get('transfer_id')}")
            
            # Build summary text with proper formatting
            distance_info = ""
            if distance_km is not None:
                distance_info = f"\n*Estimated Distance:* {distance_km:.1f} km\n"
            
            attachment_info = ""
            if attachments:
                attachment_info = f"\n*Attachments:* {len(attachments)} file(s) uploaded"
            
            remarks_info = ""
            if remarks:
                remarks_info = f"\n*Remarks:* {remarks[:50]}..."
            
            # Format scheduled time for display
            scheduled_display = f"{schedule_data.get('date_display', 'N/A')} at {display_hour}:{minute:02d} {ampm}"
            
            # Build summary parts
            summary_parts = [
                "✅ *HOSPITAL TO HOSPITAL TRANSFER CONFIRMED*",
                "",
                f"Transfer ID: {temp_data.get('transfer_id')}",
                f"Patient: {answers.get('patient_name', 'N/A')}",
                f"From: {from_hospital_name[:50]}...",
                f"To: {to_hospital_name[:50]}...",
                f"Ward: {answers.get('from_ward_number', 'N/A')}",
                f"Scheduled: {scheduled_display}"
            ]
            
            if distance_km is not None:
                summary_parts.append(f"*Estimated Distance:* {distance_km:.1f} km")
            
            if attachments:
                summary_parts.append(f"*Attachments:* {len(attachments)} file(s) uploaded")
            
            if remarks:
                summary_parts.append(f"*Remarks:* {remarks[:50]}...")
            
            summary_parts.extend([
                "",
                "Your inter-hospital transfer request has been received. Our team will coordinate with both hospitals.",
                "",
                "*Next Steps:*",
                "1. Team will contact both hospitals",
                "2. You'll receive confirmation call", 
                "3. Transfer schedule will be arranged",
                "",
                "Thank you for using AnyHealth Ambulance Service! 🚑"
            ])
            
            # Translate each line
            translated_lines = []
            for line in summary_parts:
                if line.strip():
                    if any(word in line for word in ["*", "Transfer ID:", "Patient:", "From:", "To:", "Ward:", "Scheduled:", "Estimated Distance:", "Attachments:", "Remarks:"]):
                        # Use gt_tt for dynamic content
                        translated_lines.append(gt_tt(whatsapp_number, line, supabase))
                    else:
                        # Use translate_template for static text
                        translated_lines.append(translate_template(whatsapp_number, line, supabase))
                else:
                    translated_lines.append("")
            
            summary_text = '\n'.join(translated_lines)
            
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
            logger.error(f"Failed to save hospital transfer: {response}")
            raise Exception("Failed to save hospital transfer to database")
            
    except Exception as e:
        logger.error(f"Error submitting hospital transfer for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error submitting transfer request. Please try again.", supabase)}},
            supabase
        )
        return False