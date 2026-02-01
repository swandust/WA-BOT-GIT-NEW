# bm_match.py - BAHASA MALAYSIA VERSION
import logging
import time
from google.cloud import translate_v2 as translate
import os

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Initialize Google Translate client
GOOGLE_KEY_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

if GOOGLE_KEY_PATH and os.path.exists(GOOGLE_KEY_PATH):
    try:
        from google.cloud import translate_v2 as translate
        translate_client = translate.Client.from_service_account_json(GOOGLE_KEY_PATH)
        logger.info(f"Google Translate client initialized with credentials from {GOOGLE_KEY_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize Google Translate client: {e}")
        translate_client = None
else:
    logger.warning("GOOGLE_APPLICATION_CREDENTIALS environment variable not set or file not found")
    logger.warning("Google Translate will use dictionary fallback only")
    translate_client = None

# Translation dictionary for English to Bahasa Malaysia
EN_TO_BM = {
    # ========== EXISTING TRANSLATIONS ==========
    
    # Existing translations
    "Sorry, clinic information is not available at the moment.": "Maaf, maklumat klinik tidak tersedia buat masa ini.",
    "Clinic Enquiries": "Pertanyaan Klinik",
    "Contact the front desk of {clinic_name} for further assistance.": "Hubungi kaunter penerimaan {clinic_name} untuk bantuan lanjut.",
    "Click a button to proceed": "Klik butang untuk teruskan",
    "Talk to Front Desk": "Bercakap dengan Kaunter Penerimaan",
    "Cancel": "Batal",
    "Error sending clinic information. Please try again.": "Ralat menghantar maklumat klinik. Sila cuba lagi.",
    "An error occurred. Please try again.": "Berlaku ralat. Sila cuba lagi.",
    "Please contact our front desk: https://wa.me/60127689719?text=Hi,+referred+from+AnyHealth": "Sila hubungi kaunter penerimaan: {wa_link}",
    "Invalid module. Returning to main menu.": "Modul tidak sah. Kembali ke menu utama.",
    "Language set to {}.": "Bahasa ditetapkan kepada {}.",
    "Your query is related to: {}\n\n{}\n\nPlease select the appropriate option from the menu.": "Pertanyaan anda berkaitan dengan: {}\n\n{}\n\nSila pilih pilihan yang sesuai dari menu.",
    "Please type what you need help with, and I'll guide you to the right option.": "Sila taip apa yang anda perlukan bantuan, dan saya akan pandu anda ke pilihan yang betul.",
    "Your query is related to: {}\n\n{}\n\nPlease select the appropriate option from the main menu to proceed.": "Pertanyaan anda berkaitan dengan: {}\n\n{}\n\nSila pilih pilihan yang sesuai dari menu utama untuk teruskan.",
    
    "Your query is related to: General GP Visit\n\nSteps for General GP Visit Booking:\n1. Select Menu\n2. Select Booking\n3. Select Booking Options\n4. Select General GP Options\n5. Type symptoms (e.g., Runny Nose)\n6. Select a doctor\n   a. If unsure, select Any Doctor\n7. Select a date\n8. Select an hour\n   a. Some slots may be unavailable, subject to doctor availability\n9. Click confirm and await approval\n10. Notification will be sent when doctor approves appointment - click on Menu -> Notification to view\n\nPlease select the appropriate option from the main menu to proceed.": "Pertanyaan anda berkaitan dengan: Lawatan GP Am\n\nLangkah-langkah Tempahan Lawatan GP Am:\n1. Pilih Menu\n2. Pilih Tempahan\n3. Pilih Pilihan Tempahan\n4. Pilih Pilihan GP Am\n5. Taip gejala (cth., Selsema)\n6. Pilih doktor\n   a. Jika tidak pasti, pilih Mana-mana Doktor\n7. Pilih tarikh\n8. Pilih jam\n   a. Beberapa slot mungkin tidak tersedia, tertakluk kepada ketersediaan doktor\n9. Klik sahkan dan tunggu kelulusan\n10. Pemberitahuan akan dihantar apabila doktor meluluskan temujanji - klik Menu -> Pemberitahuan untuk lihat\n\nSila pilih pilihan yang sesuai dari menu utama untuk teruskan.",
    
    "Your query is related to: Health Check-Up and Tests\n\nSteps for Check-Up and Test Booking:\n1. Select Menu\n2. Select Booking\n3. Select Booking Options\n4. Select Checkup & Test\n5. Select a checkup type (e.g., General Screening)\n6. Type remarks (e.g., For employment)\n7. Select a doctor\n   a. If unsure, select Any Doctor\n8. Select a date\n9. Select an hour\n   a. Some slots may be unavailable, subject to doctor availability\n10. Click confirm and await approval\n11. Notification will be sent when doctor approves appointment - click on Menu -> Notification to view\n\nPlease select the appropriate option from the main menu to proceed.": "Pertanyaan anda berkaitan dengan: Pemeriksaan Kesihatan dan Ujian\n\nLangkah-langkah Tempahan Pemeriksaan dan Ujian:\n1. Pilih Menu\n2. Pilih Tempahan\n3. Pilih Pilihan Tempahan\n4. Pilih Pemeriksaan & Ujian\n5. Pilih jenis pemeriksaan (cth., Saringan Umum)\n6. Taip catatan (cth., Untuk pekerjaan)\n7. Pilih doktor\n   a. Jika tidak pasti, pilih Mana-mana Doktor\n8. Pilih tarikh\n9. Pilih jam\n   a. Beberapa slot mungkin tidak tersedia, tertakluk kepada ketersediaan doktor\n10. Klik sahkan dan tunggu kelulusan\n11. Pemberitahuan akan dihantar apabila doktor meluluskan temujanji - klik Menu -> Pemberitahuan untuk lihat\n\nSila pilih pilihan yang sesuai dari menu utama untuk teruskan.",
    
    "Your query is related to: Vaccination\n\nSteps for Vaccination Booking:\n1. Select Menu\n2. Select Booking\n3. Select Booking Options\n4. Select Vaccination\n5. Select a Vaccination type (e.g., COVID Vaccine)\n6. Type remarks (e.g., Booster)\n7. Select a doctor\n   a. If unsure, select Any Doctor\n8. Select a date\n9. Select an hour\n   a. Some slots may be unavailable, subject to doctor availability\n10. Click confirm and await approval\n11. Notification will be sent when doctor approves appointment - click on Menu -> Notification to view\n\nPlease select the appropriate option from the main menu to proceed.": "Pertanyaan anda berkaitan dengan: Vaksinasi\n\nLangkah-langkah Tempahan Vaksinasi:\n1. Pilih Menu\n2. Pilih Tempahan\n3. Pilih Pilihan Tempahan\n4. Pilih Vaksinasi\n5. Pilih jenis vaksin (cth., Vaksin COVID)\n6. Taip catatan (cth., Booster)\n7. Pilih doktor\n   a. Jika tidak pasti, pilih Mana-mana Doktor\n8. Pilih tarikh\n9. Pilih jam\n   a. Beberapa slot mungkin tidak tersedia, tertakluk kepada ketersediaan doktor\n10. Klik sahkan dan tunggu kelulusan\n11. Pemberitahuan akan dihantar apabila doktor meluluskan temujanji - klik Menu -> Pemberitahuan untuk lihat\n\nSila pilih pilihan yang sesuai dari menu utama untuk teruskan.",
    
    "Your query is related to: Report Result Consultation\n\nSteps for Report Result Consultation:\n1. Notification informs you that your test result has been released\n2. Click Menu\n3. Select Booking\n4. Select Report Result Booking\n5. Select Report (e.g., Booking 1) that appears\n6. Select Yes if you have any remarks for the doctor (e.g., Result is for university)\n7. Select date for consult\n8. Select time (hour)\n9. Select slot\n10. Click confirm and await approval\n11. Notification will be sent when doctor approves appointment - click on Menu -> Notification to view\n\nPlease select the appropriate option from the main menu to proceed.": "Pertanyaan anda berkaitan dengan: Perundingan Hasil Laporan\n\nLangkah-langkah Tempahan Perundingan Hasil Laporan:\n1. Pemberitahuan memaklumkan hasil ujian anda telah dikeluarkan\n2. Klik Menu\n3. Pilih Tempahan\n4. Pilih Tempahan Hasil Laporan\n5. Pilih Laporan (cth., Tempahan 1) yang muncul\n6. Pilih Ya jika ada catatan untuk doktor (cth., Hasil untuk universiti)\n7. Pilih tarikh untuk perundingan\n8. Pilih masa (jam)\n9. Pilih slot\n10. Klik sahkan dan tunggu kelulusan\n11. Pemberitahuan akan dihantar apabila doktor meluluskan temujanji - klik Menu -> Pemberitahuan untuk lihat\n\nSila pilih pilihan yang sesuai dari menu utama untuk teruskan.",
    
    "Your query is related to: View Past Booking History\n\nSteps to View Previous Booking Reports:\n1. Click Menu\n2. Select Booking\n3. Select View Past Consultations\n\nPlease select the appropriate option from the main menu to proceed.": "Pertanyaan anda berkaitan dengan: Lihat Sejarah Tempahan Lepas\n\nLangkah-langkah Melihat Laporan Tempahan Terdahulu:\n1. Klik Menu\n2. Pilih Tempahan\n3. Pilih Lihat Perundingan Terdahulu\n\nSila pilih pilihan yang sesuai dari menu utama untuk teruskan.",
    
    "Your query is related to: View Upcoming Bookings\n\nSteps to View Upcoming Appointments:\n1. Click Menu\n2. Select Booking\n3. Select View Upcoming Bookings\n4. On the screen are Confirmed bookings and Pending Bookings\n   a. Confirmed bookings: doctor has approved and added to their calendar\n   b. Pending Bookings: awaiting doctor confirmation\n   Please allow 3 hours for doctor to confirm your booking.\n\nPlease select the appropriate option from the main menu to proceed.": "Pertanyaan anda berkaitan dengan: Lihat Tempahan Akan Datang\n\nLangkah-langkah Melihat Temujanji Akan Datang:\n1. Klik Menu\n2. Pilih Tempahan\n3. Pilih Lihat Tempahan Akan Datang\n4. Di skrin ada Tempahan Disahkan dan Tempahan Belum Disahkan\n   a. Tempahan Disahkan: doktor telah lulus dan tambah ke kalendar mereka\n   b. Tempahan Belum Disahkan: menunggu pengesahan doktor\n   Sila beri 3 jam untuk doktor mengesahkan tempahan anda.\n\nSila pilih pilihan yang sesuai dari menu utama untuk teruskan.",
    
    "Your query is related to: Accept/Reject Reschedule\n\nSteps to Accept or Reject Rescheduled Appointment:\n1. Select Menu\n2. Select Booking\n3. Select Reschedule Booking\n4. Select Choose Category\n5. Select Action Required\n6. Select the booking as required\n7. Click Accept if the timing is suitable\n   a. Booking is confirmed\n8. Click Decline if the timing is not suitable\n   a. Booking will be removed\n\nPlease select the appropriate option from the main menu to proceed.": "Pertanyaan anda berkaitan dengan: Terima/Tolak Jadual Semula\n\nLangkah-langkah Menerima atau Menolak Temujanji Dijadual Semula:\n1. Pilih Menu\n2. Pilih Tempahan\n3. Pilih Jadual Semula Tempahan\n4. Pilih Pilih Kategori\n5. Pilih Tindakan Diperlukan\n6. Pilih tempahan seperti yang dikehendaki\n7. Klik Terima jika masa sesuai\n   a. Tempahan disahkan\n8. Klik Tolak jika masa tidak sesuai\n   a. Tempahan akan dikeluarkan\n\nSila pilih pilihan yang sesuai dari menu utama untuk teruskan.",
    
    "Your query is related to: Reschedule Confirmed Booking - tgt\n\nSteps to Reschedule a Confirmed Booking:\n1. Notification informs you that your test result has been released\n2. Select Menu\n3. Select Booking\n4. Select Reschedule\n5. Click Confirmed\n6. Select Booking you wish to reschedule\n7. Select Reschedule\n8. Select new date\n9. Select new time\n10. Await Doctor Approval\n\nPlease select the appropriate option from the main menu to proceed.": "Pertanyaan anda berkaitan dengan: Jadual Semula Tempahan Disahkan\n\nLangkah-langkah Menjadual Semula Tempahan Disahkan:\n1. Pemberitahuan memaklumkan hasil ujian anda telah dikeluarkan\n2. Pilih Menu\n3. Pilih Tempahan\n4. Pilih Jadual Semula\n5. Klik Disahkan\n6. Pilih tempahan yang anda ingin jadual semula\n7. Pilih Jadual Semula\n8. Pilih tarikh baru\n9. Pilih masa baru\n10. Tunggu Kelulusan Doktor\n\nSila pilih pilihan yang sesuai dari menu utama untuk teruskan.",
    
    "Your query is related to: Cancel Confirmed Booking - tgt\n\nSteps to Cancel a Confirmed Booking:\n1. Notification informs you that your test result has been released\n2. Select Menu\n3. Select Booking\n4. Select Reschedule\n5. Click Confirmed\n6. Select Booking you wish to reschedule\n7. Select Cancel\n8. Your booking has been cancelled\n\nPlease select the appropriate option from the main menu to proceed.": "Pertanyaan anda berkaitan dengan: Batal Tempahan Disahkan\n\nLangkah-langkah Membatalkan Tempahan Disahkan:\n1. Pemberitahuan memaklumkan hasil ujian anda telah dikeluarkan\n2. Pilih Menu\n3. Pilih Tempahan\n4. Pilih Jadual Semula\n5. Klik Disahkan\n6. Pilih tempahan yang anda ingin jadual semula\n7. Pilih Batal\n8. Tempahan anda telah dibatalkan\n\nSila pilih pilihan yang sesuai dari menu utama untuk teruskan.",
    
    "Your query is related to: Reschedule/Cancel Pending Booking\n\nSteps to Reschedule or Cancel a Pending Booking:\n1. Select Menu\n2. Select Booking\n3. Select Reschedule\n4. Click Pending\n5. Select Booking you wish to reschedule or cancel\n6. To Reschedule:\n   a. Select Reschedule\n   b. Select new date\n   c. Select new time\n   d. Await Doctor Approval\n7. To Cancel:\n   a. Select Cancel\n   b. Your booking has been cancelled\n\nPlease select the appropriate option from the main menu to proceed.": "Pertanyaan anda berkaitan dengan: Jadual Semula/Batal Tempahan Belum Disahkan\n\nLangkah-langkah Menjadual Semula atau Membatalkan Tempahan Belum Disahkan:\n1. Pilih Menu\n2. Pilih Tempahan\n3. Pilih Jadual Semula\n4. Klik Belum Disahkan\n5. Pilih tempahan yang anda ingin jadual semula atau batalkan\n6. Untuk Jadual Semula:\n   a. Pilih Jadual Semula\n   b. Pilih tarikh baru\n   c. Pilih masa baru\n   d. Tunggu Kelulusan Doktor\n7. Untuk Batal:\n   a. Pilih Batal\n   b. Tempahan anda telah dibatalkan\n\nSila pilih pilihan yang sesuai dari menu utama untuk teruskan.",
    
    "Your query is related to: Notification\n\nSteps for Notifications:\n1. Select Menu\n2. Select Notifications to view all notifications\n\nPlease select the appropriate option from the main menu to proceed.": "Pertanyaan anda berkaitan dengan: Pemberitahuan\n\nLangkah-langkah Pemberitahuan:\n1. Pilih Menu\n2. Pilih Pemberitahuan untuk lihat semua pemberitahuan\n\nSila pilih pilihan yang sesuai dari menu utama untuk teruskan.",
    
    "Your query is related to: Change Language\n\nSteps to Change Language:\n1. Select Menu\n2. Select Change Language\n3. Select preferred language\n\nPlease select the appropriate option from the main menu to proceed.": "Pertanyaan anda berkaitan dengan: Tukar Bahasa\n\nLangkah-langkah Menukar Bahasa:\n1. Pilih Menu\n2. Pilih Tukar Bahasa\n3. Pilih bahasa pilihan\n\nSila pilih pilihan yang sesuai dari menu utama untuk teruskan.",
    
    # Day names for calendar
    "Monday": "Isnin",
    "Tuesday": "Selasa",
    "Wednesday": "Rabu",
    "Thursday": "Khamis",
    "Friday": "Jumaat",
    "Saturday": "Sabtu",
    "Sunday": "Ahad",
    "📅 Future Date": "📅 Tarikh Masa Depan",

    "Please enter your preferred date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:": "Sila masukkan tarikh pilihan anda sebagai DD/MM/YYYY, DD-MM-YYYY atau DD MM YYYY:",
    "Is this the correct date: {}?": "Adakah tarikh ini betul: {}?",
    "Great! {} is available. Is this the time you want?": "Bagus! {} tersedia. Adakah ini masa yang anda mahukan?",
    
    # TCM booking confirmation templates
    "Confirm your TCM booking:\n* Service: {}\n* Doctor: {}\n* Date: {}\n* Time: {}\n* Duration: {} min\n* Details: {}": "Sahkan tempahan TCM anda:\n* Perkhidmatan: {}\n* Doktor: {}\n* Tarikh: {}\n* Masa: {}\n* Tempoh: {} min\n* Butiran: {}",
    "✅ Your TCM booking has been submitted!": "✅ Tempahan TCM anda telah dihantar!",
    "Service: {}\nDate: {}\nTime: {}\nDuration: {} minutes": "Perkhidmatan: {}\nTarikh: {}\nMasa: {}\nTempoh: {} minit",
    "Booking is pending approval. You'll be notified once confirmed.": "Tempahan sedang menunggu kelulusan. Anda akan dimaklumkan sebaik disahkan.",
    "Booking ID: {}": "ID Tempahan: {}",
    
    # From main.py
    "Error registering user. Please try again.": "Ralat mendaftar pengguna. Sila cuba lagi.",
    "Please select an option from the menu.": "Sila pilih pilihan dari menu.",
    "Invalid input. Please select an option from the menu.": "Input tidak sah. Sila pilih pilihan dari menu.",
    "Invalid module. Returning to main menu.": "Modul tidak sah. Kembali ke menu utama.",
    "An error occurred. Please try again.": "Berlaku ralat. Sila cuba lagi.",
    "Language set to {}.": "Bahasa ditetapkan kepada {}.",
    
    # From utils.py
    "AnyHealth Bot": "Bot AnyHealth",
    "Welcome to AnyHealth Bot! Please choose an option:": "Selamat datang ke Bot AnyHealth! Sila pilih pilihan:",
    "Select an option to proceed": "Pilih pilihan untuk teruskan",
    "Menu": "Menu",
    "Main Options": "Pilihan Utama",
    "🔔Notification": "🔔Pemberitahuan",
    "🏥Booking": "🏥Tempahan",
    "🌐Change Language": "🌐Tukar Bahasa",
    "📞Clinic Enquiries": "📞Pertanyaan Klinik",
    "Booking Options": "Pilihan Tempahan",
    "Booking Services": "Perkhidmatan Tempahan",
    "General GP Visit": "Lawatan GP Am",
    "Checkup & Test": "Pemeriksaan & Ujian",
    "Vaccination": "Vaksinasi",
    "Report Result Booking": "Tempahan Hasil Laporan",
    "View Booking": "Lihat Tempahan",
    "Reschedule Booking": "Jadual Semula Tempahan",
    "Hi, you have new notification(s), please tap on \"notification\" button in the Main Menu to check them out.": "Anda ada pemberitahuan baru, sila tekan butang \"pemberitahuan\" di Menu Utama untuk melihat.",
    "❓Help": "❓Bantuan",
    
    # From calendar_utils.py - TITLES
    "Choose Doctor": "Pilih Doktor",
    "Available Doctors": "Doktor Tersedia",
    "Any Doctor": "Mana-mana Doktor",
    "Choose Date": "Pilih Tarikh",
    "Available Dates": "Tarikh Tersedia",
    "Choose Hour": "Pilih Jam",
    "Available Hours": "Jam Tersedia",
    "Choose Slot": "Pilih Slot",
    "30min Slots": "Slot 30min",
    "Confirm": "Sahkan",
    
    # From menu.py + main.py - TITLES
    "Select Language": "Pilih Bahasa",
    "Languages": "Bahasa",
    "English": "English",
    "Bahasa Malaysia": "Bahasa Malaysia",
    "中文": "中文",
    "தமிழ்": "தமிழ்",
    
    # From calendar_utils.py - CONTENT
    "Select a doctor for your appointment or choose 'Any Doctor':": "Pilih doktor untuk temujanji anda atau pilih 'Mana-mana Doktor':",
    "Select a date for your appointment:": "Pilih tarikh untuk temujanji anda:",
    "Select an hour for {}:": "Pilih jam untuk {}:",
    "Select {}min slot for {} {}:": "Pilih slot {}min untuk {} {}:",
    "No doctors available. Please contact support.": "Tiada doktor tersedia. Sila hubungi sokongan.",
    "Unable to fetch doctors. Please try again.": "Tidak dapat mengambil maklumat doktor. Sila cuba lagi.",
    "An error occurred while fetching doctors: {}. Please try again.": "Berlaku ralat semasa mengambil maklumat doktor: {}. Sila cuba lagi.",
    "No available dates in the next 14 days. Please select another doctor.": "Tiada tarikh tersedia dalam 14 hari akan datang. Sila pilih doktor lain.",
    "No available dates in the next 14 days. Please try again later.": "Tiada tarikh tersedia dalam 14 hari akan datang. Sila cuba lagi nanti.",
    "Unable to fetch calendar. Please try again.": "Tidak dapat mengambil kalendar. Sila cuba lagi.",
    "An error occurred while fetching the calendar: {}. Please try again.": "Berlaku ralat semasa mengambil kalendar: {}. Sila cuba lagi.",
    "No available hours for this date. Please select another date.": "Tiada jam tersedia untuk tarikh ini. Sila pilih tarikh lain.",
    "Unable to fetch hours. Please try again.": "Tidak dapat mengambil maklumat jam. Sila cuba lagi.",
    "An error occurred while fetching hours: {}. Please try again.": "Berlaku ralat semasa mengambil maklumat jam: {}. Sila cuba lagi.",
    "No available time slots.": "Tiada slot masa tersedia.",
    "Error loading slots.": "Ralat memuat slot.",
    "Selected time slot is no longer available. Please choose another.": "Slot masa yang dipilih tidak lagi tersedia. Sila pilih yang lain.",
    "No doctors available for this time slot. Please select another.": "Tiada doktor tersedia untuk slot masa ini. Sila pilih yang lain.",
    "Confirm your booking:\n• Service: {}\n• Doctor: {}\n• Date: {}\n• Time: {}\n• Duration: {} min\n• Details: {}": "Sahkan tempahan anda:\n• Perkhidmatan: {}\n• Doktor: {}\n• Tarikh: {}\n• Masa: {}\n• Tempoh: {} min\n• Butiran: {}",
    "The booking is not placed": "Tempahan tidak dibuat",
    
    # From menu.py + main.py - CONTENT
    "Please select your preferred language:": "Sila pilih bahasa pilihan anda:",
    "Choose a language to proceed": "Pilih bahasa untuk teruskan",
    "Error setting language. Please try again.": "Ralat menetapkan bahasa. Sila cuba lagi.",
    "Invalid selection. Please try again.": "Pilihan tidak sah. Sila cuba lagi.",
    "Invalid button selection. Please try again.": "Pilihan butang tidak sah. Sila cuba lagi.",
    
    # From utils.py - CONTENT
    "Please choose a booking option:": "Sila pilih pilihan tempahan:",
    
    # From notification.py
    "No notifications found.": "Tiada pemberitahuan ditemui.",
    "✅ {} notification(s) displayed!": "✅ {} pemberitahuan dipaparkan!",
    
    # From view_booking.py - TITLES
    "View Booking Options": "Lihat Pilihan Tempahan",
    "View Past Consultations": "Lihat Perundingan Terdahulu",
    "View Upcoming Bookings": "Lihat Tempahan Akan Datang",
    "Request Report": "Minta Laporan",
    "Past Consultations": "Perundingan Terdahulu",
    "Select Option": "Pilih Pilihan",
    
    # From view_booking.py - CONTENT
    "You have no past consultations.": "Anda tiada perundingan terdahulu.",
    "Your past consultations:": "Perundingan terdahulu anda:",
    "Consultation with Dr. {} at {} on {} (Diagnosis: {})": "Perundingan dengan Dr. {} di {} pada {} (Diagnosis: {})",
    "Select a past consultation to request a report:": "Pilih perundingan terdahulu untuk minta laporan:",
    "Consultation {}": "Perundingan {}",
    "User not found. Please ensure your number is registered.": "Pengguna tidak ditemui. Sila pastikan nombor anda didaftarkan.",
    "Error fetching user information. Please try again.": "Ralat mengambil maklumat pengguna. Sila cuba lagi.",
    "Error fetching doctor information. Please try again.": "Ralat mengambil maklumat doktor. Sila cuba lagi.",
    "Error fetching clinic information. Please try again.": "Ralat mengambil maklumat klinik. Sila cuba lagi.",
    "Error fetching past consultations. Please try again.": "Ralat mengambil perundingan terdahulu. Sila cuba lagi.",
    "Error processing timezone. Please try again.": "Ralat memproses zon waktu. Sila cuba lagi.",
    "You have no upcoming bookings.": "Anda tiada tempahan akan datang.",
    "Action Required": "Tindakan Diperlukan",
    "Confirmed": "Disahkan",
    "Pending": "Belum Disahkan",
    "Consultation with Dr. {} at {} on {} at {} (Symptoms: {})": "Perundingan dengan Dr. {} di {} pada {} pada {} (Gejala: {})",
    "Checkup ({}) with Dr. {} at {} on {} at {}": "Pemeriksaan ({}) dengan Dr. {} di {} pada {}",
    "Vaccination ({}) with Dr. {} at {} on {} at {}": "Vaksinasi ({}) dengan Dr. {} di {} pada {}",
    "Pending {} ({}) with Dr. {} at {} on {} at {}": "Belum Disahkan {} ({}) dengan Dr. {} di {} pada {}",
    "{} ({}) with Dr. {} at {} on {} at {} (New: {} at {})": "{} ({}) dengan Dr. {} di {} pada {} (Baru: {} pada {})",
    "Error fetching consultation bookings. Continuing with other bookings.": "Ralat mengambil tempahan perundingan. Meneruskan dengan tempahan lain.",
    "Error fetching checkup bookings. Continuing with other bookings.": "Ralat mengambil tempahan pemeriksaan. Meneruskan dengan tempahan lain.",
    "Error fetching vaccination bookings. Continuing with other bookings.": "Ralat mengambil tempahan vaksinasi. Meneruskan dengan tempahan lain.",
    "Error fetching pending bookings. Continuing with other bookings.": "Ralat mengambil tempahan belum disahkan. Meneruskan dengan tempahan lain.",
    "Error fetching reschedule requests. Continuing with other bookings.": "Ralat mengambil permintaan jadual semula. Meneruskan dengan tempahan lain.",
    "Please select an option:": "Sila pilih pilihan:",
    "Error displaying the booking menu. Please try again.": "Ralat memaparkan menu tempahan. Sila cuba lagi.",
    "An unexpected error occurred while fetching past consultations. Please try again.": "Ralat tidak dijangka berlaku semasa mengambil perundingan terdahulu. Sila cuba lagi.",
    "An unexpected error occurred while fetching upcoming bookings. Please try again.": "Ralat tidak dijangka berlaku semasa mengambil tempahan akan datang. Sila cuba lagi.",
    
    # From reschedule_booking.py - TITLES
    "Choose Category": "Pilih Kategori",
    "Categories": "Kategori",
    "Choose Booking": "Pilih Tempahan",
    "Bookings": "Tempahan",
    "Reschedule": "Jadual Semula",
    "Cancel Booking": "Batal Tempahan",
    "Accept": "Terima",
    "Decline": "Tolak",
    
    # From reschedule_booking.py - CONTENT
    "You have no upcoming bookings to reschedule.": "Anda tiada tempahan akan datang untuk dijadual semula.",
    "Select a category to reschedule from:": "Pilih kategori untuk jadual semula dari:",
    "Select a booking to manage:": "Pilih tempahan untuk urus:",
    "Selected: {}": "Dipilih: {}",
    "Booking {}": "Tempahan {}",
    "Invalid category selection. Please try again.": "Pilihan kategori tidak sah. Sila cuba lagi.",
    "No bookings available in {} category.": "Tiada tempahan tersedia dalam kategori {}.",
    "Invalid booking selection. Please try again.": "Pilihan tempahan tidak sah. Sila cuba lagi.",
    "You have accepted the reschedule. Your {} is now confirmed on {} at {}.": "Anda telah menerima jadual semula. {} anda kini disahkan pada {} pada {}.",
    "You have declined the reschedule request.": "Anda telah menolak permintaan jadual semula.",
    "Your booking has been cancelled.": "Tempahan anda telah dibatalkan.",
    "Invalid booking ID format. Please try again.": "Format ID tempahan tidak sah. Sila cuba lagi.",
    "Reschedule request not found or has invalid data. Please try again.": "Permintaan jadual semula tidak ditemui atau data tidak sah. Sila cuba lagi.",
    "Invalid booking type for reschedule request.": "Jenis tempahan tidak sah untuk permintaan jadual semula.",
    "Booking not found. It may have already been cancelled.": "Tempahan tidak ditemui. Mungkin telah dibatalkan.",
    "✅ RESCHEDULED!\n\n{} moved to {} at {} with Dr. {} ({}min)\nStatus: PENDING APPROVAL": "✅ DIJADUAL SEMULA!\n\n{} dipindahkan ke {} pada {} dengan Dr. {} ({}min)\nStatus: MENUNGGU KELULUSAN",
    "Booking not found!": "Tempahan tidak ditemui!",
    "Save error! Please try again.": "Ralat simpan! Sila cuba lagi.",
    "An error occurred during rescheduling. Please try again.": "Berlaku ralat semasa menjadual semula. Sila cuba lagi.",
    "Invalid input. Please try again.": "Input tidak sah. Sila cuba lagi.",
    
    # From checkup_booking.py
    "Please select a checkup type:": "Sila pilih jenis pemeriksaan:",
    "Choose Checkup": "Pilih Pemeriksaan",
    "Checkup Types": "Jenis Pemeriksaan",
    "Please specify the checkup type:": "Sila nyatakan jenis pemeriksaan:",
    "Do you have any remarks for {} ({} min)?": "Adakah anda ada catatan untuk {} ({} min)?",
    "Yes": "Ya",
    "No": "Tidak",
    "Please enter your remarks:": "Sila masukkan catatan anda:",
    "Your checkup booking is pending approval by the admin.": "Tempahan pemeriksaan anda sedang menunggu kelulusan admin.",
    
    # From report_symptom.py
    "Please describe your symptoms.": "Sila huraikan gejala anda.",
    
    # From vaccination.py
    "Please select a vaccine type:": "Sila pilih jenis vaksin:",
    "Choose Vaccine": "Pilih Vaksin",
    "Vaccine Types": "Jenis Vaksin",
    "Please specify the vaccine type:": "Sila nyatakan jenis vaksin:",
    
    # From report_booking.py
    "📋 Select Report": "📋 Pilih Laporan",
    "Select Report": "Pilih Laporan",
    "Your Reports": "Laporan Anda",
    "No pending reports found. Please book a checkup first.": "Tiada laporan menunggu ditemui. Sila tempah pemeriksaan dahulu.",
    "Choose a report to book review:": "Pilih laporan untuk tempah semakan:",
    "Bkng {}": "Tempahan {}",
    "Error fetching reports. Please try again.": "Ralat mengambil laporan. Sila cuba lagi.",
    "Error: No doctor found for this report. Contact support.": "Ralat: Tiada doktor ditemui untuk laporan ini. Hubungi sokongan.",
    "Error selecting report. Please try again.": "Ralat memilih laporan. Sila cuba lagi.",
    "✅ Your report review booking is pending approval!": "✅ Tempahan semakan laporan anda sedang menunggu kelulusan!",
    "Error creating booking. Please try again.": "Ralat membuat tempahan. Sila cuba lagi.",
    "Please confirm your booking:\nReport: {}\nDoctor: {}\nDate: {}\nTime: {}\nDuration: {} min": "Sila sahkan tempahan anda:\nLaporan: {}\nDoktor: {}\nTarikh: {}\nMasa: {}\nTempoh: {} min",
    
    # From post_report.py
    "Invalid selection. Please try again.": "Pilihan tidak sah. Sila cuba lagi.",
    "Error processing your selection. Please try again.": "Ralat memproses pilihan anda. Sila cuba lagi.",
    "Error fetching consultation details. Please try again.": "Ralat mengambil butiran perundingan. Sila cuba lagi.",
    "Consultation not found or not associated with this number. Please try again.": "Perundingan tidak ditemui atau tidak berkaitan dengan nombor ini. Sila cuba lagi.",
    "Error generating report request. Please try again.": "Ralat menjana permintaan laporan. Sila cuba lagi.",
    "Error processing report request. Please try again.": "Ralat memproses permintaan laporan. Sila cuba lagi.",
    "Please enter the patient's IC in the format 'verified:<IC>', e.g., verified:123456789011": "Sila masukkan IC pesakit dalam format 'verified:<IC>', contoh: verified:123456789011",
    "An unexpected error occurred while processing your report request. Please try again.": "Ralat tidak dijangka berlaku semasa memproses permintaan laporan anda. Sila cuba lagi.",
    "IC verification failed. Please enter the correct patient IC.": "Pengesahan IC gagal. Sila masukkan IC pesakit yang betul.",
    "No report request found. Please try again.": "Tiada permintaan laporan ditemui. Sila cuba lagi.",
    "Invalid report request status. Please try again.": "Status permintaan laporan tidak sah. Sila cuba lagi.",
    "Error processing verification. Please try again.": "Ralat memproses pengesahan. Sila cuba lagi.",
    "IC verified, but error sending report. Please try again.": "IC disahkan, tetapi ralat menghantar laporan. Sila cuba lagi.",
    "IC verified, but the report is not yet available. You will be notified when ready.": "IC disahkan, tetapi laporan belum tersedia. Anda akan dimaklumkan apabila sedia.",
    "IC verified successfully, but no report request pending. Please select a consultation.": "IC berjaya disahkan, tetapi tiada permintaan laporan menunggu. Sila pilih perundingan.",
    "Invalid verification format. Please use 'verified:<IC>'.": "Format pengesahan tidak sah. Sila gunakan 'verified:<IC>'.",
    "A referral letter has been generated. Please contact your healthcare provider for details.": "Surat rujukan telah dijana. Sila hubungi pembekal penjagaan kesihatan anda untuk butiran.",
    "No referral required.": "Tiada rujukan diperlukan.",
    "IC verified. Report for consultation on {} (Diagnosis: {}):\n{}\n\n{}": "IC disahkan. Laporan untuk perundingan pada {} (Diagnosis: {}):\n{}\n\n{}",
    "Booking cancelled.": "Tempahan dibatalkan.",
    
    # ========== NEW TRANSLATIONS FROM PROVIDED FILES ==========
    
    # view_booking.py – body text
    "Pending with Dr. {doctornamedrname} at {clinicname} on {pdate} at {ptime}.": "Belum Disahkan dengan Dr. {doctornamedrname} di {clinicname} pada {pdate} {ptime}.",
    "Unknown": "Tidak Diketahui",
    "Unknown Clinic": "Klinik Tidak Diketahui",
    "with Dr. {doctornamedrname} at {clinicname} on {roriginaldate} at {roriginaltime}. New at {rnewdate} at {rnewtime}.": "dengan Dr. {doctornamedrname} di {clinicname} pada {roriginaldate} {roriginaltime}. Baru pada {rnewdate} {rnewtime}.",
    "Unknown Provider": "Pembekal Tidak Diketahui",
    "Patient": "Pesakit",
    "Home-to-Home Transfer for {patientname} on {bscheduleddate} at {scheduledtimedisplay}. Provider {providername}, Distance {distance} km.": "Pemindahan Rumah ke Rumah untuk {patientname} pada {bscheduleddate} {scheduledtimedisplay}. Pembekal {providername}, Jarak {distance} km.",
    "Hospital": "Hospital",
    "Appointment at {bappointmentdate} {bappointmenttime}": "Temujanji pada {bappointmentdate} {bappointmenttime}",
    "Home-to-Hospital Transfer for {patientname} to {hospitalname} {appointmentinfo} on {bscheduleddate} at {scheduledtimedisplay}. Provider {providername}.": "Pemindahan Rumah ke Hospital untuk {patientname} ke {hospitalname} {appointmentinfo} pada {bscheduleddate} {scheduledtimedisplay}. Pembekal {providername}.",
    "TCM {bookingtypetranslated} with Dr. {doctornamedrname} at {clinicname} on {boriginaldate} at {boriginaltime}. New at {bnewdate} at {bnewtime} - Doctor Requested Reschedule": "TCM {bookingtypetranslated} dengan Dr. {doctornamedrname} di {clinicname} pada {boriginaldate} {boriginaltime}. Baru pada {bnewdate} {bnewtime} - Doktor Minta Jadual Semula",
    "TCM {bookingtypetranslated} with Dr. {doctornamedrname} at {clinicname} on {displaydate} at {displaytime} - Doctor Requested Reschedule": "TCM {bookingtypetranslated} dengan Dr. {doctornamedrname} di {clinicname} pada {displaydate} {displaytime} - Doktor Minta Jadual Semula",
    "{prefix} TCM {bookingtypetranslated} with Dr. {doctornamedrname} at {clinicname} on {displaydate} at {displaytime}. Details {details}": "{prefix} TCM {bookingtypetranslated} dengan Dr. {doctornamedrname} di {clinicname} pada {displaydate} {displaytime}. Butiran {details}",
    "{prefix} {bookingtypetranslated} with Dr. {doctornamedrname} at {clinicname} on {displaydate} at {displaytime}. Details {details}": "{prefix} {bookingtypetranslated} dengan Dr. {doctornamedrname} di {clinicname} pada {displaydate} {displaytime}. Butiran {details}",
    "Appointment at {appointmentdate} {appointmenttime}": "Temujanji pada {appointmentdate} {appointmenttime}",
    "TCM {bookingtypetranslated}": "TCM {bookingtypetranslated}",
    "TCM RESCHEDULE ACCEPTED - You have accepted the reschedule. Your TCM {bookingtypetranslated} is now confirmed on {datanewdate} at {datanewtime} with Dr. {doctorname}.": "JADUAL SEMULA TCM DITERIMA - Anda telah menerima jadual semula. TCM {bookingtypetranslated} anda kini disahkan pada {datanewdate} {datanewtime} dengan Dr. {doctorname}.",
    "ERROR accepting TCM reschedule. Please try again.": "RALAT menerima jadual semula TCM. Sila cuba lagi.",
    "TCM Doctor": "Doktor TCM",
    "TCM RESCHEDULE DECLINED - You have declined the reschedule request. Your TCM {bookingtypetranslated} remains confirmed on {dataoriginaldate} at {dataoriginaltime} with Dr. {doctorname}.": "JADUAL SEMULA TCM DITOLAK - Anda telah menolak permintaan jadual semula. TCM {bookingtypetranslated} anda kekal disahkan pada {dataoriginaldate} {dataoriginaltime} dengan Dr. {doctorname}.",
    "TCM RESCHEDULE DECLINED - You have declined the reschedule request.": "JADUAL SEMULA TCM DITOLAK - Anda telah menolak permintaan jadual semula.",
    "ERROR declining TCM reschedule. Please try again.": "RALAT menolak jadual semula TCM. Sila cuba lagi.",
    "REPEATED VISIT CANCELLATION - This booking is part of a repeated visit series. Do you want to cancel just this booking or all future repeated bookings?": "PEMBATALAN LAWATAN BERULANG - Tempahan ini adalah sebahagian daripada siri lawatan berulang. Adakah anda ingin membatalkan tempahan ini sahaja atau semua tempahan berulang masa depan?",
    "Cancel This One Only": "Batal Yang Ini Sahaja",
    "Cancel All Repeated": "Batal Semua Berulang",
    "Back": "Kembali",
    "ERROR cancelling booking. Please try again.": "RALAT membatalkan tempahan. Sila cuba lagi.",
    "CANCELLATION FAILED - Booking not found. It may have already been cancelled.": "PEMBATALAN GAGAL - Tempahan tidak ditemui. Mungkin telah dibatalkan.",
    "BOOKING CANCELLED - The booking has been successfully cancelled.": "TEMPAHAN DIBATALKAN - Tempahan telah berjaya dibatalkan.",
    "Invalid input. Please use the buttons provided.": "Input tidak sah. Sila gunakan butang yang disediakan.",
    "Please enter your preferred date as DDMMYYYY, DD-MM-YYYY or DD MM YYYY": "Sila masukkan tarikh pilihan anda sebagai DDMMYYYY, DD-MM-YYYY atau DD MM YYYY",
    "Please enter your remarks": "Sila masukkan catatan anda",
    "Please enter your preferred time e.g., 930, 2pm, 1430": "Sila masukkan masa pilihan anda cth., 930, 2pm, 1430",
    
    # tcm_calendar_utils.py – body text & buttons
    "Future Date": "Tarikh Masa Depan",
    "No available dates in the next 14 days. Please {selectanotherdoctor}.": "Tiada tarikh tersedia dalam 14 hari akan datang. Sila {selectanotherdoctor}.",
    "select another doctor": "pilih doktor lain",
    "try again later": "cuba lagi nanti",
    "Select a date for your appointment": "Pilih tarikh untuk temujanji anda",
    "Unable to fetch calendar. Please try again.": "Tidak dapat mengambil kalendar. Sila cuba lagi.",
    "An error occurred while fetching the calendar {error}. Please try again.": "Berlaku ralat semasa mengambil kalendar {error}. Sila cuba lagi.",
    "Clinic not selected. Please start over.": "Klinik tidak dipilih. Sila mula semula.",
    "No available hours for this date. Please select another date.": "Tiada jam tersedia untuk tarikh ini. Sila pilih tarikh lain.",
    "No doctors available for this time slot. Please select another.": "Tiada doktor tersedia untuk slot masa ini. Sila pilih yang lain.",
    "No doctors available. Please contact support.": "Tiada doktor tersedia. Sila hubungi sokongan.",
    "Confirm your TCM booking\n\nService: {servicetype}\nDoctor: {doctorname}\nDate: {date}\nTime: {timeslot}\nDuration: {duration} min\nDetails: {details}\nReminder: {translatedreminder}": "Sahkan tempahan TCM anda\n\nPerkhidmatan: {servicetype}\nDoktor: {doctorname}\nTarikh: {date}\nMasa: {timeslot}\nTempoh: {duration} min\nButiran: {details}\nPeringatan: {translatedreminder}",
    "Confirm your TCM booking\n\nService: {servicetype}\nDoctor: Assigned by Clinic\nDate: {date}\nTime: {timeslot}\nDuration: {duration} min\nDetails: {details}\nReminder: {translatedreminder}": "Sahkan tempahan TCM anda\n\nPerkhidmatan: {servicetype}\nDoktor: Ditentukan oleh Klinik\nTarikh: {date}\nMasa: {timeslot}\nTempoh: {duration} min\nButiran: {details}\nPeringatan: {translatedreminder}",
    "An error occurred while confirming the booking. Please try again.": "Berlaku ralat semasa mengesahkan tempahan. Sila cuba lagi.",
    "AM": "AM",
    "PM": "PM",
    "Select AM or PM for {date}": "Pilih AM atau PM untuk {date}",
    
    # tcm_service.py – headers, body, buttons
    "Clinic not found. Please select another clinic.": "Klinik tidak ditemui. Sila pilih klinik lain.",
    "Address": "Alamat",
    "Now please select a treatment category": "Sekarang sila pilih kategori rawatan",
    "Unable to load clinic information. Please try again.": "Tidak dapat memuat maklumat klinik. Sila cuba lagi.",
    "Unable to load TCM services. Please try again.": "Tidak dapat memuat perkhidmatan TCM. Sila cuba lagi.",
    "No {tcmtype} clinics available at the moment. Please select another service type.": "Tiada klinik {tcmtype} tersedia buat masa ini. Sila pilih jenis perkhidmatan lain.",
    "Unable to load TCM clinics. Please try again.": "Tidak dapat memuat klinik TCM. Sila cuba lagi.",
    "No categories available for this clinic. Please select another clinic.": "Tiada kategori tersedia untuk klinik ini. Sila pilih klinik lain.",
    "Unable to load categories. Please try again.": "Tidak dapat memuat kategori. Sila cuba lagi.",
    "Error - Clinic or category not selected. Please start over.": "Ralat - Klinik atau kategori tidak dipilih. Sila mula semula.",
    "No services available in this category. Please select another category.": "Tiada perkhidmatan tersedia dalam kategori ini. Sila pilih kategori lain.",
    "Unable to load services. Please try again.": "Tidak dapat memuat perkhidmatan. Sila cuba lagi.",
    "TCM Services": "Perkhidmatan TCM",
    "Please select the type of TCM service you need": "Sila pilih jenis perkhidmatan TCM yang anda perlukan",
    "Choose a service type to proceed": "Pilih jenis perkhidmatan untuk teruskan",
    "Select Type": "Pilih Jenis",
    "TCM Service Types": "Jenis Perkhidmatan TCM",
    "Chiropractic": "Kiropraktik",
    "Spinal adjustments, posture correction": "Pelarasan tulang belakang, pembetulan postur",
    "Physiotherapy": "Fisioterapi",
    "Muscle therapy, joint mobilization": "Terapi otot, mobilisasi sendi",
    "Back to Services": "Kembali ke Perkhidmatan",
    "Please select a clinic": "Sila pilih klinik",
    "Choose a clinic to proceed": "Pilih klinik untuk teruskan",
    "Select Clinic": "Pilih Klinik",
    "Available Clinics": "Klinik Tersedia",
    "Back to Type Selection": "Kembali ke Pemilihan Jenis",
    "Please select a treatment category": "Sila pilih kategori rawatan",
    "Choose a category to proceed": "Pilih kategori untuk teruskan",
    "Select Category": "Pilih Kategori",
    "Treatment Categories": "Kategori Rawatan",
    "Back to Clinics": "Kembali ke Klinik",
    "Please select a treatment service": "Sila pilih perkhidmatan rawatan",
    "Choose a service to proceed": "Pilih perkhidmatan untuk teruskan",
    "Select Service": "Pilih Perkhidmatan",
    "Back to Categories": "Kembali ke Kategori",
    "{duration} min": "{duration} min",
    
    # webhooksplit.py – body text
    "Thank you for acknowledging the notification. Let us know if you need any assistance.": "Terima kasih mengakui pemberitahuan. Beritahu kami jika anda perlukan bantuan.",
    
    # Headers
    "1. Relationship": "1. Hubungan",
    "📍 Current Address (Pickup)": "📍 Alamat Semasa (Ambil)",
    "📍 Pickup Address Found": "📍 Alamat Ambil Ditemui",
    "📍 Destination Address Found": "📍 Alamat Destinasi Ditemui",
    "📱 Destination Emergency Contact": "📱 Kenalan Kecemasan Destinasi",
    "📎 Attachments": "📎 Lampiran",
    "📝 Remarks": "📝 Catatan",
    "📅 Select Transfer Date": "📅 Pilih Tarikh Pemindahan",
    "📅 Select {} Date": "📅 Pilih Tarikh {}",
    "⏰ Select 2-Hour Slot ({})": "⏰ Pilih Slot 2 Jam ({})",
    "🏥 Current Hospital Address Found": "🏥 Alamat Hospital Semasa Ditemui",
    "🏥 Destination Hospital Address Found": "🏥 Alamat Hospital Destinasi Ditemui",
    "Select Individual": "Pilih Individu",
    "Options for {}": "Pilihan untuk {}",
    
    # Footers
    "Choose a language to proceed": "Pilih bahasa untuk teruskan",
    "Select one option": "Pilih satu pilihan",
    "Multiple profiles found for your account": "Berbilang profil ditemui untuk akaun anda",
    
    # Buttons
    "Try Again": "Cuba Lagi",
    "Help Me Choose": "Bantu Saya Pilih",
    "Find Another": "Cari Lain",
    "Try Another Time": "Cuba Masa Lain",
    "Yes - Life Threat": "Ya - Ancaman Nyawa",
    "No - Not Immediate": "Tidak - Tidak Segera",
    "❌ Cancel": "❌ Batal",
    "Select": "Pilih",
    "Parent": "Ibu Bapa",
    "Child": "Anak",
    "Relative": "Saudara",
    "Stranger": "Orang Asing",
    "📍 Share Location": "📍 Kongsi Lokasi",
    "📝 Type Address": "📝 Taip Alamat",
    "✅ Yes, Correct": "✅ Ya, Betul",
    "✏️ Edit Address": "✏️ Edit Alamat",
    "✅ Yes": "✅ Ya",
    "❌ No": "❌ Tidak",
    "Next": "Seterusnya",
    "Skip": "Langkau",
    "Add Remarks": "Tambah Catatan",
    "Today": "Hari Ini",
    "Tomorrow": "Esok",
    "Others": "Lain-lain",
    "AM (12am - 11:45am)": "AM (12am - 11:45am)",
    "PM (12pm - 11:45pm)": "PM (12pm - 11:45pm)",
    "Select Time Slot": "Pilih Slot Masa",
    "❌ No, Different": "❌ Tidak, Berbeza",
    "🔙 Back to Main Menu": "🔙 Kembali ke Menu Utama",
    "🔙 Back to Booking": "🔙 Kembali ke Tempahan",
    "🔙 Back to Main": "🔙 Kembali ke Utama",
    "🏥 Clinic Services": "🏥 Perkhidmatan Klinik",
    "🌿 TCM Services": "🌿 Perkhidmatan TCM",
    "🚑 Ambulance Service": "🚑 Perkhidmatan Ambulans",
    "💅 Aesthetic": "💅 Estetik",
    "🏨 Hospital": "🏨 Hospital",
    "💉 Dialysis": "💉 Dialisis",
    "👴 Elderly Care": "👴 Penjagaan Warga Emas",
    "🔙 Back to Menu": "🔙 Kembali ke Menu",
    "⚔️ Enemy (Disease)": "⚔️ Musuh (Penyakit)",
    "💊 Med & Routine": "💊 Ubat & Rutin",
    "📄 Report": "📄 Laporan",
    "🔙 Back to Patients": "🔙 Kembali ke Pesakit",
    "⬅️ Previous Page": "⬅️ Halaman Sebelum",
    "➡️ Next Page": "➡️ Halaman Seterusnya",

    # Main Menu Confirmation
    "⚠️ *Main Menu Confirmation*\n\nAre you sure you want to go back to the main menu?\nThis will cancel your current action.": "⚠️ *Pengesahan Menu Utama*\n\nAdakah anda pasti ingin kembali ke menu utama?\nIni akan membatalkan tindakan semasa anda.",
    "✅ Yes": "✅ Ya",
    "❌ No": "❌ Tidak",

    # Interactive Menu
    "AnyHealth Bot": "Bot AnyHealth",
    "Select an option to proceed": "Pilih pilihan untuk teruskan",
    "Menu": "Menu",
    "Main Options": "Pilihan Utama",
    "🔔 Notification": "🔔 Pemberitahuan",
    "👤 Profile": "👤 Profil",
    "🏥 Service Booking": "🏥 Tempahan Perkhidmatan",
    "📅 Upcoming Booking": "📅 Tempahan Akan Datang",
    "❓ Help": "❓ Bantuan",
    "🌐 Languages": "🌐 Bahasa",

    # Booking Submenu
    "Please choose a booking option:": "Sila pilih pilihan tempahan:",
    "Booking Options": "Pilihan Tempahan",
    "Booking Services": "Perkhidmatan Tempahan",
    "📞 Clinic Enquiries": "📞 Pertanyaan Klinik",
    "👨‍⚕️ General GP Visit": "👨‍⚕️ Lawatan GP Am",
    "🩺 Checkup & Test": "🩺 Pemeriksaan & Ujian",
    "💉 Vaccination": "💉 Vaksinasi",
    "🔙 Back to Main Menu": "🔙 Kembali ke Menu Utama",

    # Non-Emergency Menu
    "🚑 Non-Emergency Ambulance": "🚑 Ambulans Bukan Kecemasan",
    "Please select the type of non-emergency transport you need:\n\n• Scheduled patient transport\n• Advance booking required (24 hours)\n• Professional medical team": "Sila pilih jenis pengangkutan bukan kecemasan yang anda perlukan:\n\n• Pengangkutan pesakit berjadual\n• Tempahan awal diperlukan (24 jam)\n• Pasukan perubatan profesional",
    "Choose an option below": "Pilih pilihan di bawah",
    "Select Service": "Pilih Perkhidmatan",
    "Available Services": "Perkhidmatan Tersedia",
    "🏠 → 🏥 Home to Hosp": "🏠 → 🏥 Rumah ke Hospital",
    "🏠 → 🏠 Home to Home": "🏠 → 🏠 Rumah ke Rumah",
    "🏥 → 🏠 Hosp to Home": "🏥 → 🏠 Hospital ke Rumah",
    "🏥 → 🏥 Hosp to Hosp": "🏥 → 🏥 Hospital ke Hospital",

    # State restoration messages
    "Session expired. Returning to main menu.": "Sesi tamat. Kembali ke menu utama.",
    "Continuing with your previous action.": "Meneruskan tindakan sebelumnya anda.",
    "Could not restore previous action. Returning to main menu.": "Tidak dapat memulihkan tindakan sebelumnya. Kembali ke menu utama.",

    # Location request
    "Please share your current location:": "Sila kongsi lokasi semasa anda:",
        
    # Body Text
    "I couldn't understand the time format. Please try entering the time again, or let me help you choose from available slots.": "Saya tidak faham format masa. Sila cuba masukkan masa sekali lagi, atau biar saya bantu anda pilih dari slot yang tersedia.",
    "Great! {} is available. Is this the time you want?": "Bagus! {} tersedia. Adakah ini masa yang anda mahukan?",
    "Unfortunately {} is not available. The closest available time is {} (just {} minutes difference). Would you like to book this instead?": "Malangnya {} tidak tersedia. Masa terdekat yang tersedia ialah {} (hanya {} minit beza). Adakah anda ingin tempah ini sebagai ganti?",
    "Unfortunately {} is not available. The closest available time is {}. Would you like to book this instead?": "Malangnya {} tidak tersedia. Masa terdekat yang tersedia ialah {}. Adakah anda ingin tempah ini sebagai ganti?",
    "No available slots near {}. Would you like to try a different time or let me help you choose from available slots?": "Tiada slot tersedia berhampiran {}. Adakah anda ingin cuba masa lain atau biar saya bantu anda pilih dari slot yang tersedia?",
    "Error processing time. Please try again.": "Ralat memproses masa. Sila cuba lagi.",
    "Select a doctor for your appointment or choose 'Any Doctor':": "Pilih doktor untuk temujanji anda atau pilih 'Mana-mana Doktor':",
    "Unable to fetch doctors. Please try again.": "Tidak dapat mengambil doktor. Sila cuba lagi.",
    "An error occurred while fetching doctors: {}. Please try again.": "Berlaku ralat semasa mengambil doktor: {}. Sila cuba lagi.",
    "Time slot not found. Please try again.": "Slot masa tidak ditemui. Sila cuba lagi.",
    "Please enter your preferred time (e.g., 9:30, 2pm, 1430):": "Sila masukkan masa pilihan anda (cth., 9:30, 2pm, 1430):",
    "Error confirming time. Please try again.": "Ralat mengesahkan masa. Sila cuba lagi.",
    "Error processing choice. Please try again.": "Ralat memproses pilihan. Sila cuba lagi.",
    "Invalid date format. Please enter date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:": "Format tarikh tidak sah. Sila masukkan tarikh sebagai DD/MM/YYYY, DD-MM-YYYY atau DD MM YYYY:",
    "Error: No service selected. Please start over.": "Ralat: Tiada perkhidmatan dipilih. Sila mula semula.",
    "Do you have any remarks for {} ({} min){}?": "Adakah anda ada catatan untuk {} ({} min){}?",
    "⚠️ *ERROR STARTING EMERGENCY*\n\nUnable to start emergency service. Please try again or call 999 immediately.": "⚠️ *RALAT MEMULAKAN KECEMASAN*\n\nTidak dapat memulakan perkhidmatan kecemasan. Sila cuba lagi atau hubungi 999 segera.",
    "⚠️ *ERROR STARTING EMERGENCY*\n\nAn error occurred. Please call 999 immediately for emergency assistance.": "⚠️ *RALAT MEMULAKAN KECEMASAN*\n\nBerlaku ralat. Sila hubungi 999 segera untuk bantuan kecemasan.",
    "🚑 *EMERGENCY SERVICE*\n\nIs the patient's LIFE or FUNCTION at immediate risk?\n\nExamples of life-threatening emergencies:\n• Chest pain/heart attack\n• Severe difficulty breathing\n• Unconsciousness\n• Severe bleeding\n• Stroke symptoms\n• Major trauma/injury\n\nIf YES, ambulance will be dispatched immediately.\nIf NO, we'll collect more information first.": "🚑 *PERKHIDMATAN KECEMASAN*\n\nAdakah NYAWA atau FUNGSI pesakit dalam risiko segera?\n\nContoh kecemasan yang mengancam nyawa:\n• Sakit dada/serangan jantung\n• Kesukaran bernafas teruk\n• Tidak sedar\n• Pendarahan teruk\n• Gejala strok\n• Trauma/kecederaan besar\n\nJika YA, ambulans akan dihantar segera.\nJika TIDAK, kami akan kumpulkan lebih banyak maklumat dahulu.",
    "📍 *LOCATION REQUIRED*\n\nWe need your current location to check if you're within our service area.\n\n**Please use one of these methods:**\n1. Tap 'Share Location' button below (recommended)\n2. Or type your address manually\n Example: No 12, Jalan Tun Razak, Kuala Lumpur\n\n**Important:**\n• Share exact location for distance check\n• Service area: Within 15km of our clinic\n• We'll notify you immediately if within range": "📍 *LOKASI DIPERLUKAN*\n\nKami perlukan lokasi semasa anda untuk semak jika anda dalam kawasan perkhidmatan kami.\n\n**Sila gunakan salah satu kaedah ini:**\n1. Tekan butang 'Kongsi Lokasi' di bawah (disyorkan)\n2. Atau taip alamat anda secara manual\n Contoh: No 12, Jalan Tun Razak, Kuala Lumpur\n\n**Penting:**\n• Kongsi lokasi tepat untuk semakan jarak\n• Kawasan perkhidmatan: Dalam 15km dari klinik kami\n• Kami akan maklumkan anda segera jika dalam lingkungan",
    "❌ *ADDRESS NOT FOUND*\n\nWe couldn't find the address you provided.\n\n**Please try:**\n• A more specific address\n• Include city and state\n• Example: 'No 12, Jalan Tun Razak, Kuala Lumpur'\n\nOr use the 'Share Location' button for automatic detection.": "❌ *ALAMAT TIDAK DITEMUI*\n\nKami tidak dapat mencari alamat yang anda berikan.\n\n**Sila cuba:**\n• Alamat yang lebih spesifik\n• Termasuk bandar dan negeri\n• Contoh: 'No 12, Jalan Tun Razak, Kuala Lumpur'\n\nAtau gunakan butang 'Kongsi Lokasi' untuk pengesanan automatik.",
    "⚠️ *ERROR PROCESSING ADDRESS*\n\nThere was an error processing your address. Please try sharing your location instead.": "⚠️ *RALAT MEMPROSES ALAMAT*\n\nBerlaku ralat memproses alamat anda. Sila cuba kongsi lokasi anda sebaliknya.",
    "🚨 *DISTANCE ALERT*\n\nYour location is {} km away from our clinic.\n\n*Our Clinic Location:*\n{}\n\n*Service Radius:* 15 km\n*Your Distance:* {} km\n\n⚠️ *You are outside our service area.*\n\n**Please call 999 immediately for emergency assistance.**\n\nAlert ID: {}\nStatus: Referred to 999 emergency services": "🚨 *AMARAN JARAK*\n\nLokasi anda ialah {} km dari klinik kami.\n\n*Lokasi Klinik Kami:*\n{}\n\n*Radius Perkhidmatan:* 15 km\n*Jarak Anda:* {} km\n\n⚠️ *Anda di luar kawasan perkhidmatan kami.*\n\n**Sila hubungi 999 segera untuk bantuan kecemasan.**\n\nID Amaran: {}\nStatus: Dirujuk ke perkhidmatan kecemasan 999",
    "✅ *LOCATION CONFIRMED*\n\n*Address:* {}\n*Distance from clinic:* {} km\n*Status:* Within service area ✓\n\n🚨 *EMERGENCY TEAM NOTIFIED*\n\nAlert ID: {}\nTime: {}\n\nWe already notified the team, we will have the team departing ready, will update when departed...\n\n*STAY CALM AND DO NOT MOVE THE PATIENT* unless in immediate danger.\n\nMeanwhile could you please give more info...\nPlease answer the following questions one by one.\n\n---\n*QUESTIONS TO FOLLOW:*\n1. Relationship to patient\n2. Your name\n3. Your IC number\n4. Patient name (can type 'Nil' if unknown)\n5. Patient IC number (Nil for unknown)\n6. Patient condition details\n7. Medical history (if known)\n\nYou can cancel at any time by pressing the 'Cancel Ambulance' button.": "✅ *LOKASI DISAHKAN*\n\n*Alamat:* {}\n*Jarak dari klinik:* {} km\n*Status:* Dalam kawasan perkhidmatan ✓\n\n🚨 *PASUKAN KECEMASAN DIMAKLUMKAN*\n\nID Amaran: {}\nMasa: {}\n\nKami telah memaklumkan pasukan, kami akan sediakan pasukan untuk bertolak, akan kemaskini apabila bertolak...\n\n*KEKAL TENANG DAN JANGAN GERAKKAN PESAKIT* melainkan dalam bahaya segera.\n\nSementara itu bolehkah anda beri lebih maklumat...\nSila jawab soalan berikut satu persatu.\n\n---\n*SOALAN AKAN DATANG:*\n1. Hubungan dengan pesakit\n2. Nama anda\n3. Nombor IC anda\n4. Nama pesakit (boleh taip 'Nil' jika tidak diketahui)\n5. Nombor IC pesakit (Nil jika tidak diketahui)\n6. Butiran keadaan pesakit\n7. Sejarah perubatan (jika diketahui)\n\nAnda boleh batal pada bila-bila masa dengan menekan butang 'Batal Ambulans'.",
    "Select your relationship to the patient:": "Pilih hubungan anda dengan pesakit:",
    "2. *Your name:*\n\nPlease type your full name.\n\nExample: Ali bin Ahmad or Siti binti Mohamad": "2. *Nama anda:*\n\nSila taip nama penuh anda.\n\nContoh: Ali bin Ahmad atau Siti binti Mohamad",
    "3. *Your IC number:*\n\nPlease type your IC number.\n\nExample: 901212-14-5678 or 950505-08-1234": "3. *Nombor IC anda:*\n\nSila taip nombor IC anda.\n\nContoh: 901212-14-5678 atau 950505-08-1234",
    "4. *Patient name:*\n\nPlease type the patient's full name.\n\nExample: Ahmad bin Abdullah or Nor Aishah binti Hassan\n\nYou can type 'Nil' if unknown": "4. *Nama pesakit:*\n\nSila taip nama penuh pesakit.\n\nContoh: Ahmad bin Abdullah atau Nor Aishah binti Hassan\n\nAnda boleh taip 'Nil' jika tidak diketahui",
    "🏠 *AMBULANCE SERVICE: HOME TO HOME TRANSFER*": "🏠 *PERKHIDMATAN AMBULANS: PEMINDAHAN RUMAH KE RUMAH*",
    "Transfer ID:": "ID Pemindahan:",
    "Time:": "Masa:",
    "This service helps transfer patients between homes (e.g., moving to family home).": "Perkhidmatan ini membantu memindahkan pesakit antara rumah (cth., berpindah ke rumah keluarga).",
    "We'll collect information for your home-to-home transfer.": "Kami akan kumpulkan maklumat untuk pemindahan rumah ke rumah anda.",
    "Please answer the following questions one by one.": "Sila jawab soalan berikut satu persatu.",
    "*IMPORTANT:*": "*PENTING:*",
    "• Provide accurate addresses for both locations": "• Beri alamat tepat untuk kedua-dua lokasi",
    "• Ensure patient is stable for transfer": "• Pastikan pesakit stabil untuk dipindahkan",
    "• Have all necessary medical equipment ready": "• Sediakan semua peralatan perubatan yang diperlukan",
    "• Coordinate with family members at both locations": "• Selaras dengan ahli keluarga di kedua-dua lokasi",
    "---": "---",
    "*QUESTIONS TO FOLLOW:*": "*SOALAN AKAN DATANG:*",
    "1. Patient full name": "1. Nama penuh pesakit",
    "2. Patient IC number": "2. Nombor IC pesakit",
    "3. Patient phone number": "3. Nombor telefon pesakit",
    "4. Emergency contact at pickup location": "4. Kenalan kecemasan di lokasi ambil",
    "5. Emergency contact phone at pickup location": "5. Telefon kenalan kecemasan di lokasi ambil",
    "6. Current address (Pickup) with location sharing option": "6. Alamat semasa (Ambil) dengan pilihan perkongsian lokasi",
    "7. Destination address (manual input)": "7. Alamat destinasi (input manual)",
    "8. Reason for transfer": "8. Sebab pemindahan",
    "9. Medical condition": "9. Keadaan perubatan",
    "*After these questions, we'll ask for destination emergency contact, attachments, and schedule.*": "*Selepas soalan-soalan ini, kami akan tanya kenalan kecemasan destinasi, lampiran, dan jadual.*",
    "You can cancel anytime by typing 'cancel'.": "Anda boleh batal pada bila-bila masa dengan menaip 'cancel'.",
    "Error starting transfer request. Please try again.": "Ralat memulakan permintaan pemindahan. Sila cuba lagi.",
    "6. *Current address (Pickup)*": "6. *Alamat semasa (Ambil)*",
    "How would you like to provide your current address?": "Bagaimana anda ingin beri alamat semasa anda?",
    "• *Share Location:* Send your current location (recommended)": "• *Kongsi Lokasi:* Hantar lokasi semasa anda (disyorkan)",
    "• *Type Address:* Enter your full address manually": "• *Taip Alamat:* Masukkan alamat penuh anda secara manual",
    "Example of manual address:": "Contoh alamat manual:",
    "Please type your full current address:": "Sila taip alamat semasa penuh anda:",
    "Example:": "Contoh:",
    "Include:": "Termasuk:",
    "• House/building number": "• Nombor rumah/bangunan",
    "• Street name": "• Nama jalan",
    "• Area/Taman": "• Kawasan/Taman",
    "• Postcode and City": "• Poskod dan Bandar",
    "• State": "• Negeri",
    "We found this address:": "Kami jumpa alamat ini:",
    "Is this your correct pickup address?": "Adakah ini alamat ambil anda yang betul?",
    "7. *Destination address*": "7. *Alamat destinasi*",
    "Please type the full destination address:": "Sila taip alamat destinasi penuh:",
    "8. *Reason for transfer*": "8. *Sebab pemindahan*",
    "Please explain why you need this home-to-home transfer:": "Sila terangkan mengapa anda perlukan pemindahan rumah ke rumah ini:",
    "Examples:": "Contoh:",
    "• Moving to family home for care": "• Berpindah ke rumah keluarga untuk penjagaan",
    "• Returning from temporary stay": "• Kembali dari tinggal sementara",
    "• Home modification needed": "• Pengubahsuaian rumah diperlukan",
    "• Closer to medical facilities": "• Lebih dekat dengan kemudahan perubatan",
    "• Change of residence": "• Pertukaran tempat tinggal",
    "9. *Medical condition*": "9. *Keadaan perubatan*",
    "Please describe the patient's current medical condition:": "Sila huraikan keadaan perubatan semasa pesakit:",
    "• Post-stroke recovery": "• Pemulihan selepas strok",
    "• Mobility limited": "• Mobiliti terhad",
    "• Requires oxygen therapy": "• Perlukan terapi oksigen",
    "• Stable condition for transfer": "• Keadaan stabil untuk dipindahkan",
    "• Recent surgery": "• Pembedahan terkini",
    "Would you like to provide an emergency contact at the destination?": "Adakah anda ingin beri kenalan kecemasan di destinasi?",
    "This is optional but recommended for better coordination at the destination location.": "Ini pilihan tetapi disyorkan untuk penyelarasan lebih baik di lokasi destinasi.",
    "Please provide the emergency contact name at the destination:": "Sila beri nama kenalan kecemasan di destinasi:",
    "Example: Rahman bin Ali or Aishah binti Hassan": "Contoh: Rahman bin Ali atau Aishah binti Hassan",
    "Please provide the emergency contact phone at the destination:": "Sila beri telefon kenalan kecemasan di destinasi:",
    "Example: 012-3456789 or 019-8765432": "Contoh: 012-3456789 atau 019-8765432",
    "You can upload attachments (photos/documents) related to this transfer.": "Anda boleh muat naik lampiran (gambar/dokumen) berkaitan pemindahan ini.",
    "• Medical reports": "• Laporan perubatan",
    "• Doctor's clearance for transfer": "• Kebenaran doktor untuk pemindahan",
    "• Insurance documents": "• Dokumen insurans",
    "• Prescriptions": "• Preskripsi",
    "You can upload multiple attachments. When done, click 'Next'.": "Anda boleh muat naik berbilang lampiran. Apabila selesai, klik 'Seterusnya'.",
    "Error asking for attachments. Please try again.": "Ralat meminta lampiran. Sila cuba lagi.",
    "Do you have any additional remarks or special instructions?": "Adakah anda ada sebarang catatan tambahan atau arahan khas?",
    "• Specific route preferences": "• Keutamaan laluan tertentu",
    "• Special medical equipment needed": "• Peralatan perubatan khas diperlukan",
    "• Time constraints": "• Kekangan masa",
    "• Additional patient information": "• Maklumat pesakit tambahan",
    "You can add remarks or skip to continue.": "Anda boleh tambah catatan atau langkau untuk teruskan.",
    "Please type your remarks or special instructions:": "Sila taip catatan atau arahan khas anda:",
    "• Patient needs wheelchair assistance": "• Pesakit perlukan bantuan kerusi roda",
    "• Please use back entrance": "• Sila gunakan pintu belakang",
    "• Patient is fasting": "• Pesakit sedang berpuasa",
    "• Special handling requirements": "• Keperluan pengendalian khas",
    "Please select the {} date:": "Sila pilih tarikh {}:",
    "*Today:*": "*Hari Ini:*",
    "*Tomorrow:*": "*Esok:*",
    "If you need another date, select 'Others' and enter DD/MM/YYYY format.": "Jika anda perlukan tarikh lain, pilih 'Lain-lain' dan masukkan format DD/MM/YYYY.",
    "Error scheduling date. Please try again.": "Ralat menjadualkan tarikh. Sila cuba lagi.",
    "Please select AM or PM for the transfer time:": "Sila pilih AM atau PM untuk masa pemindahan:",
    "Please select a 2-hour time slot for transfer:": "Sila pilih slot masa 2 jam untuk pemindahan:",
    "Selected Date:": "Tarikh Dipilih:",
    "Period:": "Tempoh:",
    "After selecting a slot, you'll choose the exact 15-minute interval.": "Selepas memilih slot, anda akan pilih selang 15 minit tepat.",
    "Error selecting time. Please try again.": "Ralat memilih masa. Sila cuba lagi.",
    "🏥 *AMBULANCE SERVICE: HOSPITAL TO HOSPITAL TRANSFER*": "🏥 *PERKHIDMATAN AMBULANS: PEMINDAHAN HOSPITAL KE HOSPITAL*",
    "This service helps transfer patients between hospitals for specialized care.": "Perkhidmatan ini membantu memindahkan pesakit antara hospital untuk penjagaan khusus.",
    "We'll collect information for your inter-hospital transfer.": "Kami akan kumpulkan maklumat untuk pemindahan antara hospital anda.",
    "• Ensure both hospitals are aware of the transfer": "• Pastikan kedua-dua hospital sedar tentang pemindahan",
    "• Provide accurate hospital names": "• Beri nama hospital yang tepat",
    "• We'll automatically find hospital addresses": "• Kami akan cari alamat hospital secara automatik",
    "• Have medical files ready for transfer": "• Sediakan fail perubatan untuk pemindahan",
    "4. Emergency contact name": "4. Nama kenalan kecemasan",
    "5. Emergency contact phone": "5. Telefon kenalan kecemasan",
    "6. Current hospital name (we'll find the address)": "6. Nama hospital semasa (kami akan cari alamat)",
    "7. Ward number and level (e.g., Ward 5A, Level 3)": "7. Nombor wad dan aras (cth., Wad 5A, Aras 3)",
    "8. Destination hospital name (we'll find the address)": "8. Nama hospital destinasi (kami akan cari alamat)",
    "*After these questions, you can upload attachments, add remarks, and schedule the transfer.*": "*Selepas soalan-soalan ini, anda boleh muat naik lampiran, tambah catatan, dan jadualkan pemindahan.*",
    "Please type the name of the current hospital:": "Sila taip nama hospital semasa:",
    "We'll automatically find the address for you.": "Kami akan cari alamat untuk anda secara automatik.",
    "We found this address for *{}*:": "Kami jumpa alamat ini untuk *{}*:",
    "Is this the correct hospital address?": "Adakah ini alamat hospital yang betul?",
    "Please type the current hospital address manually:": "Sila taip alamat hospital semasa secara manual:",
    "Include full address with postcode and state.": "Termasuk alamat penuh dengan poskod dan negeri.",
    "7. *Ward number and level*": "7. *Nombor wad dan aras*",
    "Please provide the ward number and level:": "Sila beri nombor wad dan aras:",
    "• Ward 5A, Level 3": "• Wad 5A, Aras 3",
    "• ICU, Level 5": "• ICU, Aras 5",
    "• Ward 3B, Ground Floor": "• Wad 3B, Aras Bawah",
    "• Private Suite, Level 2": "• Suite Persendirian, Aras 2",
    "Enter both ward and level together.": "Masukkan kedua-dua wad dan aras bersama.",
    "8. *Destination hospital name*": "8. *Nama hospital destinasi*",
    "Please type the name of the destination hospital:": "Sila taip nama hospital destinasi:",
    "Please type the destination hospital address manually:": "Sila taip alamat hospital destinasi secara manual:",
    "• Doctor's referral letters": "• Surat rujukan doktor",
    "• Transfer forms": "• Borang pemindahan",
    "• Patient requires ventilator during transfer": "• Pesakit perlukan ventilator semasa pemindahan",
    "• Specific route preferred": "• Laluan tertentu lebih disukai",
    "• Need ambulance with ICU facilities": "• Perlukan ambulans dengan kemudahan ICU",
    "• Coordination with specific hospital staff": "• Penyelarasan dengan kakitangan hospital tertentu",
    "Please select the transfer date:": "Sila pilih tarikh pemindahan:",
    "Quantity: {}": "Kuantiti: {}",
    "Dosage: {}": "Dos: {}",
    "Method: {}": "Kaedah: {}",
    "Take: {}": "Ambil: {}",
    "Purpose: {}": "Tujuan: {}",
    "Note: {}": "Nota: {}",
    "No details available": "Tiada butiran tersedia",
    "Duration: {} day{}": "Tempoh: {} hari",
    "Frequency: {} time{}": "Kekerapan: {} kali",
    "Patient information not found. Please select a patient first.": "Maklumat pesakit tidak ditemui. Sila pilih pesakit dahulu.",
    "No visits found for {}.": "Tiada lawatan ditemui untuk {}.",
    "No {} services available for this clinic. Please select another clinic or contact support.": "Tiada perkhidmatan {} tersedia untuk klinik ini. Sila pilih klinik lain atau hubungi sokongan.",
    "GP Visit Services": "Perkhidmatan Lawatan GP",
    "Checkup Services": "Perkhidmatan Pemeriksaan",
    "Vaccination Services": "Perkhidmatan Vaksinasi",
    "Health Screening": "Saringan Kesihatan",
    "Please select a {} service:": "Sila pilih perkhidmatan {}:",
    "GP, Checkup, Vaccination, Health Screening": "GP, Pemeriksaan, Vaksinasi, Saringan Kesihatan",
    "Chiro, Physio, Rehab, Traditional Medicine": "Kiropraktik, Fisioterapi, Pemulihan, Perubatan Tradisional",
    "Non-emergency medical transport": "Pengangkutan perubatan bukan kecemasan",
    "Coming soon": "Akan Datang",
    "Service Booking": "Tempahan Perkhidmatan",
    "Location received. However, location sharing is not expected in this context. Please use the menu buttons provided for selection.": "Lokasi diterima. Namun, perkongsian lokasi tidak dijangka dalam konteks ini. Sila gunakan butang menu yang disediakan untuk pemilihan.",
    "Error processing location. Please try again.": "Ralat memproses lokasi. Sila cuba lagi.",
    "File received. However, file upload is not expected in this context. Please use the menu buttons provided for selection.": "Fail diterima. Namun, muat naik fail tidak dijangka dalam konteks ini. Sila gunakan butang menu yang disediakan untuk pemilihan.",
    "Error processing file. Please try again.": "Ralat memproses fail. Sila cuba lagi.",
    "No patient profiles found. Please contact clinic to create a profile.": "Tiada profil pesakit ditemui. Sila hubungi klinik untuk buat profil.",
    "What would you like to view?": "Apa yang anda ingin lihat?",
    "Available Options": "Pilihan Tersedia",
    "View diagnosed conditions": "Lihat keadaan yang didiagnosis",
    "View all medications and items": "Lihat semua ubat dan item",
    "Select visit for MC, Invoice, etc.": "Pilih lawatan untuk MC, Invois, dsb.",
    "No disease diagnoses found for this patient.": "Tiada diagnosis penyakit ditemui untuk pesakit ini.",
    "⚔️ **ENEMY (DISEASE) for {}**": "⚔️ **MUSUH (PENYAKIT) untuk {}**",
    "📞 Contact your clinic for more information.": "📞 Hubungi klinik anda untuk maklumat lanjut.",
    "Error loading disease information. Please try again.": "Ralat memuat maklumat penyakit. Sila cuba lagi.",
    "Medication & Routine module is currently unavailable. Please try again later.": "Modul Ubat & Rutin tidak tersedia buat masa ini. Sila cuba lagi nanti.",
    "Error loading medication details. Please try again.": "Ralat memuat butiran ubat. Sila cuba lagi.",
    "Error loading visiting history. Please try again.": "Ralat memuat sejarah lawatan. Sila cuba lagi.",
    
    # Additional translations from second list
    "📍 Pickup Address": "📍 Alamat Ambil",
    "📍 Home Address": "📍 Alamat Rumah",
    "📍 Home Address Found": "📍 Alamat Rumah Ditemui",
    "📅 Select Pickup Date": "📅 Pilih Tarikh Ambil",
    "📅 Select Discharge Date": "📅 Pilih Tarikh Keluar",
    "⏱️ Select 15-Minute Interval": "⏱️ Pilih Selang 15 Minit",
    "🏥 Hospital Address Found": "🏥 Alamat Hospital Ditemui",
    "Symptom Tracker": "Penjejak Gejala",
    "Your Follow-up Entries": "Entri Susulan Anda",
    "🔄 Return Service": "🔄 Perkhidmatan Pulangan",
    "Track your recovery progress": "Jejak kemajuan pemulihan anda",
    "Select Entry": "Pilih Entri",
    "Edit": "Edit",
    "Select Time": "Pilih Masa",
    "Error loading patient profiles. Please try again.": "Ralat memuat profil pesakit. Sila cuba lagi.",
    "Error loading options. Please try again.": "Ralat memuat pilihan. Sila cuba lagi.",
    "Hi {},\n\nHow are you feeling after your recent visit?": "Hai {},\n\nBagaimana perasaan anda selepas lawatan terkini?",
    "Hi {},\n\nIt's been a day since your visit. How are you feeling?": "Hai {},\n\nSudah sehari sejak lawatan anda. Bagaimana perasaan anda?",
    "Hi {},\n\nChecking in again 1 week later. How is your condition now?": "Hai {},\n\nSemak semula seminggu kemudian. Bagaimana keadaan anda sekarang?",
    "Glad to hear you are better! Take care.": "Gembira dengar anda lebih baik! Jaga diri.",
    "Noted. We will check on you again in 1 week. If urgent, please visit the clinic.": "Diterima. Kami akan periksa anda semula dalam 1 minggu. Jika kecemasan, sila lawati klinik.",
    "Thanks, glad to hear you are better!": "Terima kasih, gembira dengar anda lebih baik!",
    "Ok, please contact the clinic if you need assistance.": "Ok, sila hubungi klinik jika perlukan bantuan.",
    "The clinic will contact you. If urgent, please call the clinic.": "Klinik akan hubungi anda. Jika kecemasan, sila hubungi klinik.",
    "Thank you for your response.": "Terima kasih atas respons anda.",
    "You don't have any follow-up entries to track symptoms for.": "Anda tiada entri susulan untuk jejak gejala.",
    "Select the follow-up entry you want to update symptoms for:": "Pilih entri susulan yang anda ingin kemaskini gejala untuk:",
    "Thank you for updating your symptoms. Your doctor will see this information.": "Terima kasih mengemaskini gejala anda. Doktor anda akan lihat maklumat ini.",
    "Time slot not available": "Slot masa tidak tersedia",
    "📅 *AMBULANCE SERVICE: HOME TO HOSPITAL*": "📅 *PERKHIDMATAN AMBULANS: RUMAH KE HOSPITAL*",
    "Booking ID:": "ID Tempahan:",
    "We'll collect information for your ambulance booking.": "Kami akan kumpulkan maklumat untuk tempahan ambulans anda.",
    "*After these questions, we'll ask for attachments and schedule pickup.*": "*Selepas soalan-soalan ini, kami akan tanya lampiran dan jadual ambil.*",
    "6. *Pickup address (Home address)*": "6. *Alamat ambil (Alamat rumah)*",
    "How would you like to provide your pickup address?": "Bagaimana anda ingin beri alamat ambil anda?",
    "Please type your full pickup address:": "Sila taip alamat ambil penuh anda:",
    "You can upload attachments (photos/documents) related to this booking.": "Anda boleh muat naik lampiran (gambar/dokumen) berkaitan tempahan ini.",
    "Do you need return service (from hospital back to home)?": "Adakah anda perlukan perkhidmatan pulangan (dari hospital kembali ke rumah)?",
    "✅ *Return service added*": "✅ *Perkhidmatan pulangan ditambah*",
    "Please select AM or PM for the pickup time Close to the clinic.": "Sila pilih AM atau PM untuk masa ambil Berhampiran klinik.",
    "Please select a 2-hour time slot for pickup:": "Sila pilih slot masa 2 jam untuk ambil:",
    "Please select the exact pickup time:": "Sila pilih masa ambil tepat:",
    "Please provide a valid answer.": "Sila beri jawapan yang sah.",
    "❌ *Invalid IC number format*": "❌ *Format nombor IC tidak sah*",
    "Please re-enter the patient's IC number:": "Sila masukkan semula nombor IC pesakit:",
    "❌ Unsupported file type.": "❌ Jenis fail tidak disokong.",
    "Error: Could not get file information. Please try again.": "Ralat: Tidak dapat dapatkan maklumat fail. Sila cuba lagi.",
    "❌ Failed to download file from WhatsApp.": "❌ Gagal memuat turun fail dari WhatsApp.",
    "✅ *Attachment successfully saved!*": "✅ *Lampiran berjaya disimpan!*",
    "❌ Failed to save attachment.": "❌ Gagal menyimpan lampiran.",
    "Please enter the pickup date in DD/MM/YYYY format:": "Sila masukkan tarikh ambil dalam format DD/MM/YYYY:",
    "Date cannot be in the past.": "Tarikh tidak boleh pada masa lalu.",
    "✅ *AMBULANCE BOOKING CONFIRMED*": "✅ *TEMPAHAN AMBULANS DISAHKAN*",
    "Thank you for using AnyHealth Ambulance Service! 🚑": "Terima kasih menggunakan Perkhidmatan Ambulans AnyHealth! 🚑",
    "🏥 *AMBULANCE SERVICE: HOSPITAL TO HOME*": "🏥 *PERKHIDMATAN AMBULANS: HOSPITAL KE RUMAH*",
    "Request ID:": "ID Permintaan:",
    "This service helps transport patients from hospital to home after discharge.": "Perkhidmatan ini membantu mengangkut pesakit dari hospital ke rumah selepas keluar.",
    "7. Ward number and level number": "7. Nombor wad dan nombor aras",
    "8. Home location (with location sharing option)": "8. Lokasi rumah (dengan pilihan perkongsian lokasi)",
    "*After these questions, we'll ask for attachments, remarks, and schedule discharge.*": "*Selepas soalan-soalan ini, kami akan tanya lampiran, catatan, dan jadual keluar.*",
    "7. *Ward number and level number*": "7. *Nombor wad dan nombor aras*",
    "Please provide the ward and bed number:": "Sila beri nombor wad dan katil:",
    "8. *Home address*": "8. *Alamat rumah*",
    "How would you like to provide your home address?": "Bagaimana anda ingin beri alamat rumah anda?",
    "Please type your full home address:": "Sila taip alamat rumah penuh anda:",
    "Is this your correct home address?": "Adakah ini alamat rumah anda yang betul?",
    "You can upload attachments (photos/documents) related to this discharge.": "Anda boleh muat naik lampiran (gambar/dokumen) berkaitan keluar ini.",
    "Discharge summary": "Ringkasan keluar",
    "Please select AM or PM for the discharge time:": "Sila pilih AM atau PM untuk masa keluar:",
    "Please select a 2-hour time slot for discharge:": "Sila pilih slot masa 2 jam untuk keluar:",
    "Please select the exact discharge time:": "Sila pilih masa keluar tepat:",
    "Discharge request cancelled. Returning to main menu.": "Permintaan keluar dibatalkan. Kembali ke menu utama.",
    "Please share your home location using the button below:": "Sila kongsi lokasi rumah anda menggunakan butang di bawah:",
    "✅ *Home address confirmed!*": "✅ *Alamat rumah disahkan!*",
    "Please type the corrected home address:": "Sila taip alamat rumah yang dibetulkan:",
    "🔍 Searching for *{}*...": "🔍 Mencari *{}*...",
    "❌ Could not find address for *{}*": "❌ Tidak dapat cari alamat untuk *{}*",
    "Please provide the address manually.": "Sila beri alamat secara manual.",
    "✅ *DISCHARGE TRANSPORT CONFIRMED*": "✅ *PENGANGKUTAN KELUAR DISAHKAN*",
    
    # Menu selection buttons
    "🔙 Back to Type Selection": "🔙 Kembali ke Pemilihan Jenis",
    "🔙 Back to Services": "🔙 Kembali ke Perkhidmatan",
    "Back to Home": "Kembali ke Laman Utama",
    "Select Visit": "Pilih Lawatan",
    
    # Footer/status messages
    "{} confirmed booking(s)": "{} tempahan disahkan",
    "Returning to main menu.": "Kembali ke menu utama.",
    "No documents available for this visit.": "Tiada dokumen tersedia untuk lawatan ini.",
    
    # Medication module headers
    "💊 *ALL MEDICATIONS & ITEMS for {}*": "💊 *SEMUA UBAT & ITEM untuk {}*",
    "No medications or items found for any visit.": "Tiada ubat atau item ditemui untuk sebarang lawatan.",
    "*📊 Summary: {} total items across {} visits*": "*📊 Ringkasan: {} item keseluruhan merentasi {} lawatan*",
    "📞 *Contact your clinic if you have any questions.*": "📞 *Hubungi klinik anda jika ada sebarang soalan.*",
    
    # Ambulance service translations
    "📅 *AMBULANCE SERVICE: HOME TO HOSPITAL*": "📅 *PERKHIDMATAN AMBULANS: RUMAH KE HOSPITAL*",
    "Booking ID: {}": "ID Tempahan: {}",
    "This service helps patients travel from home to hospital for appointments.": "Perkhidmatan ini membantu pesakit bergerak dari rumah ke hospital untuk temujanji.",
    "Please answer the following questions one by one.": "Sila jawab soalan berikut satu persatu.",
    "*Important:*": "*Penting:*",
    "• Please provide accurate information": "• Sila beri maklumat tepat",
    "• For addresses, include full address with postcode": "• Untuk alamat, sertakan alamat penuh dengan poskod",
    "• After answering all questions, you can upload documents/attachments": "• Selepas jawab semua soalan, anda boleh muat naik dokumen/lampiran",
    "7. Hospital name (we'll find the address automatically)": "7. Nama hospital (kami akan cari alamat secara automatik)",
    "Please share your location using the button below:": "Sila kongsi lokasi anda menggunakan butang di bawah:",
    "1. Tap the location icon 📍": "1. Tekan ikon lokasi 📍",
    "2. Select 'Share Location'": "2. Pilih 'Kongsi Lokasi'",
    "3. Choose 'Send your current location'": "3. Pilih 'Hantar lokasi semasa anda'",
    "✅ Pickup address confirmed!": "✅ Alamat ambil disahkan!",
    "Now let's proceed to hospital details.": "Sekarang mari kita teruskan ke butiran hospital.",
    "7. Hospital name": "7. Nama hospital",
    "Please type the name of the hospital:": "Sila taip nama hospital:",
    "Example:": "Contoh:",
    "* Hospital Kuala Lumpur": "* Hospital Kuala Lumpur",
    "* Sunway Medical Centre": "* Sunway Medical Centre",
    "* Pantai Hospital Kuala Lumpur": "* Pantai Hospital Kuala Lumpur",
    "* University Malaya Medical Centre": "* University Malaya Medical Centre",
    "We'll automatically find the address for you.": "Kami akan cari alamat untuk anda secara automatik.",
    
    # Notifications.py
    "Your checkup booking is confirmed on ": "Tempahan pemeriksaan anda disahkan pada ",
    "Your consultation booking is confirmed on ": "Tempahan perundingan anda disahkan pada ",
    "Your vaccination booking for {} is confirmed on ": "Tempahan vaksinasi anda untuk {} disahkan pada ",
    # TCM booking confirmations  
    "Your TCM {} booking is confirmed on ": "Tempahan TCM {} anda disahkan pada ",
    # Repeated visit confirmations
    "Your repeated visit for {} {} bookings are confirmed on ": "Lawatan berulang anda untuk {} {} tempahan disahkan pada ",
    "Your repeated visit for {} TCM {} bookings are confirmed on ": "Lawatan berulang anda untuk {} TCM {} tempahan disahkan pada ",
    # Reminder messages
    "Reminder: Your repeated visit for {} {} bookings is in ": "Peringatan: Lawatan berulang anda untuk {} {} tempahan dalam ",
    "Reminder: Your {} is in ": "Peringatan: {} anda dalam ",
    "Custom reminder: Your repeated visit for {} {} bookings is in ": "Peringatan tersuai: Lawatan berulang anda untuk {} {} tempahan dalam ",
    "Custom reminder: Your {} is in ": "Peringatan tersuai: {} anda dalam ",
    "Reminder: Your repeated visit for {} TCM {} bookings is in ": "Peringatan: Lawatan berulang anda untuk {} TCM {} tempahan dalam ",
    "Reminder: Your TCM {} is in ": "Peringatan: TCM {} anda dalam ",
    "Custom reminder: Your repeated visit for {} TCM {} bookings is in ": "Peringatan tersuai: Lawatan berulang anda untuk {} TCM {} tempahan dalam ",
    "Custom reminder: Your TCM {} is in ": "Peringatan tersuai: TCM {} anda dalam ",
    # Report notifications
    "Report ready for {}: {}": "Laporan sedia untuk {}: {}",
    "Report ready: {}": "Laporan sedia: {}",
    
    # ========== NEW TRANSLATIONS FROM PROVIDED DICTIONARY ==========
    
    # From post_report.py
    "Invalid selection. Please try again.": "Pilihan tidak sah. Sila cuba lagi.",
    "Error processing your selection. Please try again.": "Ralat memproses pilihan anda. Sila cuba lagi.",
    "Past Consultations": "Perundingan Terdahulu",
    "Select a consultation to request report:": "Pilih perundingan untuk minta laporan:",
    "Request Report": "Minta Laporan",
    "🔙 Back": "🔙 Kembali",
    "IC verified. Report for consultation on {} (Diagnosis: {}):\n{}\n\n{}": "IC disahkan. Laporan untuk perundingan pada {} (Diagnosis: {}):\n{}\n\n{}",
    "IC verified, but error sending report. Please try again.": "IC disahkan, tetapi ralat menghantar laporan. Sila cuba lagi.",
    "IC verified, but the report is not yet available. You will be notified when ready.": "IC disahkan, tetapi laporan belum tersedia. Anda akan dimaklumkan apabila sedia.",
    "IC verified successfully, but no report request pending. Please select a consultation.": "IC berjaya disahkan, tetapi tiada permintaan laporan menunggu. Sila pilih perundingan.",
    "Invalid verification format. Please use 'verified:<IC>'.": "Format pengesahan tidak sah. Sila gunakan 'verified:<IC>'.",
    "Error processing verification. Please try again.": "Ralat memproses pengesahan. Sila cuba lagi.",

    # From ambulance_emergency.py
    "⚠️ *ERROR STARTING EMERGENCY*\n\nUnable to start emergency service. Please try again or call 999 immediately.": "⚠️ *RALAT MEMULAKAN KECEMASAN*\n\nTidak dapat memulakan perkhidmatan kecemasan. Sila cuba lagi atau hubungi 999 segera.",
    "⚠️ *ERROR COMPLETING EMERGENCY*\n\nPlease try again or call 999 immediately.": "⚠️ *RALAT MENYELESAIKAN KECEMASAN*\n\nSila cuba lagi atau hubungi 999 segera.",
    "⚠️ *ERROR SAVING HEALTH CONDITION*\n\nPlease try again.": "⚠️ *RALAT MENYIMPAN KEADAAN KESIHATAN*\n\nSila cuba lagi.",
    "⚠️ *AN ERROR OCCURRED*\n\nPlease try again or call 999 immediately for emergency assistance.": "⚠️ *RALAT BERLAKU*\n\nSila cuba lagi atau hubungi 999 segera untuk bantuan kecemasan.",
    "⚠️ *EMERGENCY AMBULANCE*\n\nIs this a life-threatening emergency? (e.g., heart attack, severe bleeding, unconscious)": "⚠️ *AMBULANS KECEMASAN*\n\nAdakah ini kecemasan yang mengancam nyawa? (cth., serangan jantung, pendarahan teruk, tidak sedar)",
    "⚠️ *NON-LIFE-THREATENING*\n\nFor non-critical cases, please use our standard booking service.": "⚠️ *TIDAK MENGANCAM NYAWA*\n\nUntuk kes tidak kritikal, sila gunakan perkhidmatan tempahan standard kami.",
    "⚠️ *LIFE-THREATENING EMERGENCY*\n\nPlease call 999 immediately!\n\nFor clinic transport, continue below.": "⚠️ *KECEMASAN MENGANCAM NYAWA*\n\nSila hubungi 999 segera!\n\nUntuk pengangkutan klinik, teruskan di bawah.",
    "⚠️ *EMERGENCY LOCATION*\n\nPlease share your exact location:": "⚠️ *LOKASI KECEMASAN*\n\nSila kongsi lokasi tepat anda:",
    "⚠️ *ERROR GETTING LOCATION*\n\nPlease try again or enter your address manually.": "⚠️ *RALAT MENDAPATKAN LOKASI*\n\nSila cuba lagi atau masukkan alamat anda secara manual.",
    "⚠️ *LOCATION RECEIVED*\n\nAddress: {}\n\nDistance from clinic: {} km\n\nIs this correct?": "⚠️ *LOKASI DITERIMA*\n\nAlamat: {}\n\nJarak dari klinik: {} km\n\nAdakah ini betul?",
    "⚠️ *INVALID LOCATION*\n\nLocation must be within {}km of clinic.\n\nPlease share accurate location.": "⚠️ *LOKASI TIDAK SAH*\n\nLokasi mesti dalam {}km dari klinik.\n\nSila kongsi lokasi yang tepat.",
    "⚠️ *LOCATION CONFIRMED*\n\nPatient Name:": "⚠️ *LOKASI DISAHKAN*\n\nNama Pesakit:",
    "⚠️ *ERROR SAVING NAME*\n\nPlease try again.": "⚠️ *RALAT MENYIMPAN NAMA*\n\nSila cuba lagi.",
    "⚠️ *PATIENT NAME SAVED*\n\nPatient IC (YYMMDD-XX-XXXX):": "⚠️ *NAMA PESAKIT DISIMPAN*\n\nIC Pesakit (YYMMDD-XX-XXXX):",
    "⚠️ *INVALID IC*\n\nPlease enter valid IC format.": "⚠️ *IC TIDAK SAH*\n\nSila masukkan format IC yang sah.",
    "⚠️ *ERROR SAVING IC*\n\nPlease try again.": "⚠️ *RALAT MENYIMPAN IC*\n\nSila cuba lagi.",
    "⚠️ *IC SAVED*\n\nPatient Phone:": "⚠️ *IC DISIMPAN*\n\nTelefon Pesakit:",
    "⚠️ *ERROR SAVING PHONE*\n\nPlease try again.": "⚠️ *RALAT MENYIMPAN TELEFON*\n\nSila cuba lagi.",
    "⚠️ *PHONE SAVED*\n\nEmergency Contact Name:": "⚠️ *TELEFON DISIMPAN*\n\nNama Kenalan Kecemasan:",
    "⚠️ *ERROR SAVING EMERGENCY NAME*\n\nPlease try again.": "⚠️ *RALAT MENYIMPAN NAMA KECEMASAN*\n\nSila cuba lagi.",
    "⚠️ *EMERGENCY NAME SAVED*\n\nEmergency Contact Phone:": "⚠️ *NAMA KECEMASAN DISIMPAN*\n\nTelefon Kenalan Kecemasan:",
    "⚠️ *ERROR SAVING EMERGENCY PHONE*\n\nPlease try again.": "⚠️ *RALAT MENYIMPAN TELEFON KECEMASAN*\n\nSila cuba lagi.",
    "⚠️ *EMERGENCY PHONE SAVED*\n\nHealth Condition:": "⚠️ *TELEFON KECEMASAN DISIMPAN*\n\nKeadaan Kesihatan:",
    "⚠️ *EMERGENCY REQUEST SUBMITTED*\n\nAlert ID: {}\nPatient: {}\nIC: {}\nPhone: {}\nEmergency: {} ({})\nLocation: {}\nDistance: {} km\nCondition: {}\n\nAmbulance ETA: ~{} min\n\nStay on line for updates.\n\nIf critical, call 999!": "⚠️ *PERMINTAAN KECEMASAN DIHANTAR*\n\nID Amaran: {}\nPesakit: {}\nIC: {}\nTelefon: {}\nKecemasan: {} ({})\nLokasi: {}\nJarak: {} km\nKeadaan: {}\n\nETA Ambulans: ~{} min\n\nKekal dalam talian untuk kemaskini.\n\nJika kritikal, hubungi 999!",
    "⚠️ *ERROR SUBMITTING EMERGENCY*\n\nPlease try again or call 999.": "⚠️ *RALAT MENGHANTAR KECEMASAN*\n\nSila cuba lagi atau hubungi 999.",

    # From clinicfd.py
    "Clinic enquiry cancelled.": "Pertanyaan klinik dibatalkan.",
    "An error occurred. Returning to main menu.": "Berlaku ralat. Kembali ke menu utama.",

    # From individual_med_rout.py
    "Quantity:": "Kuantiti:",
    "Dosage:": "Dos:",
    "Method:": "Kaedah:",
    "Timing:": "Masa:",
    "Duration:": "Tempoh:",
    "Notes:": "Nota:",
    "No medications found for this consultation.": "Tiada ubat ditemui untuk perundingan ini.",
    "Medication:": "Ubat:",
    "No medication details available.": "Tiada butiran ubat tersedia.",
    "No routines found for this consultation.": "Tiada rutin ditemui untuk perundingan ini.",
    "Routines:": "Rutin:",
    "No routine details available.": "Tiada butiran rutin tersedia.",

    # From individualedit.py
    "⚠️ *DETACH FROM OLD NUMBER*\n\nThis will:\n1. Remove a profile from old WhatsApp\n2. Free it for attachment to new number\n3. Requires verification of profile details\n\nAfter detachment, contact clinic/email to attach to new number.": "⚠️ *PISAHKAN DARI NOMBOR LAMA*\n\nIni akan:\n1. Keluarkan profil dari WhatsApp lama\n2. Bebaskan untuk dilampirkan ke nombor baru\n3. Memerlukan pengesahan butiran profil\n\nSelepas pemisahan, hubungi klinik/email untuk lampirkan ke nombor baru.",
    "Please enter the 12-digit IC of the profile to detach:": "Sila masukkan IC 12-digit profil yang hendak dipisahkan:",
    "An error occurred in edit module. Please try again.": "Berlaku ralat dalam modul edit. Sila cuba lagi.",

    # From report_symptoms.py
    "Please describe your symptoms:": "Sila huraikan gejala anda:",
    "Please enter your additional remarks:": "Sila masukkan catatan tambahan anda:",

    # From ReportBooking.py
    "No report available yet. Please check back later.": "Tiada laporan tersedia lagi. Sila periksa semula nanti.",
    "Error sending report. Please try again.": "Ralat menghantar laporan. Sila cuba lagi.",
    "Report sent successfully.": "Laporan berjaya dihantar.",
    "Consultation": "Perundingan",
    "Back to Main Menu": "Kembali ke Menu Utama",
    "PDF Request": "Permintaan PDF",
    "Consultation after PDF?": "Perundingan selepas PDF?",
    "Error fetching doctor's clinic:": "Ralat mengambil klinik doktor:",
    "Report Review: {}": "Semakan Laporan: {}",

    # From calendar_utils.py
    "Please select a doctor:": "Sila pilih doktor:",
    "Available Doctors": "Doktor Tersedia",
    "Any Doctor": "Mana-mana Doktor",
    "Error loading doctors. Please try again.": "Ralat memuat doktor. Sila cuba lagi.",
    "No doctors available. Please try again later.": "Tiada doktor tersedia. Sila cuba lagi nanti.",
    "Selected Doctor: {}": "Doktor Dipilih: {}",
    "Please select a date:": "Sila pilih tarikh:",
    "Available Dates": "Tarikh Tersedia",
    "Enter Future Date": "Masukkan Tarikh Masa Depan",
    "No available dates in the next 7 days.": "Tiada tarikh tersedia dalam 7 hari akan datang.",
    "Error loading calendar. Please try again.": "Ralat memuat kalendar. Sila cuba lagi.",
    "Selected Date: {}": "Tarikh Dipilih: {}",
    "Please select a period:": "Sila pilih tempoh:",
    "Time Periods": "Tempoh Masa",
    "Morning": "Pagi",
    "Afternoon": "Petang",
    "Evening": "Malam",
    "No available periods on {}.": "Tiada tempoh tersedia pada {}.",
    "Error loading periods. Please try again.": "Ralat memuat tempoh. Sila cuba lagi.",
    "Selected Period: {}": "Tempoh Dipilih: {}",
    "Please select an hour:": "Sila pilih jam:",
    "Available Hours": "Jam Tersedia",
    "No available hours in {} on {}.": "Tiada jam tersedia dalam {} pada {}.",
    "Error loading hours. Please try again.": "Ralat memuat jam. Sila cuba lagi.",
    "Selected Hour: {}": "Jam Dipilih: {}",
    "Please select a time slot:": "Sila pilih slot masa:",
    "Available Slots": "Slot Tersedia",
    "No available slots at {} on {}.": "Tiada slot tersedia pada {} pada {}.",
    "Error loading slots. Please try again.": "Ralat memuat slot. Sila cuba lagi.",
    "✅ BOOKING CONFIRMED!\n\n{} with Dr. {}\nDate: {}\nTime: {} ({}min)\n\nStatus: PENDING APPROVAL\n\nYou'll be notified when confirmed.": "✅ TEMPAHAN DISAHKAN!\n\n{} dengan Dr. {}\nTarikh: {}\nMasa: {} ({}min)\n\nStatus: MENUNGGU KELULUSAN\n\nAnda akan dimaklumkan apabila disahkan.",
    "Error confirming booking. Please try again.": "Ralat mengesahkan tempahan. Sila cuba lagi.",
    "Booking has been cancelled.": "Tempahan telah dibatalkan.",
    "Invalid date format. Please use DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY.": "Format tarikh tidak sah. Sila gunakan DD/MM/YYYY, DD-MM-YYYY atau DD MM YYYY.",
    "Date must be in the future. Please enter a valid future date.": "Tarikh mesti pada masa depan. Sila masukkan tarikh masa depan yang sah.",
    "No availability on {}. Please choose another date.": "Tiada ketersediaan pada {}. Sila pilih tarikh lain.",
    "Confirm date {}?": "Sahkan tarikh {}?",
    "Yes": "Ya",
    "No, Change Date": "Tidak, Tukar Tarikh",
    "Date confirmed: {}": "Tarikh disahkan: {}",
    "Invalid time format. Please enter time like 9:30, 2pm, or 1430.": "Format masa tidak sah. Sila masukkan masa seperti 9:30, 2pm, atau 1430.",
    "No availability at requested time. Closest available: {}. Proceed?": "Tiada ketersediaan pada masa yang diminta. Terdekat tersedia: {}. Teruskan?",
    "Try Another Time": "Cuba Masa Lain",
    "Get Help Choosing": "Dapatkan Bantuan Memilih",
    "Time confirmed: {}": "Masa disahkan: {}",
    "What would you like to edit?": "Apa yang anda ingin edit?",
    "Edit Options": "Pilihan Edit",
    "Change Doctor": "Tukar Doktor",
    "Change Date": "Tukar Tarikh",
    "Change Time": "Tukar Masa",
    "Change Remarks": "Tukar Catatan",
    "Cancel Booking": "Batal Tempahan",
    "Error processing edit. Please try again.": "Ralat memproses edit. Sila cuba lagi.",
    "Remarks updated successfully.": "Catatan berjaya dikemaskini.",
    "Please enter your remarks:": "Sila masukkan catatan anda:",
    "Invalid input. Please use the buttons provided.": "Input tidak sah. Sila gunakan butang yang disediakan.",

    # From ambulance_booking.py and related ambulance modules
    "⚠️ *AMBULANCE BOOKING*\n\nThis is for non-emergency transport.\nFor emergencies, call 999.": "⚠️ *TEMPAHAN AMBULANS*\n\nIni untuk pengangkutan bukan kecemasan.\nUntuk kecemasan, hubungi 999.",
    "⚠️ *AMBULANCE TYPE*\n\nChoose service:": "⚠️ *JENIS AMBULANS*\n\nPilih perkhidmatan:",
    "Home to Hospital": "Rumah ke Hospital",
    "Hospital to Home": "Hospital ke Rumah",
    "Hospital Discharge": "Keluar Hospital",
    "Hospital to Hospital": "Hospital ke Hospital",
    "Home to Home": "Rumah ke Rumah",
    "⚠️ *BOOKING STARTED*\n\nPlease answer step by step.\nType 'cancel' anytime to stop.": "⚠️ *TEMPAHAN DIMULAKAN*\n\nSila jawab langkah demi langkah.\nTaip 'cancel' bila-bila masa untuk berhenti.",
    "⚠️ *AMBULANCE BOOKING CANCELLED*\n\nReturned to main menu.": "⚠️ *TEMPAHAN AMBULANS DIBATALKAN*\n\nKembali ke menu utama.",
    "⚠️ *INVALID INPUT*\n\nPlease answer the question.": "⚠️ *INPUT TIDAK SAH*\n\nSila jawab soalan.",
    "⚠️ *ERROR PROCESSING*\n\nPlease try again.": "⚠️ *RALAT MEMPROSES*\n\nSila cuba lagi.",
    "⚠️ *PICKUP LOCATION*\n\nPlease share your pickup location:": "⚠️ *LOKASI AMBIL*\n\nSila kongsi lokasi ambil anda:",
    "⚠️ *LOCATION RECEIVED*\n\nAddress: {}\n\nIs this correct?": "⚠️ *LOKASI DITERIMA*\n\nAlamat: {}\n\nAdakah ini betul?",
    "⚠️ *LOCATION CONFIRMED*\n\nPlease select a hospital:": "⚠️ *LOKASI DISAHKAN*\n\nSila pilih hospital:",
    "Hospitals": "Hospital",
    "No hospitals found. Please try again.": "Tiada hospital ditemui. Sila cuba lagi.",
    "⚠️ *HOSPITAL SELECTED*\n\n{} ({} km)\n\nReturn service needed?": "⚠️ *HOSPITAL DIPILIH*\n\n{} ({} km)\n\nPerkhidmatan pulangan diperlukan?",
    "⚠️ *RETURN SERVICE*\n\nPlease select return date:": "⚠️ *PERKHIDMATAN PULANGAN*\n\nSila pilih tarikh pulangan:",
    "Return Dates": "Tarikh Pulangan",
    "⚠️ *RETURN DATE SELECTED*\n\n{}": "⚠️ *TARIKH PULANGAN DIPILIH*\n\n{}",
    "⚠️ *RETURN TIME*\n\nSelect return time period:": "⚠️ *MASA PULANGAN*\n\nPilih tempoh masa pulangan:",
    "⚠️ *RETURN TIME SELECTED*\n\n{}": "⚠️ *MASA PULANGAN DIPILIH*\n\n{}",
    "⚠️ *NO RETURN*\n\nProceed to health condition.": "⚠️ *TIADA PULANGAN*\n\nTeruskan ke keadaan kesihatan.",
    "⚠️ *HEALTH CONDITION*\n\nDescribe patient's condition:": "⚠️ *KEADAAN KESIHATAN*\n\nHuraikan keadaan pesakit:",
    "⚠️ *HEALTH CONDITION SAVED*\n\nAdd attachments? (e.g., reports)": "⚠️ *KEADAAN KESIHATAN DISIMPAN*\n\nTambah lampiran? (cth., laporan)",
    "Add Attachments": "Tambah Lampiran",
    "No Attachments": "Tiada Lampiran",
    "⚠️ *ATTACHMENTS*\n\nSend up to 3 files (images/PDFs).\nType 'done' when finished.": "⚠️ *LAMPIRAN*\n\nHantar sehingga 3 fail (gambar/PDF).\nTaip 'done' apabila selesai.",
    "⚠️ *FILE RECEIVED*\n\n{} saved.\n\nSend more or type 'done'.": "⚠️ *FAIL DITERIMA*\n\n{} disimpan.\n\nHantar lagi atau taip 'done'.",
    "⚠️ *ERROR SAVING FILE*\n\nPlease try again.": "⚠️ *RALAT MENYIMPAN FAIL*\n\nSila cuba lagi.",
    "⚠️ *NO ATTACHMENTS*\n\nProceed to remarks.": "⚠️ *TIADA LAMPIRAN*\n\nTeruskan ke catatan.",
    "⚠️ *REMARKS*\n\nAny additional remarks?": "⚠️ *CATATAN*\n\nAda catatan tambahan?",
    "⚠️ *REMARKS SAVED*\n\nPlease select booking date:": "⚠️ *CATATAN DISIMPAN*\n\nSila pilih tarikh tempahan:",
    "Booking Dates": "Tarikh Tempahan",
    "⚠️ *DATE SELECTED*\n\n{}": "⚠️ *TARIKH DIPILIH*\n\n{}",
    "⚠️ *TIME PERIOD*\n\nSelect time period:": "⚠️ *TEMPOH MASA*\n\nPilih tempoh masa:",
    "⚠️ *TIME SELECTED*\n\n{}": "⚠️ *MASA DIPILIH*\n\n{}",
    "✅ *AMBULANCE BOOKING CONFIRMED*\n\nBooking ID: {}\nPatient: {}\nIC: {}\nPhone: {}\nEmergency: {} ({})\nFrom: {}\nTo: {}\nDate: {}\nTime: {}\n*Estimated Distance:* {} km\n*Attachments:* {}\n*Remarks:* {}\n*Return Service:* {}\n\nOur team will contact you to confirm details.\n\n*Next Steps:*\n1. Team will verify details\n2. You'll receive confirmation call\n3. Ambulance will arrive 30 minutes before pickup\n\nThank you for using AnyHealth Ambulance Service! 🚑": "✅ *TEMPAHAN AMBULANS DISAHKAN*\n\nID Tempahan: {}\nPesakit: {}\nIC: {}\nTelefon: {}\nKecemasan: {} ({})\nDari: {}\nKe: {}\nTarikh: {}\nMasa: {}\n*Anggaran Jarak:* {} km\n*Lampiran:* {}\n*Catatan:* {}\n*Perkhidmatan Pulangan:* {}\n\nPasukan kami akan hubungi anda untuk sahkan butiran.\n\n*Langkah Seterusnya:*\n1. Pasukan akan sahkan butiran\n2. Anda akan terima panggilan pengesahan\n3. Ambulans akan tiba 30 minit sebelum ambil\n\nTerima kasih menggunakan Perkhidmatan Ambulans AnyHealth! 🚑",
    "Error submitting booking. Please try again.": "Ralat menghantar tempahan. Sila cuba lagi.",
    
    "⚠️ *HOME TRANSFER STARTED*\n\nPlease answer step by step.\nType 'cancel' anytime to stop.": "⚠️ *PEMINDAHAN RUMAH DIMULAKAN*\n\nSila jawab langkah demi langkah.\nTaip 'cancel' bila-bila masa untuk berhenti.",
    "⚠️ *DROP-OFF RECEIVED*\n\nAddress: {}\nDistance: {} km\n\nCorrect?": "⚠️ *HANTARAN DITERIMA*\n\nAlamat: {}\nJarak: {} km\n\nBetul?",
    "⚠️ *DROP-OFF CONFIRMED*\n\nPlease select date:": "⚠️ *HANTARAN DISAHKAN*\n\nSila pilih tarikh:",
    "Dates": "Tarikh",
    "⚠️ *HEALTH CONDITION SAVED*\n\nReview summary:": "⚠️ *KEADAAN KESIHATAN DISIMPAN*\n\nSemak ringkasan:",
    "✅ *HOME TRANSFER CONFIRMED*\n\nTransfer ID: {}\nPatient: {}\nIC: {}\nPhone: {}\nEmergency: {} ({})\nFrom: {}\nTo: {}\nDate: {}\nTime: {}\n*Estimated Distance:* {} km\n*Attachments:* {}\n*Remarks:* {}\n\nOur team will contact you to arrange details.\n\n*Next Steps:*\n1. Team will verify details\n2. You'll receive confirmation call\n3. Ambulance will arrive 30 minutes before pickup\n\nThank you for using AnyHealth Ambulance Service! 🚑": "✅ *PEMINDAHAN RUMAH DISAHKAN*\n\nID Pemindahan: {}\nPesakit: {}\nIC: {}\nTelefon: {}\nKecemasan: {} ({})\nDari: {}\nKe: {}\nTarikh: {}\nMasa: {}\n*Anggaran Jarak:* {} km\n*Lampiran:* {}\n*Catatan:* {}\n\nPasukan kami akan hubungi anda untuk atur butiran.\n\n*Langkah Seterusnya:*\n1. Pasukan akan sahkan butiran\n2. Anda akan terima panggilan pengesahan\n3. Ambulans akan tiba 30 minit sebelum ambil\n\nTerima kasih menggunakan Perkhidmatan Ambulans AnyHealth! 🚑",
    "Error submitting transfer request. Please try again.": "Ralat menghantar permintaan pemindahan. Sila cuba lagi.",
    
    "⚠️ *HOSPITAL TRANSFER STARTED*\n\nPlease answer step by step.\nType 'cancel' anytime to stop.": "⚠️ *PEMINDAHAN HOSPITAL DIMULAKAN*\n\nSila jawab langkah demi langkah.\nTaip 'cancel' bila-bila masa untuk berhenti.",
    "⚠️ *FROM HOSPITAL*\n\nPlease select pickup hospital:": "⚠️ *DARI HOSPITAL*\n\nSila pilih hospital ambil:",
    "⚠️ *FROM SELECTED*\n\n{}": "⚠️ *DARI DIPILIH*\n\n{}",
    "⚠️ *WARD/BED*\n\nEnter ward and bed:": "⚠️ *WAD/KATIL*\n\nMasukkan wad dan katil:",
    "⚠️ *WARD SAVED*\n\nTo hospital:": "⚠️ *WAD DISIMPAN*\n\nKe hospital:",
    "⚠️ *TO SELECTED*\n\n{} ({} km)": "⚠️ *KE DIPILIH*\n\n{} ({} km)",
    "✅ *HOSPITAL TRANSFER CONFIRMED*\n\nTransfer ID: {}\nPatient: {}\nIC: {}\nPhone: {}\nEmergency: {} ({})\nFrom: {}\nWard: {}\nTo: {}\nScheduled: {}\n*Estimated Distance:* {} km\n*Attachments:* {}\n*Remarks:* {}\n\nOur team will contact you to arrange details.\n\n*Next Steps:*\n1. Team will verify details\n2. You'll receive confirmation call\n3. Ambulance will arrive 30 minutes before pickup\n\nThank you for using AnyHealth Ambulance Service! 🚑": "✅ *PEMINDAHAN HOSPITAL DISAHKAN*\n\nID Pemindahan: {}\nPesakit: {}\nIC: {}\nTelefon: {}\nKecemasan: {} ({})\nDari: {}\nWad: {}\nKe: {}\nDijadualkan: {}\n*Anggaran Jarak:* {} km\n*Lampiran:* {}\n*Catatan:* {}\n\nPasukan kami akan hubungi anda untuk atur butiran.\n\n*Langkah Seterusnya:*\n1. Pasukan akan sahkan butiran\n2. Anda akan terima panggilan pengesahan\n3. Ambulans akan tiba 30 minit sebelum ambil\n\nTerima kasih menggunakan Perkhidmatan Ambulans AnyHealth! 🚑",
    
    "⚠️ *DISCHARGE STARTED*\n\nPlease answer step by step.\nType 'cancel' anytime to stop.": "⚠️ *KELUAR DIMULAKAN*\n\nSila jawab langkah demi langkah.\nTaip 'cancel' bila-bila masa untuk berhenti.",
    "⚠️ *HOSPITAL*\n\nSelect hospital:": "⚠️ *HOSPITAL*\n\nPilih hospital:",
    "⚠️ *HOSPITAL SELECTED*\n\n{}": "⚠️ *HOSPITAL DIPILIH*\n\n{}",
    "⚠️ *WARD/BED*\n\nEnter ward and bed:": "⚠️ *WAD/KATIL*\n\nMasukkan wad dan katil:",
    "⚠️ *WARD SAVED*\n\nDischarge date:": "⚠️ *WAD DISIMPAN*\n\nTarikh keluar:",
    "⚠️ *DROP-OFF LOCATION*\n\nShare drop-off location:": "⚠️ *LOKASI HANTARAN*\n\nKongsi lokasi hantaran:",
    "⚠️ *ERROR GETTING LOCATION*\n\nPlease try again or enter address manually.": "⚠️ *RALAT MENDAPATKAN LOKASI*\n\nSila cuba lagi atau masukkan alamat secara manual.",
    "⚠️ *LOCATION CONFIRMED*\n\nHealth condition:": "⚠️ *LOKASI DISAHKAN*\n\nKeadaan kesihatan:",
    "✅ *DISCHARGE CONFIRMED*\n\nID: {}\nPatient: {}\nIC: {}\nPhone: {}\nEmergency: {} ({})\nFrom: {}\nWard: {}\nTo: {}\nScheduled: {}\n*Estimated Distance:* {} km\n*Attachments:* {}\n*Remarks:* {}\n\nOur team will contact you to confirm details.\n\n*Next Steps:*\n1. Team will coordinate with hospital\n2. You'll receive confirmation call\n3. Ambulance will arrive 30 minutes before discharge\n\nThank you for using AnyHealth Ambulance Service! 🚑": "✅ *KELUAR DISAHKAN*\n\nID: {}\nPesakit: {}\nIC: {}\nTelefon: {}\nKecemasan: {} ({})\nDari: {}\nWad: {}\nKe: {}\nDijadualkan: {}\n*Anggaran Jarak:* {} km\n*Lampiran:* {}\n*Catatan:* {}\n\nPasukan kami akan hubungi anda untuk sahkan butiran.\n\n*Langkah Seterusnya:*\n1. Pasukan akan selaras dengan hospital\n2. Anda akan terima panggilan pengesahan\n3. Ambulans akan tiba 30 minit sebelum keluar\n\nTerima kasih menggunakan Perkhidmatan Ambulans AnyHealth! 🚑",
    "Error submitting discharge request. Please try again.": "Ralat menghantar permintaan keluar. Sila cuba lagi.",

    # From view_booking.py
    "❌ SYSTEM ERROR\n\nAn error occurred in the booking system. Please try again.": "❌ RALAT SISTEM\n\nBerlaku ralat dalam sistem tempahan. Sila cuba lagi.",
    "No upcoming bookings found.": "Tiada tempahan akan datang ditemui.",
    "Upcoming Bookings (Page {} of {})": "Tempahan Akan Datang (Halaman {} dari {})",
    "Previous Page": "Halaman Sebelum",
    "Next Page": "Halaman Seterusnya",
    "Back to Menu": "Kembali ke Menu",
    "Error fetching bookings: {}": "Ralat mengambil tempahan: {}",
    "No details available.": "Tiada butiran tersedia.",
    "Booking Details:\nType: {}\nDoctor: {}\nDate: {}\nTime: {}\nStatus: {}\n\nWhat would you like to do?": "Butiran Tempahan:\nJenis: {}\nDoktor: {}\nTarikh: {}\nMasa: {}\nStatus: {}\n\nApa yang anda ingin lakukan?",
    "Actions": "Tindakan",
    "Reschedule": "Jadual Semula",
    "Cancel": "Batal",
    "Back": "Kembali",
    "Error cancelling booking: {}": "Ralat membatalkan tempahan: {}",
    "Booking cancelled successfully.": "Tempahan berjaya dibatalkan.",
    "This is a repeated booking series. Cancel all future visits?": "Ini adalah siri tempahan berulang. Batalkan semua lawatan masa depan?",
    "Cancel All": "Batalkan Semua",
    "Cancel This Only": "Batalkan Yang Ini Sahaja",
    "Error cancelling repeated bookings: {}": "Ralat membatalkan tempahan berulang: {}",
    "All future repeated bookings cancelled.": "Semua tempahan berulang masa depan dibatalkan.",
    "This booking cancelled. Future repeats remain.": "Tempahan ini dibatalkan. Ulangan masa depan kekal.",
    "Cancellation cancelled.": "Pembatalan dibatalkan.",
    "This is a repeated booking series. Reschedule all future visits?": "Ini adalah siri tempahan berulang. Jadual semula semua lawatan masa depan?",
    "Reschedule All": "Jadual Semula Semua",
    "Reschedule This Only": "Jadual Semula Yang Ini Sahaja",
    "Error rescheduling repeated bookings: {}": "Ralat menjadual semula tempahan berulang: {}",
    "All future repeated bookings rescheduled.": "Semua tempahan berulang masa depan dijadual semula.",
    "This booking rescheduled. Future repeats unchanged.": "Tempahan ini dijadual semula. Ulangan masa depan tidak berubah.",
    "Reschedule cancelled.": "Jadual semula dibatalkan.",
    "Confirm reschedule to {} at {}?": "Sahkan jadual semula ke {} pada {}?",
    "Error rescheduling: {}": "Ralat menjadual semula: {}",
    "Booking rescheduled successfully.": "Tempahan berjaya dijadual semula.",

    # From reschedule_booking.py
    "No available dates. Please try again later.": "Tiada tarikh tersedia. Sila cuba lagi nanti.",
    "Available Dates": "Tarikh Tersedia",
    "Enter Future Date": "Masukkan Tarikh Masa Depan",
    "Error loading calendar. Please try again.": "Ralat memuat kalendar. Sila cuba lagi.",
    "No available periods on {}.": "Tiada tempoh tersedia pada {}.",
    "Error loading periods. Please try again.": "Ralat memuat tempoh. Sila cuba lagi.",
    "No available hours in {} on {}.": "Tiada jam tersedia dalam {} pada {}.",
    "Error loading hours. Please try again.": "Ralat memuat jam. Sila cuba lagi.",
    "No available slots at {} on {}.": "Tiada slot tersedia pada {} pada {}.",
    "Error loading slots. Please try again.": "Ralat memuat slot. Sila cuba lagi.",

    # From tcm_calendar_utils.py
    # Already included above

    # From healthsp.py
    "Health Screening Plan": "Pelan Saringan Kesihatan",
    "Please select a screening package:": "Sila pilih pakej saringan:",
    "Screening Packages": "Pakej Saringan",
    "Error loading packages. Please try again.": "Ralat memuat pakej. Sila cuba lagi.",
    "No packages available. Please try again later.": "Tiada pakej tersedia. Sila cuba lagi nanti.",
    "Selected Package: {}": "Pakej Dipilih: {}",
    "Do you have any remarks?": "Adakah anda ada catatan?",
    "No Remarks": "Tiada Catatan",
    "Enter Remarks": "Masukkan Catatan",
    "Please enter your remarks:": "Sila masukkan catatan anda:",
    "Remarks saved. Proceed to booking?": "Catatan disimpan. Teruskan ke tempahan?",
    "Proceed": "Teruskan",
    "Change Remarks": "Tukar Catatan",
    "Booking cancelled.": "Tempahan dibatalkan.",

    # From ambulance_homehome.py
    # Already included above

    # From ambulance_hosphosp.py
    # Already included above

    # From ambulance_discharge.py
    # Already included above

    # From vaccination_booking.py
    "Please select a vaccine:": "Sila pilih vaksin:",
    "Vaccines": "Vaksin",
    "Error loading vaccines. Please try again.": "Ralat memuat vaksin. Sila cuba lagi.",
    "No vaccines available. Please try again later.": "Tiada vaksin tersedia. Sila cuba lagi nanti.",
    "Selected Vaccine: {}": "Vaksin Dipilih: {}",

    # From amb_calendar_utils.py
    "⚠️ *ERROR STARTING EMERGENCY*\n\nUnable to start emergency service. Please try again or call 999 immediately.": "⚠️ *RALAT MEMULAKAN KECEMASAN*\n\nTidak dapat memulakan perkhidmatan kecemasan. Sila cuba lagi atau hubungi 999 segera.",

    # From tcm_service.py
    "⚠️ *TCM BOOKING SUMMARY*\n\nService: {}\nDoctor: {}\nDate: {}\nTime: {}\nAddress: {}\nRemarks: {}\n\nConfirm?": "⚠️ *RINGKASAN TEMPAHAN TCM*\n\nPerkhidmatan: {}\nDoktor: {}\nTarikh: {}\nMasa: {}\nAlamat: {}\nCatatan: {}\n\nSahkan?",
    "⚠️ *REMARK REQUIRED*\n\nFor {}, do you have remarks?": "⚠️ *CATATAN DIPERLUKAN*\n\nUntuk {}, adakah anda ada catatan?",
    "⚠️ *REMARKS*\n\nPlease enter remarks for {}:": "⚠️ *CATATAN*\n\nSila masukkan catatan untuk {}:",
    "⚠️ *REMARKS SAVED*\n\nProceed to booking?": "⚠️ *CATATAN DISIMPAN*\n\nTeruskan ke tempahan?",
    "⚠️ *BOOKING CANCELLED*\n\nReturned to main menu.": "⚠️ *TEMPAHAN DIBATALKAN*\n\nKembali ke menu utama.",
    "⚠️ *DOCTOR SELECTION*\n\nSelect a doctor for {}:": "⚠️ *PEMILIHAN DOKTOR*\n\nPilih doktor untuk {}:",
    "Doctors for {}": "Doktor untuk {}",
    "No doctors available for {}.": "Tiada doktor tersedia untuk {}.",
    "Error loading doctors for {}. Please try again.": "Ralat memuat doktor untuk {}. Sila cuba lagi.",
    "⚠️ *BOOKING SUMMARY*\n\nService: {}\nDoctor: {}\nDate: {}\nTime: {}\nAddress: {}\nRemarks: {}\n\nConfirm?": "⚠️ *RINGKASAN TEMPAHAN*\n\nPerkhidmatan: {}\nDoktor: {}\nTarikh: {}\nMasa: {}\nAlamat: {}\nCatatan: {}\n\nSahkan?",
    "✅ *TCM BOOKING CONFIRMED!*\n\nID: {}\nService: {}\nDoctor: {}\nDate: {}\nTime: {}\nAddress: {}\nRemarks: {}\n\nStatus: PENDING\n\nYou'll be notified when approved.": "✅ *TEMPAHAN TCM DISAHKAN!*\n\nID: {}\nPerkhidmatan: {}\nDoktor: {}\nTarikh: {}\nMasa: {}\nAlamat: {}\nCatatan: {}\n\nStatus: MENUNGGU\n\nAnda akan dimaklumkan apabila diluluskan.",

    # From report_symptoms.py
    "Symptoms saved. Proceed to booking?": "Gejala disimpan. Teruskan ke tempahan?",
    "Change Symptoms": "Tukar Gejala",

    # From checkup_booking.py
    "Please select a checkup type:": "Sila pilih jenis pemeriksaan:",
    "Checkup Types": "Jenis Pemeriksaan",
    "Error loading checkups. Please try again.": "Ralat memuat pemeriksaan. Sila cuba lagi.",
    "No checkups available. Please try again later.": "Tiada pemeriksaan tersedia. Sila cuba lagi nanti.",
    "Selected Checkup: {}": "Pemeriksaan Dipilih: {}",

    # From afterservice.py
    "Hi {patient_name}, how are you feeling regarding your {diagnosis}?": "Hai {patient_name}, bagaimana perasaan anda mengenai {diagnosis} anda?",
    "How are you feeling today?": "Bagaimana perasaan anda hari ini?",
    "Thank you for updating your symptoms. Your doctor will see this information.": "Terima kasih mengemaskini gejala anda. Doktor anda akan lihat maklumat ini.",

    # From notification.py
    "Notification already sent for user {user_id}, case {case_id}, type {reminder_type}": "Pemberitahuan sudah dihantar untuk pengguna {user_id}, kes {case_id}, jenis {reminder_type}",
    "Created {reminder_type} reminder for {whatsapp_number}, {table_name} {case_id}": "Dicipta peringatan {reminder_type} untuk {whatsapp_number}, {table_name} {case_id}",
    "Error processing {table_name} {booking_id} from {table_name}: {error}": "Ralat memproses {table_name} {booking_id} dari {table_name}: {error}",
    "Failed to fetch from {table_name}: {error}": "Gagal mengambil dari {table_name}: {error}",
    "Error sending notification: {}": "Ralat menghantar pemberitahuan: {}",
    "Notification sent successfully to {}: {}": "Pemberitahuan berjaya dihantar ke {}: {}",
    "Error sending template: {}": "Ralat menghantar templat: {}",
    "Template sent successfully to {}: {}": "Templat berjaya dihantar ke {}: {}",
    "Error sending fallback message: {}": "Ralat menghantar mesej fallback: {}",
    "Fallback message sent to {}: {}": "Mesej fallback dihantar ke {}: {}",
    "Notifications": "Pemberitahuan",
    "Error fetching notifications: {}": "Ralat mengambil pemberitahuan: {}",
    "No new notifications.": "Tiada pemberitahuan baru.",
    "✅ All notifications noted.": "✅ Semua pemberitahuan diperhatikan.",
    "Error updating notifications: {}": "Ralat mengemaskini pemberitahuan: {}",
    "Error noting notification: {}": "Ralat memperhatikan pemberitahuan: {}",
    "Notification noted successfully.": "Pemberitahuan berjaya diperhatikan.",
    "Error sending reminder: {}": "Ralat menghantar peringatan: {}",
    "Reminder sent to {}: {}": "Peringatan dihantar ke {}: {}",
    "Error sending confirmation: {}": "Ralat menghantar pengesahan: {}",
    "Confirmation sent to {}: {}": "Pengesahan dihantar ke {}: {}",
    "Error sending immediate confirmation: {}": "Ralat menghantar pengesahan segera: {}",
    "Immediate confirmation sent to {}: {}": "Pengesahan segera dihantar ke {}: {}",
    "Error sending followup: {}": "Ralat menghantar susulan: {}",
    "Followup sent to {}: {}": "Susulan dihantar ke {}: {}",
    "Error updating followup: {}": "Ralat mengemaskini susulan: {}",
    "Followup updated successfully for {}": "Susulan berjaya dikemaskini untuk {}",
    "Error saving template response: {}": "Ralat menyimpan respons templat: {}",
    "Template response saved successfully for {}": "Respons templat berjaya disimpan untuk {}",

    # From concierge.py
    # Already included above

    # From main.py - duplicate entries but ensure consistency
    "Error fetching notifications: {}": "Ralat mengambil pemberitahuan: {}",
    "Hi, you have new notification(s), please tap on \"notification\" button in the Main Menu to check them.": "Anda ada pemberitahuan baru, sila tekan butang \"pemberitahuan\" di Menu Utama untuk lihat.",
    "Report & Follow up": "Laporan & Susulan",
    
    # From reschedule_booking.py - additional entries
    "Save error! Please try again.": "Ralat simpan! Sila cuba lagi.",
    "No bookings found.": "Tiada tempahan ditemui.",
    "Please select a booking to reschedule:": "Sila pilih tempahan untuk jadual semula:",
    "Error loading available dates. Please try again.": "Ralat memuat tarikh tersedia. Sila cuba lagi.",
    "Error loading available hours. Please try again.": "Ralat memuat jam tersedia. Sila cuba lagi.",
    "Error loading available slots. Please try again.": "Ralat memuat slot tersedia. Sila cuba lagi.",
    "Error confirming reschedule. Please try again.": "Ralat mengesahkan jadual semula. Sila cuba lagi.",
    "Reschedule cancelled.": "Jadual semula dibatalkan.",
    
    # From tcm_service.py - additional entries
    "Unable to load services. Please try again.": "Tidak dapat memuat perkhidmatan. Sila cuba lagi.",
    "🌿 TCM Services": "🌿 Perkhidmatan TCM",
    "Please select a treatment service:": "Sila pilih perkhidmatan rawatan:",
    "Choose a service to proceed": "Pilih perkhidmatan untuk teruskan",
    "Select Service": "Pilih Perkhidmatan",
    "Available Services": "Perkhidmatan Tersedia",
    "🔙 Back to Categories": "🔙 Kembali ke Kategori",
    "No Remarks": "Tiada Catatan",
    "Enter Remarks": "Masukkan Catatan",
    "Proceed": "Teruskan",
    "Change Remarks": "Tukar Catatan",
    "Error confirming booking. Please try again.": "Ralat mengesahkan tempahan. Sila cuba lagi.",
    
    # From healthsp.py - additional entries
    "Selected Doctor: {}": "Doktor Dipilih: {}",
    "Selected Date: {}": "Tarikh Dipilih: {}",
    "Selected Period: {}": "Tempoh Dipilih: {}",
    "Selected Hour: {}": "Jam Dipilih: {}",
    
    # From checkup_booking.py - additional entries
    # Already included above
    
    # From vaccination_booking.py - additional entries
    # Already included above
    
    # ========== MISSING TRANSLATIONS SECTION ==========
    # These are keys from the provided dictionary that weren't in the original EN_TO_BM
    
    "⚠️ *ERROR STARTING EMERGENCY*\n\nUnable to start emergency service. Please try again or call 999 immediately.": "⚠️ *RALAT MEMULAKAN KECEMASAN*\n\nTidak dapat memulakan perkhidmatan kecemasan. Sila cuba lagi atau hubungi 999 segera.",
    "⚠️ *ERROR COMPLETING EMERGENCY*\n\nPlease try again or call 999 immediately.": "⚠️ *RALAT MENYELESAIKAN KECEMASAN*\n\nSila cuba lagi atau hubungi 999 segera.",
    "⚠️ *ERROR SAVING HEALTH CONDITION*\n\nPlease try again.": "⚠️ *RALAT MENYIMPAN KEADAAN KESIHATAN*\n\nSila cuba lagi.",
    "⚠️ *AN ERROR OCCURRED*\n\nPlease try again or call 999 immediately for emergency assistance.": "⚠️ *RALAT BERLAKU*\n\nSila cuba lagi atau hubungi 999 segera untuk bantuan kecemasan.",
    "⚠️ *EMERGENCY AMBULANCE*\n\nIs this a life-threatening emergency? (e.g., heart attack, severe bleeding, unconscious)": "⚠️ *AMBULANS KECEMASAN*\n\nAdakah ini kecemasan yang mengancam nyawa? (cth., serangan jantung, pendarahan teruk, tidak sedar)",
    "⚠️ *NON-LIFE-THREATENING*\n\nFor non-critical cases, please use our standard booking service.": "⚠️ *TIDAK MENGANCAM NYAWA*\n\nUntuk kes tidak kritikal, sila gunakan perkhidmatan tempahan standard kami.",
    "⚠️ *LIFE-THREATENING EMERGENCY*\n\nPlease call 999 immediately!\n\nFor clinic transport, continue below.": "⚠️ *KECEMASAN MENGANCAM NYAWA*\n\nSila hubungi 999 segera!\n\nUntuk pengangkutan klinik, teruskan di bawah.",
    "⚠️ *EMERGENCY LOCATION*\n\nPlease share your exact location:": "⚠️ *LOKASI KECEMASAN*\n\nSila kongsi lokasi tepat anda:",
    "⚠️ *ERROR GETTING LOCATION*\n\nPlease try again or enter your address manually.": "⚠️ *RALAT MENDAPATKAN LOKASI*\n\nSila cuba lagi atau masukkan alamat anda secara manual.",
    "⚠️ *LOCATION RECEIVED*\n\nAddress: {}\n\nDistance from clinic: {} km\n\nIs this correct?": "⚠️ *LOKASI DITERIMA*\n\nAlamat: {}\n\nJarak dari klinik: {} km\n\nAdakah ini betul?",
    "⚠️ *INVALID LOCATION*\n\nLocation must be within {}km of clinic.\n\nPlease share accurate location.": "⚠️ *LOKASI TIDAK SAH*\n\nLokasi mesti dalam {}km dari klinik.\n\nSila kongsi lokasi yang tepat.",
    "⚠️ *LOCATION CONFIRMED*\n\nPatient Name:": "⚠️ *LOKASI DISAHKAN*\n\nNama Pesakit:",
    "⚠️ *ERROR SAVING NAME*\n\nPlease try again.": "⚠️ *RALAT MENYIMPAN NAMA*\n\nSila cuba lagi.",
    "⚠️ *PATIENT NAME SAVED*\n\nPatient IC (YYMMDD-XX-XXXX):": "⚠️ *NAMA PESAKIT DISIMPAN*\n\nIC Pesakit (YYMMDD-XX-XXXX):",
    "⚠️ *INVALID IC*\n\nPlease enter valid IC format.": "⚠️ *IC TIDAK SAH*\n\nSila masukkan format IC yang sah.",
    "⚠️ *ERROR SAVING IC*\n\nPlease try again.": "⚠️ *RALAT MENYIMPAN IC*\n\nSila cuba lagi.",
    "⚠️ *IC SAVED*\n\nPatient Phone:": "⚠️ *IC DISIMPAN*\n\nTelefon Pesakit:",
    "⚠️ *ERROR SAVING PHONE*\n\nPlease try again.": "⚠️ *RALAT MENYIMPAN TELEFON*\n\nSila cuba lagi.",
    "⚠️ *PHONE SAVED*\n\nEmergency Contact Name:": "⚠️ *TELEFON DISIMPAN*\n\nNama Kenalan Kecemasan:",
    "⚠️ *ERROR SAVING EMERGENCY NAME*\n\nPlease try again.": "⚠️ *RALAT MENYIMPAN NAMA KECEMASAN*\n\nSila cuba lagi.",
    "⚠️ *EMERGENCY NAME SAVED*\n\nEmergency Contact Phone:": "⚠️ *NAMA KECEMASAN DISIMPAN*\n\nTelefon Kenalan Kecemasan:",
    "⚠️ *ERROR SAVING EMERGENCY PHONE*\n\nPlease try again.": "⚠️ *RALAT MENYIMPAN TELEFON KECEMASAN*\n\nSila cuba lagi.",
    "⚠️ *EMERGENCY PHONE SAVED*\n\nHealth Condition:": "⚠️ *TELEFON KECEMASAN DISIMPAN*\n\nKeadaan Kesihatan:",
    "⚠️ *EMERGENCY REQUEST SUBMITTED*\n\nAlert ID: {}\nPatient: {}\nIC: {}\nPhone: {}\nEmergency: {} ({})\nLocation: {}\nDistance: {} km\nCondition: {}\n\nAmbulance ETA: ~{} min\n\nStay on line for updates.\n\nIf critical, call 999!": "⚠️ *PERMINTAAN KECEMASAN DIHANTAR*\n\nID Amaran: {}\nPesakit: {}\nIC: {}\nTelefon: {}\nKecemasan: {} ({})\nLokasi: {}\nJarak: {} km\nKeadaan: {}\n\nETA Ambulans: ~{} min\n\nKekal dalam talian untuk kemaskini.\n\nJika kritikal, hubungi 999!",
    "⚠️ *ERROR SUBMITTING EMERGENCY*\n\nPlease try again or call 999.": "⚠️ *RALAT MENGHANTAR KECEMASAN*\n\nSila cuba lagi atau hubungi 999.",
    
    # Additional missing entries
    "Report & Follow up": "Laporan & Susulan",
    "Home to Hospital": "Rumah ke Hospital", 
    "Hospital to Home": "Hospital ke Rumah",
    "Hospital Discharge": "Keluar Hospital",
    "Hospital to Hospital": "Hospital ke Hospital",
    "Home to Home": "Rumah ke Rumah",
    "Return Service": "Perkhidmatan Pulangan",
    "Cancel All": "Batalkan Semua",
    "Cancel This Only": "Batalkan Yang Ini Sahaja",
    "Reschedule All": "Jadual Semula Semua",
    "Reschedule This Only": "Jadual Semula Yang Ini Sahaja",
}

# Keys that need truncation for buttons, section titles, and row titles
TRUNCATE_KEYS = [
    # utils.py
    "Menu", "Main Options", "Notification", "Booking", "🌐Change Language", "❓Help",
    "Booking Options", "Booking Services", "General GP Visit", "Checkup & Test",
    "Vaccination", "Report Result Booking", "View Booking", "Reschedule Booking",
    # calendar_utils.py
    "Choose Doctor", "Available Doctors", "Any Doctor", "Choose Date", "Available Dates",
    "Choose Hour", "Available Hours", "Choose Slot", "30min Slots", "Confirm", "Cancel",
    # menu.py + main.py
    "Select Language", "Languages", "English", "Bahasa Malaysia", "中文", "தமிழ்",
    # checkup_booking.py
    "Choose Checkup", "Checkup Types", "Yes", "No",
    # vaccination.py
    "Choose Vaccine", "Vaccine Types",
    # report_booking.py
    "📋 Select Report", "Select Report", "Your Reports",
    # view_booking.py
    "View Booking Options", "View Past Consultations", "View Upcoming Bookings", "Request Report",
    "Past Consultations", "Select Option", "Booking Options",
    # reschedule_booking.py
    "Choose Category", "Categories", "Choose Booking", "Bookings", "Reschedule", "Cancel Booking",
    "Accept", "Decline",
    # From new dictionary
    "Home to Hospital", "Hospital to Home", "Hospital Discharge", "Hospital to Hospital", "Home to Home",
    "Cancel All", "Cancel This Only", "Reschedule All", "Reschedule This Only", "Return Service",
    "Report & Follow up", "Morning", "Afternoon", "Evening", "Time Periods", "Available Dates",
    "Enter Future Date", "Hospitals", "Return Dates", "Booking Dates", "Dates", "Add Attachments",
    "No Attachments", "Enter Remarks", "No Remarks", "Proceed", "Change Remarks",
    "Health Screening Plan", "Screening Packages", "Checkup Types", "Vaccines",
    "TCM Services", "Select Service", "Available Services", "Select Type", "TCM Service Types",
    "Select Clinic", "Available Clinics", "Select Category", "Treatment Categories",
    "Back to Services", "Back to Type Selection", "Back to Clinics", "Back to Categories",
]

def truncate_text(text: str, max_length: int = 20) -> str:
    """Truncate text to max_length, preserving whole words if possible."""
    if len(text) <= max_length:
        return text
    truncated = text[:max_length]
    last_space = truncated.rfind(" ")
    if last_space != -1 and last_space > max_length // 2:
        truncated = truncated[:last_space] + "..."
    else:
        truncated = truncated[:max_length - 3] + "..."
    return truncated

def bm_translate_template(text: str, supabase=None) -> str:
    """
    Translate text to Bahasa Malaysia using the EN_TO_BM dictionary.
    Used for static UI elements and predefined messages.
    Preserves doctor names if provided.
    """
    try:
        if not text:
            return text

        # Base protected keywords
        protected_keywords = [
            "AnyHealth", "language:", "lang:", "தமிழ்", "English", "Bahasa Malaysia", "中文",
            "🌐change language", "change language", "🌐change_language"
        ]

        # Fetch doctor and clinic names from ALL tables if supabase is provided
        if supabase:
            try:
                # Regular doctors and clinics
                doctors = supabase.table("c_a_doctors").select("name").execute().data
                doctor_names = [doctor["name"] for doctor in doctors]
                clinics = supabase.table("c_a_clinics").select("name").execute().data
                clinic_names = [clinic["name"] for clinic in clinics]
                
                # TCM doctors and clinics  
                try:
                    tcm_doctors = supabase.table("tcm_a_doctors").select("name").execute().data
                    tcm_doctor_names = [doctor["name"] for doctor in tcm_doctors]
                    doctor_names.extend(tcm_doctor_names)
                except Exception as tcm_doc_e:
                    logger.warning(f"Could not fetch TCM doctors: {tcm_doc_e}")
                
                try:
                    tcm_clinics = supabase.table("tcm_a_clinics").select("name").execute().data
                    tcm_clinic_names = [clinic["name"] for clinic in tcm_clinics]
                    clinic_names.extend(tcm_clinic_names)
                except Exception as tcm_clinic_e:
                    logger.warning(f"Could not fetch TCM clinics: {tcm_clinic_e}")
                
                # Add all to protected keywords
                protected_keywords.extend(doctor_names)
                protected_keywords.extend(clinic_names)
                
            except Exception as e:
                logger.error(f"Error fetching doctor or clinic names: {e}")

        # Check for protected keywords
        clean_text = text.strip().lower()
        for keyword in protected_keywords:
            if keyword.lower() == clean_text or keyword.lower() in clean_text:
                return text

        # Handle templated strings with doctor name
        if "{}" in text:
            # Check dictionary for direct translation
            if text in EN_TO_BM:
                return EN_TO_BM[text]
            return text  # Fallback to original text if not in dictionary

        # Check dictionary for direct translation
        if text in EN_TO_BM:
            return EN_TO_BM[text]

        # If not in dictionary, return original text
        return text

    except Exception as e:
        logger.error(f"Translation error for '{text}': {e}")
        return text

def bm_gt_tt(text: str, supabase=None, doctor_name: str = None) -> str:
    """
    Translate text to Bahasa Malaysia using Google Translate API for dynamic database fields.
    Preserves AnyHealth, doctor names, and clinic names.
    Used for clinic_service.service_name, notifications.notification, and report_gen.report.
    """
    try:
        if not text:
            return text

        # Base protected keywords
        protected_keywords = ["AnyHealth", "language:", "lang:", "தமிழ்", "English", "Bahasa Malaysia", "中文",
                             "🌐change language", "change language", "🌐change_language"]

        # Fetch doctor and clinic names from ALL tables if supabase is provided
        doctor_names = []
        clinic_names = []
        if supabase:
            try:
                # Regular doctors and clinics
                doctors = supabase.table("c_a_doctors").select("name").execute().data
                doctor_names = [doctor["name"] for doctor in doctors]
                clinics = supabase.table("c_a_clinics").select("name").execute().data
                clinic_names = [clinic["name"] for clinic in clinics]
                
                # TCM doctors and clinics
                try:
                    tcm_doctors = supabase.table("tcm_a_doctors").select("name").execute().data
                    tcm_doctor_names = [doctor["name"] for doctor in tcm_doctors]
                    doctor_names.extend(tcm_doctor_names)
                except Exception as tcm_doc_e:
                    logger.warning(f"Could not fetch TCM doctors: {tcm_doc_e}")
                
                try:
                    tcm_clinics = supabase.table("tcm_a_clinics").select("name").execute().data
                    tcm_clinic_names = [clinic["name"] for clinic in tcm_clinics]
                    clinic_names.extend(tcm_clinic_names)
                except Exception as tcm_clinic_e:
                    logger.warning(f"Could not fetch TCM clinics: {tcm_clinic_e}")
                
                # Add all to protected keywords
                protected_keywords.extend(doctor_names)
                protected_keywords.extend(clinic_names)
                
            except Exception as e:
                logger.error(f"Error fetching doctor or clinic names: {e}")

        # Check for protected keywords
        clean_text = text.strip().lower()
        for keyword in protected_keywords:
            if keyword.lower() == clean_text or keyword.lower() in clean_text:
                return text

        # Protect doctor and clinic names in text
        placeholders = {}
        text_to_translate = text
        if supabase:
            for name in doctor_names + clinic_names:
                if name in text_to_translate:
                    placeholder = f"__PROTECTED_{len(placeholders)}__"
                    placeholders[placeholder] = name
                    text_to_translate = text_to_translate.replace(name, placeholder)
        elif doctor_name and doctor_name in text_to_translate:
            placeholder = "__DOCTOR_NAME__"
            placeholders[placeholder] = doctor_name
            text_to_translate = text_to_translate.replace(doctor_name, placeholder)

        # First check dictionary
        if text_to_translate in EN_TO_BM:
            translated_text = EN_TO_BM[text_to_translate]
        # Then try Google Translate if available
        elif translate_client:
            for attempt in range(3):
                try:
                    google_result = translate_client.translate(
                        text_to_translate, source_language="en", target_language="ms"
                    )
                    translated_text = google_result["translatedText"]
                    break
                except Exception as e:
                    logger.warning(f"Translate attempt {attempt + 1} failed: {e}")
                    if attempt == 2:  # Last attempt
                        translated_text = text_to_translate
                    time.sleep(2 ** attempt)
        else:
            translated_text = text_to_translate

        # Reinsert protected names
        for placeholder, name in placeholders.items():
            translated_text = translated_text.replace(placeholder, name)
            
        return translated_text

    except Exception as e:
        logger.error(f"Translation error for '{text}': {e}")
        return text

def bm_gt_t_tt(text: str, supabase=None, doctor_name: str = None) -> str:
    """
    Translate text to Bahasa Malaysia using Google Translate API with truncation for buttons/titles.
    Preserves AnyHealth, doctor names, and clinic names.
    Applies truncation (≤20 chars) for buttons, section titles, and row titles.
    Used for WhatsApp buttons and titles.
    """
    try:
        translated_text = bm_gt_tt(text, supabase, doctor_name)
        return truncate_text(translated_text, 20)
    except Exception as e:
        logger.error(f"Truncated translation error for '{text}': {e}")
        return truncate_text(text, 20)