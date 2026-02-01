import logging
import uuid
from datetime import datetime, timedelta
from utils import send_whatsapp_message, translate_template, gt_tt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default ambulance scheduling parameters
DEFAULT_TRIP_DURATION = 2  # hours
BUFFER_BEFORE = 30  # minutes
BUFFER_AFTER = 30  # minutes

def get_available_ambulances(supabase, date, start_time, end_time, ambulance_type=None):
    """Get available ambulances for a given time slot."""
    try:
        # Parse inputs
        if isinstance(date, str):
            date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        else:
            date_obj = date
        
        if isinstance(start_time, str):
            start_datetime = datetime.strptime(f"{date_obj} {start_time}", "%Y-%m-%d %H:%M:%S")
        else:
            start_datetime = datetime.combine(date_obj, start_time)
        
        if isinstance(end_time, str):
            end_datetime = datetime.strptime(f"{date_obj} {end_time}", "%Y-%m-%d %H:%M:%S")
        else:
            end_datetime = datetime.combine(date_obj, end_time)
        
        # Get all ambulances
        query = supabase.table("ambulances").select("*").eq("status", "available")
        
        if ambulance_type:
            query = query.eq("ambulance_type", ambulance_type)
        
        response = query.execute()
        all_ambulances = response.data
        
        available_ambulances = []
        
        for ambulance in all_ambulances:
            ambulance_id = ambulance["id"]
            
            # Check if ambulance is available in the calendar
            is_available = check_ambulance_slot_availability(
                supabase, ambulance_id, start_datetime, end_datetime
            )
            
            if is_available:
                available_ambulances.append(ambulance)
        
        return available_ambulances
        
    except Exception as e:
        logger.error(f"Error getting available ambulances: {e}", exc_info=True)
        return []

def check_ambulance_slot_availability(supabase, ambulance_id, start_datetime, end_datetime):
    """Check if an ambulance is available for a specific time slot."""
    try:
        date_str = start_datetime.strftime("%Y-%m-%d")
        
        # Get all bookings for this ambulance on the given date
        response = supabase.table("ambulance_availability").select("*").eq("ambulance_id", ambulance_id).eq("date", date_str).execute()
        existing_bookings = response.data
        
        # Check for conflicts
        for booking in existing_bookings:
            booking_start = datetime.strptime(f"{date_str} {booking['start_time']}", "%Y-%m-%d %H:%M:%S")
            booking_end = datetime.strptime(f"{date_str} {booking['end_time']}", "%Y-%m-%d %H:%M:%S")
            
            # Check for overlap
            if start_datetime < booking_end and end_datetime > booking_start:
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking ambulance slot availability: {e}", exc_info=True)
        return False

def book_ambulance_slot(supabase, ambulance_id, booking_type, booking_reference, 
                        start_datetime, end_datetime, notes=None):
    """Book an ambulance slot in the calendar."""
    try:
        date_str = start_datetime.strftime("%Y-%m-%d")
        start_time_str = start_datetime.strftime("%H:%M:%S")
        end_time_str = end_datetime.strftime("%H:%M:%S")
        
        # Check availability first
        if not check_ambulance_slot_availability(supabase, ambulance_id, start_datetime, end_datetime):
            return False, "Time slot not available"
        
        # Create calendar entry
        calendar_data = {
            "ambulance_id": ambulance_id,
            "date": date_str,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "status": "booked",
            "booking_type": booking_type,
            "booking_reference": booking_reference
        }
        
        if notes:
            calendar_data["notes"] = notes
        
        response = supabase.table("ambulance_availability").insert(calendar_data).execute()
        
        if response.data:
            # Update ambulance status if needed
            supabase.table("ambulances").update({
                "status": "assigned",
                "next_available_time": end_datetime.isoformat()
            }).eq("id", ambulance_id).execute()
            
            return True, "Slot booked successfully"
        else:
            return False, "Failed to book slot"
        
    except Exception as e:
        logger.error(f"Error booking ambulance slot: {e}", exc_info=True)
        return False, str(e)

def get_ambulance_schedule(supabase, ambulance_id, date):
    """Get schedule for a specific ambulance on a given date."""
    try:
        if isinstance(date, str):
            date_str = date
        else:
            date_str = date.strftime("%Y-%m-%d")
        
        response = supabase.table("ambulance_availability").select("*").eq("ambulance_id", ambulance_id).eq("date", date_str).order("start_time").execute()
        
        return response.data
        
    except Exception as e:
        logger.error(f"Error getting ambulance schedule: {e}")
        return []

def suggest_available_slots(supabase, date, duration_hours=2, ambulance_type=None):
    """Suggest available time slots for ambulance booking."""
    try:
        if isinstance(date, str):
            date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        else:
            date_obj = date
        
        # Get available ambulances for the day
        query = supabase.table("ambulances").select("*").eq("status", "available")
        
        if ambulance_type:
            query = query.eq("ambulance_type", ambulance_type)
        
        response = query.execute()
        ambulances = response.data
        
        if not ambulances:
            return []
        
        # Define working hours (8 AM to 8 PM)
        working_start = datetime.combine(date_obj, datetime.strptime("08:00", "%H:%M").time())
        working_end = datetime.combine(date_obj, datetime.strptime("20:00", "%H:%M").time())
        
        # Generate time slots
        available_slots = []
        current_time = working_start
        
        while current_time + timedelta(hours=duration_hours) <= working_end:
            end_time = current_time + timedelta(hours=duration_hours)
            
            # Check if any ambulance is available for this slot
            for ambulance in ambulances:
                ambulance_id = ambulance["id"]
                
                if check_ambulance_slot_availability(supabase, ambulance_id, current_time, end_time):
                    slot_info = {
                        "start_time": current_time.strftime("%H:%M"),
                        "end_time": end_time.strftime("%H:%M"),
                        "ambulance_id": ambulance_id,
                        "ambulance_number": ambulance["ambulance_number"],
                        "ambulance_type": ambulance["ambulance_type"]
                    }
                    available_slots.append(slot_info)
                    break  # Found an ambulance for this slot
            
            current_time += timedelta(minutes=30)  # Check every 30 minutes
        
        return available_slots
        
    except Exception as e:
        logger.error(f"Error suggesting available slots: {e}", exc_info=True)
        return []

def cancel_ambulance_booking(supabase, booking_reference, booking_type):
    """Cancel an ambulance booking."""
    try:
        # Find and delete calendar entry
        response = supabase.table("ambulance_availability").select("*").eq("booking_reference", booking_reference).eq("booking_type", booking_type).execute()
        
        if response.data:
            entry = response.data[0]
            ambulance_id = entry["ambulance_id"]
            
            # Delete calendar entry
            supabase.table("ambulance_availability").delete().eq("id", entry["id"]).execute()
            
            # Update ambulance status if no other bookings
            other_bookings = supabase.table("ambulance_availability").select("*").eq("ambulance_id", ambulance_id).gte("date", datetime.now().strftime("%Y-%m-%d")).execute()
            
            if not other_bookings.data:
                supabase.table("ambulances").update({
                    "status": "available",
                    "next_available_time": None
                }).eq("id", ambulance_id).execute()
            
            return True, "Booking cancelled successfully"
        else:
            return False, "Booking not found"
        
    except Exception as e:
        logger.error(f"Error cancelling ambulance booking: {e}", exc_info=True)
        return False, str(e)

def update_ambulance_status(supabase, ambulance_id, status, next_available=None):
    """Update ambulance status."""
    try:
        update_data = {"status": status}
        
        if next_available:
            update_data["next_available_time"] = next_available
        
        response = supabase.table("ambulances").update(update_data).eq("id", ambulance_id).execute()
        
        return bool(response.data)
        
    except Exception as e:
        logger.error(f"Error updating ambulance status: {e}")
        return False

def get_nearest_available_ambulance(supabase, latitude, longitude, ambulance_type=None):
    """Find the nearest available ambulance (simplified version)."""
    try:
        query = supabase.table("ambulances").select("*").eq("status", "available")
        
        if ambulance_type:
            query = query.eq("ambulance_type", ambulance_type)
        
        response = query.execute()
        ambulances = response.data
        
        if not ambulances:
            return None
        
        # In a real system, you would calculate distance using coordinates
        # For now, return the first available ambulance
        return ambulances[0]
        
    except Exception as e:
        logger.error(f"Error finding nearest ambulance: {e}")
        return None