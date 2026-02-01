# cn_match.py - COMPLETE VERSION (UPDATED)
import logging
import time
from google.cloud import translate_v2 as translate
import os
import json
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

# Translation dictionary for English to Chinese
EN_TO_CN = {
    # ========== EXISTING TRANSLATIONS ==========
    
    # Existing translations
    "Sorry, clinic information is not available at the moment.": "抱歉，目前无法获取诊所信息。",
    "Clinic Enquiries": "诊所咨询",
    "Contact the front desk of {clinic_name} for further assistance.": "请联系 {clinic_name} 的前台以获取进一步帮助。",
    "Click a button to proceed": "点击按钮继续",
    "Talk to Front Desk": "与前台交谈",
    "Cancel": "取消",
    "Error sending clinic information. Please try again.": "发送诊所信息时出错，请重试。",
    "An error occurred. Please try again.": "发生错误，请重试。",
    "Please contact our front desk: https://wa.me/60127689719?text=Hi,+referred+from+AnyHealth": "请联系前台：{wa_link}",
    "Invalid module. Returning to main menu.": "无效模块。返回主菜单。",
    "Language set to {}.": "语言设置为{}。",
    "Your query is related to: {}\n\n{}\n\nPlease select the appropriate option from the menu.": "您的查询与以下内容相关：{}\n\n{}\n\n请从菜单中选择适当的选项。",
    "Please type what you need help with, and I'll guide you to the right option.": "请键入您需要帮助的内容，我将引导您选择正确的选项。",
    "Your query is related to: {}\n\n{}\n\nPlease select the appropriate option from the main menu to proceed.": "您的查询与以下相关：{}\n\n{}\n\n请从主菜单中选择相应的选项继续。",
    
    "Your query is related to: General GP Visit\n\nSteps for General GP Visit Booking:\n1. Select Menu\n2. Select Booking\n3. Select Booking Options\n4. Select General GP Options\n5. Type symptoms (e.g., Runny Nose)\n6. Select a doctor\n   a. If unsure, select Any Doctor\n7. Select a date\n8. Select an hour\n   a. Some slots may be unavailable, subject to doctor availability\n9. Click confirm and await approval\n10. Notification will be sent when doctor approves appointment - click on Menu -> Notification to view\n\nPlease select the appropriate option from the main menu to proceed.": "您的查询与以下相关：普通全科医生访问\n\n普通全科医生预约步骤：\n1. 选择菜单\n2. 选择预约\n3. 选择预约选项\n4. 选择普通全科医生选项\n5. 输入症状（例如，流鼻涕）\n6. 选择医生\n   a. 如果不确定，选择任意医生\n7. 选择日期\n8. 选择时间\n   a. 某些时间段可能不可用，视医生可用性而定\n9. 点击确认并等待批准\n10. 医生批准预约后将发送通知 - 点击菜单 -> 通知查看\n\n请从主菜单中选择相应的选项继续。",
    
    "Your query is related to: Health Check-Up and Tests\n\nSteps for Check-Up and Test Booking:\n1. Select Menu\n2. Select Booking\n3. Select Booking Options\n4. Select Checkup & Test\n5. Select a checkup type (e.g., General Screening)\n6. Type remarks (e.g., For employment)\n7. Select a doctor\n   a. If unsure, select Any Doctor\n8. Select a date\n9. Select an hour\n   a. Some slots may be unavailable, subject to doctor availability\n10. Click confirm and await approval\n11. Notification will be sent when doctor approves appointment - click on Menu -> Notification to view\n\nPlease select the appropriate option from the main menu to proceed.": "您的查询与以下相关：健康体检和测试\n\n体检和测试预约步骤：\n1. 选择菜单\n2. 选择预约\n3. 选择预约选项\n4. 选择体检和测试\n5. 选择体检类型（例如，常规筛查）\n6. 输入备注（例如，用于就业）\n7. 选择医生\n   a. 如果不确定，选择任意医生\n8. 选择日期\n9. 选择时间\n   a. 某些时间段可能不可用，视医生可用性而定\n10. 点击确认并等待批准\n11. 医生批准预约后将发送通知 - 点击菜单 -> 通知查看\n\n请从主菜单中选择相应的选项继续。",
    
    "Your query is related to: Vaccination\n\nSteps for Vaccination Booking:\n1. Select Menu\n2. Select Booking\n3. Select Booking Options\n4. Select Vaccination\n5. Select a Vaccination type (e.g., COVID Vaccine)\n6. Type remarks (e.g., Booster)\n7. Select a doctor\n   a. If unsure, select Any Doctor\n8. Select a date\n9. Select an hour\n   a. Some slots may be unavailable, subject to doctor availability\n10. Click confirm and await approval\n11. Notification will be sent when doctor approves appointment - click on Menu -> Notification to view\n\nPlease select the appropriate option from the main menu to proceed.": "您的查询与以下相关：疫苗接种\n\n疫苗接种预约步骤：\n1. 选择菜单\n2. 选择预约\n3. 选择预约选项\n4. 选择疫苗接种\n5. 选择疫苗类型（例如，COVID疫苗）\n6. 输入备注（例如，追加剂）\n7. 选择医生\n   a. 如果不确定，选择任意医生\n8. 选择日期\n9. 选择时间\n   a. 某些时间段可能不可用，视医生可用性而定\n10. 点击确认并等待批准\n11. 医生批准预约后将发送通知 - 点击菜单 -> 通知查看\n\n请从主菜单中选择相应的选项继续。",
    
    "Your query is related to: Report Result Consultation\n\nSteps for Report Result Consultation:\n1. Notification informs you that your test result has been released\n2. Click Menu\n3. Select Booking\n4. Select Report Result Booking\n5. Select Report (e.g., Booking 1) that appears\n6. Select Yes if you have any remarks for the doctor (e.g., Result is for university)\n7. Select date for consult\n8. Select time (hour)\n9. Select slot\n10. Click confirm and await approval\n11. Notification will be sent when doctor approves appointment - click on Menu -> Notification to view\n\nPlease select the appropriate option from the main menu to proceed.": "您的查询与以下相关：报告结果咨询\n\n报告结果咨询预约步骤：\n1. 通知告知您的测试结果已发布\n2. 点击菜单\n3. 选择预约\n4. 选择报告结果预约\n5. 选择出现的报告（例如，预约1）\n6. 如果有对医生的备注（例如，结果用于大学），选择是\n7. 选择咨询日期\n8. 选择时间（小时）\n9. 选择时间段\n10. 点击确认并等待批准\n11. 医生批准预约后将发送通知 - 点击菜单 -> 通知查看\n\n请从主菜单中选择相应的选项继续。",
    
    "Your query is related to: View Past Booking History\n\nSteps to View Previous Booking Reports:\n1. Click Menu\n2. Select Booking\n3. Select View Past Consultations\n\nPlease select the appropriate option from the main menu to proceed.": "您的查询与以下相关：查看以往预约记录\n\n查看以往预约报告步骤：\n1. 点击菜单\n2. 选择预约\n3. 选择查看以往咨询\n\n请从主菜单中选择相应的选项继续。",
    
    "Your query is related to: View Upcoming Bookings\n\nSteps to View Upcoming Appointments:\n1. Click Menu\n2. Select Booking\n3. Select View Upcoming Bookings\n4. On the screen are Confirmed bookings and Pending Bookings\n   a. Confirmed bookings: doctor has approved and added to their calendar\n   b. Pending Bookings: awaiting doctor confirmation\n   Please allow 3 hours for doctor to confirm your booking.\n\nPlease select the appropriate option from the main menu to proceed.": "您的查询与以下相关：查看即将到来的预约\n\n查看即将到来的预约步骤：\n1. 点击菜单\n2. 选择预约\n3. 选择查看即将到来的预约\n4. 屏幕上显示已确认的预约和待确认的预约\n   a. 已确认的预约：医生已批准并添加到他们的日历\n   b. 待确认的预约：等待医生确认\n   请留出3小时让医生确认您的预约。\n\n请从主菜单中选择相应的选项继续。",
    
    "Your query is related to: Accept/Reject Reschedule\n\nSteps to Accept or Reject Rescheduled Appointment:\n1. Select Menu\n2. Select Booking\n3. Select Reschedule Booking\n4. Select Choose Category\n5. Select Action Required\n6. Select the booking as required\n7. Click Accept if the timing is suitable\n   a. Booking is confirmed\n8. Click Decline if the timing is not suitable\n   a. Booking will be removed\n\nPlease select the appropriate option from the main menu to proceed.": "您的查询与以下相关：接受/拒绝重新安排\n\n接受或拒绝重新安排的预约步骤：\n1. 选择菜单\n2. 选择预约\n3. 选择重新安排预约\n4. 选择选择类别\n5. 选择需要采取行动\n6. 根据需要选择预约\n7. 如果时间合适，点击接受\n   a. 预约已确认\n8. 如果时间不合适，点击拒绝\n   a. 预约将被移除\n\n请从主菜单中选择相应的选项继续。",
    
    "Your query is related to: Reschedule Confirmed Booking - tgt\n\nSteps to Reschedule a Confirmed Booking:\n1. Notification informs you that your test result has been released\n2. Select Menu\n3. Select Booking\n4. Select Reschedule\n5. Click Confirmed\n6. Select Booking you wish to reschedule\n7. Select Reschedule\n8. Select new date\n9. Select new time\n10. Await Doctor Approval\n\nPlease select the appropriate option from the main menu to proceed.": "您的查询与以下相关：重新安排已确认预约\n\n重新安排已确认预约的步骤：\n1. 通知告知您的测试结果已发布\n2. 选择菜单\n3. 选择预约\n4. 选择重新安排\n5. 点击已确认\n6. 选择您希望重新安排的预约\n7. 选择重新安排\n8. 选择新日期\n9. 选择新时间\n10. 等待医生批准\n\n请从主菜单中选择相应的选项继续。",
    
    "Your query is related to: Cancel Confirmed Booking - tgt\n\nSteps to Cancel a Confirmed Booking:\n1. Notification informs you that your test result has been released\n2. Select Menu\n3. Select Booking\n4. Select Reschedule\n5. Click Confirmed\n6. Select Booking you wish to reschedule\n7. Select Cancel\n8. Your booking has been cancelled\n\nPlease select the appropriate option from the main menu to proceed.": "您的查询与以下相关：取消已确认预约\n\n取消已确认预约的步骤：\n1. 通知告知您的测试结果已发布\n2. 选择菜单\n3. 选择预约\n4. 选择重新安排\n5. 点击已确认\n6. 选择您希望重新安排的预约\n7. 选择取消\n8. 您的预约已取消\n\n请从主菜单中选择相应的选项继续。",
    
    "Your query is related to: Reschedule/Cancel Pending Booking\n\nSteps to Reschedule or Cancel a Pending Booking:\n1. Select Menu\n2. Select Booking\n3. Select Reschedule\n4. Click Pending\n5. Select Booking you wish to reschedule or cancel\n6. To Reschedule:\n   a. Select Reschedule\n   b. Select new date\n   c. Select new time\n   d. Await Doctor Approval\n7. To Cancel:\n   a. Select Cancel\n   b. Your booking has been cancelled\n\nPlease select the appropriate option from the main menu to proceed.": "您的查询与以下相关：重新安排/取消待确认预约\n\n重新安排或取消待确认预约的步骤：\n1. 选择菜单\n2. 选择预约\n3. 选择重新安排\n4. 点击待确认\n5. 选择您希望重新安排或取消的预约\n6. 重新安排：\n   a. 选择重新安排\n   b. 选择新日期\n   c. 选择新时间\n   d. 等待医生批准\n7. 取消：\n   a. 选择取消\n   b. 您的预约已取消\n\n请从主菜单中选择相应的选项继续。",
    
    "Your query is related to: Notification\n\nSteps for Notifications:\n1. Select Menu\n2. Select Notifications to view all notifications\n\nPlease select the appropriate option from the main menu to proceed.": "您的查询与以下相关：通知\n\n通知步骤：\n1. 选择菜单\n2. 选择通知以查看所有通知\n\n请从主菜单中选择相应的选项继续。",
    
    "Your query is related to: Change Language\n\nSteps to Change Language:\n1. Select Menu\n2. Select Change Language\n3. Select preferred language\n\nPlease select the appropriate option from the main menu to proceed.": "您的查询与以下相关：更改语言\n\n更改语言步骤：\n1. 选择菜单\n2. 选择更改语言\n3. 选择首选语言\n\n请从主菜单中选择相应的选项继续。",
    
    # Day names for calendar
    "Monday": "星期一",
    "Tuesday": "星期二",
    "Wednesday": "星期三",
    "Thursday": "星期四",
    "Friday": "星期五",
    "Saturday": "星期六",
    "Sunday": "星期日",
    "📅 Future Date": "📅 未来日期",

    "Please enter your preferred date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:": "请输入您偏好的日期格式，例如 DD/MM/YYYY、DD-MM-YYYY 或 DD MM YYYY：",
    "Is this the correct date: {}?": "这个日期正确吗：{}？",
    "Great! {} is available. Is this the time you want?": "太好了！{} 有空。这是您想要的时间吗？",
    
    # TCM booking confirmation templates
    "Confirm your TCM booking:\n* Service: {}\n* Doctor: {}\n* Date: {}\n* Time: {}\n* Duration: {} min\n* Details: {}": "确认您的传统医疗预约：\n* 服务：{}\n* 医生：{}\n* 日期：{}\n* 时间：{}\n* 时长：{} 分钟\n* 详情：{}",
    "✅ Your TCM booking has been submitted!": "✅ 您的传统医疗预约已提交！",
    "Service: {}\nDate: {}\nTime: {}\nDuration: {} minutes": "服务：{}\n日期：{}\n时间：{}\n时长：{} 分钟",
    "Booking is pending approval. You'll be notified once confirmed.": "预约正在等待批准。一旦确认，您将收到通知。",
    "Booking ID: {}": "预约 ID：{}",
    
    # From main.py
    "Error registering user. Please try again.": "注册用户错误。请重试。",
    "Please select an option from the menu.": "请从菜单中选择一个选项。",
    "Invalid input. Please select an option from the menu.": "输入无效。请从菜单中选择一个选项。",
    "Invalid module. Returning to main menu.": "模块无效。返回主菜单。",
    "An error occurred. Please try again.": "发生错误。请重试。",
    "Language set to {}.": "语言设置为 {}。",
    
    # From utils.py
    "AnyHealth Bot": "AnyHealth 机器人",
    "Welcome to AnyHealth Bot! Please choose an option:": "欢迎使用 AnyHealth 机器人！请选择一个选项：",
    "Select an option to proceed": "选择一个选项继续",
    "Menu": "菜单",
    "Main Options": "主要选项",
    "🔔Notification": "🔔通知",
    "🏥Booking": "🏥预约",
    "🌐Change Language": "🌐更改语言",
    "📞Clinic Enquiries": "📞诊所咨询",
    "Booking Options": "预约选项",
    "Booking Services": "预约服务",
    "General GP Visit": "普通全科医生访问",
    "Checkup & Test": "体检与测试",
    "Vaccination": "疫苗接种",
    "Report Result Booking": "报告结果预约",
    "View Booking": "查看预约",
    "Reschedule Booking": "重新安排预约",
    "Hi, you have new notification(s), please tap on \"notification\" button in the Main Menu to check them out.": "您有新的通知，请点击主菜单中的通知按钮查看。",
    "❓Help": "❓帮助",
    
    # From calendar_utils.py - TITLES
    "Choose Doctor": "选择医生",
    "Available Doctors": "可用医生",
    "Any Doctor": "任何医生",
    "Choose Date": "选择日期",
    "Available Dates": "可用日期",
    "Choose Hour": "选择小时",
    "Available Hours": "可用小时",
    "Choose Slot": "选择时间段",
    "30min Slots": "30分钟时间段",
    "Confirm": "确认",
    
    # From menu.py + main.py - TITLES
    "Select Language": "选择语言",
    "Languages": "语言",
    "English": "英语",
    "Bahasa Malaysia": "马来语",
    "中文": "中文",
    "தமிழ்": "泰米尔语",
    
    # From calendar_utils.py - CONTENT
    "Select a doctor for your appointment or choose 'Any Doctor':": "为您的预约选择医生或选择\"任何医生\": ",
    "Select a date for your appointment:": "为您的预约选择日期：",
    "Select an hour for {}:": "为 {} 选择小时：",
    "Select {}min slot for {} {}:": "为 {} {} 选择 {} 分钟时间段：",
    "No doctors available. Please contact support.": "没有可用医生。请联系支持。",
    "Unable to fetch doctors. Please try again.": "无法获取医生信息。请重试。",
    "An error occurred while fetching doctors: {}. Please try again.": "获取医生信息时发生错误：{}。请重试。",
    "No available dates in the next 14 days. Please select another doctor.": "未来14天内没有可用日期。请选择其他医生。",
    "No available dates in the next 14 days. Please try again later.": "未来14天内没有可用日期。请稍后重试。",
    "Unable to fetch calendar. Please try again.": "无法获取日历。请重试。",
    "An error occurred while fetching the calendar: {}. Please try again.": "获取日历时发生错误：{}。请重试。",
    "No available hours for this date. Please select another date.": "此日期没有可用小时。请选择其他日期。",
    "Unable to fetch hours. Please try again.": "无法获取小时信息。请重试。",
    "An error occurred while fetching hours: {}. Please try again.": "获取小时信息时发生错误：{}。请重试。",
    "No available time slots.": "没有可用时间段。",
    "Error loading slots.": "加载时间段错误。",
    "Selected time slot is no longer available. Please choose another.": "所选时间段不再可用。请选择其他时间段。",
    "No doctors available for this time slot. Please select another.": "此时间段没有可用医生。请选择其他时间段。",
    "Confirm your booking:\n• Service: {}\n• Doctor: {}\n• Date: {}\n• Time: {}\n• Duration: {} min\n• Details: {}": "确认您的预约：\n• 服务：{}\n• 医生：{}\n• 日期：{}\n• 时间：{}\n• 持续时间：{} 分钟\n• 详情：{}",
    "The booking is not placed": "预约未完成",
    
    # From menu.py + main.py - CONTENT
    "Please select your preferred language:": "请选择您首选的语言：",
    "Choose a language to proceed": "选择语言继续",
    "Error setting language. Please try again.": "设置语言错误。请重试。",
    "Invalid selection. Please try again.": "选择无效。请重试。",
    "Invalid button selection. Please try again.": "按钮选择无效。请重试。",
    
    # From utils.py - CONTENT
    "Please choose a booking option:": "请选择一个预约选项：",
    
    # From notification.py
    "No notifications found.": "未找到通知。",
    "✅ {} notification(s) displayed!": "✅ 显示了 {} 个通知！",
    
    # From view_booking.py - TITLES
    "View Booking Options": "查看预约选项",
    "View Past Consultations": "查看过去的咨询",
    "View Upcoming Bookings": "查看即将进行的预约",
    "Request Report": "请求报告",
    "Past Consultations": "过去咨询",
    "Select Option": "选择选项",
    
    # From view_booking.py - CONTENT
    "You have no past consultations.": "您没有过去的咨询。",
    "Your past consultations:": "您的过去咨询：",
    "Consultation with Dr. {} at {} on {} (Diagnosis: {})": "与 {} 医生在 {} 的 {} 咨询（诊断：{}）",
    "Select a past consultation to request a report:": "选择一个过去的咨询以请求报告：",
    "Consultation {}": "咨询 {}",
    "User not found. Please ensure your number is registered.": "未找到用户。请确保您的号码已注册。",
    "Error fetching user information. Please try again.": "获取用户信息错误。请重试。",
    "Error fetching doctor information. Please try again.": "获取医生信息错误。请重试。",
    "Error fetching clinic information. Please try again.": "获取诊所信息错误。请重试。",
    "Error fetching past consultations. Please try again.": "获取过去咨询错误。请重试。",
    "Error processing timezone. Please try again.": "处理时区错误。请重试。",
    "You have no upcoming bookings.": "您没有即将进行的预约。",
    "Action Required": "需要采取行动",
    "Confirmed": "已确认",
    "Pending": "待处理",
    "Consultation with Dr. {} at {} on {} at {} (Symptoms: {})": "与 {} 医生在 {} 的 {} 咨询（症状：{}）",
    "Checkup ({}) with Dr. {} at {} on {} at {}": "体检（{}）与 {} 医生在 {} 的 {} ",
    "Vaccination ({}) with Dr. {} at {} on {} at {}": "疫苗接种（{}）与 {} 医生在 {} 的 {} ",
    "Pending {} ({}) with Dr. {} at {} on {} at {}": "待处理 {}（{}）与 {} 医生在 {} 的 {} ",
    "{} ({}) with Dr. {} at {} on {} at {} (New: {} at {})": "{}（{}）与 {} 医生在 {} 的 {} （新：{} 在 {}）",
    "Error fetching consultation bookings. Continuing with other bookings.": "获取咨询预约错误。继续处理其他预约。",
    "Error fetching checkup bookings. Continuing with other bookings.": "获取体检预约错误。继续处理其他预约。",
    "Error fetching vaccination bookings. Continuing with other bookings.": "获取疫苗预约错误。继续处理其他预约。",
    "Error fetching pending bookings. Continuing with other bookings.": "获取待处理预约错误。继续处理其他预约。",
    "Error fetching reschedule requests. Continuing with other bookings.": "获取重新安排请求错误。继续处理其他预约。",
    "Please select an option:": "请选择一个选项：",
    "Error displaying the booking menu. Please try again.": "显示预约菜单错误。请重试。",
    "An unexpected error occurred while fetching past consultations. Please try again.": "获取过去咨询时发生意外错误。请重试。",
    "An unexpected error occurred while fetching upcoming bookings. Please try again.": "获取即将进行的预约时发生意外错误。请重试。",
    
    # From reschedule_booking.py - TITLES
    "Choose Category": "选择类别",
    "Categories": "类别",
    "Choose Booking": "选择预约",
    "Bookings": "预约",
    "Reschedule": "重新安排",
    "Cancel Booking": "取消预约",
    "Accept": "接受",
    "Decline": "拒绝",
    
    # From reschedule_booking.py - CONTENT
    "You have no upcoming bookings to reschedule.": "您没有可重新安排的即将预约。",
    "Select a category to reschedule from:": "从以下类别中选择重新安排：",
    "Select a booking to manage:": "选择一个预约进行管理：",
    "Selected: {}": "已选择：{}",
    "Booking {}": "预约 {}",
    "Invalid category selection. Please try again.": "类别选择无效。请重试。",
    "No bookings available in {} category.": "{} 类别中没有可用预约。",
    "Invalid booking selection. Please try again.": "预约选择无效。请重试。",
    "You have accepted the reschedule. Your {} is now confirmed on {} at {}.": "您已接受重新安排。您的 {} 现已确认于 {} 的 {}。",
    "You have declined the reschedule request.": "您已拒绝重新安排请求。",
    "Your booking has been cancelled.": "您的预约已取消。",
    "Invalid booking ID format. Please try again.": "预约 ID 格式无效。请重试。",
    "Reschedule request not found or has invalid data. Please try again.": "未找到重新安排请求或数据无效。请重试。",
    "Invalid booking type for reschedule request.": "重新安排请求的预约类型无效。",
    "Booking not found. It may have already been cancelled.": "未找到预约。可能已被取消。",
    "✅ RESCHEDULED!\n\n{} moved to {} at {} with Dr. {} ({}min)\nStatus: PENDING APPROVAL": "✅ 已重新安排！\n\n{} 已移至 {} 的 {} 与 {} 医生（{}分钟）\n状态：待批准",
    "Booking not found!": "未找到预约！",
    "Save error! Please try again.": "保存错误！请重试。",
    "An error occurred during rescheduling. Please try again.": "重新安排时发生错误。请重试。",
    "Invalid input. Please try again.": "输入无效。请重试。",
    
    # From checkup_booking.py
    "Please select a checkup type:": "请选择体检类型：",
    "Choose Checkup": "选择体检",
    "Checkup Types": "体检类型",
    "Please specify the checkup type:": "请指定体检类型：",
    "Do you have any remarks for {} ({} min)?": "您对 {}（{} 分钟）有任何备注吗？",
    "Yes": "是",
    "No": "否",
    "Please enter your remarks:": "请输入您的备注：",
    "Your checkup booking is pending approval by the admin.": "您的体检预约正在等待管理员批准。",
    
    # From report_symptom.py
    "Please describe your symptoms.": "请描述您的症状。",
    
    # From vaccination.py
    "Please select a vaccine type:": "请选择疫苗类型：",
    "Choose Vaccine": "选择疫苗",
    "Vaccine Types": "疫苗类型",
    "Please specify the vaccine type:": "请指定疫苗类型：",
    
    # From report_booking.py
    "📋 Select Report": "📋 选择报告",
    "Select Report": "选择报告",
    "Your Reports": "您的报告",
    "No pending reports found. Please book a checkup first.": "未找到待处理报告。请先预约体检。",
    "Choose a report to book review:": "选择一个报告进行预约审查：",
    "Bkng {}": "预约 {}",
    "Error fetching reports. Please try again.": "获取报告错误。请重试。",
    "Error: No doctor found for this report. Contact support.": "错误：此报告未找到医生。请联系支持。",
    "Error selecting report. Please try again.": "选择报告错误。请重试。",
    "✅ Your report review booking is pending approval!": "✅ 您的报告审查预约正在等待批准！",
    "Error creating booking. Please try again.": "创建预约错误。请重试。",
    "Please confirm your booking:\nReport: {}\nDoctor: {}\nDate: {}\nTime: {}\nDuration: {} min": "请确认您的预约：\n报告：{}\n医生：{}\n日期：{}\n时间：{}\n持续时间：{} 分钟",
    
    # From post_report.py
    "Invalid selection. Please try again.": "选择无效。请重试。",
    "Error processing your selection. Please try again.": "处理您的选择时出错。请重试。",
    "Error fetching consultation details. Please try again.": "获取咨询详情错误。请重试。",
    "Consultation not found or not associated with this number. Please try again.": "未找到咨询或与此号码无关。请重试。",
    "Error generating report request. Please try again.": "生成报告请求错误。请重试。",
    "Error processing report request. Please try again.": "处理报告请求错误。请重试。",
    "Please enter the patient's IC in the format 'verified:<IC>', e.g., verified:123456789011": "请按照 'verified:<IC>' 的格式输入患者身份证号码，例如：verified:123456789011",
    "An unexpected error occurred while processing your report request. Please try again.": "处理您的报告请求时发生意外错误。请重试。",
    "IC verification failed. Please enter the correct patient IC.": "身份证验证失败。请输入正确的患者身份证。",
    "No report request found. Please try again.": "未找到报告请求。请重试。",
    "Invalid report request status. Please try again.": "报告请求状态无效。请重试。",
    "Error processing verification. Please try again.": "处理验证错误。请重试。",
    "IC verified, but error sending report. Please try again.": "身份证已验证，但发送报告错误。请重试。",
    "IC verified, but the report is not yet available. You will be notified when ready.": "身份证已验证，但报告尚未可用。准备好后将通知您。",
    "IC verified successfully, but no report request pending. Please select a consultation.": "身份证验证成功，但没有待处理的报告请求。请选择一个咨询。",
    "Invalid verification format. Please use 'verified:<IC>'.": "验证格式无效。请使用 'verified:<IC>'。",
    "A referral letter has been generated. Please contact your healthcare provider for details.": "已生成转诊信。请联系您的医疗提供者了解详情。",
    "No referral required.": "无需转诊。",
    "IC verified. Report for consultation on {} (Diagnosis: {}):\n{}\n\n{}": "身份证已验证。关于 {} 的咨询报告（诊断：{}）：\n{}\n\n{}",
    "Booking cancelled.": "预约已取消。",
    
    # ========== NEW TRANSLATIONS FROM PROVIDED FILES ==========
    
    # view_booking.py – body text
    "Pending with Dr. {doctornamedrname} at {clinicname} on {pdate} at {ptime}.": "与 {doctornamedrname} 医生在 {clinicname} 的预约，时间为 {pdate} {ptime}，目前为待处理状态。",
    "Unknown": "未知",
    "Unknown Clinic": "未知诊所",
    "with Dr. {doctornamedrname} at {clinicname} on {roriginaldate} at {roriginaltime}. New at {rnewdate} at {rnewtime}.": "与 {doctornamedrname} 医生在 {clinicname} 的预约，原定时间为 {roriginaldate} {roriginaltime}，新时间为 {rnewdate} {rnewtime}。",
    "Unknown Provider": "未知服务提供者",
    "Patient": "病人",
    "Home-to-Home Transfer for {patientname} on {bscheduleddate} at {scheduledtimedisplay}. Provider {providername}, Distance {distance} km.": "家到家接送服务，病人 {patientname}，预约日期 {bscheduleddate} {scheduledtimedisplay}。服务提供者 {providername}，距离 {distance} 公里。",
    "Hospital": "医院",
    "Appointment at {bappointmentdate} {bappointmenttime}": "预约时间：{bappointmentdate} {bappointmenttime}",
    "Home-to-Hospital Transfer for {patientname} to {hospitalname} {appointmentinfo} on {bscheduleddate} at {scheduledtimedisplay}. Provider {providername}.": "家到院接送服务，病人 {patientname} 前往 {hospitalname} {appointmentinfo}，日期 {bscheduleddate} {scheduledtimedisplay}。服务提供者 {providername}。",
    "TCM {bookingtypetranslated} with Dr. {doctornamedrname} at {clinicname} on {boriginaldate} at {boriginaltime}. New at {bnewdate} at {bnewtime} - Doctor Requested Reschedule": "传统医疗 {bookingtypetranslated}，与 {doctornamedrname} 医生于 {clinicname} 就诊，原时间 {boriginaldate} {boriginaltime}。新时间 {bnewdate} {bnewtime}（医生要求改期）。",
    "TCM {bookingtypetranslated} with Dr. {doctornamedrname} at {clinicname} on {displaydate} at {displaytime} - Doctor Requested Reschedule": "传统医疗 {bookingtypetranslated}，与 {doctornamedrname} 医生于 {clinicname} 就诊，时间 {displaydate} {displaytime}（医生要求改期）。",
    "{prefix} TCM {bookingtypetranslated} with Dr. {doctornamedrname} at {clinicname} on {displaydate} at {displaytime}. Details {details}": "{prefix} 传统医疗 {bookingtypetranslated}，与 {doctornamedrname} 医生于 {clinicname} 就诊，时间 {displaydate} {displaytime}。详情 {details}。",
    "{prefix} {bookingtypetranslated} with Dr. {doctornamedrname} at {clinicname} on {displaydate} at {displaytime}. Details {details}": "{prefix} {bookingtypetranslated}，与 {doctornamedrname} 医生于 {clinicname} 就诊，时间 {displaydate} {displaytime}。详情 {details}。",
    "Appointment at {appointmentdate} {appointmenttime}": "预约时间：{appointmentdate} {appointmenttime}",
    "TCM {bookingtypetranslated}": "传统医疗 {bookingtypetranslated}",
    "TCM RESCHEDULE ACCEPTED - You have accepted the reschedule. Your TCM {bookingtypetranslated} is now confirmed on {datanewdate} at {datanewtime} with Dr. {doctorname}.": "传统医疗改期已接受——您已接受改期请求。您的传统医疗 {bookingtypetranslated} 已确认于 {datanewdate} {datanewtime} 与 {doctorname} 医生就诊。",
    "ERROR accepting TCM reschedule. Please try again.": "接受传统医疗改期时出错。请稍后重试。",
    "TCM Doctor": "传统医疗医生",
    "TCM RESCHEDULE DECLINED - You have declined the reschedule request. Your TCM {bookingtypetranslated} remains confirmed on {dataoriginaldate} at {dataoriginaltime} with Dr. {doctorname}.": "传统医疗改期已拒绝——您已拒绝改期请求。您的传统医疗 {bookingtypetranslated} 仍确认于 {dataoriginaldate} {dataoriginaltime} 与 {doctorname} 医生就诊。",
    "TCM RESCHEDULE DECLINED - You have declined the reschedule request.": "传统医疗改期已拒绝——您已拒绝改期请求。",
    "ERROR declining TCM reschedule. Please try again.": "拒绝传统医疗改期时出错。请稍后重试。",
    "REPEATED VISIT CANCELLATION - This booking is part of a repeated visit series. Do you want to cancel just this booking or all future repeated bookings?": "重复就诊取消——此预约属于重复就诊系列。您要取消这一次预约，还是取消所有后续重复预约？",
    "Cancel This One Only": "只取消这一次",
    "Cancel All Repeated": "取消所有重复预约",
    "Back": "返回",
    "ERROR cancelling booking. Please try again.": "取消预约时出错。请稍后重试。",
    "CANCELLATION FAILED - Booking not found. It may have already been cancelled.": "取消失败——未找到该预约，可能已被取消。",
    "BOOKING CANCELLED - The booking has been successfully cancelled.": "预约已取消——该预约已成功取消。",
    "Invalid input. Please use the buttons provided.": "输入无效。请使用提供的按钮。",
    "Please enter your preferred date as DDMMYYYY, DD-MM-YYYY or DD MM YYYY": "请输入您偏好的日期格式，例如 DDMMYYYY、DD-MM-YYYY 或 DD MM YYYY。",
    "Please enter your remarks": "请输入备注。",
    "Please enter your preferred time e.g., 930, 2pm, 1430": "请输入您偏好的时间，例如 930、2pm、1430。",
    
    # tcm_calendar_utils.py – body text & buttons
    "Future Date": "未来日期",
    "No available dates in the next 14 days. Please {selectanotherdoctor}.": "接下来 14 天内没有可用日期。请 {selectanotherdoctor}。",
    "select another doctor": "选择其他医生",
    "try again later": "稍后再试",
    "Select a date for your appointment": "请选择您的预约日期。",
    "Unable to fetch calendar. Please try again.": "无法获取日历，请稍后重试。",
    "An error occurred while fetching the calendar {error}. Please try again.": "获取日历时发生错误 {error}。请稍后重试。",
    "Clinic not selected. Please start over.": "尚未选择诊所，请重新开始。",
    "No available hours for this date. Please select another date.": "该日期没有可用时段，请选择其他日期。",
    "No doctors available for this time slot. Please select another.": "此时间段暂无可用医生，请选择其他时间。",
    "No doctors available. Please contact support.": "暂无可用医生，请联系客服。",
    "Confirm your TCM booking\n\nService: {servicetype}\nDoctor: {doctorname}\nDate: {date}\nTime: {timeslot}\nDuration: {duration} min\nDetails: {details}\nReminder: {translatedreminder}": "确认您的传统医疗预约\n\n服务：{servicetype}\n医生：{doctorname}\n日期：{date}\n时间：{timeslot}\n时长：{duration} 分钟\n详情：{details}\n提醒：{translatedreminder}",
    "Confirm your TCM booking\n\nService: {servicetype}\nDoctor: Assigned by Clinic\nDate: {date}\nTime: {timeslot}\nDuration: {duration} min\nDetails: {details}\nReminder: {translatedreminder}": "确认您的传统医疗预约\n\n服务：{servicetype}\n医生：由诊所指派\n日期：{date}\n时间：{timeslot}\n时长：{duration} 分钟\n详情：{details}\n提醒：{translatedreminder}",
    "An error occurred while confirming the booking. Please try again.": "确认预约时发生错误，请稍后重试。",
    "AM": "上午",
    "PM": "下午",
    "Select AM or PM for {date}": "请选择 {date} 的上午或下午。",
    
    # tcm_service.py – headers, body, buttons
    "Clinic not found. Please select another clinic.": "未找到诊所，请选择其他诊所。",
    "Address": "地址",
    "Now please select a treatment category": "现在请选择治疗类别。",
    "Unable to load clinic information. Please try again.": "无法加载诊所信息，请稍后重试。",
    "Unable to load TCM services. Please try again.": "无法加载传统医疗服务，请稍后重试。",
    "No {tcmtype} clinics available at the moment. Please select another service type.": "目前没有 {tcmtype} 诊所可用，请选择其他服务类型。",
    "Unable to load TCM clinics. Please try again.": "无法加载传统医疗诊所，请稍后重试。",
    "No categories available for this clinic. Please select another clinic.": "该诊所暂无可用类别，请选择其他诊所。",
    "Unable to load categories. Please try again.": "无法加载类别，请稍后重试。",
    "Error - Clinic or category not selected. Please start over.": "错误——尚未选择诊所或类别，请重新开始。",
    "No services available in this category. Please select another category.": "此类别暂无可用服务，请选择其他类别。",
    "Unable to load services. Please try again.": "无法加载服务，请稍后重试。",
    "TCM Services": "传统医疗服务",
    "Please select the type of TCM service you need": "请选择您需要的传统医疗服务类型。",
    "Choose a service type to proceed": "请选择服务类型以继续。",
    "Select Type": "选择类型",
    "TCM Service Types": "传统医疗服务类型",
    "Chiropractic": "脊椎矫正",
    "Spinal adjustments, posture correction": "脊柱调整、姿势矫正",
    "Physiotherapy": "物理治疗",
    "Muscle therapy, joint mobilization": "肌肉治疗、关节松动",
    "Back to Services": "返回服务列表",
    "Please select a clinic": "请选择诊所。",
    "Choose a clinic to proceed": "请选择诊所以继续。",
    "Select Clinic": "选择诊所",
    "Available Clinics": "可用诊所",
    "Back to Type Selection": "返回类型选择",
    "Please select a treatment category": "请选择治疗类别。",
    "Choose a category to proceed": "请选择类别以继续。",
    "Select Category": "选择类别",
    "Treatment Categories": "治疗类别",
    "Back to Clinics": "返回诊所列表",
    "Please select a treatment service": "请选择治疗服务。",
    "Choose a service to proceed": "请选择服务以继续。",
    "Select Service": "选择服务",
    "Back to Categories": "返回类别列表",
    "{duration} min": "{duration} 分钟",
    
    # webhooksplit.py – body text
    "Thank you for acknowledging the notification. Let us know if you need any assistance.": "感谢您确认通知，如需任何协助，请随时告诉我们。",
    
    # Headers
    "1. Relationship": "1. 关系",
    "📍 Current Address (Pickup)": "📍 当前地址 (取车点)",
    "📍 Pickup Address Found": "📍 找到取车地址",
    "📍 Destination Address Found": "📍 找到目的地地址",
    "📱 Destination Emergency Contact": "📱 目的地紧急联系人",
    "📎 Attachments": "📎 附件",
    "📝 Remarks": "📝 备注",
    "📅 Select Transfer Date": "📅 选择转运日期",
    "📅 Select {} Date": "📅 选择 {} 日期",
    "⏰ Select 2-Hour Slot ({})": "⏰ 选择2小时时间段 ({})",
    "🏥 Current Hospital Address Found": "🏥 找到当前医院地址",
    "🏥 Destination Hospital Address Found": "🏥 找到目的地医院地址",
    "Select Individual": "选择个人",
    "Options for {}": "{} 的选项",
    
    # Footers
    "Choose a language to proceed": "请选择一种语言以继续",
    "Select one option": "请选择一个选项",
    "Multiple profiles found for your account": "您的账户下发现多个个人资料",
    
    # Buttons
    "Try Again": "重试",
    "Help Me Choose": "帮我选择",
    "Find Another": "寻找另一个",
    "Try Another Time": "尝试其他时间",
    "Yes - Life Threat": "是 - 生命威胁",
    "No - Not Immediate": "否 - 非紧急",
    "❌ Cancel": "❌ 取消",
    "Select": "选择",
    "Parent": "父母",
    "Child": "孩子",
    "Relative": "亲戚",
    "Stranger": "陌生人",
    "📍 Share Location": "📍 分享位置",
    "📝 Type Address": "📝 输入地址",
    "✅ Yes, Correct": "✅ 是的，正确",
    "✏️ Edit Address": "✏️ 修改地址",
    "✅ Yes": "✅ 是的",
    "❌ No": "❌ 否",
    "Next": "下一步",
    "Skip": "跳过",
    "Add Remarks": "添加备注",
    "Today": "今天",
    "Tomorrow": "明天",
    "Others": "其他",
    "AM (12am - 11:45am)": "上午 (12am - 11:45am)",
    "PM (12pm - 11:45pm)": "下午 (12pm - 11:45pm)",
    "Select Time Slot": "选择时间段",
    "❌ No, Different": "❌ 否，不同",
    "🔙 Back to Main Menu": "🔙 返回主菜单",
    "🔙 Back to Booking": "🔙 返回预约",
    "🔙 Back to Main": "🔙 返回主页",
    "🏥 Clinic Services": "🏥 诊所服务",
    "🌿 TCM Services": "🌿 传统医疗",
    "🚑 Ambulance Service": "🚑 救护车服务",
    "💅 Aesthetic": "💅 医美",
    "🏨 Hospital": "🏨 医院",
    "💉 Dialysis": "💉 透析",
    "👴 Elderly Care": "👴 养老护理",
    "🔙 Back to Menu": "🔙 返回菜单",
    "⚔️ Enemy (Disease)": "⚔️ 疾病",
    "💊 Med & Routine": "💊 药物与常规",
    "📄 Report": "📄 报告",
    "🔙 Back to Patients": "🔙 返回患者列表",
    "⬅️ Previous Page": "⬅️ 上一页",
    "➡️ Next Page": "➡️ 下一页",

    # Main Menu Confirmation
    "⚠️ *Main Menu Confirmation*\n\nAre you sure you want to go back to the main menu?\nThis will cancel your current action.": "⚠️ *主菜单确认*\n\n您确定要返回主菜单吗？\n这将取消您当前的各项操作。",
    
    # Interactive Menu
    "👤 Profile": "👤 个人资料",
    "🏥 Service Booking": "🏥 服务预约",
    "📅 Upcoming Booking": "📅 即将到来的预约",
    
    # Non-Emergency Menu
    "🚑 Non-Emergency Ambulance": "🚑 非紧急救护车",
    "Please select the type of non-emergency transport you need:\n\n• Scheduled patient transport\n• Advance booking required (24 hours)\n• Professional medical team": "请选择您需要的非紧急转运类型：\n\n• 预定的病人转运\n• 需要提前预订（24小时）\n• 专业医疗团队",
    "Choose an option below": "请选择以下选项",
    "🏠 → 🏥 Home to Hosp": "🏠 → 🏥 家到医院",
    "🏠 → 🏠 Home to Home": "🏠 → 🏠 家到家",
    "🏥 → 🏠 Hosp to Home": "🏥 → 🏠 医院到家",
    "🏥 → 🏥 Hosp to Hosp": "🏥 → 🏥 医院到医院",

    # State restoration messages
    "Session expired. Returning to main menu.": "会话已过期。正在返回主菜单。",
    "Continuing with your previous action.": "正在继续您之前的操作。",
    "Could not restore previous action. Returning to main menu.": "无法恢复之前的操作。正在返回主菜单。",

    # Location request
    "Please share your current location:": "请分享您当前的位置：",
        
    # Body Text
    "I couldn't understand the time format. Please try entering the time again, or let me help you choose from available slots.": "我无法理解该时间格式。请重新输入时间，或让我帮您从可用时段中选择。",
    "Unfortunately {} is not available. The closest available time is {} (just {} minutes difference). Would you like to book this instead?": "很抱歉，{} 已被预约。最近的可用时间是 {}（仅相差 {} 分钟）。您想改约这个时间吗？",
    "Unfortunately {} is not available. The closest available time is {}. Would you like to book this instead?": "很抱歉，{} 已被预约。最近的可用时间是 {}。您想改约这个时间吗？",
    "No available slots near {}. Would you like to try a different time or let me help you choose from available slots?": "{} 附近没有可用时段。您想尝试其他时间，还是让我帮您从可用时段中选择？",
    "Error processing time. Please try again.": "处理时间时出错。请重试。",
    "Time slot not found. Please try again.": "未找到时间段。请重试。",
    "Error confirming time. Please try again.": "确认时间时出错。请重试。",
    "Error processing choice. Please try again.": "处理选择时出错。请重试。",
    "Error: No service selected. Please start over.": "错误：未选择服务。请重新开始。",
    "Do you have any remarks for {} ({} min){}?": "您对 {}（{} 分钟）{} 有什么备注吗？",
    "⚠️ *ERROR STARTING EMERGENCY*\n\nUnable to start emergency service. Please try again or call 999 immediately.": "⚠️ *紧急启动错误*\n\n无法启动紧急服务。请重试或立即拨打 999。",
    "⚠️ *ERROR STARTING EMERGENCY*\n\nAn error occurred. Please call 999 immediately for emergency assistance.": "⚠️ *紧急启动错误*\n\n发生错误。请立即拨打 999 寻求紧急援助。",
    "🚑 *EMERGENCY SERVICE*\n\nIs the patient's LIFE or FUNCTION at immediate risk?\n\nExamples of life-threatening emergencies:\n• Chest pain/heart attack\n• Severe difficulty breathing\n• Unconsciousness\n• Severe bleeding\n• Stroke symptoms\n• Major trauma/injury\n\nIf YES, ambulance will be dispatched immediately.\nIf NO, we'll collect more information first.": "🚑 *紧急服务*\n\n患者的生命或功能是否面临直接风险？\n\n危及生命的紧急情况示例：\n• 胸痛/心脏病发作\n• 严重呼吸困难\n• 昏迷\n• 严重出血\n• 中风症状\n• 重大创伤/受伤\n\n如果是，救护车将立即出动。\n如果否，我们将首先收集更多信息。",
    "📍 *LOCATION REQUIRED*\n\nWe need your current location to check if you're within our service area.\n\n**Please use one of these methods:**\n1. Tap 'Share Location' button below (recommended)\n2. Or type your address manually\n Example: No 12, Jalan Tun Razak, Kuala Lumpur\n\n**Important:**\n• Share exact location for distance check\n• Service area: Within 15km of our clinic\n• We'll notify you immediately if within range": "📍 *需要位置信息*\n\n我们需要您的当前位置来检查您是否在我们的服务范围内。\n\n**请使用以下方法之一：**\n1. 点击下方的\"分享位置\"按钮（推荐）\n2. 或者手动输入您的地址\n 例如：No 12, Jalan Tun Razak, Kuala Lumpur\n\n**重要提示：**\n• 分享准确位置以便进行距离检查\n• 服务范围：诊所方圆 15 公里内\n• 如果在范围内，我们将立即通知您",
    "❌ *ADDRESS NOT FOUND*\n\nWe couldn't find the address you provided.\n\n**Please try:**\n• A more specific address\n• Include city and state\n• Example: 'No 12, Jalan Tun Razak, Kuala Lumpur'\n\nOr use the 'Share Location' button for automatic detection.": "❌ *未找到地址*\n\n我们找不到您提供的地址。\n\n**请尝试：**\n• 更具体的地址\n• 包括城市和州属\n• 例如：'No 12, Jalan Tun Razak, Kuala Lumpur'\n\n或使用'分享位置'按钮进行自动检测。",
    "⚠️ *ERROR PROCESSING ADDRESS*\n\nThere was an error processing your address. Please try sharing your location instead.": "⚠️ *地址处理错误*\n\n处理您的地址时发生错误。请尝试分享您的位置。",
    "🚨 *DISTANCE ALERT*\n\nYour location is {} km away from our clinic.\n\n*Our Clinic Location:*\n{}\n\n*Service Radius:* 15 km\n*Your Distance:* {} km\n\n⚠️ *You are outside our service area.*\n\n**Please call 999 immediately for emergency assistance.**\n\nAlert ID: {}\nStatus: Referred to 999 emergency services": "🚨 *距离警报*\n\n您的位置距离我们的诊所 {} 公里。\n\n*我们的诊所地点：*\n{}\n\n*服务半径：* 15 公里\n*您的距离：* {} 公里\n\n⚠️ *您超出了我们的服务范围。*\n\n**请立即拨打 999 寻求紧急援助。**\n\n警报 ID：{}\n状态：已转至 999 紧急服务",
    "✅ *LOCATION CONFIRMED*\n\n*Address:* {}\n*Distance from clinic:* {} km\n*Status:* Within service area ✓\n\n🚨 *EMERGENCY TEAM NOTIFIED*\n\nAlert ID: {}\nTime: {}\n\nWe already notified the team, we will have the team departing ready, will update when departed...\n\n*STAY CALM AND DO NOT MOVE THE PATIENT* unless in immediate danger.\n\nMeanwhile could you please give more info...\nPlease answer the following questions one by one.\n\n---\n*QUESTIONS TO FOLLOW:*\n1. Relationship to patient\n2. Your name\n3. Your IC number\n4. Patient name (can type 'Nil' if unknown)\n5. Patient IC number (Nil for unknown)\n6. Patient condition details\n7. Medical history (if known)\n\nYou can cancel at any time by pressing the 'Cancel Ambulance' button.": "✅ *位置已确认*\n\n*地址：* {}\n*距离诊所：* {} 公里\n*状态：* 在服务范围内 ✓\n\n🚨 *紧急小组已收到通知*\n\n警报 ID：{}\n时间：{}\n\n我们已经通知了小组，我们将准备好出发，出发时会更新状态...\n\n*保持冷静，除非有直接危险，否则请勿移动患者。*\n\n同时，您能否提供更多信息...\n请逐一回答以下问题。\n\n---\n*后续问题：*\n1. 与患者的关系\n2. 您的姓名\n3. 您的身份证号码 (IC)\n4. 患者姓名（如不详可输入 'Nil'）\n5. 患者身份证号码（如不详可输入 'Nil'）\n6. 患者病情详情\n7. 病史（如有）\n\n您可以随时通过点击'取消救护车'按钮来取消。",
    "Select your relationship to the patient:": "请选择您与患者的关系：",
    "2. *Your name:*\n\nPlease type your full name.\n\nExample: Ali bin Ahmad or Siti binti Mohamad": "2. *您的姓名：*\n\n请输入您的全名。\n\n例如：Ali bin Ahmad 或 Siti binti Mohamad",
    "3. *Your IC number:*\n\nPlease type your IC number.\n\nExample: 901212-14-5678 or 950505-08-1234": "3. *您的身份证号码 (IC)：*\n\n请输入您的身份证号码。\n\n例如：901212-14-5678 或 950505-08-1234",
    "4. *Patient name:*\n\nPlease type the patient's full name.\n\nExample: Ahmad bin Abdullah or Nor Aishah binti Hassan\n\nYou can type 'Nil' if unknown": "4. *患者姓名：*\n\n请输入患者的全名。\n\n例如：Ahmad bin Abdullah 或 Nor Aishah binti Hassan\n\n如不详可输入 'Nil'",
    "🏠 *AMBULANCE SERVICE: HOME TO HOME TRANSFER*": "🏠 *救护车服务：家到家转运*",
    "Transfer ID:": "转运 ID：",
    "Time:": "时间：",
    "This service helps transfer patients between homes (e.g., moving to family home).": "此服务协助在不同住处之间转运患者（例如：搬去家属家中）。",
    "We'll collect information for your home-to-home transfer.": "我们将收集您的家到家转运信息。",
    "• Provide accurate addresses for both locations": "• 提供两个地点的准确地址",
    "• Ensure patient is stable for transfer": "• 确保患者情况稳定，适合转运",
    "• Have all necessary medical equipment ready": "• 准备好所有必要的医疗设备",
    "• Coordinate with family members at both locations": "• 与两个地点的家属做好协调",
    "*QUESTIONS TO FOLLOW:*": "*后续问题：*",
    "1. Patient full name": "1. 患者全名",
    "2. Patient IC number": "2. 患者身份证号码 (IC)",
    "3. Patient phone number": "3. 患者电话号码",
    "4. Emergency contact at pickup location": "4. 取车点的紧急联系人",
    "5. Emergency contact phone at pickup location": "5. 取车点紧急联系人的电话",
    "6. Current address (Pickup) with location sharing option": "6. 当前地址（取车点），包含分享位置选项",
    "7. Destination address (manual input)": "7. 目的地地址（手动输入）",
    "8. Reason for transfer": "8. 转运原因",
    "9. Medical condition": "9. 医疗状况",
    "*After these questions, we'll ask for destination emergency contact, attachments, and schedule.*": "*在这些问题之后，我们将询问目的地紧急联系人、附件和时间安排。*",
    "You can cancel anytime by typing 'cancel'.": "您可以随时输入 'cancel' 来取消。",
    "Error starting transfer request. Please try again.": "启动转运请求时出错。请重试。",
    "6. *Current address (Pickup)*": "6. *当前地址 (取车点)*",
    "How would you like to provide your current address?": "您想如何提供您的当前地址？",
    "• *Share Location:* Send your current location (recommended)": "• *分享位置：* 发送您的当前位置（推荐）",
    "• *Type Address:* Enter your full address manually": "• *输入地址：* 手动输入您的详细地址",
    "Example of manual address:": "手动输入地址示例：",
    "Please type your full current address:": "请输入您的完整当前地址：",
    "Include:": "包括：",
    "• House/building number": "• 门牌号/建筑编号",
    "• Street name": "• 街道名称",
    "• Area/Taman": "• 地区/住宅区 (Taman)",
    "• Postcode and City": "• 邮政编码和城市",
    "• State": "• 州属",
    "We found this address:": "我们找到了这个地址：",
    "Is this your correct pickup address?": "这是您正确的取车地址吗？",
    "7. *Destination address*": "7. *目的地地址*",
    "Please type the full destination address:": "请输入完整的目的地地址：",
    "8. *Reason for transfer*": "8. *转运原因*",
    "Please explain why you need this home-to-home transfer:": "请说明您为什么需要这次家到家转运：",
    "• Moving to family home for care": "• 搬到家属家中以便照顾",
    "• Returning from temporary stay": "• 从临时居所返回",
    "• Home modification needed": "• 房屋需要改建",
    "• Closer to medical facilities": "• 靠近医疗设施",
    "• Change of residence": "• 变更住所",
    "9. *Medical condition*": "9. *医疗状况*",
    "Please describe the patient's current medical condition:": "请描述患者当前的医疗状况：",
    "• Post-stroke recovery": "• 中风后康复",
    "• Mobility limited": "• 行动受限",
    "• Requires oxygen therapy": "• 需要氧气治疗",
    "• Stable condition for transfer": "• 状况稳定，可转运",
    "• Recent surgery": "• 近期手术",
    "Would you like to provide an emergency contact at the destination?": "您想提供目的地的紧急联系人吗？",
    "This is optional but recommended for better coordination at the destination location.": "这是可选的，但建议提供，以便在目的地进行更好的协调。",
    "Please provide the emergency contact name at the destination:": "请提供目的地的紧急联系人姓名：",
    "Example: Rahman bin Ali or Aishah binti Hassan": "例如：Rahman bin Ali 或 Aishah binti Hassan",
    "Please provide the emergency contact phone at the destination:": "请提供目的地的紧急联系人电话：",
    "Example: 012-3456789 or 019-8765432": "例如：012-3456789 或 019-8765432",
    "You can upload attachments (photos/documents) related to this transfer.": "您可以上传与此次转运相关的附件（照片/文件）。",
    "• Medical reports": "• 医疗报告",
    "• Doctor's clearance for transfer": "• 医生开具的转运许可",
    "• Insurance documents": "• 保险文件",
    "• Prescriptions": "• 处方",
    "You can upload multiple attachments. When done, click 'Next'.": "您可以上传多个附件。完成后点击 '下一步'。",
    "Error asking for attachments. Please try again.": "询问附件时出错。请重试。",
    "Do you have any additional remarks or special instructions?": "您是否有任何额外备注或特殊指令？",
    "• Specific route preferences": "• 特定路线偏好",
    "• Special medical equipment needed": "• 需要特殊医疗设备",
    "• Time constraints": "• 时间限制",
    "• Additional patient information": "• 额外的患者信息",
    "You can add remarks or skip to continue.": "您可以添加备注，或跳过以继续。",
    "Please type your remarks or special instructions:": "请输入您的备注或特殊指令：",
    "• Patient needs wheelchair assistance": "• 患者需要轮椅协助",
    "• Please use back entrance": "• 请使用后门",
    "• Patient is fasting": "• 患者正在禁食",
    "• Special handling requirements": "• 特殊处理要求",
    "Please select the {} date:": "请选择 {} 日期：",
    "*Today:*": "*今天：*",
    "*Tomorrow:*": "*明天：*",
    "If you need another date, select 'Others' and enter DD/MM/YYYY format.": "如果您需要其他日期，请选择'其他'并按 DD/MM/YYYY 格式输入。",
    "Error scheduling date. Please try again.": "安排日期时出错。请重试。",
    "Please select AM or PM for the transfer time:": "请选择转运时间的上午 (AM) 或下午 (PM)：",
    "Please select a 2-hour time slot for transfer:": "请选择2小时的转运时间段：",
    "Selected Date:": "已选日期：",
    "Period:": "时间段：",
    "After selecting a slot, you'll choose the exact 15-minute interval.": "选择时间段后，您将选择确切的15分钟间隔。",
    "Error selecting time. Please try again.": "选择时间时出错。请重试。",
    "🏥 *AMBULANCE SERVICE: HOSPITAL TO HOSPITAL TRANSFER*": "🏥 *救护车服务：医院到医院转运*",
    "This service helps transfer patients between hospitals for specialized care.": "此服务协助为了专业护理而在医院之间转运患者。",
    "We'll collect information for your inter-hospital transfer.": "我们将收集您的医院间转运信息。",
    "• Ensure both hospitals are aware of the transfer": "• 确保两家医院都知晓此次转运",
    "• Provide accurate hospital names": "• 提供准确的医院名称",
    "• We'll automatically find hospital addresses": "• 我们会自动查找医院地址",
    "• Have medical files ready for transfer": "• 准备好转运所需的医疗文件",
    "4. Emergency contact name": "4. 紧急联系人姓名",
    "5. Emergency contact phone": "5. 紧急联系人电话",
    "6. Current hospital name (we'll find the address)": "6. 当前医院名称（我们会查找地址）",
    "7. Ward number and level (e.g., Ward 5A, Level 3)": "7. 病房号和楼层（例如：Ward 5A, Level 3）",
    "8. Destination hospital name (we'll find the address)": "8. 目的地医院名称（我们会查找地址）",
    "*After these questions, you can upload attachments, add remarks, and schedule the transfer.*": "*在这些问题之后，您可以上传附件、添加备注并安排转运时间。*",
    "Please type the name of the current hospital:": "请输入当前医院的名称：",
    "We'll automatically find the address for you.": "我们会为您自动查找地址。",
    "We found this address for *{}*:": "我们找到了 *{}* 的这个地址：",
    "Is this the correct hospital address?": "这是正确的医院地址吗？",
    "Please type the current hospital address manually:": "请手动输入当前医院地址：",
    "Include full address with postcode and state.": "包括完整的地址、邮政编码和州属。",
    "7. *Ward number and level*": "7. *病房号和楼层*",
    "Please provide the ward number and level:": "请提供病房号和楼层：",
    "• Ward 5A, Level 3": "• Ward 5A, Level 3",
    "• ICU, Level 5": "• ICU, Level 5",
    "• Ward 3B, Ground Floor": "• Ward 3B, Ground Floor",
    "• Private Suite, Level 2": "• Private Suite, Level 2",
    "Enter both ward and level together.": "请同时输入病房和楼层。",
    "8. *Destination hospital name*": "8. *目的地医院名称*",
    "Please type the name of the destination hospital:": "请输入目的地医院的名称：",
    "Please type the destination hospital address manually:": "请手动输入目的地医院地址：",
    "• Doctor's referral letters": "• 医生转介信",
    "• Transfer forms": "• 转运表格",
    "• Patient requires ventilator during transfer": "• 患者在转运过程中需要呼吸机",
    "• Specific route preferred": "• 偏好特定路线",
    "• Need ambulance with ICU facilities": "• 需要配备 ICU 设施的救护车",
    "• Coordination with specific hospital staff": "• 与特定医院工作人员协调",
    "Please select the transfer date:": "请选择转运日期：",
    "Quantity: {}": "数量：{}",
    "Dosage: {}": "剂量：{}",
    "Method: {}": "方法：{}",
    "Take: {}": "服用方式：{}",
    "Purpose: {}": "目的：{}",
    "Note: {}": "备注：{}",
    "No details available": "暂无详情",
    "Duration: {} day{}": "持续时间：{} 天",
    "Frequency: {} time{}": "频率：{} 次",
    "Patient information not found. Please select a patient first.": "未找到患者信息。请先选择一位患者。",
    "No visits found for {}.": "未找到 {} 的就诊记录。",
    "No {} services available for this clinic. Please select another clinic or contact support.": "该诊所没有 {} 服务。请选择另一家诊所或联系客服。",
    "GP Visit Services": "全科医生 (GP) 就诊服务",
    "Checkup Services": "检查服务",
    "Vaccination Services": "疫苗接种服务",
    "Health Screening": "健康筛查",
    "Please select a {} service:": "请选择 {} 服务：",
    "GP, Checkup, Vaccination, Health Screening": "全科医生、检查、疫苗接种、健康筛查",
    "Chiro, Physio, Rehab, Traditional Medicine": "整脊、理疗、康复、传统医学",
    "Non-emergency medical transport": "非紧急医疗转运",
    "Coming soon": "即将推出",
    "Service Booking": "服务预约",
    "Location received. However, location sharing is not expected in this context. Please use the menu buttons provided for selection.": "已收到位置信息。但在此情景下不需要分享位置。请使用提供的菜单按钮进行选择。",
    "Error processing location. Please try again.": "处理位置时出错。请重试。",
    "File received. However, file upload is not expected in this context. Please use the menu buttons provided for selection.": "已收到文件。但在此情景下不需要上传文件。请使用提供的菜单按钮进行选择。",
    "Error processing file. Please try again.": "处理文件时出错。请重试。",
    "No patient profiles found. Please contact clinic to create a profile.": "未找到患者资料。请联系诊所创建资料。",
    "What would you like to view?": "您想查看什么？",
    "Available Options": "可用选项",
    "View diagnosed conditions": "查看诊断出的病情",
    "View all medications and items": "查看所有药物和物品",
    "Select visit for MC, Invoice, etc.": "为病假单、发票等选择就诊记录。",
    "No disease diagnoses found for this patient.": "未发现该患者的疾病诊断。",
    "⚔️ **ENEMY (DISEASE) for {}**": "⚔️ **{} 的敌人 (疾病)**",
    "📞 Contact your clinic for more information.": "📞 请联系您的诊所了解更多信息。",
    "Error loading disease information. Please try again.": "加载疾病信息时出错。请重试。",
    "Medication & Routine module is currently unavailable. Please try again later.": "药物与常规模块目前不可用。请稍后再试。",
    "Error loading medication details. Please try again.": "加载药物详情时出错。请重试。",
    "Error loading visiting history. Please try again.": "加载就诊记录时出错。请重试。",
    
    # Additional translations from second list
    "📍 Pickup Address": "📍 取车地址",
    "📍 Home Address": "📍 家庭地址",
    "📍 Home Address Found": "📍 找到家庭地址",
    "📅 Select Pickup Date": "📅 选择取车日期",
    "📅 Select Discharge Date": "📅 选择出院日期",
    "⏱️ Select 15-Minute Interval": "⏱️ 选择15分钟间隔",
    "🏥 Hospital Address Found": "🏥 找到医院地址",
    "Symptom Tracker": "症状追踪",
    "Your Follow-up Entries": "您的随访记录",
    "🔄 Return Service": "🔄 返程服务",
    "Track your recovery progress": "追踪您的康复进度",
    "Select Entry": "选择记录",
    "Edit": "修改",
    "Select Time": "选择时间",
    "Error loading patient profiles. Please try again.": "加载患者资料时出错。请重试。",
    "Error loading options. Please try again.": "加载选项时出错。请重试。",
    "Hi {},\n\nHow are you feeling after your recent visit?": "您好 {}，最近一次就诊后您感觉如何？",
    "Hi {},\n\nIt's been a day since your visit. How are you feeling?": "您好 {}，距离您的就诊已经过去一天了。您今天感觉如何？",
    "Hi {},\n\nChecking in again 1 week later. How is your condition now?": "您好 {}，一周后再次随访。您现在的状况如何？",
    "Glad to hear you are better! Take care.": "很高兴听到您好转了！请保重。",
    "Noted. We will check on you again in 1 week. If urgent, please visit the clinic.": "收到。我们将在1周后再次随访。如果情况紧急，请前往诊所就医。",
    "Thanks, glad to hear you are better!": "谢谢，很高兴听到您好转了！",
    "Ok, please contact the clinic if you need assistance.": "好的，如需帮助请联系诊所。",
    "The clinic will contact you. If urgent, please call the clinic.": "诊所将会联系您。如果情况紧急，请致电诊所。",
    "Thank you for your response.": "感谢您的回应。",
    "You don't have any follow-up entries to track symptoms for.": "您没有可以追踪症状的随访记录。",
    "Select the follow-up entry you want to update symptoms for:": "请选择您想要更新症状的随访记录：",
    "Time slot not available": "该时段不可用",
    "📅 *AMBULANCE SERVICE: HOME TO HOSPITAL*": "📅 *救护车服务：从家到医院*",
    "We'll collect information for your ambulance booking.": "我们将收集您的救护车预约信息。",
    "*After these questions, we'll ask for attachments and schedule pickup.*": "*在这些问题之后，我们将询问附件并安排取车。*",
    "6. *Pickup address (Home address)*": "6. *取车地址 (家庭地址)*",
    "How would you like to provide your pickup address?": "您想如何提供您的取车地址？",
    "Please type your full pickup address:": "请输入您的完整取车地址：",
    "You can upload attachments (photos/documents) related to this booking.": "您可以上传与此预约相关的附件（照片/文件）。",
    "Do you need return service (from hospital back to home)?": "您需要返程服务吗（从医院回抵家中）？",
    "✅ *Return service added*": "✅ *已添加返程服务*",
    "Please select AM or PM for the pickup time Close to the clinic.": "请选择靠近诊所的取车时间的上午 (AM) 或下午 (PM)：",
    "Please select a 2-hour time slot for pickup:": "请选择2小时的取车时间段：",
    "Please select the exact pickup time:": "请选择确切的取车时间：",
    "Please provide a valid answer.": "请提供有效的回答。",
    "❌ *Invalid IC number format*": "❌ *身份证号码格式无效*",
    "Please re-enter the patient's IC number:": "请重新输入患者的身份证号码：",
    "❌ Unsupported file type.": "❌ 不支持的文件类型。",
    "Error: Could not get file information. Please try again.": "错误：无法获取文件信息。请重试。",
    "❌ Failed to download file from WhatsApp.": "❌ 无法从 WhatsApp 下载文件。",
    "✅ *Attachment successfully saved!*": "✅ *附件已成功保存！*",
    "❌ Failed to save attachment.": "❌ 附件保存失败。",
    "Please enter the pickup date in DD/MM/YYYY format:": "请按 DD/MM/YYYY 格式输入取车日期：",
    "Date cannot be in the past.": "日期不能是过去的日期。",
    "✅ *AMBULANCE BOOKING CONFIRMED*": "✅ *救护车预约已确认*",
    "Thank you for using AnyHealth Ambulance Service! 🚑": "感谢您使用 AnyHealth 救护车服务！🚑",
    "🏥 *AMBULANCE SERVICE: HOSPITAL TO HOME*": "🏥 *救护车服务：从医院到家*",
    "Request ID:": "请求 ID：",
    "This service helps transport patients from hospital to home after discharge.": "此服务协助患者在出院后从医院转运回家。",
    "7. Ward number and level number": "7. 病房号和楼层号",
    "8. Home location (with location sharing option)": "8. 家庭位置（包含位置分享选项）",
    "*After these questions, we'll ask for attachments, remarks, and schedule discharge.*": "*在这些问题之后，我们将询问附件、备注并安排出院转运。*",
    "7. *Ward number and level number*": "7. *病房号和楼层号*",
    "Please provide the ward and bed number:": "请提供病房和床位号：",
    "8. *Home address*": "8. *家庭地址*",
    "How would you like to provide your home address?": "您想如何提供您的家庭地址？",
    "Please type your full home address:": "请输入您的完整家庭地址：",
    "Is this your correct home address?": "这是您正确的家庭地址吗？",
    "You can upload attachments (photos/documents) related to this discharge.": "您可以上传与此次出院转运相关的附件（照片/文件）。",
    "Discharge summary": "出院小结",
    "Please select AM or PM for the discharge time:": "请选择出院转运时间的上午 (AM) 或下午 (PM)：",
    "Please select a 2-hour time slot for discharge:": "请选择2小时的出院转运时间段：",
    "Please select the exact discharge time:": "请选择确切的出院转运时间：",
    "Discharge request cancelled. Returning to main menu.": "出院转运请求已取消。正在返回主菜单。",
    "Please share your home location using the button below:": "请使用下方的按钮分享您的家庭位置：",
    "✅ *Home address confirmed!*": "✅ *家庭地址已确认！*",
    "Please type the corrected home address:": "请输入修改后的家庭地址：",
    "🔍 Searching for *{}*...": "🔍 正在搜索 *{}*...",
    "❌ Could not find address for *{}*": "❌ 找不到 *{}* 的地址",
    "Please provide the address manually.": "请手动提供地址。",
    "✅ *DISCHARGE TRANSPORT CONFIRMED*": "✅ *出院转运已确认*",
    
    # Menu selection buttons
    "Back to Home": "返回首页",
    "Select Visit": "选择就诊记录",
    
    # Footer/status messages
    "{} confirmed booking(s)": "{} 个已确认预约",
    "Returning to main menu.": "正在返回主菜单。",
    "No documents available for this visit.": "此就诊记录没有可用文件。",
    
    # Medication module headers
    "💊 *ALL MEDICATIONS & ITEMS for {}*": "💊 *{} 的所有药物和物品*",
    "No medications or items found for any visit.": "任何就诊记录中均未找到药物或物品。",
    "*📊 Summary: {} total items across {} visits*": "*📊 总结：{} 个总物品，来自 {} 次就诊*",
    "📞 *Contact your clinic if you have any questions.*": "📞 *如有任何疑问，请联系您的诊所。*",
    
    # Ambulance service translations
    "Booking ID: {}": "预约 ID：{}",
    "This service helps patients travel from home to hospital for appointments.": "此服务协助患者从家前往医院就诊。",
    "我们将收集您的救护车预约信息。": "我们将收集您的救护车预约信息。",
    "请逐一回答以下问题。": "请逐一回答以下问题。",
    "• Please provide accurate information": "• 请提供准确信息",
    "• For addresses, include full address with postcode": "• 对于地址，请提供包含邮政编码的完整地址",
    "• After answering all questions, you can upload documents/attachments": "• 回答完所有问题后，您可以上传文件/附件",
    "7. Hospital name (we'll find the address automatically)": "7. 医院名称（我们将自动查找地址）",
    "Please share your location using the button below:": "请使用下方的按钮分享您的位置：",
    "1. Tap the location icon 📍": "1. 点击位置图标 📍",
    "2. Select 'Share Location'": "2. 选择'分享位置'",
    "3. Choose 'Send your current location'": "3. 选择'发送您当前的位置'",
    "✅ Pickup address confirmed!": "✅ 取车地址已确认！",
    "Now let's proceed to hospital details.": "现在让我们继续填写医院详情。",
    "7. Hospital name": "7. 医院名称",
    "Please type the name of the hospital:": "请输入医院名称：",
    "* Hospital Kuala Lumpur": "* 吉隆坡医院",
    "* Sunway Medical Centre": "* 双威医疗中心",
    "* Pantai Hospital Kuala Lumpur": "* 班台医院吉隆坡",
    "* University Malaya Medical Centre": "* 马来亚大学医疗中心",
    "我们会为您自动查找地址。": "我们会为您自动查找地址。",

    # Notifications.py
    "Your checkup booking is confirmed on ": "您的体检预约已确认，时间：",
    "Your consultation booking is confirmed on ": "您的咨询预约已确认，时间：",
    "Your vaccination booking for {} is confirmed on ": "您的{}疫苗接种预约已确认，时间：",
    # TCM booking confirmations  
    "Your TCM {} booking is confirmed on ": "您的传统医疗{}预约已确认，时间：",
    # Repeated visit confirmations
    "Your repeated visit for {} {} bookings are confirmed on ": "您的{}次{}重复就诊预约已确认，时间：",
    "Your repeated visit for {} TCM {} bookings are confirmed on ": "您的{}次传统医疗{}重复就诊预约已确认，时间：",
    # Reminder messages
    "Reminder: Your repeated visit for {} {} bookings is in ": "提醒：您的{}次{}重复就诊预约将在",
    "Reminder: Your {} is in ": "提醒：您的{}将在",
    "Custom reminder: Your repeated visit for {} {} bookings is in ": "自定义提醒：您的{}次{}重复就诊预约将在",
    "Custom reminder: Your {} is in ": "自定义提醒：您的{}将在",
    "Reminder: Your repeated visit for {} TCM {} bookings is in ": "提醒：您的{}次传统医疗{}重复就诊预约将在",
    "Reminder: Your TCM {} is in ": "提醒：您的传统医疗{}将在",
    "Custom reminder: Your repeated visit for {} TCM {} bookings is in ": "自定义提醒：您的{}次传统医疗{}重复就诊预约将在",
    "Custom reminder: Your TCM {} is in ": "自定义提醒：您的传统医疗{}将在",
    # Report notifications
    "Report ready for {}: {}": "{}的报告已就绪：{}",
    "Report ready: {}": "报告已就绪：{}",
    
    # ========== NEW TRANSLATIONS FROM PROVIDED DICTIONARY ==========
    
    # From post_report.py
    "Past Consultations": "过去的咨询",
    "Select a consultation to request report:": "选择一个咨询以请求报告：",
    "🔙 Back": "🔙 返回",
    
    # From ambulance_emergency.py
    "⚠️ *ERROR COMPLETING EMERGENCY*\n\nPlease try again or call 999 immediately.": "⚠️ *完成紧急请求时出错*\n\n请重试或立即拨打 999。",
    "⚠️ *ERROR SAVING HEALTH CONDITION*\n\nPlease try again.": "⚠️ *保存健康状况时出错*\n\n请重试。",
    "⚠️ *AN ERROR OCCURRED*\n\nPlease try again or call 999 immediately for emergency assistance.": "⚠️ *发生错误*\n\n请重试或立即拨打 999 寻求紧急援助。",
    "⚠️ *EMERGENCY AMBULANCE*\n\nIs this a life-threatening emergency? (e.g., heart attack, severe bleeding, unconscious)": "⚠️ *紧急救护车*\n\n这是否是危及生命的紧急情况？（例如：心脏病发作、严重出血、昏迷）",
    "⚠️ *NON-LIFE-THREATENING*\n\nFor non-critical cases, please use our standard booking service.": "⚠️ *非危及生命*\n\n对于非危急情况，请使用我们的标准预约服务。",
    "⚠️ *LIFE-THREATENING EMERGENCY*\n\nPlease call 999 immediately!\n\nFor clinic transport, continue below.": "⚠️ *危及生命的紧急情况*\n\n请立即拨打 999！\n\n如需诊所转运，请继续下方操作。",
    "⚠️ *EMERGENCY LOCATION*\n\nPlease share your exact location:": "⚠️ *紧急位置*\n\n请分享您的确切位置：",
    "⚠️ *ERROR GETTING LOCATION*\n\nPlease try again or enter your address manually.": "⚠️ *获取位置时出错*\n\n请重试或手动输入您的地址。",
    "⚠️ *LOCATION RECEIVED*\n\nAddress: {}\n\nDistance from clinic: {} km\n\nIs this correct?": "⚠️ *位置已收到*\n\n地址：{}\n\n距离诊所：{} 公里\n\n是否正确？",
    "⚠️ *INVALID LOCATION*\n\nLocation must be within {}km of clinic.\n\nPlease share accurate location.": "⚠️ *无效位置*\n\n位置必须在诊所 {} 公里范围内。\n\n请分享准确位置。",
    "⚠️ *LOCATION CONFIRMED*\n\nPatient Name:": "⚠️ *位置已确认*\n\n患者姓名：",
    "⚠️ *ERROR SAVING NAME*\n\nPlease try again.": "⚠️ *保存姓名时出错*\n\n请重试。",
    "⚠️ *PATIENT NAME SAVED*\n\nPatient IC (YYMMDD-XX-XXXX):": "⚠️ *患者姓名已保存*\n\n患者身份证（YYMMDD-XX-XXXX）：",
    "⚠️ *INVALID IC*\n\nPlease enter valid IC format.": "⚠️ *无效身份证*\n\n请输入有效的身份证格式。",
    "⚠️ *ERROR SAVING IC*\n\nPlease try again.": "⚠️ *保存身份证时出错*\n\n请重试。",
    "⚠️ *IC SAVED*\n\nPatient Phone:": "⚠️ *身份证已保存*\n\n患者电话：",
    "⚠️ *ERROR SAVING PHONE*\n\nPlease try again.": "⚠️ *保存电话时出错*\n\n请重试。",
    "⚠️ *PHONE SAVED*\n\nEmergency Contact Name:": "⚠️ *电话已保存*\n\n紧急联系人姓名：",
    "⚠️ *ERROR SAVING EMERGENCY NAME*\n\nPlease try again.": "⚠️ *保存紧急联系人姓名时出错*\n\n请重试。",
    "⚠️ *EMERGENCY NAME SAVED*\n\nEmergency Contact Phone:": "⚠️ *紧急联系人姓名已保存*\n\n紧急联系人电话：",
    "⚠️ *ERROR SAVING EMERGENCY PHONE*\n\nPlease try again.": "⚠️ *保存紧急联系人电话时出错*\n\n请重试。",
    "⚠️ *EMERGENCY PHONE SAVED*\n\nHealth Condition:": "⚠️ *紧急联系人电话已保存*\n\n健康状况：",
    "⚠️ *EMERGENCY REQUEST SUBMITTED*\n\nAlert ID: {}\nPatient: {}\nIC: {}\nPhone: {}\nEmergency: {} ({})\nLocation: {}\nDistance: {} km\nCondition: {}\n\nAmbulance ETA: ~{} min\n\nStay on line for updates.\n\nIf critical, call 999!": "⚠️ *紧急请求已提交*\n\n警报 ID：{}\n患者：{}\n身份证：{}\n电话：{}\n紧急联系人：{}（{}）\n位置：{}\n距离：{} 公里\n状况：{}\n\n救护车预计到达时间：约 {} 分钟\n\n请保持在线以获取更新。\n\n如果情况危急，请拨打 999！",
    "⚠️ *ERROR SUBMITTING EMERGENCY*\n\nPlease try again or call 999.": "⚠️ *提交紧急请求时出错*\n\n请重试或拨打 999。",

    # From clinicfd.py
    "Clinic enquiry cancelled.": "诊所咨询已取消。",
    "An error occurred. Returning to main menu.": "发生错误。返回主菜单。",

    # From individual_med_rout.py
    "Quantity:": "数量：",
    "Dosage:": "剂量：",
    "Method:": "方法：",
    "Timing:": "时间：",
    "Duration:": "持续时间：",
    "Notes:": "备注：",
    "No medications found for this consultation.": "此咨询未找到药物。",
    "Medication:": "药物：",
    "No medication details available.": "无药物详情可用。",
    "No routines found for this consultation.": "此咨询未找到常规。",
    "Routines:": "常规：",
    "No routine details available.": "无常规详情可用。",

    # From individualedit.py
    "⚠️ *DETACH FROM OLD NUMBER*\n\nThis will:\n1. Remove a profile from old WhatsApp\n2. Free it for attachment to new number\n3. Requires verification of profile details\n\nAfter detachment, contact clinic/email to attach to new number.": "⚠️ *从旧号码分离*\n\n这将：\n1. 从旧 WhatsApp 移除个人资料\n2. 释放以便附加到新号码\n3. 需要验证个人资料详情\n\n分离后，请联系诊所/电子邮件以附加到新号码。",
    "Please enter the 12-digit IC of the profile to detach:": "请输入要分离的个人资料的12位身份证：",
    "An error occurred in edit module. Please try again.": "编辑模块发生错误。请重试。",

    # From report_symptoms.py
    "Please enter your additional remarks:": "请输入您的附加备注：",

    # From ReportBooking.py
    "No report available yet. Please check back later.": "报告尚不可用。请稍后检查。",
    "Error sending report. Please try again.": "发送报告时出错。请重试。",
    "Report sent successfully.": "报告发送成功。",
    "Consultation": "咨询",
    "Back to Main Menu": "返回主菜单",
    "PDF Request": "PDF 请求",
    "Consultation after PDF?": "PDF 后咨询？",
    "Error fetching doctor's clinic:": "获取医生诊所时出错：",
    "Report Review: {}": "报告审查：{}",

    # From calendar_utils.py
    "Please select a doctor:": "请选择一位医生：",
    "Enter Future Date": "输入未来日期",
    "No available dates in the next 7 days.": "接下来7天内没有可用日期。",
    "Error loading calendar. Please try again.": "加载日历时出错。请重试。",
    "Selected Doctor: {}": "已选择医生：{}",
    "Please select a period:": "请选择一个时间段：",
    "Time Periods": "时间段",
    "Morning": "上午",
    "Afternoon": "下午",
    "Evening": "晚上",
    "No available periods on {}.": "{} 没有可用时间段。",
    "Error loading periods. Please try again.": "加载时间段时出错。请重试。",
    "Selected Period: {}": "已选择时间段：{}",
    "No available hours in {} on {}.": "{} 的 {} 没有可用小时。",
    "Error loading hours. Please try again.": "加载小时时出错。请重试。",
    "Selected Hour: {}": "已选择小时：{}",
    "No available slots at {} on {}.": "{} 的 {} 没有可用时间段。",
    "Error loading slots. Please try again.": "加载时间段时出错。请重试。",
    "✅ BOOKING CONFIRMED!\n\n{} with Dr. {}\nDate: {}\nTime: {} ({}min)\n\nStatus: PENDING APPROVAL\n\nYou'll be notified when confirmed.": "✅ 预约已确认！\n\n{} 与 {} 医生\n日期：{}\n时间：{}（{}分钟）\n\n状态：待批准\n\n确认后将通知您。",
    "Error confirming booking. Please try again.": "确认预约时出错。请重试。",
    "Invalid date format. Please use DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY.": "无效日期格式。请使用 DD/MM/YYYY、DD-MM-YYYY 或 DD MM YYYY。",
    "Date must be in the future. Please enter a valid future date.": "日期必须在未来。请输入有效的未来日期。",
    "No availability on {}. Please choose another date.": "{} 没有可用时间。请选择其他日期。",
    "No, Change Date": "不，更改日期",
    "Date confirmed: {}": "日期已确认：{}",
    "Invalid time format. Please enter time like 9:30, 2pm, or 1430.": "无效时间格式。请输入时间，如 9:30、2pm 或 1430。",
    "No availability at requested time. Closest available: {}. Proceed?": "请求时间无可用时间。最近可用时间：{}。继续吗？",
    "Get Help Choosing": "获取选择帮助",
    "Time confirmed: {}": "时间已确认：{}",
    "What would you like to edit?": "您想编辑什么？",
    "Edit Options": "编辑选项",
    "Change Doctor": "更改医生",
    "Change Date": "更改日期",
    "Change Time": "更改时间",
    "Change Remarks": "更改备注",
    "Cancel Booking": "取消预约",

    # From ambulance_booking.py
    "⚠️ *AMBULANCE BOOKING*\n\nThis is for non-emergency transport.\nFor emergencies, call 999.": "⚠️ *救护车预约*\n\n这是用于非紧急转运。\n对于紧急情况，请拨打 999。",
    "⚠️ *AMBULANCE TYPE*\n\nChoose service:": "⚠️ *救护车类型*\n\n选择服务：",
    "Home to Hospital": "家到医院",
    "Hospital to Home": "医院到家",
    "Hospital Discharge": "医院出院",
    "Hospital to Hospital": "医院到医院",
    "Home to Home": "家到家",
    "⚠️ *BOOKING STARTED*\n\nPlease answer step by step.\nType 'cancel' anytime to stop.": "⚠️ *预约开始*\n\n请逐步回答。\n随时输入 'cancel' 停止。",
    "⚠️ *AMBULANCE BOOKING CANCELLED*\n\nReturned to main menu.": "⚠️ *救护车预约已取消*\n\n已返回主菜单。",
    "⚠️ *INVALID INPUT*\n\nPlease answer the question.": "⚠️ *无效输入*\n\n请回答问题。",
    "⚠️ *ERROR PROCESSING*\n\nPlease try again.": "⚠️ *处理错误*\n\n请重试。",
    "⚠️ *PICKUP LOCATION*\n\nPlease share your pickup location:": "⚠️ *取车位置*\n\n请分享您的取车位置：",
    "⚠️ *LOCATION RECEIVED*\n\nAddress: {}\n\nIs this correct?": "⚠️ *位置已收到*\n\n地址：{}\n\n是否正确？",
    "⚠️ *LOCATION CONFIRMED*\n\nPlease select a hospital:": "⚠️ *位置已确认*\n\n请选择一家医院：",
    "Hospitals": "医院",
    "No hospitals found. Please try again.": "未找到医院。请重试。",
    "⚠️ *HOSPITAL SELECTED*\n\n{} ({} km)\n\nReturn service needed?": "⚠️ *医院已选择*\n\n{}（{} 公里）\n\n需要返程服务吗？",
    "⚠️ *RETURN SERVICE*\n\nPlease select return date:": "⚠️ *返程服务*\n\n请选择返程日期：",
    "Return Dates": "返程日期",
    "⚠️ *RETURN DATE SELECTED*\n\n{}": "⚠️ *返程日期已选择*\n\n{}",
    "⚠️ *RETURN TIME*\n\nSelect return time period:": "⚠️ *返程时间*\n\n选择返程时间段：",
    "⚠️ *RETURN TIME SELECTED*\n\n{}": "⚠️ *返程时间已选择*\n\n{}",
    "⚠️ *NO RETURN*\n\nProceed to health condition.": "⚠️ *无返程*\n\n继续健康状况。",
    "⚠️ *HEALTH CONDITION*\n\nDescribe patient's condition:": "⚠️ *健康状况*\n\n描述患者状况：",
    "⚠️ *HEALTH CONDITION SAVED*\n\nAdd attachments? (e.g., reports)": "⚠️ *健康状况已保存*\n\n添加附件吗？（例如：报告）",
    "Add Attachments": "添加附件",
    "No Attachments": "无附件",
    "⚠️ *ATTACHMENTS*\n\nSend up to 3 files (images/PDFs).\nType 'done' when finished.": "⚠️ *附件*\n\n最多发送 3 个文件（图像/PDF）。\n完成后输入 'done'。",
    "⚠️ *FILE RECEIVED*\n\n{} saved.\n\nSend more or type 'done'.": "⚠️ *文件已收到*\n\n{} 已保存。\n\n发送更多或输入 'done'。",
    "⚠️ *ERROR SAVING FILE*\n\nPlease try again.": "⚠️ *保存文件时出错*\n\n请重试。",
    "⚠️ *NO ATTACHMENTS*\n\nProceed to remarks.": "⚠️ *无附件*\n\n继续备注。",
    "⚠️ *REMARKS*\n\nAny additional remarks?": "⚠️ *备注*\n\n有任何附加备注吗？",
    "⚠️ *REMARKS SAVED*\n\nPlease select booking date:": "⚠️ *备注已保存*\n\n请选择预约日期：",
    "Booking Dates": "预约日期",
    "⚠️ *DATE SELECTED*\n\n{}": "⚠️ *日期已选择*\n\n{}",
    "⚠️ *TIME PERIOD*\n\nSelect time period:": "⚠️ *时间段*\n\n选择时间段：",
    "⚠️ *TIME SELECTED*\n\n{}": "⚠️ *时间已选择*\n\n{}",
    "✅ *AMBULANCE BOOKING CONFIRMED*\n\nBooking ID: {}\nPatient: {}\nIC: {}\nPhone: {}\nEmergency: {} ({})\nFrom: {}\nTo: {}\nDate: {}\nTime: {}\n*Estimated Distance:* {} km\n*Attachments:* {}\n*Remarks:* {}\n*Return Service:* {}\n\nOur team will contact you to confirm details.\n\n*Next Steps:*\n1. Team will verify details\n2. You'll receive confirmation call\n3. Ambulance will arrive 30 minutes before pickup\n\nThank you for using AnyHealth Ambulance Service! 🚑": "✅ *救护车预约已确认*\n\n预约 ID：{}\n患者：{}\n身份证：{}\n电话：{}\n紧急联系人：{}（{}）\n从：{}\n到：{}\n日期：{}\n时间：{}\n*预计距离：* {} 公里\n*附件：* {}\n*备注：* {}\n*返程服务：* {}\n\n我们的团队将联系您确认详情。\n\n*后续步骤：*\n1. 团队将验证详情\n2. 您将收到确认电话\n3. 救护车将在取车前 30 分钟到达\n\n感谢您使用 AnyHealth 救护车服务！🚑",

    # From view_booking.py
    "❌ SYSTEM ERROR\n\nAn error occurred in the booking system. Please try again.": "❌ 系统错误\n\n预约系统发生错误。请重试。",
    "Upcoming Bookings (Page {} of {})": "即将到来的预约（第 {} 页，共 {} 页）",
    "Previous Page": "上一页",
    "Next Page": "下一页",
    "Back to Menu": "返回菜单",
    "No details available.": "无详情可用。",
    "Booking Details:\nType: {}\nDoctor: {}\nDate: {}\nTime: {}\nStatus: {}\n\nWhat would you like to do?": "预约详情：\n类型：{}\n医生：{}\n日期：{}\n时间：{}\n状态：{}\n\n您想做什么？",
    "Actions": "操作",
    "Back": "返回",
    "Error cancelling booking: {}": "取消预约时出错：{}",
    "Booking cancelled successfully.": "预约已成功取消。",
    "This is a repeated booking series. Cancel all future visits?": "这是一个重复预约系列。取消所有未来访问吗？",
    "Cancel All": "全部取消",
    "Cancel This Only": "仅取消此个",
    "Error cancelling repeated bookings: {}": "取消重复预约时出错：{}",
    "All future repeated bookings cancelled.": "所有未来重复预约已取消。",
    "This booking cancelled. Future repeats remain.": "此预约已取消。未来重复预约保留。",
    "Cancellation cancelled.": "取消已取消。",
    "This is a repeated booking series. Reschedule all future visits?": "这是一个重复预约系列。重新安排所有未来访问吗？",
    "Reschedule All": "全部重新安排",
    "Reschedule This Only": "仅重新安排此个",
    "Error rescheduling repeated bookings: {}": "重新安排重复预约时出错：{}",
    "All future repeated bookings rescheduled.": "所有未来重复预约已重新安排。",
    "This booking rescheduled. Future repeats unchanged.": "此预约已重新安排。未来重复预约未更改。",
    "Reschedule cancelled.": "重新安排已取消。",
    "Confirm reschedule to {} at {}?": "确认重新安排到 {} 的 {} 吗？",
    "Error rescheduling: {}": "重新安排时出错：{}",
    "Booking rescheduled successfully.": "预约已成功重新安排。",

    # From healthsp.py
    "Health Screening Plan": "健康筛查计划",
    "Please select a screening package:": "请选择一个筛查套餐：",
    "Screening Packages": "筛查套餐",
    "Error loading packages. Please try again.": "加载套餐时出错。请重试。",
    "No packages available. Please try again later.": "无可用套餐。请稍后重试。",
    "Selected Package: {}": "已选择套餐：{}",
    
    # From ambulance_homehome.py
    "⚠️ *HOME TRANSFER STARTED*\n\nPlease answer step by step.\nType 'cancel' anytime to stop.": "⚠️ *家到家中转开始*\n\n请逐步回答。\n随时输入 'cancel' 停止。",
    "⚠️ *DROP-OFF RECEIVED*\n\nAddress: {}\nDistance: {} km\n\nCorrect?": "⚠️ *下车位置已收到*\n\n地址：{}\n距离：{} 公里\n\n是否正确？",
    "⚠️ *DROP-OFF CONFIRMED*\n\nPlease select date:": "⚠️ *下车位置已确认*\n\n请选择日期：",
    "Dates": "日期",
    "⚠️ *DATE SELECTED*\n\n{}": "⚠️ *日期已选择*\n\n{}",
    "⚠️ *TIME PERIOD*\n\nSelect time period:": "⚠️ *时间段*\n\n选择时间段：",
    "⚠️ *TIME SELECTED*\n\n{}": "⚠️ *时间已选择*\n\n{}",
    "⚠️ *REMARKS SAVED*\n\nReview summary:": "⚠️ *备注已保存*\n\n查看摘要：",
    "✅ *HOME TRANSFER CONFIRMED*\n\nTransfer ID: {}\nPatient: {}\nIC: {}\nPhone: {}\nEmergency: {} ({})\nFrom: {}\nTo: {}\nDate: {}\nTime: {}\n*Estimated Distance:* {} km\n*Attachments:* {}\n*Remarks:* {}\n\nOur team will contact you to arrange details.\n\n*Next Steps:*\n1. Team will verify details\n2. You'll receive confirmation call\n3. Ambulance will arrive 30 minutes before pickup\n\nThank you for using AnyHealth Ambulance Service! 🚑": "✅ *家到家中转已确认*\n\n中转 ID：{}\n患者：{}\n身份证：{}\n电话：{}\n紧急联系人：{}（{}）\n从：{}\n到：{}\n日期：{}\n时间：{}\n*预计距离：* {} 公里\n*附件：* {}\n*备注：* {}\n\n我们的团队将联系您安排详情。\n\n*后续步骤：*\n1. 团队将验证详情\n2. 您将收到确认电话\n3. 救护车将在取车前 30 分钟到达\n\n感谢您使用 AnyHealth 救护车服务！🚑",

    # From ambulance_hosphosp.py
    "⚠️ *HOSPITAL TRANSFER STARTED*\n\nPlease answer step by step.\nType 'cancel' anytime to stop.": "⚠️ *医院中转开始*\n\n请逐步回答。\n随时输入 'cancel' 停止。",
    "⚠️ *FROM HOSPITAL*\n\nPlease select pickup hospital:": "⚠️ *从医院*\n\n请选择取车医院：",
    "⚠️ *FROM SELECTED*\n\n{}": "⚠️ *从已选择*\n\n{}",
    "⚠️ *WARD/BED*\n\nEnter ward and bed:": "⚠️ *病房/床位*\n\n输入病房和床位：",
    "⚠️ *WARD SAVED*\n\nTo hospital:": "⚠️ *病房已保存*\n\n到医院：",
    "⚠️ *TO SELECTED*\n\n{} ({} km)": "⚠️ *到已选择*\n\n{}（{} 公里）",
    "✅ *HOSPITAL TRANSFER CONFIRMED*\n\nTransfer ID: {}\nPatient: {}\nIC: {}\nPhone: {}\nEmergency: {} ({})\nFrom: {}\nWard: {}\nTo: {}\nScheduled: {}\n*Estimated Distance:* {} km\n*Attachments:* {}\n*Remarks:* {}\n\nOur team will contact you to arrange details.\n\n*Next Steps:*\n1. Team will verify details\n2. You'll receive confirmation call\n3. Ambulance will arrive 30 minutes before pickup\n\nThank you for using AnyHealth Ambulance Service! 🚑": "✅ *医院中转已确认*\n\n中转 ID：{}\n患者：{}\n身份证：{}\n电话：{}\n紧急联系人：{}（{}）\n从：{}\n病房：{}\n到：{}\n预定时间：{}\n*预计距离：* {} 公里\n*附件：* {}\n*备注：* {}\n\n我们的团队将联系您安排详情。\n\n*后续步骤：*\n1. 团队将验证详情\n2. 您将收到确认电话\n3. 救护车将在取车前 30 分钟到达\n\n感谢您使用 AnyHealth 救护车服务！🚑",

    # From ambulance_discharge.py
    "⚠️ *DISCHARGE STARTED*\n\nPlease answer step by step.\nType 'cancel' anytime to stop.": "⚠️ *出院开始*\n\n请逐步回答。\n随时输入 'cancel' 停止。",
    "⚠️ *HOSPITAL*\n\nSelect hospital:": "⚠️ *医院*\n\n选择医院：",
    "⚠️ *HOSPITAL SELECTED*\n\n{}": "⚠️ *医院已选择*\n\n{}",
    "⚠️ *WARD/BED*\n\nEnter ward and bed:": "⚠️ *病房/床位*\n\n输入病房和床位：",
    "⚠️ *WARD SAVED*\n\nDischarge date:": "⚠️ *病房已保存*\n\n出院日期：",
    "⚠️ *DROP-OFF LOCATION*\n\nShare drop-off location:": "⚠️ *下车位置*\n\n分享下车位置：",
    "⚠️ *LOCATION RECEIVED*\n\nAddress: {}\nDistance: {} km\n\nCorrect?": "⚠️ *位置已收到*\n\n地址：{}\n距离：{} 公里\n\n是否正确？",
    "⚠️ *LOCATION CONFIRMED*\n\nHealth condition:": "⚠️ *位置已确认*\n\n健康状况：",
    "✅ *DISCHARGE CONFIRMED*\n\nID: {}\nPatient: {}\nIC: {}\nPhone: {}\nEmergency: {} ({})\nFrom: {}\nWard: {}\nTo: {}\nScheduled: {}\n*Estimated Distance:* {} km\n*Attachments:* {}\n*Remarks:* {}\n\nOur team will contact you to confirm details.\n\n*Next Steps:*\n1. Team will coordinate with hospital\n2. You'll receive confirmation call\n3. Ambulance will arrive 30 minutes before discharge\n\nThank you for using AnyHealth Ambulance Service! 🚑": "✅ *出院已确认*\n\nID：{}\n患者：{}\n身份证：{}\n电话：{}\n紧急联系人：{}（{}）\n从：{}\n病房：{}\n到：{}\n预定时间：{}\n*预计距离：* {} 公里\n*附件：* {}\n*备注：* {}\n\n我们的团队将联系您确认详情。\n\n*后续步骤：*\n1. 团队将与医院协调\n2. 您将收到确认电话\n3. 救护车将在出院前 30 分钟到达\n\n感谢您使用 AnyHealth 救护车服务！🚑",

    # From vaccination_booking.py
    "Please select a vaccine:": "请选择一种疫苗：",
    "Vaccines": "疫苗",
    "Error loading vaccines. Please try again.": "加载疫苗时出错。请重试。",
    "No vaccines available. Please try again later.": "无可用疫苗。请稍后重试。",
    "Selected Vaccine: {}": "已选择疫苗：{}",

    # From amb_calendar_utils.py
    # (Already handled by existing translation)

    # From tcm_service.py
    "⚠️ *TCM BOOKING SUMMARY*\n\nService: {}\nDoctor: {}\nDate: {}\nTime: {}\nAddress: {}\nRemarks: {}\n\nConfirm?": "⚠️ *传统医疗预约摘要*\n\n服务：{}\n医生：{}\n日期：{}\n时间：{}\n地址：{}\n备注：{}\n\n确认吗？",
    "⚠️ *REMARK REQUIRED*\n\nFor {}, do you have remarks?": "⚠️ *需要备注*\n\n对于 {}，您有备注吗？",
    "⚠️ *REMARKS*\n\nPlease enter remarks for {}:": "⚠️ *备注*\n\n请输入 {} 的备注：",
    "⚠️ *REMARKS SAVED*\n\nProceed to booking?": "⚠️ *备注已保存*\n\n继续预约吗？",
    "Proceed": "继续",
    "Change Remarks": "更改备注",
    "⚠️ *BOOKING CANCELLED*\n\nReturned to main menu.": "⚠️ *预约已取消*\n\n已返回主菜单。",
    "⚠️ *DOCTOR SELECTION*\n\nSelect a doctor for {}:": "⚠️ *医生选择*\n\n为 {} 选择一位医生：",
    "Doctors for {}": "{} 的医生",
    "No doctors available for {}.": "{} 无可用医生。",
    "Error loading doctors for {}. Please try again.": "加载 {} 的医生时出错。请重试。",
    "⚠️ *BOOKING SUMMARY*\n\nService: {}\nDoctor: {}\nDate: {}\nTime: {}\nAddress: {}\nRemarks: {}\n\nConfirm?": "⚠️ *预约摘要*\n\n服务：{}\n医生：{}\n日期：{}\n时间：{}\n地址：{}\n备注：{}\n\n确认吗？",
    "✅ *TCM BOOKING CONFIRMED!*\n\nID: {}\nService: {}\nDoctor: {}\nDate: {}\nTime: {}\nAddress: {}\nRemarks: {}\n\nStatus: PENDING\n\nYou'll be notified when approved.": "✅ *传统医疗预约已确认！*\n\nID：{}\n服务：{}\n医生：{}\n日期：{}\n时间：{}\n地址：{}\n备注：{}\n\n状态：待处理\n\n批准后将通知您。",

    # From afterservice.py
    "Hi {patient_name}, how are you feeling regarding your {diagnosis}?": "您好 {patient_name}，您对您的 {diagnosis} 感觉如何？",
    "How are you feeling today?": "您今天感觉如何？",

    # From notification.py
    "Notification already sent for user {user_id}, case {case_id}, type {reminder_type}": "用户 {user_id}、病例 {case_id}、类型 {reminder_type} 的通知已发送",
    "Created {reminder_type} reminder for {whatsapp_number}, {table_name} {case_id}": "已为 {whatsapp_number}、{table_name} {case_id} 创建 {reminder_type} 提醒",
    "Error processing {table_name} {booking_id} from {table_name}: {error}": "处理 {table_name} {booking_id} 从 {table_name} 时出错：{error}",
    "Failed to fetch from {table_name}: {error}": "从 {table_name} 获取失败：{error}",
    "Error sending notification: {}": "发送通知时出错：{}",
    "Notification sent successfully to {}: {}": "通知已成功发送到 {}：{}",
    "Error sending template: {}": "发送模板时出错：{}",
    "Template sent successfully to {}: {}": "模板已成功发送到 {}：{}",
    "Error sending fallback message: {}": "发送备用消息时出错：{}",
    "Fallback message sent to {}: {}": "备用消息已发送到 {}：{}",
    "Notifications": "通知",
    "Error fetching notifications: {}": "获取通知时出错：{}",
    "Error sending reminder: {}": "发送提醒时出错：{}",
    "Reminder sent to {}: {}": "提醒已发送到 {}：{}",
    "Error sending confirmation: {}": "发送确认时出错：{}",
    "Confirmation sent to {}: {}": "确认已发送到 {}：{}",
    "Error sending immediate confirmation: {}": "发送即时确认时出错：{}",
    "Immediate confirmation sent to {}: {}": "即时确认已发送到 {}：{}",
    "Error sending followup: {}": "发送随访时出错：{}",
    "Followup sent to {}: {}": "随访已发送到 {}：{}",
    "Error updating followup: {}": "更新随访时出错：{}",
    "Followup updated successfully for {}": "随访已成功更新 {}",
    "Error saving template response: {}": "保存模板响应时出错：{}",
    "Template response saved successfully for {}": "模板响应已成功保存 {}",

    # From concierge.py
    # (Already handled by existing translation)

    # From main.py
    "Report & Follow up": "报告与随访",
    "Hi, you have new notification(s), please tap on \"notification\" button in the Main Menu to check them.": "您有新的通知，请点击主菜单中的“通知”按钮查看。",
    "Error fetching notifications: {}": "获取通知时出错：{}",
    "Error updating notifications: {}": "更新通知时出错：{}",
    "Error noting notification: {}": "记录通知时出错：{}",
    "Notification noted successfully.": "通知已成功记录。",

    # ========== MISSING TRANSLATIONS (EMPTY VALUES TO BE FILLED) ==========
    
    # From the provided dictionary with empty values that weren't in existing EN_TO_CN
    # These are keys that were in the provided CN_DICT but not in the existing EN_TO_CN
    # We'll add them with empty values so they can be filled later
    
    # Note: Since the provided dictionary had many duplicates and was very large,
    # I've filtered out the ones that are already in EN_TO_CN above.
    # The ones below are those that weren't found in the existing EN_TO_CN
    
    # From individualedit.py
    "IC verified, but error sending report. Please try again.": "",
    "IC verified, but the report is not yet available. You will be notified when ready.": "",
    "IC verified successfully, but no report request pending. Please select a consultation.": "",
    "Invalid verification format. Please use 'verified:<IC>'.": "",
    "Error processing verification. Please try again.": "",
    
    # Additional ambulance booking messages
    "Error submitting booking. Please try again.": "",
    "Error submitting transfer request. Please try again.": "",
    "Error submitting discharge request. Please try again.": "",
    
    # Additional error messages
    "Error loading checkups. Please try again.": "",
    "Error loading vaccines. Please try again.": "",
    "Error loading doctors. Please try again.": "",
    "Error loading calendar. Please try again.": "",
    "Error loading periods. Please try again.": "",
    "Error loading hours. Please try again.": "",
    "Error loading slots. Please try again.": "",
    
    # Additional phrases
    "Remarks saved. Proceed to booking?": "",
    "Symptoms saved. Proceed to booking?": "",
    "Change Symptoms": "",
    
    # Report & PDF related
    "PDF Request": "",
    "Consultation after PDF?": "",
    
    # TCM specific
    "Doctors for {}": "",
    "Error loading doctors for {}. Please try again.": "",
    
    # Notification system
    "Error sending reminder: {}": "",
    "Reminder sent to {}: {}": "",
    "Error sending confirmation: {}": "",
    "Confirmation sent to {}: {}": "",
    "Error sending immediate confirmation: {}": "",
    "Immediate confirmation sent to {}: {}": "",
    "Error sending followup: {}": "",
    "Followup sent to {}: {}": "",
    "Error updating followup: {}": "",
    "Followup updated successfully for {}": "",
    "Error saving template response: {}": "",
    "Template response saved successfully for {}": "",
    
    # View booking additional
    "Error fetching bookings: {}": "",
    "Error cancelling booking: {}": "",
    "Error cancelling repeated bookings: {}": "",
    "Error rescheduling repeated bookings: {}": "",
    "Error rescheduling: {}": "",
    
    # Additional ambulance
    "Error submitting booking. Please try again.": "",
    "Error submitting transfer request. Please try again.": "",
    "Error submitting discharge request. Please try again.": "",
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
    # New additions from the updated dictionary
    "Back to Main Menu", "PDF Request", "Home to Hospital", "Hospital to Home", 
    "Hospital Discharge", "Hospital to Hospital", "Home to Home", "Add Attachments",
    "No Attachments", "No Remarks", "Enter Remarks", "Proceed", "Change Remarks",
    "Cancel All", "Cancel This Only", "Reschedule All", "Reschedule This Only",
    "Previous Page", "Next Page", "Back to Menu", "Actions", "Back", "Morning",
    "Afternoon", "Evening", "Get Help Choosing", "No, Change Date", "Change Doctor",
    "Change Date", "Change Time", "Change Remarks", "Cancel Booking", "Edit Options",
    "Back to Categories", "Doctors for {}", "Screening Packages", "Vaccines",
    "Return Dates", "Time Periods", "Booking Dates", "Dates", "Hospitals",
    "Checkup Types", "Health Screening Plan"
]

def truncate_text(text: str, max_length: int = 20) -> str:
    """Truncate text to max_length, preserving whole words if possible."""
    if len(text) <= max_length:
        return text
    truncated = text[:max_length]
    last_space = truncated.rfind(" ")
    if last_space != -1 and last_space > max_length // 2:
        truncated = truncated[:last_space]
    else:
        truncated = truncated[:max_length - 1] + "…"
    return truncated

def cn_translate_template(text: str, supabase=None) -> str:
    """
    Translate text to Chinese using the EN_TO_CN dictionary.
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
            if text in EN_TO_CN:
                return EN_TO_CN[text]
            return text  # Fallback to original text if not in dictionary

        # Check dictionary for direct translation
        if text in EN_TO_CN:
            return EN_TO_CN[text]

        # If not in dictionary, return original text
        return text

    except Exception as e:
        logger.error(f"Translation error for '{text}': {e}")
        return text

def cn_gt_tt(text: str, supabase=None, doctor_name: str = None) -> str:
    """
    Translate text to Chinese using Google Translate API for dynamic database fields.
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
        if text_to_translate in EN_TO_CN:
            translated_text = EN_TO_CN[text_to_translate]
        # Then try Google Translate if available
        elif translate_client:
            for attempt in range(3):
                try:
                    google_result = translate_client.translate(
                        text_to_translate, source_language="en", target_language="zh-CN"
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

def cn_gt_t_tt(text: str, supabase=None, doctor_name: str = None) -> str:
    """
    Translate text to Chinese using Google Translate API with truncation for buttons/titles.
    Preserves AnyHealth, doctor names, and clinic names.
    Applies truncation (≤20 chars) for buttons, section titles, and row titles.
    Used for WhatsApp buttons and titles.
    """
    try:
        translated_text = cn_gt_tt(text, supabase, doctor_name)
        return truncate_text(translated_text, 20)
    except Exception as e:
        logger.error(f"Truncated translation error for '{text}': {e}")
        return truncate_text(text, 20)

