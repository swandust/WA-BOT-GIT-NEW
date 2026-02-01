# individual.py (updated - fix reset_profiles state handling)
import logging
import re
import time
from datetime import datetime, timedelta
from utils import (
    send_whatsapp_message,
    translate_template,
    gt_t_tt,
    gt_tt,
    gt_dt_tt,
    send_document
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# WhatsApp character limits
MAX_TITLE_LENGTH = 24
MAX_BUTTON_TEXT = 20
MAX_HEADER_TEXT = 60
MAX_BODY_TEXT = 1024

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

def get_clinic_name(supabase, provider_cat, provider_id):
    """Get clinic name based on provider category and ID."""
    try:
        if provider_cat == "tcm":
            response = supabase.table("tcm_a_clinics").select("name").eq("id", provider_id).execute()
        elif provider_cat == "clinic":
            response = supabase.table("c_a_clinics").select("name").eq("id", provider_id).execute()
        else:
            return "Unknown Clinic"
        
        if response.data and len(response.data) > 0:
            return response.data[0]["name"]
        return "Unknown Clinic"
    except Exception as e:
        logger.error(f"Error getting clinic name: {e}")
        return "Unknown Clinic"

def format_visit_date(visit_datetime_str):
    """Format visit datetime to readable format."""
    try:
        if not visit_datetime_str:
            return "Date not set"
        
        dt = datetime.fromisoformat(visit_datetime_str.replace('Z', '+00:00'))
        return dt.strftime("%d/%m/%Y")
    except Exception as e:
        logger.error(f"Error formatting date: {e}")
        return visit_datetime_str[:10] if visit_datetime_str else "Invalid date"

def handle_individual_start(whatsapp_number, user_id, supabase, user_data):
    """Start the individual module - show profile management menu."""
    try:
        # Get all patients for this user
        patients_response = supabase.table("patient_id").select(
            "id, patient_name"
        ).eq("wa_user_id", user_id).execute()
        
        patients = patients_response.data if patients_response.data else []
        
        # Store patients data for pagination
        user_data[whatsapp_number]["individual_data"] = {
            "patients": patients,
            "selected_patient_id": None,
            "selected_patient_name": None,
            "selected_vh_id": None,
            "selected_diagnosis_id": None,
            "profile_page": 0,
            "edit_mode": False
        }
        
        # Show profile management menu
        return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data)
        
    except Exception as e:
        logger.error(f"Error in handle_individual_start for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error loading profiles. Please try again.", supabase)}}
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        return False

def show_profile_management_menu(whatsapp_number, user_id, supabase, user_data, page=0):
    """Show profile management menu with pagination - SHOW ONLY NAMES."""
    try:
        ind_data = user_data[whatsapp_number].get("individual_data", {})
        patients = ind_data.get("patients", [])
        
        # Calculate pagination
        items_per_page = 6
        start_idx = page * items_per_page
        end_idx = start_idx + items_per_page
        page_items = patients[start_idx:end_idx]
        total_pages = (len(patients) + items_per_page - 1) // items_per_page
        
        # Prepare rows
        rows = []
        
        # Add patient rows - ONLY SHOW NAME
        for idx, patient in enumerate(page_items, start=1):
            patient_name = patient["patient_name"]
            
            title = f"{idx}. {patient_name}"
            display_title = truncate_text(title, MAX_TITLE_LENGTH) 
            
            rows.append({
                "id": f"select_patient_{patient['id']}",
                "title": display_title
            })
        
        # Add management options
        rows.append({
            "id": "edit_profiles",
            "title": translate_template(whatsapp_number, "📝 Edit Profiles", supabase)
        })
        
        rows.append({
            "id": "reset_profiles",
            "title": translate_template(whatsapp_number, "🔄 Changed Numbers", supabase)  # Changed from Reset Profiles
        })
        
        # Add pagination if needed
        if total_pages > 1:
            if page < total_pages - 1:
                rows.append({
                    "id": "next_page",
                    "title": translate_template(whatsapp_number, "➡️ Next Page", supabase)
                })
            if page > 0:
                rows.append({
                    "id": "prev_page",
                    "title": translate_template(whatsapp_number, "⬅️ Previous Page", supabase)
                })
        
        # Add back button
        rows.append({
            "id": "back_to_menu",
            "title": translate_template(whatsapp_number, "🔙 Back to Menu", supabase)
        })
        
        # Page info
        page_info = f" (Page {page + 1}/{total_pages})" if total_pages > 1 else ""
        num_profiles = len(patients)
        
        # Build header text
        header_text = f"{num_profiles} {translate_template(whatsapp_number, 'Profiles', supabase)}"
        
        # Build body text
        body_text = translate_template(whatsapp_number, f"Select a profile to view or manage{page_info}:", supabase)
        
        # Send interactive list
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text", 
                    "text": truncate_text(header_text, MAX_HEADER_TEXT)
                },
                "body": {
                    "text": truncate_text(body_text, MAX_BODY_TEXT)
                },
                "action": {
                    "button": truncate_text(translate_template(whatsapp_number, "Manage Profiles", supabase), MAX_BUTTON_TEXT),
                    "sections": [{
                        "title": truncate_text(translate_template(whatsapp_number, "Your Profiles", supabase), MAX_TITLE_LENGTH),
                        "rows": rows
                    }]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "INDIVIDUAL_PROFILE_MANAGEMENT"
        user_data[whatsapp_number]["module"] = "individual"  # Ensure module is set
        user_data[whatsapp_number]["individual_data"]["profile_page"] = page
        return False
        
    except Exception as e:
        logger.error(f"Error in show_profile_management_menu for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error loading profile menu. Please try again.", supabase)}}
        )
        return False

def handle_profile_selection(whatsapp_number, user_id, supabase, user_data, patient_id):
    """Handle when user selects a profile - ask for password first."""
    try:
        # Get patient's IC/passport
        response = supabase.table("patient_id").select("ic_passport, error, patient_name").eq("id", patient_id).execute()
        if not response.data:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Patient not found.", supabase)}}
            )
            return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data)
        
        patient_data = response.data[0]
        ic_passport = patient_data.get("ic_passport", "")
        error_count = patient_data.get("error", 0) or 0
        patient_name = patient_data.get("patient_name", "Unknown")
        
        # Check if account is locked
        if error_count >= 5:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Account locked. Please contact contact@anyhealth.asia to unlock.", supabase)}}
            )
            return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data)
        
        # Ask for password (first 6 digits of IC)
        password_prompt = translate_template(whatsapp_number, 
            f"Please enter the first 6 digits of the IC number for {patient_name}:", supabase)
        
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": password_prompt}}
        )
        
        # Store patient ID for password verification
        user_data[whatsapp_number]["individual_data"]["password_check"] = {
            "patient_id": patient_id,
            "patient_name": patient_name,
            "ic_passport": ic_passport,
            "error_count": error_count,
            "max_attempts": 5,
            "action": "select_patient"
        }
        
        user_data[whatsapp_number]["state"] = "INDIVIDUAL_PASSWORD_CHECK"
        return False
        
    except Exception as e:
        logger.error(f"Error in handle_profile_selection for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error in verification. Please try again.", supabase)}}
        )
        return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data)

def verify_password_for_patient(whatsapp_number, user_id, supabase, user_data, password):
    """Verify password and handle error counting for patient selection."""
    try:
        ind_data = user_data[whatsapp_number].get("individual_data", {})
        password_check = ind_data.get("password_check", {})
        
        ic_passport = password_check.get("ic_passport", "")
        patient_id = password_check.get("patient_id")
        patient_name = password_check.get("patient_name", "Unknown")
        error_count = password_check.get("error_count", 0)
        max_attempts = password_check.get("max_attempts", 5)
        
        # Get first 6 digits of IC
        ic_clean = re.sub(r'[-\s]', '', ic_passport)
        expected_password = ic_clean[:6] if len(ic_clean) >= 6 else ""
        
        # Check password
        if password == expected_password:
            # Reset error count to 0
            supabase.table("patient_id").update({"error": 0}).eq("id", patient_id).execute()
            
            # Store selected patient
            user_data[whatsapp_number]["individual_data"]["selected_patient_id"] = patient_id
            user_data[whatsapp_number]["individual_data"]["selected_patient_name"] = patient_name
            
            # Show main options menu
            return show_patient_main_options(whatsapp_number, user_id, supabase, user_data)
        else:
            # Increment error count
            new_error_count = error_count + 1
            
            if new_error_count >= max_attempts:
                # Lock account
                supabase.table("patient_id").update({"error": new_error_count}).eq("id", patient_id).execute()
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, 
                        "Account locked after 5 failed attempts. Please contact contact@anyhealth.asia to unlock.", supabase)}}
                )
                return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data)
            else:
                # Update error count
                supabase.table("patient_id").update({"error": new_error_count}).eq("id", patient_id).execute()
                
                attempts_left = max_attempts - new_error_count
                attempts_msg = translate_template(whatsapp_number, 
                    f"Incorrect password. {attempts_left} attempt(s) left.", supabase)
                
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": attempts_msg}}
                )
                
                # Ask for password again
                password_prompt = translate_template(whatsapp_number, 
                    f"Please enter the first 6 digits of the IC number for {patient_name}:", supabase)
                
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": password_prompt}}
                )
                
                # Update error count in user data
                user_data[whatsapp_number]["individual_data"]["password_check"]["error_count"] = new_error_count
                return False
        
    except Exception as e:
        logger.error(f"Error in verify_password_for_patient for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Verification failed. Please try again.", supabase)}}
        )
        return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data)

def show_patient_main_options(whatsapp_number, user_id, supabase, user_data):
    """Show the main 3-option menu after selecting a patient."""
    try:
        ind_data = user_data[whatsapp_number].get("individual_data", {})
        patient_name = ind_data.get("selected_patient_name", "Patient")
        
        # Create the 3-option menu
        rows = [
            {
                "id": "option_enemy",
                "title": translate_template(whatsapp_number, "⚔️ Enemy (Disease)", supabase),
                "description": translate_template(whatsapp_number, "View diagnosed conditions", supabase)
            },
            {
                "id": "option_med_routine",
                "title": translate_template(whatsapp_number, "💊 Med & Routine", supabase),
                "description": translate_template(whatsapp_number, "View all medications and items", supabase)
            },
            {
                "id": "option_report",
                "title": translate_template(whatsapp_number, "📄 Report", supabase),
                "description": translate_template(whatsapp_number, "Select visit for MC, Invoice, etc.", supabase)
            },
            {
                "id": "back_to_profiles",
                "title": translate_template(whatsapp_number, "🔙 Back to Profiles", supabase)
            }
        ]
        
        # Build header text
        header_text = translate_template(whatsapp_number, "Options for {}", supabase).format(patient_name)
        
        # Send interactive list
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text", 
                    "text": truncate_text(header_text, MAX_HEADER_TEXT)
                },
                "body": {
                    "text": truncate_text(
                        translate_template(whatsapp_number, "What would you like to view?", supabase),
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
        user_data[whatsapp_number]["state"] = "INDIVIDUAL_MAIN_OPTIONS"
        user_data[whatsapp_number]["module"] = "individual"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in show_patient_main_options for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error loading options. Please try again.", supabase)}}
        )
        return handle_individual_start(whatsapp_number, user_id, supabase, user_data)

def handle_enemy_disease(whatsapp_number, user_id, supabase, user_data):
    """Handle Enemy (Disease) option - show all diagnoses for the patient."""
    try:
        ind_data = user_data[whatsapp_number].get("individual_data", {})
        patient_id = ind_data.get("selected_patient_id")
        
        if not patient_id:
            return handle_individual_start(whatsapp_number, user_id, supabase, user_data)
        
        # Get all visits for this patient with their diagnoses
        vh_response = supabase.table("actual_visiting_history").select(
            "id, visit_datetime, provider_cat, provider_id"
        ).eq("patient_id", patient_id).order("visit_datetime", desc=True).execute()
        
        if not vh_response.data:
            patient_name = ind_data.get("selected_patient_name", "the patient")
            no_visits_msg = translate_template(whatsapp_number, 
                f"No visits found for {patient_name}.", supabase)
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": no_visits_msg}}
            )
            return show_patient_main_options(whatsapp_number, user_id, supabase, user_data)
        
        # Get diagnoses for each visit
        all_diagnoses = []
        for vh in vh_response.data:
            diagnosis_response = supabase.table("actual_diagnosis").select(
                "diagnosis, suspected_disease, created_at"
            ).eq("vh_id", vh["id"]).execute()
            
            if diagnosis_response.data:
                for diag in diagnosis_response.data:
                    # Get clinic name
                    clinic_name = get_clinic_name(supabase, vh["provider_cat"], vh["provider_id"])
                    
                    # Format date
                    formatted_date = format_visit_date(vh["visit_datetime"])
                    
                    diagnosis_info = {
                        "date": formatted_date,
                        "clinic": clinic_name,
                        "diagnosis": diag.get("diagnosis", "No diagnosis recorded"),
                        "suspected_disease": diag.get("suspected_disease"),
                        "created_at": diag.get("created_at")
                    }
                    all_diagnoses.append(diagnosis_info)
        
        # Build message
        if not all_diagnoses:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "No disease diagnoses found for this patient.", supabase)}}
            )
            return show_patient_main_options(whatsapp_number, user_id, supabase, user_data)
        
        patient_name = ind_data.get("selected_patient_name", "Patient")
        message_parts = []
        
        # Header
        enemy_header = translate_template(whatsapp_number, f"⚔️ **ENEMY (DISEASE) for {patient_name}**", supabase)
        message_parts.append(enemy_header)
        message_parts.append("")
        
        for i, diag in enumerate(all_diagnoses, 1):
            # Translate the static parts of each diagnosis entry
            message_parts.append(f"{i}. **{diag['date']} - {diag['clinic']}**")
            
            diagnosis_label = translate_template(whatsapp_number, "Diagnosis:", supabase)
            message_parts.append(f"   {diagnosis_label} {diag['diagnosis']}")
            
            if diag.get("suspected_disease"):
                suspected_label = translate_template(whatsapp_number, "Suspected Disease:", supabase)
                message_parts.append(f"   {suspected_label} {diag['suspected_disease']}")
            message_parts.append("")
        
        contact_msg = translate_template(whatsapp_number, "📞 Contact your clinic for more information.", supabase)
        message_parts.append(contact_msg)
        
        # Send message
        full_message = "\n".join(message_parts)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": full_message}}
        )
        
        # Ask if user wants to go back
        time.sleep(1)
        return ask_back_to_options(whatsapp_number, user_id, supabase, user_data)
        
    except Exception as e:
        logger.error(f"Error in handle_enemy_disease for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error loading disease information. Please try again.", supabase)}}
        )
        return show_patient_main_options(whatsapp_number, user_id, supabase, user_data)

def handle_med_routine(whatsapp_number, user_id, supabase, user_data):
    """Handle Med & Routine option - call the individual_med_rout module."""
    try:
        # Import the med/routine module
        from individual_med_rout import handle_patient_all_medications
        
        # Store that we're switching to med/routine module
        user_data[whatsapp_number]["module"] = "individual_med_rout"
        
        # Start the med/routine module for ALL medications (patient-level)
        return handle_patient_all_medications(whatsapp_number, user_id, supabase, user_data)
        
    except ImportError as e:
        logger.error(f"Error importing individual_med_rout module: {e}")
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Medication & Routine module is currently unavailable. Please try again later.", supabase)}}
        )
        return show_patient_main_options(whatsapp_number, user_id, supabase, user_data)
        
    except Exception as e:
        logger.error(f"Error in handle_med_routine for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error loading medication details. Please try again.", supabase)}}
        )
        return show_patient_main_options(whatsapp_number, user_id, supabase, user_data)

def handle_report(whatsapp_number, user_id, supabase, user_data):
    """Handle Report option - select a visit first."""
    try:
        ind_data = user_data[whatsapp_number].get("individual_data", {})
        patient_id = ind_data.get("selected_patient_id")
        
        if not patient_id:
            return handle_individual_start(whatsapp_number, user_id, supabase, user_data)
        
        # Get visiting history for this patient
        vh_response = supabase.table("actual_visiting_history").select(
            "id, visit_datetime, provider_cat, provider_id"
        ).eq("patient_id", patient_id).order("visit_datetime", desc=True).execute()
        
        if not vh_response.data:
            patient_name = ind_data.get("selected_patient_name", "the patient")
            no_history_msg = translate_template(whatsapp_number, 
                f"No visiting history found for {patient_name}.", supabase)
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": no_history_msg}}
            )
            return show_patient_main_options(whatsapp_number, user_id, supabase, user_data)
        
        vh_list = vh_response.data
        
        # Store visiting history data for pagination
        user_data[whatsapp_number]["individual_data"]["vh_list"] = vh_list
        user_data[whatsapp_number]["individual_data"]["vh_page"] = 0
        
        # Show first page of visits
        return show_report_visits_page(whatsapp_number, user_id, supabase, user_data, page=0)
        
    except Exception as e:
        logger.error(f"Error in handle_report for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error loading visiting history. Please try again.", supabase)}}
        )
        return show_patient_main_options(whatsapp_number, user_id, supabase, user_data)

def show_report_visits_page(whatsapp_number, user_id, supabase, user_data, page=0):
    """Show a page of visits for report selection."""
    try:
        ind_data = user_data[whatsapp_number].get("individual_data", {})
        vh_list = ind_data.get("vh_list", [])
        
        if not vh_list:
            return handle_report(whatsapp_number, user_id, supabase, user_data)
        
        # Calculate pagination
        items_per_page = 8
        start_idx = page * items_per_page
        end_idx = start_idx + items_per_page
        page_items = vh_list[start_idx:end_idx]
        total_pages = (len(vh_list) + items_per_page - 1) // items_per_page
        
        # Prepare rows
        rows = []
        for vh in page_items:
            # Get clinic name
            clinic_name = get_clinic_name(supabase, vh["provider_cat"], vh["provider_id"])
            
            # Format date
            formatted_date = format_visit_date(vh["visit_datetime"])
            
            # Create title
            title = f"{formatted_date} - {clinic_name}"
            display_title = gt_t_tt(whatsapp_number, title, supabase)
            
            rows.append({
                "id": f"report_vh_{vh['id']}",
                "title": display_title
            })
        
        # Add navigation buttons if needed
        if total_pages > 1:
            if page < total_pages - 1:
                rows.append({
                    "id": "report_next_page",
                    "title": translate_template(whatsapp_number, "➡️ Next Page", supabase)
                })
            if page > 0:
                rows.append({
                    "id": "report_prev_page",
                    "title": translate_template(whatsapp_number, "⬅️ Previous Page", supabase)
                })
        
        # Add back button
        rows.append({
            "id": "back_to_options",
            "title": translate_template(whatsapp_number, "🔙 Back to Options", supabase)
        })
        
        # Page info
        page_info = f" (Page {page + 1}/{total_pages})" if total_pages > 1 else ""
        
        # Build body text
        select_visit_msg = translate_template(whatsapp_number, f"Select a visit to view documents{page_info}:", supabase)
        
        # Send interactive list
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text", 
                    "text": truncate_text(translate_template(whatsapp_number, "Select Visit for Report", supabase), MAX_HEADER_TEXT)
                },
                "body": {
                    "text": truncate_text(select_visit_msg, MAX_BODY_TEXT)
                },
                "footer": {
                    "text": truncate_text(
                        translate_template(whatsapp_number, "MC, Invoice, Referral letter, Report", supabase),
                        MAX_BODY_TEXT
                    )
                },
                "action": {
                    "button": truncate_text(
                        translate_template(whatsapp_number, "Select Visit", supabase),
                        MAX_BUTTON_TEXT
                    ),
                    "sections": [{
                        "title": truncate_text(
                            translate_template(whatsapp_number, "Visiting History", supabase),
                            MAX_TITLE_LENGTH
                        ),
                        "rows": rows
                    }]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "REPORT_SELECT_VISIT"
        user_data[whatsapp_number]["module"] = "individual"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in show_report_visits_page for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error displaying visits. Please try again.", supabase)}}
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        return False

def handle_report_document_selection(whatsapp_number, user_id, supabase, user_data, vh_id):
    """Show document selection for selected visit."""
    try:
        logger.info(f"=== Checking documents for vh_id: {vh_id} ===")
        
        # Get diagnosis ID for this vh_id
        diagnosis_response = supabase.table("actual_diagnosis").select("id").eq("vh_id", vh_id).execute()
        
        diagnosis_id = None
        if diagnosis_response.data:
            diagnosis_id = diagnosis_response.data[0]["id"]
            logger.info(f"Found diagnosis_id: {diagnosis_id}")
        else:
            logger.info("No diagnosis found for this visit")
        
        # Store vh_id and diagnosis_id
        user_data[whatsapp_number]["individual_data"]["selected_vh_id"] = vh_id
        user_data[whatsapp_number]["individual_data"]["selected_diagnosis_id"] = diagnosis_id
        
        # Check which documents are available
        documents_available = {
            "medical_certificate": False,
            "invoice": False,
            "referral_letter": False,
            "consultation_report": False
        }
        document_titles = {}
        
        # Check Medical Certificate
        mc_response = supabase.table("actual_mc").select("id, mcsign").eq("vh_id", vh_id).execute()
        if mc_response.data:
            if mc_response.data[0].get("mcsign"):
                documents_available["medical_certificate"] = True
                document_titles["medical_certificate"] = translate_template(whatsapp_number, "📄 Medical Certificate", supabase)
        
        # Check Invoice/Bill
        bill_response = supabase.table("actual_invoice").select("id, invoicesign").eq("vh_id", vh_id).execute()
        if bill_response.data:
            if bill_response.data[0].get("invoicesign"):
                documents_available["invoice"] = True
                document_titles["invoice"] = translate_template(whatsapp_number, "💰 Bill/Invoice", supabase)
        
        # Check Referral Letter
        referral_response = supabase.table("actual_referral").select("id, referralsign").eq("vh_id", vh_id).execute()
        if referral_response.data:
            if referral_response.data[0].get("referralsign"):
                documents_available["referral_letter"] = True
                document_titles["referral_letter"] = translate_template(whatsapp_number, "📋 Referral Letter", supabase)
        
        # Check Consultation Report
        if diagnosis_id:
            report_response = supabase.table("tcm_report_consult").select("id, pdf_url").eq("actual_diagnosis_id", diagnosis_id).execute()
            if report_response.data:
                if report_response.data[0].get("pdf_url"):
                    documents_available["consultation_report"] = True
                    document_titles["consultation_report"] = translate_template(whatsapp_number, "📊 Consultation Report", supabase)
        
        # Prepare rows for list
        rows = []
        
        # Add available documents
        if documents_available["medical_certificate"]:
            rows.append({
                "id": "doc_mc",
                "title": document_titles["medical_certificate"]
            })
        
        if documents_available["invoice"]:
            rows.append({
                "id": "doc_bill",
                "title": document_titles["invoice"]
            })
        
        if documents_available["referral_letter"]:
            rows.append({
                "id": "doc_referral",
                "title": document_titles["referral_letter"]
            })
        
        if documents_available["consultation_report"]:
            rows.append({
                "id": "doc_report",
                "title": document_titles["consultation_report"]
            })
        
        # Add back button
        rows.append({
            "id": "back_to_visits",
            "title": translate_template(whatsapp_number, "🔙 Back to Visits", supabase)
        })
        
        if len(rows) == 1:  # Only back button
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "No documents available for this visit.", supabase)}}
            )
            return show_report_visits_page(whatsapp_number, user_id, supabase, user_data, page=0)
        
        # Send document selection list
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text", 
                    "text": truncate_text(translate_template(whatsapp_number, "Select Document", supabase), MAX_HEADER_TEXT)
                },
                "body": {
                    "text": truncate_text(
                        translate_template(whatsapp_number, "Select a document to download:", supabase),
                        MAX_BODY_TEXT
                    )
                },
                "action": {
                    "button": truncate_text(
                        translate_template(whatsapp_number, "Select Document", supabase),
                        MAX_BUTTON_TEXT
                    ),
                    "sections": [{
                        "title": truncate_text(
                            translate_template(whatsapp_number, "Available Documents", supabase),
                            MAX_TITLE_LENGTH
                        ),
                        "rows": rows
                    }]
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "REPORT_SELECT_DOCUMENT"
        user_data[whatsapp_number]["module"] = "individual"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in handle_report_document_selection for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error loading documents. Please try again.", supabase)}}
        )
        return show_report_visits_page(whatsapp_number, user_id, supabase, user_data, page=0)

def send_report_document(whatsapp_number, user_id, supabase, user_data, doc_type):
    """Send the requested document."""
    try:
        ind_data = user_data[whatsapp_number].get("individual_data", {})
        vh_id = ind_data.get("selected_vh_id")
        diagnosis_id = ind_data.get("selected_diagnosis_id")
        
        if not vh_id:
            return handle_report(whatsapp_number, user_id, supabase, user_data)
        
        document_url = None
        document_name = ""
        
        if doc_type == "mc":
            mc_response = supabase.table("actual_mc").select("mcsign").eq("vh_id", vh_id).execute()
            if mc_response.data and mc_response.data[0].get("mcsign"):
                document_url = mc_response.data[0]["mcsign"]
                document_name = translate_template(whatsapp_number, "Medical Certificate", supabase)
        
        elif doc_type == "bill":
            bill_response = supabase.table("actual_invoice").select("invoicesign").eq("vh_id", vh_id).execute()
            if bill_response.data and bill_response.data[0].get("invoicesign"):
                document_url = bill_response.data[0]["invoicesign"]
                document_name = translate_template(whatsapp_number, "Invoice", supabase)
        
        elif doc_type == "referral":
            referral_response = supabase.table("actual_referral").select("referralsign").eq("vh_id", vh_id).execute()
            if referral_response.data and referral_response.data[0].get("referralsign"):
                document_url = referral_response.data[0]["referralsign"]
                document_name = translate_template(whatsapp_number, "Referral Letter", supabase)
        
        elif doc_type == "report":
            if diagnosis_id:
                report_response = supabase.table("tcm_report_consult").select("pdf_url").eq("actual_diagnosis_id", diagnosis_id).execute()
                if report_response.data and report_response.data[0].get("pdf_url"):
                    document_url = report_response.data[0]["pdf_url"]
                    document_name = translate_template(whatsapp_number, "Consultation Report", supabase)
        
        if document_url:
            # Send the document
            caption = translate_template(whatsapp_number, f"Your {document_name}", supabase)
            success = send_document(whatsapp_number, document_url, caption=caption, supabase=supabase)
            
            if success:
                time.sleep(2)
                return ask_report_next_action(whatsapp_number, user_id, supabase, user_data)
            else:
                failed_msg = translate_template(whatsapp_number, 
                    f"Failed to send {document_name}. Please try again.", supabase)
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": failed_msg}}
                )
                return handle_report_document_selection(whatsapp_number, user_id, supabase, user_data, vh_id)
        else:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Document not available. Please select another document.", supabase)}}
            )
            return handle_report_document_selection(whatsapp_number, user_id, supabase, user_data, vh_id)
        
    except Exception as e:
        logger.error(f"Error in send_report_document for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error sending document. Please try again.", supabase)}}
        )
        ind_data = user_data[whatsapp_number].get("individual_data", {})
        vh_id = ind_data.get("selected_vh_id")
        if vh_id:
            return handle_report_document_selection(whatsapp_number, user_id, supabase, user_data, vh_id)
        else:
            return show_patient_main_options(whatsapp_number, user_id, supabase, user_data)

def ask_report_next_action(whatsapp_number, user_id, supabase, user_data):
    """Ask user what to do next after sending a document."""
    try:
        buttons = [
            {
                "type": "reply",
                "reply": {
                    "id": "another_doc",
                    "title": translate_template(whatsapp_number, "📄 Another Document", supabase)
                }
            },
            {
                "type": "reply",
                "reply": {
                    "id": "back_to_options",
                    "title": translate_template(whatsapp_number, "🔙 Back to Options", supabase)
                }
            }
        ]
        
        content = {
            "interactive": {
                "type": "button",
                "body": {
                    "text": translate_template(whatsapp_number, "What would you like to do next?", supabase)
                },
                "action": {
                    "buttons": buttons
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "REPORT_NEXT_ACTION"
        user_data[whatsapp_number]["module"] = "individual"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in ask_report_next_action for {whatsapp_number}: {e}")
        ind_data = user_data[whatsapp_number].get("individual_data", {})
        vh_id = ind_data.get("selected_vh_id")
        if vh_id:
            return handle_report_document_selection(whatsapp_number, user_id, supabase, user_data, vh_id)
        else:
            return show_patient_main_options(whatsapp_number, user_id, supabase, user_data)

def ask_back_to_options(whatsapp_number, user_id, supabase, user_data):
    """Ask user if they want to go back to options."""
    try:
        buttons = [
            {
                "type": "reply",
                "reply": {
                    "id": "back_to_options",
                    "title": translate_template(whatsapp_number, "🔙 Back to Options", supabase)
                }
            }
        ]
        
        content = {
            "interactive": {
                "type": "button",
                "body": {
                    "text": translate_template(whatsapp_number, "What would you like to do next?", supabase)
                },
                "action": {
                    "buttons": buttons
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "BACK_TO_OPTIONS"
        user_data[whatsapp_number]["module"] = "individual"  # Ensure module is set
        return False
        
    except Exception as e:
        logger.error(f"Error in ask_back_to_options for {whatsapp_number}: {e}")
        return show_patient_main_options(whatsapp_number, user_id, supabase, user_data)

def handle_individual_response(whatsapp_number, user_id, supabase, user_data, message):
    """Handle responses in the individual module."""
    try:
        state = user_data.get(whatsapp_number, {}).get("state")
        module = user_data.get(whatsapp_number, {}).get("module")
        
        # If user is in med_rout module, handle with that module's handler
        if module == "individual_med_rout":
            try:
                from individual_med_rout import handle_med_rout_response
                return handle_med_rout_response(whatsapp_number, user_id, supabase, user_data, message)
            except ImportError:
                logger.error("individual_med_rout module not found")
                user_data[whatsapp_number]["module"] = "individual"
        
        # If user is in individualedit module, handle with that module's handler
        if module == "individualedit":
            try:
                from individualedit import handle_edit_response
                return handle_edit_response(whatsapp_number, user_id, supabase, user_data, message)
            except ImportError as e:
                logger.error(f"individualedit module not found: {e}")
                user_data[whatsapp_number]["module"] = "individual"
        
        # Handle text messages
        if "text" in message:
            text_content = message["text"]["body"].strip()
            
            # Handle password check for PATIENT SELECTION ONLY (not for edit)
            if state == "INDIVIDUAL_PASSWORD_CHECK":
                # Only verify password for patient selection, NOT for edit
                password_check = user_data[whatsapp_number]["individual_data"].get("password_check", {})
                action = password_check.get("action", "")
                
                if action == "select_patient":
                    return verify_password_for_patient(whatsapp_number, user_id, supabase, user_data, text_content)
                # No password check for edit profiles
            
            # Handle back/menu commands
            elif text_content.lower() in ["back", "menu", "main menu"]:
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                from utils import send_interactive_menu
                send_interactive_menu(whatsapp_number, supabase)
                return False
        
        # Handle interactive messages
        if "interactive" in message:
            interactive_type = message["interactive"]["type"]
            
            if interactive_type == "list_reply":
                list_id = message["interactive"]["list_reply"]["id"]
                
                # Profile management menu
                if state == "INDIVIDUAL_PROFILE_MANAGEMENT":
                    if list_id.startswith("select_patient_"):
                        patient_id = list_id.replace("select_patient_", "")
                        # Ask for password before showing main options (only for patient selection)
                        return handle_profile_selection(whatsapp_number, user_id, supabase, user_data, patient_id)
                    
                    elif list_id == "edit_profiles":
                        # Set module to individualedit for edit operations
                        user_data[whatsapp_number]["module"] = "individualedit"
                        user_data[whatsapp_number]["state"] = "INDIVIDUAL_EDIT_MENU"
                        
                        # NO PASSWORD REQUIRED - go directly to edit menu
                        from individualedit import show_edit_profiles_menu
                        return show_edit_profiles_menu(whatsapp_number, user_id, supabase, user_data)
                    
                    # individual.py - FIXED reset_profiles handler with proper state and module setting

                    elif list_id == "reset_profiles":
                        # Set module to individualedit for reset operations
                        user_data[whatsapp_number]["module"] = "individualedit"
                        user_data[whatsapp_number]["state"] = "INDIVIDUAL_EDIT_MENU"
                        
                        # Call the reset function directly
                        from individualedit import start_reset_profiles
                        return start_reset_profiles(whatsapp_number, user_id, supabase, user_data)
                    
                    elif list_id == "next_page":
                        current_page = user_data[whatsapp_number]["individual_data"].get("profile_page", 0)
                        return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data, current_page + 1)
                    
                    elif list_id == "prev_page":
                        current_page = user_data[whatsapp_number]["individual_data"].get("profile_page", 0)
                        return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data, max(0, current_page - 1))
                    
                    elif list_id == "back_to_menu":
                        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                        from utils import send_interactive_menu
                        send_interactive_menu(whatsapp_number, supabase)
                        return False
                
                # Main options menu
                elif state == "INDIVIDUAL_MAIN_OPTIONS":
                    if list_id == "option_enemy":
                        return handle_enemy_disease(whatsapp_number, user_id, supabase, user_data)
                    
                    elif list_id == "option_med_routine":
                        return handle_med_routine(whatsapp_number, user_id, supabase, user_data)
                    
                    elif list_id == "option_report":
                        return handle_report(whatsapp_number, user_id, supabase, user_data)
                    
                    elif list_id == "back_to_profiles":
                        return show_profile_management_menu(whatsapp_number, user_id, supabase, user_data)
                
                # Report visit selection
                elif state == "REPORT_SELECT_VISIT":
                    if list_id.startswith("report_vh_"):
                        vh_id = list_id.replace("report_vh_", "")
                        return handle_report_document_selection(whatsapp_number, user_id, supabase, user_data, vh_id)
                    
                    elif list_id == "report_next_page":
                        current_page = user_data[whatsapp_number]["individual_data"].get("vh_page", 0)
                        return show_report_visits_page(whatsapp_number, user_id, supabase, user_data, current_page + 1)
                    
                    elif list_id == "report_prev_page":
                        current_page = user_data[whatsapp_number]["individual_data"].get("vh_page", 0)
                        return show_report_visits_page(whatsapp_number, user_id, supabase, user_data, max(0, current_page - 1))
                    
                    elif list_id == "back_to_options":
                        return show_patient_main_options(whatsapp_number, user_id, supabase, user_data)
                
                # Report document selection
                elif state == "REPORT_SELECT_DOCUMENT":
                    if list_id == "doc_mc":
                        return send_report_document(whatsapp_number, user_id, supabase, user_data, "mc")
                    elif list_id == "doc_bill":
                        return send_report_document(whatsapp_number, user_id, supabase, user_data, "bill")
                    elif list_id == "doc_referral":
                        return send_report_document(whatsapp_number, user_id, supabase, user_data, "referral")
                    elif list_id == "doc_report":
                        return send_report_document(whatsapp_number, user_id, supabase, user_data, "report")
                    elif list_id == "back_to_visits":
                        return show_report_visits_page(whatsapp_number, user_id, supabase, user_data, page=0)
            
            elif interactive_type == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                # Check current state for button replies
                if state == "REPORT_NEXT_ACTION":
                    if button_id == "another_doc":
                        ind_data = user_data[whatsapp_number].get("individual_data", {})
                        vh_id = ind_data.get("selected_vh_id")
                        return handle_report_document_selection(whatsapp_number, user_id, supabase, user_data, vh_id)
                    elif button_id == "back_to_options":
                        return show_patient_main_options(whatsapp_number, user_id, supabase, user_data)
                
                elif state == "BACK_TO_OPTIONS":
                    if button_id == "back_to_options":
                        return show_patient_main_options(whatsapp_number, user_id, supabase, user_data)
        
        return False
        
    except Exception as e:
        # Add your exception handling here
        logger.error(f"Error in handle_individual_response: {str(e)}", exc_info=True)
        return False