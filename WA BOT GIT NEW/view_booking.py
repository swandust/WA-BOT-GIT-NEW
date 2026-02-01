# view_booking.py - Complete with corrected TCM reschedule handling

import logging
import uuid
from datetime import datetime, timedelta, timezone
from utils import send_whatsapp_message, send_interactive_menu, get_user_id, translate_template, gt_t_tt
from calendar_utils import (
    get_doctors, get_calendar, select_period, get_available_hours, 
    get_time_slots, handle_future_date_input, handle_future_date_confirmation,
    get_service_duration
)

from tcm_calendar_utils import (
    get_available_doctors_for_service as get_tcm_doctors,
    get_calendar as get_tcm_calendar,
    select_period as select_tcm_period,
    get_available_hours as get_tcm_hours,
    get_time_slots as get_tcm_time_slots,
    handle_future_date_input as handle_tcm_future_date,
    handle_future_date_confirmation as handle_tcm_future_confirm,
    get_available_doctors as confirm_tcm_doctor,
    get_clinic_doctor_selection,
    handle_confirm_booking_tcm,
    handle_cancel_booking_tcm
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def table_exists(supabase, table_name):
    """Check if a table exists in Supabase."""
    try:
        supabase.table(table_name).select("id").limit(1).execute()
        return True
    except Exception as e:
        logger.warning(f"Table {table_name} does not exist or is inaccessible: {e}")
        return False

def process_repeated_visits(bookings, current_datetime):
    """Process bookings to handle repeated_visit_uuid logic.
    
    For bookings with same repeated_visit_uuid, only show the most upcoming booking
    and mark it with {repeated}.
    """
    try:
        # Group bookings by repeated_visit_uuid
        repeated_groups = {}
        single_bookings = []
        
        for booking in bookings:
            # Check if booking has repeated_visit_uuid
            repeated_uuid = booking.get('repeated_visit_uuid')
            
            if repeated_uuid:
                # Group by repeated_visit_uuid
                if repeated_uuid not in repeated_groups:
                    repeated_groups[repeated_uuid] = []
                repeated_groups[repeated_uuid].append(booking)
            else:
                # Single booking, no repeated_visit_uuid
                single_bookings.append(booking)
        
        # For each repeated group, find the most upcoming booking
        processed_repeated_bookings = []
        
        for repeated_uuid, group_bookings in repeated_groups.items():
            if not group_bookings:
                continue
                
            # Sort by date and time (most upcoming first)
            sorted_bookings = sorted(
                group_bookings,
                key=lambda x: (
                    datetime.strptime(f"{x['date']} {x['time']}", "%Y-%m-%d %H:%M")
                    if x.get('date') and x.get('time')
                    else datetime.max
                )
            )
            
            # Take the most upcoming booking (first after sorting)
            if sorted_bookings:
                most_upcoming = sorted_bookings[0]
                
                # Add {repeated} marker to the text
                if 'text' in most_upcoming:
                    most_upcoming['text'] += " {repeated}"
                if 'display_text' in most_upcoming:
                    most_upcoming['display_text'] += " {repeated}"
                
                # Mark as repeated for tracking
                most_upcoming['is_repeated'] = True
                most_upcoming['repeated_visit_uuid'] = repeated_uuid
                most_upcoming['total_repeated_count'] = len(sorted_bookings)
                
                processed_repeated_bookings.append(most_upcoming)
        
        # Combine single bookings and processed repeated bookings
        all_bookings = single_bookings + processed_repeated_bookings
        
        # Sort all bookings by date and time (most upcoming first)
        all_bookings = sorted(
            all_bookings,
            key=lambda x: (
                datetime.strptime(f"{x['date']} {x['time']}", "%Y-%m-%d %H:%M")
                if x.get('date') and x.get('time')
                else datetime.max
            )
        )
        
        return all_bookings
        
    except Exception as e:
        logger.error(f"Error processing repeated visits: {e}", exc_info=True)
        # Return original bookings if processing fails
        return bookings

def send_booking_type_selection_menu(whatsapp_number, supabase, user_data, processed_action_required, confirmed_bookings, pending_bookings_list):
    """Send booking type selection menu (action required, pending, confirmed)."""
    try:
        rows = []
        
        # Check which categories have bookings
        if processed_action_required:
            rows.append({
                "id": "action_required",
                "title": translate_template(whatsapp_number, "Action Required", supabase),
                "description": translate_template(whatsapp_number, f"{len(processed_action_required)} booking(s) need your action", supabase)
            })
        
        if confirmed_bookings:
            rows.append({
                "id": "confirmed",
                "title": translate_template(whatsapp_number, "Confirmed", supabase),
                "description": translate_template(whatsapp_number, f"{len(confirmed_bookings)} confirmed booking(s)", supabase)
            })
        
        if pending_bookings_list:
            rows.append({
                "id": "pending",
                "title": translate_template(whatsapp_number, "Pending", supabase),
                "description": translate_template(whatsapp_number, f"{len(pending_bookings_list)} pending booking(s)", supabase)
            })
        
        if not rows:
            # No bookings in any category
            return None
        
        # Add back button
        rows.append({
            "id": "back_to_home",
            "title": translate_template(whatsapp_number, "🔙 Back", supabase),
            "description": translate_template(whatsapp_number, "Return to main menu", supabase)
        })
        
        # Store categories data for later use
        user_data[whatsapp_number]["booking_categories"] = {
            "action_required": processed_action_required,
            "confirmed": confirmed_bookings,
            "pending": pending_bookings_list
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "to": whatsapp_number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": translate_template(whatsapp_number, "Select booking type:", supabase)},
                "action": {
                    "button": translate_template(whatsapp_number, "Select Type", supabase),
                    "sections": [{
                        "title": translate_template(whatsapp_number, "Booking Categories", supabase),
                        "rows": rows
                    }]
                }
            }
        }
        
        return payload
        
    except Exception as e:
        logger.error(f"Error in send_booking_type_selection_menu for {whatsapp_number}: {e}", exc_info=True)
        return None

def handle_booking_type_selection(whatsapp_number, user_id, supabase, user_data, message):
    """Handle booking type selection (action required, pending, confirmed)."""
    try:
        if message["type"] == "interactive" and message["interactive"]["type"] == "list_reply":
            selected_type = message["interactive"]["list_reply"]["id"]
            
            # Handle back button
            if selected_type == "back_to_home":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Returning to main menu.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False
            
            # Get the selected category bookings
            categories = user_data[whatsapp_number].get("booking_categories", {})
            
            if selected_type == "action_required":
                selected_bookings = categories.get("action_required", [])
                category_name = "Action Required"
            elif selected_type == "confirmed":
                selected_bookings = categories.get("confirmed", [])
                category_name = "Confirmed"
            elif selected_type == "pending":
                selected_bookings = categories.get("pending", [])
                category_name = "Pending"
            else:
                logger.error(f"Invalid booking type selected: {selected_type}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Invalid selection. Please try again.", supabase)}},
                    supabase
                )
                return False
            
            if not selected_bookings:
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number, 
                        "No bookings found in the {} category.", 
                        supabase
                    ).format(category_name)}},
                    supabase
                )
                return False
            
            # Store selected bookings for next step
            user_data[whatsapp_number]["selected_category"] = selected_type
            user_data[whatsapp_number]["bookings"] = selected_bookings
            
            # Send booking selection menu
            payload = {
                "messaging_product": "whatsapp",
                "to": whatsapp_number,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": translate_template(
                        whatsapp_number, 
                        "Select a booking to manage or reschedule from {} category:", 
                        supabase
                    ).format(category_name)},
                    "action": {
                        "button": translate_template(whatsapp_number, "Choose Booking", supabase),
                        "sections": [{
                            "title": translate_template(whatsapp_number, "{} Bookings", supabase).format(category_name),
                            "rows": [
                                {
                                    "id": b["id"],
                                    "title": translate_template(whatsapp_number, "Booking {}", supabase).format(i + 1),
                                    "description": translate_template(whatsapp_number, b['text'][:72], supabase)
                                } for i, b in enumerate(selected_bookings)
                            ][:10]
                        }]
                    }
                }
            }
            send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
            
            user_data[whatsapp_number]["state"] = "SELECT_BOOKING_FOR_RESCHEDULE"
            return False
            
    except Exception as e:
        logger.error(f"Error in handle_booking_type_selection for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing booking type selection. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def handle_view_upcoming_booking(whatsapp_number, user_id, supabase, user_data):
    """Handle the View Upcoming Booking flow with reschedule option and categorized sections."""
    try:
        # Normalize whatsapp_number
        from_number_norm = whatsapp_number.lstrip("+").strip()
        number_variants = [from_number_norm, f"+{from_number_norm}"]
        logger.info(f"Fetching upcoming bookings for whatsapp_number: {number_variants}")

        # Fetch user_id from whatsapp_users
        try:
            user_id = get_user_id(supabase, whatsapp_number)
            if not user_id:
                logger.warning(f"No user_id found for {from_number_norm}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "User not found. Please ensure your number is registered.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False
        except Exception as e:
            logger.error(f"Error fetching user_id from whatsapp_users: {e}", exc_info=True)
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Error fetching user information. Please try again.", supabase)}},
                supabase
            )
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False

        # Fetch doctors (for conventional medicine)
        try:
            doctors_data = supabase.table("c_a_doctors").select("id, name, clinic_id").execute().data
            doctors_dict = {str(d["id"]): {"name": d["name"], "clinic_id": str(d.get("clinic_id", ""))} for d in doctors_data}
            logger.info(f"Conventional doctors fetched: {len(doctors_data)}")
        except Exception as e:
            logger.error(f"Error fetching conventional doctors: {e}", exc_info=True)
            doctors_dict = {}

        # Fetch TCM doctors
        try:
            tcm_doctors_data = supabase.table("tcm_a_doctors").select("id, name, clinic_id").execute().data
            tcm_doctors_dict = {str(d["id"]): {"name": d["name"], "clinic_id": str(d.get("clinic_id", ""))} for d in tcm_doctors_data}
            logger.info(f"TCM doctors fetched: {len(tcm_doctors_data)}")
        except Exception as e:
            logger.error(f"Error fetching TCM doctors: {e}", exc_info=True)
            tcm_doctors_dict = {}

        # Fetch clinics (conventional)
        try:
            clinics_data = supabase.table("c_a_clinics").select("id, name").execute().data
            clinics_dict = {str(c["id"]): c["name"] for c in clinics_data}
            logger.info(f"Conventional clinics fetched: {len(clinics_data)}")
        except Exception as e:
            logger.error(f"Error fetching conventional clinics: {e}", exc_info=True)
            clinics_dict = {}

        # Fetch TCM clinics
        try:
            tcm_clinics_data = supabase.table("tcm_a_clinics").select("id, name").execute().data
            tcm_clinics_dict = {str(c["id"]): c["name"] for c in tcm_clinics_data}
            logger.info(f"TCM clinics fetched: {len(tcm_clinics_data)}")
        except Exception as e:
            logger.error(f"Error fetching TCM clinics: {e}", exc_info=True)
            tcm_clinics_dict = {}

        # Fetch ambulance providers
        try:
            ambulance_providers_data = supabase.table("a_provider").select("id, name").execute().data
            ambulance_providers_dict = {str(p["id"]): p["name"] for p in ambulance_providers_data}
            logger.info(f"Ambulance providers fetched: {len(ambulance_providers_data)}")
        except Exception as e:
            logger.error(f"Error fetching ambulance providers: {e}", exc_info=True)
            ambulance_providers_dict = {}

        # Current date and time in +08 timezone
        try:
            now = datetime.now(timezone(timedelta(hours=8)))
            current_datetime = now
            logger.info(f"Current datetime (+08): {current_datetime}")
        except Exception as e:
            logger.error(f"Error setting timezone: {e}", exc_info=True)
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Error processing timezone. Please try again.", supabase)}},
                supabase
            )
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False

        # Query bookings for the user
        action_required = []
        confirmed_bookings_raw = []
        pending_bookings_raw = []

        # Query c_s_consultation table with repeated_visit_uuid
        if table_exists(supabase, "c_s_consultation"):
            try:
                # Check if repeated_visit_uuid column exists
                consultations = supabase.table("c_s_consultation").select(
                    "id, doctor_id, details, date, time, duration_minutes, reminder_duration, reminder_remark, repeated_visit_uuid"
                ).eq("user_id", user_id).execute().data
            except Exception as e:
                # If column doesn't exist, fetch without it
                consultations = supabase.table("c_s_consultation").select(
                    "id, doctor_id, details, date, time, duration_minutes, reminder_duration, reminder_remark"
                ).eq("user_id", user_id).execute().data
                for c in consultations:
                    c['repeated_visit_uuid'] = None
            
            logger.info(f"Found {len(consultations)} conventional consultation records")
            for c in consultations:
                if not (c.get('date') and c.get('time')):
                    logger.warning(f"Skipping consultation with missing date/time: {c}")
                    continue
                try:
                    booking_datetime = datetime.strptime(f"{c['date']} {c['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=8)))
                    if booking_datetime >= current_datetime:
                        dr_info = doctors_dict.get(str(c['doctor_id']), {"name": translate_template(whatsapp_number, "Unknown", supabase), "clinic_id": ""})
                        dr_name = dr_info["name"]
                        clinic_name = clinics_dict.get(dr_info["clinic_id"], translate_template(whatsapp_number, "Unknown Clinic", supabase))
                        details = gt_t_tt(whatsapp_number, c['details'] or 'N/A', supabase, doctor_name=dr_name)
                        booking_str = translate_template(
                            whatsapp_number,
                            "Consultation with Dr. {} at {} on {} at {} (Symptoms: {})",
                            supabase
                        ).format(
                            dr_name,
                            clinic_name,
                            c['date'],
                            c['time'],
                            details
                        )
                        confirmed_bookings_raw.append({
                            "id": f"con_{str(c['id'])}",
                            "text": booking_str,
                            "date": c['date'],
                            "time": c['time'],
                            "doctor_id": str(c['doctor_id']),
                            "details": c['details'],
                            "type": "consultation",
                            "table": "c_s_consultation",
                            "display_details": details,
                            "clinic_id": dr_info["clinic_id"],
                            "duration_minutes": c['duration_minutes'],
                            "reminder_duration": c.get("reminder_duration"),
                            "reminder_remark": c.get("reminder_remark"),
                            "repeated_visit_uuid": c.get('repeated_visit_uuid'),
                            "module": "conventional"
                        })
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing consultation date/time {c}: {e}")
                    continue

        # Query c_s_checkup table with repeated_visit_uuid
        if table_exists(supabase, "c_s_checkup"):
            try:
                checkups = supabase.table("c_s_checkup").select(
                    "id, doctor_id, details, date, time, duration_minutes, reminder_duration, reminder_remark, repeated_visit_uuid"
                ).eq("user_id", user_id).execute().data
            except Exception as e:
                checkups = supabase.table("c_s_checkup").select(
                    "id, doctor_id, details, date, time, duration_minutes, reminder_duration, reminder_remark"
                ).eq("user_id", user_id).execute().data
                for c in checkups:
                    c['repeated_visit_uuid'] = None
            
            logger.info(f"Found {len(checkups)} conventional checkup records")
            for c in checkups:
                if not (c.get('date') and c.get('time')):
                    logger.warning(f"Skipping checkup with missing date/time: {c}")
                    continue
                try:
                    booking_datetime = datetime.strptime(f"{c['date']} {c['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=8)))
                    if booking_datetime >= current_datetime:
                        dr_info = doctors_dict.get(str(c['doctor_id']), {"name": translate_template(whatsapp_number, "Unknown", supabase), "clinic_id": ""})
                        dr_name = dr_info["name"]
                        clinic_name = clinics_dict.get(dr_info["clinic_id"], translate_template(whatsapp_number, "Unknown Clinic", supabase))
                        details = gt_t_tt(whatsapp_number, c['details'] or 'N/A', supabase, doctor_name=dr_name)
                        booking_str = translate_template(
                            whatsapp_number,
                            "Checkup ({}) with Dr. {} at {} on {} at {}",
                            supabase
                        ).format(
                            details,
                            dr_name,
                            clinic_name,
                            c['date'],
                            c['time']
                        )
                        confirmed_bookings_raw.append({
                            "id": f"chk_{str(c['id'])}",
                            "text": booking_str,
                            "date": c['date'],
                            "time": c['time'],
                            "doctor_id": str(c['doctor_id']),
                            "details": c['details'],
                            "type": "checkup",
                            "table": "c_s_checkup",
                            "display_details": details,
                            "clinic_id": dr_info["clinic_id"],
                            "duration_minutes": c['duration_minutes'],
                            "reminder_duration": c.get("reminder_duration"),
                            "reminder_remark": c.get("reminder_remark"),
                            "repeated_visit_uuid": c.get('repeated_visit_uuid'),
                            "module": "conventional"
                        })
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing checkup date/time {c}: {e}")
                    continue

        # Query c_s_vaccination table with repeated_visit_uuid
        if table_exists(supabase, "c_s_vaccination"):
            try:
                vaccinations = supabase.table("c_s_vaccination").select(
                    "id, doctor_id, vaccine_type, date, time, duration_minutes, reminder_duration, reminder_remark, repeated_visit_uuid"
                ).eq("user_id", user_id).execute().data
            except Exception as e:
                vaccinations = supabase.table("c_s_vaccination").select(
                    "id, doctor_id, vaccine_type, date, time, duration_minutes, reminder_duration, reminder_remark"
                ).eq("user_id", user_id).execute().data
                for v in vaccinations:
                    v['repeated_visit_uuid'] = None
            
            logger.info(f"Found {len(vaccinations)} conventional vaccination records")
            for v in vaccinations:
                if not (v.get('date') and v.get('time')):
                    logger.warning(f"Skipping vaccination with missing date/time: {v}")
                    continue
                try:
                    booking_datetime = datetime.strptime(f"{v['date']} {v['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=8)))
                    if booking_datetime >= current_datetime:
                        dr_info = doctors_dict.get(str(v['doctor_id']), {"name": translate_template(whatsapp_number, "Unknown", supabase), "clinic_id": ""})
                        dr_name = dr_info["name"]
                        clinic_name = clinics_dict.get(dr_info["clinic_id"], translate_template(whatsapp_number, "Unknown Clinic", supabase))
                        vaccine_type = gt_t_tt(whatsapp_number, v['vaccine_type'] or 'N/A', supabase, doctor_name=dr_name)
                        booking_str = translate_template(
                            whatsapp_number,
                            "Vaccination ({}) with Dr. {} at {} on {} at {}",
                            supabase
                        ).format(
                            vaccine_type,
                            dr_name,
                            clinic_name,
                            v['date'],
                            v['time']
                        )
                        confirmed_bookings_raw.append({
                            "id": f"vac_{str(v['id'])}",
                            "text": booking_str,
                            "date": v['date'],
                            "time": v['time'],
                            "doctor_id": str(v['doctor_id']),
                            "vaccine_type": v['vaccine_type'],
                            "type": "vaccination",
                            "table": "c_s_vaccination",
                            "display_vaccine_type": vaccine_type,
                            "clinic_id": dr_info["clinic_id"],
                            "duration_minutes": v['duration_minutes'],
                            "reminder_duration": v.get("reminder_duration"),
                            "reminder_remark": v.get("reminder_remark"),
                            "repeated_visit_uuid": v.get('repeated_visit_uuid'),
                            "module": "conventional"
                        })
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing vaccination date/time {v}: {e}")
                    continue

        # Query c_s_pending_bookings table with repeated_visit_uuid
        if table_exists(supabase, "c_s_pending_bookings"):
            try:
                pending_bookings = supabase.table("c_s_pending_bookings").select(
                    "id, doctor_id, booking_type, details, vaccine_type, date, time, duration_minutes, reminder_duration, reminder_remark, repeated_visit_uuid"
                ).eq("user_id", user_id).execute().data
            except Exception as e:
                pending_bookings = supabase.table("c_s_pending_bookings").select(
                    "id, doctor_id, booking_type, details, vaccine_type, date, time, duration_minutes, reminder_duration, reminder_remark"
                ).eq("user_id", user_id).execute().data
                for p in pending_bookings:
                    p['repeated_visit_uuid'] = None
            
            logger.info(f"Found {len(pending_bookings)} conventional pending booking records")
            for p in pending_bookings:
                if not (p.get('date') and p.get('time')):
                    logger.warning(f"Skipping pending booking with missing date/time: {p}")
                    continue
                try:
                    booking_datetime = datetime.strptime(f"{p['date']} {p['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=8)))
                    if booking_datetime >= current_datetime:
                        dr_info = doctors_dict.get(str(p['doctor_id']), {"name": translate_template(whatsapp_number, "Unknown", supabase), "clinic_id": ""})
                        dr_name = dr_info["name"]
                        clinic_name = clinics_dict.get(dr_info["clinic_id"], translate_template(whatsapp_number, "Unknown Clinic", supabase))
                        details = gt_t_tt(whatsapp_number, p['details'] or p['vaccine_type'] or p['booking_type'] or 'N/A', supabase, doctor_name=dr_name)
                        booking_type_translated = translate_template(whatsapp_number, p['booking_type'].capitalize(), supabase)
                        booking_str = translate_template(
                            whatsapp_number,
                            "Pending {} ({}) with Dr. {} at {} on {} at {}",
                            supabase
                        ).format(
                            booking_type_translated,
                            details,
                            dr_name,
                            clinic_name,
                            p['date'],
                            p['time']
                        )
                        pending_bookings_raw.append({
                            "id": f"pen_{str(p['id'])}",
                            "text": booking_str,
                            "date": p['date'],
                            "time": p['time'],
                            "doctor_id": str(p['doctor_id']),
                            "details": p['details'],
                            "vaccine_type": p['vaccine_type'],
                            "type": p['booking_type'],
                            "table": "c_s_pending_bookings",
                            "display_details": details,
                            "clinic_id": dr_info["clinic_id"],
                            "duration_minutes": p['duration_minutes'],
                            "reminder_duration": p.get("reminder_duration"),
                            "reminder_remark": p.get("reminder_remark"),
                            "repeated_visit_uuid": p.get('repeated_visit_uuid'),
                            "module": "conventional"
                        })
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing pending booking date/time {p}: {e}")
                    continue

        # Query c_s_reschedule_requests table with repeated_visit_uuid
        if table_exists(supabase, "c_s_reschedule_requests"):
            try:
                reschedule_requests = supabase.table("c_s_reschedule_requests").select(
                    "id, doctor_id, booking_type, details, vaccine_type, original_date, original_time, new_date, new_time, status, duration_minutes, reminder_duration, reminder_remark, repeated_visit_uuid"
                ).eq("user_id", user_id).eq("status", "pending").execute().data
            except Exception as e:
                reschedule_requests = supabase.table("c_s_reschedule_requests").select(
                    "id, doctor_id, booking_type, details, vaccine_type, original_date, original_time, new_date, new_time, status, duration_minutes, reminder_duration, reminder_remark"
                ).eq("user_id", user_id).eq("status", "pending").execute().data
                for r in reschedule_requests:
                    r['repeated_visit_uuid'] = None
            
            logger.info(f"Found {len(reschedule_requests)} conventional reschedule request records")
            for r in reschedule_requests:
                if not (r.get('original_date') and r.get('original_time') and r.get('new_date') and r.get('new_time')):
                    logger.warning(f"Skipping reschedule request with missing date/time: {r}")
                    continue
                try:
                    booking_datetime = datetime.strptime(f"{r['original_date']} {r['original_time']}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=8)))
                    if booking_datetime >= current_datetime:
                        dr_info = doctors_dict.get(str(r['doctor_id']), {"name": translate_template(whatsapp_number, "Unknown", supabase), "clinic_id": ""})
                        dr_name = dr_info["name"]
                        clinic_name = clinics_dict.get(dr_info["clinic_id"], translate_template(whatsapp_number, "Unknown Clinic", supabase))
                        details = gt_t_tt(whatsapp_number, r['details'] or r['vaccine_type'] or r['booking_type'] or 'N/A', supabase, doctor_name=dr_name)
                        booking_type_translated = translate_template(whatsapp_number, r['booking_type'].capitalize(), supabase)
                        booking_str = translate_template(
                            whatsapp_number,
                            "{} ({}) with Dr. {} at {} on {} at {} (New: {} at {})",
                            supabase
                        ).format(
                            booking_type_translated,
                            details,
                            dr_name,
                            clinic_name,
                            r['original_date'],
                            r['original_time'],
                            r['new_date'],
                            r['new_time']
                        )
                        action_required.append({
                            "id": f"res_{str(r['id'])}",
                            "text": booking_str,
                            "original_date": r['original_date'],
                            "original_time": r['original_time'],
                            "new_date": r['new_date'],
                            "new_time": r['new_time'],
                            "doctor_id": str(r['doctor_id']),
                            "details": r['details'],
                            "vaccine_type": r['vaccine_type'],
                            "type": r['booking_type'],
                            "table": "c_s_reschedule_requests",
                            "display_details": details,
                            "clinic_id": dr_info["clinic_id"],
                            "duration_minutes": r['duration_minutes'],
                            "reminder_duration": r.get("reminder_duration"),
                            "reminder_remark": r.get("reminder_remark"),
                            "repeated_visit_uuid": r.get('repeated_visit_uuid'),
                            "module": "conventional"
                        })
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing reschedule request date/time {r}: {e}")
                    continue

        # Query tcm_s_bookings table
        if table_exists(supabase, "tcm_s_bookings"):
            try:
                tcm_bookings = supabase.table("tcm_s_bookings").select(
                    "id, doctor_id, booking_type, details, original_date, original_time, new_date, new_time, status, duration_minutes, reminder_duration, reminder_remark, repeated_visit_uuid, service_id"
                ).eq("user_id", user_id).in_("status", ["pending", "confirmed", "reschedule_pending", "cancelled"]).execute().data
                
                logger.info(f"Found {len(tcm_bookings)} TCM booking records")
                for b in tcm_bookings:
                    # Skip cancelled bookings
                    if b['status'] == 'cancelled':
                        continue
                    
                    # For reschedule_pending, use new_date and new_time (proposed by doctor)
                    if b['status'] == 'reschedule_pending' and b.get('new_date') and b.get('new_time'):
                        display_date = b['new_date']
                        display_time = b['new_time']
                        is_reschedule_pending = True
                    else:
                        display_date = b.get('new_date') or b.get('original_date')
                        display_time = b.get('new_time') or b.get('original_time')
                        is_reschedule_pending = False
                    
                    if not (display_date and display_time):
                        logger.warning(f"Skipping TCM booking with missing date/time: {b}")
                        continue
                    
                    try:
                        booking_datetime = datetime.strptime(f"{display_date} {display_time}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=8)))
                        if booking_datetime >= current_datetime:
                            dr_info = tcm_doctors_dict.get(str(b['doctor_id']), {"name": translate_template(whatsapp_number, "Unknown TCM Doctor", supabase), "clinic_id": ""})
                            dr_name = dr_info["name"]
                            clinic_name = tcm_clinics_dict.get(dr_info["clinic_id"], translate_template(whatsapp_number, "Unknown TCM Clinic", supabase))
                            details = gt_t_tt(whatsapp_number, b['details'] or 'N/A', supabase, doctor_name=dr_name)
                            booking_type_translated = translate_template(whatsapp_number, b['booking_type'].capitalize(), supabase)
                            
                            # Determine category based on status
                            if b['status'] == 'reschedule_pending':
                                # Show both original and new times for reschedule_pending
                                if b.get('original_date') and b.get('original_time'):
                                    booking_str = translate_template(
                                        whatsapp_number,
                                        "TCM {} with Dr. {} at {} on {} at {} (New: {} at {}) - Doctor Requested Reschedule",
                                        supabase
                                    ).format(
                                        booking_type_translated,
                                        dr_name,
                                        clinic_name,
                                        b['original_date'],
                                        b['original_time'],
                                        b['new_date'],
                                        b['new_time']
                                    )
                                else:
                                    booking_str = translate_template(
                                        whatsapp_number,
                                        "TCM {} with Dr. {} at {} on {} at {} - Doctor Requested Reschedule",
                                        supabase
                                    ).format(
                                        booking_type_translated,
                                        dr_name,
                                        clinic_name,
                                        display_date,
                                        display_time
                                    )
                                
                                booking_data = {
                                    "id": f"tcm_{str(b['id'])}",
                                    "text": booking_str,
                                    "original_date": b['original_date'],
                                    "original_time": b['original_time'],
                                    "new_date": b['new_date'],
                                    "new_time": b['new_time'],
                                    "doctor_id": str(b['doctor_id']),
                                    "details": b['details'],
                                    "type": b['booking_type'],
                                    "table": "tcm_s_bookings",
                                    "display_details": details,
                                    "clinic_id": dr_info["clinic_id"],
                                    "duration_minutes": b['duration_minutes'],
                                    "reminder_duration": b.get("reminder_duration"),
                                    "reminder_remark": b.get("reminder_remark"),
                                    "repeated_visit_uuid": b.get('repeated_visit_uuid'),
                                    "module": "tcm",
                                    "service_id": b.get('service_id'),
                                    "status": b['status']
                                }
                                
                                action_required.append(booking_data)

                            elif b['status'] == 'pending':
                                prefix = "Pending TCM"
                                booking_str = translate_template(
                                    whatsapp_number,
                                    "{} {} with Dr. {} at {} on {} at {} (Details: {})",
                                    supabase
                                ).format(
                                    prefix,
                                    booking_type_translated,
                                    dr_name,
                                    clinic_name,
                                    display_date,
                                    display_time,
                                    details
                                )
                                
                                booking_data = {
                                    "id": f"tcm_{str(b['id'])}",
                                    "text": booking_str,
                                    "date": display_date,
                                    "time": display_time,
                                    "doctor_id": str(b['doctor_id']),
                                    "details": b['details'],
                                    "type": b['booking_type'],
                                    "table": "tcm_s_bookings",
                                    "display_details": details,
                                    "clinic_id": dr_info["clinic_id"],
                                    "duration_minutes": b['duration_minutes'],
                                    "reminder_duration": b.get("reminder_duration"),
                                    "reminder_remark": b.get("reminder_remark"),
                                    "repeated_visit_uuid": b.get('repeated_visit_uuid'),
                                    "module": "tcm",
                                    "service_id": b.get('service_id'),
                                    "status": b['status']
                                }
                                
                                pending_bookings_raw.append(booking_data)
                                
                            elif b['status'] == 'confirmed':
                                prefix = "TCM"
                                booking_str = translate_template(
                                    whatsapp_number,
                                    "{} {} with Dr. {} at {} on {} at {} (Details: {})",
                                    supabase
                                ).format(
                                    prefix,
                                    booking_type_translated,
                                    dr_name,
                                    clinic_name,
                                    display_date,
                                    display_time,
                                    details
                                )
                                
                                booking_data = {
                                    "id": f"tcm_{str(b['id'])}",
                                    "text": booking_str,
                                    "date": display_date,
                                    "time": display_time,
                                    "doctor_id": str(b['doctor_id']),
                                    "details": b['details'],
                                    "type": b['booking_type'],
                                    "table": "tcm_s_bookings",
                                    "display_details": details,
                                    "clinic_id": dr_info["clinic_id"],
                                    "duration_minutes": b['duration_minutes'],
                                    "reminder_duration": b.get("reminder_duration"),
                                    "reminder_remark": b.get("reminder_remark"),
                                    "repeated_visit_uuid": b.get('repeated_visit_uuid'),
                                    "module": "tcm",
                                    "service_id": b.get('service_id'),
                                    "status": b['status']
                                }
                                
                                confirmed_bookings_raw.append(booking_data)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Error parsing TCM booking date/time {b}: {e}")
                        continue
            except Exception as e:
                logger.error(f"Error fetching TCM bookings: {e}", exc_info=True)

        # Query a_s_hometohome table
        if table_exists(supabase, "a_s_hometohome"):
            try:
                hometohome_bookings = supabase.table("a_s_hometohome").select(
                    "id, transfer_id, patient_name, scheduled_date, scheduled_time, status, provider_id, distance_km, from_address, to_address"
                ).in_("whatsapp_number", number_variants).in_("status", ["pending", "confirmed", "scheduled"]).execute().data
                
                logger.info(f"Found {len(hometohome_bookings)} home-to-home ambulance records")
                for b in hometohome_bookings:
                    if not (b.get('scheduled_date') and b.get('scheduled_time')):
                        logger.warning(f"Skipping home-to-home with missing date/time: {b}")
                        continue
                    
                    try:
                        # Parse time (might be HH:MM:SS or HH:MM)
                        scheduled_time_str = str(b['scheduled_time'])
                        if ':' in scheduled_time_str:
                            time_parts = scheduled_time_str.split(':')
                            if len(time_parts) >= 2:
                                scheduled_time_display = f"{time_parts[0]}:{time_parts[1]}"
                            else:
                                scheduled_time_display = scheduled_time_str
                        else:
                            scheduled_time_display = scheduled_time_str
                            
                        booking_datetime = datetime.strptime(f"{b['scheduled_date']} {scheduled_time_display}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=8)))
                        if booking_datetime >= current_datetime:
                            provider_name = ambulance_providers_dict.get(str(b['provider_id']), translate_template(whatsapp_number, "Unknown Provider", supabase))
                            patient_name = b.get('patient_name') or translate_template(whatsapp_number, "Patient", supabase)
                            
                            # Determine prefix based on status
                            if b['status'] in ['pending', 'scheduled']:
                                prefix = "Scheduled"
                            else:
                                prefix = "Confirmed"
                            
                            booking_str = translate_template(
                                whatsapp_number,
                                "{} Home-to-Home Transfer for {} on {} at {} (Provider: {}, Distance: {} km)",
                                supabase
                            ).format(
                                prefix,
                                patient_name,
                                b['scheduled_date'],
                                scheduled_time_display,
                                provider_name,
                                b.get('distance_km', 'N/A')
                            )
                            
                            booking_data = {
                                "id": f"h2h_{str(b['id'])}",
                                "text": booking_str,
                                "date": b['scheduled_date'],
                                "time": scheduled_time_display,
                                "provider_id": str(b['provider_id']),
                                "type": "hometohome",
                                "table": "a_s_hometohome",
                                "patient_name": patient_name,
                                "from_address": b.get('from_address'),
                                "to_address": b.get('to_address'),
                                "module": "ambulance",
                                "status": b['status']
                            }
                            
                            # Add to appropriate list
                            if b['status'] == 'confirmed':
                                confirmed_bookings_raw.append(booking_data)
                            else:
                                pending_bookings_raw.append(booking_data)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Error parsing home-to-home date/time {b}: {e}")
                        continue
            except Exception as e:
                logger.error(f"Error fetching home-to-home bookings: {e}", exc_info=True)

        # Query a_s_hometohosp table
        if table_exists(supabase, "a_s_hometohosp"):
            try:
                hometohosp_bookings = supabase.table("a_s_hometohosp").select(
                    "id, booking_id, patient_name, scheduled_date, scheduled_time, status, provider_id, hospital_name, appointment_date, appointment_time, pickup_address"
                ).in_("whatsapp_number", number_variants).in_("status", ["pending", "confirmed", "scheduled"]).execute().data
                
                logger.info(f"Found {len(hometohosp_bookings)} home-to-hospital ambulance records")
                for b in hometohosp_bookings:
                    if not (b.get('scheduled_date') and b.get('scheduled_time')):
                        logger.warning(f"Skipping home-to-hospital with missing date/time: {b}")
                        continue
                    
                    try:
                        # Parse time (might be HH:MM:SS or HH:MM)
                        scheduled_time_str = str(b['scheduled_time'])
                        if ':' in scheduled_time_str:
                            time_parts = scheduled_time_str.split(':')
                            if len(time_parts) >= 2:
                                scheduled_time_display = f"{time_parts[0]}:{time_parts[1]}"
                            else:
                                scheduled_time_display = scheduled_time_str
                        else:
                            scheduled_time_display = scheduled_time_str
                            
                        booking_datetime = datetime.strptime(f"{b['scheduled_date']} {scheduled_time_display}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=8)))
                        if booking_datetime >= current_datetime:
                            provider_name = ambulance_providers_dict.get(str(b['provider_id']), translate_template(whatsapp_number, "Unknown Provider", supabase))
                            patient_name = b.get('patient_name') or translate_template(whatsapp_number, "Patient", supabase)
                            hospital_name = b.get('hospital_name') or translate_template(whatsapp_number, "Hospital", supabase)
                            
                            # Determine prefix based on status
                            if b['status'] in ['pending', 'scheduled']:
                                prefix = "Scheduled"
                            else:
                                prefix = "Confirmed"
                            
                            # Check if there's an appointment time
                            appointment_info = ""
                            if b.get('appointment_date') and b.get('appointment_time'):
                                appointment_info = translate_template(whatsapp_number, " (Appointment: {} at {})", supabase).format(
                                    b['appointment_date'], b['appointment_time']
                                )
                            
                            booking_str = translate_template(
                                whatsapp_number,
                                "{} Home-to-Hospital Transfer for {} to {}{} on {} at {} (Provider: {})",
                                supabase
                            ).format(
                                prefix,
                                patient_name,
                                hospital_name,
                                appointment_info,
                                b['scheduled_date'],
                                scheduled_time_display,
                                provider_name
                            )
                            
                            booking_data = {
                                "id": f"h2hosp_{str(b['id'])}",
                                "text": booking_str,
                                "date": b['scheduled_date'],
                                "time": scheduled_time_display,
                                "provider_id": str(b['provider_id']),
                                "type": "hometohosp",
                                "table": "a_s_hometohosp",
                                "patient_name": patient_name,
                                "hospital_name": hospital_name,
                                "pickup_address": b.get('pickup_address'),
                                "module": "ambulance",
                                "status": b['status']
                            }
                            
                            # Add to appropriate list
                            if b['status'] == 'confirmed':
                                confirmed_bookings_raw.append(booking_data)
                            else:
                                pending_bookings_raw.append(booking_data)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Error parsing home-to-hospital date/time {b}: {e}")
                        continue
            except Exception as e:
                logger.error(f"Error fetching home-to-hospital bookings: {e}", exc_info=True)

        # Query a_s_hosptohome table
        if table_exists(supabase, "a_s_hosptohome"):
            try:
                hosptohome_bookings = supabase.table("a_s_hosptohome").select(
                    "id, discharge_id, patient_name, scheduled_date, scheduled_time, status, provider_id, distance_km, hospital_name, home_address"
                ).in_("whatsapp_number", number_variants).in_("status", ["pending", "confirmed", "scheduled"]).execute().data
                
                logger.info(f"Found {len(hosptohome_bookings)} hospital-to-home ambulance records")
                for b in hosptohome_bookings:
                    if not (b.get('scheduled_date') and b.get('scheduled_time')):
                        logger.warning(f"Skipping hospital-to-home with missing date/time: {b}")
                        continue
                    
                    try:
                        # Parse time (might be HH:MM:SS or HH:MM)
                        scheduled_time_str = str(b['scheduled_time'])
                        if ':' in scheduled_time_str:
                            time_parts = scheduled_time_str.split(':')
                            if len(time_parts) >= 2:
                                scheduled_time_display = f"{time_parts[0]}:{time_parts[1]}"
                            else:
                                scheduled_time_display = scheduled_time_str
                        else:
                            scheduled_time_display = scheduled_time_str
                            
                        booking_datetime = datetime.strptime(f"{b['scheduled_date']} {scheduled_time_display}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=8)))
                        if booking_datetime >= current_datetime:
                            provider_name = ambulance_providers_dict.get(str(b['provider_id']), translate_template(whatsapp_number, "Unknown Provider", supabase))
                            patient_name = b.get('patient_name') or translate_template(whatsapp_number, "Patient", supabase)
                            hospital_name = b.get('hospital_name') or translate_template(whatsapp_number, "Hospital", supabase)
                            
                            # Determine prefix based on status
                            if b['status'] in ['pending', 'scheduled']:
                                prefix = "Scheduled"
                            else:
                                prefix = "Confirmed"
                            
                            booking_str = translate_template(
                                whatsapp_number,
                                "{} Hospital-to-Home Transfer for {} from {} on {} at {} (Provider: {}, Distance: {} km)",
                                supabase
                            ).format(
                                prefix,
                                patient_name,
                                hospital_name,
                                b['scheduled_date'],
                                scheduled_time_display,
                                provider_name,
                                b.get('distance_km', 'N/A')
                            )
                            
                            booking_data = {
                                "id": f"hosp2h_{str(b['id'])}",
                                "text": booking_str,
                                "date": b['scheduled_date'],
                                "time": scheduled_time_display,
                                "provider_id": str(b['provider_id']),
                                "type": "hosptohome",
                                "table": "a_s_hosptohome",
                                "patient_name": patient_name,
                                "hospital_name": hospital_name,
                                "home_address": b.get('home_address'),
                                "module": "ambulance",
                                "status": b['status']
                            }
                            
                            # Add to appropriate list
                            if b['status'] == 'confirmed':
                                confirmed_bookings_raw.append(booking_data)
                            else:
                                pending_bookings_raw.append(booking_data)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Error parsing hospital-to-home date/time {b}: {e}")
                        continue
            except Exception as e:
                logger.error(f"Error fetching hospital-to-home bookings: {e}", exc_info=True)

        # Query a_s_hosptohosp table
        if table_exists(supabase, "a_s_hosptohosp"):
            try:
                hosptohosp_bookings = supabase.table("a_s_hosptohosp").select(
                    "id, transfer_id, patient_name, scheduled_date, scheduled_time, status, provider_id, distance_km, from_hospital_name, to_hospital_name"
                ).in_("whatsapp_number", number_variants).in_("status", ["pending", "confirmed", "scheduled"]).execute().data
                
                logger.info(f"Found {len(hosptohosp_bookings)} hospital-to-hospital ambulance records")
                for b in hosptohosp_bookings:
                    if not (b.get('scheduled_date') and b.get('scheduled_time')):
                        logger.warning(f"Skipping hospital-to-hospital with missing date/time: {b}")
                        continue
                    
                    try:
                        # Parse time (might be HH:MM:SS or HH:MM)
                        scheduled_time_str = str(b['scheduled_time'])
                        if ':' in scheduled_time_str:
                            time_parts = scheduled_time_str.split(':')
                            if len(time_parts) >= 2:
                                scheduled_time_display = f"{time_parts[0]}:{time_parts[1]}"
                            else:
                                scheduled_time_display = scheduled_time_str
                        else:
                            scheduled_time_display = scheduled_time_str
                            
                        booking_datetime = datetime.strptime(f"{b['scheduled_date']} {scheduled_time_display}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=8)))
                        if booking_datetime >= current_datetime:
                            provider_name = ambulance_providers_dict.get(str(b['provider_id']), translate_template(whatsapp_number, "Unknown Provider", supabase))
                            patient_name = b.get('patient_name') or translate_template(whatsapp_number, "Patient", supabase)
                            from_hospital = b.get('from_hospital_name') or translate_template(whatsapp_number, "Hospital", supabase)
                            to_hospital = b.get('to_hospital_name') or translate_template(whatsapp_number, "Hospital", supabase)
                            
                            # Determine prefix based on status
                            if b['status'] in ['pending', 'scheduled']:
                                prefix = "Scheduled"
                            else:
                                prefix = "Confirmed"
                            
                            booking_str = translate_template(
                                whatsapp_number,
                                "{} Hospital-to-Hospital Transfer for {} from {} to {} on {} at {} (Provider: {}, Distance: {} km)",
                                supabase
                            ).format(
                                prefix,
                                patient_name,
                                from_hospital,
                                to_hospital,
                                b['scheduled_date'],
                                scheduled_time_display,
                                provider_name,
                                b.get('distance_km', 'N/A')
                            )
                            
                            booking_data = {
                                "id": f"hosp2hosp_{str(b['id'])}",
                                "text": booking_str,
                                "date": b['scheduled_date'],
                                "time": scheduled_time_display,
                                "provider_id": str(b['provider_id']),
                                "type": "hosptohosp",
                                "table": "a_s_hosptohosp",
                                "patient_name": patient_name,
                                "from_hospital": from_hospital,
                                "to_hospital": to_hospital,
                                "module": "ambulance",
                                "status": b['status']
                            }
                            
                            # Add to appropriate list
                            if b['status'] == 'confirmed':
                                confirmed_bookings_raw.append(booking_data)
                            else:
                                pending_bookings_raw.append(booking_data)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Error parsing hospital-to-hospital date/time {b}: {e}")
                        continue
            except Exception as e:
                logger.error(f"Error fetching hospital-to-hospital bookings: {e}", exc_info=True)

        # Process repeated visits for confirmed and pending bookings
        confirmed_bookings = process_repeated_visits(confirmed_bookings_raw, current_datetime)
        pending_bookings_list = process_repeated_visits(pending_bookings_raw, current_datetime)
        
        # Process action required (reschedule requests) for repeated visits
        processed_action_required = process_repeated_visits(action_required, current_datetime)

        # Check total number of bookings
        total_bookings = len(processed_action_required) + len(confirmed_bookings) + len(pending_bookings_list)
        
        # If there's only one booking, handle it directly
        if total_bookings == 1:
            # Determine which category the single booking belongs to
            if processed_action_required:
                selected_bookings = processed_action_required
                category_name = "Action Required"
            elif confirmed_bookings:
                selected_bookings = confirmed_bookings
                category_name = "Confirmed"
            else:
                selected_bookings = pending_bookings_list
                category_name = "Pending"
            
            # Select the single booking
            selected_booking = selected_bookings[0]
            booking_id = selected_booking["id"]
            
            # Store booking details
            user_data[whatsapp_number]["selected_booking"] = selected_booking
            user_data[whatsapp_number]["booking_id"] = booking_id
            user_data[whatsapp_number]["original_date"] = selected_booking.get("date") or selected_booking.get("original_date")
            user_data[whatsapp_number]["original_time"] = selected_booking.get("time") or selected_booking.get("original_time")
            user_data[whatsapp_number]["doctor_id"] = selected_booking.get("doctor_id")
            user_data[whatsapp_number]["provider_id"] = selected_booking.get("provider_id")
            user_data[whatsapp_number]["details"] = selected_booking.get("details")
            user_data[whatsapp_number]["vaccine_type"] = selected_booking.get("vaccine_type")
            user_data[whatsapp_number]["booking_type"] = selected_booking["type"]
            user_data[whatsapp_number]["table_name"] = selected_booking["table"]
            user_data[whatsapp_number]["clinic_id"] = selected_booking.get("clinic_id")
            user_data[whatsapp_number]["duration_minutes"] = selected_booking.get("duration_minutes")
            user_data[whatsapp_number]["reminder_duration"] = selected_booking.get("reminder_duration")
            user_data[whatsapp_number]["reminder_remark"] = selected_booking.get("reminder_remark")
            user_data[whatsapp_number]["repeated_visit_uuid"] = selected_booking.get("repeated_visit_uuid")
            user_data[whatsapp_number]["is_repeated"] = selected_booking.get("is_repeated", False)
            user_data[whatsapp_number]["module"] = selected_booking.get("module", "conventional")
            user_data[whatsapp_number]["service_id"] = selected_booking.get("service_id")
            user_data[whatsapp_number]["status"] = selected_booking.get("status", "confirmed")
            
            # Send action buttons directly
            return handle_booking_selection_for_reschedule_direct(whatsapp_number, user_id, supabase, user_data, booking_id)

        # Construct message with categorized sections
        message_parts = []
        if processed_action_required:
            message_parts.append(translate_template(whatsapp_number, "Action Required", supabase) + ":\n" + "\n".join(f"{i+1}. {b['text']}" for i, b in enumerate(processed_action_required)))
        if confirmed_bookings:
            message_parts.append(translate_template(whatsapp_number, "Confirmed", supabase) + ":\n" + "\n".join(f"{i+1}. {b['text']}" for i, b in enumerate(confirmed_bookings)))
        if pending_bookings_list:
            message_parts.append(translate_template(whatsapp_number, "Pending", supabase) + ":\n" + "\n".join(f"{i+1}. {b['text']}" for i, b in enumerate(pending_bookings_list)))

        if not message_parts:
            message = translate_template(whatsapp_number, "You have no upcoming bookings.", supabase)
            logger.info(f"No upcoming bookings found for {from_number_norm}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": message}},
                supabase
            )
            
            # Send back to home button
            send_back_to_home_options(whatsapp_number, supabase)
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            return False

        # Send the categorized booking list
        message = "\n\n".join(message_parts)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": message}},
            supabase
        )

        # Send booking type selection menu
        payload = send_booking_type_selection_menu(
            whatsapp_number, supabase, user_data, 
            processed_action_required, confirmed_bookings, pending_bookings_list
        )
        
        if not payload:
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "No bookings found in any category.", supabase)}},
                supabase
            )
            send_back_to_home_options(whatsapp_number, supabase)
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            return False
        
        send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
        
        # Store bookings data and update state
        user_data[whatsapp_number]["state"] = "SELECT_BOOKING_TYPE"
        user_data[whatsapp_number]["module"] = "view_booking"
        return False

    except Exception as e:
        logger.error(f"Unexpected error in handle_view_upcoming_booking for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "An unexpected error occurred while fetching upcoming bookings. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def handle_booking_selection_for_reschedule_direct(whatsapp_number, user_id, supabase, user_data, booking_id):
    """Handle booking selection for reschedule directly (for single booking case)."""
    try:
        # Find the selected booking from stored data
        selected_booking = user_data[whatsapp_number].get("selected_booking")
        
        if not selected_booking:
            logger.error(f"Selected booking {booking_id} not found for {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Invalid booking selection. Please try again.", supabase)}},
                supabase
            )
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False
        
        # Send action buttons based on booking type
        if selected_booking["table"] == "c_s_reschedule_requests":
            # For reschedule requests, show accept/decline buttons
            payload = {
                "messaging_product": "whatsapp",
                "to": whatsapp_number,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": translate_template(
                            whatsapp_number,
                            "Selected: {}",
                            supabase
                        ).format(translate_template(whatsapp_number, selected_booking['text'], supabase))
                    },
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": f"accept_{booking_id[4:]}",
                                    "title": translate_template(whatsapp_number, "Accept", supabase)
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": f"decline_{booking_id[4:]}",
                                    "title": translate_template(whatsapp_number, "Decline", supabase)
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "back_to_home",
                                    "title": translate_template(whatsapp_number, "Back to Home", supabase)
                                }
                            }
                        ]
                    }
                }
            }

        # Update the section for TCM reschedule_pending bookings
        elif selected_booking.get("module") == "tcm" and selected_booking.get("status") == "reschedule_pending":
            # For TCM reschedule pending (doctor requested reschedule), show accept/decline buttons
            payload = {
                "messaging_product": "whatsapp",
                "to": whatsapp_number,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": translate_template(
                            whatsapp_number,
                            "Selected: {}\n\nDoctor has requested to reschedule this appointment.",
                            supabase
                        ).format(translate_template(whatsapp_number, selected_booking['text'], supabase))
                    },
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": f"accept_{booking_id[4:]}",  # Remove "tcm_" prefix
                                    "title": translate_template(whatsapp_number, "Accept", supabase)
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": f"decline_{booking_id[4:]}",
                                    "title": translate_template(whatsapp_number, "Decline", supabase)
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "back_to_home",
                                    "title": translate_template(whatsapp_number, "Back to Home", supabase)
                                }
                            }
                        ]
                    }
                }
            }

        elif selected_booking.get("module") == "ambulance":
            # For ambulance bookings, show limited options
            payload = {
                "messaging_product": "whatsapp",
                "to": whatsapp_number,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": translate_template(
                            whatsapp_number,
                            "Selected: {}\n\nAmbulance bookings cannot be modified via WhatsApp. Please contact the ambulance service directly for any changes.",
                            supabase
                        ).format(translate_template(whatsapp_number, selected_booking['text'], supabase))
                    },
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "back_to_home",
                                    "title": translate_template(whatsapp_number, "Back to Home", supabase)
                                }
                            }
                        ]
                    }
                }
            }
        else:
            # For regular bookings, show reschedule/cancel buttons
            payload = {
                "messaging_product": "whatsapp",
                "to": whatsapp_number,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": translate_template(
                            whatsapp_number,
                            "Selected: {}",
                            supabase
                        ).format(translate_template(whatsapp_number, selected_booking['text'], supabase))
                    },
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": f"reschedule_{booking_id}",
                                    "title": translate_template(whatsapp_number, "Reschedule", supabase)
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": f"cancel_{booking_id}",
                                    "title": translate_template(whatsapp_number, "Cancel Booking", supabase)
                                }
                            },
                            {
                                "type": "reply",
                                "reply": {
                                    "id": "back_to_home",
                                    "title": translate_template(whatsapp_number, "Back to Home", supabase)
                                }
                            }
                        ]
                    }
                }
            }
        
        send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
        user_data[whatsapp_number]["state"] = "SELECT_ACTION"
        return False
            
    except Exception as e:
        logger.error(f"Error in handle_booking_selection_for_reschedule_direct for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing booking selection. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def handle_booking_selection_for_reschedule(whatsapp_number, user_id, supabase, user_data, message):
    """Handle booking selection for reschedule."""
    try:
        if message["type"] == "interactive" and message["interactive"]["type"] == "list_reply":
            booking_id = message["interactive"]["list_reply"]["id"]
            bookings = user_data[whatsapp_number].get("bookings", [])
            
            # Find the selected booking
            selected_booking = next((b for b in bookings if b["id"] == booking_id), None)
            
            if not selected_booking:
                logger.error(f"Selected booking {booking_id} not found for {whatsapp_number}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Invalid booking selection. Please try again.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False
            
            # Store booking details for reschedule
            user_data[whatsapp_number]["selected_booking"] = selected_booking
            user_data[whatsapp_number]["booking_id"] = booking_id
            user_data[whatsapp_number]["original_date"] = selected_booking.get("date") or selected_booking.get("original_date")
            user_data[whatsapp_number]["original_time"] = selected_booking.get("time") or selected_booking.get("original_time")
            user_data[whatsapp_number]["doctor_id"] = selected_booking.get("doctor_id")
            user_data[whatsapp_number]["provider_id"] = selected_booking.get("provider_id")
            user_data[whatsapp_number]["details"] = selected_booking.get("details")
            user_data[whatsapp_number]["vaccine_type"] = selected_booking.get("vaccine_type")
            user_data[whatsapp_number]["booking_type"] = selected_booking["type"]
            user_data[whatsapp_number]["table_name"] = selected_booking["table"]
            user_data[whatsapp_number]["clinic_id"] = selected_booking.get("clinic_id")
            user_data[whatsapp_number]["duration_minutes"] = selected_booking.get("duration_minutes")
            user_data[whatsapp_number]["reminder_duration"] = selected_booking.get("reminder_duration")
            user_data[whatsapp_number]["reminder_remark"] = selected_booking.get("reminder_remark")
            user_data[whatsapp_number]["repeated_visit_uuid"] = selected_booking.get("repeated_visit_uuid")
            user_data[whatsapp_number]["is_repeated"] = selected_booking.get("is_repeated", False)
            user_data[whatsapp_number]["module"] = selected_booking.get("module", "conventional")
            user_data[whatsapp_number]["service_id"] = selected_booking.get("service_id")
            user_data[whatsapp_number]["status"] = selected_booking.get("status", "confirmed")
            
            # Send action buttons based on booking type
            if selected_booking["table"] == "c_s_reschedule_requests":
                # For reschedule requests, show accept/decline buttons
                payload = {
                    "messaging_product": "whatsapp",
                    "to": whatsapp_number,
                    "type": "interactive",
                    "interactive": {
                        "type": "button",
                        "body": {
                            "text": translate_template(
                                whatsapp_number,
                                "Selected: {}",
                                supabase
                            ).format(translate_template(whatsapp_number, selected_booking['text'], supabase))
                        },
                        "action": {
                            "buttons": [
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": f"accept_{booking_id[4:]}",
                                        "title": translate_template(whatsapp_number, "Accept", supabase)
                                    }
                                },
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": f"decline_{booking_id[4:]}",
                                        "title": translate_template(whatsapp_number, "Decline", supabase)
                                    }
                                },
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": "back_to_home",
                                        "title": translate_template(whatsapp_number, "Back to Home", supabase)
                                    }
                                }
                            ]
                        }
                    }
                }

            # Update the section for TCM reschedule_pending bookings
            elif selected_booking.get("module") == "tcm" and selected_booking.get("status") == "reschedule_pending":
                # For TCM reschedule pending (doctor requested reschedule), show accept/decline buttons
                payload = {
                    "messaging_product": "whatsapp",
                    "to": whatsapp_number,
                    "type": "interactive",
                    "interactive": {
                        "type": "button",
                        "body": {
                            "text": translate_template(
                                whatsapp_number,
                                "Selected: {}\n\nDoctor has requested to reschedule this appointment.",
                                supabase
                            ).format(translate_template(whatsapp_number, selected_booking['text'], supabase))
                        },
                        "action": {
                            "buttons": [
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": f"accept_{booking_id[4:]}",  # Remove "tcm_" prefix
                                        "title": translate_template(whatsapp_number, "Accept", supabase)
                                    }
                                },
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": f"decline_{booking_id[4:]}",
                                        "title": translate_template(whatsapp_number, "Decline", supabase)
                                    }
                                },
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": "back_to_home",
                                        "title": translate_template(whatsapp_number, "Back to Home", supabase)
                                    }
                                }
                            ]
                        }
                    }
                }

            elif selected_booking.get("module") == "ambulance":
                # For ambulance bookings, show limited options
                payload = {
                    "messaging_product": "whatsapp",
                    "to": whatsapp_number,
                    "type": "interactive",
                    "interactive": {
                        "type": "button",
                        "body": {
                            "text": translate_template(
                                whatsapp_number,
                                "Selected: {}\n\nAmbulance bookings cannot be modified via WhatsApp. Please contact the ambulance service directly for any changes.",
                                supabase
                            ).format(translate_template(whatsapp_number, selected_booking['text'], supabase))
                        },
                        "action": {
                            "buttons": [
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": "back_to_home",
                                        "title": translate_template(whatsapp_number, "Back to Home", supabase)
                                    }
                                }
                            ]
                        }
                    }
                }
            else:
                # For regular bookings, show reschedule/cancel buttons
                payload = {
                    "messaging_product": "whatsapp",
                    "to": whatsapp_number,
                    "type": "interactive",
                    "interactive": {
                        "type": "button",
                        "body": {
                            "text": translate_template(
                                whatsapp_number,
                                "Selected: {}",
                                supabase
                            ).format(translate_template(whatsapp_number, selected_booking['text'], supabase))
                        },
                        "action": {
                            "buttons": [
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": f"reschedule_{booking_id}",
                                        "title": translate_template(whatsapp_number, "Reschedule", supabase)
                                    }
                                },
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": f"cancel_{booking_id}",
                                        "title": translate_template(whatsapp_number, "Cancel Booking", supabase)
                                    }
                                },
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": "back_to_home",
                                        "title": translate_template(whatsapp_number, "Back to Home", supabase)
                                    }
                                }
                            ]
                        }
                    }
                }
            
            send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
            user_data[whatsapp_number]["state"] = "SELECT_ACTION"
            return False
            
    except Exception as e:
        logger.error(f"Error in handle_booking_selection_for_reschedule for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing booking selection. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def check_repeated_visit(booking, supabase):
    """Check if a booking is part of a repeated visit series."""
    try:
        module = booking.get("module", "conventional")
        booking_id = booking.get("id", "")
        
        # Extract original ID by removing prefix
        prefixes = ["con_", "chk_", "vac_", "pen_", "res_", "tcm_"]
        original_id = booking_id
        for prefix in prefixes:
            if original_id.startswith(prefix):
                original_id = original_id[len(prefix):]
                break
        
        # FIRST: Check if booking itself has repeated_visit_uuid
        repeated_visit_uuid = booking.get("repeated_visit_uuid")
        
        if repeated_visit_uuid:
            # Check if there are other bookings with the same UUID
            if module == "tcm":
                # Query tcm_s_bookings table
                repeated_bookings = supabase.table("tcm_s_bookings").select(
                    "id"
                ).eq("repeated_visit_uuid", repeated_visit_uuid).neq("id", original_id).execute().data
            else:
                # Query conventional tables
                repeated_bookings = supabase.table("c_s_consultation").select(
                    "id"
                ).eq("repeated_visit_uuid", repeated_visit_uuid).neq("id", original_id).execute().data
            
            if repeated_bookings and len(repeated_bookings) > 0:
                return {
                    "is_repeated": True,
                    "repeated_visit_uuid": repeated_visit_uuid,
                    "total_repeated_count": len(repeated_bookings) + 1  # +1 for current booking
                }
        
        return {"is_repeated": False}
        
    except Exception as e:
        logger.error(f"Error checking repeated visit: {e}")
        return {"is_repeated": False}

def handle_booking_action(whatsapp_number, user_id, supabase, user_data, message):
    """Handle booking actions (reschedule, cancel, accept, decline)."""
    try:
        if message["type"] == "interactive" and message["interactive"]["type"] == "button_reply":
            action_id = message["interactive"]["button_reply"]["id"]
            
            # Handle back to home
            if action_id == "back_to_home":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Returning to main menu.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False
            
            # Check if this is an ambulance booking
            selected_booking = user_data[whatsapp_number].get("selected_booking", {})
            module = selected_booking.get("module", "conventional")
            
            # Handle ambulance bookings differently
            if module == "ambulance":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        "Ambulance bookings cannot be rescheduled or cancelled via WhatsApp. Please contact the ambulance service directly for any changes.",
                        supabase
                    )}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False
            
            # Extract the original UUID by removing prefixes
            booking_id = user_data[whatsapp_number].get("booking_id")
            table_name = user_data[whatsapp_number].get("table_name")
            booking_type = user_data[whatsapp_number].get("booking_type")
            
            prefixes = ["con_", "chk_", "vac_", "pen_", "res_", "tcm_"]
            original_id = booking_id
            for prefix in prefixes:
                if original_id.startswith(prefix):
                    original_id = original_id[len(prefix):]
                    break
            
            # Check if this booking is part of a repeated visit
            repeated_check = check_repeated_visit(selected_booking, supabase)
            is_repeated = repeated_check.get("is_repeated", False)
            repeated_visit_uuid = repeated_check.get("repeated_visit_uuid")
            
            # Store repeated visit info in user_data
            if is_repeated:
                user_data[whatsapp_number]["is_repeated"] = True
                user_data[whatsapp_number]["repeated_visit_uuid"] = repeated_visit_uuid
                user_data[whatsapp_number]["repeated_visit_data"] = repeated_check.get("repeated_visit_data")
            
            # Handle accept action for reschedule requests
            if action_id.startswith("accept_"):
                reschedule_id = action_id[7:]
                
                # Check if this is a TCM booking
                if user_data[whatsapp_number].get("table_name") == "tcm_s_bookings":
                    return handle_accept_tcm_reschedule(whatsapp_number, user_id, supabase, user_data, reschedule_id)
                else:
                    return handle_accept_reschedule(whatsapp_number, user_id, supabase, user_data, reschedule_id)

            # Handle decline action for reschedule requests
            elif action_id.startswith("decline_"):
                reschedule_id = action_id[8:]
                
                # Check if this is a TCM booking
                if user_data[whatsapp_number].get("table_name") == "tcm_s_bookings":
                    return handle_decline_tcm_reschedule(whatsapp_number, user_id, supabase, user_data, reschedule_id)
                else:
                    return handle_decline_reschedule(whatsapp_number, user_id, supabase, user_data, reschedule_id)
            
            # Handle reschedule action
            elif action_id.startswith("reschedule_"):
                # Check if this is a repeated visit
                if is_repeated:
                    # For repeated visits, we only reschedule the selected instance
                    # Show confirmation that only this instance will be rescheduled
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": whatsapp_number,
                        "type": "interactive",
                        "interactive": {
                            "type": "button",
                            "body": {
                                "text": translate_template(
                                    whatsapp_number,
                                    "This is part of a repeated visit series. Only this specific appointment will be rescheduled. Continue?",
                                    supabase
                                )
                            },
                            "action": {
                                "buttons": [
                                    {
                                        "type": "reply",
                                        "reply": {
                                            "id": f"confirm_one_{booking_id}",
                                            "title": translate_template(whatsapp_number, "Reschedule One", supabase)
                                        }
                                    },
                                    {
                                        "type": "reply",
                                        "reply": {
                                            "id": "back_to_actions",
                                            "title": translate_template(whatsapp_number, "Back", supabase)
                                        }
                                    }
                                ]
                            }
                        }
                    }
                    send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
                    user_data[whatsapp_number]["state"] = "CONFIRM_REPEATED_RESCHEDULE"
                    return False
                else:
                    # Proceed with normal reschedule flow
                    if table_name == "tcm_s_bookings":
                        # Start TCM reschedule flow
                        return start_tcm_reschedule_flow(whatsapp_number, user_id, supabase, user_data, original_id)
                    else:
                        # Conventional logic remains the same
                        user_data[whatsapp_number]["state"] = "SELECT_DOCTOR"
                        user_data[whatsapp_number]["module"] = "view_booking"
                        user_data[whatsapp_number]["clinic_id"] = user_data[whatsapp_number].get("clinic_id", "76d39438-a2c4-4e79-83e8-000000000000")
                        user_data[whatsapp_number]["service_id"] = "others"
                        get_doctors(whatsapp_number, user_id, supabase, user_data, "view_booking")
                    return False
            
            # Handle cancel action
            elif action_id.startswith("cancel_"):
                return handle_cancel_booking_action(whatsapp_number, user_id, supabase, user_data, original_id, table_name, booking_type, repeated_visit_uuid)
    
    except Exception as e:
        logger.error(f"Error in handle_booking_action for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing action. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def start_tcm_reschedule_flow(whatsapp_number, user_id, supabase, user_data, original_id):
    """Start the TCM reschedule flow."""
    try:
        logger.info(f"Starting TCM reschedule flow for booking ID: {original_id}")
        
        # Set module and TCM flag
        user_data[whatsapp_number]["module"] = "view_booking"
        user_data[whatsapp_number]["is_tcm"] = True
        
        # Get clinic_id and service_id if not already set
        clinic_id = user_data[whatsapp_number].get("clinic_id")
        if not clinic_id:
            # Try to get from selected booking
            clinic_id = user_data[whatsapp_number].get("selected_booking", {}).get("clinic_id")
            user_data[whatsapp_number]["clinic_id"] = clinic_id
        
        # If still no clinic_id, try to get it from the database
        if not clinic_id:
            try:
                booking_details = supabase.table("tcm_s_bookings") \
                    .select("service_id, doctor_id") \
                    .eq("id", original_id) \
                    .single() \
                    .execute()
                
                if booking_details.data:
                    # Store service_id
                    service_id = booking_details.data.get("service_id")
                    user_data[whatsapp_number]["service_id"] = service_id
                    
                    # Try to get clinic_id from service
                    if service_id:
                        try:
                            service_clinic = supabase.table("tcm_a_clinic_service") \
                                .select("clinic_id") \
                                .eq("id", service_id) \
                                .single() \
                                .execute()
                            if service_clinic.data:
                                clinic_id = service_clinic.data.get("clinic_id")
                                user_data[whatsapp_number]["clinic_id"] = clinic_id
                        except Exception as e:
                            logger.warning(f"Could not get clinic from service: {e}")
                    
                    # If still no clinic_id, try to get from doctor
                    if not clinic_id:
                        doctor_id = booking_details.data.get("doctor_id")
                        if doctor_id:
                            try:
                                doctor_clinic = supabase.table("tcm_a_doctors") \
                                    .select("clinic_id") \
                                    .eq("id", doctor_id) \
                                    .single() \
                                    .execute()
                                if doctor_clinic.data:
                                    clinic_id = doctor_clinic.data.get("clinic_id")
                                    user_data[whatsapp_number]["clinic_id"] = clinic_id
                            except Exception as e:
                                logger.warning(f"Could not get clinic from doctor: {e}")
            except Exception as e:
                logger.error(f"Error fetching booking details for TCM booking: {e}")
        
        # Ensure service_id is set
        if not user_data[whatsapp_number].get("service_id"):
            user_data[whatsapp_number]["service_id"] = "others"
        
        # Check if clinic allows doctor selection
        if clinic_id and get_clinic_doctor_selection(supabase, clinic_id):
            user_data[whatsapp_number]["state"] = "SELECT_DOCTOR"
            get_tcm_doctors(whatsapp_number, user_id, supabase, user_data, "view_booking")
        else:
            user_data[whatsapp_number]["state"] = "SELECT_DATE"
            user_data[whatsapp_number]["doctor_id"] = None
            user_data[whatsapp_number]["any_doctor"] = False
            get_tcm_calendar(whatsapp_number, user_id, supabase, user_data, "view_booking")
        
        return False
        
    except Exception as e:
        logger.error(f"Error starting TCM reschedule flow for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error starting reschedule process. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def handle_accept_reschedule(whatsapp_number, user_id, supabase, user_data, reschedule_id):
    """Handle accepting a reschedule request."""
    try:
        reschedule_data = supabase.table("c_s_reschedule_requests").select("*").eq("id", reschedule_id).execute().data
        
        if not reschedule_data or not (reschedule_data[0].get("new_date") and reschedule_data[0].get("new_time")):
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nReschedule request not found or has invalid data. Please try again.", supabase)}},
                supabase
            )
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False
        
        data = reschedule_data[0]
        
        # Map booking types to table names
        table_map = {
            "consultation": "c_s_consultation",
            "checkup": "c_s_checkup",
            "vaccination": "c_s_vaccination"
        }
        
        table = table_map.get(data["booking_type"])
        if not table:
            logger.error(f"Invalid booking type {data['booking_type']} for reschedule request {reschedule_id}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nInvalid booking type for reschedule request.", supabase)}},
                supabase
            )
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False
        
        # Create new booking with rescheduled date/time
        booking_data = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "doctor_id": data["doctor_id"],
            "date": data["new_date"],
            "time": data["new_time"],
            "duration_minutes": data["duration_minutes"],
            "reminder_duration": data.get("reminder_duration"),
            "reminder_remark": data.get("reminder_remark"),
            "repeated_visit_uuid": data.get("repeated_visit_uuid"),
            "created_at": datetime.now().isoformat()
        }
        
        if table in ["c_s_consultation", "c_s_checkup"]:
            booking_data["details"] = data.get("details") or 'General'
        elif table == "c_s_vaccination":
            booking_data["vaccine_type"] = data.get("vaccine_type") or ''
        
        # Insert new booking and delete reschedule request
        supabase.table(table).insert(booking_data).execute()
        supabase.table("c_s_reschedule_requests").delete().eq("id", reschedule_id).execute()
        
        # Send success message
        booking_type_translated = translate_template(whatsapp_number, data['booking_type'].capitalize(), supabase)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(
                whatsapp_number,
                "✅ ACCEPTED RESCHEDULE\n\nYou have accepted the reschedule. Your {} is now confirmed on {} at {}.",
                supabase
            ).format(
                booking_type_translated,
                data['new_date'],
                data['new_time']
            )}},
            supabase
        )
        
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return True
        
    except Exception as e:
        logger.error(f"Error accepting reschedule for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nError accepting reschedule. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def handle_decline_reschedule(whatsapp_number, user_id, supabase, user_data, reschedule_id):
    """Handle declining a reschedule request."""
    try:
        supabase.table("c_s_reschedule_requests").delete().eq("id", reschedule_id).execute()
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "✅ DECLINED RESCHEDULE\n\nYou have declined the reschedule request.", supabase)}},
            supabase
        )
        
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False
        
    except Exception as e:
        logger.error(f"Error declining reschedule for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nError declining reschedule. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def handle_accept_tcm_reschedule(whatsapp_number, user_id, supabase, user_data, booking_id):
    """Handle accepting a TCM reschedule request from doctor."""
    try:
        # Get the booking from tcm_s_bookings
        booking_data = supabase.table("tcm_s_bookings").select("*").eq("id", booking_id).execute().data
        
        if not booking_data or not (booking_data[0].get("new_date") and booking_data[0].get("new_time")):
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nReschedule request not found or has invalid data. Please try again.", supabase)}},
                supabase
            )
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False
        
        data = booking_data[0]
        
        # Update the booking: move new date/time to original, clear new fields, set status to confirmed
        update_data = {
            "original_date": data["new_date"],  # Move new_date to original_date
            "original_time": data["new_time"],  # Move new_time to original_time
            "new_date": None,  # Clear new_date
            "new_time": None,  # Clear new_time
            "status": "confirmed",  # Set to confirmed
            "updated_at": datetime.now().isoformat()
        }
        
        supabase.table("tcm_s_bookings").update(update_data).eq("id", booking_id).execute()
        
        # Get doctor name for success message
        try:
            doctor_response = supabase.table("tcm_a_doctors").select("name").eq("id", data["doctor_id"]).execute().data
            doctor_name = doctor_response[0]["name"] if doctor_response else "TCM Doctor"
        except Exception as e:
            logger.error(f"Error fetching TCM doctor name: {e}")
            doctor_name = translate_template(whatsapp_number, "TCM Doctor", supabase)
        
        # Send success message
        booking_type_translated = translate_template(whatsapp_number, data['booking_type'].capitalize(), supabase)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(
                whatsapp_number,
                "✅ TCM RESCHEDULE ACCEPTED\n\nYou have accepted the reschedule. Your TCM {} is now confirmed on {} at {} with Dr. {}.",
                supabase
            ).format(
                booking_type_translated,
                data['new_date'],
                data['new_time'],
                doctor_name
            )}},
            supabase
        )
        
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return True
        
    except Exception as e:
        logger.error(f"Error accepting TCM reschedule for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nError accepting TCM reschedule. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def handle_decline_tcm_reschedule(whatsapp_number, user_id, supabase, user_data, booking_id):
    """Handle declining a TCM reschedule request from doctor."""
    try:
        # Update the booking: clear new fields, keep original date/time, set status back to confirmed
        update_data = {
            "new_date": None,  # Clear new_date
            "new_time": None,  # Clear new_time
            "status": "confirmed",  # Return to confirmed status with original time
            "updated_at": datetime.now().isoformat()
        }
        
        supabase.table("tcm_s_bookings").update(update_data).eq("id", booking_id).execute()
        
        # Get original booking details for message
        booking_data = supabase.table("tcm_s_bookings").select("original_date, original_time, booking_type, doctor_id").eq("id", booking_id).execute().data
        
        if booking_data:
            data = booking_data[0]
            # Get doctor name
            try:
                doctor_response = supabase.table("tcm_a_doctors").select("name").eq("id", data["doctor_id"]).execute().data
                doctor_name = doctor_response[0]["name"] if doctor_response else "TCM Doctor"
            except Exception as e:
                logger.error(f"Error fetching TCM doctor name: {e}")
                doctor_name = translate_template(whatsapp_number, "TCM Doctor", supabase)
            
            booking_type_translated = translate_template(whatsapp_number, data['booking_type'].capitalize(), supabase)
            
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "✅ TCM RESCHEDULE DECLINED\n\nYou have declined the reschedule request. Your TCM {} remains confirmed on {} at {} with Dr. {}.",
                    supabase
                ).format(
                    booking_type_translated,
                    data['original_date'],
                    data['original_time'],
                    doctor_name
                )}},
                supabase
            )
        else:
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "✅ TCM RESCHEDULE DECLINED\n\nYou have declined the reschedule request.", supabase)}},
                supabase
            )
        
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False
        
    except Exception as e:
        logger.error(f"Error declining TCM reschedule for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nError declining TCM reschedule. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def handle_cancel_booking_action(whatsapp_number, user_id, supabase, user_data, original_id, table_name, booking_type, repeated_visit_uuid=None):
    """Handle canceling a booking."""
    try:
        # Check if this is a repeated visit AND we're not already in CONFIRM_REPEATED_CANCEL state
        current_state = user_data[whatsapp_number].get("state")
        if repeated_visit_uuid and current_state != "CONFIRM_REPEATED_CANCEL":
            # For repeated visits, we need to handle differently
            # Check if there are other bookings with the same repeated_visit_uuid
            
            try:
                # Query to find all bookings with the same repeated_visit_uuid
                if table_name in ["c_s_consultation", "c_s_checkup", "c_s_vaccination", "tcm_s_bookings", "c_s_pending_bookings"]:
                    # FIX: Use proper SQL syntax for aliases
                    if table_name == "tcm_s_bookings":
                        # TCM bookings - use original_date/original_time columns
                        repeated_bookings = supabase.table(table_name).select(
                            "id, original_date, original_time"  # Remove the alias - we'll handle it in Python
                        ).eq("user_id", user_id).eq("repeated_visit_uuid", repeated_visit_uuid).execute().data
                        
                        # Map the TCM column names to match conventional format
                        for booking in repeated_bookings:
                            booking['date'] = booking.get('original_date')
                            booking['time'] = booking.get('original_time')
                    else:
                        # Conventional bookings
                        repeated_bookings = supabase.table(table_name).select(
                            "id, date, time"
                        ).eq("user_id", user_id).eq("repeated_visit_uuid", repeated_visit_uuid).execute().data
                else:
                    repeated_bookings = []
                
                logger.info(f"Found {len(repeated_bookings)} repeated bookings for UUID {repeated_visit_uuid}")
                
                # IMPORTANT: Exclude the current booking from the count
                # The query above returns ALL bookings with the UUID, including the current one
                # We need to count only OTHER bookings (not the one being cancelled)
                other_repeated_bookings = [b for b in repeated_bookings if str(b['id']) != original_id]
                
                logger.info(f"Found {len(other_repeated_bookings)} OTHER repeated bookings (excluding current)")
                
                if len(other_repeated_bookings) > 0:
                    # There are other repeated bookings
                    # Ask user if they want to cancel just this one or all future repeated bookings
                    
                    # Get the current booking ID with prefix
                    booking_id = user_data[whatsapp_number].get("booking_id", "")
                    
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": whatsapp_number,
                        "type": "interactive",
                        "interactive": {
                            "type": "button",
                            "body": {
                                "text": translate_template(
                                    whatsapp_number,
                                    "⚠️ REPEATED VISIT CANCELLATION\n\nThis is part of a repeated visit series. Do you want to cancel just this booking or all future repeated bookings?",
                                    supabase
                                )
                            },
                            "action": {
                                "buttons": [
                                    {
                                        "type": "reply",
                                        "reply": {
                                            "id": f"cancel_single_{original_id}_{table_name.replace('_', '-')}_{booking_type}",
                                            "title": translate_template(whatsapp_number, "Cancel This One Only", supabase)
                                        }
                                    },
                                    {
                                        "type": "reply",
                                        "reply": {
                                            "id": f"cancel_all_{repeated_visit_uuid}_{table_name.replace('_', '-')}_{booking_type}",
                                            "title": translate_template(whatsapp_number, "Cancel All Repeated", supabase)
                                        }
                                    },
                                    {
                                        "type": "reply",
                                        "reply": {
                                            "id": "cancel_action",
                                            "title": translate_template(whatsapp_number, "Back", supabase)
                                        }
                                    }
                                ]
                            }
                        }
                    }
                    send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
                    user_data[whatsapp_number]["state"] = "CONFIRM_REPEATED_CANCEL"
                    return False
                else:
                    logger.info(f"No other repeated bookings found for UUID {repeated_visit_uuid}")
                    
            except Exception as e:
                logger.error(f"Error checking repeated bookings: {e}")
                # Continue with normal cancellation if error
        
        # Normal cancellation flow
        return handle_normal_cancellation(whatsapp_number, user_id, supabase, user_data, original_id, table_name, booking_type)
        
    except Exception as e:
        logger.error(f"Error in handle_cancel_booking_action for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nError cancelling booking. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def handle_normal_cancellation(whatsapp_number, user_id, supabase, user_data, original_id, table_name, booking_type):
    """Handle normal booking cancellation."""
    try:
        # For TCM bookings, update status to 'cancelled' instead of deleting
        if table_name == "tcm_s_bookings":
            update_data = {
                "status": "cancelled",
                "updated_at": datetime.now().isoformat()
            }
            supabase.table(table_name).update(update_data).eq("id", original_id).execute()
            logger.info(f"Cancelled TCM booking {original_id} by setting status to cancelled for {whatsapp_number}")
        else:
            # For conventional bookings, delete the record
            booking_exists = supabase.table(table_name).select("id").eq("id", original_id).execute().data
            if not booking_exists:
                logger.warning(f"Booking {original_id} in table {table_name} not found for {whatsapp_number}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "❌ CANCELLATION FAILED\n\nBooking not found. It may have already been cancelled.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False
            
            # Delete the booking
            supabase.table(table_name).delete().eq("id", original_id).execute()
            logger.info(f"Cancelled booking {original_id} from {table_name} for {whatsapp_number}")
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "✅ BOOKING CANCELLED\n\nYour booking has been successfully cancelled.", supabase)}},
            supabase
        )
        
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False
        
    except Exception as e:
        logger.error(f"Error canceling booking for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nError cancelling booking. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def handle_repeated_reschedule_confirmation(whatsapp_number, user_id, supabase, user_data, message):
    """Handle confirmation for repeated visit reschedule."""
    try:
        if message["type"] == "interactive" and message["interactive"]["type"] == "button_reply":
            action_id = message["interactive"]["button_reply"]["id"]
            
            if action_id == "back_to_actions":
                # Go back to action selection
                selected_booking = user_data[whatsapp_number].get("selected_booking", {})
                booking_id = user_data[whatsapp_number].get("booking_id", "")
                
                # Send action buttons again
                payload = {
                    "messaging_product": "whatsapp",
                    "to": whatsapp_number,
                    "type": "interactive",
                    "interactive": {
                        "type": "button",
                        "body": {
                            "text": translate_template(
                                whatsapp_number,
                                "Selected: {}",
                                supabase
                            ).format(translate_template(whatsapp_number, selected_booking.get('text', ''), supabase))
                        },
                        "action": {
                            "buttons": [
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": f"reschedule_{booking_id}",
                                        "title": translate_template(whatsapp_number, "Reschedule", supabase)
                                    }
                                },
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": f"cancel_{booking_id}",
                                        "title": translate_template(whatsapp_number, "Cancel Booking", supabase)
                                    }
                                },
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": "back_to_home",
                                        "title": translate_template(whatsapp_number, "Back to Home", supabase)
                                    }
                                }
                            ]
                        }
                    }
                }
                send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
                user_data[whatsapp_number]["state"] = "SELECT_ACTION"
                return False
            
            elif action_id.startswith("confirm_one_"):
                # Proceed with reschedule flow - extract the full booking_id
                full_booking_id = action_id[12:]  # Remove "confirm_one_" prefix
                logger.info(f"Processing reschedule confirmation for booking: {full_booking_id}")
                
                # Extract original ID without "tcm_" prefix
                if full_booking_id.startswith("tcm_"):
                    original_id = full_booking_id[4:]  # Remove "tcm_" prefix
                else:
                    original_id = full_booking_id
                
                # CRITICAL FIX: Don't re-check for repeated visits here - we already did that
                # Just start the TCM reschedule flow directly
                return start_tcm_reschedule_flow(whatsapp_number, user_id, supabase, user_data, original_id)
    
    except Exception as e:
        logger.error(f"Error in handle_repeated_reschedule_confirmation for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error processing reschedule confirmation. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def handle_repeated_cancellation_confirmation(whatsapp_number, user_id, supabase, user_data, message):
    """Handle confirmation for repeated visit cancellation."""
    try:
        logger.info(f"handle_repeated_cancellation_confirmation called for {whatsapp_number}")
        
        if message["type"] == "interactive" and message["interactive"]["type"] == "button_reply":
            action_id = message["interactive"]["button_reply"]["id"]
            logger.info(f"Action ID: {action_id}")
            
            if action_id == "cancel_action":
                logger.info("Handling cancel_action (Back button)")
                # Go back to action selection
                selected_booking = user_data[whatsapp_number].get("selected_booking", {})
                
                # Send action buttons again
                payload = {
                    "messaging_product": "whatsapp",
                    "to": whatsapp_number,
                    "type": "interactive",
                    "interactive": {
                        "type": "button",
                        "body": {
                            "text": translate_template(
                                whatsapp_number,
                                "Selected: {}",
                                supabase
                            ).format(translate_template(whatsapp_number, selected_booking.get('text', ''), supabase))
                        },
                        "action": {
                            "buttons": [
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": f"reschedule_{user_data[whatsapp_number].get('booking_id')}",
                                        "title": translate_template(whatsapp_number, "Reschedule", supabase)
                                    }
                                },
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": f"cancel_{user_data[whatsapp_number].get('booking_id')}",
                                        "title": translate_template(whatsapp_number, "Cancel Booking", supabase)
                                    }
                                },
                                {
                                    "type": "reply",
                                    "reply": {
                                        "id": "back_to_home",
                                        "title": translate_template(whatsapp_number, "Back to Home", supabase)
                                    }
                                }
                            ]
                        }
                    }
                }
                send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
                user_data[whatsapp_number]["state"] = "SELECT_ACTION"
                logger.info(f"State updated to SELECT_ACTION for {whatsapp_number}")
                return False
            
            elif action_id.startswith("cancel_single_"):
                logger.info(f"Handling cancel_single: {action_id}")
                # Cancel single booking only
                parts = action_id.split("_")
                logger.info(f"Parts: {parts}, Length: {len(parts)}")
                
                if len(parts) >= 5:
                    booking_id = parts[2]
                    table_name = parts[3].replace('-', '_')  # Convert hyphens back to underscores
                    booking_type = parts[4]
                    
                    logger.info(f"Parsed: booking_id={booking_id}, table_name={table_name}, booking_type={booking_type}")
                    
                    return handle_normal_cancellation(whatsapp_number, user_id, supabase, user_data, booking_id, table_name, booking_type)
                else:
                    logger.error(f"Invalid cancel_single button format: {action_id}. Parts: {parts}")
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nError processing cancellation. Please try again.", supabase)}},
                        supabase
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return False
            
            elif action_id.startswith("cancel_all_"):
                logger.info(f"Handling cancel_all: {action_id}")
                # Cancel all repeated bookings
                parts = action_id.split("_")
                logger.info(f"Parts: {parts}, Length: {len(parts)}")
                
                if len(parts) >= 5:
                    repeated_visit_uuid = parts[2]
                    table_name = parts[3].replace('-', '_')  # Convert hyphens back to underscores
                    booking_type = parts[4]
                    
                    logger.info(f"Parsed: repeated_visit_uuid={repeated_visit_uuid}, table_name={table_name}, booking_type={booking_type}")
                    
                    return handle_cancel_all_repeated(whatsapp_number, user_id, supabase, user_data, repeated_visit_uuid, table_name, booking_type)
                else:
                    logger.error(f"Invalid cancel_all button format: {action_id}. Parts: {parts}")
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nError processing cancellation. Please try again.", supabase)}},
                        supabase
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return False
            
            else:
                logger.error(f"Unrecognized action_id in repeated cancellation: {action_id}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nError processing cancellation. Please try again.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False
    
    except Exception as e:
        logger.error(f"Error in handle_repeated_cancellation_confirmation for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nError processing cancellation. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def handle_cancel_all_repeated(whatsapp_number, user_id, supabase, user_data, repeated_visit_uuid, table_name, booking_type):
    """Cancel all bookings with the same repeated_visit_uuid."""
    try:
        # For TCM, update status to 'cancelled' for all repeated bookings
        if table_name == "tcm_s_bookings":
            update_data = {
                "status": "cancelled",
                "updated_at": datetime.now().isoformat()
            }
            supabase.table(table_name).update(update_data).eq("repeated_visit_uuid", repeated_visit_uuid).eq("user_id", user_id).execute()
            logger.info(f"Cancelled all repeated TCM bookings with uuid {repeated_visit_uuid} from {table_name} for {whatsapp_number}")
        else:
            # Delete all bookings with the same repeated_visit_uuid
            supabase.table(table_name).delete().eq("repeated_visit_uuid", repeated_visit_uuid).eq("user_id", user_id).execute()
            logger.info(f"Cancelled all repeated bookings with uuid {repeated_visit_uuid} from {table_name} for {whatsapp_number}")
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "✅ ALL REPEATED BOOKINGS CANCELLED\n\nAll repeated bookings in this series have been cancelled.", supabase)}},
            supabase
        )
        
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False
        
    except Exception as e:
        logger.error(f"Error canceling all repeated bookings for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nError cancelling repeated bookings. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def handle_reschedule_flow(whatsapp_number, user_id, supabase, user_data, message):
    """Handle the complete reschedule flow including doctor selection."""
    try:
        state = user_data[whatsapp_number].get("state")
        is_tcm = user_data[whatsapp_number].get("is_tcm", False)  # Check flag
        
        logger.info(f"handle_reschedule_flow called for {whatsapp_number}, state: {state}, is_tcm: {is_tcm}")

        # Handle doctor selection
        if state == "SELECT_DOCTOR":
            if is_tcm:
                clinic_id = user_data[whatsapp_number].get("clinic_id")
                if not get_clinic_doctor_selection(supabase, clinic_id):
                    user_data[whatsapp_number]["state"] = "SELECT_DATE"
                    user_data[whatsapp_number]["doctor_id"] = None
                    user_data[whatsapp_number]["any_doctor"] = False
                    get_tcm_calendar(whatsapp_number, user_id, supabase, user_data, "view_booking")
                    return False
            if message["type"] == "interactive" and message["interactive"]["type"] == "list_reply":
                selected_doctor = message["interactive"]["list_reply"]["id"]
                
                if selected_doctor == "any_doctor":
                    user_data[whatsapp_number]["any_doctor"] = True
                    user_data[whatsapp_number].pop("doctor_id", None)
                else:
                    user_data[whatsapp_number]["doctor_id"] = selected_doctor
                    user_data[whatsapp_number]["any_doctor"] = False
                
                user_data[whatsapp_number]["state"] = "SELECT_DATE"
                
                # === ROUTING ===
                if is_tcm:
                    get_tcm_calendar(whatsapp_number, user_id, supabase, user_data, "view_booking")
                else:
                    get_calendar(whatsapp_number, user_id, supabase, user_data, "view_booking")
                return False
        
        # Handle date selection
        elif state == "SELECT_DATE":
            if message["type"] == "interactive" and message["interactive"]["type"] == "list_reply":
                selected_date = message["interactive"]["list_reply"]["id"]
                
                if selected_date == "future_date":
                    user_data[whatsapp_number]["state"] = "AWAITING_FUTURE_DATE"
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {
                            "text": {
                                "body": translate_template(
                                    whatsapp_number, 
                                    "Please enter your preferred date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:", 
                                    supabase
                                )
                            }
                        },
                        supabase
                    )
                else:
                    user_data[whatsapp_number]["date"] = selected_date
                    user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
                    # === ROUTING ===
                    if is_tcm:
                        select_tcm_period(whatsapp_number, user_id, supabase, user_data, "view_booking")
                    else:
                        select_period(whatsapp_number, user_id, supabase, user_data, "view_booking")
                return False
        
        # Handle future date input - FIXED SECTION
        elif state == "AWAITING_FUTURE_DATE":
            logger.info(f"State AWAITING_FUTURE_DATE for {whatsapp_number}, is_tcm: {is_tcm}")
            
            if message["type"] == "text":
                date_input = message["text"]["body"].strip()
                logger.info(f"Processing future date input for {whatsapp_number}: {date_input}")
                
                # IMPORTANT FIX: Check if this is a TCM reschedule
                if is_tcm:
                    # For TCM, use the TCM calendar utils function
                    logger.info(f"Calling handle_tcm_future_date for TCM reschedule with date: {date_input}")
                    handle_tcm_future_date(whatsapp_number, user_id, supabase, user_data, "view_booking", date_input)
                else:
                    # For conventional, use regular calendar utils
                    logger.info(f"Calling handle_future_date_input for conventional reschedule with date: {date_input}")
                    handle_future_date_input(whatsapp_number, user_id, supabase, user_data, "view_booking", date_input)
                return False
            else:
                # If not text, remind user
                logger.warning(f"Unexpected message type in AWAITING_FUTURE_DATE: {message.get('type')}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {
                        "text": {
                            "body": translate_template(
                                whatsapp_number, 
                                "Please enter your preferred date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:", 
                                supabase
                            )
                        }
                    },
                    supabase
                )
                return False
        
        # Handle future date confirmation - FIXED SECTION
        elif state == "CONFIRM_FUTURE_DATE":
            logger.info(f"State CONFIRM_FUTURE_DATE for {whatsapp_number}, is_tcm: {is_tcm}")
            
            if message["type"] == "interactive" and message["interactive"]["type"] == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                confirmed = (button_id == "confirm_future_date")
                
                logger.info(f"Future date confirmation for {whatsapp_number}: {button_id}, confirmed={confirmed}, is_tcm={is_tcm}")
                
                if is_tcm:
                    handle_tcm_future_confirm(whatsapp_number, user_id, supabase, user_data, "view_booking", confirmed=confirmed)
                else:
                    handle_future_date_confirmation(whatsapp_number, user_id, supabase, user_data, "view_booking", confirmed=confirmed)
                return False
            else:
                # Resend confirmation buttons if not button reply
                logger.warning(f"Unexpected message type in CONFIRM_FUTURE_DATE: {message.get('type')}")
                date_obj = user_data[whatsapp_number].get("future_date_input")
                if date_obj:
                    send_whatsapp_message(
                        whatsapp_number,
                        "interactive",
                        {
                            "messaging_product": "whatsapp",
                            "to": whatsapp_number,
                            "type": "interactive",
                            "interactive": {
                                "type": "button",
                                "body": {
                                    "text": translate_template(
                                        whatsapp_number,
                                        "Selected date: {}. Confirm?",
                                        supabase
                                    ).format(date_obj.strftime("%d/%m/%Y"))
                                },
                                "action": {
                                    "buttons": [
                                        {
                                            "type": "reply",
                                            "reply": {
                                                "id": "confirm_future_date",
                                                "title": translate_template(whatsapp_number, "Confirm", supabase)
                                            }
                                        },
                                        {
                                            "type": "reply",
                                            "reply": {
                                                "id": "reject_future_date",
                                                "title": translate_template(whatsapp_number, "Choose Another", supabase)
                                            }
                                        }
                                    ]
                                }
                            }
                        },
                        supabase
                    )
                else:
                    # If no date object, go back to calendar
                    logger.error("No future_date_input found in CONFIRM_FUTURE_DATE state")
                    if is_tcm:
                        get_tcm_calendar(whatsapp_number, user_id, supabase, user_data, "view_booking")
                    else:
                        get_calendar(whatsapp_number, user_id, supabase, user_data, "view_booking")
                return False

        # Handle period selection
        elif state == "SELECT_PERIOD":
            if message["type"] == "interactive" and message["interactive"]["type"] == "button_reply":
                user_data[whatsapp_number]["period"] = message["interactive"]["button_reply"]["id"]
                user_data[whatsapp_number]["state"] = "SELECT_HOUR"
                if is_tcm:
                    get_tcm_hours(whatsapp_number, user_id, supabase, user_data, "view_booking")
                else:
                    get_available_hours(whatsapp_number, user_id, supabase, user_data, "view_booking")
                return False

        # Handle hour selection
        elif state == "SELECT_HOUR":
            if message["type"] == "interactive" and message["interactive"]["type"] == "list_reply":
                user_data[whatsapp_number]["hour"] = message["interactive"]["list_reply"]["id"]
                user_data[whatsapp_number]["state"] = "SELECT_TIME_SLOT"
                if is_tcm:
                    get_tcm_time_slots(whatsapp_number, user_id, supabase, user_data, "view_booking")
                else:
                    get_time_slots(whatsapp_number, user_id, supabase, user_data, "view_booking")
                return False

        # Handle time slot selection - CRITICAL FIX HERE
        elif state == "SELECT_TIME_SLOT":
            if message["type"] == "interactive" and message["interactive"]["type"] == "list_reply":
                selected_time = message["interactive"]["list_reply"]["id"]
                user_data[whatsapp_number]["time_slot"] = selected_time
                user_data[whatsapp_number]["new_time"] = selected_time
                user_data[whatsapp_number]["new_date"] = user_data[whatsapp_number]["date"]
                
                # FIXED: For TCM reschedule, we should NOT use confirm_tcm_doctor 
                # because it creates a NEW booking. Instead, go directly to confirmation.
                if is_tcm:
                    # Proceed directly to reschedule confirmation for TCM
                    return confirm_reschedule_booking(whatsapp_number, user_id, supabase, user_data)
                else:
                    # Conventional logic continues...
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": whatsapp_number,
                        "type": "interactive",
                        "interactive": {
                            "type": "button",
                            "body": {
                                "text": translate_template(
                                    whatsapp_number, 
                                    "Selected time: {}\n\nConfirm this time slot?", 
                                    supabase
                                ).format(selected_time)
                            },
                            "action": {
                                "buttons": [
                                    {
                                        "type": "reply",
                                        "reply": {
                                            "id": "confirm_time",
                                            "title": translate_template(whatsapp_number, "Confirm Time", supabase)
                                        }
                                    },
                                    {
                                        "type": "reply",
                                        "reply": {
                                            "id": "back_to_time_slots",
                                            "title": translate_template(whatsapp_number, "Find Another", supabase)
                                        }
                                    }
                                ]
                            }
                        }
                    }
                    send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
                    user_data[whatsapp_number]["state"] = "CONFIRM_TIME"
                    return False

        # Handle time confirmation
        elif state == "CONFIRM_TIME":
            if message["type"] == "interactive" and message["interactive"]["type"] == "button_reply":
                button_id = message["interactive"]["button_reply"]["id"]
                
                if button_id == "confirm_time":
                    # Proceed to final reschedule confirmation
                    return confirm_reschedule_booking(whatsapp_number, user_id, supabase, user_data)
                elif button_id == "back_to_time_slots":
                    # Go back to time slot selection
                    user_data[whatsapp_number]["state"] = "SELECT_TIME_SLOT"
                    # Check if TCM or conventional
                    is_tcm = user_data[whatsapp_number].get("is_tcm", False)
                    if is_tcm:
                        get_tcm_time_slots(whatsapp_number, user_id, supabase, user_data, "view_booking")
                    else:
                        get_time_slots(whatsapp_number, user_id, supabase, user_data, "view_booking")
                    return False
    
    except Exception as e:
        logger.error(f"Error in handle_reschedule_flow for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nError processing reschedule. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def confirm_reschedule_booking(whatsapp_number, user_id, supabase, user_data):
    """Confirm reschedule booking with user."""
    try:
        # Get doctor name
        doctor_id = user_data[whatsapp_number].get("doctor_id")
        is_tcm = user_data[whatsapp_number].get("is_tcm", False)
        any_doctor = user_data[whatsapp_number].get("any_doctor", False)
        
        if any_doctor:
            doctor_name = translate_template(whatsapp_number, "Any Doctor", supabase)
        else:
            if is_tcm:
                if doctor_id:
                    doctor_response = supabase.table("tcm_a_doctors").select("name").eq("id", doctor_id).execute().data
                    doctor_name = doctor_response[0]["name"] if doctor_response else "TCM Doctor"
                else:
                    doctor_name = translate_template(whatsapp_number, "TCM Doctor", supabase)
            else:
                if doctor_id:
                    doctor_response = supabase.table("c_a_doctors").select("name").eq("id", doctor_id).execute().data
                    doctor_name = doctor_response[0]["name"] if doctor_response else "Doctor"
                else:
                    doctor_name = translate_template(whatsapp_number, "Doctor", supabase)
        
        # Get original booking details
        selected_booking = user_data[whatsapp_number].get("selected_booking", {})
        booking_type = selected_booking.get("type", "appointment").capitalize()
        original_date = selected_booking.get("date") or selected_booking.get("original_date")
        original_time = selected_booking.get("time") or selected_booking.get("original_time")
        
        # Check if it's a repeated visit
        is_repeated = user_data[whatsapp_number].get("is_repeated", False)
        repeated_text = "\n⚠️ This is part of a repeated visit series. Only this specific appointment will be rescheduled." if is_repeated else ""
        
        # Prepare confirmation message
        confirmation_text = translate_template(
            whatsapp_number,
            "Confirm reschedule:{} \n\nOriginal Booking:\n• Type: {}\n• Date: {}\n• Time: {}\n\nNew Booking:\n• Doctor: {}\n• Date: {}\n• Time: {}\n• Duration: {} min",
            supabase
        ).format(
            repeated_text,
            booking_type,
            original_date,
            original_time,
            doctor_name,
            user_data[whatsapp_number]["new_date"],
            user_data[whatsapp_number]["new_time"],
            user_data[whatsapp_number].get("duration_minutes", 30)
        )
        
        send_whatsapp_message(
            whatsapp_number,
            "interactive",
            {
                "messaging_product": "whatsapp",
                "to": whatsapp_number,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": confirmation_text},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply", 
                                "reply": {
                                    "id": "confirm_reschedule", 
                                    "title": translate_template(whatsapp_number, "Confirm Reschedule", supabase)
                                }
                            },
                            {
                                "type": "reply", 
                                "reply": {
                                    "id": "cancel_reschedule", 
                                    "title": translate_template(whatsapp_number, "Cancel", supabase)
                                }
                            }
                        ]
                    }
                }
            },
            supabase
        )
        user_data[whatsapp_number]["state"] = "CONFIRM_RESCHEDULE"
        return False
        
    except Exception as e:
        logger.error(f"Error confirming reschedule for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "Error confirming reschedule. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def handle_reschedule_confirmation(whatsapp_number, user_id, supabase, user_data, message):
    """Handle confirmation of reschedule booking."""
    try:
        if message["type"] == "interactive" and message["interactive"]["type"] == "button_reply":
            action_id = message["interactive"]["button_reply"]["id"]
            
            if action_id == "cancel_reschedule":
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "❌ RESCHEDULE CANCELLED\n\nYour booking remains unchanged.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False
                
            elif action_id == "confirm_reschedule":
                # Save reschedule to database
                try:
                    success = save_reschedule_to_database(whatsapp_number, user_id, supabase, user_data)
                    if success:
                        return True  # Success message is already sent in save_reschedule_to_database
                    else:
                        # Error message is already sent in save_reschedule_to_database
                        return False
                except Exception as e:
                    logger.error(f"Error in reschedule confirmation for {whatsapp_number}: {e}", exc_info=True)
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "❌ RESCHEDULE FAILED\n\nAn error occurred while processing your reschedule request. Please try again or contact support.", supabase)}},
                        supabase
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return False
    
    except Exception as e:
        logger.error(f"Error in handle_reschedule_confirmation for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nAn unexpected error occurred. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def save_reschedule_to_database(whatsapp_number, user_id, supabase, user_data):
    """Save rescheduled booking to pending bookings table and delete the old one."""
    try:
        booking_data = user_data.get(whatsapp_number, {})
        
        # Check if booking_id exists (it might be missing if server restarted)
        if "booking_id" not in booking_data:
            logger.error(f"Missing booking_id for {whatsapp_number}. Session might have expired.")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "❌ SESSION EXPIRED\n\nPlease start the reschedule process again.", supabase)}},
                supabase
            )
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False
        
        # Get the original booking ID
        booking_id = booking_data['booking_id']
        prefixes = ["con_", "chk_", "vac_", "pen_", "res_", "tcm_"]
        original_id = booking_id
        for prefix in prefixes:
            if original_id.startswith(prefix):
                original_id = original_id[len(prefix):]
                break
        
        table_name = booking_data['table_name']
        booking_type = booking_data['booking_type']
        repeated_visit_uuid = booking_data.get('repeated_visit_uuid')
        is_repeated = booking_data.get('is_repeated', False)
        is_tcm = booking_data.get('is_tcm', False) or table_name == "tcm_s_bookings"
        
        # Check if this is a TCM booking
        if is_tcm:
            # Handle TCM booking reschedule
            try:
                success = save_tcm_reschedule_to_database(whatsapp_number, user_id, supabase, user_data, booking_data, original_id)
                return success  # Return success without sending error message
            except Exception as e:
                logger.error(f"Error in TCM reschedule save for {whatsapp_number}: {e}", exc_info=True)
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "", supabase).format(str(e))}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False
        
        # Prepare data for c_s_pending_bookings (conventional bookings)
        pending_booking_data = {
            "user_id": user_id,
            "booking_type": booking_type,
            "date": booking_data["new_date"],
            "time": booking_data["new_time"],
            "duration_minutes": booking_data["duration_minutes"],
            "reminder_duration": booking_data.get("reminder_duration"),
            "reminder_remark": booking_data.get("reminder_remark"),
            "created_at": datetime.now().isoformat()
        }
        
        # Handle doctor_id - check if user selected a specific doctor or "Any Doctor"
        any_doctor = booking_data.get("any_doctor", False)
        
        if any_doctor:
            # For "Any Doctor", we need to get a default doctor for the clinic
            selected_booking = booking_data.get("selected_booking", {})
            original_doctor_id = selected_booking.get("doctor_id")
            
            if original_doctor_id:
                pending_booking_data["doctor_id"] = original_doctor_id
            else:
                clinic_id = booking_data.get("clinic_id", "")
                if clinic_id:
                    try:
                        doctors_response = supabase.table("c_a_doctors").select(
                            "id"
                        ).eq("clinic_id", clinic_id).eq("is_active", True).limit(1).execute()
                        
                        if doctors_response.data and len(doctors_response.data) > 0:
                            pending_booking_data["doctor_id"] = doctors_response.data[0]["id"]
                        else:
                            doctors_response = supabase.table("c_a_doctors").select(
                                "id"
                            ).eq("clinic_id", clinic_id).limit(1).execute()
                            
                            if doctors_response.data and len(doctors_response.data) > 0:
                                pending_booking_data["doctor_id"] = doctors_response.data[0]["id"]
                    except Exception as e:
                        logger.error(f"Error fetching default doctor for clinic {clinic_id}: {e}")
        else:
            doctor_id = booking_data.get("doctor_id")
            if doctor_id:
                pending_booking_data["doctor_id"] = doctor_id
            else:
                selected_booking = booking_data.get("selected_booking", {})
                original_doctor_id = selected_booking.get("doctor_id")
                if original_doctor_id:
                    pending_booking_data["doctor_id"] = original_doctor_id
        
        if "doctor_id" not in pending_booking_data:
            logger.error(f"No doctor_id available for reschedule booking for {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number, 
                    "❌ UNABLE TO COMPLETE\n\nUnable to complete reschedule. No doctor information available. Please contact support.", 
                    supabase
                )}},
                supabase
            )
            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            return False
        
        # IMPORTANT: For repeated visit reschedule, we DON'T preserve repeated_visit_uuid
        # This breaks the repetition chain for this specific instance
        # Only set repeated_visit_uuid if NOT a repeated visit
        if not is_repeated:
            if repeated_visit_uuid:
                pending_booking_data["repeated_visit_uuid"] = repeated_visit_uuid
        else:
            # For repeated visit reschedule, set repeated_visit_uuid to NULL
            # This breaks the repetition for this specific instance
            pending_booking_data["repeated_visit_uuid"] = None

        # Add details or vaccine_type based on booking type
        if booking_type == "vaccination":
            pending_booking_data["vaccine_type"] = booking_data.get("vaccine_type") or "General"
            pending_booking_data["details"] = None
        else:
            pending_booking_data["details"] = booking_data.get("details") or "General"
            pending_booking_data["vaccine_type"] = None
        
        # Insert into c_s_pending_bookings
        try:
            supabase.table("c_s_pending_bookings").insert(pending_booking_data).execute()
        except Exception as e:
            # If the database table is missing the 'repeated_visit_uuid' column, try again without it
            error_msg = str(e)
            if "repeated_visit_uuid" in error_msg and "column" in error_msg:
                logger.warning("Column 'repeated_visit_uuid' missing in c_s_pending_bookings. Retrying without it.")
                pending_booking_data.pop("repeated_visit_uuid", None)
                supabase.table("c_s_pending_bookings").insert(pending_booking_data).execute()
            else:
                # If it's a different error, raise it so we know about it
                raise e

        # Delete original booking (from confirmed or pending tables)
        supabase.table(table_name).delete().eq("id", original_id).execute()
        
        # Get doctor name for success message
        try:
            doctor_response = supabase.table("c_a_doctors").select("name").eq("id", pending_booking_data["doctor_id"]).execute().data
            doctor_name = doctor_response[0]["name"] if doctor_response else "Doctor"
        except Exception as e:
            logger.error(f"Error fetching doctor name: {e}")
            doctor_name = translate_template(whatsapp_number, "Doctor", supabase)
        
        # Send success message
        booking_type_translated = translate_template(whatsapp_number, booking_type.capitalize(), supabase)
        repeated_text = " (Repeated Visit - This Instance Only)" if is_repeated else ""
        
        success_message = translate_template(
            whatsapp_number,
            "✅ RESCHEDULE SUCCESSFUL!{}\n\n{} rescheduled to {} at {} with Dr. {}.\n\nStatus: PENDING CONFIRMATION",
            supabase
        ).format(
            repeated_text,
            booking_type_translated,
            booking_data["new_date"],
            booking_data["new_time"],
            doctor_name
        )
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": success_message}},
            supabase
        )
        
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        logger.info(f"✅ Reschedule moved to pending bookings for {whatsapp_number}")
        return True

    except Exception as e:
        logger.error(f"Error saving reschedule to database for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "❌ DATABASE ERROR\n\nError saving reschedule. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def save_tcm_reschedule_to_database(whatsapp_number, user_id, supabase, user_data, booking_data, original_id):
    """Save TCM rescheduled booking to tcm_s_bookings table."""
    try:
        # Check if this is a repeated visit
        is_repeated = booking_data.get("is_repeated", False)
        repeated_visit_uuid = booking_data.get("repeated_visit_uuid")
        
        # For TCM bookings, we update the existing record with new date/time and set status to pending
        update_data = {
            "original_date": booking_data["new_date"],  # Update original date
            "original_time": booking_data["new_time"],  # Update original time
            "status": "pending",  # Set status to pending for admin confirmation
            "updated_at": datetime.now().isoformat()
        }
        
        # Handle doctor_id for TCM - check if user selected a specific doctor or "Any Doctor"
        any_doctor = booking_data.get("any_doctor", False)
        
        if not any_doctor:
            # User selected a specific doctor
            doctor_id = booking_data.get("doctor_id")
            if doctor_id:
                update_data["doctor_id"] = doctor_id
            else:
                # Fallback to original doctor_id from selected booking
                selected_booking = booking_data.get("selected_booking", {})
                original_doctor_id = selected_booking.get("doctor_id")
                if original_doctor_id:
                    update_data["doctor_id"] = original_doctor_id
        # If any_doctor is True, we keep the existing doctor_id in the database
        
        # Handle service_id if changed during reschedule
        service_id = booking_data.get("service_id")
        if service_id:
            update_data["service_id"] = service_id
        
        # IMPORTANT: For repeated visit reschedule, we DON'T preserve repeated_visit_uuid
        # This breaks the repetition chain for this specific instance
        # Only set repeated_visit_uuid if NOT a repeated visit
        if not is_repeated:
            if repeated_visit_uuid:
                update_data["repeated_visit_uuid"] = repeated_visit_uuid
        else:
            # For repeated visit reschedule, set repeated_visit_uuid to NULL
            # This breaks the repetition for this specific instance
            update_data["repeated_visit_uuid"] = None
        
        # Update the TCM booking - only affect original_date, original_time, status, and possibly service_id
        supabase.table("tcm_s_bookings").update(update_data).eq("id", original_id).execute()
        
        # Get doctor name for success message
        try:
            # Get the current doctor_id from the database to display the name
            tcm_booking_response = supabase.table("tcm_s_bookings").select("doctor_id").eq("id", original_id).execute().data
            if tcm_booking_response and tcm_booking_response[0].get("doctor_id"):
                doctor_id = tcm_booking_response[0]["doctor_id"]
                doctor_response = supabase.table("tcm_a_doctors").select("name").eq("id", doctor_id).execute().data
                doctor_name = doctor_response[0]["name"] if doctor_response else "TCM Doctor"
            else:
                doctor_name = translate_template(whatsapp_number, "TCM Doctor", supabase)
        except Exception as e:
            logger.error(f"Error fetching TCM doctor name: {e}")
            doctor_name = translate_template(whatsapp_number, "TCM Doctor", supabase)
        
        # Send success message
        booking_type_translated = translate_template(whatsapp_number, booking_data['booking_type'].capitalize(), supabase)
        
        # Check if it's a repeated visit
        repeated_text = " (Repeated Visit - This Instance Only)" if is_repeated else ""
        
        success_message = translate_template(
            whatsapp_number,
            "✅ TCM RESCHEDULE SUCCESSFUL!{}\n\nTCM {} rescheduled to {} at {} with Dr. {}.\n\nStatus: PENDING CONFIRMATION",
            supabase
        ).format(
            repeated_text,
            booking_type_translated,
            booking_data["new_date"],
            booking_data["new_time"],
            doctor_name
        )
        
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": success_message}},
            supabase
        )
        
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        logger.info(f"✅ TCM reschedule updated for {whatsapp_number}. Updated: original_date={booking_data['new_date']}, original_time={booking_data['new_time']}, status=pending")
        return True
        
    except Exception as e:
        logger.error(f"Error saving TCM reschedule to database for {whatsapp_number}: {e}", exc_info=True)
        raise e  # Re-raise to be caught by parent function

def handle_tcm_booking_confirmation(whatsapp_number, user_id, supabase, user_data, message):
    """Handle TCM booking confirmation specifically for view_booking reschedule flow."""
    try:
        if message["type"] == "interactive" and message["interactive"]["type"] == "button_reply":
            action_id = message["interactive"]["button_reply"]["id"]
            
            # Handle TCM confirmation from tcm_calendar_utils
            if action_id == "confirm_booking":
                # Get original booking details
                selected_booking = user_data[whatsapp_number].get("selected_booking", {})
                original_id = user_data[whatsapp_number].get("booking_id", "")
                
                # Remove "tcm_" prefix if present
                if original_id.startswith("tcm_"):
                    original_id = original_id[4:]
                
                # Call the TCM confirm booking handler
                result = handle_confirm_booking_tcm(whatsapp_number, user_id, supabase, user_data, "view_booking")
                
                # Check if the booking was successful
                if result:
                    # Get updated booking details for success message
                    try:
                        tcm_booking_response = supabase.table("tcm_s_bookings").select(
                            "original_date, original_time, booking_type, doctor_id"
                        ).eq("id", original_id).execute().data
                        
                        if tcm_booking_response:
                            booking = tcm_booking_response[0]
                            # Get doctor name
                            try:
                                doctor_response = supabase.table("tcm_a_doctors").select("name").eq("id", booking["doctor_id"]).execute().data
                                doctor_name = doctor_response[0]["name"] if doctor_response else "TCM Doctor"
                            except Exception as e:
                                logger.error(f"Error fetching TCM doctor name: {e}")
                                doctor_name = translate_template(whatsapp_number, "TCM Doctor", supabase)
                            
                            booking_type_translated = translate_template(whatsapp_number, booking['booking_type'].capitalize(), supabase)
                            
                            success_message = translate_template(
                                whatsapp_number,
                                "✅ TCM RESCHEDULE SUCCESSFUL!\n\nTCM {} rescheduled to {} at {} with Dr. {}.\n\nStatus: PENDING CONFIRMATION",
                                supabase
                            ).format(
                                booking_type_translated,
                                booking["original_date"],
                                booking["original_time"],
                                doctor_name
                            )
                            
                            send_whatsapp_message(
                                whatsapp_number,
                                "text",
                                {"text": {"body": success_message}},
                                supabase
                            )
                    except Exception as e:
                        logger.error(f"Error fetching updated TCM booking: {e}")
                        # Still send generic success message
                        send_whatsapp_message(
                            whatsapp_number,
                            "text",
                            {"text": {"body": translate_template(whatsapp_number, "✅ TCM RESCHEDULE SUCCESSFUL!\n\nYour TCM appointment has been rescheduled.\n\nStatus: PENDING CONFIRMATION", supabase)}},
                            supabase
                        )
                    
                    user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return True
                else:
                    # Only send error if handle_confirm_booking_tcm returned False
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "❌ TCM RESCHEDULE FAILED\n\nError rescheduling TCM appointment. Please try again.", supabase)}},
                        supabase
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return False
            
            elif action_id == "cancel_booking":
                # Call the TCM cancel booking handler
                result = handle_cancel_booking_tcm(whatsapp_number, user_id, supabase, user_data)
                
                if result:
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "❌ RESCHEDULE CANCELLED\n\nYour TCM booking reschedule has been cancelled.", supabase)}},
                        supabase
                    )
                else:
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nError cancelling TCM reschedule. Please try again.", supabase)}},
                        supabase
                    )
                
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False
    
    except Exception as e:
        logger.error(f"Error in handle_tcm_booking_confirmation for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "❌ ERROR\n\nAn unexpected error occurred. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

def send_back_to_home_options(whatsapp_number, supabase):
    """Send back to home options."""
    payload = {
        "messaging_product": "whatsapp",
        "to": whatsapp_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": translate_template(whatsapp_number, "What would you like to do next?", supabase)},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "back_to_home",
                            "title": translate_template(whatsapp_number, "Back to Home", supabase)
                        }
                    }
                ]
            }
        }
    }
    send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)

# Main handler function to route view_booking requests
def handle_view_booking(whatsapp_number, user_id, supabase, user_data, message):
    """Main handler for view_booking module."""
    try:
        state = user_data[whatsapp_number].get("state", "IDLE")
        
        # Route based on state
        if state == "VIEW_BOOKING_SUBMENU":
            # This state should no longer be used since we removed the submenu
            # Go directly to view upcoming bookings
            return handle_view_upcoming_booking(whatsapp_number, user_id, supabase, user_data)
        
        elif state == "SELECT_BOOKING_TYPE":
            return handle_booking_type_selection(whatsapp_number, user_id, supabase, user_data, message)
        
        elif state == "SELECT_BOOKING_FOR_RESCHEDULE":
            return handle_booking_selection_for_reschedule(whatsapp_number, user_id, supabase, user_data, message)
        
        elif state == "SELECT_ACTION":
            return handle_booking_action(whatsapp_number, user_id, supabase, user_data, message)
        
        elif state == "CONFIRM_REPEATED_CANCEL":
            return handle_repeated_cancellation_confirmation(whatsapp_number, user_id, supabase, user_data, message)
        
        elif state == "CONFIRM_REPEATED_RESCHEDULE":
            return handle_repeated_reschedule_confirmation(whatsapp_number, user_id, supabase, user_data, message)
        
        elif state == "CONFIRM_RESCHEDULE":
            return handle_reschedule_confirmation(whatsapp_number, user_id, supabase, user_data, message)
        
        elif state == "CONFIRM_BOOKING":
            # Handle TCM booking confirmation specifically
            return handle_tcm_booking_confirmation(whatsapp_number, user_id, supabase, user_data, message)
        
        elif state in ["SELECT_DOCTOR", "SELECT_DATE", "SELECT_PERIOD", "SELECT_HOUR", "SELECT_TIME_SLOT", 
                        "AWAITING_FUTURE_DATE", "CONFIRM_FUTURE_DATE", "CONFIRM_TIME"]:
            return handle_reschedule_flow(whatsapp_number, user_id, supabase, user_data, message)
        
        else:
            # Default: go directly to view upcoming bookings (skip submenu)
            return handle_view_upcoming_booking(whatsapp_number, user_id, supabase, user_data)
            
    except Exception as e:
        logger.error(f"Error in handle_view_booking for {whatsapp_number}: {e}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "❌ SYSTEM ERROR\n\nAn error occurred in the booking system. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False

