import logging
import uuid
from datetime import datetime
from utils import send_whatsapp_message, translate_template, gt_tt, gt_t_tt, send_location_request, calculate_distance, geocode_address
import base64
import tempfile
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Clinic location coordinates
CLINIC_LATITUDE = 2.99170000
CLINIC_LONGITUDE = 101.61560000
MAX_DISTANCE_KM = 15  # Changed from 20 to 15km

# Default provider ID from your data
DEFAULT_PROVIDER_ID = "aff725c1-c333-4039-bd2d-000000000000"

def handle_emergency_start(whatsapp_number, user_id, supabase, user_data):
    """Start emergency conversation flow."""
    try:
        # Generate alert ID
        alert_id = f"EMG-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        
        # Initialize emergency data
        user_data[whatsapp_number]["emergency_data"] = {
            "alert_id": alert_id,
            "whatsapp_number": whatsapp_number,
            "step": "life_risk",
            "created_at": datetime.now().isoformat(),
            "provider_id": DEFAULT_PROVIDER_ID  # Add provider_id here
        }
        
        user_data[whatsapp_number]["state"] = "EMERGENCY_LIFE_RISK"
        
        # Save initial alert to database
        if not save_initial_alert(whatsapp_number, supabase, user_data):
            # If save fails, send error message
            send_whatsapp_message(whatsapp_number, "text", {
                "text": {"body": gt_tt(whatsapp_number, 
                    "⚠️ *ERROR STARTING EMERGENCY*\n\n"
                    "Unable to start emergency service. Please try again or call 999 immediately.", supabase)}
            }, supabase)
            user_data[whatsapp_number].pop("emergency_data", None)
            user_data[whatsapp_number]["state"] = "MAIN_MENU"
            return False
        
        # Ask first question
        ask_life_risk_question(whatsapp_number, supabase)
        
        return True
    except Exception as e:
        logger.error(f"Error starting emergency for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(whatsapp_number, "text", {
            "text": {"body": gt_tt(whatsapp_number, 
                "⚠️ *ERROR STARTING EMERGENCY*\n\n"
                "An error occurred. Please call 999 immediately for emergency assistance.", supabase)}
        }, supabase)
        return False

def save_initial_alert(whatsapp_number, supabase, user_data):
    """Save initial emergency alert to database (a_s_1_emergency table)."""
    try:
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        
        alert_data = {
            "alert_id": emergency_data["alert_id"],
            "whatsapp_number": whatsapp_number,
            "status": "awaiting_life_risk",
            "provider_id": DEFAULT_PROVIDER_ID,  # Use the actual provider ID
            "dispatched_status": "pending",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        logger.info(f"Saving initial alert for {whatsapp_number}: {alert_data}")
        response = supabase.table("a_s_1_emergency").insert(alert_data).execute()
        
        if response.data:
            # Get the UUID id from the response
            db_alert_id = response.data[0]["id"]
            emergency_data["db_alert_id"] = db_alert_id
            logger.info(f"Alert saved with ID: {db_alert_id} and alert_id: {alert_data['alert_id']}")
            return True
        else:
            logger.error(f"No data returned when saving alert for {whatsapp_number}")
            return False
            
    except Exception as e:
        logger.error(f"Error saving initial alert for {whatsapp_number}: {e}", exc_info=True)
        return False

def ask_life_risk_question(whatsapp_number, supabase):
    """Ask if patient's life or function is at immediate risk."""
    content = {
        "interactive": {
            "type": "button",
            "body": {
                "text": gt_tt(whatsapp_number, 
                    "🚑 *EMERGENCY SERVICE*\n\n"
                    "Is the patient's LIFE or FUNCTION at immediate risk?\n\n"
                    "Examples of life-threatening emergencies:\n"
                    "• Chest pain/heart attack\n"
                    "• Severe difficulty breathing\n"
                    "• Unconsciousness\n"
                    "• Severe bleeding\n"
                    "• Stroke symptoms\n"
                    "• Major trauma/injury\n\n"
                    "If YES, ambulance will be dispatched immediately.\n"
                    "If NO, we'll collect more information first.", supabase)
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": "emergency_yes", "title": gt_t_tt(whatsapp_number, "Yes - Life Threat", supabase)}
                    },
                    {
                        "type": "reply",
                        "reply": {"id": "emergency_no", "title": gt_t_tt(whatsapp_number, "No - Not Immediate", supabase)}
                    },
                    {
                        "type": "reply",
                        "reply": {"id": "cancel_ambulance_service", "title": gt_t_tt(whatsapp_number, "❌ Cancel", supabase)}
                    }
                ]
            }
        }
    }
    
    return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)

def save_life_risk_response(whatsapp_number, supabase, user_data, is_emergency):
    """Save life risk response and update alert in a_s_1_emergency and a_s_2_emergency."""
    try:
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        db_alert_id = emergency_data.get("db_alert_id")  # This is the UUID
        
        if not db_alert_id:
            logger.error(f"No database alert ID found for {whatsapp_number}")
            # Try to get it from database using alert_id
            alert_id = emergency_data.get("alert_id")
            if alert_id:
                response = supabase.table("a_s_1_emergency").select("id").eq("alert_id", alert_id).execute()
                if response.data:
                    db_alert_id = response.data[0]["id"]
                    emergency_data["db_alert_id"] = db_alert_id
                    logger.info(f"Retrieved db_alert_id from alert_id: {db_alert_id}")
                else:
                    logger.error(f"Could not find alert with alert_id: {alert_id}")
                    return False
            else:
                return False
        
        # Update a_s_1_emergency table
        update_data = {
            "life_or_function_risk": is_emergency,
            "status": "awaiting_location",
            "updated_at": datetime.now().isoformat()
        }
        
        response = supabase.table("a_s_1_emergency").update(update_data).eq("id", db_alert_id).execute()
        
        if response.data:
            emergency_data["life_or_function_risk"] = is_emergency
            emergency_data["step"] = "location"
            user_data[whatsapp_number]["state"] = "EMERGENCY_LOCATION"
            
            # Also save to a_s_2_emergency (emergency details)
            detail_data = {
                "emergency_id": db_alert_id,
                "step_name": "life_risk",
                "data_type": "boolean",
                "data_value": str(is_emergency),
                "step_order": 1,
                "provider_id": DEFAULT_PROVIDER_ID  # Use actual provider ID
            }
            
            supabase.table("a_s_2_emergency").insert(detail_data).execute()
            
            return True
        else:
            logger.error(f"Failed to update life risk response for alert {db_alert_id}")
            return False
        
    except Exception as e:
        logger.error(f"Error saving life risk response for {whatsapp_number}: {e}", exc_info=True)
        return False

def ask_location(whatsapp_number, supabase, user_data):
    """Ask for location using WhatsApp location sharing."""
    user_data[whatsapp_number]["emergency_data"]["step"] = "location"
    user_data[whatsapp_number]["state"] = "EMERGENCY_LOCATION"
    
    # Send explanation
    send_whatsapp_message(whatsapp_number, "text", {
        "text": {"body": gt_tt(whatsapp_number, 
            "📍 *LOCATION REQUIRED*\n\n"
            "We need your current location to check if you're within our service area.\n\n"
            "**Please use one of these methods:**\n"
            "1. Tap 'Share Location' button below (recommended)\n"
            "2. Or type your address manually\n"
            "   Example: No 12, Jalan Tun Razak, Kuala Lumpur\n\n"
            "**Important:**\n"
            "• Share exact location for distance check\n"
            "• Service area: Within 15km of our clinic\n"
            "• We'll notify you immediately if within range", supabase)}
    }, supabase)
    
    # Send location request button
    return send_location_request(whatsapp_number, supabase)

def geocode_and_save_address(whatsapp_number, supabase, user_data, address_text):
    """Geocode address text and save location information."""
    try:
        logger.info(f"Geocoding address for {whatsapp_number}: {address_text}")
        
        # Geocode the address
        geocoded = geocode_address(address_text)
        
        if not geocoded:
            send_whatsapp_message(whatsapp_number, "text", {
                "text": {"body": gt_tt(whatsapp_number,
                    "❌ *ADDRESS NOT FOUND*\n\n"
                    "We couldn't find the address you provided.\n\n"
                    "**Please try:**\n"
                    "• A more specific address\n"
                    "• Include city and state\n"
                    "• Example: 'No 12, Jalan Tun Razak, Kuala Lumpur'\n\n"
                    "Or use the 'Share Location' button for automatic detection.", supabase)}
            }, supabase)
            return False
        
        # Create location info from geocoded data
        location_info = {
            "latitude": geocoded["latitude"],
            "longitude": geocoded["longitude"],
            "address": geocoded["formatted_address"],
            "original_address": address_text
        }
        
        logger.info(f"Geocoding successful: {geocoded['formatted_address']} - Lat: {geocoded['latitude']}, Long: {geocoded['longitude']}")
        
        # Check distance and handle
        return check_distance_and_handle(whatsapp_number, supabase, user_data, location_info)
        
    except Exception as e:
        logger.error(f"Error geocoding address for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(whatsapp_number, "text", {
            "text": {"body": gt_tt(whatsapp_number,
                "⚠️ *ERROR PROCESSING ADDRESS*\n\n"
                "There was an error processing your address. Please try sharing your location instead.", supabase)}
        }, supabase)
        return False

def check_distance_and_handle(whatsapp_number, supabase, user_data, location_info):
    """Check distance from clinic and handle accordingly."""
    try:
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        db_alert_id = emergency_data.get("db_alert_id")  # This is the UUID
        alert_id_string = emergency_data.get("alert_id", "Unknown")  # This is the human-readable ID
        
        if not db_alert_id:
            logger.error(f"No database alert ID found for {whatsapp_number}")
            # Try to get it from database using alert_id
            alert_id = emergency_data.get("alert_id")
            if alert_id:
                response = supabase.table("a_s_1_emergency").select("id").eq("alert_id", alert_id).execute()
                if response.data:
                    db_alert_id = response.data[0]["id"]
                    emergency_data["db_alert_id"] = db_alert_id
                else:
                    return False
            else:
                return False
        
        # Check if we have coordinates
        if location_info.get("latitude") and location_info.get("longitude"):
            patient_lat = location_info["latitude"]
            patient_lng = location_info["longitude"]
            
            # Calculate distance from clinic
            distance_km = calculate_distance(
                CLINIC_LATITUDE, CLINIC_LONGITUDE,
                patient_lat, patient_lng
            )
            
            if distance_km is None:
                logger.error(f"Failed to calculate distance for {whatsapp_number}")
                # Assume within distance and proceed
                distance_km = 0  # Default to 0 if calculation fails
            
            logger.info(f"Distance from clinic for {whatsapp_number}: {distance_km:.2f} km")
            
            # Update a_s_1_emergency table with distance
            update_data = {
                "location_latitude": float(patient_lat),
                "location_longitude": float(patient_lng),
                "location_address": location_info.get("address", location_info.get("original_address", "Location provided")),
                "distance_km": float(distance_km),
                "status": "team_notified",
                "updated_at": datetime.now().isoformat()
            }
            
            response = supabase.table("a_s_1_emergency").update(update_data).eq("id", db_alert_id).execute()
            
            if not response.data:
                logger.error(f"Failed to update location for alert {db_alert_id}")
            
            # Check if distance exceeds 15km
            if distance_km > MAX_DISTANCE_KM:
                # Update status to call_back
                update_status_data = {
                    "status": "call_back",
                    "dispatched_status": "cancelled",
                    "updated_at": datetime.now().isoformat()
                }
                supabase.table("a_s_1_emergency").update(update_status_data).eq("id", db_alert_id).execute()
                
                # Send message to call 999
                clinic_address = "No. 33, 1, Jalan PU 7/4, Taman Puchong Utama, 47140 Puchong, Selangor"
                
                distance_message = gt_tt(whatsapp_number,
                    f"🚨 *DISTANCE ALERT*\n\n"
                    f"Your location is {distance_km:.1f} km away from our clinic.\n\n"
                    f"*Our Clinic Location:*\n"
                    f"{clinic_address}\n\n"
                    f"*Service Radius:* 15 km\n"
                    f"*Your Distance:* {distance_km:.1f} km\n\n"
                    f"⚠️ *You are outside our service area.*\n\n"
                    f"**Please call 999 immediately for emergency assistance.**\n\n"
                    f"Alert ID: {alert_id_string}\n"
                    f"Status: Referred to 999 emergency services", supabase)
                
                send_whatsapp_message(whatsapp_number, "text", {
                    "text": {"body": distance_message}
                }, supabase)
                
                # Save to a_s_2_emergency
                detail_data = {
                    "emergency_id": db_alert_id,
                    "step_name": "location_distance_check",
                    "data_type": "text",
                    "data_value": f"Distance: {distance_km:.1f} km, Outside service area, Referred to 999",
                    "step_order": 2,
                    "provider_id": DEFAULT_PROVIDER_ID
                }
                supabase.table("a_s_2_emergency").insert(detail_data).execute()
                
                # Clean up emergency data
                user_data[whatsapp_number].pop("emergency_data", None)
                user_data[whatsapp_number]["state"] = "MAIN_MENU"
                user_data[whatsapp_number]["module"] = None
                
                return False
            else:
                # Within distance, send confirmation and continue
                current_time = datetime.now().strftime("%H:%M")
                
                # Show formatted address if available
                display_address = location_info.get("address", location_info.get("original_address", "Location provided"))
                
                confirmation_text = gt_tt(whatsapp_number,
                    f"✅ *LOCATION CONFIRMED*\n\n"
                    f"*Address:* {display_address}\n"
                    f"*Distance from clinic:* {distance_km:.1f} km\n"
                    f"*Status:* Within service area ✓\n\n"
                    f"🚨 *EMERGENCY TEAM NOTIFIED*\n\n"
                    f"Alert ID: {alert_id_string}\n"
                    f"Time: {current_time}\n\n"
                    f"We already notified the team, we will have the team departing ready, will update when departed...\n\n"
                    f"*STAY CALM AND DO NOT MOVE THE PATIENT* unless in immediate danger.\n\n"
                    f"Meanwhile could you please give more info...\n"
                    f"Please answer the following questions one by one.\n\n"
                    f"---\n"
                    f"*QUESTIONS TO FOLLOW:*\n"
                    f"1. Relationship to patient\n"
                    f"2. Your name\n"
                    f"3. Your IC number\n"
                    f"4. Patient name (can type 'Nil' if unknown)\n"
                    f"5. Patient IC number (Nil for unknown)\n"
                    f"6. Patient condition details\n"
                    f"7. Medical history (if known)\n\n"
                    f"You can cancel at any time by pressing the 'Cancel Ambulance' button.", supabase)
                
                send_whatsapp_message(whatsapp_number, "text", {
                    "text": {"body": confirmation_text}
                }, supabase)
                
                # Save location to a_s_2_emergency
                detail_data = {
                    "emergency_id": db_alert_id,
                    "step_name": "location",
                    "data_type": "location",
                    "data_value": f"Lat: {location_info.get('latitude')}, Long: {location_info.get('longitude')}, Address: {display_address}, Distance: {distance_km:.1f} km",
                    "step_order": 2,
                    "provider_id": DEFAULT_PROVIDER_ID
                }
                
                supabase.table("a_s_2_emergency").insert(detail_data).execute()
                
                # Set next step and ask first question
                emergency_data["location"] = location_info
                emergency_data["distance_km"] = distance_km
                emergency_data["step"] = "relationship"
                user_data[whatsapp_number]["state"] = "EMERGENCY_RELATIONSHIP"
                ask_relationship_question(whatsapp_number, supabase, user_data)
                
                return True
        else:
            # No coordinates, just save the address
            logger.warning(f"No coordinates available for {whatsapp_number}, saving address only")
            
            # Update a_s_1_emergency table with address only
            update_data = {
                "location_address": location_info.get("address", location_info.get("original_address", "Location provided")),
                "status": "team_notified",
                "updated_at": datetime.now().isoformat()
            }
            
            response = supabase.table("a_s_1_emergency").update(update_data).eq("id", db_alert_id).execute()
            
            if not response.data:
                logger.error(f"Failed to update location for alert {db_alert_id}")
            
            # Send confirmation and continue
            current_time = datetime.now().strftime("%H:%M")
            display_address = location_info.get("address", location_info.get("original_address", "Location provided"))
            
            confirmation_text = gt_tt(whatsapp_number,
                f"✅ *LOCATION CONFIRMED*\n\n"
                f"*Address:* {display_address}\n"
                f"*Note:* Could not calculate exact distance (no GPS coordinates)\n"
                f"*Status:* Proceeding with emergency...\n\n"
                f"🚨 *EMERGENCY TEAM NOTIFIED*\n\n"
                f"Alert ID: {alert_id_string}\n"
                f"Time: {current_time}\n\n"
                f"We already notified the team, we will have the team departing ready, will update when departed...\n\n"
                f"*STAY CALM AND DO NOT MOVE THE PATIENT* unless in immediate danger.\n\n"
                f"Meanwhile could you please give more info...\n"
                f"Please answer the following questions one by one.\n\n"
                f"---\n"
                f"*QUESTIONS TO FOLLOW:*\n"
                f"1. Relationship to patient\n"
                f"2. Your name\n"
                f"3. Your IC number\n"
                f"4. Patient name (can type 'Nil' if unknown)\n"
                f"5. Patient IC number (Nil for unknown)\n"
                f"6. Patient condition details\n"
                f"7. Medical history (if known)\n\n"
                f"You can cancel at any time by pressing the 'Cancel Ambulance' button.", supabase)
            
            send_whatsapp_message(whatsapp_number, "text", {
                "text": {"body": confirmation_text}
            }, supabase)
            
            # Save location to a_s_2_emergency
            detail_data = {
                "emergency_id": db_alert_id,
                "step_name": "location",
                "data_type": "text",
                "data_value": f"Address: {display_address} (No GPS coordinates)",
                "step_order": 2,
                "provider_id": DEFAULT_PROVIDER_ID
            }
            
            supabase.table("a_s_2_emergency").insert(detail_data).execute()
            
            # Set next step and ask first question
            emergency_data["location"] = location_info
            emergency_data["step"] = "relationship"
            user_data[whatsapp_number]["state"] = "EMERGENCY_RELATIONSHIP"
            ask_relationship_question(whatsapp_number, supabase, user_data)
            
            return True
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking distance for {whatsapp_number}: {e}", exc_info=True)
        # Proceed with emergency if distance check fails
        return True

def save_location_response(whatsapp_number, supabase, user_data, location_info):
    """Save location response and handle distance check."""
    try:
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        
        # Check distance and handle accordingly
        should_proceed = check_distance_and_handle(whatsapp_number, supabase, user_data, location_info)
        
        if not should_proceed:
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error saving location response for {whatsapp_number}: {e}", exc_info=True)
        return False

def ask_relationship_question(whatsapp_number, supabase, user_data):
    """Ask relationship to patient using list menu."""
    content = {
        "interactive": {
            "type": "list",
            "header": {
                "type": "text",
                "text": gt_t_tt(whatsapp_number, "1. Relationship", supabase)
            },
            "body": {
                "text": gt_tt(whatsapp_number, "Select your relationship to the patient:", supabase)
            },
            "footer": {
                "text": gt_t_tt(whatsapp_number, "Select one option", supabase)
            },
            "action": {
                "button": gt_t_tt(whatsapp_number, "Select", supabase),
                "sections": [{
                    "title": gt_t_tt(whatsapp_number, "Relationship", supabase),
                    "rows": [
                        {
                            "id": "relation_parent",
                            "title": gt_t_tt(whatsapp_number, "Parent", supabase)
                        },
                        {
                            "id": "relation_child",
                            "title": gt_t_tt(whatsapp_number, "Child", supabase)
                        },
                        {
                            "id": "relation_relative",
                            "title": gt_t_tt(whatsapp_number, "Relative", supabase)
                        },
                        {
                            "id": "relation_stranger",
                            "title": gt_t_tt(whatsapp_number, "Stranger", supabase)
                        },
                        {
                            "id": "cancel_ambulance_service",
                            "title": gt_t_tt(whatsapp_number, "❌ Cancel", supabase)
                        }
                    ]
                }]
            }
        }
    }
    
    return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)

def save_relationship_response(whatsapp_number, supabase, user_data, relationship):
    """Save relationship response to a_s_2_emergency."""
    try:
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        db_alert_id = emergency_data.get("db_alert_id")
        
        if not db_alert_id:
            logger.error(f"No database alert ID found for {whatsapp_number}")
            return False
        
        detail_data = {
            "emergency_id": db_alert_id,
            "step_name": "relationship",
            "data_type": "relationship",
            "data_value": relationship,
            "step_order": 3,
            "provider_id": DEFAULT_PROVIDER_ID
        }
        
        supabase.table("a_s_2_emergency").insert(detail_data).execute()
        emergency_data["relationship"] = relationship
        return True
        
    except Exception as e:
        logger.error(f"Error saving relationship for {whatsapp_number}: {e}", exc_info=True)
        return False

def ask_caller_name(whatsapp_number, supabase, user_data):
    """Ask for caller's name."""
    user_data[whatsapp_number]["emergency_data"]["step"] = "caller_name"
    user_data[whatsapp_number]["state"] = "EMERGENCY_CALLER_NAME"
    
    content = {
        "interactive": {
            "type": "button",
            "body": {
                "text": gt_tt(whatsapp_number, "2. *Your name:*\n\nPlease type your full name.\n\nExample: Ali bin Ahmad or Siti binti Mohamad", supabase)
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": "cancel_ambulance_service", "title": gt_t_tt(whatsapp_number, "❌ Cancel", supabase)}
                    }
                ]
            }
        }
    }
    
    return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)

def save_caller_name_response(whatsapp_number, supabase, user_data, name):
    """Save caller name response to a_s_2_emergency."""
    try:
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        db_alert_id = emergency_data.get("db_alert_id")
        
        if not db_alert_id:
            logger.error(f"No database alert ID found for {whatsapp_number}")
            return False
        
        detail_data = {
            "emergency_id": db_alert_id,
            "step_name": "caller_name",
            "data_type": "text",
            "data_value": name,
            "step_order": 4,
            "provider_id": DEFAULT_PROVIDER_ID
        }
        
        supabase.table("a_s_2_emergency").insert(detail_data).execute()
        emergency_data["caller_name"] = name
        return True
        
    except Exception as e:
        logger.error(f"Error saving caller name for {whatsapp_number}: {e}", exc_info=True)
        return False

def ask_caller_ic(whatsapp_number, supabase, user_data):
    """Ask for caller's IC number."""
    user_data[whatsapp_number]["emergency_data"]["step"] = "caller_ic"
    user_data[whatsapp_number]["state"] = "EMERGENCY_CALLER_IC"
    
    content = {
        "interactive": {
            "type": "button",
            "body": {
                "text": gt_tt(whatsapp_number, "3. *Your IC number:*\n\nPlease type your IC number.\n\nExample: 901212-14-5678 or 950505-08-1234", supabase)
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": "cancel_ambulance_service", "title": gt_t_tt(whatsapp_number, "❌ Cancel", supabase)}
                    }
                ]
            }
        }
    }
    
    return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)

def save_caller_ic_response(whatsapp_number, supabase, user_data, ic):
    """Save caller IC response to a_s_2_emergency."""
    try:
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        db_alert_id = emergency_data.get("db_alert_id")
        
        if not db_alert_id:
            logger.error(f"No database alert ID found for {whatsapp_number}")
            return False
        
        detail_data = {
            "emergency_id": db_alert_id,
            "step_name": "caller_ic",
            "data_type": "text",
            "data_value": ic,
            "step_order": 5,
            "provider_id": DEFAULT_PROVIDER_ID
        }
        
        supabase.table("a_s_2_emergency").insert(detail_data).execute()
        emergency_data["caller_ic"] = ic
        return True
        
    except Exception as e:
        logger.error(f"Error saving caller IC for {whatsapp_number}: {e}", exc_info=True)
        return False

def ask_patient_name(whatsapp_number, supabase, user_data):
    """Ask for patient's name."""
    user_data[whatsapp_number]["emergency_data"]["step"] = "patient_name"
    user_data[whatsapp_number]["state"] = "EMERGENCY_PATIENT_NAME"
    
    content = {
        "interactive": {
            "type": "button",
            "body": {
                "text": gt_tt(whatsapp_number, "4. *Patient name:*\n\nPlease type the patient's full name.\n\nExample: Ahmad bin Abdullah or Nor Aishah binti Hassan\n\nYou can type 'Nil' if unknown", supabase)
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": "cancel_ambulance_service", "title": gt_t_tt(whatsapp_number, "❌ Cancel", supabase)}
                    }
                ]
            }
        }
    }
    
    return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)

def save_patient_name_response(whatsapp_number, supabase, user_data, name):
    """Save patient name response to a_s_1_emergency and a_s_2_emergency."""
    try:
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        db_alert_id = emergency_data.get("db_alert_id")
        
        if not db_alert_id:
            logger.error(f"No database alert ID found for {whatsapp_number}")
            return False
        
        # Handle "Nil" response
        if name.lower() == "nil":
            name = "Unknown"
        
        # Update patient name in a_s_1_emergency
        update_data = {
            "patient_name": name,
            "updated_at": datetime.now().isoformat()
        }
        supabase.table("a_s_1_emergency").update(update_data).eq("id", db_alert_id).execute()
        
        # Save to a_s_2_emergency
        detail_data = {
            "emergency_id": db_alert_id,
            "step_name": "patient_name",
            "data_type": "text",
            "data_value": name,
            "step_order": 6,
            "provider_id": DEFAULT_PROVIDER_ID
        }
        
        supabase.table("a_s_2_emergency").insert(detail_data).execute()
        emergency_data["patient_name"] = name
        return True
        
    except Exception as e:
        logger.error(f"Error saving patient name for {whatsapp_number}: {e}", exc_info=True)
        return False

def ask_patient_ic(whatsapp_number, supabase, user_data):
    """Ask for patient's IC number."""
    user_data[whatsapp_number]["emergency_data"]["step"] = "patient_ic"
    user_data[whatsapp_number]["state"] = "EMERGENCY_PATIENT_IC"
    
    content = {
        "interactive": {
            "type": "button",
            "body": {
                "text": gt_tt(whatsapp_number, "5. *Patient IC Number:*\n\nPlease type the patient's IC number.\n\nExample: 801212-14-5678\n\nType 'Nil' if unknown", supabase)
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": "cancel_ambulance_service", "title": gt_t_tt(whatsapp_number, "❌ Cancel", supabase)}
                    }
                ]
            }
        }
    }
    
    return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)

def save_patient_ic_response(whatsapp_number, supabase, user_data, ic):
    """Save patient IC response to a_s_2_emergency."""
    try:
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        db_alert_id = emergency_data.get("db_alert_id")
        
        if not db_alert_id:
            logger.error(f"No database alert ID found for {whatsapp_number}")
            return False
        
        detail_data = {
            "emergency_id": db_alert_id,
            "step_name": "patient_ic",
            "data_type": "text",
            "data_value": ic if ic.lower() != "nil" else "Unknown",
            "step_order": 7,
            "provider_id": DEFAULT_PROVIDER_ID
        }
        
        supabase.table("a_s_2_emergency").insert(detail_data).execute()
        emergency_data["patient_ic"] = ic if ic.lower() != "nil" else "Unknown"
        return True
        
    except Exception as e:
        logger.error(f"Error saving patient IC for {whatsapp_number}: {e}", exc_info=True)
        return False

def send_personal_info_summary(whatsapp_number, supabase, user_data):
    """Send summary of personal info collected."""
    emergency_data = user_data[whatsapp_number]["emergency_data"]
    
    summary_text = gt_tt(whatsapp_number,
        "✅ *Personal Information Collected*\n\n"
        f"Relationship: {emergency_data.get('relationship', 'Not provided')}\n"
        f"Your Name: {emergency_data.get('caller_name', 'Not provided')}\n"
        f"Your IC: {emergency_data.get('caller_ic', 'Not provided')}\n"
        f"Patient Name: {emergency_data.get('patient_name', 'Not provided')}\n"
        f"Patient IC: {emergency_data.get('patient_ic', 'Not provided')}\n\n"
        "Now let's collect the emergency details.", supabase)
    
    send_whatsapp_message(whatsapp_number, "text", {
        "text": {"body": summary_text}
    }, supabase)
    
    # Ask for condition video
    emergency_data["step"] = "condition_video"
    user_data[whatsapp_number]["state"] = "EMERGENCY_CONDITION_VIDEO"
    ask_condition_video(whatsapp_number, supabase, user_data)

def ask_condition_video(whatsapp_number, supabase, user_data):
    """Ask for video of the condition using proper WhatsApp API format."""
    # First send a text message explaining
    send_whatsapp_message(whatsapp_number, "text", {
        "text": {"body": gt_tt(whatsapp_number, 
            "6. *Patient Condition Details*\n\n"
            "**If possible, please take a short video showing:**\n"
            "• Patient's breathing\n"
            "• Any visible injuries\n"
            "• Patient's position\n"
            "• Surrounding environment\n\n"
            "**How to send video:**\n"
            "1. Tap the 📎 (attachment) button\n"
            "2. Select 'Camera' to record a video\n"
            "3. Keep video short (10-20 seconds)\n\n"
            "**Or tap 'Skip Video' if you cannot provide a video.**\n\n"
            "This helps our paramedics prepare better.", supabase)}
    }, supabase)
    
    # Send options for skip or cancel
    content = {
        "interactive": {
            "type": "button",
            "body": {
                "text": gt_tt(whatsapp_number, "Choose an option:", supabase)
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": "skip_video", "title": gt_t_tt(whatsapp_number, "Skip Video", supabase)}
                    },
                    {
                        "type": "reply",
                        "reply": {"id": "cancel_ambulance_service", "title": gt_t_tt(whatsapp_number, "❌ Cancel", supabase)}
                    }
                ]
            }
        }
    }
    
    return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)

def save_video_response(whatsapp_number, supabase, user_data, video_url):
    """Save video response to a_s_2_emergency."""
    try:
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        db_alert_id = emergency_data.get("db_alert_id")
        
        if not db_alert_id:
            logger.error(f"No database alert ID found for {whatsapp_number}")
            return False
        
        detail_data = {
            "emergency_id": db_alert_id,
            "step_name": "condition_video",
            "data_type": "video_url",
            "data_value": video_url if video_url else "Skipped",
            "step_order": 8,
            "provider_id": DEFAULT_PROVIDER_ID
        }
        
        supabase.table("a_s_2_emergency").insert(detail_data).execute()
        if video_url:
            emergency_data["video_url"] = video_url
        return True
        
    except Exception as e:
        logger.error(f"Error saving video for {whatsapp_number}: {e}", exc_info=True)
        return False

def ask_conscious_status(whatsapp_number, supabase, user_data):
    """Ask if patient is conscious."""
    emergency_data = user_data[whatsapp_number]["emergency_data"]
    emergency_data["step"] = "conscious"
    user_data[whatsapp_number]["state"] = "EMERGENCY_CONSCIOUS"
    
    content = {
        "interactive": {
            "type": "button",
            "body": {
                "text": gt_tt(whatsapp_number, 
                    "Is the patient conscious?\n\n"
                    "**Conscious:** Patient is awake and responding\n"
                    "**Unconscious:** Patient is not responding to voice or touch", supabase)
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": "conscious_yes", "title": gt_t_tt(whatsapp_number, "Yes - Conscious", supabase)}
                    },
                    {
                        "type": "reply",
                        "reply": {"id": "conscious_no", "title": gt_t_tt(whatsapp_number, "No - Unconscious", supabase)}
                    },
                    {
                        "type": "reply",
                        "reply": {"id": "cancel_ambulance_service", "title": gt_t_tt(whatsapp_number, "❌ Cancel", supabase)}
                    }
                ]
            }
        }
    }
    
    return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)

def save_conscious_response(whatsapp_number, supabase, user_data, is_conscious):
    """Save conscious status response to a_s_2_emergency."""
    try:
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        db_alert_id = emergency_data.get("db_alert_id")
        
        if not db_alert_id:
            logger.error(f"No database alert ID found for {whatsapp_number}")
            return False
        
        detail_data = {
            "emergency_id": db_alert_id,
            "step_name": "conscious",
            "data_type": "boolean",
            "data_value": str(is_conscious),
            "step_order": 9,
            "provider_id": DEFAULT_PROVIDER_ID
        }
        
        supabase.table("a_s_2_emergency").insert(detail_data).execute()
        emergency_data["conscious"] = is_conscious
        return True
        
    except Exception as e:
        logger.error(f"Error saving conscious status for {whatsapp_number}: {e}", exc_info=True)
        return False

def ask_symptoms(whatsapp_number, supabase, user_data):
    """Ask to describe symptoms."""
    emergency_data = user_data[whatsapp_number]["emergency_data"]
    emergency_data["step"] = "symptoms"
    user_data[whatsapp_number]["state"] = "EMERGENCY_SYMPTOMS"
    
    content = {
        "interactive": {
            "type": "button",
            "body": {
                "text": gt_tt(whatsapp_number, 
                    "Please describe the patient's symptoms:\n\n"
                    "**Examples:**\n"
                    "• Chest pain, left side, radiating to arm\n"
                    "• Difficulty breathing, wheezing sound\n"
                    "• Sudden weakness on right side of body\n"
                    "• Severe headache with vomiting\n"
                    "• High fever with confusion\n"
                    "• Fall from height, unable to move legs\n\n"
                    "Be as specific as possible about:\n"
                    "• What symptoms\n"
                    "• When started\n"
                    "• Severity (scale 1-10)", supabase)
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": "cancel_ambulance_service", "title": gt_t_tt(whatsapp_number, "❌ Cancel", supabase)}
                    }
                ]
            }
        }
    }
    
    return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)

def save_symptoms_response(whatsapp_number, supabase, user_data, symptoms):
    """Save symptoms response to a_s_1_emergency and a_s_2_emergency."""
    try:
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        db_alert_id = emergency_data.get("db_alert_id")
        
        if not db_alert_id:
            logger.error(f"No database alert ID found for {whatsapp_number}")
            return False
        
        # Update patient condition in a_s_1_emergency
        update_data = {
            "patient_condition": symptoms[:500],  # Limit to 500 characters
            "updated_at": datetime.now().isoformat()
        }
        supabase.table("a_s_1_emergency").update(update_data).eq("id", db_alert_id).execute()
        
        # Save to a_s_2_emergency
        detail_data = {
            "emergency_id": db_alert_id,
            "step_name": "symptoms",
            "data_type": "text",
            "data_value": symptoms,
            "step_order": 10,
            "provider_id": DEFAULT_PROVIDER_ID
        }
        
        supabase.table("a_s_2_emergency").insert(detail_data).execute()
        emergency_data["symptoms"] = symptoms
        return True
        
    except Exception as e:
        logger.error(f"Error saving symptoms for {whatsapp_number}: {e}", exc_info=True)
        return False

def ask_onset_time(whatsapp_number, supabase, user_data):
    """Ask when symptoms started."""
    emergency_data = user_data[whatsapp_number]["emergency_data"]
    emergency_data["step"] = "onset_time"
    user_data[whatsapp_number]["state"] = "EMERGENCY_ONSET_TIME"
    
    content = {
        "interactive": {
            "type": "button",
            "body": {
                "text": gt_tt(whatsapp_number, 
                    "When did the symptoms start?\n\n"
                    "**Examples:**\n"
                    "• 2:30 PM (exact time)\n"
                    "• About 30 minutes ago\n"
                    "• Sudden onset at 3:15 PM\n"
                    "• Gradual over past 2 hours\n"
                    "• Started this morning\n\n"
                    "Please be as specific as possible.", supabase)
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": "cancel_ambulance_service", "title": gt_t_tt(whatsapp_number, "❌ Cancel", supabase)}
                    }
                ]
            }
        }
    }
    
    return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)

def save_onset_time_response(whatsapp_number, supabase, user_data, onset_time):
    """Save onset time response to a_s_2_emergency."""
    try:
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        db_alert_id = emergency_data.get("db_alert_id")
        
        if not db_alert_id:
            logger.error(f"No database alert ID found for {whatsapp_number}")
            return False
        
        detail_data = {
            "emergency_id": db_alert_id,
            "step_name": "onset_time",
            "data_type": "text",
            "data_value": onset_time,
            "step_order": 11,
            "provider_id": DEFAULT_PROVIDER_ID
        }
        
        supabase.table("a_s_2_emergency").insert(detail_data).execute()
        emergency_data["onset_time"] = onset_time
        return True
        
    except Exception as e:
        logger.error(f"Error saving onset time for {whatsapp_number}: {e}", exc_info=True)
        return False

def ask_breathing_status(whatsapp_number, supabase, user_data):
    """Ask if patient is breathing."""
    emergency_data = user_data[whatsapp_number]["emergency_data"]
    emergency_data["step"] = "breathing"
    user_data[whatsapp_number]["state"] = "EMERGENCY_BREATHING"
    
    content = {
        "interactive": {
            "type": "button",
            "body": {
                "text": gt_tt(whatsapp_number, 
                    "Is the patient breathing?\n\n"
                    "**How to check:**\n"
                    "• Look for chest movement\n"
                    "• Listen for breathing sounds\n"
                    "• Feel for breath on your cheek\n\n"
                    "**Note:** If patient is NOT breathing, we will guide you through CPR instructions immediately.", supabase)
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": "breathing_yes", "title": gt_t_tt(whatsapp_number, "Yes - Breathing", supabase)}
                    },
                    {
                        "type": "reply",
                        "reply": {"id": "breathing_no", "title": gt_t_tt(whatsapp_number, "No - Not Breathing", supabase)}
                    },
                    {
                        "type": "reply",
                        "reply": {"id": "cancel_ambulance_service", "title": gt_t_tt(whatsapp_number, "❌ Cancel", supabase)}
                    }
                ]
            }
        }
    }
    
    return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)

def save_breathing_response(whatsapp_number, supabase, user_data, is_breathing):
    """Save breathing status response to a_s_2_emergency."""
    try:
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        db_alert_id = emergency_data.get("db_alert_id")
        
        if not db_alert_id:
            logger.error(f"No database alert ID found for {whatsapp_number}")
            return False
        
        detail_data = {
            "emergency_id": db_alert_id,
            "step_name": "breathing",
            "data_type": "boolean",
            "data_value": str(is_breathing),
            "step_order": 12,
            "provider_id": DEFAULT_PROVIDER_ID
        }
        
        supabase.table("a_s_2_emergency").insert(detail_data).execute()
        emergency_data["breathing"] = is_breathing
        return True
        
    except Exception as e:
        logger.error(f"Error saving breathing status for {whatsapp_number}: {e}", exc_info=True)
        return False

def ask_health_condition(whatsapp_number, supabase, user_data):
    """Ask about patient's health condition."""
    emergency_data = user_data[whatsapp_number]["emergency_data"]
    emergency_data["step"] = "health_condition"
    user_data[whatsapp_number]["state"] = "EMERGENCY_HEALTH_CONDITION"
    
    content = {
        "interactive": {
            "type": "button",
            "body": {
                "text": gt_tt(whatsapp_number, 
                    "7. *Medical History*\n\n"
                    "Do you know the patient's health condition?\n\n"
                    "**Please provide any known information about:**\n"
                    "• Past diseases (diabetes, hypertension, heart disease)\n"
                    "• Allergies (medication, food, environmental)\n"
                    "• Current medications\n"
                    "• Recent surgeries/hospitalizations\n"
                    "• Known medical conditions\n\n"
                    "**Examples:**\n"
                    "• Diabetic for 10 years, on insulin\n"
                    "• High blood pressure, takes amlodipine\n"
                    "• Allergic to penicillin\n"
                    "• Had heart bypass surgery in 2020\n\n"
                    "If unknown, type 'Unknown'.", supabase)
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": "cancel_ambulance_service", "title": gt_t_tt(whatsapp_number, "❌ Cancel", supabase)}
                    }
                ]
            }
        }
    }
    
    return send_whatsapp_message(whatsapp_number, "interactive", content, supabase)

def save_health_condition_response(whatsapp_number, supabase, user_data, health_info):
    """Save health condition response to a_s_2_emergency."""
    try:
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        db_alert_id = emergency_data.get("db_alert_id")
        
        if not db_alert_id:
            logger.error(f"No database alert ID found for {whatsapp_number}")
            return False
        
        detail_data = {
            "emergency_id": db_alert_id,
            "step_name": "health_condition",
            "data_type": "text",
            "data_value": health_info,
            "step_order": 13,
            "provider_id": DEFAULT_PROVIDER_ID
        }
        
        supabase.table("a_s_2_emergency").insert(detail_data).execute()
        emergency_data["health_condition"] = health_info
        return True
        
    except Exception as e:
        logger.error(f"Error saving health condition for {whatsapp_number}: {e}", exc_info=True)
        return False

def complete_emergency_request(whatsapp_number, supabase, user_data):
    """Complete emergency request without ambulance assignment."""
    try:
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        db_alert_id = emergency_data.get("db_alert_id")
        alert_id_string = emergency_data.get("alert_id", "Unknown")
        
        if not db_alert_id:
            logger.error(f"No database alert ID found for {whatsapp_number}")
            return False
        
        # Update a_s_1_emergency status to information_complete
        update_data = {
            "status": "information_complete",
            "dispatched_status": "awaiting_dispatch",
            "updated_at": datetime.now().isoformat()
        }
        
        response = supabase.table("a_s_1_emergency").update(update_data).eq("id", db_alert_id).execute()
        
        if not response.data:
            return False
        
        # Send final confirmation
        priority = "HIGH" if emergency_data.get('life_or_function_risk') else "MEDIUM"
        
        confirmation_msg = gt_tt(whatsapp_number,
            f"✅ *EMERGENCY REQUEST COMPLETE*\n\n"
            f"Alert ID: {alert_id_string}\n"
            f"Status: All information submitted\n"
            f"Priority: {priority}\n\n"
            f"Thank you for providing all the information.\n"
            f"*Our team is now preparing for departure.*\n\n"
            f"*IMPORTANT INSTRUCTIONS:*\n"
            f"• Stay with the patient\n"
            f"• Do not move the patient unless in immediate danger\n"
            f"• Keep the airway clear if patient is unconscious\n"
            f"• If breathing stops, begin CPR\n"
            f"• We will update you when the ambulance departs\n\n"
            f"**Ambulance is being prepared for dispatch.**\n"
            f"You will receive an ETA shortly.\n\n"
            f"Stay on this chat for updates.", supabase)
        
        send_whatsapp_message(whatsapp_number, "text", {
            "text": {"body": confirmation_msg}
        }, supabase)
        
        # Clean up emergency data
        user_data[whatsapp_number].pop("emergency_data", None)
        user_data[whatsapp_number]["state"] = "MAIN_MENU"
        user_data[whatsapp_number]["module"] = None
        
        return True
        
    except Exception as e:
        logger.error(f"Error completing emergency request for {whatsapp_number}: {e}", exc_info=True)
        return False

def handle_cancel_ambulance_service(whatsapp_number, supabase, user_data):
    """Handle ambulance service cancellation."""
    try:
        # If there's an emergency in progress, update its status
        emergency_data = user_data[whatsapp_number].get("emergency_data")
        if emergency_data and "db_alert_id" in emergency_data:
            db_alert_id = emergency_data["db_alert_id"]
            # Update the emergency status to cancelled
            update_data = {
                "status": "cancelled",
                "dispatched_status": "cancelled",
                "cancelled_time": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            supabase.table("a_s_1_emergency").update(update_data).eq("id", db_alert_id).execute()
            
            # Also save cancellation to a_s_2_emergency
            detail_data = {
                "emergency_id": db_alert_id,
                "step_name": "cancelled",
                "data_type": "text",
                "data_value": "User cancelled ambulance service",
                "step_order": 99,  # High number to indicate it's the last step
                "provider_id": DEFAULT_PROVIDER_ID
            }
            supabase.table("a_s_2_emergency").insert(detail_data).execute()
        
        send_whatsapp_message(whatsapp_number, "text", {
            "text": {"body": gt_tt(whatsapp_number, 
                "❌ *AMBULANCE SERVICE CANCELLED*\n\n"
                "Ambulance service has been cancelled.\n\n"
                "**For emergencies, please call 999 immediately.**\n\n"
                "If this was a mistake, you can restart the emergency service by typing 'emergency'.", supabase)}
        }, supabase)
        
        # Clean up emergency data
        user_data[whatsapp_number].pop("emergency_data", None)
        user_data[whatsapp_number]["state"] = "MAIN_MENU"
        user_data[whatsapp_number]["module"] = None
        
        return True
        
    except Exception as e:
        logger.error(f"Error cancelling ambulance service for {whatsapp_number}: {e}")
        return False

def handle_emergency_response(whatsapp_number, user_id, supabase, user_data, message):
    """Handle emergency conversation responses step by step."""
    try:
        if whatsapp_number not in user_data:
            user_data[whatsapp_number] = {}
        
        if "emergency_data" not in user_data[whatsapp_number]:
            user_data[whatsapp_number]["emergency_data"] = {}
        
        emergency_data = user_data[whatsapp_number]["emergency_data"]
        current_step = emergency_data.get("step", "life_risk")
        
        logger.info(f"Emergency response for {whatsapp_number}, step: {current_step}, message type: {message.get('type')}")
        
        # Handle cancel ambulance service
        if message.get("type") == "interactive":
            interactive = message.get("interactive", {})
            
            if interactive.get("type") == "button_reply":
                button_id = interactive["button_reply"]["id"]
                
                if button_id == "cancel_ambulance_service":
                    return handle_cancel_ambulance_service(whatsapp_number, supabase, user_data)
            
            elif interactive.get("type") == "list_reply":
                selected_id = interactive["list_reply"]["id"]
                
                if selected_id == "cancel_ambulance_service":
                    return handle_cancel_ambulance_service(whatsapp_number, supabase, user_data)
                
                # Handle relationship selection from list
                if current_step == "relationship" and selected_id.startswith("relation_"):
                    relationship_map = {
                        "relation_parent": "Parent",
                        "relation_child": "Child", 
                        "relation_relative": "Relative",
                        "relation_stranger": "Stranger"
                    }
                    relationship = relationship_map.get(selected_id, "Unknown")
                    
                    if save_relationship_response(whatsapp_number, supabase, user_data, relationship):
                        ask_caller_name(whatsapp_number, supabase, user_data)
                    return False
        
        # Step 1: Life risk question
        if current_step == "life_risk":
            if message.get("type") == "interactive":
                interactive = message.get("interactive", {})
                if interactive.get("type") == "button_reply":
                    button_id = interactive["button_reply"]["id"]
                    
                    if button_id in ["emergency_yes", "emergency_no"]:
                        is_emergency = (button_id == "emergency_yes")
                        if save_life_risk_response(whatsapp_number, supabase, user_data, is_emergency):
                            ask_location(whatsapp_number, supabase, user_data)
                        else:
                            # If save fails, send error and restart
                            send_whatsapp_message(whatsapp_number, "text", {
                                "text": {"body": gt_tt(whatsapp_number, 
                                    "⚠️ *ERROR SAVING RESPONSE*\n\n"
                                    "Please try again or call 999 immediately.", supabase)}
                            }, supabase)
                            ask_life_risk_question(whatsapp_number, supabase)
                        return False
        
        # Step 2: Location
        elif current_step == "location":
            if message.get("type") == "location":
                location = message["location"]
                latitude = location.get("latitude")
                longitude = location.get("longitude")
                address = location.get("name", location.get("address", "Location shared"))
                
                location_info = {
                    "latitude": latitude,
                    "longitude": longitude,
                    "address": address
                }
                
                if save_location_response(whatsapp_number, supabase, user_data, location_info):
                    # The check_distance_and_handle function will handle the rest
                    pass
                else:
                    # If save fails, ask for location again
                    send_whatsapp_message(whatsapp_number, "text", {
                        "text": {"body": gt_tt(whatsapp_number, 
                            "⚠️ *ERROR SAVING LOCATION*\n\n"
                            "Please try sharing your location again.", supabase)}
                    }, supabase)
                    ask_location(whatsapp_number, supabase, user_data)
                return False
            
            elif message.get("type") == "text":
                # User typed address instead of sharing location
                address = message["text"]["body"].strip()
                if address and address.lower() != "cancel":
                    # Geocode the address
                    if geocode_and_save_address(whatsapp_number, supabase, user_data, address):
                        # Successfully geocoded and saved
                        pass
                    else:
                        # Geocoding failed, ask for address again
                        ask_location(whatsapp_number, supabase, user_data)
                    return False
        
        # Step 4: Caller name
        elif current_step == "caller_name":
            if message.get("type") == "text":
                name = message["text"]["body"].strip()
                if name and name.lower() != "cancel":
                    if save_caller_name_response(whatsapp_number, supabase, user_data, name):
                        ask_caller_ic(whatsapp_number, supabase, user_data)
                    else:
                        send_whatsapp_message(whatsapp_number, "text", {
                            "text": {"body": gt_tt(whatsapp_number, 
                                "⚠️ *ERROR SAVING NAME*\n\n"
                                "Please try again.", supabase)}
                        }, supabase)
                        ask_caller_name(whatsapp_number, supabase, user_data)
                    return False
        
        # Step 5: Caller IC
        elif current_step == "caller_ic":
            if message.get("type") == "text":
                ic = message["text"]["body"].strip()
                if ic and ic.lower() != "cancel":
                    if save_caller_ic_response(whatsapp_number, supabase, user_data, ic):
                        ask_patient_name(whatsapp_number, supabase, user_data)
                    else:
                        send_whatsapp_message(whatsapp_number, "text", {
                            "text": {"body": gt_tt(whatsapp_number, 
                                "⚠️ *ERROR SAVING IC*\n\n"
                                "Please try again.", supabase)}
                        }, supabase)
                        ask_caller_ic(whatsapp_number, supabase, user_data)
                    return False
        
        # Step 6: Patient name
        elif current_step == "patient_name":
            if message.get("type") == "text":
                name = message["text"]["body"].strip()
                if name and name.lower() != "cancel":
                    if save_patient_name_response(whatsapp_number, supabase, user_data, name):
                        ask_patient_ic(whatsapp_number, supabase, user_data)
                    else:
                        send_whatsapp_message(whatsapp_number, "text", {
                            "text": {"body": gt_tt(whatsapp_number, 
                                "⚠️ *ERROR SAVING PATIENT NAME*\n\n"
                                "Please try again.", supabase)}
                        }, supabase)
                        ask_patient_name(whatsapp_number, supabase, user_data)
                    return False
        
        # Step 7: Patient IC
        elif current_step == "patient_ic":
            if message.get("type") == "text":
                ic = message["text"]["body"].strip()
                if ic and ic.lower() != "cancel":
                    if save_patient_ic_response(whatsapp_number, supabase, user_data, ic):
                        send_personal_info_summary(whatsapp_number, supabase, user_data)
                    else:
                        send_whatsapp_message(whatsapp_number, "text", {
                            "text": {"body": gt_tt(whatsapp_number, 
                                "⚠️ *ERROR SAVING PATIENT IC*\n\n"
                                "Please try again.", supabase)}
                        }, supabase)
                        ask_patient_ic(whatsapp_number, supabase, user_data)
                    return False
        
        # Step 8: Condition video
        elif current_step == "condition_video":
            if message.get("type") == "interactive":
                interactive = message.get("interactive", {})
                if interactive.get("type") == "button_reply":
                    button_id = interactive["button_reply"]["id"]
                    if button_id == "skip_video":
                        if save_video_response(whatsapp_number, supabase, user_data, None):
                            ask_conscious_status(whatsapp_number, supabase, user_data)
                        else:
                            ask_condition_video(whatsapp_number, supabase, user_data)
                        return False
            
            elif message.get("type") == "video":
                # Save video URL
                video = message["video"]
                video_url = video.get("url") or video.get("link")
                if save_video_response(whatsapp_number, supabase, user_data, video_url):
                    ask_conscious_status(whatsapp_number, supabase, user_data)
                else:
                    ask_condition_video(whatsapp_number, supabase, user_data)
                return False
        
        # Step 9: Conscious status
        elif current_step == "conscious":
            if message.get("type") == "interactive":
                interactive = message.get("interactive", {})
                if interactive.get("type") == "button_reply":
                    button_id = interactive["button_reply"]["id"]
                    
                    if button_id in ["conscious_yes", "conscious_no"]:
                        is_conscious = (button_id == "conscious_yes")
                        if save_conscious_response(whatsapp_number, supabase, user_data, is_conscious):
                            ask_symptoms(whatsapp_number, supabase, user_data)
                        else:
                            ask_conscious_status(whatsapp_number, supabase, user_data)
                        return False
        
        # Step 10: Symptoms
        elif current_step == "symptoms":
            if message.get("type") == "text":
                symptoms = message["text"]["body"].strip()
                if symptoms and symptoms.lower() != "cancel":
                    if save_symptoms_response(whatsapp_number, supabase, user_data, symptoms):
                        ask_onset_time(whatsapp_number, supabase, user_data)
                    else:
                        send_whatsapp_message(whatsapp_number, "text", {
                            "text": {"body": gt_tt(whatsapp_number, 
                                "⚠️ *ERROR SAVING SYMPTOMS*\n\n"
                                "Please try again.", supabase)}
                        }, supabase)
                        ask_symptoms(whatsapp_number, supabase, user_data)
                    return False
        
        # Step 11: Onset time
        elif current_step == "onset_time":
            if message.get("type") == "text":
                onset_time = message["text"]["body"].strip()
                if onset_time and onset_time.lower() != "cancel":
                    if save_onset_time_response(whatsapp_number, supabase, user_data, onset_time):
                        ask_breathing_status(whatsapp_number, supabase, user_data)
                    else:
                        send_whatsapp_message(whatsapp_number, "text", {
                            "text": {"body": gt_tt(whatsapp_number, 
                                "⚠️ *ERROR SAVING ONSET TIME*\n\n"
                                "Please try again.", supabase)}
                        }, supabase)
                        ask_onset_time(whatsapp_number, supabase, user_data)
                    return False
        
        # Step 12: Breathing status
        elif current_step == "breathing":
            if message.get("type") == "interactive":
                interactive = message.get("interactive", {})
                if interactive.get("type") == "button_reply":
                    button_id = interactive["button_reply"]["id"]
                    
                    if button_id in ["breathing_yes", "breathing_no"]:
                        is_breathing = (button_id == "breathing_yes")
                        if save_breathing_response(whatsapp_number, supabase, user_data, is_breathing):
                            ask_health_condition(whatsapp_number, supabase, user_data)
                        else:
                            ask_breathing_status(whatsapp_number, supabase, user_data)
                        return False
        
        # Step 13: Health condition
        elif current_step == "health_condition":
            if message.get("type") == "text":
                health_info = message["text"]["body"].strip()
                if health_info and health_info.lower() != "cancel":
                    if save_health_condition_response(whatsapp_number, supabase, user_data, health_info):
                        # Complete the emergency request
                        if complete_emergency_request(whatsapp_number, supabase, user_data):
                            return True
                        else:
                            send_whatsapp_message(whatsapp_number, "text", {
                                "text": {"body": gt_tt(whatsapp_number, 
                                    "⚠️ *ERROR COMPLETING EMERGENCY*\n\n"
                                    "Please try again or call 999 immediately.", supabase)}
                            }, supabase)
                            return False
                    else:
                        send_whatsapp_message(whatsapp_number, "text", {
                            "text": {"body": gt_tt(whatsapp_number, 
                                "⚠️ *ERROR SAVING HEALTH CONDITION*\n\n"
                                "Please try again.", supabase)}
                        }, supabase)
                        ask_health_condition(whatsapp_number, supabase, user_data)
                        return False
        
        return False
        
    except Exception as e:
        logger.error(f"Error handling emergency response for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(whatsapp_number, "text", {
            "text": {"body": gt_tt(whatsapp_number, 
                "⚠️ *AN ERROR OCCURRED*\n\n"
                "Please try again or call 999 immediately for emergency assistance.", supabase)}
        }, supabase)
        return False