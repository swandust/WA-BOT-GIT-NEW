# tcm_service.py - UPDATED WITH PROPER TRANSLATION FUNCTIONS
import uuid
import logging
import time
from datetime import datetime
from tcm_calendar_utils import (
    get_available_doctors_for_service, get_calendar, select_period, get_available_hours,
    get_time_slots, get_available_doctors, handle_confirm_booking_tcm,
    handle_cancel_booking_tcm, handle_future_date_input, handle_future_date_confirmation,
    show_edit_options, handle_edit_choice, handle_time_input, handle_time_confirmation,
    handle_retry_time_or_help, get_clinic_doctor_selection
)
from utils import (
    send_whatsapp_message, send_interactive_menu, translate_template,
    gt_t_tt, gt_tt, send_image_message, gt_dt_tt
)
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_address_from_lat_lon(lat, lon):
    """Reverse geocode latitude and longitude to address using Nominatim."""
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
    headers = {'User-Agent': 'TCMBookingApp'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get('display_name', 'Address not found')
        else:
            return 'Address not found'
    except Exception as e:
        logger.error(f"Error in reverse geocoding: {e}")
        return 'Address not found'

def truncate_text(text, max_length, suffix="..."):
    """Helper function to truncate text to specified length."""
    if not text:
        return text
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix

def proceed_to_remark(whatsapp_number, supabase, user_data):
    """Proceed to remark yes/no after sending service description."""
    user_data[whatsapp_number]["state"] = "TCM_REMARK_YES_NO"
    user_data[whatsapp_number]["module"] = "tcm_service"
    
    service_name = user_data[whatsapp_number].get("service_name")
    duration = user_data[whatsapp_number].get("duration_minutes", 30)
    description = user_data[whatsapp_number].get("service_description", "")
    
    if description.strip():
        truncated_desc = gt_tt(whatsapp_number, description.strip(), supabase)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": truncated_desc}},
            supabase
        )
        time.sleep(1)
    
    prompt = translate_template(
        whatsapp_number,
        "Do you have any remarks for {} ({} min)?", supabase
    ).format(service_name, duration)
    
    send_whatsapp_message(
        whatsapp_number,
        "interactive",
        {
            "interactive": {
                "type": "button",
                "body": {"text": prompt},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "remark_yes", "title": translate_template(whatsapp_number, "Yes", supabase)}},
                        {"type": "reply", "reply": {"id": "remark_no", "title": translate_template(whatsapp_number, "No", supabase)}}
                    ]
                }
            }
        },
        supabase
    )

def set_method_and_proceed(whatsapp_number, user_id, supabase, user_data, method_id):
    """Set the selected method and proceed based on address and priority requirements."""
    try:
        # Fetch method details
        method_response = supabase.table("tcm_a_service_method") \
            .select("method_name, address, priority, description") \
            .eq("id", method_id) \
            .single() \
            .execute()
        
        if method_response.data:
            method = method_response.data
            user_data[whatsapp_number]["method_id"] = method_id
            user_data[whatsapp_number]["method_name"] = method["method_name"]  # Keep original name
            user_data[whatsapp_number]["address_required"] = method["address"]
            user_data[whatsapp_number]["priority_required"] = method["priority"]
        else:
            # Fallback if method not found
            user_data[whatsapp_number]["method_id"] = method_id
            user_data[whatsapp_number]["method_name"] = "Selected Method"  # Hardcoded, use translate_template
            user_data[whatsapp_number]["address_required"] = False
            user_data[whatsapp_number]["priority_required"] = True
        
        # Check if address is required
        if user_data[whatsapp_number].get("address_required", False):
            user_data[whatsapp_number]["state"] = "AWAITING_ADDRESS"
            send_whatsapp_message(
                whatsapp_number,
                "interactive",
                {
                    "interactive": {
                        "type": "location_request_message",
                        "body": {"text": translate_template(whatsapp_number, "Please share your current location or enter your address manually:", supabase)},
                        "action": {"name": "send_location"}
                    }
                },
                supabase
            )
        else:
            # Skip address input, proceed to remark yes/no
            proceed_to_remark(whatsapp_number, supabase, user_data)
        
    except Exception as e:
        logger.error(f"[TCM] Error in set_method_and_proceed for {whatsapp_number}: {str(e)}")
        # Fallback to original flow
        proceed_to_remark(whatsapp_number, supabase, user_data)

def handle_tcm_service(whatsapp_number, user_id, supabase, user_data, message):
    """Main handler for TCM service booking flow."""
    state = user_data.get(whatsapp_number, {}).get("state", "IDLE")
    logger.info(f"[TCM] Handling TCM service for {whatsapp_number}, state: {state}")
    # ------------------------------------------------------------------
    # 1. FETCH USER LANGUAGE
    # ------------------------------------------------------------------
    language = "en"
    try:
        resp = supabase.table("whatsapp_users") \
            .select("language") \
            .eq("whatsapp_number", whatsapp_number.lstrip("+")) \
            .limit(1).execute()
        if resp.data:
            language = resp.data[0]["language"]
    except Exception as e:
        logger.error(f"[TCM] Error fetching language for {whatsapp_number}: {e}")
    # ------------------------------------------------------------------
    # 2. IDLE → Logic modified for Auto-Routing
    # ------------------------------------------------------------------
    if state == "IDLE":
        # Check if the router already injected a clinic
        prefilled_clinic_id = user_data.get(whatsapp_number, {}).get("clinic_id")
       
        if prefilled_clinic_id:
            logger.info(f"[TCM] Auto-routing for clinic: {prefilled_clinic_id}")
            # Jump straight to clinic info display
            user_data[whatsapp_number]["state"] = "TCM_CLINIC_INFO_DISPLAY"
            display_clinic_info_and_proceed(whatsapp_number, supabase, user_data, prefilled_clinic_id)
        else:
            # Standard flow: Send TCM type selection menu
            send_tcm_type_selection_menu(whatsapp_number, supabase, user_data)
        return False
   
    # ------------------------------------------------------------------
    # 3. TCM TYPE SELECTION
    # ------------------------------------------------------------------
    elif state == "TCM_TYPE_SELECTION" and message.get("type") == "interactive":
        list_id = message["interactive"]["list_reply"]["id"]
       
        if list_id == "back_button":
            # Return to services main menu
            user_data[whatsapp_number]["state"] = "SERVICES_MAIN_MENU"
            user_data[whatsapp_number]["module"] = "services_menu"
            from menu import send_services_main_menu
            send_services_main_menu(whatsapp_number, supabase)
            return False
       
        if list_id.startswith("tcm_type_"):
            tcm_type = list_id.replace("tcm_type_", "")
           
            logger.info(f"[TCM] TCM type selected: {tcm_type} for {whatsapp_number}")
           
            # Store TCM type in user_data
            user_data[whatsapp_number]["tcm_type"] = tcm_type
           
            # Now show clinics filtered by this type
            user_data[whatsapp_number]["state"] = "TCM_CLINIC_SELECTION"
            send_tcm_clinic_selection_menu(whatsapp_number, supabase, user_data)
            return False
   
    # ------------------------------------------------------------------
    # 4. TCM CLINIC SELECTION (filtered by service_type1) - UPDATED WITH TRUNCATION
    # ------------------------------------------------------------------
    elif state == "TCM_CLINIC_SELECTION" and message.get("type") == "interactive":
        list_id = message["interactive"]["list_reply"]["id"]
       
        if list_id == "back_button":
            # Return to type selection
            user_data[whatsapp_number]["state"] = "TCM_TYPE_SELECTION"
            send_tcm_type_selection_menu(whatsapp_number, supabase, user_data)
            return False
       
        if list_id.startswith("clinic_"):
            clinic_id = list_id.replace("clinic_", "")
           
            # Move to clinic info display state
            user_data[whatsapp_number]["state"] = "TCM_CLINIC_INFO_DISPLAY"
            display_clinic_info_and_proceed(whatsapp_number, supabase, user_data, clinic_id)
            return False
   
    # ------------------------------------------------------------------
    # 5. TCM CLINIC INFO DISPLAY (NEW STATE)
    # ------------------------------------------------------------------
    elif state == "TCM_CLINIC_INFO_DISPLAY":
        # This state is triggered after clinic selection to display clinic info
        # We don't expect user input here, just auto-proceed after displaying info
       
        # Check if we have already displayed the info
        if not user_data[whatsapp_number].get("clinic_info_displayed"):
            # Get clinic details including image_url
            clinic_id = user_data[whatsapp_number].get("clinic_id")
            clinic_response = supabase.table("tcm_a_clinics") \
                .select("id, name, address, phone_number, admin_email, service_type1, service_type2, service_type3, doctor_selection, image_url") \
                .eq("id", clinic_id) \
                .execute()
           
            if clinic_response.data:
                clinic = clinic_response.data[0]
                clinic_name = clinic["name"]  # Keep original name
                clinic_address = clinic.get("address", "")  # Keep original address
                clinic_image_url = clinic.get("image_url", "")
               
                # Store clinic details in user_data
                user_data[whatsapp_number]["clinic_name"] = clinic_name
                user_data[whatsapp_number]["clinic_address"] = clinic_address
                user_data[whatsapp_number]["clinic_image_url"] = clinic_image_url
               
                logger.info(f"[TCM] Clinic selected: {clinic_name} (ID: {clinic_id}) for {whatsapp_number}")
               
                # Display clinic image if available
                if clinic_image_url:
                    send_image_message(whatsapp_number, clinic_image_url, supabase)
                    time.sleep(1) # Small delay for better UX
               
                # Display clinic name and address
                clinic_info_text = f"📍 *{clinic_name}*\n\n"
                if clinic_address:
                    clinic_info_text += f"🏢 {translate_template(whatsapp_number, 'Address:', supabase)} {clinic_address}\n\n"
               
                clinic_info_text += translate_template(whatsapp_number, "Now please select a treatment category:", supabase)
               
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": clinic_info_text}},
                    supabase
                )
               
                # Mark as displayed
                user_data[whatsapp_number]["clinic_info_displayed"] = True
               
                # Small delay before showing category menu
                time.sleep(1)
               
                # Now show TCM service categories for this clinic
                user_data[whatsapp_number]["state"] = "TCM_CATEGORY_SELECTION"
                send_tcm_category_selection_menu(whatsapp_number, supabase, clinic_id)
           
            else:
                logger.error(f"[TCM] Clinic {clinic_id} not found for {whatsapp_number}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        "Clinic not found. Please select another clinic.",
                        supabase
                    )}},
                    supabase
                )
                # Return to clinic selection
                user_data[whatsapp_number]["state"] = "TCM_CLINIC_SELECTION"
                send_tcm_clinic_selection_menu(whatsapp_number, supabase, user_data)
       
        return False
   
    # ------------------------------------------------------------------
    # 6. TCM CATEGORY SELECTION
    # ------------------------------------------------------------------
    elif state == "TCM_CATEGORY_SELECTION" and message.get("type") == "interactive":
        list_id = message["interactive"]["list_reply"]["id"]
       
        if list_id == "back_button":
            # Clear the clinic info displayed flag
            user_data[whatsapp_number].pop("clinic_info_displayed", None)
           
            # Return to clinic selection
            user_data[whatsapp_number]["state"] = "TCM_CLINIC_SELECTION"
            send_tcm_clinic_selection_menu(whatsapp_number, supabase, user_data)
            return False
       
        if list_id.startswith("category_"):
            category_id = list_id.replace("category_", "")
           
            # Get category details
            category_response = supabase.table("tcm_a_clinic_cat").select("category, description, image_url").eq("id", category_id).execute()
            if category_response.data:
                category_name = category_response.data[0]["category"]
                category_desc = category_response.data[0].get("description", "")
                category_image = category_response.data[0].get("image_url", "")
            else:
                category_name = translate_template(whatsapp_number, "Selected Category", supabase)  # Hardcoded, use translate_template
                category_desc = ""
                category_image = ""
           
            logger.info(f"[TCM] Category selected: {category_name} (ID: {category_id}) for {whatsapp_number}")
           
            # Store category details
            user_data[whatsapp_number]["category_id"] = category_id
            user_data[whatsapp_number]["category_name"] = category_name
            user_data[whatsapp_number]["category_description"] = category_desc
            user_data[whatsapp_number]["category_image_url"] = category_image
           
            # Send category image if available
            if category_image:
                send_image_message(whatsapp_number, category_image, supabase)
                time.sleep(1)
           
            # Now show services for this category
            user_data[whatsapp_number]["state"] = "TCM_SERVICE_SELECTION"
            send_tcm_service_selection_menu(whatsapp_number, supabase, user_data)
            return False
   
    # ------------------------------------------------------------------
    # 7. TCM SERVICE SELECTION (UPDATED WITH METHOD CHECKING)
    # ------------------------------------------------------------------
    elif state == "TCM_SERVICE_SELECTION" and message.get("type") == "interactive":
        list_id = message["interactive"]["list_reply"]["id"]
       
        if list_id == "back_button":
            # Return to category selection
            user_data[whatsapp_number]["state"] = "TCM_CATEGORY_SELECTION"
            clinic_id = user_data[whatsapp_number].get("clinic_id")
            send_tcm_category_selection_menu(whatsapp_number, supabase, clinic_id)
            return False
       
        if list_id.startswith("service_"):
            service_id = list_id.replace("service_", "")
           
            # Get service details INCLUDING METHODS
            service_response = supabase.table("tcm_a_clinic_service") \
                .select("service_name, description, duration_minutes, brochure_image_url, doctor_id, reminder_duration, reminder_remark, method_1, method_2, method_3, method_4, method_5, method_6, method_7, method_8") \
                .eq("id", service_id) \
                .eq("is_active", True) \
                .execute()
           
            if not service_response.data:
                logger.error(f"[TCM] Service {service_id} not found or not active")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        "Error: Service not found. Please select another.",
                        supabase
                    )}},
                    supabase
                )
                send_tcm_service_selection_menu(whatsapp_number, supabase, user_data)
                return False
           
            service = service_response.data[0]
            service_name = service["service_name"]
            description = service.get("description", "")
            duration = service.get("duration_minutes", 30)
            brochure = service.get("brochure_image_url")
            doctor_id = service.get("doctor_id")
            reminder_duration = service.get("reminder_duration")
            reminder_remark = service.get("reminder_remark")
           
            logger.info(f"[TCM] Service selected: {service_name} (ID: {service_id}) for {whatsapp_number}")
           
            # Store service details
            user_data[whatsapp_number]["service_id"] = service_id
            user_data[whatsapp_number]["service_name"] = service_name  # Keep original name
            user_data[whatsapp_number]["service_description"] = description.strip()
            user_data[whatsapp_number]["duration_minutes"] = duration
            user_data[whatsapp_number]["brochure_image_url"] = brochure
            user_data[whatsapp_number]["reminder_duration"] = reminder_duration
            user_data[whatsapp_number]["reminder_remark"] = reminder_remark
           
            # Store doctor_id if assigned to service
            if doctor_id:
                user_data[whatsapp_number]["service_doctor_id"] = doctor_id
            
            # Send brochure image if available
            if brochure:
                send_image_message(whatsapp_number, brochure, supabase)
                time.sleep(1)
            
            # Send description separately
            if description.strip():
                truncated_desc = gt_tt(whatsapp_number, description.strip(), supabase)
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": truncated_desc}},
                    supabase
                )
                time.sleep(1)
            
            # Check for methods (method_1 to method_8)
            methods = []
            for i in range(1, 9):
                method_field = f"method_{i}"
                method_id = service.get(method_field)
                if method_id:
                    methods.append(method_id)
            
            logger.info(f"[TCM] Found {len(methods)} methods for service {service_id}: {methods}")
            
            if not methods:
                # No methods - proceed to original remark yes/no flow
                user_data[whatsapp_number]["state"] = "TCM_REMARK_YES_NO"
                user_data[whatsapp_number]["module"] = "tcm_service"
                user_data[whatsapp_number]["language"] = language
                
                # Ask for remarks (without desc since already sent)
                prompt = translate_template(
                    whatsapp_number,
                    "Do you have any remarks for {} ({} min)?", supabase
                ).format(service_name, duration)
               
                send_whatsapp_message(
                    whatsapp_number,
                    "interactive",
                    {
                        "interactive": {
                            "type": "button",
                            "body": {"text": prompt},
                            "action": {
                                "buttons": [
                                    {"type": "reply", "reply": {"id": "remark_yes", "title": translate_template(whatsapp_number, "Yes", supabase)}},
                                    {"type": "reply", "reply": {"id": "remark_no", "title": translate_template(whatsapp_number, "No", supabase)}}
                                ]
                            }
                        }
                    },
                    supabase
                )
            elif len(methods) == 1:
                # Only one method - automatically select it
                method_id = methods[0]
                set_method_and_proceed(whatsapp_number, user_id, supabase, user_data, method_id)
            else:
                # Multiple methods - let user choose
                # Fetch method details
                method_details = supabase.table("tcm_a_service_method") \
                    .select("id, method_name, description") \
                    .in_("id", methods) \
                    .execute().data
                
                if not method_details:
                    logger.error(f"[TCM] No method details found for method IDs: {methods}")
                    # Fallback to original flow
                    user_data[whatsapp_number]["state"] = "TCM_REMARK_YES_NO"
                    user_data[whatsapp_number]["module"] = "tcm_service"
                    user_data[whatsapp_number]["language"] = language
                    
                    # Ask for remarks
                    prompt = translate_template(
                        whatsapp_number,
                        "Do you have any remarks for {} ({} min)?", supabase
                    ).format(service_name, duration)
                   
                    send_whatsapp_message(
                        whatsapp_number,
                        "interactive",
                        {
                            "interactive": {
                                "type": "button",
                                "body": {"text": prompt},
                                "action": {
                                    "buttons": [
                                        {"type": "reply", "reply": {"id": "remark_yes", "title": translate_template(whatsapp_number, "Yes", supabase)}},
                                        {"type": "reply", "reply": {"id": "remark_no", "title": translate_template(whatsapp_number, "No", supabase)}}
                                    ]
                                }
                            }
                        },
                        supabase
                    )
                    return False
                
                # Prepare method selection rows
                rows = []
                for m in method_details:
                    display_name = gt_t_tt(whatsapp_number, m["method_name"], supabase)
                    display_desc = gt_dt_tt(whatsapp_number, m.get("description", ""), supabase)
                    rows.append({
                        "id": str(m["id"]),
                        "title": display_name[:21] + "..." if len(display_name) > 21 else display_name,
                        "description": display_desc[:50] + "..." if len(display_desc) > 50 else display_desc
                    })
                
                # Send method selection menu
                send_whatsapp_message(
                    whatsapp_number,
                    "interactive",
                    {
                        "interactive": {
                            "type": "list",
                            "body": {"text": translate_template(whatsapp_number, "Select an appointment method:", supabase)},
                            "action": {
                                "button": translate_template(whatsapp_number, "Choose Method", supabase),
                                "sections": [{
                                    "title": translate_template(whatsapp_number, "Available Methods", supabase),
                                    "rows": rows
                                }]
                            }
                        }
                    },
                    supabase
                )
                user_data[whatsapp_number]["state"] = "SELECT_METHOD"
           
            return False
   
    # ------------------------------------------------------------------
    # 8. METHOD SELECTION (NEW STATE)
    # ------------------------------------------------------------------
    elif state == "SELECT_METHOD" and message.get("type") == "interactive":
        method_id = message["interactive"]["list_reply"]["id"]
        set_method_and_proceed(whatsapp_number, user_id, supabase, user_data, method_id)
        return False
    
    # ------------------------------------------------------------------
    # 9. INPUT ADDRESS (NEW STATE)
    # ------------------------------------------------------------------
    elif state == "AWAITING_ADDRESS":
        if message.get("type") == "location":
            lat = message["location"]["latitude"]
            lon = message["location"]["longitude"]
            address = get_address_from_lat_lon(lat, lon)
            if address == 'Address not found':
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Unable to retrieve address from location. Please enter manually:", supabase)}},
                    supabase
                )
                # Stay in state
            else:
                user_data[whatsapp_number]["temp_address"] = address
                user_data[whatsapp_number]["state"] = "CONFIRM_ADDRESS"
                prompt = translate_template(whatsapp_number, "Is this address correct?\n{}", supabase).format(address)
                send_whatsapp_message(
                    whatsapp_number,
                    "interactive",
                    {
                        "interactive": {
                            "type": "button",
                            "body": {"text": prompt},
                            "action": {
                                "buttons": [
                                    {"type": "reply", "reply": {"id": "confirm_address", "title": translate_template(whatsapp_number, "Confirm", supabase)}},
                                    {"type": "reply", "reply": {"id": "edit_address", "title": translate_template(whatsapp_number, "Edit", supabase)}}
                                ]
                            }
                        }
                    },
                    supabase
                )
        elif message.get("type") == "text":
            address = message["text"]["body"].strip()
            if address:
                user_data[whatsapp_number]["address"] = address
                proceed_to_remark(whatsapp_number, supabase, user_data)
            else:
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Please enter a valid address:", supabase)}},
                    supabase
                )
        return False
    
    elif state == "CONFIRM_ADDRESS" and message.get("type") == "interactive":
        btn = message["interactive"]["button_reply"]["id"]
        if btn == "confirm_address":
            user_data[whatsapp_number]["address"] = user_data[whatsapp_number].pop("temp_address", "")
            proceed_to_remark(whatsapp_number, supabase, user_data)
        elif btn == "edit_address":
            address = user_data[whatsapp_number].pop("temp_address", "")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": address}},
                supabase
            )
            time.sleep(1)
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Please edit the address and send it back:", supabase)}},
                supabase
            )
            user_data[whatsapp_number]["state"] = "EDIT_ADDRESS"
        return False
    
    elif state == "EDIT_ADDRESS" and message.get("type") == "text":
        address = message["text"]["body"].strip()
        if address:
            user_data[whatsapp_number]["address"] = address
            proceed_to_remark(whatsapp_number, supabase, user_data)
        else:
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Please enter a valid address:", supabase)}},
                supabase
            )
        return False
   
    # ------------------------------------------------------------------
    # 10. REMARK YES/NO
    # ------------------------------------------------------------------
    elif state == "TCM_REMARK_YES_NO" and message.get("type") == "interactive":
        btn = message["interactive"]["button_reply"]["id"]
        if btn == "remark_yes":
            user_data[whatsapp_number]["state"] = "TCM_REMARK_INPUT"
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Please enter your remarks:", supabase)}},
                supabase
            )
        else:
            # No remark → store the service name as details
            user_data[whatsapp_number]["details"] = user_data[whatsapp_number]["service_name"]
            user_data[whatsapp_number]["state"] = "SELECT_DOCTOR"
            # Use the new function that checks doctor selection setting
            get_available_doctors_for_service(whatsapp_number, user_id, supabase, user_data, "tcm_service")
        return False
   
    # ------------------------------------------------------------------
    # 11. REMARK INPUT
    # ------------------------------------------------------------------
    elif state == "TCM_REMARK_INPUT" and message.get("type") == "text":
        remark = message["text"]["body"].strip()
        details = f"{user_data[whatsapp_number]['service_name']}: {remark}"
        user_data[whatsapp_number]["details"] = details
        user_data[whatsapp_number]["state"] = "SELECT_DOCTOR"
        # Use the new function that checks doctor selection setting
        get_available_doctors_for_service(whatsapp_number, user_id, supabase, user_data, "tcm_service")
        return False
   
    # ------------------------------------------------------------------
    # 12. CALENDAR FLOW (uses tcm_calendar_utils)
    # ------------------------------------------------------------------
    elif state == "SELECT_DOCTOR" and message.get("type") == "interactive":
        sel = message["interactive"]["list_reply"]["id"]
        if sel == "any_doctor":
            user_data[whatsapp_number]["any_doctor"] = True
            user_data[whatsapp_number]["doctor_id"] = None
        else:
            user_data[whatsapp_number]["doctor_id"] = sel
            user_data[whatsapp_number]["any_doctor"] = False
            
            # Get doctor name for display
            doctor_response = supabase.table("tcm_a_doctors").select("name").eq("id", sel).execute()
            if doctor_response.data:
                user_data[whatsapp_number]["doctor_name"] = doctor_response.data[0]["name"]  # Keep original name
       
        # Check if we have a date already (from future date input)
        if user_data[whatsapp_number].get("date"):
            # If we have a date from future date input, go directly to period selection
            user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
            select_period(whatsapp_number, user_id, supabase, user_data, "tcm_service")
        else:
            # Otherwise go to calendar
            user_data[whatsapp_number]["state"] = "SELECT_DATE"
            get_calendar(whatsapp_number, user_id, supabase, user_data, "tcm_service")
        return False
   
    elif state == "SELECT_DATE" and message.get("type") == "interactive":
        selected_date = message["interactive"]["list_reply"]["id"]
       
        if selected_date == "future_date":
            user_data[whatsapp_number]["state"] = "AWAITING_FUTURE_DATE"
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "Please enter your preferred date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:",
                    supabase
                )}},
                supabase
            )
        else:
            user_data[whatsapp_number]["date"] = selected_date
            
            # Check if priority is required
            priority_required = user_data[whatsapp_number].get("priority_required", True)
            
            if priority_required:
                # Priority is true - proceed to time input
                clinic_id = user_data[whatsapp_number].get("clinic_id")
                doctor_selection_enabled = get_clinic_doctor_selection(supabase, clinic_id)
                if doctor_selection_enabled:
                    user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(
                            whatsapp_number,
                            "Please enter your preferred time (e.g., 9:30, 2pm, 1430):",
                            supabase
                        )}},
                        supabase
                    )
                else:
                    # Doctor selection disabled - go to period selection
                    user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
                    select_period(whatsapp_number, user_id, supabase, user_data, "tcm_service")
            else:
                # Priority is false - skip time selection, set time_slot to None
                user_data[whatsapp_number]["time_slot"] = None
                # Go directly to doctor confirmation (which will handle non-priority case)
                get_available_doctors(whatsapp_number, user_id, supabase, user_data, "tcm_service")
        return False
   
    elif state == "AWAITING_FUTURE_DATE" and message.get("type") == "text":
        date_input = message["text"]["body"].strip()
        handle_future_date_input(whatsapp_number, user_id, supabase, user_data, "tcm_service", date_input)
        return False
   
    elif state == "CONFIRM_FUTURE_DATE" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        if button_id == "confirm_future_date":
            date_obj = user_data[whatsapp_number].get("future_date_input")
            if date_obj:
                user_data[whatsapp_number]["date"] = date_obj.strftime("%Y-%m-%d")
                user_data[whatsapp_number].pop("future_date_input", None)
                
                # Check if priority is required
                priority_required = user_data[whatsapp_number].get("priority_required", True)
                
                if priority_required:
                    # Priority is true - proceed to time input
                    user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(
                            whatsapp_number,
                            "Please enter your preferred time (e.g., 9:30, 2pm, 1430):",
                            supabase
                        )}},
                        supabase
                    )
                else:
                    # Priority is false - skip time selection, set time_slot to None
                    user_data[whatsapp_number]["time_slot"] = None
                    # Go directly to doctor confirmation (which will handle non-priority case)
                    get_available_doctors(whatsapp_number, user_id, supabase, user_data, "tcm_service")
        elif button_id == "reject_future_date":
            handle_future_date_confirmation(whatsapp_number, user_id, supabase, user_data, "tcm_service", confirmed=False)
        return False
   
    # ------------------------------------------------------------------
    # TIME INPUT FLOW (NEW - like checkup flow)
    # ------------------------------------------------------------------
    elif state == "AWAITING_TIME_INPUT" and message.get("type") == "text":
        time_input = message["text"]["body"].strip()
        handle_time_input(whatsapp_number, user_id, supabase, user_data, "tcm_service", time_input)
        return False
   
    elif state == "CONFIRM_TIME" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        if button_id == "confirm_time":
            handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, "tcm_service", confirmed=True, use_closest=False)
        elif button_id == "find_another_time":
            # User wants to find another time - go to AM/PM selection
            user_data[whatsapp_number].pop("parsed_time_input", None)
            user_data[whatsapp_number].pop("closest_available_time", None)
            user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
            select_period(whatsapp_number, user_id, supabase, user_data, "tcm_service")
        return False
   
    elif state == "CONFIRM_CLOSEST_TIME" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        if button_id == "accept_closest_time":
            handle_time_confirmation(whatsapp_number, user_id, supabase, user_data, "tcm_service", confirmed=True, use_closest=True)
        elif button_id == "find_another_time":
            # User wants to find another time - go to AM/PM selection
            user_data[whatsapp_number].pop("parsed_time_input", None)
            user_data[whatsapp_number].pop("closest_available_time", None)
            user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
            select_period(whatsapp_number, user_id, supabase, user_data, "tcm_service")
        return False
   
    elif state == "RETRY_TIME_OR_HELP" and message.get("type") == "interactive":
        button_id = message["interactive"]["button_reply"]["id"]
        if button_id == "try_again_time":
            # User wants to try entering time again
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "Please enter your preferred time (e.g., 9:30, 2pm, 1430):",
                    supabase
                )}}
            )
            user_data[whatsapp_number]["state"] = "AWAITING_TIME_INPUT"
        elif button_id == "help_choose_time":
            # User wants help choosing - go to AM/PM selection
            user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
            select_period(whatsapp_number, user_id, supabase, user_data, "tcm_service")
        return False
   
    # ------------------------------------------------------------------
    # FALLBACK PERIOD SELECTION (when user chooses "Help Me Choose" or "Find Another")
    # ------------------------------------------------------------------
    elif state == "SELECT_PERIOD" and message.get("type") == "interactive":
        user_data[whatsapp_number]["period"] = message["interactive"]["button_reply"]["id"]
        user_data[whatsapp_number]["state"] = "SELECT_HOUR"
        get_available_hours(whatsapp_number, user_id, supabase, user_data, "tcm_service")
        return False
   
    elif state == "SELECT_HOUR" and message.get("type") == "interactive":
        user_data[whatsapp_number]["hour"] = message["interactive"]["list_reply"]["id"]
        user_data[whatsapp_number]["state"] = "SELECT_TIME_SLOT"
        get_time_slots(whatsapp_number, user_id, supabase, user_data, "tcm_service")
        return False
   
    elif state == "SELECT_TIME_SLOT" and message.get("type") == "interactive":
        user_data[whatsapp_number]["time_slot"] = message["interactive"]["list_reply"]["id"]
        get_available_doctors(whatsapp_number, user_id, supabase, user_data, "tcm_service")
        return False
   
    # ------------------------------------------------------------------
    # 13. CONFIRM BOOKING - Save to tcm_s_bookings
    # ------------------------------------------------------------------
    elif state == "CONFIRM_BOOKING" and message.get("type") == "interactive":
        btn = message["interactive"]["button_reply"]["id"]
        if btn == "confirm_booking":
            return handle_confirm_booking_tcm(whatsapp_number, user_id, supabase, user_data, "tcm_service")
        elif btn == "edit_booking":
            # Show edit options
            show_edit_options(whatsapp_number, user_id, supabase, user_data, "tcm_service")
            return False
        elif btn == "cancel_booking":
            return handle_cancel_booking_tcm(whatsapp_number, user_id, supabase, user_data)
   
    # ------------------------------------------------------------------
    # 14. EDIT BOOKING FLOW
    # ------------------------------------------------------------------
    elif state == "EDIT_BOOKING" and message.get("type") == "interactive":
        edit_choice = message["interactive"]["list_reply"]["id"]
        handle_edit_choice(whatsapp_number, user_id, supabase, user_data, "tcm_service", edit_choice)
        return False
   
    # ------------------------------------------------------------------
    # 15. FALLBACK
    # ------------------------------------------------------------------
    else:
        current_state = user_data[whatsapp_number].get("state")
       
        # Handle text input states
        if current_state in ["AWAITING_FUTURE_DATE", "TCM_REMARK_INPUT", "AWAITING_TIME_INPUT", "AWAITING_ADDRESS", "EDIT_ADDRESS"]:
            if current_state == "AWAITING_FUTURE_DATE":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        "Please enter your preferred date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:",
                        supabase
                    )}},
                    supabase
                )
            elif current_state == "TCM_REMARK_INPUT":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Please enter your remarks:", supabase)}},
                    supabase
                )
            elif current_state == "AWAITING_TIME_INPUT":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        "Please enter your preferred time (e.g., 9:30, 2pm, 1430):",
                        supabase
                    )}},
                    supabase
                )
            elif current_state == "AWAITING_ADDRESS":
                send_whatsapp_message(
                    whatsapp_number,
                    "interactive",
                    {
                        "interactive": {
                            "type": "location_request_message",
                            "body": {"text": translate_template(whatsapp_number, "Please share your current location or enter your address manually:", supabase)},
                            "action": {"name": "send_location"}
                        }
                    },
                    supabase
                )
            elif current_state == "EDIT_ADDRESS":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Please edit the address and send it back:", supabase)}},
                    supabase
                )
        elif current_state == "CONFIRM_ADDRESS":
            address = user_data[whatsapp_number].get("temp_address", "")
            if address:
                prompt = translate_template(whatsapp_number, "Is this address correct?\n{}", supabase).format(address)
                send_whatsapp_message(
                    whatsapp_number,
                    "interactive",
                    {
                        "interactive": {
                            "type": "button",
                            "body": {"text": prompt},
                            "action": {
                                "buttons": [
                                    {"type": "reply", "reply": {"id": "confirm_address", "title": translate_template(whatsapp_number, "Confirm", supabase)}},
                                    {"type": "reply", "reply": {"id": "edit_address", "title": translate_template(whatsapp_number, "Edit", supabase)}}
                                ]
                            }
                        }
                    },
                    supabase
                )
            else:
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Please enter your address:", supabase)}},
                    supabase
                )
                user_data[whatsapp_number]["state"] = "AWAITING_ADDRESS"
        elif current_state == "TCM_CLINIC_INFO_DISPLAY":
            # If we're in clinic info display state but haven't displayed yet, display it
            if not user_data[whatsapp_number].get("clinic_info_displayed"):
                clinic_id = user_data[whatsapp_number].get("clinic_id")
                if clinic_id:
                    display_clinic_info_and_proceed(whatsapp_number, supabase, user_data, clinic_id)
                else:
                    # Go back to clinic selection
                    user_data[whatsapp_number]["state"] = "TCM_CLINIC_SELECTION"
                    send_tcm_clinic_selection_menu(whatsapp_number, supabase, user_data)
        else:
            # Handle interactive menu states
            if current_state in ["TCM_TYPE_SELECTION", "TCM_CLINIC_SELECTION",
                                 "TCM_CATEGORY_SELECTION", "TCM_SERVICE_SELECTION",
                                 "SELECT_METHOD"]:
                # Re-send the appropriate menu
                if current_state == "TCM_TYPE_SELECTION":
                    send_tcm_type_selection_menu(whatsapp_number, supabase, user_data)
                elif current_state == "TCM_CLINIC_SELECTION":
                    send_tcm_clinic_selection_menu(whatsapp_number, supabase, user_data)
                elif current_state == "TCM_CATEGORY_SELECTION":
                    clinic_id = user_data[whatsapp_number].get("clinic_id")
                    if clinic_id:
                        send_tcm_category_selection_menu(whatsapp_number, supabase, clinic_id)
                    else:
                        send_tcm_clinic_selection_menu(whatsapp_number, supabase, user_data)
                elif current_state == "TCM_SERVICE_SELECTION":
                    send_tcm_service_selection_menu(whatsapp_number, supabase, user_data)
                elif current_state == "SELECT_METHOD":
                    # Re-fetch methods and show selection
                    service_id = user_data[whatsapp_number].get("service_id")
                    if service_id:
                        # Get service methods
                        service_response = supabase.table("tcm_a_clinic_service") \
                            .select("method_1, method_2, method_3, method_4, method_5, method_6, method_7, method_8") \
                            .eq("id", service_id) \
                            .single() \
                            .execute()
                        
                        if service_response.data:
                            service = service_response.data
                            methods = []
                            for i in range(1, 9):
                                method_field = f"method_{i}"
                                method_id = service.get(method_field)
                                if method_id:
                                    methods.append(method_id)
                            
                            if methods:
                                # Fetch method details
                                method_details = supabase.table("tcm_a_service_method") \
                                    .select("id, method_name, description") \
                                    .in_("id", methods) \
                                    .execute().data
                                
                                if method_details:
                                    # Prepare method selection rows
                                    rows = []
                                    for m in method_details:
                                        display_name = gt_t_tt(whatsapp_number, m["method_name"], supabase)
                                        display_desc = gt_dt_tt(whatsapp_number, m.get("description", ""), supabase)
                                        rows.append({
                                            "id": str(m["id"]),
                                            "title": display_name[:21] + "..." if len(display_name) > 21 else display_name,
                                            "description": display_desc[:50] + "..." if len(display_desc) > 50 else display_desc
                                        })
                                    
                                    # Send method selection menu
                                    send_whatsapp_message(
                                        whatsapp_number,
                                        "interactive",
                                        {
                                            "interactive": {
                                                "type": "list",
                                                "body": {"text": translate_template(whatsapp_number, "Select an appointment method:", supabase)},
                                                "action": {
                                                    "button": translate_template(whatsapp_number, "Choose Method", supabase),
                                                    "sections": [{
                                                        "title": translate_template(whatsapp_number, "Available Methods", supabase),
                                                        "rows": rows
                                                    }]
                                                }
                                            }
                                        },
                                        supabase
                                    )
                                    return False
                    
                    # Fallback to service selection
                    user_data[whatsapp_number]["state"] = "TCM_SERVICE_SELECTION"
                    send_tcm_service_selection_menu(whatsapp_number, supabase, user_data)
            elif current_state == "SELECT_DOCTOR":
                get_available_doctors_for_service(whatsapp_number, user_id, supabase, user_data, "tcm_service")
            elif current_state == "SELECT_DATE":
                get_calendar(whatsapp_number, user_id, supabase, user_data, "tcm_service")
            elif current_state in ["SELECT_PERIOD", "SELECT_HOUR", "SELECT_TIME_SLOT"]:
                # Go back to calendar if user is stuck
                get_calendar(whatsapp_number, user_id, supabase, user_data, "tcm_service")
            else:
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Invalid input. Please use the buttons provided.", supabase)}},
                    supabase
                )
       
        return False
    return False

def display_clinic_info_and_proceed(whatsapp_number, supabase, user_data, clinic_id):
    """Display clinic information and proceed to category selection."""
    try:
        # Fetch clinic details
        clinic_response = supabase.table("tcm_a_clinics") \
            .select("id, name, address, phone_number, admin_email, service_type1, service_type2, service_type3, doctor_selection, image_url") \
            .eq("id", clinic_id) \
            .execute()
       
        if not clinic_response.data:
            logger.error(f"[TCM] Clinic {clinic_id} not found for {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "Clinic not found. Please select another clinic.",
                    supabase
                )}},
                supabase
            )
            # Return to clinic selection
            user_data[whatsapp_number]["state"] = "TCM_CLINIC_SELECTION"
            send_tcm_clinic_selection_menu(whatsapp_number, supabase, user_data)
            return
       
        clinic = clinic_response.data[0]
        clinic_name = clinic["name"]  # Keep original name
        clinic_address = clinic.get("address", "")  # Keep original address
        clinic_image_url = clinic.get("image_url", "")
       
        # Store clinic details in user_data
        user_data[whatsapp_number]["clinic_id"] = clinic_id
        user_data[whatsapp_number]["clinic_name"] = clinic_name
        user_data[whatsapp_number]["clinic_address"] = clinic_address
        user_data[whatsapp_number]["clinic_image_url"] = clinic_image_url
       
        logger.info(f"[TCM] Clinic selected: {clinic_name} (ID: {clinic_id}) for {whatsapp_number}")
       
        # Display clinic image if available
        if clinic_image_url:
            send_image_message(whatsapp_number, clinic_image_url, supabase)
            time.sleep(1) # Small delay for better UX
       
        # Display clinic name and address
        clinic_info_text = f"📍 *{clinic_name}*\n\n"
        if clinic_address:
            clinic_info_text += f"🏢 {translate_template(whatsapp_number, 'Address:', supabase)} {clinic_address}\n\n"
       
        clinic_info_text += translate_template(whatsapp_number, "Now please select a treatment category:", supabase)
       
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": clinic_info_text}},
            supabase
        )
       
        # Mark as displayed
        user_data[whatsapp_number]["clinic_info_displayed"] = True
       
        # Small delay before showing category menu
        time.sleep(1)
       
        # Now show TCM service categories for this clinic
        user_data[whatsapp_number]["state"] = "TCM_CATEGORY_SELECTION"
        send_tcm_category_selection_menu(whatsapp_number, supabase, clinic_id)
       
    except Exception as e:
        logger.error(f"[TCM] Error displaying clinic info: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Unable to load clinic information. Please try again.", supabase)}}
        )
        # Return to clinic selection
        user_data[whatsapp_number]["state"] = "TCM_CLINIC_SELECTION"
        send_tcm_clinic_selection_menu(whatsapp_number, supabase, user_data)

def send_tcm_type_selection_menu(whatsapp_number, supabase, user_data):
    """Send TCM type selection menu (Chiro or Physio)."""
    try:
        # Prepare type rows
        rows = [
            {
                "id": "tcm_type_chiro",
                "title": translate_template(whatsapp_number, "Chiropractic", supabase), # Already using translate_template
                "description": translate_template(whatsapp_number, "Spinal adjustments, posture correction", supabase) # Already using translate_template
            },
            {
                "id": "tcm_type_physio",
                "title": translate_template(whatsapp_number, "Physiotherapy", supabase), # Already using translate_template
                "description": translate_template(whatsapp_number, "Muscle therapy, joint mobilization", supabase) # Already using translate_template
            }
        ]
       
        # Add back button
        rows.append({
            "id": "back_button",
            "title": translate_template(whatsapp_number, "🔙 Back to Services", supabase) # Already using translate_template
        })
       
        # Update user state
        user_data[whatsapp_number]["state"] = "TCM_TYPE_SELECTION"
        user_data[whatsapp_number]["module"] = "tcm_service"
       
        # Send interactive menu
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "🌿 TCM Services", supabase) # Already using translate_template
                },
                "body": {
                    "text": translate_template(whatsapp_number, "Please select the type of TCM service you need:", supabase) # Already using translate_template
                },
                "footer": {
                    "text": translate_template(whatsapp_number, "Choose a service type to proceed", supabase) # Already using translate_template
                },
                "action": {
                    "button": translate_template(whatsapp_number, "Select Type", supabase), # Already using translate_template
                    "sections": [{
                        "title": translate_template(whatsapp_number, "TCM Service Types", supabase), # Already using translate_template
                        "rows": rows
                    }]
                }
            }
        }
       
        return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
       
    except Exception as e:
        logger.error(f"[TCM] Error sending type selection menu: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Unable to load TCM services. Please try again.", supabase)}}
        )
        return False

def send_tcm_clinic_selection_menu(whatsapp_number, supabase, user_data):
    """Send TCM clinic selection menu filtered by service_type1 with truncated names and addresses."""
    try:
        # Get selected TCM type
        tcm_type = user_data[whatsapp_number].get("tcm_type")
       
        if not tcm_type:
            logger.error(f"[TCM] No TCM type selected for {whatsapp_number}")
            # Fallback: show type selection again
            user_data[whatsapp_number]["state"] = "TCM_TYPE_SELECTION"
            send_tcm_type_selection_menu(whatsapp_number, supabase, user_data)
            return False
       
        # Clear the clinic info displayed flag when returning to clinic selection
        user_data[whatsapp_number].pop("clinic_info_displayed", None)
       
        # Fetch TCM clinics with addresses, filtered by service_type1
        clinics = supabase.table("tcm_a_clinics") \
            .select("id, name, address, service_type1") \
            .eq("service_type1", tcm_type) \
            .execute()
       
        if not clinics.data:
            logger.warning(f"[TCM] No {tcm_type} clinics found for {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    f"No {tcm_type} clinics available at the moment. Please select another service type.",
                    supabase
                )}}
            )
            # Return to type selection
            user_data[whatsapp_number]["state"] = "TCM_TYPE_SELECTION"
            send_tcm_type_selection_menu(whatsapp_number, supabase, user_data)
            return False
       
        # Prepare clinic rows with truncated names and addresses
        rows = []
        for clinic in clinics.data[:8]: # WhatsApp allows max 8 rows
            clinic_name = clinic["name"]  # Keep original name
            address = clinic.get("address", "")  # Keep original address
           
            # Truncate clinic name for button title (max 24 chars, truncate to 21 + ...)
            truncated_name = truncate_text(clinic_name, 24, suffix="...")
            display_name = truncated_name  # Keep original name (no translation)
           
            # Truncate address for description (max 72 chars, truncate to 69 + ...)
            # WhatsApp list description has 72 char limit, but let's use 60 for safety
            truncated_address = truncate_text(address, 60, suffix="...")
            display_address = truncated_address if truncated_address else ""  # Keep original address (no translation)
           
            rows.append({
                "id": f"clinic_{clinic['id']}",
                "title": display_name,
                "description": display_address
            })
       
        # Add back button
        rows.append({
            "id": "back_button",
            "title": translate_template(whatsapp_number, "🔙 Back to Type Selection", supabase) # Already using translate_template
        })
       
        # Send interactive menu
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "🌿 TCM Services", supabase) # Already using translate_template
                },
                "body": {
                    "text": translate_template(whatsapp_number, "Please select a {} clinic:", supabase).format(tcm_type) # Already using translate_template
                },
                "footer": {
                    "text": translate_template(whatsapp_number, "Choose a clinic to proceed", supabase) # Already using translate_template
                },
                "action": {
                    "button": translate_template(whatsapp_number, "Select Clinic", supabase), # Already using translate_template
                    "sections": [{
                        "title": translate_template(whatsapp_number, "Available {} Clinics", supabase).format(tcm_type.capitalize()), # Already using translate_template
                        "rows": rows
                    }]
                }
            }
        }
       
        return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
       
    except Exception as e:
        logger.error(f"[TCM] Error sending clinic selection menu: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Unable to load TCM clinics. Please try again.", supabase)}}
        )
        return False

def send_tcm_category_selection_menu(whatsapp_number, supabase, clinic_id):
    """Send TCM category selection menu for selected clinic."""
    try:
        # Fetch categories for this clinic
        categories = supabase.table("tcm_a_clinic_cat") \
            .select("id, category, description, image_url") \
            .eq("clinic_id", clinic_id) \
            .order("rank") \
            .execute()
       
        if not categories.data:
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "No categories available for this clinic. Please select another clinic.",
                    supabase
                )}}
            )
            return False
       
        # Prepare category rows
        rows = []
        for category in categories.data[:8]: # WhatsApp allows max 8 rows
            category_name = category["category"]
            description = category.get("description", "")
            display_name = gt_t_tt(whatsapp_number, category_name, supabase) # Use gt_t_tt for dynamic category names
            display_desc = gt_dt_tt(whatsapp_number, description, supabase) if description else "" # Use gt_dt_tt for dynamic descriptions
           
            rows.append({
                "id": f"category_{category['id']}",
                "title": display_name,
                "description": display_desc
            })
       
        # Add back button
        rows.append({
            "id": "back_button",
            "title": translate_template(whatsapp_number, "🔙 Back to Clinics", supabase) # Already using translate_template
        })
       
        # Send interactive menu
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "🌿 TCM Services", supabase) # Already using translate_template
                },
                "body": {
                    "text": translate_template(whatsapp_number, "Please select a treatment category:", supabase) # Already using translate_template
                },
                "footer": {
                    "text": translate_template(whatsapp_number, "Choose a category to proceed", supabase) # Already using translate_template
                },
                "action": {
                    "button": translate_template(whatsapp_number, "Select Category", supabase), # Already using translate_template
                    "sections": [{
                        "title": translate_template(whatsapp_number, "Treatment Categories", supabase), # Already using translate_template
                        "rows": rows
                    }]
                }
            }
        }
       
        return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
       
    except Exception as e:
        logger.error(f"[TCM] Error sending category selection menu: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Unable to load categories. Please try again.", supabase)}}
        )
        return False

def send_tcm_service_selection_menu(whatsapp_number, supabase, user_data):
    """Send TCM service selection menu for selected category."""
    try:
        clinic_id = user_data[whatsapp_number].get("clinic_id")
        category_id = user_data[whatsapp_number].get("category_id")
       
        if not clinic_id or not category_id:
            logger.error(f"[TCM] Missing clinic_id or category_id for {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "Error: Clinic or category not selected. Please start over.",
                    supabase
                )}}
            )
            user_data[whatsapp_number]["state"] = "IDLE"
            user_data[whatsapp_number]["module"] = None
            send_interactive_menu(whatsapp_number, supabase)
            return False
       
        # Fetch services for this clinic and category
        services = supabase.table("tcm_a_clinic_service") \
            .select("id, service_name, description, duration_minutes, brochure_image_url") \
            .eq("clinic_id", clinic_id) \
            .eq("cat_id", category_id) \
            .eq("is_active", True) \
            .order("rank") \
            .execute()
       
        if not services.data:
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "No services available in this category. Please select another category.",
                    supabase
                )}}
            )
            user_data[whatsapp_number]["state"] = "TCM_CATEGORY_SELECTION"
            send_tcm_category_selection_menu(whatsapp_number, supabase, clinic_id)
            return False
       
        # Prepare service rows
        rows = []
        for service in services.data[:8]: # WhatsApp allows max 8 rows
            service_name = service["service_name"]
            description = service.get("description", "")
            duration = service.get("duration_minutes", 30)
            display_name = gt_t_tt(whatsapp_number, service_name, supabase) # Use gt_t_tt for dynamic service names
            display_desc = gt_dt_tt(whatsapp_number, description, supabase) if description else "" # Use gt_dt_tt for dynamic descriptions
            display_duration = gt_tt(whatsapp_number, f"{duration} min", supabase) # Use gt_tt for dynamic duration
           
            rows.append({
                "id": f"service_{service['id']}",
                "title": display_name,
                "description": f"{display_desc} ({display_duration})"
            })
       
        # Add back button
        rows.append({
            "id": "back_button",
            "title": translate_template(whatsapp_number, "🔙 Back to Categories", supabase) # Already using translate_template
        })
       
        # Send interactive menu
        content = {
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": translate_template(whatsapp_number, "🌿 TCM Services", supabase) # Already using translate_template
                },
                "body": {
                    "text": translate_template(whatsapp_number, "Please select a treatment service:", supabase) # Already using translate_template
                },
                "footer": {
                    "text": translate_template(whatsapp_number, "Choose a service to proceed", supabase) # Already using translate_template
                },
                "action": {
                    "button": translate_template(whatsapp_number, "Select Service", supabase), # Already using translate_template
                    "sections": [{
                        "title": translate_template(whatsapp_number, "Available Services", supabase), # Already using translate_template
                        "rows": rows
                    }]
                }
            }
        }
       
        return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
       
    except Exception as e:
        logger.error(f"[TCM] Error sending service selection menu: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Unable to load services. Please try again.", supabase)}}
        )
        return False