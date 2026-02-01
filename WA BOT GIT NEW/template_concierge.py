import logging
from sentence_transformers import SentenceTransformer
from supabase import create_client, Client

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Supabase Credentials
#SUPABASE_URL = "https://qwvglybkftfptzlhdffg.supabase.co"
#SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF3dmdseWJrZnRmcHR6bGhkZmZnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU0MTA4NDQsImV4cCI6MjA3MDk4Njg0NH0.A89YzGK1i5YxNjRHAJkwxLQOAC8WJ4xgb35UKyFY7ro"
SUPABASE_URL="https://umpbmweobqlowgavdydu.supabase.co"
SUPABASE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVtcGJtd2VvYnFsb3dnYXZkeWR1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjUwMDM3MTIsImV4cCI6MjA4MDU3OTcxMn0.jUVCioepUoTbadeqykzPq_73WsCScAP8XrtqvOJFhR0"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize SentenceTransformer model
model = SentenceTransformer('all-distilroberta-v1')

# Define 12 categories with 25+ descriptions each
CATEGORIES = [
    {
        "category": "Notification",
        "descriptions": [
            "Show me my appointment reminder messages.",
            "Check my notifications for upcoming clinic visits.",
            "Why did I get a notification from the bot?",
            "View my reschedule alerts from the clinic.",
            "Show all messages sent by the bot about my bookings.",
            "I got a reminder, what’s it about?",
            "Check my appointment confirmation notifications.",
            "View my clinic notification history.",
            "Show my booking update messages.",
            "Why did I receive a bot message about my appointment?",
            "Check my reschedule prompts from the clinic.",
            "Show my appointment approval notifications.",
            "View alerts about my doctor visit changes.",
            "I got a message, what does it say?",
            "Check my notifications for booking updates.",
            "Show my clinic visit reminder alerts.",
            "View my notification history for appointments.",
            "Why did the bot send me an alert?",
            "Check my messages about upcoming visits.",
            "Show my appointment reschedule notifications.",
            "View my bot messages for booking confirmations.",
            "I received an alert, what’s it for?",
            "Check my notifications for doctor visit updates.",
            "Show my reminder messages for clinic appointments.",
            "View my messages about rescheduling or approvals.",
            "Check my clinic notification updates for this week."
        ]
    },
    {
        "category": "Change Language",
        "descriptions": [
            "Switch the chatbot to Bahasa Malaysia.",
            "I want to use Chinese for the chatbot.",
            "Change the language to Tamil please.",
            "Set the chatbot language to English.",
            "I need the menu in Malay language.",
            "Switch to Chinese for all bot messages.",
            "Change the bot to speak in Tamil.",
            "I want to use English for the chatbot.",
            "Set the language to Bahasa Malaysia for menus.",
            "Switch the chatbot to Chinese language.",
            "I need the bot in Tamil, how to change?",
            "Change all messages to English language.",
            "I want the menu in Bahasa Malaysia.",
            "Switch the bot language to Chinese menus.",
            "Set the chatbot to speak Tamil for me.",
            "Change the language to English for the bot.",
            "I need the bot in Malay, switch now.",
            "Use Chinese for the chatbot interface.",
            "Switch the menu language to Tamil.",
            "I want to change to English for messages.",
            "Set the bot to Bahasa Malaysia for replies.",
            "Change the chatbot to Chinese for the menu.",
            "I need Tamil language for the bot interface.",
            "Switch the bot to English for all replies.",
            "Change the language to Malay for the chatbot.",
            "Set the bot to use Tamil for communication."
        ]
    },
    {
        "category": "General GP Visit",
        "descriptions": [
            "I’m feeling sick and need to see a doctor.",
            "Book a GP appointment for my fever and cough.",
            "I have a sore throat, can I consult a doctor?",
            "Feeling unwell, need a family doctor visit.",
            "My child has a fever, book a same-day appointment.",
            "I’m dizzy and need medical advice from a GP.",
            "Schedule a doctor visit for my stomach pain.",
            "I have a headache and body ache, need a doctor.",
            "Feeling tired and unwell, book a clinic visit.",
            "I need to see a doctor for flu symptoms.",
            "Can you book a general practitioner for me?",
            "I’m not feeling well, arrange a doctor consultation.",
            "Book an appointment for my cough and cold.",
            "Need a doctor for mild illness, how to book?",
            "I have a health problem, need a GP visit.",
            "Feeling sick, can I see a doctor today?",
            "My throat hurts, book a clinic appointment.",
            "I’m experiencing body pain, need a doctor.",
            "Arrange a family doctor visit for my symptoms.",
            "I need medical advice for feeling unwell.",
            "Book a doctor for my persistent cough.",
            "I have a fever, need to see a GP soon.",
            "Feeling fatigued, schedule a doctor visit.",
            "I’m sick and want a same-day doctor appointment.",
            "Need to consult a doctor for general health issues.",
            "I have a cold, book a GP consultation."
        ]
    },
    {
        "category": "Health Check-Up and Tests",
        "descriptions": [
            "I need a full body check-up for health monitoring.",
            "Book a blood test for cholesterol and diabetes.",
            "Arrange a pre-employment medical check for my job.",
            "I want a health screening, how to book it?",
            "Schedule an annual check-up for wellness.",
            "Need a urine test for my health check.",
            "Book a medical test, no symptoms, just checking.",
            "I need a company-required health check-up.",
            "Arrange a fasting blood test for screening.",
            "I want a wellness package for health tests.",
            "Book a diabetes screening test for me.",
            "Need a cholesterol check, how to arrange?",
            "Schedule a preventive health check-up.",
            "I need a medical test for my university entry.",
            "Book a health screening for my annual check.",
            "Arrange a blood test for health monitoring.",
            "I want a full medical check-up, no illness.",
            "Need a test for pre-employment requirements.",
            "Book a screening for blood sugar and cholesterol.",
            "I need a health test for my job application.",
            "Schedule a routine medical check-up for me.",
            "Arrange a wellness check without symptoms.",
            "I want to book a medical screening test.",
            "Need a health check for my visa application.",
            "Book a preventive test for my health.",
            "I need a blood test for routine monitoring."
        ]
    },
    {
        "category": "Vaccination",
        "descriptions": [
            "I need to book a flu shot appointment.",
            "Schedule a COVID-19 booster vaccination.",
            "I want a hepatitis vaccine, how to book?",
            "Book a travel vaccine for my upcoming trip.",
            "Arrange an HPV vaccine for my child.",
            "I need a flu jab, can you book it?",
            "Schedule a vaccination appointment for me.",
            "Book a COVID booster shot for next week.",
            "I need a vaccine for international travel.",
            "Arrange a child vaccination for school.",
            "Book an injection for flu prevention.",
            "I want to get vaccinated, how to proceed?",
            "Schedule a hepatitis B vaccine appointment.",
            "Need a travel injection, book a slot.",
            "I want a booster shot, arrange it please.",
            "Book a flu vaccine for my family.",
            "I need an immunization shot, how to book?",
            "Schedule a vaccine for my upcoming travel.",
            "Arrange a COVID-19 vaccination for me.",
            "I want a flu shot for my child, book it.",
            "Need a vaccine appointment for school entry.",
            "Book a travel vaccine for my trip abroad.",
            "I need a hepatitis shot, arrange a slot.",
            "Schedule an HPV vaccination for my teenager.",
            "I want to book a vaccination for flu season.",
            "Arrange a vaccine for my overseas travel."
        ]
    },
    {
        "category": "Report Result Consultation",
        "descriptions": [
            "I need to discuss my test results with a doctor.",
            "Book a consultation to review my medical report.",
            "My blood test results are out, need a doctor.",
            "Schedule a follow-up for my test outcomes.",
            "I got my report, book a doctor consultation.",
            "Doctor said to come back for my results.",
            "I want to review my health check-up results.",
            "Book a post-lab discussion with a doctor.",
            "Need a consultation for my test report.",
            "My results are ready, arrange a doctor visit.",
            "Schedule a meeting to discuss my lab results.",
            "I need to talk to a doctor about my report.",
            "Book a follow-up consultation for my tests.",
            "My cholesterol test results need review.",
            "Arrange a doctor visit to discuss my results.",
            "I want to go over my medical test report.",
            "Book a session to review my health screening.",
            "Need a doctor to explain my test results.",
            "Schedule a consultation for my lab report.",
            "My test results are out, book a doctor slot.",
            "I need a follow-up for my medical report.",
            "Arrange a consultation to check my results.",
            "Book a doctor to discuss my blood test.",
            "I want a post-test consultation with a GP.",
            "Schedule a review for my health test results.",
            "Need to discuss my lab results with a doctor."
        ]
    },
    {
        "category": "View Past Booking History",
        "descriptions": [
            "Show my past doctor appointments.",
            "I want to check my appointment history.",
            "View my past clinic visits and reports.",
            "Can you show my past booking records?",
            "Check my history of doctor consultations.",
            "I need to see my past medical visits.",
            "Show my past appointment details.",
            "View my consultation history with reports.",
            "Check my past bookings for clinic visits.",
            "I want to download my post-consultation report.",
            "Show my history of doctor appointments.",
            "View my past medical appointment records.",
            "Check my previous clinic visit details.",
            "I need to see my past consultation reports.",
            "Show my past bookings and their reports.",
            "View my history of clinic appointments.",
            "Check my past doctor visit records.",
            "I want to see my past health reports.",
            "Show my previous appointment history.",
            "View my past consultations and reports.",
            "Check my medical visit history.",
            "I need to download my consultation report.",
            "Show my past clinic visit history.",
            "View my past appointment records.",
            "Check my history of medical consultations.",
            "I want to see my old booking reports."
        ]
    },
    {
        "category": "View Upcoming Bookings",
        "descriptions": [
            "Show my upcoming doctor appointments.",
            "I want to check my upcoming bookings.",
            "View my scheduled clinic visits.",
            "What appointments do I have coming up?",
            "Check my upcoming appointment details.",
            "Show my bookings for next week.",
            "View my upcoming doctor visit schedule.",
            "Check my scheduled appointments.",
            "I need to see my upcoming clinic visits.",
            "Show my future appointment details.",
            "View my upcoming medical bookings.",
            "Check my bookings for this month.",
            "I want to see my upcoming doctor slots.",
            "Show my scheduled clinic appointments.",
            "View my upcoming visit details.",
            "Check my future doctor appointments.",
            "I need to see my upcoming booking schedule.",
            "Show my appointments for next month.",
            "View my upcoming clinic visit schedule.",
            "Check my scheduled doctor visits.",
            "I want to see my future bookings.",
            "Show my upcoming appointment times.",
            "View my scheduled medical appointments.",
            "Check my upcoming clinic booking details.",
            "I need to see my future visit schedule.",
            "Show my upcoming bookings for the clinic."
        ]
    },
    {
        "category": "Accept/Reject Reschedule",
        "descriptions": [
            "Doctor suggested a new time, I want to accept.",
            "Reject the clinic’s reschedule suggestion.",
            "I need to accept a reschedule for my appointment.",
            "The doctor is unavailable, reject the new time.",
            "Accept the new timeslot suggested by the clinic.",
            "I want to reject the proposed reschedule time.",
            "Confirm the new appointment time suggested.",
            "Reject the reschedule time for my booking.",
            "I need to act on a reschedule suggestion.",
            "Accept the clinic’s new appointment slot.",
            "Reject the new time proposed by the doctor.",
            "I want to confirm the reschedule suggestion.",
            "Decline the suggested time for my appointment.",
            "Accept the new time for my doctor visit.",
            "I need to reject the reschedule proposal.",
            "Confirm the reschedule time for my booking.",
            "Reject the clinic’s suggested appointment time.",
            "I want to accept the new slot for my visit.",
            "Decline the new timeslot suggested by the clinic.",
            "Accept the reschedule for my doctor appointment.",
            "I need to reject the new appointment time.",
            "Confirm the suggested reschedule for my visit.",
            "Reject the proposed time for my clinic visit.",
            "Accept the new appointment time from the clinic.",
            "I want to decline the reschedule suggestion.",
            "Act on the clinic’s reschedule proposal."
        ]
    },
    {
        "category": "Reschedule Confirmed Booking",
        "descriptions": [
            "I need to reschedule my confirmed appointment.",
            "Change my doctor appointment to another day.",
            "I want to move my confirmed booking time.",
            "Reschedule my confirmed clinic visit.",
            "Change my appointment slot to next week.",
            "I need to update my confirmed booking time.",
            "Move my confirmed doctor visit to another day.",
            "Reschedule my confirmed appointment slot.",
            "I want to change my confirmed visit time.",
            "Update my confirmed appointment to a new date.",
            "Reschedule my confirmed doctor appointment.",
            "I need to move my confirmed booking to evening.",
            "Change my confirmed clinic appointment time.",
            "I want to reschedule my confirmed visit slot.",
            "Move my confirmed appointment to next month.",
            "Update my confirmed booking to a new time.",
            "Reschedule my confirmed medical appointment.",
            "I need to change my confirmed visit schedule.",
            "Move my confirmed doctor slot to another day.",
            "I want to update my confirmed appointment time.",
            "Reschedule my confirmed clinic visit time.",
            "Change my confirmed booking to a later date.",
            "I need to move my confirmed visit to morning.",
            "Update my confirmed appointment schedule.",
            "Reschedule my confirmed doctor visit slot.",
            "I want to change my confirmed booking date."
        ]
    },
    {
        "category": "Cancel Confirmed Booking",
        "descriptions": [
            "I want to cancel my confirmed appointment.",
            "Cancel my doctor booking for next week.",
            "I need to cancel my confirmed clinic visit.",
            "Remove my confirmed doctor appointment.",
            "Cancel my confirmed booking slot.",
            "I want to stop my confirmed clinic visit.",
            "Cancel my confirmed medical appointment.",
            "I need to cancel my booked doctor slot.",
            "Remove my confirmed appointment from the schedule.",
            "Cancel my confirmed visit for this month.",
            "I want to cancel my confirmed doctor visit.",
            "Stop my confirmed clinic appointment.",
            "Cancel my confirmed booking for next week.",
            "I need to remove my confirmed visit slot.",
            "Cancel my confirmed appointment with the doctor.",
            "I want to cancel my confirmed booking time.",
            "Remove my confirmed clinic visit from the schedule.",
            "Cancel my confirmed doctor appointment slot.",
            "I need to stop my confirmed medical visit.",
            "Cancel my confirmed booking for this week.",
            "I want to remove my confirmed appointment.",
            "Cancel my confirmed clinic visit slot.",
            "Stop my confirmed doctor visit schedule.",
            "I need to cancel my confirmed visit time.",
            "Remove my confirmed booking from the clinic.",
            "Cancel my confirmed appointment for next month."
        ]
    },
    {
        "category": "Reschedule/Cancel Pending Booking",
        "descriptions": [
            "I need to reschedule my pending booking.",
            "Cancel my booking that’s pending approval.",
            "Change my pending clinic appointment time.",
            "I want to cancel my pending doctor visit.",
            "Reschedule my booking awaiting clinic approval.",
            "I need to modify my pending appointment slot.",
            "Cancel my pending medical appointment.",
            "Change my pending booking to another day.",
            "I want to reschedule my pending visit time.",
            "Cancel my booking that’s not yet approved.",
            "Reschedule my pending doctor appointment.",
            "I need to cancel my pending clinic slot.",
            "Change my pending appointment to next week.",
            "I want to modify my pending booking schedule.",
            "Cancel my pending visit awaiting approval.",
            "Reschedule my pending clinic visit slot.",
            "I need to change my pending appointment time.",
            "Cancel my pending doctor booking slot.",
            "Reschedule my pending medical visit.",
            "I want to cancel my pending appointment time.",
            "Change my pending booking to a new date.",
            "Cancel my pending clinic visit schedule.",
            "I need to reschedule my pending doctor slot.",
            "Modify my pending appointment awaiting approval.",
            "Cancel my pending booking for next week.",
            "Reschedule my pending clinic appointment time."
        ]
    }
]

def initialize_concierge_vectors(supabase: Client):
    """Initialize the concierge_vectors table with multiple description embeddings per category."""
    try:
        # Clear existing data to avoid duplicates
        supabase.table("c_concierge_vectors").delete().gte("id", 0).execute()
        logger.info("Cleared existing concierge_vectors table")

        # Generate embeddings for each description
        total_inserted = 0
        for category in CATEGORIES:
            for description in category["descriptions"]:
                embedding = model.encode(description).tolist()
                supabase.table("c_concierge_vectors").insert({
                    "category": category["category"],
                    "description": description,
                    "embedding": embedding
                }).execute()
                total_inserted += 1
                logger.info(f"Inserted vector {total_inserted} for category: {category['category']}, description: {description[:50]}...")
        logger.info(f"Concierge vectors initialized successfully with {total_inserted} entries")
    except Exception as e:
        logger.error(f"Error initializing concierge_vectors: {e}", exc_info=True)
        raise

def main():
    """Main function to run the initialization."""
    try:
        initialize_concierge_vectors(supabase)
        logger.info("Template initialization completed")
    except Exception as e:
        logger.error(f"Failed to initialize templates: {e}", exc_info=True)

if __name__ == "__main__":
    main()