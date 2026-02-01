import logging
import time
from datetime import datetime
from utils import (
    send_whatsapp_message,
    translate_template,
    gt_t_tt,
    gt_tt,
    gt_dt_tt
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# WhatsApp character limits
MAX_TITLE_LENGTH = 24
MAX_BUTTON_TEXT = 20
MAX_HEADER_TEXT = 60
MAX_BODY_TEXT = 1024
MAX_MESSAGE_LENGTH = 4000  # WhatsApp limit with buffer

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

def format_medication_details(whatsapp_number, med, supabase):
    """Format medication details for display."""
    try:
        details_parts = []
        
        if med.get("quantity"):
            quantity_label = translate_template(whatsapp_number, "Quantity:", supabase)
            details_parts.append(f"{quantity_label} {med['quantity']}")
        
        if med.get("times_per_day") and med.get("pills_per_time"):
            dosage_label = translate_template(whatsapp_number, "Dosage:", supabase)
            dosage = gt_tt(whatsapp_number, f"{med['pills_per_time']} pill{'s' if med['pills_per_time'] > 1 else ''}, {med['times_per_day']} time{'s' if med['times_per_day'] > 1 else ''}/day", supabase)
            details_parts.append(f"{dosage_label} {dosage}")
        
        if med.get("usage_method"):
            method_label = translate_template(whatsapp_number, "Method:", supabase)
            usage = gt_tt(whatsapp_number, med["usage_method"].capitalize(), supabase)
            details_parts.append(f"{method_label} {usage}")
        
        if med.get("meal_timing"):
            take_label = translate_template(whatsapp_number, "Take:", supabase)
            meal_timing_map = {
                "before": translate_template(whatsapp_number, "before meal", supabase),
                "after": translate_template(whatsapp_number, "after meal", supabase),
                "with": translate_template(whatsapp_number, "with meal", supabase),
                "empty": translate_template(whatsapp_number, "on empty stomach", supabase)
            }
            timing = meal_timing_map.get(med["meal_timing"], gt_tt(whatsapp_number, med["meal_timing"], supabase))
            details_parts.append(f"{take_label} {timing}")
        
        if med.get("purpose"):
            purpose_label = translate_template(whatsapp_number, "Purpose:", supabase)
            # Purpose is dynamic content from database, use gt_tt
            purpose = gt_tt(whatsapp_number, med["purpose"], supabase)
            details_parts.append(f"{purpose_label} {purpose}")
        
        if med.get("remark"):
            note_label = translate_template(whatsapp_number, "Note:", supabase)
            # Remark is dynamic content from database, use gt_tt
            note = gt_tt(whatsapp_number, med["remark"], supabase)
            details_parts.append(f"{note_label} {note}")
        
        return "\n".join(details_parts)
    
    except Exception as e:
        logger.error(f"Error formatting medication details: {e}")
        return translate_template(whatsapp_number, "No details available", supabase)

def format_equipment_details(whatsapp_number, equipment, supabase):
    """Format equipment details for display."""
    try:
        details_parts = []
        
        if equipment.get("number_of_days"):
            duration_label = translate_template(whatsapp_number, "Duration:", supabase)
            days = int(equipment["number_of_days"])
            duration = gt_tt(whatsapp_number, f"{days} day{'s' if days > 1 else ''}", supabase)
            details_parts.append(f"{duration_label} {duration}")
        
        if equipment.get("quantity"):
            quantity_label = translate_template(whatsapp_number, "Quantity:", supabase)
            quantity = int(equipment["quantity"])
            details_parts.append(f"{quantity_label} {quantity}")
        
        if equipment.get("frequency"):
            frequency_label = translate_template(whatsapp_number, "Frequency:", supabase)
            freq = int(equipment["frequency"])
            frequency = gt_tt(whatsapp_number, f"{freq} time{'s' if freq > 1 else ''}", supabase)
            details_parts.append(f"{frequency_label} {frequency}")
        
        if equipment.get("purpose"):
            purpose_label = translate_template(whatsapp_number, "Purpose:", supabase)
            # Purpose is dynamic content from database, use gt_tt
            purpose = gt_tt(whatsapp_number, equipment["purpose"], supabase)
            details_parts.append(f"{purpose_label} {purpose}")
        
        if equipment.get("remark"):
            note_label = translate_template(whatsapp_number, "Note:", supabase)
            # Remark is dynamic content from database, use gt_tt
            note = gt_tt(whatsapp_number, equipment["remark"], supabase)
            details_parts.append(f"{note_label} {note}")
        
        return "\n".join(details_parts)
    
    except Exception as e:
        logger.error(f"Error formatting equipment details: {e}")
        return translate_template(whatsapp_number, "No details available", supabase)

def format_product_details(whatsapp_number, product, supabase):
    """Format product details for display."""
    try:
        details_parts = []
        
        if product.get("number_of_days"):
            duration_label = translate_template(whatsapp_number, "Duration:", supabase)
            days = int(product["number_of_days"])
            duration = gt_tt(whatsapp_number, f"{days} day{'s' if days > 1 else ''}", supabase)
            details_parts.append(f"{duration_label} {duration}")
        
        if product.get("quantity"):
            quantity_label = translate_template(whatsapp_number, "Quantity:", supabase)
            quantity = int(product["quantity"])
            details_parts.append(f"{quantity_label} {quantity}")
        
        if product.get("frequency"):
            frequency_label = translate_template(whatsapp_number, "Frequency:", supabase)
            freq = int(product["frequency"])
            frequency = gt_tt(whatsapp_number, f"{freq} time{'s' if freq > 1 else ''}", supabase)
            details_parts.append(f"{frequency_label} {frequency}")
        
        if product.get("purpose"):
            purpose_label = translate_template(whatsapp_number, "Purpose:", supabase)
            # Purpose is dynamic content from database, use gt_tt
            purpose = gt_tt(whatsapp_number, product["purpose"], supabase)
            details_parts.append(f"{purpose_label} {purpose}")
        
        if product.get("remark"):
            note_label = translate_template(whatsapp_number, "Note:", supabase)
            # Remark is dynamic content from database, use gt_tt
            note = gt_tt(whatsapp_number, product["remark"], supabase)
            details_parts.append(f"{note_label} {note}")
        
        return "\n".join(details_parts)
    
    except Exception as e:
        logger.error(f"Error formatting product details: {e}")
        return translate_template(whatsapp_number, "No details available", supabase)

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
        
        # Parse the datetime string
        dt = datetime.fromisoformat(visit_datetime_str.replace('Z', '+00:00'))
        
        # Format as: DD/MM/YYYY
        return dt.strftime("%d/%m/%Y")
    except Exception as e:
        logger.error(f"Error formatting date: {e}")
        return visit_datetime_str[:10] if visit_datetime_str else "Invalid date"

def split_message_if_needed(message_parts):
    """Split message into multiple parts if too long for WhatsApp."""
    full_message = "\n".join(message_parts)
    
    if len(full_message) > MAX_MESSAGE_LENGTH:
        messages = []
        current_message = []
        current_length = 0
        
        for part in message_parts:
            part_length = len(part) + 1  # +1 for newline
            
            if current_length + part_length > MAX_MESSAGE_LENGTH:
                messages.append("\n".join(current_message))
                current_message = [part]
                current_length = part_length
            else:
                current_message.append(part)
                current_length += part_length
        
        if current_message:
            messages.append("\n".join(current_message))
        
        return messages
    
    return [full_message]

def send_split_messages(whatsapp_number, messages, supabase):
    """Send multiple messages with delay between them."""
    for i, msg in enumerate(messages):
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": msg}},
            supabase
        )
        if i < len(messages) - 1:  # Don't wait after last message
            time.sleep(1)

def handle_patient_all_medications(whatsapp_number, user_id, supabase, user_data):
    """Show ALL medications, equipment, and products for the patient across all visits."""
    try:
        # Get patient data from individual module
        ind_data = user_data[whatsapp_number].get("individual_data", {})
        patient_id = ind_data.get("selected_patient_id")
        patient_name = ind_data.get("selected_patient_name", "Patient")
        
        if not patient_id:
            logger.error("No patient_id found in user_data")
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": translate_template(whatsapp_number, 
                    "Patient information not found. Please select a patient first.", supabase)}},
                supabase
            )
            return False
        
        logger.info(f"Getting all medications for patient_id: {patient_id}")
        
        # Step 1: Get all visits for this patient
        vh_response = supabase.table("actual_visiting_history").select(
            "id, visit_datetime, provider_cat, provider_id"
        ).eq("patient_id", patient_id).order("visit_datetime", desc=True).execute()
        
        if not vh_response.data:
            send_whatsapp_message(
                whatsapp_number, "text",
                {"text": {"body": gt_tt(whatsapp_number, f"No visits found for {patient_name}.", supabase)}},
                supabase
            )
            return False
        
        vh_list = vh_response.data
        logger.info(f"Found {len(vh_list)} visits for patient {patient_id}")
        
        # Store data for this module
        user_data[whatsapp_number]["med_rout_data"] = {
            "patient_id": patient_id,
            "patient_name": patient_name,
            "vh_list": vh_list
        }
        
        # Step 2: For each visit, get diagnosis and collect all items
        all_medications = []
        all_equipment = []
        all_products = []
        
        for vh in vh_list:
            # Get diagnosis for this visit
            diagnosis_response = supabase.table("actual_diagnosis").select("id").eq("vh_id", vh["id"]).execute()
            
            if diagnosis_response.data:
                diagnosis_id = diagnosis_response.data[0]["id"]
                
                # Get medications for this diagnosis
                med_response = supabase.table("actual_med").select(
                    "id, purpose, med_id, quantity, times_per_day, pills_per_time, usage_method, meal_timing, remark"
                ).eq("diagnosis_id", diagnosis_id).execute()
                
                if med_response.data:
                    for med in med_response.data:
                        med["vh_id"] = vh["id"]
                        med["visit_date"] = vh["visit_datetime"]
                        med["provider_cat"] = vh["provider_cat"]
                        med["provider_id"] = vh["provider_id"]
                        all_medications.append(med)
                
                # Get equipment for this diagnosis
                equipment_response = supabase.table("actual_equipment").select(
                    "id, purpose, equipment_id, number_of_days, quantity, frequency, remark"
                ).eq("diagnosis_id", diagnosis_id).execute()
                
                if equipment_response.data:
                    for equip in equipment_response.data:
                        equip["vh_id"] = vh["id"]
                        equip["visit_date"] = vh["visit_datetime"]
                        equip["provider_cat"] = vh["provider_cat"]
                        equip["provider_id"] = vh["provider_id"]
                        all_equipment.append(equip)
                
                # Get products for this diagnosis
                product_response = supabase.table("actual_product").select(
                    "id, purpose, product_id, number_of_days, quantity, frequency, remark"
                ).eq("diagnosis_id", diagnosis_id).execute()
                
                if product_response.data:
                    for product in product_response.data:
                        product["vh_id"] = vh["id"]
                        product["visit_date"] = vh["visit_datetime"]
                        product["provider_cat"] = vh["provider_cat"]
                        product["provider_id"] = vh["provider_id"]
                        all_products.append(product)
        
        logger.info(f"Found {len(all_medications)} medications, {len(all_equipment)} equipment, {len(all_products)} products")
        
        # Step 3: Build the comprehensive message
        message_parts = []
        message_parts.append(gt_tt(whatsapp_number, f"💊 **ALL MEDICATIONS & ITEMS for {patient_name}**", supabase))
        message_parts.append("")
        
        # Group by visit for better organization
        visits_dict = {}
        
        # Organize medications by visit
        for med in all_medications:
            vh_id = med["vh_id"]
            if vh_id not in visits_dict:
                visits_dict[vh_id] = {
                    "medications": [],
                    "equipment": [],
                    "products": [],
                    "visit_date": med["visit_date"],
                    "provider_cat": med["provider_cat"],
                    "provider_id": med["provider_id"]
                }
            visits_dict[vh_id]["medications"].append(med)
        
        # Organize equipment by visit
        for equip in all_equipment:
            vh_id = equip["vh_id"]
            if vh_id not in visits_dict:
                visits_dict[vh_id] = {
                    "medications": [],
                    "equipment": [],
                    "products": [],
                    "visit_date": equip["visit_date"],
                    "provider_cat": equip["provider_cat"],
                    "provider_id": equip["provider_id"]
                }
            visits_dict[vh_id]["equipment"].append(equip)
        
        # Organize products by visit
        for product in all_products:
            vh_id = product["vh_id"]
            if vh_id not in visits_dict:
                visits_dict[vh_id] = {
                    "medications": [],
                    "equipment": [],
                    "products": [],
                    "visit_date": product["visit_date"],
                    "provider_cat": product["provider_cat"],
                    "provider_id": product["provider_id"]
                }
            visits_dict[vh_id]["products"].append(product)
        
        # Display by visit (most recent first)
        sorted_visits = sorted(visits_dict.keys(), 
                              key=lambda x: visits_dict[x]["visit_date"], 
                              reverse=True)
        
        if not sorted_visits:
            message_parts.append(translate_template(whatsapp_number, "No medications or items found for any visit.", supabase))
        else:
            for vh_id in sorted_visits:
                visit_data = visits_dict[vh_id]
                
                # Format visit header
                clinic_name = get_clinic_name(supabase, visit_data["provider_cat"], visit_data["provider_id"])
                formatted_date = format_visit_date(visit_data["visit_date"])
                
                # Use gt_tt for dynamic content with variables
                visit_header = gt_tt(whatsapp_number, f"**📅 Visit: {formatted_date} - {clinic_name}**", supabase)
                message_parts.append(visit_header)
                message_parts.append("")
                
                # Show medications for this visit
                if visit_data["medications"]:
                    message_parts.append(translate_template(whatsapp_number, "💊 **Medications:**", supabase))
                    for med in visit_data["medications"]:
                        # Get medication name from inventory
                        inventory_response = supabase.table("acc_inventory_medicine").select(
                            "item_name, prescription_instruction, warning"
                        ).eq("id", med["med_id"]).execute()
                        
                        med_name = "Unknown Medication"
                        if inventory_response.data and len(inventory_response.data) > 0:
                            med_name = inventory_response.data[0].get("item_name", "Unknown Medication")
                        
                        # Medication name stays in English (proper noun)
                        message_parts.append(f"• {med_name}")
                        
                        # Add details
                        details = format_medication_details(whatsapp_number, med, supabase)
                        if details:
                            for line in details.split('\n'):
                                message_parts.append(f"  {line}")
                        
                        # Add inventory instructions if available
                        if inventory_response.data and len(inventory_response.data) > 0:
                            inv_data = inventory_response.data[0]
                            if inv_data.get("prescription_instruction"):
                                instruction = gt_tt(whatsapp_number, f"Instruction: {inv_data['prescription_instruction']}", supabase)
                                message_parts.append(f"  {instruction}")
                            if inv_data.get("warning"):
                                warning = gt_tt(whatsapp_number, f"⚠️ Warning: {inv_data['warning']}", supabase)
                                message_parts.append(f"  {warning}")
                        
                        message_parts.append("")
                
                # Show equipment for this visit
                if visit_data["equipment"]:
                    message_parts.append(translate_template(whatsapp_number, "🩺 **Equipment:**", supabase))
                    for equip in visit_data["equipment"]:
                        # Get equipment name from inventory
                        inventory_response = supabase.table("acc_inventory_equipment").select(
                            "item_name, prescription_instruction, warning"
                        ).eq("id", equip["equipment_id"]).execute()
                        
                        equip_name = "Unknown Equipment"
                        if inventory_response.data and len(inventory_response.data) > 0:
                            equip_name = inventory_response.data[0].get("item_name", "Unknown Equipment")
                        
                        # Equipment name stays in English (proper noun)
                        message_parts.append(f"• {equip_name}")
                        
                        # Add details
                        details = format_equipment_details(whatsapp_number, equip, supabase)
                        if details:
                            for line in details.split('\n'):
                                message_parts.append(f"  {line}")
                        
                        message_parts.append("")
                
                # Show products for this visit
                if visit_data["products"]:
                    message_parts.append(translate_template(whatsapp_number, "🛒 **Products:**", supabase))
                    for product in visit_data["products"]:
                        # Get product name from inventory
                        inventory_response = supabase.table("acc_inventory_product").select(
                            "item_name, prescription_instruction, warning"
                        ).eq("id", product["product_id"]).execute()
                        
                        product_name = "Unknown Product"
                        if inventory_response.data and len(inventory_response.data) > 0:
                            product_name = inventory_response.data[0].get("item_name", "Unknown Product")
                        
                        # Product name stays in English (proper noun)
                        message_parts.append(f"• {product_name}")
                        
                        # Add details
                        details = format_product_details(whatsapp_number, product, supabase)
                        if details:
                            for line in details.split('\n'):
                                message_parts.append(f"  {line}")
                        
                        message_parts.append("")
                
                message_parts.append("─" * 40)
                message_parts.append("")
        
        # Add summary
        total_items = len(all_medications) + len(all_equipment) + len(all_products)
        summary = gt_tt(whatsapp_number, f"**📊 Summary: {total_items} total items across {len(sorted_visits)} visits**", supabase)
        message_parts.append(summary)
        message_parts.append("")
        message_parts.append(translate_template(whatsapp_number, "📞 **Contact your clinic if you have any questions.**", supabase))
        
        # Send the message(s)
        messages = split_message_if_needed(message_parts)
        send_split_messages(whatsapp_number, messages, supabase)
        
        # Ask if user wants to go back
        time.sleep(2)
        return ask_back_to_options(whatsapp_number, user_id, supabase, user_data)
        
    except Exception as e:
        logger.error(f"Error in handle_patient_all_medications for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "Error loading all medications. Please try again.", supabase)}},
            supabase
        )
        return False

def ask_back_to_options(whatsapp_number, user_id, supabase, user_data):
    """Ask user if they want to go back to options."""
    try:
        buttons = [
            {
                "type": "reply",
                "reply": {
                    "id": "back_to_options",
                    "title": gt_t_tt(whatsapp_number, "🔙 Back to Options", supabase)
                }
            }
        ]
        
        content = {
            "interactive": {
                "type": "button",
                "body": {
                    "text": gt_tt(whatsapp_number, "What would you like to do next?", supabase)
                },
                "action": {
                    "buttons": buttons
                }
            }
        }
        
        send_whatsapp_message(whatsapp_number, "interactive", content, supabase)
        user_data[whatsapp_number]["state"] = "MED_ROUT_BACK_TO_OPTIONS"
        return False
        
    except Exception as e:
        logger.error(f"Error in ask_back_to_options for {whatsapp_number}: {e}")
        return False

def handle_med_rout_response(whatsapp_number, user_id, supabase, user_data, message):
    """Handle responses in the medication/routine module."""
    try:
        state = user_data.get(whatsapp_number, {}).get("state")
        
        if "interactive" in message:
            interactive_type = message["interactive"]["type"]
            
            if interactive_type == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if state == "MED_ROUT_BACK_TO_OPTIONS":
                    if button_id == "back_to_options":
                        # Clear module flag and return to individual module
                        user_data[whatsapp_number]["module"] = "individual"
                        from individual import show_patient_main_options
                        return show_patient_main_options(whatsapp_number, user_id, supabase, user_data)
        
        # Handle text messages
        elif "text" in message:
            text_content = message["text"]["body"].strip().lower()
            
            if text_content in ["back", "menu", "main menu"]:
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                from utils import send_interactive_menu
                send_interactive_menu(whatsapp_number, supabase)
                return False
        
        return False
        
    except Exception as e:
        logger.error(f"Error in handle_med_rout_response for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number, 
                "An error occurred. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        return False