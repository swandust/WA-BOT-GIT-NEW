# menu.py - UPDATED WITH NEW MAIN MENU STRUCTURE
import logging
import time
from utils import (
    send_whatsapp_message,
    gt_tt,
    gt_t_tt,
    gt_dt_tt,
    send_interactive_menu,
    translate_template,
    send_image_message,
    get_notification_badge,
    send_non_emergency_menu_updated
)
from report_symptoms import handle_symptoms
from checkup_booking import handle_checkup
from vaccination_booking import handle_vaccination
from view_booking import (
    handle_view_upcoming_booking,
    handle_view_booking
)
from reschedule_booking import handle_reschedule
from post_report import handle_verification_response, handle_request_report
from ReportBooking import handle_report_booking
from concierge import send_concierge_prompt
from clinicfd import handle_clinic_enquiries, handle_clinic_enquiries_response
from healthsp import handle_healthsp
from afterservice import handle_symptom_tracker_selection, handle_symptom_tracker_response
from calendar_utils import handle_time_input, handle_time_confirmation, handle_retry_time_or_help, handle_future_date_input  
from checkup_booking import handle_checkup


# ===== AMBULANCE MODULE IMPORTS =====
from ambulance_booking import handle_booking_response, handle_booking_start
from ambulance_homehome import handle_homehome_response, handle_homehome_start

# ===== ADD DISCHARGE AND HOSP-HOSP MODULE IMPORTS =====
from ambulance_discharge import handle_discharge_response, handle_discharge_start
from ambulance_hosphosp import handle_hosphosp_response, handle_hosphosp_start

# ===== ADD TCM SERVICE IMPORT =====
from tcm_service import handle_tcm_service

# ===== ADD INDIVIDUAL MODULE IMPORT =====
from individual import handle_individual_response, handle_individual_start

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# WhatsApp character limits
MAX_TITLE_LENGTH = 24      # For row titles (21 + "...")
MAX_DESC_LENGTH = 72       # For row descriptions (69 + "...")
MAX_SECTION_TITLE = 24     # For section titles
MAX_BUTTON_TEXT = 20       # For button text
MAX_HEADER_TEXT = 60       # For header text
MAX_BODY_TEXT = 1024       # For body text

# UPDATED MAIN MENU OPTION IDs
MAIN_MENU_IDS = [
    "notification", "profile", "service_booking", "upcoming_booking", 
    "help", "languages"
]

# Special quick-booking options
BOOKING_OPTIONS = {
    'chk_d932225e-b543-41e4-90df-9609e7701184': {
        'service': 'Checkup (Report Review)',
        'doctor_id': '1c9ae4fe-0213-4e9f-97f0-875e065d4159',
        'clinic_id': '76d39438-a2c4-4e79-83e8-000000000000'
    }
}

def truncate_text(text, max_length, add_ellipsis=True):
    """Truncate text to max_length, adding ellipsis if needed."""
    if not text:
        return ""
    
    if len(text) > max_length:
        if add_ellipsis:
            # Reserve 3 characters for "..."
            return text[:max_length-3] + "..."
        else:
            return text[:max_length]
    return text

def get_clinic_services(supabase, clinic_id: str, category: str):
    """Get available services for a specific clinic and category."""
    try:
        response = supabase.table("c_a_clinic_service").select(
            "id, service_name, description, duration_minutes, brochure_image_url, doctor_id"
        ).eq("clinic_id", clinic_id).eq("category", category).eq("is_active", True).execute()
        
        logger.info(f"Found {len(response.data)} services for clinic {clinic_id}, category {category}")
        return response.data
    except Exception as e:
        logger.error(f"Error fetching clinic services: {e}", exc_info=True)
        return []

def send_services_menu(whatsapp_number: str, supabase, clinic_id: str, category: str, next_action: str):
    """Send services menu for the selected clinic and category with proper truncation."""
    try:
        # Get services for the selected clinic and category
        services = get_clinic_services(supabase, clinic_id, category)
        
        if not services:
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number, 
                    f"No {category} services available for this clinic. Please select another clinic or contact support.", 
                    supabase
                )}}
            )
            # Return to clinic selection
            send_clinic_selection_menu(whatsapp_number, supabase)
            return False
        
        # Prepare service rows with proper truncation using gt_t_tt for titles and gt_dt_tt for descriptions
        rows = []
        for service in services[:8]:  # WhatsApp allows max 8 rows
            service_name = service["service_name"]
            description = service.get("description", "") or ""
            
            # Use gt_t_tt for service name (title) - 24 character limit
            display_name = gt_t_tt(whatsapp_number, service_name, supabase)
            
            # Use gt_dt_tt for description - 72 character limit
            display_description = gt_dt_tt(whatsapp_number, description, supabase) if description else ""
            
            rows.append({
                "id": f"service_{service['id']}",
                "title": display_name,
                "description": display_description
            })
        
        # Add back button using translate_template
        rows.append({
            "id": "back_button",
            "title": translate_template(whatsapp_number, "🔙 Back to Booking", supabase)
        })
        
        # Store services data in user_data for later use
        try:
            user_db_data = supabase.table("whatsapp_users").select("temp_data").eq(
                "whatsapp_number", whatsapp_number.lstrip("+")
            ).limit(1).execute()
            
            if user_db_data.data and user_db_data.data[0]:
                temp_data = user_db_data.data[0].get("temp_data", {})
                if temp_data is None:
                    temp_data = {}
                temp_data["services"] = services
                temp_data["clinic_id"] = clinic_id
                temp_data["category"] = category
                temp_data["next_action"] = next_action
                
                supabase.table("whatsapp_users").update({
                    "temp_data": temp_data
                }).eq("whatsapp_number", whatsapp_number.lstrip("+")).execute()
            else:
                # If no temp_data exists, create it
                temp_data = {
                    "services": services,
                    "clinic_id": clinic_id,
                    "category": category,
                    "next_action": next_action
                }
                
                supabase.table("whatsapp_users").update({
                    "temp_data": temp_data
                }).eq("whatsapp_number", whatsapp_number.lstrip("+")).execute()
                
        except Exception as e:
            logger.error(f"Error storing temp_data for {whatsapp_number}: {e}")
            # Continue with the flow even if storing fails
        
        # Section title mapping with proper truncation using translate_template
        section_title_map = {
            "General GP visit": "GP Visit Services",
            "Checkup & Test": "Checkup Services",
            "Vaccination": "Vaccination Services",
            "Health Screening Plan": "Health Screening"
        }
        
        section_title = section_title_map.get(category, category)
        # Use translate_template for section title
        section_title = translate_template(whatsapp_number, section_title, supabase)
        
        # Prepare the message body using gt_tt
        body_text = gt_tt(whatsapp_number, f"Please select a {category} service:", supabase)
        body_text = truncate_text(body_text, MAX_BODY_TEXT, add_ellipsis=False)
        
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text", 
                    "text": truncate_text(translate_template(whatsapp_number, "AnyHealth Bot", supabase), MAX_HEADER_TEXT)
                },
                "body": {"text": body_text},
                "footer": {
                    "text": truncate_text(
                        translate_template(whatsapp_number, "Choose a service to proceed", supabase), 
                        MAX_BODY_TEXT
                    )
                },
                "action": {
                    "button": truncate_text(
                        translate_template(whatsapp_number, "Select Service", supabase), 
                        MAX_BUTTON_TEXT
                    ),
                    "sections": [{
                        "title": section_title,
                        "rows": rows
                    }]
                }
            }
        }
        
        return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        
    except Exception as e:
        logger.error(f"Error sending services menu to {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Unable to load services. Please try again.", supabase)}}
        )
        return False

def send_clinic_selection_menu(whatsapp_number: str, supabase, next_action=None) -> bool:
    """Send clinic selection menu to user with proper truncation."""
    try:
        # Fetch available clinics
        clinics = supabase.table("c_a_clinics").select("id, name").execute()
        
        if not clinics.data:
            # If no clinics found, use default and proceed directly
            logger.warning(f"No clinics found for {whatsapp_number}, using default")
            default_clinic_id = "76d39438-a2c4-4e79-83e8-000000000000"
            
            # Store clinic ID in temp_data
            try:
                user_db_data = supabase.table("whatsapp_users").select("temp_data").eq(
                    "whatsapp_number", whatsapp_number.lstrip("+")
                ).limit(1).execute()
                
                if user_db_data.data and user_db_data.data[0]:
                    temp_data = user_db_data.data[0].get("temp_data", {})
                    if temp_data is None:
                        temp_data = {}
                    temp_data["clinic_id"] = default_clinic_id
                    if next_action:
                        temp_data["next_action"] = next_action
                    
                    supabase.table("whatsapp_users").update({
                        "temp_data": temp_data
                    }).eq("whatsapp_number", whatsapp_number.lstrip("+")).execute()
                else:
                    # Create new temp_data
                    temp_data = {
                        "clinic_id": default_clinic_id
                    }
                    if next_action:
                        temp_data["next_action"] = next_action
                    
                    supabase.table("whatsapp_users").update({
                        "temp_data": temp_data
                    }).eq("whatsapp_number", whatsapp_number.lstrip("+")).execute()
                    
            except Exception as e:
                logger.error(f"Error storing default clinic: {e}")
            
            if next_action:
                # Directly proceed to services menu with default clinic
                category_map = {
                    "checkup_booking": "Checkup & Test",
                    "vaccination_booking": "Vaccination",
                    "health_screening": "Health Screening Plan",
                    "symptoms_checker": "General GP visit"
                }
                category = category_map.get(next_action, "Checkup & Test")
                return send_services_menu(whatsapp_number, supabase, default_clinic_id, category, next_action)
            else:
                send_booking_submenu(whatsapp_number, supabase)
                return True
            
        # Prepare clinic rows with proper truncation using gt_t_tt for titles
        rows = []
        for clinic in clinics.data[:8]:  # WhatsApp allows max 8 rows
            clinic_name = clinic["name"]
            display_name = gt_t_tt(whatsapp_number, clinic_name, supabase)
            rows.append({
                "id": f"clinic_{clinic['id']}",
                "title": display_name
            })
        
        # Add back button using translate_template
        rows.append({
            "id": "back_button",
            "title": translate_template(whatsapp_number, "🔙 Back to Main", supabase)
        })
        
        # Store next_action in temp_data
        if next_action:
            try:
                user_db_data = supabase.table("whatsapp_users").select("temp_data").eq(
                    "whatsapp_number", whatsapp_number.lstrip("+")
                ).limit(1).execute()
                
                if user_db_data.data and user_db_data.data[0]:
                    temp_data = user_db_data.data[0].get("temp_data", {})
                    if temp_data is None:
                        temp_data = {}
                    temp_data["next_action"] = next_action
                    
                    supabase.table("whatsapp_users").update({
                        "temp_data": temp_data
                    }).eq("whatsapp_number", whatsapp_number.lstrip("+")).execute()
                else:
                    # Create new temp_data
                    temp_data = {"next_action": next_action}
                    supabase.table("whatsapp_users").update({
                        "temp_data": temp_data
                    }).eq("whatsapp_number", whatsapp_number.lstrip("+")).execute()
                    
            except Exception as e:
                logger.error(f"Error storing next_action: {e}")
        
        # Prepare section title using translate_template
        section_title = translate_template(whatsapp_number, "Available Clinics", supabase)
        
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text", 
                    "text": truncate_text(translate_template(whatsapp_number, "AnyHealth Bot", supabase), MAX_HEADER_TEXT)
                },
                "body": {
                    "text": truncate_text(
                        translate_template(whatsapp_number, "Please select a clinic:", supabase),
                        MAX_BODY_TEXT
                    )
                },
                "footer": {
                    "text": truncate_text(
                        translate_template(whatsapp_number, "Choose a clinic to proceed", supabase),
                        MAX_BODY_TEXT
                    )
                },
                "action": {
                    "button": truncate_text(
                        translate_template(whatsapp_number, "Select Clinic", supabase),
                        MAX_BUTTON_TEXT
                    ),
                    "sections": [{
                        "title": section_title,
                        "rows": rows
                    }]
                }
            }
        }
        
        return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        
    except Exception as e:
        logger.error(f"Error sending clinic selection menu to {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Unable to load clinics. Please try again.", supabase)}}
        )
        return False

# ===== NEW FUNCTION: send_service_booking_menu =====
def send_service_booking_menu(whatsapp_number: str, supabase) -> bool:
    """Send the service booking menu with clinics, TCM, and ambulance services."""
    try:
        rows = [
            {
                "id": "service_clinic",
                "title": translate_template(whatsapp_number, "🏥 Clinic Services", supabase),
                "description": translate_template(whatsapp_number, "GP, Checkup, Vaccination, Health Screening", supabase)
            },
            {
                "id": "service_tcm",
                "title": translate_template(whatsapp_number, "🌿 TCM Services", supabase),
                "description": translate_template(whatsapp_number, "Chiro, Physio, Rehab, Traditional Medicine", supabase)
            },
            {
                "id": "service_ambulance",
                "title": translate_template(whatsapp_number, "🚑 Ambulance Service", supabase),
                "description": translate_template(whatsapp_number, "Non-emergency medical transport", supabase)
            },
            {
                "id": "service_aesthetic",
                "title": translate_template(whatsapp_number, "💅 Aesthetic", supabase),
                "description": translate_template(whatsapp_number, "Coming soon", supabase)
            },
            {
                "id": "service_hospital",
                "title": translate_template(whatsapp_number, "🏨 Hospital", supabase),
                "description": translate_template(whatsapp_number, "Coming soon", supabase)
            },
            {
                "id": "service_dialysis",
                "title": translate_template(whatsapp_number, "💉 Dialysis", supabase),
                "description": translate_template(whatsapp_number, "Coming soon", supabase)
            },
            {
                "id": "service_elderly",
                "title": translate_template(whatsapp_number, "👴 Elderly Care", supabase),
                "description": translate_template(whatsapp_number, "Coming soon", supabase)
            },
            {
                "id": "back_button",
                "title": translate_template(whatsapp_number, "🔙 Back to Main Menu", supabase)
            }
        ]
        
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text", 
                    "text": truncate_text(translate_template(whatsapp_number, "AnyHealth Bot", supabase), MAX_HEADER_TEXT)
                },
                "body": {
                    "text": truncate_text(
                        translate_template(whatsapp_number, "Select a service type:", supabase),
                        MAX_BODY_TEXT
                    )
                },
                "footer": {
                    "text": truncate_text(
                        translate_template(whatsapp_number, "Choose a service to proceed", supabase),
                        MAX_BODY_TEXT
                    )
                },
                "action": {
                    "button": truncate_text(
                        translate_template(whatsapp_number, "Select Service", supabase),
                        MAX_BUTTON_TEXT
                    ),
                    "sections": [{
                        "title": translate_template(whatsapp_number, "Service Booking", supabase),
                        "rows": rows
                    }]
                }
            }
        }
        
        return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        
    except Exception as e:
        logger.error(f"Error sending service booking menu to {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Unable to load services. Please try again.", supabase)}}
        )
        return False

def handle_menu_selection(whatsapp_number, user_id, supabase, user_data, message):
    """Handle interactive menu selections and text messages."""
    try:
        module = user_data[whatsapp_number].get("module")
        state = user_data[whatsapp_number].get("state")
        
        # ===== HANDLE MAIN MENU CONFIRMATION BUTTONS =====
        # Check if this is a main menu confirmation button
        if message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
            button_id = message["interactive"]["button_reply"]["id"]
            
            # Handle main menu confirmation buttons
            if button_id in ["confirm_main_menu", "cancel_main_menu"]:
                # These are handled in main.py, not here
                # Just acknowledge and return
                logger.info(f"Main menu confirmation button {button_id} handled in main.py")
                return False
        
        # Now process the message based on its type
        if "interactive" in message:
            interactive_type = message["interactive"]["type"]
            return _handle_interactive_message(whatsapp_number, user_id, supabase, user_data, message, interactive_type)
        elif "text" in message:
            return _handle_text_message(whatsapp_number, user_id, supabase, user_data, message)
        elif message.get("type") == "location":
            # Handle location messages - route to the appropriate module
            return _handle_location_message(whatsapp_number, user_id, supabase, user_data, message)
        elif message.get("type") in ["image", "video", "document", "audio"]:
            # Handle media messages - route to the appropriate module
            return _handle_media_message(whatsapp_number, user_id, supabase, user_data, message)
        else:
            logger.warning(f"Unknown message type from {whatsapp_number}: {message.get('type')}")
            return False
    except Exception as e:
        logger.error(f"Error in menu selection for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, "An error occurred. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def _handle_location_message(whatsapp_number, user_id, supabase, user_data, message):
    """Handle location messages and route to appropriate module."""
    try:
        module = user_data[whatsapp_number].get("module")
        state = user_data[whatsapp_number].get("state")
        
        logger.info(f"Location message received for {whatsapp_number}, module: {module}, state: {state}")
        
        # Route to appropriate module based on current state
        if module == "ambulance_booking":
            return handle_booking_response(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "ambulance_homehome":
            return handle_homehome_response(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "ambulance_discharge":
            return handle_discharge_response(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "ambulance_hosphosp":
            return handle_hosphosp_response(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "emergency":
            # Handle emergency location if needed
            from ambulance_emergency import handle_emergency_response
            return handle_emergency_response(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "tcm_service":
            # Route location messages to TCM service module
            return handle_tcm_service(whatsapp_number, user_id, supabase, user_data, message)
        else:
            # If location is not expected in this context, send a message
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Location received. However, location sharing is not expected in this context. "
                    "Please use the menu buttons provided for selection.", supabase)}},
                supabase
            )
            return False
            
    except Exception as e:
        logger.error(f"Error handling location message for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing location. Please try again.", supabase)}},
            supabase
        )
        return False

def _handle_media_message(whatsapp_number, user_id, supabase, user_data, message):
    """Handle media messages (images, documents, etc.) and route to appropriate module."""
    try:
        module = user_data[whatsapp_number].get("module")
        state = user_data[whatsapp_number].get("state")
        
        logger.info(f"Media message received for {whatsapp_number}, module: {module}, state: {state}")
        
        # Route to appropriate module based on current state
        if module == "ambulance_booking":
            return handle_booking_response(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "ambulance_homehome":
            return handle_homehome_response(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "ambulance_discharge":
            return handle_discharge_response(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "ambulance_hosphosp":
            return handle_hosphosp_response(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "emergency":
            # Handle emergency media if needed
            from ambulance_emergency import handle_emergency_response
            return handle_emergency_response(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "tcm_service":
            # Route media messages to TCM service module
            return handle_tcm_service(whatsapp_number, user_id, supabase, user_data, message)
        else:
            # If media is not expected in this context, send a message
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "File received. However, file upload is not expected in this context. "
                    "Please use the menu buttons provided for selection.", supabase)}},
                supabase
            )
            return False
            
    except Exception as e:
        logger.error(f"Error handling media message for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing file. Please try again.", supabase)}},
            supabase
        )
        return False

def handle_view_booking_submenu(whatsapp_number, user_data, supabase):
    """Send a submenu for View Booking options (Upcoming Bookings only)."""
    try:
        payload = {
            "messaging_product": "whatsapp",
            "to": whatsapp_number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": translate_template(whatsapp_number, "View Booking Options", supabase)},
                "body": {"text": translate_template(whatsapp_number, "Please select an option:", supabase)},
                "action": {
                    "button": translate_template(whatsapp_number, "Select Option", supabase),
                    "sections": [
                        {
                            "title": translate_template(whatsapp_number, "Booking Options", supabase),
                            "rows": [
                                {"id": "view_upcoming_bookings", "title": translate_template(whatsapp_number, "View Upcoming Bookings", supabase)}
                            ]
                        }
                    ]
                }
            }
        }
        send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
        user_data[whatsapp_number] = {"state": "VIEW_BOOKING_SUBMENU", "module": "view_booking"}
        return False

    except Exception as e:
        logger.error(f"Error in handle_view_booking_submenu for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error displaying the booking menu. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False


def _handle_interactive_message(whatsapp_number, user_id, supabase, user_data, message, interactive_type):
    """Handle interactive menu selections."""
    module = user_data[whatsapp_number].get("module")
    state = user_data[whatsapp_number].get("state")

    if interactive_type == "list_reply":
        list_id = message["interactive"]["list_reply"]["id"]
        logger.info(f"Received list reply: {list_id} from {whatsapp_number}")

        # ===== SERVICE BOOKING MENU HANDLING =====
        if list_id == "service_booking":
            logger.info(f"User {whatsapp_number} selected service booking")
            
            # Send service booking menu
            user_data[whatsapp_number]["state"] = "SERVICE_BOOKING_MENU"
            user_data[whatsapp_number]["module"] = "service_booking_menu"
            return send_service_booking_menu(whatsapp_number, supabase)

        # ===== SERVICE BOOKING SUBMENU HANDLING =====
        elif state == "SERVICE_BOOKING_MENU":
            if list_id == "back_button":
                return _handle_back_button(whatsapp_number, user_id, supabase, user_data)
            
            if list_id == "service_clinic":
                user_data[whatsapp_number]["state"] = "CLINIC_SELECTION"
                user_data[whatsapp_number]["module"] = "clinic_selection"
                send_clinic_selection_menu(whatsapp_number, supabase)
                return False
                
            elif list_id == "service_tcm":
                # Start TCM service flow
                user_data[whatsapp_number]["module"] = "tcm_service"
                user_data[whatsapp_number]["state"] = "IDLE"
                # Start TCM service flow
                dummy_message = {"type": "text", "text": {"body": "start"}}
                return handle_tcm_service(whatsapp_number, user_id, supabase, user_data, dummy_message)
                
            elif list_id == "service_ambulance":
                logger.info(f"User {whatsapp_number} selected ambulance service from service booking")
                # Send non-emergency ambulance menu
                user_data[whatsapp_number]["module"] = "ambulance_menu"
                user_data[whatsapp_number]["state"] = "AMBULANCE_MENU"
                send_non_emergency_menu_updated(whatsapp_number, supabase)
                return False
                
            elif list_id == "service_aesthetic":
                send_coming_soon_message(whatsapp_number, supabase, "💅 Aesthetic Services", "aesthetic care services", "03-1234 5678")
                send_service_booking_menu(whatsapp_number, supabase)
                return False
                
            elif list_id == "service_hospital":
                send_coming_soon_message(whatsapp_number, supabase, "🏨 Hospital Services", "comprehensive hospital care services", "03-1234 5678")
                send_service_booking_menu(whatsapp_number, supabase)
                return False
                
            elif list_id == "service_dialysis":
                send_coming_soon_message(whatsapp_number, supabase, "💉 Dialysis Services", "quality dialysis care services", "03-1234 5678")
                send_service_booking_menu(whatsapp_number, supabase)
                return False
                
            elif list_id == "service_elderly":
                send_coming_soon_message(whatsapp_number, supabase, "👴 Elderly Care Services", "comprehensive elderly care services", "03-1234 5678")
                send_service_booking_menu(whatsapp_number, supabase)
                return False

        # ===== AMBULANCE MENU HANDLING =====
        elif module == "ambulance_menu" and state == "AMBULANCE_MENU":
            logger.info(f"Handling ambulance menu selection: {list_id}")
            
            if list_id == "advance_booking":
                user_data[whatsapp_number]["module"] = "ambulance_booking"
                user_data[whatsapp_number]["state"] = "BOOKING_STARTED"
                # Start the ambulance booking (Home to Hospital) process
                handle_booking_start(whatsapp_number, user_id, supabase, user_data)
                return False
                
            elif list_id == "homehome_transfer":
                user_data[whatsapp_number]["module"] = "ambulance_homehome"
                user_data[whatsapp_number]["state"] = "HOMEHOME_STARTED"
                # Start the home to home transfer process
                handle_homehome_start(whatsapp_number, user_id, supabase, user_data)
                return False
                
            elif list_id == "discharge_service":
                # Handle discharge service (Hospital to Home)
                user_data[whatsapp_number]["module"] = "ambulance_discharge"
                user_data[whatsapp_number]["state"] = "DISCHARGE_STARTED"
                # Start the discharge service process
                handle_discharge_start(whatsapp_number, user_id, supabase, user_data)
                return False
                
            elif list_id == "hosphosp_transfer":
                # Handle hospital to hospital transfer
                user_data[whatsapp_number]["module"] = "ambulance_hosphosp"
                user_data[whatsapp_number]["state"] = "HOSPHOSP_STARTED"
                # Start the hospital to hospital transfer process
                handle_hosphosp_start(whatsapp_number, user_id, supabase, user_data)
                return False
                
            elif list_id == "back_to_main":
                # Ask for confirmation before returning to main menu
                try:
                    # Store current state
                    user_db_data = supabase.table("whatsapp_users").select("temp_data").eq(
                        "whatsapp_number", whatsapp_number.lstrip("+")
                    ).limit(1).execute()
                    
                    if user_db_data.data and user_db_data.data[0]:
                        temp_data = user_db_data.data[0].get("temp_data", {})
                        if temp_data is None:
                            temp_data = {}
                        temp_data["previous_state"] = state
                        temp_data["previous_module"] = module
                        
                        supabase.table("whatsapp_users").update({
                            "temp_data": temp_data
                        }).eq("whatsapp_number", whatsapp_number.lstrip("+")).execute()
                except Exception as e:
                    logger.error(f"Error storing temp_data: {e}")
                
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
                
                send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
                return False
                
            else:
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, "Invalid selection. Please try again.", supabase)}}
                )
                send_non_emergency_menu_updated(whatsapp_number, supabase)
                return False

        # --- CLINIC SELECTION HANDLING ---
        elif state == "CLINIC_SELECTION":
            if list_id == "back_button":
                # Return to service booking menu
                user_data[whatsapp_number]["state"] = "SERVICE_BOOKING_MENU"
                user_data[whatsapp_number]["module"] = "service_booking_menu"
                send_service_booking_menu(whatsapp_number, supabase)
                return False
            
            if list_id.startswith("clinic_"):
                clinic_id = list_id.replace("clinic_", "")
                
                # Get clinic name for display
                clinic_response = supabase.table("c_a_clinics").select("name").eq("id", clinic_id).execute()
                clinic_name = clinic_response.data[0]["name"] if clinic_response.data else "Selected Clinic"
                
                logger.info(f"Clinic selected: {clinic_name} (ID: {clinic_id}) for {whatsapp_number}")
                
                # Check what action to take next
                next_action = user_data[whatsapp_number].get("next_action")
                
                # Store clinic ID in user_data for this session
                user_data[whatsapp_number]["clinic_id"] = clinic_id
                user_data[whatsapp_number]["clinic_name"] = clinic_name
                
                if next_action:
                    # Map next_action to category
                    category_map = {
                        "checkup_booking": "Checkup & Test",
                        "vaccination_booking": "Vaccination",
                        "health_screening": "Health Screening Plan",
                        "symptoms_checker": "General GP visit"
                    }
                    category = category_map.get(next_action)
                    
                    if category:
                        # Store in temp_data for persistence
                        try:
                            user_db_data = supabase.table("whatsapp_users").select("temp_data").eq(
                                "whatsapp_number", whatsapp_number.lstrip("+")
                            ).limit(1).execute()
                            
                            if user_db_data.data and user_db_data.data[0]:
                                temp_data = user_db_data.data[0].get("temp_data", {})
                                if temp_data is None:
                                    temp_data = {}
                                temp_data["clinic_id"] = clinic_id
                                temp_data["clinic_name"] = clinic_name
                                temp_data["next_action"] = next_action
                                
                                supabase.table("whatsapp_users").update({
                                    "temp_data": temp_data
                                }).eq("whatsapp_number", whatsapp_number.lstrip("+")).execute()
                        except Exception as e:
                            logger.error(f"Error storing clinic data: {e}")
                        
                        # Send services menu for the selected clinic and category
                        return send_services_menu(whatsapp_number, supabase, clinic_id, category, next_action)
                
                # If no next_action, send booking submenu
                send_booking_submenu(whatsapp_number, supabase)
                # Update state to show we're in booking submenu
                user_data[whatsapp_number]["state"] = "BOOKING_SUBMENU"
                user_data[whatsapp_number]["module"] = None
                return False
        
        # --- SERVICE SELECTION HANDLING ---
        elif state == "SERVICE_SELECTION":
            if list_id == "back_button":
                # Return to clinic selection
                user_data[whatsapp_number]["state"] = "CLINIC_SELECTION"
                user_data[whatsapp_number]["module"] = "clinic_selection"
                send_clinic_selection_menu(whatsapp_number, supabase, user_data[whatsapp_number].get("next_action"))
                return False
            
            if list_id.startswith("service_"):
                service_id = list_id.replace("service_", "")
                
                # Get stored services data from temp_data
                try:
                    user_db_data = supabase.table("whatsapp_users").select("temp_data").eq(
                        "whatsapp_number", whatsapp_number.lstrip("+")
                    ).limit(1).execute()
                    
                    if not user_db_data.data or not user_db_data.data[0]:
                        logger.error(f"No user data found for {whatsapp_number}")
                        send_whatsapp_message(
                            whatsapp_number, "text",
                            {"text": {"body": translate_template(whatsapp_number, "Error: User data not found. Please start over.", supabase)}}
                        )
                        user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                        send_interactive_menu(whatsapp_number, supabase)
                        return False
                    
                    temp_data = user_db_data.data[0].get("temp_data", {})
                    if temp_data is None:
                        temp_data = {}
                    services = temp_data.get("services", [])
                    clinic_id = temp_data.get("clinic_id")
                    next_action = temp_data.get("next_action")
                    
                    # Find the selected service
                    selected_service = next((s for s in services if s["id"] == service_id), None)
                    
                    if not selected_service:
                        logger.error(f"Service {service_id} not found in services list")
                        send_whatsapp_message(
                            whatsapp_number, "text",
                            {"text": {"body": translate_template(whatsapp_number, "Error: Service not found. Please try again.", supabase)}}
                        )
                        # Resend services menu
                        category_map = {
                            "checkup_booking": "Checkup & Test",
                            "vaccination_booking": "Vaccination",
                            "health_screening": "Health Screening Plan",
                            "symptoms_checker": "General GP visit"
                        }
                        category = category_map.get(next_action, "Checkup & Test")
                        return send_services_menu(whatsapp_number, supabase, clinic_id, category, next_action)
                    
                    logger.info(f"Service selected: {selected_service['service_name']} (ID: {service_id}) for {whatsapp_number}")
                    
                    # Store service details in user_data
                    user_data[whatsapp_number]["service_id"] = service_id
                    user_data[whatsapp_number]["service_name"] = selected_service["service_name"]
                    user_data[whatsapp_number]["description"] = selected_service.get("description", "")
                    user_data[whatsapp_number]["duration_minutes"] = selected_service.get("duration_minutes", 30)
                    user_data[whatsapp_number]["doctor_id"] = selected_service.get("doctor_id")
                    user_data[whatsapp_number]["clinic_id"] = clinic_id
                    
                    # Route to the appropriate module based on next_action
                    if next_action == "checkup_booking":
                        user_data[whatsapp_number]["module"] = "checkup_booking"
                        user_data[whatsapp_number]["state"] = "IDLE"
                        # Start checkup booking flow
                        dummy_message = {"type": "text", "text": {"body": "start"}}
                        return handle_checkup(whatsapp_number, user_id, supabase, user_data, dummy_message)
                    elif next_action == "vaccination_booking":
                        user_data[whatsapp_number]["module"] = "vaccination_booking"
                        user_data[whatsapp_number]["state"] = "IDLE"
                        # Start vaccination booking flow
                        dummy_message = {"type": "text", "text": {"body": "start"}}
                        return handle_vaccination(whatsapp_number, user_id, supabase, user_data, dummy_message)
                    elif next_action == "health_screening":
                        user_data[whatsapp_number]["module"] = "health_screening"
                        user_data[whatsapp_number]["state"] = "IDLE"
                        # Store category image URL if available
                        if selected_service.get("brochure_image_url"):
                            if "temp_data" not in user_data[whatsapp_number]:
                                user_data[whatsapp_number]["temp_data"] = {}
                            user_data[whatsapp_number]["temp_data"]["category_image_url"] = selected_service.get("brochure_image_url")
                        # Start health screening flow
                        dummy_message = {"type": "text", "text": {"body": "start"}}
                        return handle_healthsp(whatsapp_number, user_id, supabase, user_data, dummy_message)
                    elif next_action == "symptoms_checker":
                        user_data[whatsapp_number]["module"] = "report_symptoms"
                        user_data[whatsapp_number]["state"] = "IDLE"
                        # Start symptoms checker flow
                        dummy_message = {"type": "text", "text": {"body": "start"}}
                        return handle_symptoms(whatsapp_number, user_id, supabase, user_data, dummy_message)
                    
                    # Default fallback
                    send_whatsapp_message(
                        whatsapp_number, "text",
                        {"text": {"body": translate_template(whatsapp_number, "Error: Invalid service selection. Please try again.", supabase)}}
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return False
                    
                except Exception as e:
                    logger.error(f"Error processing service selection: {e}", exc_info=True)
                    send_whatsapp_message(
                        whatsapp_number, "text",
                        {"text": {"body": translate_template(whatsapp_number, "An error occurred. Please try again.", supabase)}}
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return False
        
        # --- BACK BUTTON ---
        if list_id == "back_button":
            # Ask for confirmation before returning to main menu
            try:
                # Store current state
                user_db_data = supabase.table("whatsapp_users").select("temp_data").eq(
                    "whatsapp_number", whatsapp_number.lstrip("+")
                ).limit(1).execute()
                
                if user_db_data.data and user_db_data.data[0]:
                    temp_data = user_db_data.data[0].get("temp_data", {})
                    if temp_data is None:
                        temp_data = {}
                    temp_data["previous_state"] = state
                    temp_data["previous_module"] = module
                    
                    supabase.table("whatsapp_users").update({
                        "temp_data": temp_data
                    }).eq("whatsapp_number", whatsapp_number.lstrip("+")).execute()
            except Exception as e:
                logger.error(f"Error storing temp_data: {e}")
            
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
            
            send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
            return False

        # --- QUICK BOOKING (Report Review) ---
        if list_id in BOOKING_OPTIONS:
            booking_data = BOOKING_OPTIONS[list_id]
            user_data[whatsapp_number]["module"] = "checkup_result_booking"
            user_data[whatsapp_number]["state"] = "BOOKING_SELECTED"
            user_data[whatsapp_number]["temp_data"] = booking_data
            supabase.table("whatsapp_users").update({
                "state": "BOOKING_SELECTED",
                "temp_data": booking_data
            }).eq("id", user_id).execute()
            logger.info(f"Booking selected: {booking_data['service']} for {whatsapp_number}")
            send_doctor_selection_message(whatsapp_number, supabase, booking_data['clinic_id'])
            return False

        # --- REQUEST REPORT ---
        if list_id.startswith("request_report_"):
            user_data[whatsapp_number]["state"] = "AWAITING_VERIFICATION"
            user_data[whatsapp_number]["list_reply_id"] = list_id
            user_data[whatsapp_number]["module"] = "view_booking"
            handle_request_report(whatsapp_number, user_id, supabase, user_data, list_id)
            return False

        # --- BOOKING SUBMENU HANDLING ---
        if state == "BOOKING_SUBMENU":
            # Handle selections from the booking submenu
            category_map = {
                "checkup_booking": "Checkup & Test",
                "vaccination_booking": "Vaccination",
                "health_screening": "Health Screening Plan",
                "symptoms_checker": "General GP visit",
                "clinic_enquiries": None
            }
            
            if list_id in ["checkup_booking", "vaccination_booking", "health_screening", "symptoms_checker"]:
                # Get clinic ID from user_data
                clinic_id = user_data[whatsapp_number].get("clinic_id")
                if not clinic_id:
                    # Try to get from temp_data in database
                    try:
                        user_db_data = supabase.table("whatsapp_users").select("temp_data").eq(
                            "whatsapp_number", whatsapp_number.lstrip("+")
                        ).limit(1).execute()
                        
                        if user_db_data.data and user_db_data.data[0]:
                            temp_data = user_db_data.data[0].get("temp_data", {})
                            if temp_data:
                                clinic_id = temp_data.get("clinic_id")
                    except Exception as e:
                        logger.error(f"Error fetching clinic_id from temp_data: {e}")
                
                if not clinic_id:
                    logger.error(f"No clinic_id found for {whatsapp_number} in booking submenu")
                    send_whatsapp_message(
                        whatsapp_number, "text",
                        {"text": {"body": translate_template(whatsapp_number, "Error: Clinic not selected. Please start over.", supabase)}}
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return False
                
                # Store next_action and update state
                user_data[whatsapp_number]["next_action"] = list_id
                user_data[whatsapp_number]["state"] = "SERVICE_SELECTION"
                
                # Send services menu for the selected category
                category = category_map.get(list_id)
                return send_services_menu(whatsapp_number, supabase, clinic_id, category, list_id)
            
            elif list_id == "clinic_enquiries":
                user_data[whatsapp_number]["module"] = "clinic_enquiries"
                user_data[whatsapp_number]["state"] = "CLINIC_ENQUIRIES"
                handle_clinic_enquiries(whatsapp_number, user_id, supabase, user_data)
                return False
            elif list_id == "view_booking":
                user_data[whatsapp_number]["module"] = "view_booking"
                handle_view_booking_submenu(whatsapp_number, user_data, supabase)
                return False
            elif list_id == "reschedule_booking":
                user_data[whatsapp_number]["module"] = "reschedule_booking"
                return handle_reschedule(whatsapp_number, user_id, supabase, user_data, message)
            
            # --- FIX: RESET STATE TO IDLE BEFORE CALLING REPORT BOOKING ---
            elif list_id == "checkup_result_booking":
                user_data[whatsapp_number]["module"] = "checkup_result_booking"
                user_data[whatsapp_number]["state"] = "IDLE"
                return handle_report_booking(whatsapp_number, user_id, supabase, user_data, message)
            
            elif list_id == "back_button":
                # Ask for confirmation before returning to clinic selection
                try:
                    # Store current state
                    user_db_data = supabase.table("whatsapp_users").select("temp_data").eq(
                        "whatsapp_number", whatsapp_number.lstrip("+")
                    ).limit(1).execute()
                    
                    if user_db_data.data and user_db_data.data[0]:
                        temp_data = user_db_data.data[0].get("temp_data", {})
                        if temp_data is None:
                            temp_data = {}
                        temp_data["previous_state"] = state
                        temp_data["previous_module"] = module
                        
                        supabase.table("whatsapp_users").update({
                            "temp_data": temp_data
                        }).eq("whatsapp_number", whatsapp_number.lstrip("+")).execute()
                except Exception as e:
                    logger.error(f"Error storing temp_data: {e}")
                
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
                
                send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
                return False

        # --- VIEW BOOKING SUBMENU ---
        if state == "VIEW_BOOKING_SUBMENU" and module == "view_booking":
            if list_id == "view_upcoming_bookings":
                handle_view_upcoming_booking(whatsapp_number, user_id, supabase, user_data)
                return False
            else:
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, "Invalid selection. Please try again.", supabase)}}
                )
                handle_view_booking_submenu(whatsapp_number, user_data, supabase)
                return False

        # --- CHANGE LANGUAGE (now LANGUAGES) ---
        elif state == "CHANGE_LANGUAGE" and module == "change_language":
            lang_map = {"lang_en": "en", "lang_bm": "bm", "lang_cn": "cn", "lang_tm": "tm"}
            selected_language = lang_map.get(list_id, "en")
            try:
                supabase.table("whatsapp_users").update({"language": selected_language}).eq("id", user_id).execute()
                logger.info(f"Updated language for {whatsapp_number} to {selected_language}")
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, f"Language set to {selected_language}.", supabase)}}
                )
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False
            except Exception as e:
                logger.error(f"Error updating language for {whatsapp_number}: {e}", exc_info=True)
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, "Error setting language. Please try again.", supabase)}}
                )
                user_data[whatsapp_number] = {"state": "CHANGE_LANGUAGE", "processing": False, "module": "change_language"}
                send_language_selection_menu(whatsapp_number, supabase)
                return False

        # --- HELP / CONCIERGE ---
        elif list_id == "help":
            user_data[whatsapp_number]["module"] = "concierge"
            user_data[whatsapp_number]["state"] = "CONCIERGE"
            send_concierge_prompt(whatsapp_number, supabase)
            return False

        # --- CLINIC ENQUIRIES ---
        elif list_id == "clinic_enquiries":
            user_data[whatsapp_number]["module"] = "clinic_enquiries"
            user_data[whatsapp_number]["state"] = "CLINIC_ENQUIRIES"
            handle_clinic_enquiries(whatsapp_number, user_id, supabase, user_data)
            return False

        # --- SYMPTOM TRACKER ---
        elif list_id == "symptom_tracker":
            user_data[whatsapp_number]["module"] = "symptom_tracker"
            user_data[whatsapp_number]["state"] = "SYMPTOM_TRACKER_SELECT"
            return handle_symptom_tracker_selection(whatsapp_number, user_id, supabase, user_data)

        # --- NOTIFICATION ---
        elif list_id == "notification":
            from notification import display_and_clear_notifications
            display_and_clear_notifications(supabase, whatsapp_number)
            user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
            return False

        # === PROFILE (Individual Module) ===
        elif list_id == "profile":
            logger.info(f"User {whatsapp_number} selected profile")
            # Start individual module (keeping same functionality but renamed)
            user_data[whatsapp_number]["module"] = "individual"
            user_data[whatsapp_number]["state"] = "IDLE"
            
            # Start individual module flow
            return handle_individual_start(whatsapp_number, user_id, supabase, user_data)

        # --- MODULE-SPECIFIC HANDLING ---
        elif module:
            if module == "report_symptoms":
                return handle_symptoms(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "checkup_booking":
                return handle_checkup(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "vaccination_booking":
                return handle_vaccination(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "reschedule_booking":
                return handle_reschedule(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "checkup_result_booking":
                return handle_report_booking(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "health_screening":
                return handle_healthsp(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "symptom_tracker":
                return handle_symptom_tracker_response(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "view_booking":
                return handle_view_booking(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "tcm_service":
                return handle_tcm_service(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "individual":
                return handle_individual_response(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "ambulance_discharge":
                return handle_discharge_response(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "ambulance_hosphosp":
                return handle_hosphosp_response(whatsapp_number, user_id, supabase, user_data, message)

        # --- MAIN MENU OPTIONS (no active module) ---
        else:
            # === NOTIFICATION ===
            if list_id == "notification":
                from notification import display_and_clear_notifications
                display_and_clear_notifications(supabase, whatsapp_number)
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                return False

            # === PROFILE (Individual Module) ===
            elif list_id == "profile":
                logger.info(f"User {whatsapp_number} selected profile")
                # Start individual module
                user_data[whatsapp_number]["module"] = "individual"
                user_data[whatsapp_number]["state"] = "IDLE"
                return handle_individual_start(whatsapp_number, user_id, supabase, user_data)

            # === SERVICE BOOKING ===
            elif list_id == "service_booking":
                logger.info(f"User {whatsapp_number} selected service booking")
                # Send service booking menu
                user_data[whatsapp_number]["state"] = "SERVICE_BOOKING_MENU"
                user_data[whatsapp_number]["module"] = "service_booking_menu"
                return send_service_booking_menu(whatsapp_number, supabase)

            # === UPCOMING BOOKING ===
            elif list_id == "upcoming_booking":
                user_data[whatsapp_number]["module"] = "view_booking"
                handle_view_booking_submenu(whatsapp_number, user_data, supabase)
                return False

            # === HELP ===
            elif list_id == "help":
                user_data[whatsapp_number]["module"] = "concierge"
                user_data[whatsapp_number]["state"] = "CONCIERGE"
                send_concierge_prompt(whatsapp_number, supabase)
                return False

            # === LANGUAGES ===
            elif list_id == "languages":
                user_data[whatsapp_number]["module"] = "change_language"
                user_data[whatsapp_number]["state"] = "CHANGE_LANGUAGE"
                send_language_selection_menu(whatsapp_number, supabase)
                return False

            # === FALLBACK ===
            else:
                send_whatsapp_message(
                    whatsapp_number, "text",
                    {"text": {"body": translate_template(whatsapp_number, "Invalid selection. Please try again.", supabase)}}
                )
                user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False

    # --- BUTTON REPLY ---
    elif interactive_type == "button_reply":
        button_id = message["interactive"]["button_reply"]["id"]
        logger.info(f"Received button reply: {button_id} from {whatsapp_number}")

        # 1. Handle Back to Home from View Booking
        if button_id == "back_to_home":
            # Ask for confirmation
            try:
                # Store current state
                user_db_data = supabase.table("whatsapp_users").select("temp_data").eq(
                    "whatsapp_number", whatsapp_number.lstrip("+")
                ).limit(1).execute()
                
                if user_db_data.data and user_db_data.data[0]:
                    temp_data = user_db_data.data[0].get("temp_data", {})
                    if temp_data is None:
                        temp_data = {}
                    temp_data["previous_state"] = state
                    temp_data["previous_module"] = module
                    
                    supabase.table("whatsapp_users").update({
                        "temp_data": temp_data
                    }).eq("whatsapp_number", whatsapp_number.lstrip("+")).execute()
            except Exception as e:
                logger.error(f"Error storing temp_data: {e}")
            
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
            
            send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
            return False

        # --- TIME CONFIRMATION HANDLING ---
        # Handle time confirmation buttons before they get routed to view_booking
        if button_id in ["confirm_time", "accept_closest_time", "find_another_time", "try_again_time", "help_choose_time"]:
            logger.info(f"Handling time confirmation button: {button_id} for {whatsapp_number}")
            
            # Check if we're in a time confirmation state
            if state in ["CONFIRM_TIME", "CONFIRM_CLOSEST_TIME", "RETRY_TIME_OR_HELP"]:
                # Handle based on button
                if button_id == "confirm_time":
                    # Check if this is for reschedule (view_booking) or other module
                    if module == "view_booking":
                        return handle_view_booking(whatsapp_number, user_id, supabase, user_data, message)
                    else:
                        # Handle normal time confirmation
                        handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, module, confirmed=True)
                elif button_id == "accept_closest_time":
                    handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, module, confirmed=True, use_closest=True)
                elif button_id == "find_another_time":
                    handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, module, confirmed=False)
                elif button_id in ["try_again_time", "help_choose_time"]:
                    handle_retry_time_or_help(whatsapp_number, user_id, supabase, user_data, module, button_id)
                return False

        # 2. Handle View Booking Actions (Reschedule, Cancel, Accept, Decline)
        # Exclude time confirmation buttons that should be handled by calendar_utils
        should_route_to_view_booking = (
            button_id.startswith("reschedule_") or 
            (button_id.startswith("cancel_") and button_id != "cancel_button" and not (state == "CONFIRM_BOOKING" and button_id == "cancel_booking")) or 
            (button_id.startswith("accept_") and button_id not in ["accept_closest_time"]) or 
            button_id.startswith("decline_") or
            button_id in ["confirm_reschedule", "cancel_reschedule", "confirm_future_date", "reject_future_date"]
        )
            
        if should_route_to_view_booking:
            logger.info(f"Routing button {button_id} to view_booking module")
            user_data[whatsapp_number]["module"] = "view_booking"

            # If it's an action button, ensure state allows action handling
            # DON'T change state if we're already in CONFIRM_REPEATED_CANCEL or if it's a repeated cancellation button
            current_state = user_data[whatsapp_number].get("state")
            
            if button_id.startswith(("reschedule_", "cancel_", "accept_", "decline_")):
                # Check if we're already in CONFIRM_REPEATED_CANCEL state
                if current_state != "CONFIRM_REPEATED_CANCEL" and not button_id.startswith(("cancel_single_", "cancel_all_")):
                    user_data[whatsapp_number]["state"] = "SELECT_ACTION"
                
            return handle_view_booking(whatsapp_number, user_id, supabase, user_data, message)


        if button_id == "back_button":
            # Ask for confirmation
            try:
                # Store current state
                user_db_data = supabase.table("whatsapp_users").select("temp_data").eq(
                    "whatsapp_number", whatsapp_number.lstrip("+")
                ).limit(1).execute()
                
                if user_db_data.data and user_db_data.data[0]:
                    temp_data = user_db_data.data[0].get("temp_data", {})
                    if temp_data is None:
                        temp_data = {}
                    temp_data["previous_state"] = state
                    temp_data["previous_module"] = module
                    
                    supabase.table("whatsapp_users").update({
                        "temp_data": temp_data
                    }).eq("whatsapp_number", whatsapp_number.lstrip("+")).execute()
            except Exception as e:
                logger.error(f"Error storing temp_data: {e}")
            
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
            
            send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
            return False

        if button_id.startswith("doc_") and button_id != "doc_more":
            # Check if this is for view_booking (reschedule) or report_booking
            if module == "view_booking":
                return handle_view_booking(whatsapp_number, user_id, supabase, user_data, message)
            else:
                handle_doctor_selection(whatsapp_number, user_id, supabase, user_data, button_id)
            return False

        elif button_id.startswith("hour_"):
            if module == "view_booking":
                return handle_view_booking(whatsapp_number, user_id, supabase, user_data, message)
            else:
                handle_hour_selection(whatsapp_number, user_id, supabase, user_data, button_id)
            return False

        elif module == "clinic_enquiries":
            handle_clinic_enquiries_response(whatsapp_number, button_id, user_id, supabase, user_data)
            return False

        if button_id == "request_report":
            handle_verification_response(whatsapp_number, user_id, supabase, user_data, button_id=button_id)
            return False
        elif button_id == "cancel_button":
            # Ask for confirmation
            try:
                # Store current state
                user_db_data = supabase.table("whatsapp_users").select("temp_data").eq(
                    "whatsapp_number", whatsapp_number.lstrip("+")
                ).limit(1).execute()
                
                if user_db_data.data and user_db_data.data[0]:
                    temp_data = user_db_data.data[0].get("temp_data", {})
                    if temp_data is None:
                        temp_data = {}
                    temp_data["previous_state"] = state
                    temp_data["previous_module"] = module
                    
                    supabase.table("whatsapp_users").update({
                        "temp_data": temp_data
                    }).eq("whatsapp_number", whatsapp_number.lstrip("+")).execute()
            except Exception as e:
                logger.error(f"Error storing temp_data: {e}")
            
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
            
            send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
            return False
        elif button_id.startswith("request_report_"):
            user_data[whatsapp_number]["state"] = "AWAITING_VERIFICATION"
            user_data[whatsapp_number]["list_reply_id"] = button_id
            user_data[whatsapp_number]["module"] = "view_booking"
            handle_request_report(whatsapp_number, user_id, supabase, user_data, button_id)
            return False
        elif button_id == "return_menu":
            # Ask for confirmation
            try:
                # Store current state
                user_db_data = supabase.table("whatsapp_users").select("temp_data").eq(
                    "whatsapp_number", whatsapp_number.lstrip("+")
                ).limit(1).execute()
                
                if user_db_data.data and user_db_data.data[0]:
                    temp_data = user_db_data.data[0].get("temp_data", {})
                    if temp_data is None:
                        temp_data = {}
                    temp_data["previous_state"] = state
                    temp_data["previous_module"] = module
                    
                    supabase.table("whatsapp_users").update({
                        "temp_data": temp_data
                    }).eq("whatsapp_number", whatsapp_number.lstrip("+")).execute()
            except Exception as e:
                logger.error(f"Error storing temp_data: {e}")
            
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
            
            send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
            return False

        # Pass to module handler
        elif module:
            if module == "report_symptoms":
                return handle_symptoms(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "checkup_booking":
                return handle_checkup(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "vaccination_booking":
                return handle_vaccination(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "reschedule_booking":
                return handle_reschedule(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "checkup_result_booking":
                return handle_report_booking(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "health_screening":
                return handle_healthsp(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "symptom_tracker":
                return handle_symptom_tracker_response(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "view_booking":
                return handle_view_booking(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "tcm_service":
                return handle_tcm_service(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "individual":
                return handle_individual_response(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "ambulance_discharge":
                return handle_discharge_response(whatsapp_number, user_id, supabase, user_data, message)
            elif module == "ambulance_hosphosp":
                return handle_hosphosp_response(whatsapp_number, user_id, supabase, user_data, message)

        else:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, "Invalid button selection. Please try again.", supabase)}}
            )
            user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False

def _handle_text_message(whatsapp_number, user_id, supabase, user_data, message):
    """Handle text messages when buttons are expected."""
    module = user_data[whatsapp_number].get("module")
    state = user_data[whatsapp_number].get("state")
    original_text = message["text"]["body"].strip() if "text" in message else ""
    text_content = original_text.lower() if original_text else ""

    # ===== SPECIAL HANDLING FOR DATE/TIME INPUT STATES =====
    # These states expect free-form text input, not menu buttons
    
    # Check if we're in a state that expects text input (dates or times)
    if state in ["AWAITING_FUTURE_DATE", "RETRY_FUTURE_DATE"]:
        # This is a date input for future date selection
        logger.info(f"Processing future date input for {whatsapp_number}: {original_text}")
        from calendar_utils import handle_future_date_input
        return handle_future_date_input(whatsapp_number, user_id, supabase, user_data, module, original_text)
    
    elif state in ["AWAITING_TIME_INPUT", "RETRY_TIME_OR_HELP"]:
        # This is a time input
        logger.info(f"Processing time input for {whatsapp_number}: {original_text}")
        from calendar_utils import handle_time_input
        return handle_time_input(whatsapp_number, user_id, supabase, user_data, module, original_text)
    
    elif state == "AWAITING_SYMPTOMS":
        # Symptoms input for report_symptoms module
        logger.info(f"Processing symptoms input for {whatsapp_number}: {original_text}")
        if module == "report_symptoms":
            return handle_symptoms(whatsapp_number, user_id, supabase, user_data, message)
    
    elif state == "AWAITING_CHECKUP_TYPE":
        # Checkup type input for checkup_booking module
        logger.info(f"Processing checkup type input for {whatsapp_number}: {original_text}")
        if module == "checkup_booking":
            return handle_checkup(whatsapp_number, user_id, supabase, user_data, message)
    
    elif state == "AWAITING_VACCINE_TYPE":
        # Vaccine type input for vaccination_booking module
        logger.info(f"Processing vaccine type input for {whatsapp_number}: {original_text}")
        if module == "vaccination_booking":
            return handle_vaccination(whatsapp_number, user_id, supabase, user_data, message)
    
    # Handle module-specific text responses
    elif module:
        if module == "report_symptoms":
            return handle_symptoms(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "checkup_booking":
            return handle_checkup(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "vaccination_booking":
            return handle_vaccination(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "reschedule_booking":
            return handle_reschedule(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "checkup_result_booking":
            return handle_report_booking(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "health_screening":
            return handle_healthsp(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "concierge":
            from concierge import handle_concierge_response
            return handle_concierge_response(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "clinic_enquiries":
            return handle_clinic_enquiries(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "symptom_tracker":
            return handle_symptom_tracker_response(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "view_booking":
            return handle_view_booking(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "tcm_service":
            return handle_tcm_service(whatsapp_number, user_id, supabase, user_data, message)
        # Handle ambulance modules
        elif module == "ambulance_booking":
            return handle_booking_response(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "ambulance_homehome":
            return handle_homehome_response(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "ambulance_discharge":
            return handle_discharge_response(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "ambulance_hosphosp":
            return handle_hosphosp_response(whatsapp_number, user_id, supabase, user_data, message)
        elif module == "individual":
            return handle_individual_response(whatsapp_number, user_id, supabase, user_data, message)
    else:
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, "Please use the menu below to select an option:", supabase)}}
        )
        send_interactive_menu(whatsapp_number, supabase)
        return False

def _handle_back_button(whatsapp_number, user_id, supabase, user_data):
    """Handle back button - return to main menu."""
    module = user_data[whatsapp_number].get("module")
    state = user_data[whatsapp_number].get("state")
    logger.info(f"Back button pressed in module: {module}, state: {state}")

    user_data[whatsapp_number] = {"state": "IDLE", "processing": False, "module": None}
    supabase.table("whatsapp_users").update({
        "state": "IDLE",
        "module": None,
        "temp_data": {}
    }).eq("id", user_id).execute()

    send_whatsapp_message(
        whatsapp_number, "text",
        {"text": {"body": translate_template(whatsapp_number, "Returning to main menu.", supabase)}}
    )
    send_interactive_menu(whatsapp_number, supabase)
    return False

def send_coming_soon_message(whatsapp_number: str, supabase, service_name: str, service_description: str, hotline: str):
    """Send a 'coming soon' message for services under development."""
    message = translate_template(
        whatsapp_number, 
        f"{service_name}\n\n"
        f"{service_description} are coming soon!\n\n"
        f"We're working to bring you the best {service_description}. "
        f"Please check back later or contact our hotline for more information:\n"
        f"📞 {hotline}", 
        supabase
    )
    send_whatsapp_message(
        whatsapp_number, 
        "text",
        {"text": {"body": message}}
    )

# === DOCTOR & TIME SELECTION (used by Report Booking) ===
def send_doctor_selection_message(whatsapp_number: str, supabase, clinic_id: str):
    try:
        doctors = supabase.table('c_a_doctors').select('id, name').eq('clinic_id', clinic_id).execute()
        buttons = []
        for doctor in doctors.data[:3]:
            # Use gt_t_tt for doctor name (dynamic content)
            doctor_name = gt_t_tt(whatsapp_number, doctor['name'], supabase)
            buttons.append({
                "type": "reply",
                "reply": {"id": f"doc_{doctor['id']}", "title": doctor_name}
            })
        if len(doctors.data) > 3:
            buttons.append({"type": "reply", "reply": {"id": "doc_more", "title": translate_template(whatsapp_number, "More Doctors", supabase)}})
        buttons.append({"type": "reply", "reply": {"id": "back_button", "title": translate_template(whatsapp_number, "Back", supabase)}})

        message = {
            "messaging_product": "whatsapp",
            "to": whatsapp_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": gt_tt(whatsapp_number, "SELECT DOCTOR\n\nWhich doctor would you like to book with?", supabase)},
                "action": {"buttons": buttons}
            }
        }
        send_whatsapp_message(whatsapp_number, "interactive", message, supabase)
    except Exception as e:
        logger.error(f"Error sending doctor selection: {e}")

def handle_doctor_selection(whatsapp_number: str, user_id: str, supabase, user_data, button_id: str):
    doctor_id = button_id.replace('doc_', '')
    user_data[whatsapp_number]["state"] = "DOCTOR_SELECTED"
    user_data[whatsapp_number]["temp_data"]["doctor_id"] = doctor_id
    supabase.table("whatsapp_users").update({
        "state": "DOCTOR_SELECTED",
        "temp_data": user_data[whatsapp_number]["temp_data"]
    }).eq("id", user_id).execute()
    send_hour_selection_message(whatsapp_number, supabase)

def send_hour_selection_message(whatsapp_number: str, supabase):
    hours = ["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"]
    buttons = []
    for hour in hours:
        buttons.append({
            "type": "reply",
            "reply": {"id": f"hour_{hour.replace(':', '')}", "title": f"{hour}"}
        })
    buttons.append({"type": "reply", "reply": {"id": "back_button", "title": translate_template(whatsapp_number, "Back", supabase)}})

    message = {
        "messaging_product": "whatsapp",
        "to": whatsapp_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": gt_tt(whatsapp_number, "SELECT TIME\n\nChoose your preferred time slot:", supabase)},
            "action": {"buttons": buttons}
        }
    }
    send_whatsapp_message(whatsapp_number, "interactive", message, supabase)

def handle_hour_selection(whatsapp_number: str, user_id: str, supabase, user_data, button_id: str):
    hour_str = button_id.replace('hour_', '')
    hour = f"{hour_str[:2]}:{hour_str[2:]}"
    user_data[whatsapp_number]["temp_data"]["time"] = hour
    user_data[whatsapp_number]["state"] = "TIME_SELECTED"
    supabase.table("whatsapp_users").update({
        "state": "TIME_SELECTED",
        "temp_data": user_data[whatsapp_number]["temp_data"]
    }).eq("id", user_id).execute()
    message = {"type": "text", "text": {"body": hour}}
    handle_report_booking(whatsapp_number, user_id, supabase, user_data, message)

# === LANGUAGE SELECTION ===
def send_language_selection_menu(whatsapp_number: str, supabase):
    content = {
        "interactive": {
            "type": "list",
            "header": {
                "type": "text", 
                "text": truncate_text(translate_template(whatsapp_number, "AnyHealth Bot", supabase), MAX_HEADER_TEXT)
            },
            "body": {
                "text": truncate_text(
                    translate_template(whatsapp_number, "Please select your preferred language:", supabase),
                    MAX_BODY_TEXT
                )
            },
            "footer": {
                "text": truncate_text(
                    translate_template(whatsapp_number, "Choose a language to proceed", supabase),
                    MAX_BODY_TEXT
                )
            },
            "action": {
                "button": truncate_text(translate_template(whatsapp_number, "Select Language", supabase), MAX_BUTTON_TEXT),
                "sections": [{
                    "title": truncate_text(translate_template(whatsapp_number, "Languages", supabase), MAX_SECTION_TITLE),
                    "rows": [
                        {"id": "lang_en", "title": translate_template(whatsapp_number, "English", supabase)},
                        {"id": "lang_bm", "title": translate_template(whatsapp_number, "Bahasa Malaysia", supabase)},
                        {"id": "lang_cn", "title": translate_template(whatsapp_number, "中文", supabase)},
                        {"id": "lang_tm", "title": translate_template(whatsapp_number, "தமிழ்", supabase)},
                        {"id": "back_button", "title": translate_template(whatsapp_number, "Back to Main Menu", supabase)}
                    ]
                }]
            }
        }
    }
    send_whatsapp_message(whatsapp_number, "interactive", content, supabase)

# === BOOKING SUBMENU ===
def send_booking_submenu(to: str, supabase=None) -> bool:
    """Send booking submenu with Health Screening Plan added and proper truncation."""
    to = to.strip()
    if not to.startswith("+"):
        to = f"+{to}"

    section_title = translate_template(to, "Booking Services", supabase)
    
    rows = [
        {
            "id": "clinic_enquiries", 
            "title": truncate_text(translate_template(to, "📞 Clinic Enquiries", supabase), MAX_TITLE_LENGTH)
        },
        {
            "id": "health_screening", 
            "title": translate_template(to, "Health Screening Plan", supabase)
        },
        {
            "id": "symptoms_checker", 
            "title": truncate_text(translate_template(to, "General GP Visit", supabase), MAX_TITLE_LENGTH)
        },
        {
            "id": "checkup_booking", 
            "title": truncate_text(translate_template(to, "Checkup & Test", supabase), MAX_TITLE_LENGTH)
        },
        {
            "id": "vaccination_booking", 
            "title": truncate_text(translate_template(to, "Vaccination", supabase), MAX_TITLE_LENGTH)
        },
        {
            "id": "back_button", 
            "title": translate_template(to, "🔙 Back to Main Menu", supabase)
        }
    ]

    content = {
        "interactive": {
            "type": "list",
            "header": {
                "type": "text", 
                "text": truncate_text(translate_template(to, "AnyHealth Bot", supabase), MAX_HEADER_TEXT)
            },
            "body": {
                "text": truncate_text(
                    translate_template(to, "Please choose a booking option:", supabase),
                    MAX_BODY_TEXT
                )
            },
            "footer": {
                "text": truncate_text(
                    translate_template(to, "Select an option to proceed", supabase),
                    MAX_BODY_TEXT
                )
            },
            "action": {
                "button": truncate_text(translate_template(to, "Booking Options", supabase), MAX_BUTTON_TEXT),
                "sections": [{
                    "title": section_title,
                    "rows": rows
                }]
            }
        }
    }
    return send_whatsapp_message(to, "interactive", content, supabase)

