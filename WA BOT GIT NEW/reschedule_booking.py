import uuid
import logging
from datetime import datetime
from calendar_utils import get_calendar, select_period, get_available_hours, get_time_slots, handle_future_date_input, handle_future_date_confirmation
from utils import send_whatsapp_message, send_interactive_menu, translate_template, gt_t_tt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handle_reschedule(whatsapp_number, user_id, supabase, user_data, message):
    """SIMPLIFIED RESCHEDULE: Confirmed → Pending (SAME DOCTOR + NEW TIME ONLY)"""
    try:
        state = user_data.get(whatsapp_number, {}).get("state", "IDLE")

        if state == "IDLE" and message.get("type") == "interactive" and message["interactive"].get("type") == "list_reply" and message["interactive"]["list_reply"]["id"] == "reschedule_booking":
            # Fetch doctors dict
            doctors_data = supabase.table("doctors").select("id, name, clinic_id").execute().data
            doctors_dict = {str(d["id"]): d["name"] for d in doctors_data}
            clinic_dict = {str(d["id"]): d["clinic_id"] for d in doctors_data}

            # Query upcoming bookings for the user
            consultations = supabase.table("consultation").select("id, doctor_id, details, date, time, duration_minutes, reminder_duration, reminder_remark").eq("user_id", user_id).execute().data
            checkups = supabase.table("checkup").select("id, doctor_id, details, date, time, duration_minutes, reminder_duration, reminder_remark").eq("user_id", user_id).execute().data
            vaccinations = supabase.table("vaccination").select("id, doctor_id, vaccine_type, date, time, duration_minutes, reminder_duration, reminder_remark").eq("user_id", user_id).execute().data
            pending_bookings = supabase.table("pending_bookings").select("id, doctor_id, booking_type, details, vaccine_type, date, time, duration_minutes, reminder_duration, reminder_remark").eq("user_id", user_id).execute().data
            reschedule_requests = supabase.table("reschedule_requests").select("id, doctor_id, booking_type, details, vaccine_type, original_date, original_time, new_date, new_time, status, duration_minutes").eq("user_id", user_id).eq("status", "pending").execute().data

            # Current date and time for separating upcoming bookings
            current_date = datetime.now().date()
            current_time = datetime.now().time()

            # Format upcoming bookings into three categories
            action_required = []
            confirmed_bookings = []
            pending_bookings_list = []

            # ACTION REQUIRED (reschedule_requests)
            for r in reschedule_requests:
                if r.get("status") != "pending" or not (r.get("original_date") and r.get("original_time") and r.get("new_date") and r.get("new_time")):
                    logger.warning(f"Skipping reschedule request with invalid data: {r}")
                    continue
                try:
                    booking_date = datetime.strptime(r['original_date'], "%Y-%m-%d").date()
                    booking_time = datetime.strptime(r['original_time'], "%H:%M").time()
                    if booking_date > current_date or (booking_date == current_date and booking_time >= current_time):
                        dr_name = doctors_dict.get(str(r['doctor_id']), translate_template(whatsapp_number, "Unknown", supabase))
                        clinic_id = clinic_dict.get(str(r['doctor_id']), "Unknown")
                        clinic_data = supabase.table("clinics").select("name").eq("id", clinic_id).single().execute().data
                        clinic_name = clinic_data.get("name", "Unknown") if clinic_data else translate_template(whatsapp_number, "Unknown", supabase)
                        details = gt_t_tt(whatsapp_number, r['details'] or r['vaccine_type'] or r['booking_type'] or 'N/A', supabase)
                        booking_type_translated = translate_template(whatsapp_number, r['booking_type'].capitalize(), supabase)
                        booking_str = translate_template(
                            whatsapp_number,
                            "{} ({}) with Dr. {} at {} on {} at {} has been rescheduled to {} at {}",
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
                            "table": "reschedule_requests",
                            "display_details": details,
                            "clinic_id": clinic_id,
                            "duration_minutes": r['duration_minutes']
                        })
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing reschedule request date/time {r}: {e}")
                    continue

            # CONFIRMED CONSULTATIONS
            for c in consultations:
                if not (c.get('date') and c.get('time')):
                    logger.warning(f"Skipping consultation with missing date/time: {c}")
                    continue
                booking_date = datetime.strptime(c['date'], "%Y-%m-%d").date()
                booking_time = datetime.strptime(c['time'], "%H:%M").time()
                if booking_date > current_date or (booking_date == current_date and booking_time >= current_time):
                    dr_name = doctors_dict.get(str(c['doctor_id']), translate_template(whatsapp_number, "Unknown", supabase))
                    clinic_id = clinic_dict.get(str(c['doctor_id']), "Unknown")
                    clinic_data = supabase.table("clinics").select("name").eq("id", clinic_id).single().execute().data
                    clinic_name = clinic_data.get("name", "Unknown") if clinic_data else translate_template(whatsapp_number, "Unknown", supabase)
                    display_details = gt_t_tt(whatsapp_number, c['details'] or 'N/A', supabase)
                    booking_str = translate_template(
                        whatsapp_number,
                        "{} ({}) with Dr. {} at {} on {} at {}",
                        supabase
                    ).format(
                        translate_template(whatsapp_number, "Consultation", supabase),
                        display_details,
                        dr_name,
                        clinic_name,
                        c['date'],
                        c['time']
                    )
                    confirmed_bookings.append({
                        "id": f"con_{str(c['id'])}",
                        "text": booking_str,
                        "date": c['date'],
                        "time": c['time'],
                        "doctor_id": str(c['doctor_id']),
                        "details": c['details'],
                        "type": "consultation",
                        "table": "consultation",
                        "display_details": display_details,
                        "clinic_id": clinic_id,
                        "duration_minutes": c['duration_minutes'],
                        "reminder_duration": c.get("reminder_duration"),
                        "reminder_remark": c.get("reminder_remark")
                    })

            # CONFIRMED CHECKUPS
            for c in checkups:
                if not (c.get('date') and c.get('time')):
                    logger.warning(f"Skipping checkup with missing date/time: {c}")
                    continue
                booking_date = datetime.strptime(c['date'], "%Y-%m-%d").date()
                booking_time = datetime.strptime(c['time'], "%H:%M").time()
                if booking_date > current_date or (booking_date == current_date and booking_time >= current_time):
                    dr_name = doctors_dict.get(str(c['doctor_id']), translate_template(whatsapp_number, "Unknown", supabase))
                    clinic_id = clinic_dict.get(str(c['doctor_id']), "Unknown")
                    clinic_data = supabase.table("clinics").select("name").eq("id", clinic_id).single().execute().data
                    clinic_name = clinic_data.get("name", "Unknown") if clinic_data else translate_template(whatsapp_number, "Unknown", supabase)
                    display_details = gt_t_tt(whatsapp_number, c['details'] or 'N/A', supabase)
                    booking_str = translate_template(
                        whatsapp_number,
                        "{} ({}) with Dr. {} at {} on {} at {}",
                        supabase
                    ).format(
                        translate_template(whatsapp_number, "Checkup", supabase),
                        display_details,
                        dr_name,
                        clinic_name,
                        c['date'],
                        c['time']
                    )
                    confirmed_bookings.append({
                        "id": f"chk_{str(c['id'])}",
                        "text": booking_str,
                        "date": c['date'],
                        "time": c['time'],
                        "doctor_id": str(c['doctor_id']),
                        "details": c['details'],
                        "type": "checkup",
                        "table": "checkup",
                        "display_details": display_details,
                        "clinic_id": clinic_id,
                        "duration_minutes": c['duration_minutes'],
                        "reminder_duration": c.get("reminder_duration"),
                        "reminder_remark": c.get("reminder_remark")
                    })

            # CONFIRMED VACCINATIONS
            for v in vaccinations:
                if not (v.get('date') and v.get('time')):
                    logger.warning(f"Skipping vaccination with missing date/time: {v}")
                    continue
                booking_date = datetime.strptime(v['date'], "%Y-%m-%d").date()
                booking_time = datetime.strptime(v['time'], "%H:%M").time()
                if booking_date > current_date or (booking_date == current_date and booking_time >= current_time):
                    dr_name = doctors_dict.get(str(v['doctor_id']), translate_template(whatsapp_number, "Unknown", supabase))
                    clinic_id = clinic_dict.get(str(v['doctor_id']), "Unknown")
                    clinic_data = supabase.table("clinics").select("name").eq("id", clinic_id).single().execute().data
                    clinic_name = clinic_data.get("name", "Unknown") if clinic_data else translate_template(whatsapp_number, "Unknown", supabase)
                    display_vaccine_type = gt_t_tt(whatsapp_number, v['vaccine_type'] or 'N/A', supabase)
                    booking_str = translate_template(
                        whatsapp_number,
                        "{} ({}) with Dr. {} at {} on {} at {}",
                        supabase
                    ).format(
                        translate_template(whatsapp_number, "Vaccination", supabase),
                        display_vaccine_type,
                        dr_name,
                        clinic_name,
                        v['date'],
                        v['time']
                    )
                    confirmed_bookings.append({
                        "id": f"vac_{str(v['id'])}",
                        "text": booking_str,
                        "date": v['date'],
                        "time": v['time'],
                        "doctor_id": str(v['doctor_id']),
                        "vaccine_type": v['vaccine_type'],
                        "type": "vaccination",
                        "table": "vaccination",
                        "display_vaccine_type": display_vaccine_type,
                        "clinic_id": clinic_id,
                        "duration_minutes": v['duration_minutes'],
                        "reminder_duration": v.get("reminder_duration"),
                        "reminder_remark": v.get("reminder_remark")
                    })

            # PENDING BOOKINGS
            for p in pending_bookings:
                if not (p.get('date') and p.get('time')):
                    logger.warning(f"Skipping pending booking with missing date/time: {p}")
                    continue
                booking_date = datetime.strptime(p['date'], "%Y-%m-%d").date()
                booking_time = datetime.strptime(p['time'], "%H:%M").time()
                if booking_date > current_date or (booking_date == current_date and booking_time >= current_time):
                    dr_name = doctors_dict.get(str(p['doctor_id']), translate_template(whatsapp_number, "Unknown", supabase))
                    clinic_id = clinic_dict.get(str(p['doctor_id']), "Unknown")
                    clinic_data = supabase.table("clinics").select("name").eq("id", clinic_id).single().execute().data
                    clinic_name = clinic_data.get("name", "Unknown") if clinic_data else translate_template(whatsapp_number, "Unknown", supabase)
                    display_details = gt_t_tt(whatsapp_number, p['details'] or p['vaccine_type'] or p['booking_type'] or 'N/A', supabase)
                    booking_type_translated = translate_template(whatsapp_number, p['booking_type'].capitalize(), supabase)
                    booking_str = translate_template(
                        whatsapp_number,
                        "Pending {} ({}) with Dr. {} at {} on {} at {}",
                        supabase
                    ).format(
                        booking_type_translated,
                        display_details,
                        dr_name,
                        clinic_name,
                        p['date'],
                        p['time']
                    )
                    pending_bookings_list.append({
                        "id": f"pen_{str(p['id'])}",
                        "text": booking_str,
                        "date": p['date'],
                        "time": p['time'],
                        "doctor_id": str(p['doctor_id']),
                        "details": p['details'],
                        "vaccine_type": p['vaccine_type'],
                        "type": p['booking_type'],
                        "table": "pending_bookings",
                        "display_details": display_details,
                        "clinic_id": clinic_id,
                        "duration_minutes": p['duration_minutes'],
                        "reminder_duration": p.get("reminder_duration"),
                        "reminder_remark": p.get("reminder_remark")
                    })

            # Construct message with categorized sections
            message_parts = []
            if action_required:
                message_parts.append(translate_template(whatsapp_number, "Action Required", supabase) + ":\n" + "\n".join(f"{i+1}. {b['text']}" for i, b in enumerate(action_required)))
            if confirmed_bookings:
                message_parts.append(translate_template(whatsapp_number, "Confirmed", supabase) + ":\n" + "\n".join(f"{i+1}. {b['text']}" for i, b in enumerate(confirmed_bookings)))
            if pending_bookings_list:
                message_parts.append(translate_template(whatsapp_number, "Pending", supabase) + ":\n" + "\n".join(f"{i+1}. {b['text']}" for i, b in enumerate(pending_bookings_list)))

            # Combine all bookings for later use
            all_bookings = action_required + confirmed_bookings + pending_bookings_list

            if not message_parts:
                message = translate_template(whatsapp_number, "You have no upcoming bookings to reschedule.", supabase)
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": message}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False, None

            # Send the categorized booking list
            message = "\n\n".join(message_parts)
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": message}},
                supabase
            )

            # Send category selection menu
            categories = []
            if action_required:
                categories.append({
                    "id": "category_action_required",
                    "title": translate_template(whatsapp_number, "Action Required", supabase)
                })
            if confirmed_bookings:
                categories.append({
                    "id": "category_confirmed",
                    "title": translate_template(whatsapp_number, "Confirmed", supabase)
                })
            if pending_bookings_list:
                categories.append({
                    "id": "category_pending",
                    "title": translate_template(whatsapp_number, "Pending", supabase)
                })

            payload = {
                "messaging_product": "whatsapp",
                "to": whatsapp_number,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": translate_template(whatsapp_number, "Select a category to reschedule from:", supabase)},
                    "action": {
                        "button": translate_template(whatsapp_number, "Choose Category", supabase),
                        "sections": [{
                            "title": translate_template(whatsapp_number, "Categories", supabase),
                            "rows": [
                                {"id": cat["id"], "title": cat["title"]} for cat in categories
                            ]
                        }]
                    }
                }
            }
            send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
            user_data[whatsapp_number] = {"state": "SELECT_CATEGORY", "bookings": all_bookings, "module": "reschedule_booking"}
            return False, None

        elif state == "SELECT_CATEGORY" and message.get("type") == "interactive" and message["interactive"].get("type") == "list_reply":
            category_id = message["interactive"]["list_reply"]["id"]
            all_bookings = user_data[whatsapp_number]["bookings"]
            category_map = {
                "category_action_required": ["reschedule_requests"],
                "category_confirmed": ["consultation", "checkup", "vaccination"],
                "category_pending": ["pending_bookings"]
            }
            selected_tables = category_map.get(category_id, [])
            if not selected_tables:
                logger.error(f"Invalid category {category_id} for {whatsapp_number}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Invalid category selection. Please try again.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False, None

            # Filter bookings by selected category
            selected_bookings = [b for b in all_bookings if b["table"] in selected_tables]
            if not selected_bookings:
                category_name = translate_template(whatsapp_number, category_id.replace('category_', '').replace('_', ' ').title(), supabase)
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "No bookings available in {} category.", supabase).format(category_name)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False, None

            # Send booking selection menu
            payload = {
                "messaging_product": "whatsapp",
                "to": whatsapp_number,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": translate_template(whatsapp_number, "Select a booking to manage:", supabase)},
                    "action": {
                        "button": translate_template(whatsapp_number, "Choose Booking", supabase),
                        "sections": [{
                            "title": translate_template(whatsapp_number, "Bookings", supabase),
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
            user_data[whatsapp_number] = {"state": "SELECT_BOOKING", "bookings": selected_bookings, "module": "reschedule_booking"}
            return False, None

        elif state == "SELECT_BOOKING" and message.get("type") == "interactive" and message["interactive"].get("type") == "list_reply":
            booking_id = message["interactive"]["list_reply"]["id"]
            selected_booking = next((b for b in user_data[whatsapp_number]["bookings"] if b["id"] == booking_id), None)
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
                return False, None

            user_data[whatsapp_number]["booking_id"] = booking_id
            user_data[whatsapp_number]["original_date"] = selected_booking.get("date") or selected_booking.get("original_date")
            user_data[whatsapp_number]["original_time"] = selected_booking.get("time") or selected_booking.get("original_time")
            user_data[whatsapp_number]["new_date"] = selected_booking.get("new_date")
            user_data[whatsapp_number]["new_time"] = selected_booking.get("new_time")
            user_data[whatsapp_number]["original_doctor_id"] = selected_booking["doctor_id"]
            user_data[whatsapp_number]["details"] = selected_booking.get("details")
            user_data[whatsapp_number]["vaccine_type"] = selected_booking.get("vaccine_type")
            user_data[whatsapp_number]["booking_type"] = selected_booking["type"]
            user_data[whatsapp_number]["table_name"] = selected_booking["table"]
            user_data[whatsapp_number]["display_details"] = selected_booking.get("display_details")
            user_data[whatsapp_number]["display_vaccine_type"] = selected_booking.get("display_vaccine_type")
            user_data[whatsapp_number]["clinic_id"] = selected_booking["clinic_id"]
            user_data[whatsapp_number]["duration_minutes"] = selected_booking["duration_minutes"]
            user_data[whatsapp_number]["reminder_duration"] = selected_booking.get("reminder_duration")
            user_data[whatsapp_number]["reminder_remark"] = selected_booking.get("reminder_remark")

            # Send action buttons based on category
            if selected_booking["table"] == "reschedule_requests":
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
                                }
                            ]
                        }
                    }
                }
            else:
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
                                }
                            ]
                        }
                    }
                }
            send_whatsapp_message(whatsapp_number, "interactive", payload, supabase)
            user_data[whatsapp_number]["state"] = "SELECT_ACTION"
            return False, None

        elif state == "SELECT_ACTION" and message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
            action_id = message["interactive"]["button_reply"]["id"]
            booking_id = user_data[whatsapp_number]["booking_id"]
            table_name = user_data[whatsapp_number]["table_name"]
            booking_type = user_data[whatsapp_number]["booking_type"]
            booking_type_translated = translate_template(whatsapp_number, booking_type.capitalize(), supabase)
            clinic_id = user_data[whatsapp_number]["clinic_id"]
            clinic_data = supabase.table("clinics").select("name").eq("id", clinic_id).single().execute().data
            clinic_name = clinic_data.get("name", "Unknown") if clinic_data else translate_template(whatsapp_number, "Unknown", supabase)

            # Extract the original UUID by removing prefixes
            prefixes = ["con_", "chk_", "vac_", "pen_", "res_"]
            original_id = booking_id
            for prefix in prefixes:
                if original_id.startswith(prefix):
                    original_id = original_id[len(prefix):]
                    break

            # Validate that original_id is a valid UUID
            try:
                uuid.UUID(original_id)
            except ValueError:
                logger.error(f"Invalid UUID format for booking_id {original_id} in table {table_name} for {whatsapp_number}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Invalid booking ID format. Please try again.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False, None

            if action_id.startswith("accept_"):
                reschedule_id = action_id[7:]
                reschedule_data = supabase.table("reschedule_requests").select("*").eq("id", reschedule_id).execute().data
                if not reschedule_data or not (reschedule_data[0].get("new_date") and reschedule_data[0].get("new_time")):
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "Reschedule request not found or has invalid data. Please try again.", supabase)}},
                        supabase
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return False, None

                data = reschedule_data[0]
                table_map = {
                    "consultation": "consultation",
                    "checkup": "checkup",
                    "vaccination": "vaccination"
                }
                table = table_map.get(data["booking_type"])
                booking_type_translated = translate_template(whatsapp_number, data['booking_type'].capitalize(), supabase)
                if not table:
                    logger.error(f"Invalid booking type {data['booking_type']} for reschedule request {reschedule_id}")
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "Invalid booking type for reschedule request.", supabase)}},
                        supabase
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return False, None

                # Create new booking in the appropriate table using new_date and new_time
                booking_data = {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "doctor_id": data["doctor_id"],
                    "date": data["new_date"],
                    "time": data["new_time"],
                    "duration_minutes": data["duration_minutes"],
                    "created_at": datetime.now().isoformat()
                }
                if table in ["consultation", "checkup"]:
                    booking_data["details"] = data.get("details") or 'General'
                elif table == "vaccination":
                    booking_data["vaccine_type"] = data.get("vaccine_type") or ''

                supabase.table(table).insert(booking_data).execute()
                supabase.table("reschedule_requests").delete().eq("id", reschedule_id).execute()

                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(
                        whatsapp_number,
                        "You have accepted the reschedule. Your {} is now confirmed on {} at {}.",
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
                return True, None

            elif action_id.startswith("decline_"):
                reschedule_id = action_id[8:]
                supabase.table("reschedule_requests").delete().eq("id", reschedule_id).execute()
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "You have declined the reschedule request.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False, None

            elif action_id.startswith("reschedule_"):
                user_data[whatsapp_number]["doctor_id"] = user_data[whatsapp_number]["original_doctor_id"]
                user_data[whatsapp_number]["state"] = "SELECT_DATE"
                logger.info(f"🔄 Rescheduling for SAME Doctor {user_data[whatsapp_number]['doctor_id']} for {whatsapp_number}")
                get_calendar(whatsapp_number, user_id, supabase, user_data, "reschedule_booking")
                return False, None

            elif action_id.startswith("cancel_"):
                # Verify booking exists before deletion
                booking_exists = supabase.table(table_name).select("id").eq("id", original_id).execute().data
                if not booking_exists:
                    logger.warning(f"Booking {original_id} in table {table_name} not found for {whatsapp_number}")
                    send_whatsapp_message(
                        whatsapp_number,
                        "text",
                        {"text": {"body": translate_template(whatsapp_number, "Booking not found. It may have already been cancelled.", supabase)}},
                        supabase
                    )
                    user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                    send_interactive_menu(whatsapp_number, supabase)
                    return False, None

                # Delete the booking from the appropriate table
                supabase.table(table_name).delete().eq("id", original_id).execute()
                logger.info(f"Cancelled booking {original_id} from {table_name} for {whatsapp_number}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Your booking has been cancelled.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
                return False, None

        elif state == "SELECT_DATE" and message.get("type") == "interactive" and message["interactive"].get("type") == "list_reply":
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
                user_data[whatsapp_number]["new_date"] = selected_date
                user_data[whatsapp_number]["date"] = selected_date
                user_data[whatsapp_number]["state"] = "SELECT_PERIOD"
                logger.info(f"Date selected for reschedule {whatsapp_number}: {user_data[whatsapp_number]['new_date']} (Doctor: {user_data[whatsapp_number]['doctor_id']})")
                select_period(whatsapp_number, user_id, supabase, user_data, "reschedule_booking")
            return False, None

        elif state == "AWAITING_FUTURE_DATE" and message.get("type") == "text":
            date_input = message["text"]["body"].strip()
            handle_future_date_input(whatsapp_number, user_id, supabase, user_data, "reschedule_booking", date_input)
            return False, None

        elif state == "CONFIRM_FUTURE_DATE" and message.get("type") == "interactive":
            button_id = message["interactive"]["button_reply"]["id"]
            if button_id == "confirm_future_date":
                handle_future_date_confirmation(whatsapp_number, user_id, supabase, user_data, "reschedule_booking", confirmed=True)
            elif button_id == "reject_future_date":
                handle_future_date_confirmation(whatsapp_number, user_id, supabase, user_data, "reschedule_booking", confirmed=False)
            return False, None

        elif state == "SELECT_PERIOD" and message.get("type") == "interactive" and message["interactive"].get("type") == "button_reply":
            user_data[whatsapp_number]["period"] = message["interactive"]["button_reply"]["id"]
            user_data[whatsapp_number]["state"] = "SELECT_HOUR"
            logger.info(f"Period selected for reschedule {whatsapp_number}: {user_data[whatsapp_number]['period']} (Doctor: {user_data[whatsapp_number]['doctor_id']})")
            get_available_hours(whatsapp_number, user_id, supabase, user_data, "reschedule_booking")
            return False, None

        elif state == "SELECT_HOUR" and message.get("type") == "interactive" and message["interactive"].get("type") == "list_reply":
            user_data[whatsapp_number]["hour"] = message["interactive"]["list_reply"]["id"]
            user_data[whatsapp_number]["state"] = "SELECT_TIME_SLOT"
            logger.info(f"Hour selected for reschedule {whatsapp_number}: {user_data[whatsapp_number]['hour']} (Doctor: {user_data[whatsapp_number]['doctor_id']})")
            get_time_slots(whatsapp_number, user_id, supabase, user_data, "reschedule_booking")
            return False, None

        elif state == "SELECT_TIME_SLOT" and message.get("type") == "interactive" and message["interactive"].get("type") == "list_reply":
            user_data[whatsapp_number]["new_time"] = message["interactive"]["list_reply"]["id"]
            return save_to_pending_bookings(whatsapp_number, user_id, supabase, user_data)

        else:
            current_state = user_data.get(whatsapp_number, {}).get("state", "IDLE")
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
            else:
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Invalid input. Please try again.", supabase)}},
                    supabase
                )
                user_data[whatsapp_number] = {"state": "IDLE", "module": None}
                send_interactive_menu(whatsapp_number, supabase)
            return False, None

    except Exception as e:
        logger.error(f"Error in reschedule_booking: {str(e)}", exc_info=True)
        send_whatsapp_message(
            whatsapp_number,
            "text",
            {"text": {"body": translate_template(whatsapp_number, "An error occurred during rescheduling. Please try again.", supabase)}},
            supabase
        )
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False, None

def save_to_pending_bookings(whatsapp_number, user_id, supabase, user_data):
    """MIGRATE confirmed → pending_bookings with SAME DOCTOR + NEW TIME or UPDATE pending_bookings"""
    try:
        booking_data = user_data[whatsapp_number]
        # Ensure all prefixes are removed from booking_id
        prefixes = ["con_", "chk_", "vac_", "pen_", "res_"]
        original_id = booking_data['booking_id']
        for prefix in prefixes:
            if original_id.startswith(prefix):
                original_id = original_id[len(prefix):]
                break
        
        # Validate UUID format
        try:
            uuid.UUID(original_id)
        except ValueError:
            logger.error(f"Invalid UUID format for booking_id {original_id} in table {booking_data['table_name']} for {whatsapp_number}")
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(whatsapp_number, "Invalid booking ID format. Please try again.", supabase)}},
                supabase
            )
            return False, None

        # If the booking is already in pending_bookings, update date and time
        if booking_data['table_name'] == 'pending_bookings':
            # Verify the booking exists
            original = supabase.table('pending_bookings').select('id, doctor_id, booking_type, details, vaccine_type, date, time, duration_minutes, reminder_duration, reminder_remark').eq('id', original_id).single().execute().data
            if not original:
                logger.error(f"Pending booking {original_id} not found for {whatsapp_number}")
                send_whatsapp_message(
                    whatsapp_number,
                    "text",
                    {"text": {"body": translate_template(whatsapp_number, "Booking not found!", supabase)}},
                    supabase
                )
                return False, None

            # Update the existing pending booking with new date and time
            supabase.table('pending_bookings').update({
                "date": booking_data["new_date"],
                "time": booking_data["new_time"],
            }).eq('id', original_id).execute()

            # GET DOCTOR NAME
            doctor_data = supabase.table("doctors").select("name").eq("id", original['doctor_id']).single().execute().data
            doctor_name = doctor_data.get('name', 'Doctor') if doctor_data else 'Doctor'

            # SUCCESS MESSAGE
            send_whatsapp_message(
                whatsapp_number,
                "text",
                {"text": {"body": translate_template(
                    whatsapp_number,
                    "✅ RESCHEDULED!\n\n{} moved to {} at {} with Dr. {} ({}min)\nStatus: PENDING APPROVAL",
                    supabase
                ).format(
                    translate_template(whatsapp_number, booking_data['booking_type'].upper(), supabase),
                    booking_data["new_date"],
                    booking_data["new_time"],
                    doctor_name,
                    original['duration_minutes']
                )}},
                supabase
            )

            user_data[whatsapp_number] = {"state": "IDLE", "module": None}
            send_interactive_menu(whatsapp_number, supabase)
            logger.info(f"✅ Updated pending booking {original_id} for {whatsapp_number}")
            return True, None

        # Handle confirmed bookings (consultation, checkup, vaccination)
        # GET ORIGINAL BOOKING DATA
        if booking_data['table_name'] == 'consultation':
            original = supabase.table('consultation').select('id, doctor_id, details, date, time, duration_minutes, reminder_duration, reminder_remark').eq('id', original_id).single().execute().data
        elif booking_data['table_name'] == 'checkup':
            original = supabase.table('checkup').select('id, doctor_id, details, date, time, duration_minutes, reminder_duration, reminder_remark').eq('id', original_id).single().execute().data
        else:  # vaccination
            original = supabase.table('vaccination').select('id, doctor_id, vaccine_type, date, time, duration_minutes, reminder_duration, reminder_remark').eq('id', original_id).single().execute().data
        
        if not original:
            send_whatsapp_message(whatsapp_number, "text", {"text": {"body": translate_template(whatsapp_number, "Booking not found!", supabase)}},
                                 supabase)
            return False, None

        # CREATE PENDING BOOKING (SAME DOCTOR + NEW TIME)
        pending_data = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "doctor_id": original['doctor_id'],  # SAME DOCTOR!
            "booking_type": booking_data['table_name'],
            "date": booking_data["new_date"],
            "time": booking_data["new_time"],
            "duration_minutes": original['duration_minutes'],
            "reminder_duration": original['reminder_duration'],
            "reminder_remark": original['reminder_remark'],
            "created_at": datetime.now().isoformat()
        }
        
        if booking_data['table_name'] in ['consultation', 'checkup']:
            pending_data["details"] = original['details']
        else:  # vaccination
            pending_data["vaccine_type"] = original['vaccine_type']

        # SAVE TO PENDING + DELETE ORIGINAL
        supabase.table("pending_bookings").insert(pending_data).execute()
        supabase.table(booking_data['table_name']).delete().eq("id", original_id).execute()

        # GET DOCTOR NAME
        doctor_data = supabase.table("doctors").select("name").eq("id", original['doctor_id']).single().execute().data
        doctor_name = doctor_data.get('name', 'Doctor') if doctor_data else 'Doctor'

        # SUCCESS MESSAGE
        send_whatsapp_message(whatsapp_number, "text",
            {"text": {"body": translate_template(whatsapp_number,
                "✅ RESCHEDULED!\n\n{} moved to {} at {} with Dr. {} ({}min)\nStatus: PENDING APPROVAL",
                supabase).format(
                    translate_template(whatsapp_number, booking_data['booking_type'].upper(), supabase),
                    booking_data["new_date"],
                    booking_data["new_time"],
                    doctor_name,
                    original['duration_minutes']
                )}},
            supabase)

        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        logger.info(f"✅ Rescheduled {original_id} → pending for {whatsapp_number}")
        return True, None

    except Exception as e:
        logger.error(f"Save to pending error: {e}")
        send_whatsapp_message(whatsapp_number, "text", {"text": {"body": translate_template(whatsapp_number, "Save error! Please try again.", supabase)}},
                             supabase)
        user_data[whatsapp_number] = {"state": "IDLE", "module": None}
        send_interactive_menu(whatsapp_number, supabase)
        return False, None