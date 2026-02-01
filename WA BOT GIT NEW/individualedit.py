# individualedit.py (updated - fix state management after reset)
import logging
import re
import time
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

# WhatsApp character limits
MAX_TITLE_LENGTH = 24
MAX_BUTTON_TEXT = 20
MAX_HEADER_TEXT = 60
MAX_BODY_TEXT = 1024

from utils import (
    send_whatsapp_message,
    translate_template,
    gt_t_tt,
    gt_tt,
    gt_dt_tt,
    get_user_id
)

def truncate_text(text, max_length, add_ellipsis=True):
    """Truncate text to max_length, adding ellipsis if needed."""
    if not text:
        return ""
    
    if len(text) > max_length:
        if add_ellipsis:
            return text[:max_length-3] + "..."
        else:
            return text[:max_length]
    return text

def validate_ic_number(ic_number):
    """Validate Malaysian IC number format."""
    # Remove any dashes or spaces
    ic_clean = re.sub(r'[-\s]', '', ic_number)
    
    # Check if it's 12 digits
    if not re.match(r'^\d{12}$', ic_clean):
        return False, translate_template("whatsapp_number", "IC must be 12 digits", None)  # Use translate_template for error message
        # Note: We don't have whatsapp_number here, so we pass a placeholder
    
    return True, ic_clean

def format_ic_display(ic_number):
    """Format IC for display (XXXXXX-XX-XXXX)."""
    ic_clean = re.sub(r'[-\s]', '', ic_number)
    if len(ic_clean) == 12:
        return f"{ic_clean[:6]}-{ic_clean[6:8]}-{ic_clean[8:]}"
    return ic_number

def show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data):
    """Show edit profiles menu (add/remove) - NO PASSWORD REQUIRED."""
    try:
        # This menu can use buttons since it has exactly 3 options
        buttons = [
            {
                "type": "reply",
                "reply": {
                    "id": "add_profile",
                    "title": translate_template(whatsapp_number, "➕ Add Profile", supabase)  # CHANGED from gt_t_tt to translate_template
                }
            },
            {
                "type": "reply",
                "reply": {
                    "id": "remove_profile",
                    "title": translate_template(whatsapp_number, "➖ Remove Profile", supabase)  # CHANGED from gt_t_tt to translate_template
                }
            },
            {
                "type": "reply",
                "reply": {
                    "id": "back_to_profiles",
                    "title": translate_template(whatsapp_number, "🔙 Back to Profiles", supabase)  # CHANGED from gt_t_tt to translate_template
                }
            }
        ]
        
        content = {
            "interactive": {
                "type": "button",
                "body": {
                    "text": translate_template(whatsapp_number, "Edit Profiles Menu:", supabase)  # CHANGED from gt_tt to translate_template
                },
                "action": {
                    "buttons": buttons
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "INDIVIDUAL_EDIT_MENU"
        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in show_edit_profiles_menu for {whatsapp_number}: {e}")
        from individual import show_profile_management_menu
        return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data)

def start_add_profile(whatsapp_number, user_id, supabase, user_data):
    """Start add profile flow - ask for IC number."""
    try:
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Please enter the IC number (12 digits):\n" +
                "Format: XXXXXX-XX-XXXX or XXXXXX XX XXXX or XXXXXXXXXXXX\n\n" +
                "Note: Only Malaysian IC accepted, no passport.", supabase)}}
        )
        
        user_data[whatsapp_number]["state"] = "INDIVIDUAL_ADD_IC"
        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in start_add_profile for {whatsapp_number}: {e}")
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def handle_add_profile_ic(whatsapp_number, user_id, supabase, user_data, ic_number):
    """Handle IC number input for add profile."""
    try:
        # Validate IC number
        is_valid, result = validate_ic_number(ic_number)
        
        if not is_valid:
            # result contains the error message from validate_ic_number
            error_msg = result if isinstance(result, str) else "Invalid IC format"
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    f"Invalid IC: {error_msg}. Please enter a valid 12-digit Malaysian IC:", supabase)}}
            )
            return False
        
        # Check if IC already exists
        response = supabase.table("patient_id").select("id, wa_user_id, patient_name, change_acc_error").eq("ic_passport", result).execute()
        
        if response.data:
            patient_data = response.data[0]
            
            # Check if IC is already attached to ANOTHER WhatsApp account
            if patient_data["wa_user_id"] and patient_data["wa_user_id"] != user_id:
                # Check if change_acc_error is 3 or more (handle None)
                change_acc_error = patient_data.get("change_acc_error")
                if change_acc_error is None:
                    change_acc_error = 0
                    
                if change_acc_error >= 3:
                    send_whatsapp_message(
                        whatsapp_number, "text",
                        {"text": {"body": translate_template(whatsapp_number, 
                            "❌ This IC has reached maximum detachment attempts.\n" +
                            "Please email contact@anyhealth.asia or visit partner clinics.", supabase)}}
                    )
                    return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
                
                # Store patient data for detachment
                user_data[whatsapp_number]["individual_data"]["detach_patient_data"] = patient_data
                
                # Ask if user wants to detach
                buttons = [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "detach_yes",
                            "title": translate_template(whatsapp_number, "Yes, detach", supabase)  # CHANGED from gt_t_tt to translate_template
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "detach_no",
                            "title": translate_template(whatsapp_number, "No, cancel", supabase)  # CHANGED from gt_t_tt to translate_template
                        }
                    }
                ]
                
                content = {
                    "interactive": {
                        "type": "button",
                        "body": {
                            "text": translate_template(whatsapp_number,  # CHANGED from gt_tt to translate_template
                                f"This IC is registered to another WhatsApp account.\n" +
                                f"Name: {patient_data['patient_name']}\n\n" +
                                "Do you want to detach it from the old account?", supabase)
                        },
                        "action": {
                            "buttons": buttons
                        }
                    }
                }
                
                send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
                user_data[whatsapp_number]["state"] = "DETACH_CONFIRM"
                user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
                return False
            elif patient_data["wa_user_id"] == user_id:
                # IC already registered to current user
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        "✅ This IC is already registered to your account.", supabase)}}
                )
                return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
        
        # If IC not found or belongs to current user, continue with normal flow
        # Store IC and ask for name
        user_data[whatsapp_number]["individual_data"]["temp_profile_data"] = {
            "ic_passport": result
        }
        
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Please enter the full name:", supabase)}}
        )
        
        user_data[whatsapp_number]["state"] = "INDIVIDUAL_ADD_NAME"
        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in handle_add_profile_ic for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error processing IC. Please try again.", supabase)}}
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def handle_add_profile_name(whatsapp_number, user_id, supabase, user_data, name):
    """Handle name input for add profile."""
    try:
        if not name or len(name.strip()) < 2:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Invalid name. Please enter a valid name (minimum 2 characters):", supabase)}}
            )
            return False
        
        # Store name
        user_data[whatsapp_number]["individual_data"]["temp_profile_data"]["patient_name"] = name.strip()
        
        # Nationality is always Malaysian
        user_data[whatsapp_number]["individual_data"]["temp_profile_data"]["nationality"] = "Malaysian"
        
        # Ask for race using LIST (not buttons)
        race_options = [
            {"id": "race_malay", "title": translate_template(whatsapp_number, "Malay", supabase)},  # Hardcoded race names
            {"id": "race_chinese", "title": translate_template(whatsapp_number, "Chinese", supabase)},
            {"id": "race_indian", "title": translate_template(whatsapp_number, "Indian", supabase)},
            {"id": "race_bumiputera_sabah", "title": translate_template(whatsapp_number, "Bumiputera Sabah", supabase)},
            {"id": "race_bumiputera_sarawak", "title": translate_template(whatsapp_number, "Bumiputera Sarawak", supabase)},
            {"id": "race_other", "title": translate_template(whatsapp_number, "Others", supabase)}
        ]
        
        # Prepare rows for list message
        rows = []
        for option in race_options:
            display_title = truncate_text(option["title"], MAX_TITLE_LENGTH)  # Already translated
            rows.append({
                "id": option["id"],
                "title": display_title
            })
        
        # Add back button
        rows.append({
            "id": "back_to_edit",
            "title": translate_template(whatsapp_number, "🔙 Back to Edit Menu", supabase)  # Already using translate_template
        })
        
        # Send race selection list
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text", 
                    "text": truncate_text(translate_template(whatsapp_number, "Select Race", supabase), MAX_HEADER_TEXT)
                },
                "body": {
                    "text": truncate_text(
                        translate_template(whatsapp_number, "Select race:", supabase),
                        MAX_BODY_TEXT
                    )
                },
                "action": {
                    "button": truncate_text(
                        translate_template(whatsapp_number, "Select Race", supabase),
                        MAX_BUTTON_TEXT
                    ),
                    "sections": [{
                        "title": truncate_text(
                            translate_template(whatsapp_number, "Available Races", supabase),
                            MAX_TITLE_LENGTH
                        ),
                        "rows": rows
                    }]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "INDIVIDUAL_ADD_RACE"
        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in handle_add_profile_name for {whatsapp_number}: {e}")
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error processing name. Please try again.", supabase)}}
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def handle_add_profile_race(whatsapp_number, user_id, supabase, user_data, race, is_other=False):
    """Handle race selection for add profile."""
    try:
        race_map = {
            "race_malay": translate_template(whatsapp_number, "Malay", supabase),
            "race_chinese": translate_template(whatsapp_number, "Chinese", supabase),
            "race_indian": translate_template(whatsapp_number, "Indian", supabase),
            "race_bumiputera_sabah": translate_template(whatsapp_number, "Bumiputera Sabah", supabase),
            "race_bumiputera_sarawak": translate_template(whatsapp_number, "Bumiputera Sarawak", supabase),
            "race_other": translate_template(whatsapp_number, "Others", supabase)
        }
        
        if is_other:
            if not race or len(race.strip()) < 2:
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        "Please specify the race (minimum 2 characters):", supabase)}}
                )
                return False
            
            user_data[whatsapp_number]["individual_data"]["temp_profile_data"]["race"] = race.strip()
        else:
            if race == "back_to_edit":
                return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
                
            if race not in race_map:
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        "Invalid selection. Please select a race from the list:", supabase)}}
                )
                return handle_add_profile_name(whatsapp_number, user_id, supabase, user_data, 
                    user_data[whatsapp_number]["individual_data"]["temp_profile_data"]["patient_name"])
            
            race_value = race_map[race]
            if race == "race_other":  # Check if "Others" was selected
                # Ask for specific race
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        "Please specify the race:", supabase)}}
                )
                user_data[whatsapp_number]["state"] = "INDIVIDUAL_ADD_RACE_OTHER"
                user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
                return False
            
            user_data[whatsapp_number]["individual_data"]["temp_profile_data"]["race"] = race_value
        
        # Ask for religion using LIST
        religion_options = [
            {"id": "religion_muslim", "title": translate_template(whatsapp_number, "Muslim", supabase)},
            {"id": "religion_buddhist", "title": translate_template(whatsapp_number, "Buddhist", supabase)},
            {"id": "religion_christian", "title": translate_template(whatsapp_number, "Christian", supabase)},
            {"id": "religion_hindu", "title": translate_template(whatsapp_number, "Hindu", supabase)},
            {"id": "religion_sikh", "title": translate_template(whatsapp_number, "Sikh", supabase)},
            {"id": "religion_other", "title": translate_template(whatsapp_number, "Others", supabase)}
        ]
        
        # Prepare rows for list message
        rows = []
        for option in religion_options:
            display_title = truncate_text(option["title"], MAX_TITLE_LENGTH)  # Already translated
            rows.append({
                "id": option["id"],
                "title": display_title
            })
        
        # Add back button
        rows.append({
            "id": "back_to_race",
            "title": translate_template(whatsapp_number, "🔙 Back to Race Selection", supabase)  # Already using translate_template
        })
        
        # Send religion selection list
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text", 
                    "text": truncate_text(translate_template(whatsapp_number, "Select Religion", supabase), MAX_HEADER_TEXT)
                },
                "body": {
                    "text": truncate_text(
                        translate_template(whatsapp_number, "Select religion:", supabase),
                        MAX_BODY_TEXT
                    )
                },
                "action": {
                    "button": truncate_text(
                        translate_template(whatsapp_number, "Select Religion", supabase),
                        MAX_BUTTON_TEXT
                    ),
                    "sections": [{
                        "title": truncate_text(
                            translate_template(whatsapp_number, "Available Religions", supabase),
                            MAX_TITLE_LENGTH
                        ),
                        "rows": rows
                    }]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "INDIVIDUAL_ADD_RELIGION"
        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in handle_add_profile_race for {whatsapp_number}: {e}")
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error processing race. Please try again.", supabase)}}
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def handle_add_profile_religion(whatsapp_number, user_id, supabase, user_data, religion, is_other=False):
    """Handle religion selection for add profile."""
    try:
        religion_map = {
            "religion_muslim": translate_template(whatsapp_number, "Muslim", supabase),
            "religion_buddhist": translate_template(whatsapp_number, "Buddhist", supabase),
            "religion_christian": translate_template(whatsapp_number, "Christian", supabase),
            "religion_hindu": translate_template(whatsapp_number, "Hindu", supabase),
            "religion_sikh": translate_template(whatsapp_number, "Sikh", supabase),
            "religion_other": translate_template(whatsapp_number, "Others", supabase)
        }
        
        if is_other:
            if not religion or len(religion.strip()) < 2:
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        "Please specify the religion (minimum 2 characters):", supabase)}}
                )
                return False
            
            user_data[whatsapp_number]["individual_data"]["temp_profile_data"]["religion"] = religion.strip()
        else:
            if religion == "back_to_race":
                # Go back to race selection
                return handle_add_profile_name(whatsapp_number, user_id, supabase, user_data,
                    user_data[whatsapp_number]["individual_data"]["temp_profile_data"]["patient_name"])
                
            if religion not in religion_map:
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        "Invalid selection. Please select a religion from the list:", supabase)}}
                )
                return False
            
            religion_value = religion_map[religion]
            if religion == "religion_other":  # Check if "Others" was selected
                # Ask for specific religion
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        "Please specify the religion:", supabase)}}
                )
                user_data[whatsapp_number]["state"] = "INDIVIDUAL_ADD_RELIGION_OTHER"
                user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
                return False
            
            user_data[whatsapp_number]["individual_data"]["temp_profile_data"]["religion"] = religion_value
        
        # Ask for blood type using LIST
        blood_type_options = [
            {"id": "blood_a_plus", "title": "A+"},  # Blood types are symbols, not translated
            {"id": "blood_b_plus", "title": "B+"},
            {"id": "blood_ab_plus", "title": "AB+"},
            {"id": "blood_o_plus", "title": "O+"},
            {"id": "blood_a_minus", "title": "A-"},
            {"id": "blood_b_minus", "title": "B-"},
            {"id": "blood_ab_minus", "title": "AB-"},
            {"id": "blood_o_minus", "title": "O-"}
        ]
        
        # Prepare rows for list message (split into two sections if needed)
        rows = []
        for option in blood_type_options:
            display_title = truncate_text(option["title"], MAX_TITLE_LENGTH)  # Blood type symbols not translated
            rows.append({
                "id": option["id"],
                "title": display_title
            })
        
        # Add back button
        rows.append({
            "id": "back_to_religion",
            "title": translate_template(whatsapp_number, "🔙 Back to Religion", supabase)  # Already using translate_template
        })
        
        # Send blood type selection list
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text", 
                    "text": truncate_text(translate_template(whatsapp_number, "Select Blood Type", supabase), MAX_HEADER_TEXT)
                },
                "body": {
                    "text": truncate_text(
                        translate_template(whatsapp_number, "Select blood type:", supabase),
                        MAX_BODY_TEXT
                    )
                },
                "action": {
                    "button": truncate_text(
                        translate_template(whatsapp_number, "Select Blood Type", supabase),
                        MAX_BUTTON_TEXT
                    ),
                    "sections": [{
                        "title": truncate_text(
                            translate_template(whatsapp_number, "Blood Types", supabase),
                            MAX_TITLE_LENGTH
                        ),
                        "rows": rows
                    }]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "INDIVIDUAL_ADD_BLOOD_TYPE"
        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in handle_add_profile_religion for {whatsapp_number}: {e}")
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error processing religion. Please try again.", supabase)}}
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def handle_add_profile_blood_type(whatsapp_number, user_id, supabase, user_data, blood_type):
    """Handle blood type selection and save profile."""
    try:
        blood_type_map = {
            "blood_a_plus": "A+",
            "blood_b_plus": "B+",
            "blood_ab_plus": "AB+",
            "blood_o_plus": "O+",
            "blood_a_minus": "A-",
            "blood_b_minus": "B-",
            "blood_ab_minus": "AB-",
            "blood_o_minus": "O-"
        }
        
        if blood_type == "back_to_religion":
            # Go back to religion selection
            religion_value = user_data[whatsapp_number]["individual_data"]["temp_profile_data"].get("religion")
            if religion_value == translate_template(whatsapp_number, "Others", supabase):
                # If it was "Others", we need to ask for specific religion again
                user_data[whatsapp_number]["state"] = "INDIVIDUAL_ADD_RELIGION"
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        "Please select religion again:", supabase)}}
                )
                return False
            else:
                # Find the religion ID
                religion_id = None
                for key, value in {
                    "religion_muslim": translate_template(whatsapp_number, "Muslim", supabase),
                    "religion_buddhist": translate_template(whatsapp_number, "Buddhist", supabase),
                    "religion_christian": translate_template(whatsapp_number, "Christian", supabase),
                    "religion_hindu": translate_template(whatsapp_number, "Hindu", supabase),
                    "religion_sikh": translate_template(whatsapp_number, "Sikh", supabase)
                }.items():
                    if value == religion_value:
                        religion_id = key
                        break
                
                if religion_id:
                    return handle_add_profile_religion(whatsapp_number, user_id, supabase, user_data, 
                        religion_id, is_other=False)
                else:
                    return handle_add_profile_religion(whatsapp_number, user_id, supabase, user_data, 
                        "religion_other", is_other=False)
        
        if blood_type not in blood_type_map:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Invalid selection. Please select a blood type from the list:", supabase)}}
            )
            return False
        
        # Get profile data
        temp_data = user_data[whatsapp_number]["individual_data"]["temp_profile_data"]
        
        # FIRST: Get WhatsApp user ID from the phone number
        user_response = supabase.table("whatsapp_users").select("id").eq("whatsapp_number", whatsapp_number).execute()
        
        if not user_response.data:
            logger.error(f"No WhatsApp user found for number: {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Error: WhatsApp user not found. Please try again.", supabase)}}
            )
            return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
        
        wa_user_id_from_phone = user_response.data[0]["id"]
        logger.info(f"Found WhatsApp user ID {wa_user_id_from_phone} for number {whatsapp_number}")
        
        # Prepare patient data
        patient_data = {
            "patient_name": temp_data["patient_name"],
            "nationality": temp_data["nationality"],
            "ic_passport": temp_data["ic_passport"],
            "race": temp_data.get("race"),
            "religion": temp_data.get("religion"),
            "blood_type": blood_type_map[blood_type],
            "wa_user_id": wa_user_id_from_phone,
            "error": 0,
            "change_acc_error": 0
        }
        
        # Debug log
        logger.info(f"Inserting patient data with wa_user_id: {wa_user_id_from_phone}")
        
        # Insert into database
        response = supabase.table("patient_id").insert(patient_data).execute()
        
        if response.data:
            # Success
            patient_name = temp_data["patient_name"]
            ic_display = format_ic_display(temp_data["ic_passport"])
            
            # Keep patient name and blood type in English (not translated)
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    f"✅ Profile created successfully!\n\n" +
                    f"Name: {patient_name}\n" +
                    f"IC: {ic_display}\n" +
                    f"Nationality: Malaysian\n" +
                    f"Race: {temp_data.get('race', 'Not specified')}\n" +
                    f"Religion: {temp_data.get('religion', 'Not specified')}\n" +
                    f"Blood Type: {blood_type_map[blood_type]}", supabase)}}
            )
            
            # Clear temp data
            user_data[whatsapp_number]["individual_data"]["temp_profile_data"] = {}
            
            # Refresh patient list - IMPORTANT: Set module back to individual
            from individual import handle_individual_start
            user_data[whatsapp_number]["module"] = "individual"  # Reset module to individual
            return handle_individual_start(whatsapp_number, user_id, supabase, user_data)
        else:
            logger.error(f"Failed to insert patient data. Response: {response}")
            raise Exception("Failed to insert patient data")
        
    except Exception as e:
        logger.error(f"Error in handle_add_profile_blood_type for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                f"Error creating profile: {str(e)[:100]}", supabase)}}
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def start_remove_profile(whatsapp_number, user_id, supabase, user_data):
    """Start remove profile flow - show patient selection with warning."""
    try:
        # Get all patients for this user
        patients_response = supabase.table("patient_id").select(
            "id, patient_name"
        ).eq("wa_user_id", user_id).execute()
        
        patients = patients_response.data if patients_response.data else []
        
        if not patients:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "No profiles found to remove.", supabase)}}
            )
            return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
        
        # First show warning message
        warning_msg = translate_template(whatsapp_number, 
            "⚠️ WARNING: Removing a profile will erase all previous data.\n" +
            "To undo this action, you will need to visit our nearest partner clinics.\n\n" +
            "Are you sure you want to continue?", supabase)
        
        send_whatsapp_message(whatsapp_number, "text", {"text": {"body": warning_msg}})
        
        time.sleep(1)
        
        # Then ask for confirmation
        buttons = [
            {
                "type": "reply",
                "reply": {
                    "id": "warning_yes",
                    "title": translate_template(whatsapp_number, "Yes", supabase)  # CHANGED from gt_t_tt to translate_template
                }
            },
            {
                "type": "reply",
                "reply": {
                    "id": "warning_no",
                    "title": translate_template(whatsapp_number, "No", supabase)  # CHANGED from gt_t_tt to translate_template
                }
            }
        ]
        
        content = {
            "interactive": {
                "type": "button",
                "body": {
                    "text": translate_template(whatsapp_number, "Continue with profile removal?", supabase)  # CHANGED from gt_tt to translate_template
                },
                "action": {
                    "buttons": buttons
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "INDIVIDUAL_REMOVE_WARNING"
        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in start_remove_profile for {whatsapp_number}: {e}")
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error loading profiles for removal. Please try again.", supabase)}}
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def handle_remove_warning(whatsapp_number, user_id, supabase, user_data, continue_removal):
    """Handle warning response for profile removal."""
    try:
        if not continue_removal:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Profile removal cancelled.", supabase)}}
            )
            return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
        
        # Get all patients for this user
        patients_response = supabase.table("patient_id").select(
            "id, patient_name"
        ).eq("wa_user_id", user_id).execute()
        
        patients = patients_response.data if patients_response.data else []
        
        if not patients:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "No profiles found to remove.", supabase)}}
            )
            return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
        
        # Prepare rows
        rows = []
        for patient in patients:
            patient_name = patient["patient_name"]  # Keep patient name in English
            
            title = f"{patient_name}"
            display_title = truncate_text(title, MAX_TITLE_LENGTH)  # Patient name not translated
            
            rows.append({
                "id": f"remove_patient_{patient['id']}",
                "title": display_title
            })
        
        # Add back button
        rows.append({
            "id": "back_to_edit",
            "title": translate_template(whatsapp_number, "🔙 Back to Edit Menu", supabase)  # Already using translate_template
        })
        
        # Send patient selection list
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text", 
                    "text": truncate_text(translate_template(whatsapp_number, "Remove Profile", supabase), MAX_HEADER_TEXT)
                },
                "body": {
                    "text": truncate_text(
                        translate_template(whatsapp_number, "Select a profile to remove:", supabase),
                        MAX_BODY_TEXT
                    )
                },
                "action": {
                    "button": truncate_text(
                        translate_template(whatsapp_number, "Select Profile", supabase),
                        MAX_BUTTON_TEXT
                    ),
                    "sections": [{
                        "title": truncate_text(
                            translate_template(whatsapp_number, "Your Profiles", supabase),
                            MAX_TITLE_LENGTH
                        ),
                        "rows": rows
                    }]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "INDIVIDUAL_REMOVE_SELECT"
        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in handle_remove_warning for {whatsapp_number}: {e}")
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error loading profiles for removal. Please try again.", supabase)}}
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def confirm_remove_profile(whatsapp_number, user_id, supabase, user_data, patient_id):
    """Confirm removal of a specific profile."""
    try:
        # Get patient details
        response = supabase.table("patient_id").select("patient_name").eq("id", patient_id).execute()
        
        if not response.data:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Patient not found.", supabase)}}
            )
            return start_remove_profile(whatsapp_number, user_id, supabase, user_data)
        
        patient_name = response.data[0]["patient_name"]  # Keep patient name in English
        
        # Store patient ID for confirmation
        user_data[whatsapp_number]["individual_data"]["pending_removal"] = patient_id
        
        # Send confirmation buttons
        buttons = [
            {
                "type": "reply",
                "reply": {
                    "id": "confirm_yes",
                    "title": translate_template(whatsapp_number, "Yes", supabase)  # CHANGED from gt_t_tt to translate_template
                }
            },
            {
                "type": "reply",
                "reply": {
                    "id": "confirm_no",
                    "title": translate_template(whatsapp_number, "No", supabase)  # CHANGED from gt_t_tt to translate_template
                }
            }
        ]
        
        content = {
            "interactive": {
                "type": "button",
                "body": {
                    "text": translate_template(whatsapp_number,  # CHANGED from gt_tt to translate_template
                        f"Do you want to remove the profile of {patient_name}?\n" +
                        "⚠️ This action cannot be undone.", supabase)
                },
                "action": {
                    "buttons": buttons
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "INDIVIDUAL_REMOVE_CONFIRM"
        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in confirm_remove_profile for {whatsapp_number}: {e}")
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error confirming removal. Please try again.", supabase)}}
        )
        return start_remove_profile(whatsapp_number, user_id, supabase, user_data)

def execute_remove_profile(whatsapp_number, user_id, supabase, user_data, confirm):
    """Execute profile removal based on confirmation."""
    try:
        if not confirm:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Profile removal cancelled.", supabase)}}
            )
            return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
        
        patient_id = user_data[whatsapp_number]["individual_data"].get("pending_removal")
        
        if not patient_id:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "No profile selected for removal.", supabase)}}
            )
            return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
        
        # Remove profile by setting wa_user_id to null and adding delete_reason
        response = supabase.table("patient_id").update({
            "wa_user_id": None,
            "delete_reason": "User removed profile via WhatsApp"
        }).eq("id", patient_id).execute()
        
        if response.data:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "✅ Profile removed successfully.", supabase)}}
            )
            
            # Clear pending removal
            user_data[whatsapp_number]["individual_data"].pop("pending_removal", None)
            
            # Refresh patient list - IMPORTANT: Set module back to individual
            from individual import handle_individual_start
            user_data[whatsapp_number]["module"] = "individual"  # Reset module to individual
            return handle_individual_start(whatsapp_number, user_id, supabase, user_data)
        else:
            raise Exception("Failed to remove profile")
        
    except Exception as e:
        logger.error(f"Error in execute_remove_profile for {whatsapp_number}: {e}")
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error removing profile. Please try again.", supabase)}}
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def start_reset_profiles(whatsapp_number, user_id, supabase, user_data):
    """Start changed numbers menu with clear explanations."""
    try:
        # First show main warning message
        warning_msg = translate_template(whatsapp_number, 
            "⚠️ *CHANGED NUMBERS*\n\n" +
            "You've changed your WhatsApp number.\n" +
            "Choose how to handle your existing profiles:", supabase)
        
        send_whatsapp_message(whatsapp_number, "text", {"text": {"body": warning_msg}})
        
        time.sleep(1)
        
        # Get number of profiles
        patients_response = supabase.table("patient_id").select("id").eq("wa_user_id", user_id).execute()
        num_profiles = len(patients_response.data) if patients_response.data else 0
        
        # Create interactive list with explanations in body
        rows = [
            {
                "id": "reset_remove_previous",
                "title": translate_template(whatsapp_number, "🔄 Reset account", supabase),  # CHANGED from gt_t_tt to translate_template
                "description": translate_template(whatsapp_number, "Start fresh with new account", supabase)  # CHANGED from gt_t_tt to translate_template
            },
            {
                "id": "reset_detach_profile", 
                "title": translate_template(whatsapp_number, "📱 Detach from old", supabase),  # CHANGED from gt_t_tt to translate_template
                "description": translate_template(whatsapp_number, "Move profile from old number", supabase)  # CHANGED from gt_t_tt to translate_template
            },
            {
                "id": "reset_cancel",
                "title": translate_template(whatsapp_number, "❌ Cancel", supabase)  # CHANGED from gt_t_tt to translate_template
            }
        ]
        
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text", 
                    "text": truncate_text(translate_template(whatsapp_number, "Changed Numbers", supabase), MAX_HEADER_TEXT)
                },
                "body": {
                    "text": truncate_text(
                        translate_template(whatsapp_number,  # CHANGED from gt_tt to translate_template
                            f"You have {num_profiles} profile(s) on this number.\n\n" +
                            "🔄 Reset account: Remove all profiles, start fresh\n" +
                            "📱 Detach from old: Move one profile from old number", supabase),
                        MAX_BODY_TEXT
                    )
                },
                "action": {
                    "button": truncate_text(
                        translate_template(whatsapp_number, "Select Option", supabase),
                        MAX_BUTTON_TEXT
                    ),
                    "sections": [{
                        "title": truncate_text(
                            translate_template(whatsapp_number, "Available Options", supabase),
                            MAX_TITLE_LENGTH
                        ),
                        "rows": rows
                    }]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "CHANGED_NUMBERS_MENU"
        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in start_reset_profiles for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, "Error starting process. Please try again.", supabase)}}  # Added translate_template
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def execute_reset_profiles(whatsapp_number, user_id, supabase, user_data, confirm):
    """Execute profile reset based on confirmation - SIMPLIFIED VERSION."""
    try:
        if not confirm:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Profile reset cancelled.", supabase)}}
            )
            from individual import show_profile_management_menu
            user_data[whatsapp_number]["module"] = "individual"  # Reset module to individual
            return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data)
        
        # FIRST: Ask for phone number verification
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "⚠️ For security, please retype your full phone number starting with 60... (e.g., 601223456789):", supabase)}}
        )
        
        # Store user_id for phone verification
        if "individual_data" not in user_data[whatsapp_number]:
            user_data[whatsapp_number]["individual_data"] = {}
        
        user_data[whatsapp_number]["individual_data"]["reset_verification"] = {
            "user_id": user_id,
            "attempts": 0,
            "max_attempts": 3
        }
        
        user_data[whatsapp_number]["state"] = "INDIVIDUAL_RESET_PHONE_VERIFY"
        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in execute_reset_profiles for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error in reset process. Please try again.", supabase)}}
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def verify_reset_phone_number(whatsapp_number, user_id, supabase, user_data, phone_input):
    """Verify phone number for reset and execute reset if valid."""
    try:
        reset_data = user_data[whatsapp_number]["individual_data"].get("reset_verification", {})
        current_user_id = reset_data.get("user_id")
        attempts = reset_data.get("attempts", 0)
        max_attempts = reset_data.get("max_attempts", 3)
        
        if attempts >= max_attempts:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Too many failed attempts. Reset process cancelled.", supabase)}}
            )
            # Clear reset data
            user_data[whatsapp_number]["individual_data"].pop("reset_verification", None)
            
            # IMPORTANT: Return to INDIVIDUAL module, not edit module
            user_data[whatsapp_number]["module"] = "individual"
            user_data[whatsapp_number]["state"] = "INDIVIDUAL_PROFILE_MANAGEMENT"
            from individual import show_profile_management_menu
            return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data)
        
        # Normalize phone input
        phone_clean = re.sub(r'[+\s\-]', '', phone_input)
        
        # Ensure it starts with 60 (Malaysian number)
        if not phone_clean.startswith('60'):
            phone_clean = '60' + phone_clean.lstrip('0')
        
        # Get current WhatsApp user's phone number
        user_response = supabase.table("whatsapp_users").select(
            "whatsapp_number, user_name"
        ).eq("id", current_user_id).execute()
        
        if not user_response.data:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "User not found.", supabase)}}
            )
            # Clear reset data
            user_data[whatsapp_number]["individual_data"].pop("reset_verification", None)
            
            # IMPORTANT: Return to INDIVIDUAL module, not edit module
            user_data[whatsapp_number]["module"] = "individual"
            user_data[whatsapp_number]["state"] = "INDIVIDUAL_PROFILE_MANAGEMENT"
            from individual import show_profile_management_menu
            return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data)
        
        current_user = user_response.data[0]
        current_whatsapp_number = re.sub(r'[+\s\-]', '', current_user["whatsapp_number"])
        
        # Normalize current number too
        if not current_whatsapp_number.startswith('60'):
            current_whatsapp_number = '60' + current_whatsapp_number.lstrip('0')
        
        # Debug log
        logger.info(f"Verifying phone: Input={phone_clean}, Current={current_whatsapp_number}")
        
        # Verify phone number
        if phone_clean == current_whatsapp_number:
            # Phone verified, proceed with reset
            return perform_actual_reset(whatsapp_number, current_user_id, supabase, user_data, current_user)
        else:
            # Increment attempts
            attempts += 1
            user_data[whatsapp_number]["individual_data"]["reset_verification"]["attempts"] = attempts
            
            attempts_left = max_attempts - attempts
            if attempts_left > 0:
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        f"Phone number does not match. {attempts_left} attempt(s) left.\n"
                        "Please retype your full phone number starting with 60...:", supabase)}}
                )
                return False
            else:
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        "Phone verification failed. Reset process cancelled.", supabase)}}
                )
                # Clear reset data
                user_data[whatsapp_number]["individual_data"].pop("reset_verification", None)
                
                # IMPORTANT: Return to INDIVIDUAL module, not edit module
                user_data[whatsapp_number]["module"] = "individual"
                user_data[whatsapp_number]["state"] = "INDIVIDUAL_PROFILE_MANAGEMENT"
                from individual import show_profile_management_menu
                return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data)
        
    except Exception as e:
        logger.error(f"Error in verify_reset_phone_number for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error verifying phone number. Please try again.", supabase)}}
        )
        # Clear reset data
        user_data[whatsapp_number]["individual_data"].pop("reset_verification", None)
        
        # IMPORTANT: Return to INDIVIDUAL module, not edit module
        user_data[whatsapp_number]["module"] = "individual"
        user_data[whatsapp_number]["state"] = "INDIVIDUAL_PROFILE_MANAGEMENT"
        from individual import show_profile_management_menu
        return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data)
    
def perform_actual_reset(whatsapp_number, user_id, supabase, user_data, current_user):
    """Perform the actual reset after phone verification."""
    try:
        current_whatsapp_number = current_user["whatsapp_number"]
        user_name = current_user["user_name"]
        
        # Step 1: Set wa_user_id to null and add delete_reason for all profiles of this user
        update_patients = supabase.table("patient_id").update({
            "wa_user_id": None,
            "delete_reason": "User initiated reset via WhatsApp"
        }).eq("wa_user_id", user_id).execute()
        
        logger.info(f"Reset: Updated {len(update_patients.data) if update_patients.data else 0} patients for user {user_id}")
        
        # Step 2: Instead of creating a new user, update the existing user
        # Reset the user's state and clear module/temp_data
        update_user = supabase.table("whatsapp_users").update({
            "state": "IDLE",
            "module": None,
            "temp_data": None,
            "delete_reason": "User initiated reset via WhatsApp - account refreshed"
        }).eq("id", user_id).execute()
        
        logger.info(f"Reset: Updated existing user {user_id}")
        
        # Clear ALL reset verification data
        if "individual_data" in user_data[whatsapp_number]:
            user_data[whatsapp_number]["individual_data"].pop("reset_verification", None)
        
        # IMPORTANT: Re-initialize the entire user_data for this number
        user_data[whatsapp_number] = {
            "state": "INDIVIDUAL_PROFILE_MANAGEMENT",
            "module": "individual",
            "user_id": user_id,  # Keep the same user_id since we're updating, not creating
            "individual_data": {
                "patients": [],
                "selected_patient_id": None,
                "selected_patient_name": None,
                "selected_vh_id": None,
                "selected_diagnosis_id": None,
                "profile_page": 0,
                "edit_mode": False
            }
        }
        
        # Send success message
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "✅ All profiles have been reset successfully!\n\n" +
                "Your WhatsApp account has been refreshed with no profiles.", supabase)}}
        )
        
        # Show profile menu (should be empty)
        time.sleep(1)
        
        # Return to main individual menu with fresh state
        from individual import handle_individual_start
        return handle_individual_start(whatsapp_number, user_id, supabase, user_data)
        
    except Exception as e:
        logger.error(f"Error in perform_actual_reset for {whatsapp_number}: {e}", exc_info=True)
        
        # IMPORTANT: Reset to INDIVIDUAL module state on failure
        user_data[whatsapp_number] = {
            "state": "INDIVIDUAL_PROFILE_MANAGEMENT",
            "module": "individual",
            "user_id": user_id  # Keep the original user_id
        }
        
        # Send error message
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error during reset process. Please try again.", supabase)}}
        )
        
        # Return to profile management menu
        from individual import show_profile_management_menu
        return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data)
def start_detach_verification(whatsapp_number, user_id, supabase, user_data):
    """Start detachment verification flow."""
    try:
        patient_data = user_data[whatsapp_number]["individual_data"]["detach_patient_data"]
        
        # Handle None value for change_acc_error
        change_acc_error = patient_data.get("change_acc_error")
        if change_acc_error is None:
            change_acc_error = 0
            
        # Store verification data
        user_data[whatsapp_number]["individual_data"]["detach_verification"] = {
            "patient_id": patient_data["id"],
            "patient_name": patient_data["patient_name"],
            "ic_passport": patient_data.get("ic_passport"),
            "race": patient_data.get("race"),
            "religion": patient_data.get("religion"),
            "blood_type": patient_data.get("blood_type"),
            "verified_fields": {},
            "current_step": "name",
            "change_acc_error": change_acc_error
        }
        
        # Start with name verification
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "To detach this profile, please verify the details.\n\n" +
                "Step 1/4: Enter the full name:", supabase)}}
        )
        
        user_data[whatsapp_number]["state"] = "DETACH_VERIFY_NAME"
        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in start_detach_verification for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error starting verification. Please try again.", supabase)}}
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def handle_detach_verify_name(whatsapp_number, user_id, supabase, user_data, name_input):
    """Verify name for detachment."""
    try:
        detach_data = user_data[whatsapp_number]["individual_data"]["detach_verification"]
        patient_id = detach_data["patient_id"]
        
        # Get current patient data
        response = supabase.table("patient_id").select("patient_name, race").eq("id", patient_id).execute()
        
        if not response.data:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Patient not found.", supabase)}}
            )
            return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
        
        current_data = response.data[0]
        current_name = current_data.get("patient_name", "").strip()
        name_input_clean = name_input.strip()
        
        logger.info(f"Current patient name: '{current_name}', Input: '{name_input_clean}'")
        
        # Check if name matches (case-insensitive, strip whitespace)
        if name_input_clean.lower() == current_name.lower():
            detach_data["verified_fields"]["name"] = True
            logger.info("Name verification: PASSED")
        else:
            detach_data["verified_fields"]["name"] = False
            logger.info(f"Name verification: FAILED. Expected: '{current_name}'")
        
        # Ask for race
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Step 2/4: Enter the race (e.g., Malay, Chinese, Indian, etc.):", supabase)}}
        )
        
        user_data[whatsapp_number]["state"] = "DETACH_VERIFY_RACE"
        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
        return False
            
    except Exception as e:
        logger.error(f"Error in handle_detach_verify_name for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error verifying name. Please try again.", supabase)}}
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def handle_detach_verify_race(whatsapp_number, user_id, supabase, user_data, race_input):
    """Verify race for detachment."""
    try:
        detach_data = user_data[whatsapp_number]["individual_data"]["detach_verification"]
        patient_id = detach_data["patient_id"]
        
        # Get current patient data
        response = supabase.table("patient_id").select("race, religion").eq("id", patient_id).execute()
        
        if not response.data:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Patient not found.", supabase)}}
            )
            return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
        
        current_data = response.data[0]
        current_race = current_data.get("race", "").strip()
        race_input_clean = race_input.strip()
        
        logger.info(f"Current patient race: '{current_race}', Input: '{race_input_clean}'")
        
        # Check if race matches
        if current_race and race_input_clean.lower() == current_race.lower():
            detach_data["verified_fields"]["race"] = True
            logger.info("Race verification: PASSED")
        else:
            detach_data["verified_fields"]["race"] = False
            logger.info(f"Race verification: FAILED. Expected: '{current_race}'")
        
        # Ask for religion
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Step 3/4: Enter the religion:", supabase)}}
        )
        
        user_data[whatsapp_number]["state"] = "DETACH_VERIFY_RELIGION"
        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
        return False
            
    except Exception as e:
        logger.error(f"Error in handle_detach_verify_race for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error verifying race. Please try again.", supabase)}}
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def handle_detach_verify_religion(whatsapp_number, user_id, supabase, user_data, religion_input):
    """Verify religion for detachment."""
    try:
        detach_data = user_data[whatsapp_number]["individual_data"]["detach_verification"]
        patient_id = detach_data["patient_id"]
        
        # Get current patient data
        response = supabase.table("patient_id").select("religion, blood_type").eq("id", patient_id).execute()
        
        if not response.data:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Patient not found.", supabase)}}
            )
            return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
        
        current_data = response.data[0]
        current_religion = current_data.get("religion", "").strip()
        religion_input_clean = religion_input.strip()
        
        logger.info(f"Current patient religion: '{current_religion}', Input: '{religion_input_clean}'")
        
        # Check if religion matches
        if current_religion and religion_input_clean.lower() == current_religion.lower():
            detach_data["verified_fields"]["religion"] = True
            logger.info("Religion verification: PASSED")
        else:
            detach_data["verified_fields"]["religion"] = False
            logger.info(f"Religion verification: FAILED. Expected: '{current_religion}'")
        
        # Ask for blood type
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Step 4/4: Enter the blood type (e.g., A+, B-, O+):", supabase)}}
        )
        
        user_data[whatsapp_number]["state"] = "DETACH_VERIFY_BLOOD_TYPE"
        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
        return False
            
    except Exception as e:
        logger.error(f"Error in handle_detach_verify_religion for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error verifying religion. Please try again.", supabase)}}
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def handle_detach_verify_blood_type(whatsapp_number, user_id, supabase, user_data, blood_type_input):
    """Verify blood type and complete detachment."""
    try:
        detach_data = user_data[whatsapp_number]["individual_data"]["detach_verification"]
        patient_id = detach_data["patient_id"]
        current_error_count = detach_data.get("change_acc_error", 0) or 0
        
        # Get current patient data
        response = supabase.table("patient_id").select("blood_type").eq("id", patient_id).execute()
        
        if not response.data:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Patient not found.", supabase)}}
            )
            return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
        
        current_data = response.data[0]
        current_blood_type = current_data.get("blood_type", "").strip().upper()
        blood_type_input_clean = blood_type_input.strip().upper()
        
        logger.info(f"Current patient blood type: '{current_blood_type}', Input: '{blood_type_input_clean}'")
        
        # Check if blood type matches
        if current_blood_type and blood_type_input_clean == current_blood_type:
            detach_data["verified_fields"]["blood_type"] = True
            logger.info("Blood type verification: PASSED")
        else:
            detach_data["verified_fields"]["blood_type"] = False
            logger.info(f"Blood type verification: FAILED. Expected: '{current_blood_type}'")
        
        # Check if all fields are correct
        all_correct = all(detach_data["verified_fields"].values())
        
        if all_correct:
            # All correct - detach profile
            update_response = supabase.table("patient_id").update({
                "wa_user_id": None,
                "delete_reason": "User detached via WhatsApp verification",
                "change_acc_error": 0  # Reset error count on success
            }).eq("id", patient_id).execute()
            
            if update_response.data:
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        "✅ Profile detached successfully!\n\n" +
                        "The profile is now available for reattachment.\n" +
                        "To add it to your account, please email contact@anyhealth.asia or visit partner clinics.", supabase)}}
                )
                
                # Clear detach data
                user_data[whatsapp_number]["individual_data"].pop("detach_patient_data", None)
                user_data[whatsapp_number]["individual_data"].pop("detach_verification", None)
                
                # Return to edit menu
                return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
            else:
                raise Exception("Failed to update patient")
        else:
            # Some fields incorrect - increment error count
            new_error_count = current_error_count + 1
            
            update_response = supabase.table("patient_id").update({
                "change_acc_error": new_error_count
            }).eq("id", patient_id).execute()
            
            if new_error_count >= 3:
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        "❌ Verification failed 3 times.\n" +
                        "Profile is now locked.\n" +
                        "Please email contact@anyhealth.asia or visit partner clinics.", supabase)}}
                )
            else:
                attempts_left = 3 - new_error_count
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        f"❌ Verification failed.\n" +
                        f"You have {attempts_left} attempt(s) left.\n" +
                        "Please try again or visit partner clinics.", supabase)}}
                )
            
            # Clear detach data
            user_data[whatsapp_number]["individual_data"].pop("detach_patient_data", None)
            user_data[whatsapp_number]["individual_data"].pop("detach_verification", None)
            
            return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
            
    except Exception as e:
        logger.error(f"Error in handle_detach_verify_blood_type for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error completing verification. Please try again.", supabase)}}
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def handle_detach_ic_input(whatsapp_number, user_id, supabase, user_data, ic_number):
    """Handle IC input for detach flow."""
    try:
        logger.info(f"Starting detach for IC: {ic_number}")
        
        # Validate IC number
        is_valid, result = validate_ic_number(ic_number)
        
        if not is_valid:
            # result contains the error message from validate_ic_number
            error_msg = result if isinstance(result, str) else "Invalid IC format"
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    f"Invalid IC: {error_msg}. Please enter a valid 12-digit Malaysian IC:", supabase)}}
            )
            return False
        
        # Clean the IC
        ic_clean = re.sub(r'[-\s]', '', result)
        logger.info(f"Looking for IC (cleaned): {ic_clean}")
        
        # Check if IC exists
        response = supabase.table("patient_id").select("id, wa_user_id, patient_name, change_acc_error, race, religion, blood_type").eq("ic_passport", ic_clean).execute()
        
        logger.info(f"Database response: {response.data}")
        
        if not response.data:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "❌ IC not found in our system.", supabase)}}
            )
            return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
        
        patient_data = response.data[0]
        logger.info(f"Found patient: {patient_data}")
        
        # Check if IC is attached to any account
        if not patient_data["wa_user_id"]:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "✅ This IC is not attached to any WhatsApp account.\n" +
                    "You can add it directly.", supabase)}}
            )
            return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
        
        # Check if attached to current user
        if patient_data["wa_user_id"] == user_id:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "✅ This IC is already attached to your current account.\n" +
                    "No need to detach.", supabase)}}
            )
            return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
        
        # Check error count - handle None value
        change_acc_error = patient_data.get("change_acc_error")
        if change_acc_error is None:
            change_acc_error = 0  # Default to 0 if null
            
        logger.info(f"Change acc error count: {change_acc_error}")
        
        if change_acc_error >= 3:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "❌ This IC has reached maximum detachment attempts (3).\n" +
                    "Please email contact@anyhealth.asia or visit partner clinics.", supabase)}}
            )
            return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
        
        # Store patient data for detachment
        user_data[whatsapp_number]["individual_data"]["detach_patient_data"] = patient_data
        
        # Start verification
        logger.info(f"Starting verification for patient: {patient_data['id']}")
        return start_detach_verification(whatsapp_number, user_id, supabase, user_data)
        
    except Exception as e:
        logger.error(f"Error in handle_detach_ic_input for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                f"Error: {str(e)[:50]}... Please try again.", supabase)}}
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)

def handle_edit_response(whatsapp_number, user_id, supabase, user_data, message):
    """Handle responses for edit module - NO PASSWORD CHECK."""
    try:
        state = user_data.get(whatsapp_number, {}).get("state")
        
        # Handle text messages
        if "text" in message:
            text_content = message["text"]["body"].strip()
            
            # Handle add profile - IC number
            if state == "INDIVIDUAL_ADD_IC":
                return handle_add_profile_ic(whatsapp_number, user_id, supabase, user_data, text_content)
            
            # Handle add profile - Name
            elif state == "INDIVIDUAL_ADD_NAME":
                return handle_add_profile_name(whatsapp_number, user_id, supabase, user_data, text_content)
            
            # Handle add profile - Race (Other)
            elif state == "INDIVIDUAL_ADD_RACE_OTHER":
                return handle_add_profile_race(whatsapp_number, user_id, supabase, user_data, text_content, is_other=True)
            
            # Handle add profile - Religion (Other)
            elif state == "INDIVIDUAL_ADD_RELIGION_OTHER":
                return handle_add_profile_religion(whatsapp_number, user_id, supabase, user_data, text_content, is_other=True)
            
            # Handle reset phone verification
            elif state == "INDIVIDUAL_RESET_PHONE_VERIFY":
                return verify_reset_phone_number(whatsapp_number, user_id, supabase, user_data, text_content)
            
            # Handle detach IC input
            elif state == "DETACH_IC_INPUT":
                return handle_detach_ic_input(whatsapp_number, user_id, supabase, user_data, text_content)
            
            # Add new detach verification handlers
            elif state == "DETACH_VERIFY_NAME":
                return handle_detach_verify_name(whatsapp_number, user_id, supabase, user_data, text_content)
            elif state == "DETACH_VERIFY_RACE":
                return handle_detach_verify_race(whatsapp_number, user_id, supabase, user_data, text_content)
            elif state == "DETACH_VERIFY_RELIGION":
                return handle_detach_verify_religion(whatsapp_number, user_id, supabase, user_data, text_content)
            elif state == "DETACH_VERIFY_BLOOD_TYPE":
                return handle_detach_verify_blood_type(whatsapp_number, user_id, supabase, user_data, text_content)
        
        # Handle interactive messages
        if "interactive" in message:
            interactive_type = message["interactive"]["type"]
            
            if interactive_type == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                # Edit menu
                if state == "INDIVIDUAL_EDIT_MENU":
                    if button_id == "add_profile":
                        return start_add_profile(whatsapp_number, user_id, supabase, user_data)
                    elif button_id == "remove_profile":
                        return start_remove_profile(whatsapp_number, user_id, supabase, user_data)
                    elif button_id == "back_to_profiles":
                        from individual import show_profile_management_menu
                        user_data[whatsapp_number]["module"] = "individual"  # Reset module to individual
                        return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data)
                
                # Reset confirmation
                elif state == "INDIVIDUAL_RESET_CONFIRM":
                    if button_id == "reset_confirm_yes":
                        return execute_reset_profiles(whatsapp_number, user_id, supabase, user_data, True)
                    elif button_id == "reset_confirm_no":
                        return execute_reset_profiles(whatsapp_number, user_id, supabase, user_data, False)
                
                # Remove warning
                elif state == "INDIVIDUAL_REMOVE_WARNING":
                    if button_id == "warning_yes":
                        return handle_remove_warning(whatsapp_number, user_id, supabase, user_data, True)
                    elif button_id == "warning_no":
                        return handle_remove_warning(whatsapp_number, user_id, supabase, user_data, False)
                
                # Remove confirmation
                elif state == "INDIVIDUAL_REMOVE_CONFIRM":
                    if button_id == "confirm_yes":
                        return execute_remove_profile(whatsapp_number, user_id, supabase, user_data, True)
                    elif button_id == "confirm_no":
                        return execute_remove_profile(whatsapp_number, user_id, supabase, user_data, False)
                
                # After reset setup
                elif state == "INDIVIDUAL_AFTER_RESET":
                    if button_id == "setup_profile_yes":
                        # Start add profile flow
                        return start_add_profile(whatsapp_number, user_id, supabase, user_data)
                    elif button_id == "setup_profile_no":
                        from utils import send_interactive_menu
                        user_data[whatsapp_number] = {"state": "IDLE", "module": None, "user_id": user_id}
                        send_interactive_menu(whatsapp_number, supabase)
                        return False
                
                # Detach confirmation from add profile flow
                elif state == "DETACH_CONFIRM":
                    if button_id == "detach_yes":
                        return start_detach_verification(whatsapp_number, user_id, supabase, user_data)
                    elif button_id == "detach_no":
                        send_whatsapp_message(
                            whatsapp_number, "text",
                            {"text": {"body": translate_template(whatsapp_number, 
                                "Detachment cancelled.", supabase)}}
                        )
                        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
            
            elif interactive_type == "list_reply":
                list_id = message["interactive"]["list_reply"]["id"]
                
                # Edit menu (shouldn't happen, but just in case)
                if state == "INDIVIDUAL_EDIT_MENU":
                    if list_id == "add_profile":
                        return start_add_profile(whatsapp_number, user_id, supabase, user_data)
                    elif list_id == "remove_profile":
                        return start_remove_profile(whatsapp_number, user_id, supabase, user_data)
                    elif list_id == "back_to_profiles":
                        from individual import show_profile_management_menu
                        user_data[whatsapp_number]["module"] = "individual"  # Reset module to individual
                        return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data)
                
                # Add profile - Race selection (LIST)
                elif state == "INDIVIDUAL_ADD_RACE":
                    return handle_add_profile_race(whatsapp_number, user_id, supabase, user_data, list_id, is_other=False)
                
                # Add profile - Religion selection (LIST)
                elif state == "INDIVIDUAL_ADD_RELIGION":
                    return handle_add_profile_religion(whatsapp_number, user_id, supabase, user_data, list_id, is_other=False)
                
                # Add profile - Blood type selection (LIST)
                elif state == "INDIVIDUAL_ADD_BLOOD_TYPE":
                    return handle_add_profile_blood_type(whatsapp_number, user_id, supabase, user_data, list_id)
                
                # Remove profile selection
                elif state == "INDIVIDUAL_REMOVE_SELECT":
                    if list_id.startswith("remove_patient_"):
                        patient_id = list_id.replace("remove_patient_", "")
                        return confirm_remove_profile(whatsapp_number, user_id, supabase, user_data, patient_id)
                    elif list_id == "back_to_edit":
                        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
                
                # Changed Numbers Menu
                elif state == "CHANGED_NUMBERS_MENU":
                    if list_id == "reset_remove_previous":
                        # Show warning for reset account
                        warning_msg = translate_template(whatsapp_number,
                            "⚠️ *RESET ACCOUNT WARNING*\n\n" +
                            "This will:\n" +
                            "1. Remove all profiles from this WhatsApp\n" +
                            "2. Create a fresh account for your number\n" +
                            "3. Previous profiles cannot be restored\n\n" +
                            "To undo, visit partner clinics.", supabase)
                        
                        send_whatsapp_message(whatsapp_number, "text", {"text": {"body": warning_msg}})
                        
                        time.sleep(1)
                        
                        # Get profile count again for confirmation
                        patients_response = supabase.table("patient_id").select("id").eq("wa_user_id", user_id).execute()
                        num_profiles = len(patients_response.data) if patients_response.data else 0
                        
                        buttons = [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "reset_confirm_yes",
                                    "title": translate_template(whatsapp_number, "Yes, reset", supabase)  # CHANGED from gt_t_tt to translate_template
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "reset_confirm_no",
                                    "title": translate_template(whatsapp_number, "No, cancel", supabase)  # CHANGED from gt_t_tt to translate_template
                                }
                            }
                        ]
                        
                        content = {
                            "interactive": {
                                "type": "button",
                                "body": {
                                    "text": translate_template(whatsapp_number,  # CHANGED from gt_tt to translate_template
                                        f"You have {num_profiles} profile(s).\n" +
                                        "Confirm account reset?", supabase)
                                },
                                "action": {
                                    "buttons": buttons
                                }
                            }
                        }
                        
                        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
                        user_data[whatsapp_number]["state"] = "INDIVIDUAL_RESET_CONFIRM"
                        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
                        return False
                        
                    elif list_id == "reset_detach_profile":
                        # Show warning for detach
                        warning_msg = translate_template(whatsapp_number,
                            "⚠️ *DETACH FROM OLD NUMBER*\n\n" +
                            "This will:\n" +
                            "1. Remove a profile from old WhatsApp\n" +
                            "2. Free it for attachment to new number\n" +
                            "3. Requires verification of profile details\n\n" +
                            "After detachment, contact clinic/email to attach to new number.", supabase)
                        
                        send_whatsapp_message(whatsapp_number, "text", {"text": {"body": warning_msg}})
                        
                        time.sleep(1)
                        
                        send_whatsapp_message(
                            whatsapp_number, "text",
                            {"text": {"body": translate_template(whatsapp_number, 
                                "Please enter the 12-digit IC of the profile to detach:", supabase)}}
                        )
                        user_data[whatsapp_number]["state"] = "DETACH_IC_INPUT"
                        user_data[whatsapp_number]["module"] = "individualedit"  # Ensure module is set
                        return False
                        
                    elif list_id == "reset_cancel":
                        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
        
        return False
        
    except Exception as e:
        logger.error(f"Error in handle_edit_response for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "An error occurred in edit module. Please try again.", supabase)}}
        )
        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)