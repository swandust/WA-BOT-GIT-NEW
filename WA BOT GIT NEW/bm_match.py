# bm_match.py - BAHASA MALAYSIA VERSION
import logging
import time
from google.cloud import translate_v2 as translate
import os
import html

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

EN_TO_BM = {
    # HEADER
    "AnyHealth Bot": "Bot AnyHealth",
    "Profiles": "Profil",
    "Options for {}": "Pilihan untuk {}",
    "Select Visit for Report": "Pilih Lawatan untuk Laporan",
    "Select Document": "Pilih Dokumen",
    "Select Race": "Pilih Bangsa",
    "Select Religion": "Pilih Agama",
    "Select Blood Type": "Pilih Jenis Darah",
    "Remove Profile": "Buang Profil",
    "Changed Numbers": "Nombor Ditukar",
    "Action Required": "Tindakan Diperlukan",
    "Confirmed": "Disahkan",
    "Pending": "Dalam Proses",
    "View Booking Options": "Lihat Pilihan Tempahan",
    "📍 Current Address (Pickup)": "📍 Alamat Semasa (Ambil)",
    "📍 Pickup Address Found": "📍 Alamat Ambil Ditemui",
    "📍 Destination Address Found": "📍 Alamat Destinasi Ditemui",
    "📱 Destination Emergency Contact": "📱 Kontak Kecemasan Destinasi",
    "📎 Attachments": "📎 Lampiran",
    "📝 Remarks": "📝 Catatan",
    "📅 Select Transfer Date": "📅 Pilih Tarikh Pindah",
    "⏰ Select 2-Hour Slot ({period})": "⏰ Pilih Slot 2 Jam ({period})",
    "⏱️ Select 15-Minute Interval": "⏱️ Pilih Selang 15 Minit",
    "🏥 Current Hospital Address Found": "🏥 Alamat Hospital Semasa Ditemui",
    "🏥 Destination Hospital Address Found": "🏥 Alamat Hospital Destinasi Ditemui",
    "🚑 Non-Emergency Ambulance": "🚑 Ambulans Bukan Kecemasan",
    "🌿 TCM Services": "🌿 Perkhidmatan TCM",

    # BODY
    "Please select your preferred language:": "Sila pilih bahasa pilihan anda:",
    "Welcome to our clinic! Please select a booking option.": "Selamat datang ke klinik kami! Sila pilih pilihan tempahan.",
    "Please choose a booking option:": "Sila pilih pilihan tempahan:",
    "⚠️ *Main Menu Confirmation*\n\nAre you sure you want to go back to the main menu?\nThis will cancel your current action.": "⚠️ *Pengesahan Menu Utama*\n\nAnda pasti mahu kembali ke menu utama?\nIni akan membatalkan tindakan semasa anda.",
    "Please select the type of non-emergency transport you need:\n\n• Scheduled patient transport\n• Advance booking required (24 hours)\n• Professional medical team": "Sila pilih jenis pengangkutan bukan kecemasan yang anda perlukan:\n\n• Pengangkutan pesakit berjadual\n• Tempahan awal diperlukan (24 jam)\n• Pasukan perubatan profesional",
    "Please share your current location:": "Sila kongsikan lokasi semasa anda:",
    "Session expired. Returning to main menu.": "Sesi tamat. Kembali ke menu utama.",
    "Continuing with your previous action.": "Meneruskan tindakan sebelumnya.",
    "Could not restore previous action. Returning to main menu.": "Tidak dapat memulihkan tindakan sebelumnya. Kembali ke menu utama.",
    "Error: No service selected. Please start over.": "Ralat: Tiada perkhidmatan dipilih. Sila mulakan semula.",
    "Do you have any remarks for {} ({} min){}?": "Ada sebarang catatan untuk {} ({} min){}?",
    "Please enter your remarks:": "Sila masukkan catatan anda:",
    "Please enter your preferred date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:": "Sila masukkan tarikh pilihan anda sebagai HH/BB/TTTT, HH-BB-TTTT atau HH BB TTTT:",
    "Please enter your preferred time (e.g., 9:30, 2pm, 1430):": "Sila masukkan masa pilihan anda (cth: 9:30, 2pm, 1430):",
    "Error saving vaccination booking. Please try again.": "Ralat menyimpan tempahan vaksin. Sila cuba lagi.",
    "Invalid input. Please use the buttons provided.": "Input tidak sah. Sila gunakan butang yang disediakan.",
    "✅ Your vaccination booking has been submitted!\n\n": "✅ Tempahan vaksin anda telah dihantar!\n\n",
    "Vaccine: ": "Vaksin: ",
    "Date: ": "Tarikh: ",
    "Time: ": "Masa: ",
    "Duration: ": "Tempoh: ",
    " minutes\n\n": " minit\n\n",
    "Booking is pending approval. You'll be notified once confirmed.\n": "Tempahan menunggu kelulusan. Anda akan dimaklumkan sekali disahkan.\n",
    "Booking ID: ": "ID Tempahan: ",
    "🏠 *AMBULANCE SERVICE: HOME TO HOME TRANSFER*": "🏠 *PERKHIDMATAN AMBULANS: PINDAH RUMAH KE RUMAH*",
    "This service helps transfer patients between homes (e.g., moving to family home).": "Perkhidmatan ini membantu memindahkan pesakit antara rumah (cth: pindah ke rumah keluarga).",
    "We'll collect information for your home-to-home transfer.": "Kami akan kumpulkan maklumat untuk pindahan rumah-ke-rumah anda.",
    "Please answer the following questions one by one.": "Sila jawab soalan berikut satu persatu.",
    "*IMPORTANT:*": "*PENTING:*",
    "• Provide accurate addresses for both locations": "• Beri alamat tepat untuk kedua-dua lokasi",
    "• Ensure patient is stable for transfer": "• Pastikan pesakit stabil untuk dipindah",
    "• Have all necessary medical equipment ready": "• Sediakan semua peralatan perubatan perlu",
    "• Coordinate with family members at both locations": "• Berkoordinasi dengan ahli keluarga di kedua-dua lokasi",
    "*QUESTIONS TO FOLLOW:*": "*SOALAN AKAN DITANYA:*",
    "1. Patient full name": "1. Nama penuh pesakit",
    "2. Patient IC number": "2. Nombor IC pesakit",
    "3. Patient phone number": "3. Nombor telefon pesakit",
    "4. Emergency contact at pickup location": "4. Kontak kecemasan di lokasi ambil",
    "5. Emergency contact phone at pickup location": "5. Telefon kontak kecemasan di lokasi ambil",
    "6. Current address (Pickup) with location sharing option": "6. Alamat semasa (Ambil) dengan pilihan kongsikan lokasi",
    "7. Destination address (manual input)": "7. Alamat destinasi (input manual)",
    "8. Reason for transfer": "8. Sebab pindahan",
    "9. Medical condition": "9. Keadaan perubatan",
    "*After these questions, we'll ask for destination emergency contact, attachments, and schedule.*": "*Selepas soalan ini, kami akan tanya kontak kecemasan destinasi, lampiran, dan jadual.*",
    "You can cancel anytime by typing 'cancel'.": "Anda boleh batal bila-bila dengan taip 'cancel'.",
    "6. *Current address (Pickup)*": "6. *Alamat semasa (Ambil)*",
    "How would you like to provide your current address?": "Bagaimana anda ingin beri alamat semasa?",
    "• *Share Location:* Send your current location (recommended)": "• *Kongsi Lokasi:* Hantar lokasi semasa (disyorkan)",
    "• *Type Address:* Enter your full address manually": "• *Taip Alamat:* Masukkan alamat penuh secara manual",
    "Example of manual address:": "Contoh alamat manual:",
    "Please type your full current address:": "Sila taip alamat semasa penuh anda:",
    "Example:": "Contoh:",
    "Include:": "Sertakan:",
    "• House/building number": "• Nombor rumah/bangunan",
    "• Street name": "• Nama jalan",
    "• Area/Taman": "• Kawasan/Taman",
    "• Postcode and City": "• Poskod dan Bandar",
    "• State": "• Negeri",
    "We found this address:": "Kami jumpa alamat ini:",
    "Is this your correct pickup address?": "Adakah ini alamat ambil yang betul?",
    "7. *Destination address*": "7. *Alamat destinasi*",
    "Please type the full destination address:": "Sila taip alamat destinasi penuh:",
    "Example:": "Contoh:",
    "Include:": "Sertakan:",
    "• House/building number": "• Nombor rumah/bangunan",
    "• Street name": "• Nama jalan",
    "• Area/Taman": "• Kawasan/Taman",
    "• Postcode and City": "• Poskod dan Bandar",
    "• State": "• Negeri",
    "We found this address:": "Kami jumpa alamat ini:",
    "Is this your correct destination address?": "Adakah ini alamat destinasi yang betul?",
    "8. *Reason for transfer*": "8. *Sebab pindahan*",
    "Please explain why you need this home-to-home transfer:": "Sila terangkan mengapa anda perlukan pindahan rumah-ke-rumah ini:",
    "Examples:": "Contoh:",
    "• Moving to family home for care": "• Pindah ke rumah keluarga untuk penjagaan",
    "• Returning from temporary stay": "• Kembali dari tempat tinggal sementara",
    "• Home modification needed": "• Pengubahsuaian rumah diperlukan",
    "• Closer to medical facilities": "• Lebih dekat ke kemudahan perubatan",
    "• Change of residence": "• Pertukaran tempat tinggal",
    "9. *Medical condition*": "9. *Keadaan perubatan*",
    "Please describe the patient's current medical condition:": "Sila huraikan keadaan perubatan semasa pesakit:",
    "Examples:": "Contoh:",
    "• Post-stroke recovery": "• Pemulihan selepas strok",
    "• Mobility limited": "• Pergerakan terhad",
    "• Requires oxygen therapy": "• Memerlukan terapi oksigen",
    "• Stable condition for transfer": "• Keadaan stabil untuk dipindah",
    "• Recent surgery": "• Pembedahan baru-baru ini",
    "Would you like to provide an emergency contact at the destination?": "Adakah anda ingin berikan kontak kecemasan di destinasi?",
    "This is optional but recommended for better coordination at the destination location.": "Ini pilihan tetapi disyorkan untuk koordinasi lebih baik di lokasi destinasi.",
    "Please provide the emergency contact name at the destination:": "Sila berikan nama kontak kecemasan di destinasi:",
    "Example: Rahman bin Ali or Aishah binti Hassan": "Contoh: Rahman bin Ali atau Aishah binti Hassan",
    "Please provide the emergency contact phone at the destination:": "Sila berikan telefon kontak kecemasan di destinasi:",
    "Example: 012-3456789 or 019-8765432": "Contoh: 012-3456789 atau 019-8765432",
    "You can upload attachments (photos/documents) related to this transfer.": "Anda boleh muat naik lampiran (gambar/dokumen) berkaitan pindahan ini.",
    "Examples:": "Contoh:",
    "• Medical reports": "• Laporan perubatan",
    "• Doctor's clearance for transfer": "• Kebenaran doktor untuk pindahan",
    "• Insurance documents": "• Dokumen insurans",
    "• Prescriptions": "• Preskripsi",
    "You can upload multiple attachments. When done, click 'Next'.": "Anda boleh muat naik pelbagai lampiran. Bila siap, klik 'Seterusnya'.",
    "Do you have any additional remarks or special instructions?": "Ada sebarang catatan tambahan atau arahan khas?",
    "Examples:": "Contoh:",
    "• Specific route preferences": "• Keutamaan laluan tertentu",
    "• Special medical equipment needed": "• Peralatan perubatan khas diperlukan",
    "• Time constraints": "• Kekangan masa",
    "• Additional patient information": "• Maklumat pesakit tambahan",
    "You can add remarks or skip to continue.": "Anda boleh tambah catatan atau langkau untuk teruskan.",
    "Please type your remarks or special instructions:": "Sila taip catatan atau arahan khas anda:",
    "Examples:": "Contoh:",
    "• Patient needs wheelchair assistance": "• Pesakit perlukan bantuan kerusi roda",
    "• Please use back entrance": "• Sila guna pintu belakang",
    "• Patient is fasting": "• Pesakit sedang berpuasa",
    "• Special handling requirements": "• Keperluan pengendalian khas",
    "Please select the transfer date:": "Sila pilih tarikh pindahan:",
    "*Today:*": "*Hari ini:*",
    "*Tomorrow:*": "*Esok:*",
    "If you need another date, select 'Others' and enter DD/MM/YYYY format.": "Jika perlukan tarikh lain, pilih 'Lain' dan masukkan format HH/BB/TTTT.",
    "Please select AM or PM for the transfer time:": "Sila pilih AM atau PM untuk masa pindahan:",
    "Please select a 2-hour time slot for transfer:": "Sila pilih slot masa 2 jam untuk pindahan:",
    "Selected Date:": "Tarikh Dipilih:",
    "Period:": "Tempoh:",
    "After selecting a slot, you'll choose the exact 15-minute interval.": "Selepas pilih slot, anda akan pilih selang tepat 15 minit.",
    "Please select the exact transfer time:": "Sila pilih masa pindahan yang tepat:",
    "Selected Date:": "Tarikh Dipilih:",
    "Selected Slot:": "Slot Dipilih:",
    "Choose your preferred 15-minute interval within this slot.": "Pilih selang 15 minit pilihan dalam slot ini.",
    "Error starting transfer request. Please try again.": "Ralat memulakan permintaan pindahan. Sila cuba lagi.",
    "Home transfer cancelled. Returning to main menu.": "Pindahan rumah dibatalkan. Kembali ke menu utama.",
    "Please provide a valid answer.": "Sila berikan jawapan yang sah.",
    "❌ *Invalid IC number format*": "❌ *Format nombor IC tidak sah*",
    "IC must be 12 digits.": "IC mesti 12 digit.",
    "Accepted formats:": "Format diterima:",
    "• 801212-14-5678": "• 801212-14-5678",
    "• 801212145678": "• 801212145678",
    "• 801212 14 5678": "• 801212 14 5678",
    "Please re-enter the patient's IC number:": "Sila masukkan semula nombor IC pesakit:",
    "Error processing your answer. Please try again.": "Ralat memproses jawapan anda. Sila cuba lagi.",
    "❌ Unsupported file type.": "❌ Jenis fail tidak disokong.",
    "Please send images (JPEG, PNG) or documents (PDF, DOC) only.": "Sila hantar imej (JPEG, PNG) atau dokumen (PDF, DOC) sahaja.",
    "Error: Could not get file information. Please try again.": "Ralat: Tidak dapat dapatkan maklumat fail. Sila cuba lagi.",
    "❌ Failed to download file from WhatsApp.": "❌ Gagal muat turun fail dari WhatsApp.",
    "Please try sending the file again.": "Sila cuba hantar fail semula.",
    "✅ *Attachment successfully saved!*": "✅ *Lampiran berjaya disimpan!*",
    "You can send more attachments or click 'Next' to continue.": "Anda boleh hantar lebih lampiran atau klik 'Seterusnya' untuk teruskan.",
    "❌ Failed to save attachment.": "❌ Gagal menyimpan lampiran.",
    "Please try again or click 'Skip' to continue without attachments.": "Sila cuba lagi atau klik 'Langkau' untuk teruskan tanpa lampiran.",
    "Error processing attachment. Please try again.": "Ralat memproses lampiran. Sila cuba lagi.",
    "Invalid selection. Please try again.": "Pilihan tidak sah. Sila cuba lagi.",
    "Date cannot be in the past.": "Tarikh tidak boleh dari masa lalu.",
    "Please enter a future date in DD/MM/YYYY format.": "Sila masukkan tarikh akan datang dalam format HH/BB/TTTT.",
    "Invalid date format.": "Format tarikh tidak sah.",
    "Please enter date in DD/MM/YYYY format.": "Sila masukkan tarikh dalam format HH/BB/TTTT.",
    "Example: 25/12/2024": "Contoh: 25/12/2024",
    "Error selecting time interval. Please try again.": "Ralat memilih selang masa. Sila cuba lagi.",
    "Error submitting transfer request. Please try again.": "Ralat menghantar permintaan pindahan. Sila cuba lagi.",
    "✅ *HOME TO HOME TRANSFER CONFIRMED*": "✅ *PINDAH RUMAH KE RUMAH DISAHKAN*",
    "Your home-to-home transfer request has been received.": "Permintaan pindahan rumah-ke-rumah anda telah diterima.",
    "Our team will contact you to arrange details.": "Pasukan kami akan hubungi anda untuk atur butiran.",
    "*Next Steps:*": "*Langkah Seterusnya:*",
    "1. Team will verify details": "1. Pasukan akan sahkan butiran",
    "2. You'll receive confirmation call": "2. Anda akan terima panggilan pengesahan",
    "3. Transfer schedule will be arranged": "3. Jadual pindahan akan diatur",
    "Thank you for using AnyHealth Ambulance Service! 🚑": "Terima kasih kerana menggunakan Perkhidmatan Ambulans AnyHealth! 🚑",
    "🏥 *AMBULANCE SERVICE: HOSPITAL TO HOSPITAL TRANSFER*": "🏥 *PERKHIDMATAN AMBULANS: PINDAH HOSPITAL KE HOSPITAL*",
    "This service helps transfer patients between hospitals for specialized care.": "Perkhidmatan ini membantu memindahkan pesakit antara hospital untuk rawatan pakar.",
    "We'll collect information for your inter-hospital transfer.": "Kami akan kumpulkan maklumat untuk pindahan antara hospital anda.",
    "Please answer the following questions one by one.": "Sila jawab soalan berikut satu persatu.",
    "*IMPORTANT:*": "*PENTING:*",
    "• Ensure both hospitals are aware of the transfer": "• Pastikan kedua-dua hospital maklum tentang pindahan",
    "• Provide accurate hospital names": "• Beri nama hospital yang tepat",
    "• We'll automatically find hospital addresses": "• Kami akan cari alamat hospital secara automatik",
    "• Have medical files ready for transfer": "• Sediakan fail perubatan untuk pindahan",
    "---": "---",
    "*QUESTIONS TO FOLLOW:*": "*SOALAN AKAN DITANYA:*",
    "1. Patient name": "1. Nama pesakit",
    "2. Patient IC number": "2. Nombor IC pesakit",
    "3. Patient phone number": "3. Nombor telefon pesakit",
    "4. Emergency contact name": "4. Nama kontak kecemasan",
    "5. Emergency contact phone": "5. Telefon kontak kecemasan",
    "6. Current hospital name (we'll find the address)": "6. Nama hospital semasa (kami akan cari alamat)",
    "7. Ward number and level (e.g., Ward 5A, Level 3)": "7. Nombor wad dan tingkat (cth: Wad 5A, Tingkat 3)",
    "8. Destination hospital name (we'll find the address)": "8. Nama hospital destinasi (kami akan cari alamat)",
    "*After these questions, you can upload attachments, add remarks, and schedule the transfer.*": "*Selepas soalan ini, anda boleh muat naik lampiran, tambah catatan, dan jadualkan pindahan.*",
    "You can cancel anytime by typing 'cancel'.": "Anda boleh batal bila-bila dengan taip 'cancel'.",
    "6. *Current hospital name*": "6. *Nama hospital semasa*",
    "Please type the name of the current hospital:": "Sila taip nama hospital semasa:",
    "Examples:": "Contoh:",
    "• Hospital Kuala Lumpur": "• Hospital Kuala Lumpur",
    "• Sunway Medical Centre": "• Sunway Medical Centre",
    "• Pantai Hospital Kuala Lumpur": "• Pantai Hospital Kuala Lumpur",
    "• University Malaya Medical Centre": "• University Malaya Medical Centre",
    "We'll automatically find the address for you.": "Kami akan cari alamat untuk anda secara automatik.",
    "We found this address for *{hospital_name}*:": "Kami jumpa alamat ini untuk *{hospital_name}*:",
    "Is this the correct hospital address?": "Adakah ini alamat hospital yang betul?",
    "Please type the current hospital address manually:": "Sila taip alamat hospital semasa secara manual:",
    "Example:": "Contoh:",
    "Jalan Pahang, 53000 Kuala Lumpur, Wilayah Persekutuan Kuala Lumpur": "Jalan Pahang, 53000 Kuala Lumpur, Wilayah Persekutuan Kuala Lumpur",
    "Include full address with postcode and state.": "Sertakan alamat penuh dengan poskod dan negeri.",
    "7. *Ward number and level*": "7. *Nombor wad dan tingkat*",
    "Please provide the ward number and level:": "Sila berikan nombor wad dan tingkat:",
    "Examples:": "Contoh:",
    "• Ward 5A, Level 3": "• Wad 5A, Tingkat 3",
    "• ICU, Level 5": "• ICU, Tingkat 5",
    "• Ward 3B, Ground Floor": "• Wad 3B, Aras Bawah",
    "• Private Suite, Level 2": "• Suite Persendirian, Tingkat 2",
    "Enter both ward and level together.": "Masukkan kedua-dua wad dan tingkat bersama.",
    "8. *Destination hospital name*": "8. *Nama hospital destinasi*",
    "Please type the name of the destination hospital:": "Sila taip nama hospital destinasi:",
    "Examples:": "Contoh:",
    "• Hospital Kuala Lumpur": "• Hospital Kuala Lumpur",
    "• Sunway Medical Centre": "• Sunway Medical Centre",
    "• Pantai Hospital Kuala Lumpur": "• Pantai Hospital Kuala Lumpur",
    "• University Malaya Medical Centre": "• University Malaya Medical Centre",
    "We'll automatically find the address for you.": "Kami akan cari alamat untuk anda secara automatik.",
    "We found this address for *{hospital_name}*:": "Kami jumpa alamat ini untuk *{hospital_name}*:",
    "Is this the correct hospital address?": "Adakah ini alamat hospital yang betul?",
    "Please type the destination hospital address manually:": "Sila taip alamat hospital destinasi secara manual:",
    "Example:": "Contoh:",
    "Jalan Pahang, 53000 Kuala Lumpur, Wilayah Persekutuan Kuala Lumpur": "Jalan Pahang, 53000 Kuala Lumpur, Wilayah Persekutuan Kuala Lumpur",
    "Include full address with postcode and state.": "Sertakan alamat penuh dengan poskod dan negeri.",
    "You can upload attachments (photos/documents) related to this transfer.": "Anda boleh muat naik lampiran (gambar/dokumen) berkaitan pindahan ini.",
    "Examples:": "Contoh:",
    "• Medical reports": "• Laporan perubatan",
    "• Doctor's referral letters": "• Surat rujukan doktor",
    "• Insurance documents": "• Dokumen insurans",
    "• Transfer forms": "• Borang pindahan",
    "You can upload multiple attachments. When done, click 'Next'.": "Anda boleh muat naik pelbagai lampiran. Bila siap, klik 'Seterusnya'.",
    "Do you have any additional remarks or special instructions?": "Ada sebarang catatan tambahan atau arahan khas?",
    "Examples:": "Contoh:",
    "• Specific medical equipment needed": "• Peralatan perubatan tertentu diperlukan",
    "• Time constraints for transfer": "• Kekangan masa untuk pindahan",
    "• Special handling requirements": "• Keperluan pengendalian khas",
    "• Additional patient information": "• Maklumat pesakit tambahan",
    "You can add remarks or skip to continue.": "Anda boleh tambah catatan atau langkau untuk teruskan.",
    "Please type your remarks or special instructions:": "Sila taip catatan atau arahan khas anda:",
    "Examples:": "Contoh:",
    "• Patient requires ventilator during transfer": "• Pesakit perlukan ventilator semasa pindahan",
    "• Specific route preferred": "• Laluan tertentu diutamakan",
    "• Need ambulance with ICU facilities": "• Perlukan ambulans dengan kemudahan ICU",
    "• Coordination with specific hospital staff": "• Koordinasi dengan kakitangan hospital tertentu",
    "Please select the transfer date:": "Sila pilih tarikh pindahan:",
    "*Today:*": "*Hari ini:*",
    "*Tomorrow:*": "*Esok:*",
    "If you need another date, select 'Others' and enter DD/MM/YYYY format.": "Jika perlukan tarikh lain, pilih 'Lain' dan masukkan format HH/BB/TTTT.",
    "Please select AM or PM for the transfer time:": "Sila pilih AM atau PM untuk masa pindahan:",
    "Please select a 2-hour time slot for the transfer:": "Sila pilih slot masa 2 jam untuk pindahan:",
    "Selected Date:": "Tarikh Dipilih:",
    "Period:": "Tempoh:",
    "After selecting a slot, you'll choose the exact 15-minute interval.": "Selepas pilih slot, anda akan pilih selang tepat 15 minit.",
    "Please select the exact time for the transfer:": "Sila pilih masa pindahan yang tepat:",
    "Selected Date:": "Tarikh Dipilih:",
    "Selected Slot:": "Slot Dipilih:",
    "Choose your preferred 15-minute interval within this slot.": "Pilih selang 15 minit pilihan dalam slot ini.",
    "Error starting transfer request. Please try again.": "Ralat memulakan permintaan pindahan. Sila cuba lagi.",
    "Could not find address for this hospital. Please provide the address manually.": "Tidak dapat cari alamat untuk hospital ini. Sila berikan alamat secara manual.",
    "Please enter the transfer date in DD/MM/YYYY format:": "Sila masukkan tarikh pindahan dalam format HH/BB/TTTT:",
    "Example: 25/12/2024": "Contoh: 25/12/2024",
    "Error scheduling date. Please try again.": "Ralat menjadualkan tarikh. Sila cuba lagi.",
    "Error selecting time interval. Please try again.": "Ralat memilih selang masa. Sila cuba lagi.",
    "Hospital transfer cancelled. Returning to main menu.": "Pindahan hospital dibatalkan. Kembali ke menu utama.",
    "Please provide a valid answer.": "Sila berikan jawapan yang sah.",
    "❌ *Invalid IC number format*": "❌ *Format nombor IC tidak sah*",
    "IC must be 12 digits.": "IC mesti 12 digit.",
    "Accepted formats:": "Format diterima:",
    "• 801212-14-5678": "• 801212-14-5678",
    "• 801212145678": "• 801212145678",
    "• 801212 14 5678": "• 801212 14 5678",
    "Please re-enter the patient's IC number:": "Sila masukkan semula nombor IC pesakit:",
    "Error processing your answer. Please try again.": "Ralat memproses jawapan anda. Sila cuba lagi.",
    "Unsupported file type. Please send images (JPEG, PNG) or documents (PDF, DOC) only.": "Jenis fail tidak disokong. Sila hantar imej (JPEG, PNG) atau dokumen (PDF, DOC) sahaja.",
    "Error: Could not get file information. Please try again.": "Ralat: Tidak dapat dapatkan maklumat fail. Sila cuba lagi.",
    "Failed to download file from WhatsApp. Please try sending the file again.": "Gagal muat turun fail dari WhatsApp. Sila cuba hantar fail semula.",
    "Failed to save attachment. Please try again or click 'Skip' to continue without attachments.": "Gagal menyimpan lampiran. Sila cuba lagi atau klik 'Langkau' untuk teruskan tanpa lampiran.",
    "Error processing attachment. Please try again.": "Ralat memproses lampiran. Sila cuba lagi.",
    "Invalid selection. Please try again.": "Pilihan tidak sah. Sila cuba lagi.",
    "Date cannot be in the past. Please enter a future date in DD/MM/YYYY format.": "Tarikh tidak boleh dari masa lalu. Sila masukkan tarikh akan datang dalam format HH/BB/TTTT.",
    "Invalid date format. Please enter date in DD/MM/YYYY format.": "Format tarikh tidak sah. Sila masukkan tarikh dalam format HH/BB/TTTT.",
    "Example: 25/12/2024": "Contoh: 25/12/2024",
    "Error submitting transfer request. Please try again.": "Ralat menghantar permintaan pindahan. Sila cuba lagi.",
    "✅ *HOSPITAL TO HOSPITAL TRANSFER CONFIRMED*": "✅ *PINDAH HOSPITAL KE HOSPITAL DISAHKAN*",
    "Your inter-hospital transfer request has been received. Our team will coordinate with both hospitals.": "Permintaan pindahan antara hospital anda telah diterima. Pasukan kami akan berkoordinasi dengan kedua-dua hospital.",
    "*Next Steps:*": "*Langkah Seterusnya:*",
    "1. Team will contact both hospitals": "1. Pasukan akan hubungi kedua-dua hospital",
    "2. You'll receive confirmation call": "2. Anda akan terima panggilan pengesahan",
    "3. Transfer schedule will be arranged": "3. Jadual pindahan akan diatur",
    "Thank you for using AnyHealth Ambulance Service! 🚑": "Terima kasih kerana menggunakan Perkhidmatan Ambulans AnyHealth! 🚑",
    "I couldn't understand the time format. Please try entering the time again, or let me help you choose from available slots.": "Saya tidak faham format masa. Sila cuba masukkan masa semula, atau biar saya bantu pilih dari slot yang ada.",
    "Great! {formatted_display_time} is available. Is this the time you want?": "Bagus! {formatted_display_time} tersedia. Adakah ini masa yang anda mahu?",
    "Unfortunately {formatted_display_time} is not available. The closest available time is {formatted_closest} (just {minutes_diff} minutes difference). Would you like to book this instead?": "Malangnya {formatted_display_time} tidak tersedia. Masa terdekat yang ada ialah {formatted_closest} (hanya {minutes_diff} minit beza). Adakah anda ingin tempah ini?",
    "Unfortunately {formatted_display_time} is not available. The closest available time is {formatted_closest}. Would you like to book this instead?": "Malangnya {formatted_display_time} tidak tersedia. Masa terdekat yang ada ialah {formatted_closest}. Adakah anda ingin tempah ini?",
    "No available slots near {formatted_display_time}. Would you like to try a different time or let me help you choose from available slots?": "Tiada slot tersedia berhampiran {formatted_display_time}. Adakah anda ingin cuba masa lain atau biar saya bantu pilih dari slot yang ada?",
    "Select a doctor for your appointment or choose 'Any Doctor':": "Pilih doktor untuk temujanji anda atau pilih 'Mana-mana Doktor':",
    "Select a date for your appointment:": "Pilih tarikh untuk temujanji anda:",
    "Select {duration}min slot for {date} {hour}:": "Pilih slot {duration}min untuk {date} {hour}:",
    "What would you like to edit?": "Apa yang anda ingin edit?",
    "Is this the correct date: {formatted_date}?": "Adakah tarikh ini betul: {formatted_date}?",
    "Selected date {formatted_date_short} is not available. Here are the nearest available dates:": "Tarikh dipilih {formatted_date_short} tidak tersedia. Ini tarikh tersedia terdekat:",
    "Confirm your booking:\n• Service: {}\n• Doctor: {}\n• Date: {}\n• Time: {}\n• Duration: {} min\n• Details: {}\n• Reminder: {}": "Sahkan tempahan anda:\n• Perkhidmatan: {}\n• Doktor: {}\n• Tarikh: {}\n• Masa: {}\n• Tempoh: {} min\n• Butiran: {}\n• Peringatan: {}",
    "Confirm your booking:\n• Service: {}\n• Doctor: {}\n• Date: {}\n• Time: {}\n• Duration: {} min\n• Details: {}": "Sahkan tempahan anda:\n• Perkhidmatan: {}\n• Doktor: {}\n• Tarikh: {}\n• Masa: {}\n• Tempoh: {} min\n• Butiran: {}",
    "Your checkup booking is pending approval by the admin.": "Tempahan pemeriksaan anda menunggu kelulusan admin.",
    "Your consultation booking is pending approval by the admin.": "Tempahan konsultasi anda menunggu kelulusan admin.",
    "Your vaccination booking is pending approval by the admin.": "Tempahan vaksinasi anda menunggu kelulusan admin.",
    "Your health screening booking is pending approval by the admin.": "Tempahan saringan kesihatan anda menunggu kelulusan admin.",
    "Error processing time. Please try again.": "Ralat memproses masa. Sila cuba lagi.",
    "No doctors available. Please contact support.": "Tiada doktor tersedia. Sila hubungi sokongan.",
    "Unable to fetch doctors. Please try again.": "Tidak dapat dapatkan doktor. Sila cuba lagi.",
    "An error occurred while fetching doctors: {str(e)}. Please try again.": "Ralat berlaku semasa mendapatkan doktor: {str(e)}. Sila cuba lagi.",
    "Time slot not found. Please try again.": "Slot masa tidak ditemui. Sila cuba lagi.",
    "Error confirming time. Please try again.": "Ralat mengesahkan masa. Sila cuba lagi.",
    "Error processing choice. Please try again.": "Ralat memproses pilihan. Sila cuba lagi.",
    "No available dates in the next 14 days. Please {}.": "Tiada tarikh tersedia dalam 14 hari akan datang. Sila {}.",
    "Unable to fetch calendar. Please try again.": "Tidak dapat dapatkan kalendar. Sila cuba lagi.",
    "An error occurred while fetching the calendar: {str(e)}. Please try again.": "Ralat berlaku semasa mendapatkan kalendar: {str(e)}. Sila cuba lagi.",
    "No available hours for this date. Please select another date.": "Tiada jam tersedia untuk tarikh ini. Sila pilih tarikh lain.",
    "Unable to fetch hours. Please try again.": "Tidak dapat dapatkan jam. Sila cuba lagi.",
    "An error occurred while fetching hours: {str(e)}. Please try again.": "Ralat berlaku semasa mendapatkan jam: {str(e)}. Sila cuba lagi.",
    "Invalid period selection. Please try again.": "Pilihan tempoh tidak sah. Sila cuba lagi.",
    "No available hours in this period. Please select another date.": "Tiada jam tersedia dalam tempoh ini. Sila pilih tarikh lain.",
    "No available time slots.": "Tiada slot masa tersedia.",
    "Error loading slots.": "Ralat memuatkan slot.",
    "No doctors available. Please try again later.": "Tiada doktor tersedia. Sila cuba lagi kemudian.",
    "No doctors available for this time slot. Please select another.": "Tiada doktor tersedia untuk slot masa ini. Sila pilih yang lain.",
    "An error occurred while confirming the booking: {str(e)}. Please try again.": "Ralat berlaku semasa mengesahkan tempahan: {str(e)}. Sila cuba lagi.",
    "Error loading edit options. Please try again.": "Ralat memuatkan pilihan edit. Sila cuba lagi.",
    "Invalid edit option. Please try again.": "Pilihan edit tidak sah. Sila cuba lagi.",
    "Error processing edit choice. Please try again.": "Ralat memproses pilihan edit. Sila cuba lagi.",
    "Failed to save booking. Please try again.": "Gagal menyimpan tempahan. Sila cuba lagi.",
    "Failed to send confirmation. Booking cancelled. Please try again.": "Gagal menghantar pengesahan. Tempahan dibatalkan. Sila cuba lagi.",
    "An error occurred while confirming the booking: {str(e)}. Please try again.": "Ralat berlaku semasa mengesahkan tempahan: {str(e)}. Sila cuba lagi.",
    "Booking has been cancelled.": "Tempahan telah dibatalkan.",
    "Invalid date format. Please enter date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:": "Format tarikh tidak sah. Sila masukkan tarikh sebagai HH/BB/TTTT, HH-BB-TTTT atau HH BB TTTT:",
    "Please select a future date. Enter date as DD/MM/YYYY:": "Sila pilih tarikh akan datang. Masukkan tarikh sebagai HH/BB/TTTT:",
    "Error processing date. Please try again.": "Ralat memproses tarikh. Sila cuba lagi.",
    "Date not found. Please try again.": "Tarikh tidak ditemui. Sila cuba lagi.",
    "Error confirming date. Please try again.": "Ralat mengesahkan tarikh. Sila cuba lagi.",
    "No available dates found near {formatted_date_short}. Please enter a different date as DD/MM/YYYY:": "Tiada tarikh tersedia berhampiran {formatted_date_short}. Sila masukkan tarikh lain sebagai HH/BB/TTTT:",
    "Monday": "Isnin",
    "Tuesday": "Selasa",
    "Wednesday": "Rabu",
    "Thursday": "Khamis",
    "Friday": "Jumaat",
    "Saturday": "Sabtu",
    "Sunday": "Ahad",
    "Checkup": "Pemeriksaan",
    "Vaccination": "Vaksinasi",
    "Consultation": "Konsultasi",
    "Health Screening": "Saringan Kesihatan",
    "Appointment": "Temujanji",
    "Do you have any remarks for {} ({} min){}?": "Ada sebarang catatan untuk {} ({} min){}?",
    "Error: No service selected. Please start over.": "Ralat: Tiada perkhidmatan dipilih. Sila mulakan semula.",
    "Please enter your remarks:": "Sila masukkan catatan anda:",
    "Please enter your preferred date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:": "Sila masukkan tarikh pilihan anda sebagai HH/BB/TTTT, HH-BB-TTTT atau HH BB TTTT:",
    "Please enter your preferred time (e.g., 9:30, 2pm, 1430):": "Sila masukkan masa pilihan anda (cth: 9:30, 2pm, 1430):",
    "✅ Your checkup booking has been submitted!\n\nService: {}\nDate: {}\nTime: {}\nDuration: {} minutes\n\nBooking is pending approval. You'll be notified once confirmed.\nBooking ID: {}...": "✅ Tempahan pemeriksaan anda telah dihantar!\n\nPerkhidmatan: {}\nTarikh: {}\nMasa: {}\nTempoh: {} minit\n\nTempahan menunggu kelulusan. Anda akan dimaklumkan sekali disahkan.\nID Tempahan: {}...",
    "Error saving checkup booking. Please try again.": "Ralat menyimpan tempahan pemeriksaan. Sila cuba lagi.",
    "Invalid input. Please use the buttons provided.": "Input tidak sah. Sila gunakan butang yang disediakan.",
    "Please describe your symptoms or health concerns:": "Sila huraikan simptom atau kebimbangan kesihatan anda:",
    "What would you like to do next?": "Apa yang anda ingin lakukan seterusnya?",
    "Select a profile to view or manage{}:": "Pilih profil untuk lihat atau urus{}:",
    "What would you like to view?": "Apa yang anda ingin lihat?",
    "Select a visit to view documents{}:": "Pilih lawatan untuk lihat dokumen{}:",
    "Select a document to download:": "Pilih dokumen untuk muat turun:",
    "Select race:": "Pilih bangsa:",
    "Select religion:": "Pilih agama:",
    "Select blood type:": "Pilih jenis darah:",
    "Continue with profile removal?": "Teruskan dengan pembuangan profil?",
    "Select a profile to remove:": "Pilih profil untuk buang:",
    "Edit Profiles Menu:": "Menu Edit Profil:",
    "Select booking type:": "Pilih jenis tempahan:",
    "Select a booking to manage or reschedule from {} category:": "Pilih tempahan untuk urus atau jadual semula dari kategori {}:",
    "Selected: {}": "Dipilih: {}",
    "Selected: {}\n\nDoctor has requested to reschedule this appointment.": "Dipilih: {}\n\nDoktor telah minta untuk jadual semula temujanji ini.",
    "Selected: {}\n\nAmbulance bookings cannot be modified via WhatsApp. Please contact the ambulance service directly for any changes.": "Dipilih: {}\n\nTempahan ambulans tidak boleh diubah melalui WhatsApp. Sila hubungi perkhidmatan ambulans secara langsung untuk sebarang perubahan.",
    "Selected date: {}. Confirm?": "Tarikh dipilih: {}. Sahkan?",
    "Selected time: {}\n\nConfirm this time slot?": "Masa dipilih: {}\n\nSahkan slot masa ini?",
    "Confirm reschedule:{} \n\nOriginal Booking:\n• Type: {}\n• Date: {}\n• Time: {}\n\nNew Booking:\n• Doctor: {}\n• Date: {}\n• Time: {}\n• Duration: {} min": "Sahkan jadual semula:{} \n\nTempahan Asal:\n• Jenis: {}\n• Tarikh: {}\n• Masa: {}\n\nTempahan Baru:\n• Doktor: {}\n• Tarikh: {}\n• Masa: {}\n• Tempoh: {} min",
    "MC, Invoice, Referral letter, Report": "MC, Invois, Surat rujukan, Laporan",
    "Returning to main menu.": "Kembali ke menu utama.",
    "Continuing with your previous action.": "Meneruskan tindakan sebelumnya.",
    "Could not restore previous action. Returning to main menu.": "Tidak dapat pulihkan tindakan sebelumnya. Kembali ke menu utama.",
    "Error registering user. Please try again.": "Ralat mendaftar pengguna. Sila cuba lagi.",
    "Please use the menu buttons provided for selection.": "Sila gunakan butang menu yang disediakan untuk pilihan.",
    "An error occurred while setting up your booking. Please try again.": "Ralat berlaku semasa menyediakan tempahan anda. Sila cuba lagi.",
    "Clinic information not found. Please try again.": "Maklumat klinik tidak ditemui. Sila cuba lagi.",
    "Error retrieving clinic information. Please try again.": "Ralat mendapatkan maklumat klinik. Sila cuba lagi.",
    "No clinic found with that keyword. Please try a different search.": "Tiada klinik ditemui dengan kata kunci itu. Sila cuba carian lain.",
    "Error setting language. Please try again.": "Ralat menetapkan bahasa. Sila cuba lagi.",
    "Error storing temp_data:": "Ralat menyimpan temp_data:",
    "Invalid input. Returning to main menu.": "Input tidak sah. Kembali ke menu utama.",
    "An error occurred. Please try again.": "Ralat berlaku. Sila cuba lagi.",
    "Please select an option from the menu.": "Sila pilih pilihan dari menu.",
    "Language set to {selected_language}.": "Bahasa ditetapkan kepada {selected_language}.",
    "Select a service type:": "Pilih jenis perkhidmatan:",
    "Please select a clinic:": "Sila pilih klinik:",
    "Please select a {category} service:": "Sila pilih perkhidmatan {category}:",
    "Please use the menu below to select an option:": "Sila gunakan menu di bawah untuk pilih pilihan:",
    "SELECT DOCTOR\n\nWhich doctor would you like to book with?": "PILIH DOKTOR\n\nDoktor mana yang anda ingin tempah?",
    "SELECT TIME\n\nChoose your preferred time slot:": "PILIH MASA\n\nPilih slot masa pilihan anda:",
    "Location received. However, location sharing is not expected in this context. Please use the menu buttons provided for selection.": "Lokasi diterima. Namun, perkongsian lokasi tidak dijangka dalam konteks ini. Sila gunakan butang menu yang disediakan untuk pilihan.",
    "Error processing location. Please try again.": "Ralat memproses lokasi. Sila cuba lagi.",
    "File received. However, file upload is not expected in this context. Please use the menu buttons provided for selection.": "Fail diterima. Namun, muat naik fail tidak dijangka dalam konteks ini. Sila gunakan butang menu yang disediakan untuk pilihan.",
    "Error processing file. Please try again.": "Ralat memproses fail. Sila cuba lagi.",
    "Error displaying the booking menu. Please try again.": "Ralat memaparkan menu tempahan. Sila cuba lagi.",
    "Unable to load services. Please try again.": "Tidak dapat memuatkan perkhidmatan. Sila cuba lagi.",
    "Unable to load clinics. Please try again.": "Tidak dapat memuatkan klinik. Sila cuba lagi.",
    "Invalid selection. Please try again.": "Pilihan tidak sah. Sila cuba lagi.",
    "Invalid input. Returning to main menu.": "Input tidak sah. Kembali ke menu utama.",
    "Invalid button selection. Please try again.": "Pilihan butang tidak sah. Sila cuba lagi.",
    "{service_name}\n\n{service_description} are coming soon!\n\nWe're working to bring you the best {service_description}. Please check back later or contact our hotline for more information:\n📞 {hotline}": "{service_name}\n\n{service_description} akan datang tidak lama lagi!\n\nKami sedang berusaha membawakan anda {service_description} terbaik. Sila semak kemudian atau hubungi talian panas kami untuk maklumat lanjut:\n📞 {hotline}",
    "Your checkup booking is confirmed on {date} at {time}.": "Tempahan pemeriksaan anda disahkan pada {date} jam {time}.",
    "Your consultation booking is confirmed on {date} at {time}.": "Tempahan konsultasi anda disahkan pada {date} jam {time}.",
    "Your vaccination booking for {vaccine_type} is confirmed on {date} at {time}.": "Tempahan vaksinasi anda untuk {vaccine_type} disahkan pada {date} jam {time}.",
    "Your TCM {booking_type} booking is confirmed on {date} at {time}.": "Tempahan TCM {booking_type} anda disahkan pada {date} jam {time}.",
    "Reminder: Your {details} is in {time_desc}": "Peringatan: {details} anda dalam {time_desc}",
    " - {remark}": " - {remark}",
    "Custom reminder: Your {details} is in {reminder_duration} hours": "Peringatan tersuai: {details} anda dalam {reminder_duration} jam",
    "Reminder: Your TCM {booking_type} is in {time_desc}": "Peringatan: TCM {booking_type} anda dalam {time_desc}",
    "Custom reminder: Your TCM {booking_type} is in {reminder_duration} hours": "Peringatan tersuai: TCM {booking_type} anda dalam {reminder_duration} jam",
    "Reminder: Your {service_type} for {patient_name} is scheduled tomorrow at {time}.": "Peringatan: {service_type} anda untuk {patient_name} dijadualkan esok jam {time}.",
    "No new notifications found.": "Tiada pemberitahuan baru ditemui.",
    "Error: User not found.": "Ralat: Pengguna tidak ditemui.",
    "N/A": "Tidak Berkenaan",
    "Error displaying notifications. Please try again.": "Ralat memaparkan pemberitahuan. Sila cuba lagi.",
    "Thank you for acknowledging!": "Terima kasih kerana mengakui!",
    "{len(message_parts)} notification(s) displayed!": "{len(message_parts)} pemberitahuan dipaparkan!",
    "Appointment": "Temujanji",
    "Vaccination": "Vaksinasi",
    "TCM Appointment": "Temujanji TCM",
    "consultation": "konsultasi",
    "Patient": "Pesakit",
    "1 week": "1 minggu",
    "1 day": "1 hari",
    "{hours} hours": "{hours} jam",
    "Home to Home Transfer": "Pindahan Rumah ke Rumah",
    "Home to Hospital Transfer": "Pindahan Rumah ke Hospital",
    "Hospital to Home Discharge": "Pindahan Hospital ke Rumah",
    "Hospital to Hospital Transfer": "Pindahan Hospital ke Hospital",
    "Please describe your symptoms:": "Sila huraikan simptom anda:",
    "Do you have any additional remarks about your symptoms?": "Ada sebarang catatan tambahan tentang simptom anda?",
    "Please enter your additional remarks:": "Sila masukkan catatan tambahan anda:",
    "✅ Your GP consultation booking has been submitted!\n\nDoctor: {doctor}\nDate: {date}\nTime: {time}\nDuration: {duration} minutes\nSymptoms: {symptoms}...\n\nBooking is pending approval. You'll be notified once confirmed.\nBooking ID: {booking_id}...": "✅ Tempahan konsultasi GP anda telah dihantar!\n\nDoktor: {doctor}\nTarikh: {date}\nMasa: {time}\nTempoh: {duration} minit\nSimptom: {symptoms}...\n\nTempahan menunggu kelulusan. Anda akan dimaklumkan sekali disahkan.\nID Tempahan: {booking_id}...",
    "Error saving booking. Please try again or contact clinic for assistance.": "Ralat menyimpan tempahan. Sila cuba lagi atau hubungi klinik untuk bantuan.",
    "Clinic not selected. Please contact support.": "Klinik tidak dipilih. Sila hubungi sokongan.",
    "Select AM or PM for {}:": "Pilih AM atau PM untuk {}:",
    "Select an hour range for {}:": "Pilih julat jam untuk {}:",
    "Confirm your TCM booking:": "Sahkan tempahan TCM anda:",
    "• Service: {}": "• Perkhidmatan: {}",
    "• Method: {}": "• Kaedah: {}",
    "• Doctor: {}": "• Doktor: {}",
    "• Doctor: Assigned by Clinic": "• Doktor: Ditugaskan oleh Klinik",
    "• Date: {}": "• Tarikh: {}",
    "• Time: {}": "• Masa: {}",
    "• Duration: {} min": "• Tempoh: {} min",
    "• Details: {}": "• Butiran: {}",
    "• Address: {}": "• Alamat: {}",
    "• Reminder: {}": "• Peringatan: {}",
    "Due to the appointment method allowing for doctor flexibility, the doctor will contact you by 10 AM on the selected date. Note: Your booking may be rescheduled, and you may need to go to 'upcoming bookings' to accept or decline the suggested time after notification has been sent to you.": "Oleh kerana kaedah temujanji membenarkan fleksibiliti doktor, doktor akan menghubungi anda sebelum 10 pagi pada tarikh yang dipilih. Nota: Tempahan anda mungkin dijadual semula, dan anda mungkin perlu pergi ke 'tempahan akan datang' untuk terima atau tolak masa yang dicadangkan selepas pemberitahuan dihantar kepada anda.",
    "An error occurred while confirming the booking. Please try again.": "Ralat berlaku semasa mengesahkan tempahan. Sila cuba lagi.",
    "The TCM booking is not placed": "Tempahan TCM tidak ditempatkan",
    "Doctor selection is not enabled for this clinic. Please contact the clinic directly for doctor changes.": "Pemilihan doktor tidak diaktifkan untuk klinik ini. Sila hubungi klinik secara langsung untuk pertukaran doktor.",
    "Please share your current location or enter your address manually:": "Sila kongsikan lokasi semasa anda atau masukkan alamat secara manual:",
    "Unable to retrieve address from location. Please enter manually:": "Tidak dapat dapatkan alamat dari lokasi. Sila masukkan secara manual:",
    "Is this address correct?\n{}": "Adakah alamat ini betul?\n{}",
    "Please enter a valid address:": "Sila masukkan alamat yang sah:",
    "Please edit the address and send it back:": "Sila edit alamat dan hantar balik:",
    "Do you have any remarks for {} ({} min)?": "Ada sebarang catatan untuk {} ({} min)?",
    "Clinic not found. Please select another clinic.": "Klinik tidak ditemui. Sila pilih klinik lain.",
    "Now please select a treatment category:": "Sekarang sila pilih kategori rawatan:",
    "Unable to load clinic information. Please try again.": "Tidak dapat memuatkan maklumat klinik. Sila cuba lagi.",
    "Unable to load TCM services. Please try again.": "Tidak dapat memuatkan perkhidmatan TCM. Sila cuba lagi.",
    "No {} clinics available at the moment. Please select another service type.": "Tiada klinik {} tersedia buat masa ini. Sila pilih jenis perkhidmatan lain.",
    "Unable to load TCM clinics. Please try again.": "Tidak dapat memuatkan klinik TCM. Sila cuba lagi.",
    "No categories available for this clinic. Please select another clinic.": "Tiada kategori tersedia untuk klinik ini. Sila pilih klinik lain.",
    "Unable to load categories. Please try again.": "Tidak dapat memuatkan kategori. Sila cuba lagi.",
    "Error: Clinic or category not selected. Please start over.": "Ralat: Klinik atau kategori tidak dipilih. Sila mulakan semula.",
    "No services available in this category. Please select another category.": "Tiada perkhidmatan tersedia dalam kategori ini. Sila pilih kategori lain.",
    "Unable to load services. Please try again.": "Tidak dapat memuatkan perkhidmatan. Sila cuba lagi.",
    "Please select the type of TCM service you need:": "Sila pilih jenis perkhidmatan TCM yang anda perlukan:",
    "Please select a {} clinic:": "Sila pilih klinik {}:",
    "Please select a treatment category:": "Sila pilih kategori rawatan:",
    "Please select a treatment service:": "Sila pilih perkhidmatan rawatan:",
    "Patient information not found. Please select a patient first.": "Maklumat pesakit tidak ditemui. Sila pilih pesakit dahulu.",
    "No details available": "Tiada butiran tersedia",
    "Quantity:": "Kuantiti:",
    "Dosage:": "Dos:",
    "Method:": "Kaedah:",
    "Take:": "Ambil:",
    "before meal": "sebelum makan",
    "after meal": "selepas makan",
    "with meal": "dengan makanan",
    "on empty stomach": "semasa perut kosong",
    "Purpose:": "Tujuan:",
    "Note:": "Catatan:",
    "Duration:": "Tempoh:",
    "Frequency:": "Kekerapan:",
    "No medications or items found for any visit.": "Tiada ubat atau item ditemui untuk sebarang lawatan.",
    "💊 **Medications:**": "💊 **Ubat-ubatan:**",
    "🩺 **Equipment:**": "🩺 **Peralatan:**",
    "🛒 **Products:**": "🛒 **Produk:**",
    "📞 **Contact your clinic if you have any questions.**": "📞 **Hubungi klinik anda jika ada sebarang soalan.**",
    "Error loading all medications. Please try again.": "Ralat memuatkan semua ubat. Sila cuba lagi.",
    "Error loading profiles. Please try again.": "Ralat memuatkan profil. Sila cuba lagi.",
    "Patient not found.": "Pesakit tidak ditemui.",
    "Account locked. Please contact contact@anyhealth.asia to unlock.": "Akaun dikunci. Sila hubungi contact@anyhealth.asia untuk buka kunci.",
    "Error in verification. Please try again.": "Ralat dalam pengesahan. Sila cuba lagi.",
    "Verification failed. Please try again.": "Pengesahan gagal. Sila cuba lagi.",
    "No visits found for {}.": "Tiada lawatan ditemui untuk {}.",
    "Error loading disease information. Please try again.": "Ralat memuatkan maklumat penyakit. Sila cuba lagi.",
    "No disease diagnoses found for this patient.": "Tiada diagnosis penyakit ditemui untuk pesakit ini.",
    "Diagnosis:": "Diagnosis:",
    "Suspected Disease:": "Penyakit Disyaki:",
    "📞 Contact your clinic for more information.": "📞 Hubungi klinik anda untuk maklumat lanjut.",
    "Medication & Routine module is currently unavailable. Please try again later.": "Modul Ubat & Rutin tidak tersedia buat masa ini. Sila cuba lagi kemudian.",
    "Error loading medication details. Please try again.": "Ralat memuatkan butiran ubat. Sila cuba lagi.",
    "No visiting history found for {}.": "Tiada sejarah lawatan ditemui untuk {}.",
    "Error loading visiting history. Please try again.": "Ralat memuatkan sejarah lawatan. Sila cuba lagi.",
    "Error displaying visits. Please try again.": "Ralat memaparkan lawatan. Sila cuba lagi.",
    "No documents available for this visit.": "Tiada dokumen tersedia untuk lawatan ini.",
    "Error loading documents. Please try again.": "Ralat memuatkan dokumen. Sila cuba lagi.",
    "Medical Certificate": "Sijil Perubatan",
    "Invoice": "Invois",
    "Referral Letter": "Surat Rujukan",
    "Consultation Report": "Laporan Konsultasi",
    "Document not available. Please select another document.": "Dokumen tidak tersedia. Sila pilih dokumen lain.",
    "Error sending document. Please try again.": "Ralat menghantar dokumen. Sila cuba lagi.",
    "IC must be 12 digits": "IC mesti 12 digit",
    "Please enter the IC number (12 digits):\nFormat: XXXXXX-XX-XXXX or XXXXXX XX XXXX or XXXXXXXXXXXX\n\nNote: Only Malaysian IC accepted, no passport.": "Sila masukkan nombor IC (12 digit):\nFormat: XXXXXX-XX-XXXX atau XXXXXX XX XXXX atau XXXXXXXXXXXX\n\nNota: Hanya IC Malaysia diterima, tiada pasport.",
    "Invalid IC: {}. Please enter a valid 12-digit Malaysian IC:": "IC tidak sah: {}. Sila masukkan IC Malaysia 12 digit yang sah:",
    "❌ This IC has reached maximum detachment attempts.\nPlease email contact@anyhealth.asia or visit partner clinics.": "❌ IC ini telah capai percubaan detach maksimum.\nSila email contact@anyhealth.asia atau lawati klinik rakan kongsi.",
    "✅ This IC is already registered to your account.": "✅ IC ini sudah didaftarkan ke akaun anda.",
    "Please enter the full name:": "Sila masukkan nama penuh:",
    "Invalid name. Please enter a valid name (minimum 2 characters):": "Nama tidak sah. Sila masukkan nama yang sah (minimum 2 aksara):",
    "Please specify the race:": "Sila nyatakan bangsa:",
    "Please specify the religion:": "Sila nyatakan agama:",
    "Error: WhatsApp user not found. Please try again.": "Ralat: Pengguna WhatsApp tidak ditemui. Sila cuba lagi.",
    "Error creating profile: {}": "Ralat mencipta profil: {}",
    "No profiles found to remove.": "Tiada profil ditemui untuk dibuang.",
    "Error loading profiles for removal. Please try again.": "Ralat memuatkan profil untuk dibuang. Sila cuba lagi.",
    "⚠️ WARNING: Removing a profile will erase all previous data.\nTo undo this action, you will need to visit our nearest partner clinics.\n\nAre you sure you want to continue?": "⚠️ AMARAN: Membuang profil akan padam semua data sebelumnya.\nUntuk batal tindakan ini, anda perlu lawati klinik rakan kongsi terdekat.\n\nAnda pasti ingin teruskan?",
    "Profile removal cancelled.": "Pembuangan profil dibatalkan.",
    "Profile removed successfully.": "Profil berjaya dibuang.",
    "Error removing profile. Please try again.": "Ralat membuang profil. Sila cuba lagi.",
    "⚠️ *CHANGED NUMBERS*": "⚠️ *NOMBOR DITUKAR*",
    "Error starting process. Please try again.": "Ralat memulakan proses. Sila cuba lagi.",
    "⚠️ For security, please retype your full phone number starting with 60... (e.g., 601223456789):": "⚠️ Untuk keselamatan, sila taip semula nombor telefon penuh anda bermula dengan 60... (cth: 601223456789):",
    "Too many failed attempts. Reset process cancelled.": "Terlalu banyak percubaan gagal. Proses reset dibatalkan.",
    "User not found.": "Pengguna tidak ditemui.",
    "Phone number does not match. {} attempt(s) left.\nPlease retype your full phone number starting with 60...:": "Nombor telefon tidak sepadan. {} percubaan tinggal.\nSila taip semula nombor telefon penuh anda bermula dengan 60...:",
    "Phone verification failed. Reset process cancelled.": "Pengesahan telefon gagal. Proses reset dibatalkan.",
    "Error verifying phone number. Please try again.": "Ralat mengesahkan nombor telefon. Sila cuba lagi.",
    "✅ All profiles have been reset successfully!\n\nYour WhatsApp account has been refreshed with no profiles.": "✅ Semua profil telah berjaya direset!\n\nAkaun WhatsApp anda telah disegarkan tanpa profil.",
    "Error during reset process. Please try again.": "Ralat semasa proses reset. Sila cuba lagi.",
    "Error starting verification. Please try again.": "Ralat memulakan pengesahan. Sila cuba lagi.",
    "Step 1/4: Enter the full name:": "Langkah 1/4: Masukkan nama penuh:",
    "Error verifying name. Please try again.": "Ralat mengesahkan nama. Sila cuba lagi.",
    "Step 2/4: Enter the race (e.g., Malay, Chinese, Indian, etc.):": "Langkah 2/4: Masukkan bangsa (cth: Melayu, Cina, India, dll.):",
    "Error verifying race. Please try again.": "Ralat mengesahkan bangsa. Sila cuba lagi.",
    "Step 3/4: Enter the religion:": "Langkah 3/4: Masukkan agama:",
    "Error verifying religion. Please try again.": "Ralat mengesahkan agama. Sila cuba lagi.",
    "Step 4/4: Enter the blood type (e.g., A+, B-, O+):": "Langkah 4/4: Masukkan jenis darah (cth: A+, B-, O+):",
    "✅ Profile detached successfully!\n\nThe profile is now available for reattachment.\nTo add it to your account, please email contact@anyhealth.asia or visit partner clinics.": "✅ Profil berjaya didetach!\n\nProfil kini tersedia untuk reattachment.\nUntuk tambah ke akaun anda, sila email contact@anyhealth.asia atau lawati klinik rakan kongsi.",
    "❌ Verification failed 3 times.\nProfile is now locked.\nPlease email contact@anyhealth.asia or visit partner clinics.": "❌ Pengesahan gagal 3 kali.\nProfil kini dikunci.\nSila email contact@anyhealth.asia atau lawati klinik rakan kongsi.",
    "❌ Verification failed.\nYou have {} attempt(s) left.\nPlease try again or visit partner clinics.": "❌ Pengesahan gagal.\nAnda ada {} percubaan tinggal.\nSila cuba lagi atau lawati klinik rakan kongsi.",
    "Error completing verification. Please try again.": "Ralat melengkapkan pengesahan. Sila cuba lagi.",
    "❌ IC not found in our system.": "❌ IC tidak ditemui dalam sistem kami.",
    "✅ This IC is not attached to any WhatsApp account.\nYou can add it directly.": "✅ IC ini tidak dilampirkan ke sebarang akaun WhatsApp.\nAnda boleh tambah secara langsung.",
    "✅ This IC is already attached to your current account.\nNo need to detach.": "✅ IC ini sudah dilampirkan ke akaun semasa anda.\nTidak perlu detach.",
    "❌ This IC has reached maximum detachment attempts (3).\nPlease email contact@anyhealth.asia or visit partner clinics.": "❌ IC ini telah capai percubaan detach maksimum (3).\nSila email contact@anyhealth.asia atau lawati klinik rakan kongsi.",
    "Detachment cancelled.": "Detachment dibatalkan.",
    "⚠️ *RESET ACCOUNT WARNING*": "⚠️ *AMARAN RESET AKAUN*",
    "⚠️ *DETACH FROM OLD NUMBER*": "⚠️ *DETACH DARI NOMBOR LAMA*",
    "Please enter the 12-digit IC of the profile to detach:": "Sila masukkan 12 digit IC profil untuk detach:",
    "An error occurred in edit module. Please try again.": "Ralat berlaku dalam modul edit. Sila cuba lagi.",
    "User not found. Please ensure your number is registered.": "Pengguna tidak ditemui. Sila pastikan nombor anda didaftarkan.",
    "Error fetching user information. Please try again.": "Ralat mengambil maklumat pengguna. Sila cuba lagi.",
    "Unknown": "Tidak Diketahui",
    "Unknown Clinic": "Klinik Tidak Diketahui",
    "Unknown TCM Doctor": "Doktor TCM Tidak Diketahui",
    "Unknown TCM Clinic": "Klinik TCM Tidak Diketahui",
    "Unknown Provider": "Pembekal Tidak Diketahui",
    "You have no upcoming bookings.": "Anda tiada tempahan akan datang.",
    "No bookings found in any category.": "Tiada tempahan ditemui dalam sebarang kategori.",
    "Invalid booking selection. Please try again.": "Pilihan tempahan tidak sah. Sila cuba lagi.",
    "⚠️ REPEATED VISIT CANCELLATION\n\nThis is part of a repeated visit series. Do you want to cancel just this booking or all future repeated bookings?": "⚠️ PEMBATALAN LAWATAN BERULANG\n\nIni sebahagian dari siri lawatan berulang. Anda ingin batalkan hanya tempahan ini atau semua tempahan berulang akan datang?",
    "❌ CANCELLATION FAILED\n\nBooking not found. It may have already been cancelled.": "❌ PEMBATALAN GAGAL\n\nTempahan tidak ditemui. Mungkin sudah dibatalkan.",
    "✅ BOOKING CANCELLED\n\nYour booking has been successfully cancelled.": "✅ TEMPAHAN DIBATALKAN\n\nTempahan anda telah berjaya dibatalkan.",
    "❌ ERROR\n\nError cancelling booking. Please try again.": "❌ RALAT\n\nRalat membatalkan tempahan. Sila cuba lagi.",
    "❌ ERROR\n\nReschedule request not found or has invalid data. Please try again.": "❌ RALAT\n\nPermintaan jadual semula tidak ditemui atau ada data tidak sah. Sila cuba lagi.",
    "Invalid booking type for reschedule request.": "Jenis tempahan tidak sah untuk permintaan jadual semula.",
    "✅ ACCEPTED RESCHEDULE\n\nYou have accepted the reschedule. Your {} is now confirmed on {} at {}.": "✅ JADUAL SEMULA DITERIMA\n\nAnda telah terima jadual semula. {} anda kini disahkan pada {} jam {}.",
    "✅ DECLINED RESCHEDULE\n\nYou have declined the reschedule request.": "✅ JADUAL SEMULA DITOLAK\n\nAnda telah tolak permintaan jadual semula.",
    "❌ ERROR\n\nError declining reschedule. Please try again.": "❌ RALAT\n\nRalat menolak jadual semula. Sila cuba lagi.",
    "✅ TCM RESCHEDULE ACCEPTED\n\nYou have accepted the reschedule. Your TCM {} is now confirmed on {} at {} with Dr. {}.": "✅ JADUAL SEMULA TCM DITERIMA\n\nAnda telah terima jadual semula. TCM {} anda kini disahkan pada {} jam {} dengan Dr. {}.",
    "❌ ERROR\n\nError accepting TCM reschedule. Please try again.": "❌ RALAT\n\nRalat menerima jadual semula TCM. Sila cuba lagi.",
    "TCM Doctor": "Doktor TCM",
    "✅ TCM RESCHEDULE DECLINED\n\nYou have declined the reschedule request. Your TCM {} remains confirmed on {} at {} with Dr. {}.": "✅ JADUAL SEMULA TCM DITOLAK\n\nAnda telah tolak permintaan jadual semula. TCM {} anda kekal disahkan pada {} jam {} dengan Dr. {}.",
    "✅ TCM RESCHEDULE DECLINED\n\nYou have declined the reschedule request.": "✅ JADUAL SEMULA TCM DITOLAK\n\nAnda telah tolak permintaan jadual semula.",
    "❌ ERROR\n\nError declining TCM reschedule. Please try again.": "❌ RALAT\n\nRalat menolak jadual semula TCM. Sila cuba lagi.",
    "❌ ERROR\n\nError processing cancellation. Please try again.": "❌ RALAT\n\nRalat memproses pembatalan. Sila cuba lagi.",
    "✅ ALL REPEATED BOOKINGS CANCELLED\n\nAll repeated bookings in this series have been cancelled.": "✅ SEMUA TEMPAHAN BERULANG DIBATALKAN\n\nSemua tempahan berulang dalam siri ini telah dibatalkan.",
    "❌ ERROR\n\nError cancelling repeated bookings. Please try again.": "❌ RALAT\n\nRalat membatalkan tempahan berulang. Sila cuba lagi.",
    "This is part of a repeated visit series. Only this specific appointment will be rescheduled. Continue?": "Ini sebahagian dari siri lawatan berulang. Hanya temujanji khusus ini akan dijadual semula. Teruskan?",
    "Error processing reschedule confirmation. Please try again.": "Ralat memproses pengesahan jadual semula. Sila cuba lagi.",
    "❌ RESCHEDULE CANCELLED\n\nYour booking remains unchanged.": "❌ JADUAL SEMULA DIBATALKAN\n\nTempahan anda kekal tidak berubah.",
    "Error confirming reschedule. Please try again.": "Ralat mengesahkan jadual semula. Sila cuba lagi.",
    "❌ RESCHEDULE FAILED\n\nAn error occurred while processing your reschedule request. Please try again or contact support.": "❌ JADUAL SEMULA GAGAL\n\nRalat berlaku semasa memproses permintaan jadual semula anda. Sila cuba lagi atau hubungi sokongan.",
    "❌ ERROR\n\nAn unexpected error occurred. Please try again.": "❌ RALAT\n\nRalat tidak dijangka berlaku. Sila cuba lagi.",
    "❌ SESSION EXPIRED\n\nPlease start the reschedule process again.": "❌ SESI TAMAT\n\nSila mulakan proses jadual semula semula.",
    "Error fetching default doctor for clinic {}": "Ralat mengambil doktor lalai untuk klinik {}",
    "❌ UNABLE TO COMPLETE\n\nUnable to complete reschedule. No doctor information available. Please contact support.": "❌ TIDAK DAPAT LENGKAPKAN\n\nTidak dapat lengkapkan jadual semula. Tiada maklumat doktor tersedia. Sila hubungi sokongan.",
    "✅ RESCHEDULE SUCCESSFUL!{}\n\n{} rescheduled to {} at {} with Dr. {}.\n\nStatus: PENDING CONFIRMATION": "✅ JADUAL SEMULA BERJAYA!{}\n\n{} dijadual semula ke {} jam {} dengan Dr. {}.\n\nStatus: MENUNGGU PENGESAHAN",
    "❌ DATABASE ERROR\n\nError saving reschedule. Please try again.": "❌ RALAT PANGKALAN DATA\n\nRalat menyimpan jadual semula. Sila cuba lagi.",
    "Error fetching TCM doctor name: {}": "Ralat mengambil nama doktor TCM: {}",
    "✅ TCM RESCHEDULE SUCCESSFUL!{}\n\nTCM {} rescheduled to {} at {} with Dr. {}.\n\nStatus: PENDING CONFIRMATION": "✅ JADUAL SEMULA TCM BERJAYA!{}\n\nTCM {} dijadual semula ke {} jam {} dengan Dr. {}.\n\nStatus: MENUNGGU PENGESAHAN",
    "Error fetching updated TCM booking: {}": "Ralat mengambil tempahan TCM dikemas kini: {}",
    "✅ TCM RESCHEDULE SUCCESSFUL!\n\nYour TCM appointment has been rescheduled.\n\nStatus: PENDING CONFIRMATION": "✅ JADUAL SEMULA TCM BERJAYA!\n\nTemujanji TCM anda telah dijadual semula.\n\nStatus: MENUNGGU PENGESAHAN",
    "❌ TCM RESCHEDULE FAILED\n\nError rescheduling TCM appointment. Please try again.": "❌ JADUAL SEMULA TCM GAGAL\n\nRalat menjadual semula temujanji TCM. Sila cuba lagi.",
    "❌ RESCHEDULE CANCELLED\n\nYour TCM booking reschedule has been cancelled.": "❌ JADUAL SEMULA DIBATALKAN\n\nJadual semula tempahan TCM anda telah dibatalkan.",
    "❌ ERROR\n\nError cancelling TCM reschedule. Please try again.": "❌ RALAT\n\nRalat membatalkan jadual semula TCM. Sila cuba lagi.",
    "Returning to main menu.": "Kembali ke menu utama.",
    "Ambulance bookings cannot be rescheduled or cancelled via WhatsApp. Please contact the ambulance service directly for any changes.": "Tempahan ambulans tidak boleh dijadual semula atau dibatalkan melalui WhatsApp. Sila hubungi perkhidmatan ambulans secara langsung untuk sebarang perubahan.",
    "Invalid selection. Please try again.": "Pilihan tidak sah. Sila cuba lagi.",
    "Error processing booking type selection. Please try again.": "Ralat memproses pemilihan jenis tempahan. Sila cuba lagi.",
    "An unexpected error occurred while fetching upcoming bookings. Please try again.": "Ralat tidak dijangka berlaku semasa mengambil tempahan akan datang. Sila cuba lagi.",
    "❌ SYSTEM ERROR\n\nAn error occurred in the booking system. Please try again.": "❌ RALAT SISTEM\n\nRalat berlaku dalam sistem tempahan. Sila cuba lagi.",
    "No bookings found in the {} category.": "Tiada tempahan ditemui dalam kategori {}.",
    "Error processing booking selection. Please try again.": "Ralat memproses pemilihan tempahan. Sila cuba lagi.",
    "Error processing action. Please try again.": "Ralat memproses tindakan. Sila cuba lagi.",
    "Doctor": "Doktor",
    "Any Doctor": "Mana-mana Doktor",
    "Would you like to book an appointment at this clinic?": "Adakah anda ingin tempah temujanji di klinik ini?",

    # BUTTON
    "Menu": "Menu",
    "Booking Options": "Pilihan Tempahan",
    "✅ Yes": "✅ Ya",
    "❌ No": "❌ Tidak",
    "Select Service": "Pilih Perkhidmatan",
    "Noted": "Dituhu",
    "Select Language": "Pilih Bahasa",
    "✅ Yes, Book": "✅ Ya, Tempah",
    "❌ No, Just Browsing": "❌ Tidak, Hanya Melihat",
    "Back": "Kembali",
    "More Doctors": "Lebih Banyak Doktor",
    "Select Option": "Pilih Pilihan",
    "Yes": "Ya",
    "No": "Tidak",
    "📍 Share Location": "📍 Kongsi Lokasi",
    "📝 Type Address": "📝 Taip Alamat",
    "✅ Yes, Correct": "✅ Ya, Betul",
    "✏️ Edit Address": "✏️ Edit Alamat",
    "Next": "Seterusnya",
    "Skip": "Langkau",
    "Add Remarks": "Tambah Catatan",
    "Today": "Hari Ini",
    "Tomorrow": "Esok",
    "Others": "Tarikh Lain",
    "AM (12am - 11:45am)": "AM (12am - 11:45am)",
    "PM (12pm - 11:45pm)": "PM (12pm - 11:45pm)",
    "Select Time Slot": "Pilih Slot Masa",
    "Select Time": "Pilih Masa",
    "❌ No, Different": "❌ Tidak, Berbeza",
    "Choose Doctor": "Pilih Doktor",
    "Any Doctor": "Mana-mana Doktor",
    "Choose Date": "Pilih Tarikh",
    "📅 Future Date": "📅 Tarikh Lain",
    "AM": "AM",
    "PM": "PM",
    "Choose Hour": "Pilih Jam",
    "Choose Slot": "Pilih Slot",
    "Confirm": "Sahkan",
    "Edit": "Edit",
    "Cancel": "Batal",
    "Edit Option": "Pilihan Edit",
    "Change Time": "Tukar Masa",
    "Change Date": "Tukar Tarikh",
    "Change Doctor": "Tukar Doktor",
    "Change Service": "Tukar Perkhidmatan",
    "Try Again": "Cuba Lagi",
    "Help Me Choose": "Bantu Saya Pilih",
    "Find Another": "Cari Lain",
    "Try Another Time": "Cuba Masa Lain",
    "Choose Method": "Pilih Kaedah",
    "🔙 Back to Type Selection": "🔙 Kembali ke Pilihan Jenis",
    "🔙 Back to Clinics": "🔙 Kembali ke Senarai Klinik",
    "🔙 Back to Categories": "🔙 Kembali ke Kategori",
    "Select Type": "Pilih Jenis",
    "Chiropractic": "Kiropraktik",
    "Physiotherapy": "Fisioterapi",
    "🔙 Back to Services": "🔙 Kembali ke Senarai Perkhidmatan",
    "Select Clinic": "Pilih Klinik",
    "Select Category": "Pilih Kategori",
    "Select Service": "Pilih Perkhidmatan",
    "🔙 Back to Options": "🔙 Kembali ke Pilihan",
    "Manage Profiles": "Urus Profil",
    "Select Visit": "Pilih Lawatan",
    "📄 Another Document": "📄 Dokumen Lain",
    "🔙 Back to Edit Menu": "🔙 Kembali ke Menu Edit",
    "🔙 Back to Religion": "🔙 Kembali ke Agama",
    "Select Profile": "Pilih Profil",
    "➕ Add Profile": "➕ Tambah Profil",
    "➖ Remove Profile": "➖ Buang Profil",
    "🔙 Back to Profiles": "🔙 Kembali ke Senarai Profil",
    "Yes, detach": "Ya, detach",
    "No, cancel": "Tidak, batal",
    "Yes, reset": "Ya, reset",
    "No, cancel": "Tidak, batal",
    "Select Type": "Pilih Jenis",
    "Choose Booking": "Pilih Tempahan",
    "Accept": "Terima",
    "Decline": "Tolak",
    "Back to Home": "Kembali ke Laman Utama",
    "Reschedule": "Jadual Semula",
    "Cancel Booking": "Batalkan Tempahan",
    "Choose Another": "Pilih Lain",
    "Confirm Time": "Sahkan Masa",
    "Back": "Kembali",
    "Reschedule One": "Jadual Semula Satu",
    "Back to actions": "Kembali ke tindakan",
    "Cancel This One Only": "Batalkan Ini Sahaja",
    "Cancel All Repeated": "Batalkan Semua Berulang",

    # FOOTER
    "Select an option to proceed": "Sila pilih pilihan untuk teruskan",
    "Choose an option below": "Sila pilih di bawah",
    "Choose a language to proceed": "Sila pilih bahasa untuk teruskan",
    "Choose a service to proceed": "Sila pilih perkhidmatan untuk teruskan",
    "Choose a clinic to proceed": "Sila pilih klinik untuk teruskan",
    "Choose a service type to proceed": "Sila pilih jenis perkhidmatan untuk teruskan",
    "Choose a category to proceed": "Sila pilih kategori untuk teruskan",

    # SECTION TITLES
    "Main Options": "Pilihan Utama",
    "Booking Services": "Perkhidmatan Tempahan",
    "Available Services": "Perkhidmatan Tersedia",
    "Languages": "Bahasa",
    "Service Booking": "Tempahan Perkhidmatan",
    "Available Clinics": "Klinik Tersedia",
    "Booking Options": "Pilihan Tempahan",
    "Your Profiles": "Profil Anda",
    "Available Options": "Pilihan Tersedia",
    "Visiting History": "Sejarah Lawatan",
    "Available Documents": "Dokumen Tersedia",
    "Available Races": "Bangsa Tersedia",
    "Available Religions": "Agama Tersedia",
    "Blood Types": "Jenis Darah",
    "Booking Categories": "Kategori Tempahan",
    "{} Bookings": "Tempahan {}",
    "Available Doctors": "Doktor Tersedia",
    "Available Dates": "Tarikh Tersedia",
    "{period} Hours": "Jam {period}",
    "{}min Slots": "Slot {}min",
    "Edit Options": "Pilihan Edit",
    "TCM Service Types": "Jenis Perkhidmatan TCM",
    "Available {} Clinics": "Klinik {} Tersedia",
    "Treatment Categories": "Kategori Rawatan",
    "Available Methods": "Kaedah Tersedia",
    "Available Services": "Perkhidmatan Tersedia",

    # LIST ROW TITLES
    "👤 Profile": "👤 Profil",
    "🏥 Service Booking": "🏥 Tempahan Perkhidmatan",
    "📅 Upcoming Booking": "📅 Tempahan Akan Datang",
    "❓ Help": "❓ Bantuan",
    "🌐 Languages": "🌐 Bahasa",
    "🔔 Notification": "🔔 Pemberitahuan",
    "📞 Clinic Enquiries": "📞 Pertanyaan Klinik",
    "👨‍⚕️ General GP Visit": "👨‍⚕️ Lawatan GP Umum",
    "🩺 Checkup & Test": "🩺 Pemeriksaan & Ujian",
    "💉 Vaccination": "💉 Vaksinasi",
    "🔙 Back to Main Menu": "🔙 Kembali ke Menu Utama",
    "🏠 → 🏥 Home to Hosp": "🏠 → 🏥 Rumah ke Hospital",
    "🏠 → 🏠 Home to Home": "🏠 → 🏠 Rumah ke Rumah",
    "🏥 → 🏠 Hosp to Home": "🏥 → 🏠 Hospital ke Rumah",
    "🏥 → 🏥 Hosp to Hosp": "🏥 → 🏥 Hospital ke Hospital",
    "English": "English",
    "Bahasa Malaysia": "Bahasa Malaysia",
    "中文": "中文",
    "தமிழ்": "தமிழ்",
    "🏥 Clinic Services": "🏥 Perkhidmatan Klinik",
    "🌿 TCM Services": "🌿 Perkhidmatan TCM",
    "🚑 Ambulance Service": "🚑 Perkhidmatan Ambulans",
    "💅 Aesthetic": "💅 Estetik",
    "🏨 Hospital": "🏨 Hospital",
    "💉 Dialysis": "💉 Dialisis",
    "👴 Elderly Care": "👴 Penjagaan Warga Emas",
    "🔙 Back to Main": "🔙 Kembali ke Utama",
    "🔙 Back to Booking": "🔙 Kembali ke Tempahan",
    "Health Screening Plan": "Pelan Saringan Kesihatan",
    "View Upcoming Bookings": "Lihat Tempahan Akan Datang",
    "📝 Edit Profiles": "📝 Edit Profil",
    "🔄 Changed Numbers": "🔄 Nombor Ditukar",
    "➡️ Next Page": "➡️ Halaman Seterusnya",
    "⬅️ Previous Page": "⬅️ Halaman Sebelumnya",
    "🔙 Back to Menu": "🔙 Kembali ke Menu",
    "⚔️ Enemy (Disease)": "⚔️ Musuh (Penyakit)",
    "💊 Med & Routine": "💊 Ubat & Rutin",
    "📄 Report": "📄 Laporan",
    "🔙 Back to Profiles": "🔙 Kembali ke Profil",
    "📄 Medical Certificate": "📄 Sijil Perubatan",
    "💰 Bill/Invoice": "💰 Bil/Invois",
    "📋 Referral Letter": "📋 Surat Rujukan",
    "📊 Consultation Report": "📊 Laporan Konsultasi",
    "Malay": "Melayu",
    "Chinese": "Cina",
    "Indian": "India",
    "Bumiputera Sabah": "Bumiputera Sabah",
    "Bumiputera Sarawak": "Bumiputera Sarawak",
    "Others": "Lain-lain",
    "Muslim": "Muslim",
    "Buddhist": "Buddha",
    "Christian": "Kristian",
    "Hindu": "Hindu",
    "Sikh": "Sikh",
    "🔄 Reset account": "🔄 Reset akaun",
    "📱 Detach from old": "📱 Detach dari lama",
    "❌ Cancel": "❌ Batal",
    "Action Required": "Tindakan Diperlukan",
    "Confirmed": "Disahkan",
    "Pending": "Dalam Proses",
    "🔙 Back": "🔙 Kembali",
    "Booking {}": "Tempahan {}",

    # LIST ROW DESCRIPTIONS
    "GP, Checkup, Vaccination, Health Screening": "GP, Pemeriksaan, Vaksinasi, Saringan Kesihatan",
    "Chiro, Physio, Rehab, Traditional Medicine": "Kiropraktik, Fisioterapi, Rehab, Perubatan Tradisional",
    "Non-emergency medical transport": "Pengangkutan perubatan bukan kecemasan",
    "Coming soon": "Akan datang",
    "Coming soon": "Akan datang",
    "Coming soon": "Akan datang",
    "Coming soon": "Akan datang",
    "View diagnosed conditions": "Lihat keadaan yang didiagnosis",
    "View all medications and items": "Lihat semua ubat dan item",
    "Select visit for MC, Invoice, etc.": "Pilih lawatan untuk MC, Invois, dll.",
    "Start fresh with new account": "Mulakan segar dengan akaun baru",
    "Move profile from old number": "Pindah profil dari nombor lama",
    "{} booking(s) need your action": "{} tempahan perlukan tindakan anda",
    "{} confirmed booking(s)": "{} tempahan disahkan",
    "{} pending booking(s)": "{} tempahan dalam proses",
    "Return to main menu": "Kembali ke menu utama",
    "Spinal adjustments, posture correction": "Pelarasan tulang belakang, pembetulan postur",
    "Muscle therapy, joint mobilization": "Terapi otot, mobilisasi sendi",

    # Existing translations from your example
    "Sorry, clinic information is not available at the moment.": "Maaf, maklumat klinik tidak tersedia buat masa ini.",
    "Clinic Enquiries": "Pertanyaan Klinik",
    "Failed to save booking. Please try again.": "Gagal menyimpan tempahan. Sila cuba lagi.",
    "✅ Your TCM booking has been submitted!": "✅ Tempahan TCM anda telah dihantar!",
    "Service: {}": "Perkhidmatan: {}",
    "Date: {}": "Tarikh: {}",
    "Time: {}": "Masa: {}",
    "Duration: {} minutes": "Tempoh: {} minit",
    "Method: {}": "Kaedah: {}",
    "Due to doctor flexibility, the doctor will contact you by 10 AM on the selected date. Your booking may be rescheduled - please check your upcoming bookings to accept or decline suggested times.": "Disebabkan fleksibiliti doktor, doktor akan hubungi anda sebelum 10 pagi pada tarikh dipilih. Tempahan anda mungkin dijadual semula - sila semak tempahan akan datang untuk terima atau tolak masa yang dicadangkan.",
    "Booking is pending approval. You'll be notified once confirmed.": "Tempahan menunggu kelulusan. Anda akan dimaklumkan sekali disahkan.",
    "Booking ID: {}": "ID Tempahan: {}",
    "Failed to send confirmation. Booking cancelled. Please try again.": "Gagal menghantar pengesahan. Tempahan dibatalkan. Sila cuba lagi.",
    "An error occurred while confirming the booking: {}. Please try again.": "Ralat berlaku semasa mengesahkan tempahan: {}. Sila cuba lagi."

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

