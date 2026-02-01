# cn_match.py - COMPLETE VERSION
import logging
import time
import html
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


# Translation dictionary for English to Chinese
EN_TO_CN = {
    # HEADER
    "AnyHealth Bot": "AnyHealth 机器人",
    "Profiles": "个人档案",
    "Options for {}": "{}的选项",
    "Select Visit for Report": "选择就诊记录以查看报告",
    "Select Document": "选择文件",
    "Select Race": "选择种族",
    "Select Religion": "选择宗教",
    "Select Blood Type": "选择血型",
    "Remove Profile": "移除档案",
    "Changed Numbers": "已更换号码",
    "Action Required": "需您操作",
    "Confirmed": "已确认",
    "Pending": "待处理",
    "View Booking Options": "查看预约选项",
    "📍 Current Address (Pickup)": "📍 当前地址（接载点）",
    "📍 Pickup Address Found": "📍 已找到接载地址",
    "📍 Destination Address Found": "📍 已找到目的地地址",
    "📱 Destination Emergency Contact": "📱 目的地紧急联系人",
    "📎 Attachments": "📎 附件",
    "📝 Remarks": "📝 备注",
    "📅 Select Transfer Date": "📅 选择转运日期",
    "⏰ Select 2-Hour Slot ({period})": "⏰ 选择2小时时段（{period}）",
    "⏱️ Select 15-Minute Interval": "⏱️ 选择15分钟间隔",
    "🏥 Current Hospital Address Found": "🏥 已找到当前医院地址",
    "🏥 Destination Hospital Address Found": "🏥 已找到目的地医院地址",
    "🚑 Non-Emergency Ambulance": "🚑 非紧急救护车服务",
    "🌿 TCM Services": "🌿 传统医疗服务",


    # BODY
    "Please select your preferred language:": "请选择您的首选语言：",
    "Welcome to our clinic! Please select a booking option.": "欢迎来到我们的诊所！请选择预约选项。",
    "Please choose a booking option:": "请选择预约选项：",
    "⚠️ *Main Menu Confirmation*\n\nAre you sure you want to go back to the main menu?\nThis will cancel your current action.": "⚠️ *返回主菜单确认*\n\n确定要返回主菜单吗？\n这将取消当前操作。",
    "Please select the type of non-emergency transport you need:\n\n• Scheduled patient transport\n• Advance booking required (24 hours)\n• Professional medical team": "请选择您需要的非紧急转运类型：\n\n• 预约患者转运\n• 需提前预订（24小时）\n• 专业医疗团队",
    "Please share your current location:": "请分享您的当前位置：",
    "Session expired. Returning to main menu.": "会话已过期。正在返回主菜单。",
    "Continuing with your previous action.": "继续您之前的操作。",
    "Could not restore previous action. Returning to main menu.": "无法恢复之前操作。正在返回主菜单。",
    "Error: No service selected. Please start over.": "错误：未选择服务。请重新开始。",
    "Do you have any remarks for {} ({} min){}?": "您对{}（{}分钟）{}有任何备注吗？",
    "Please enter your remarks:": "请输入您的备注：",
    "Please enter your preferred date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:": "请输入您希望的日期（格式：日/月/年）：",
    "Please enter your preferred time (e.g., 9:30, 2pm, 1430):": "请输入您希望的时间（例如：9:30、下午2点、1430）：",
    "Error saving vaccination booking. Please try again.": "保存疫苗接种预约时出错。请重试。",
    "Invalid input. Please use the buttons provided.": "输入无效。请使用提供的按钮。",
    "✅ Your vaccination booking has been submitted!\n\n": "✅ 您的疫苗接种预约已提交！\n\n",
    "Vaccine: ": "疫苗：",
    "Date: ": "日期：",
    "Time: ": "时间：",
    "Duration: ": "时长：",
    " minutes\n\n": " 分钟\n\n",
    "Booking is pending approval. You'll be notified once confirmed.\n": "预约待批准。确认后您将收到通知。\n",
    "Booking ID: ": "预约编号：",
    "🏠 *AMBULANCE SERVICE: HOME TO HOME TRANSFER*": "🏠 *救护车服务：住家转运*",
    "This service helps transfer patients between homes (e.g., moving to family home).": "本服务协助患者在住家之间转运（例如，搬往亲属家）。",
    "We'll collect information for your home-to-home transfer.": "我们将为您收集住家转运所需信息。",
    "Please answer the following questions one by one.": "请逐一回答以下问题。",
    "*IMPORTANT:*": "*重要提示：*",
    "• Provide accurate addresses for both locations": "• 提供双方地址准确信息",
    "• Ensure patient is stable for transfer": "• 确保患者情况稳定适合转运",
    "• Have all necessary medical equipment ready": "• 备好所有必要医疗设备",
    "• Coordinate with family members at both locations": "• 与双方住址的家人协调",
    "*QUESTIONS TO FOLLOW:*": "*即将询问：*",
    "1. Patient full name": "1. 患者全名",
    "2. Patient IC number": "2. 患者身份证号码",
    "3. Patient phone number": "3. 患者电话号码",
    "4. Emergency contact at pickup location": "4. 接载地点紧急联系人",
    "5. Emergency contact phone at pickup location": "5. 接载地点紧急联系电话",
    "6. Current address (Pickup) with location sharing option": "6. 当前地址（接载点），可分享位置",
    "7. Destination address (manual input)": "7. 目的地地址（手动输入）",
    "8. Reason for transfer": "8. 转运原因",
    "9. Medical condition": "9. 医疗状况",
    "*After these questions, we'll ask for destination emergency contact, attachments, and schedule.*": "*这些问题之后，我们将询问目的地紧急联系人、附件和日程安排。*",
    "You can cancel anytime by typing 'cancel'.": "可随时输入 'cancel' 取消。",
    "6. *Current address (Pickup)*": "6. *当前地址（接载点）*",
    "How would you like to provide your current address?": "您希望如何提供当前地址？",
    "• *Share Location:* Send your current location (recommended)": "• *分享位置：* 发送您当前位置（推荐）",
    "• *Type Address:* Enter your full address manually": "• *输入地址：* 手动输入完整地址",
    "Example of manual address:": "手动地址示例：",
    "Please type your full current address:": "请输入您的完整当前地址：",
    "Example:": "例如：",
    "Include:": "请包括：",
    "• House/building number": "• 门牌/楼号",
    "• Street name": "• 街道名称",
    "• Area/Taman": "• 区域/花园",
    "• Postcode and City": "• 邮编与城市",
    "• State": "• 州属",
    "We found this address:": "我们找到此地址：",
    "Is this your correct pickup address?": "这是正确的接载地址吗？",
    "7. *Destination address*": "7. *目的地地址*",
    "Please type the full destination address:": "请输入完整的目的地地址：",
    "Example:": "例如：",
    "Include:": "请包括：",
    "• House/building number": "• 门牌/楼号",
    "• Street name": "• 街道名称",
    "• Area/Taman": "• 区域/花园",
    "• Postcode and City": "• 邮编与城市",
    "• State": "• 州属",
    "We found this address:": "我们找到此地址：",
    "Is this your correct destination address?": "这是正确的目的地地址吗？",
    "8. *Reason for transfer*": "8. *转运原因*",
    "Please explain why you need this home-to-home transfer:": "请说明您需要此次住家转运的原因：",
    "Examples:": "例如：",
    "• Moving to family home for care": "• 搬往亲属家以便照料",
    "• Returning from temporary stay": "• 从临时住所返回",
    "• Home modification needed": "• 需进行房屋改造",
    "• Closer to medical facilities": "• 更靠近医疗设施",
    "• Change of residence": "• 变更居住地",
    "9. *Medical condition*": "9. *医疗状况*",
    "Please describe the patient's current medical condition:": "请描述患者目前的医疗状况：",
    "Examples:": "例如：",
    "• Post-stroke recovery": "• 中风后康复期",
    "• Mobility limited": "• 行动受限",
    "• Requires oxygen therapy": "• 需要氧气治疗",
    "• Stable condition for transfer": "• 状况稳定适合转运",
    "• Recent surgery": "• 近期手术",
    "Would you like to provide an emergency contact at the destination?": "您是否想提供目的地的紧急联系人？",
    "This is optional but recommended for better coordination at the destination location.": "此为可选，但建议提供以便在目的地更好协调。",
    "Please provide the emergency contact name at the destination:": "请提供目的地的紧急联系人姓名：",
    "Example: Rahman bin Ali or Aishah binti Hassan": "例如：Rahman bin Ali 或 Aishah binti Hassan",
    "Please provide the emergency contact phone at the destination:": "请提供目的地的紧急联系电话：",
    "Example: 012-3456789 or 019-8765432": "例如：012-3456789 或 019-8765432",
    "You can upload attachments (photos/documents) related to this transfer.": "您可以上传与此转运相关的附件（照片/文件）。",
    "Examples:": "例如：",
    "• Medical reports": "• 医疗报告",
    "• Doctor's clearance for transfer": "• 医生出具的转运许可",
    "• Insurance documents": "• 保险文件",
    "• Prescriptions": "• 处方",
    "You can upload multiple attachments. When done, click 'Next'.": "您可以上传多个附件。完成后，请点击'下一步'。",
    "Do you have any additional remarks or special instructions?": "您有任何额外备注或特别指示吗？",
    "Examples:": "例如：",
    "• Specific route preferences": "• 特定路线偏好",
    "• Special medical equipment needed": "• 需要的特殊医疗设备",
    "• Time constraints": "• 时间限制",
    "• Additional patient information": "• 额外的患者信息",
    "You can add remarks or skip to continue.": "您可以添加备注或跳过继续。",
    "Please type your remarks or special instructions:": "请输入您的备注或特别指示：",
    "Examples:": "例如：",
    "• Patient needs wheelchair assistance": "• 患者需要轮椅协助",
    "• Please use back entrance": "• 请使用后门",
    "• Patient is fasting": "• 患者正在禁食",
    "• Special handling requirements": "• 特殊处理要求",
    "Please select the transfer date:": "请选择转运日期：",
    "*Today:*": "*今天：*",
    "*Tomorrow:*": "*明天：*",
    "If you need another date, select 'Others' and enter DD/MM/YYYY format.": "如需其他日期，请选择'其他日期'并按日/月/年格式输入。",
    "Please select AM or PM for the transfer time:": "请选择转运时间的上午或下午：",
    "Please select a 2-hour time slot for transfer:": "请选择2小时的转运时段：",
    "Selected Date:": "已选日期：",
    "Period:": "时段：",
    "After selecting a slot, you'll choose the exact 15-minute interval.": "选择时段后，您将选择精确的15分钟间隔。",
    "Please select the exact transfer time:": "请选择确切的转运时间：",
    "Selected Date:": "已选日期：",
    "Selected Slot:": "已选时段：",
    "Choose your preferred 15-minute interval within this slot.": "请在此时段内选择您偏好的15分钟间隔。",
    "Error starting transfer request. Please try again.": "启动转运请求时出错。请重试。",
    "Home transfer cancelled. Returning to main menu.": "住家转运已取消。正在返回主菜单。",
    "Please provide a valid answer.": "请提供有效回答。",
    "❌ *Invalid IC number format*": "❌ *身份证号码格式无效*",
    "IC must be 12 digits.": "身份证必须是12位数字。",
    "Accepted formats:": "可接受的格式：",
    "• 801212-14-5678": "• 801212-14-5678",
    "• 801212145678": "• 801212145678",
    "• 801212 14 5678": "• 801212 14 5678",
    "Please re-enter the patient's IC number:": "请重新输入患者的身份证号码：",
    "Error processing your answer. Please try again.": "处理您的回答时出错。请重试。",
    "❌ Unsupported file type.": "❌ 不支持的文件类型。",
    "Please send images (JPEG, PNG) or documents (PDF, DOC) only.": "请仅发送图像（JPEG、PNG）或文档（PDF、DOC）。",
    "Error: Could not get file information. Please try again.": "错误：无法获取文件信息。请重试。",
    "❌ Failed to download file from WhatsApp.": "❌ 从WhatsApp下载文件失败。",
    "Please try sending the file again.": "请尝试重新发送文件。",
    "✅ *Attachment successfully saved!*": "✅ *附件保存成功！*",
    "You can send more attachments or click 'Next' to continue.": "您可以发送更多附件，或点击'下一步'继续。",
    "❌ Failed to save attachment.": "❌ 保存附件失败。",
    "Please try again or click 'Skip' to continue without attachments.": "请重试，或点击'跳过'继续（不带附件）。",
    "Error processing attachment. Please try again.": "处理附件时出错。请重试。",
    "Invalid selection. Please try again.": "选择无效。请重试。",
    "Date cannot be in the past.": "日期不能是过去日期。",
    "Please enter a future date in DD/MM/YYYY format.": "请按日/月/年格式输入未来日期。",
    "Invalid date format.": "日期格式无效。",
    "Please enter date in DD/MM/YYYY format.": "请按日/月/年格式输入日期。",
    "Example: 25/12/2024": "例如：2024年12月25日",
    "Error selecting time interval. Please try again.": "选择时间间隔时出错。请重试。",
    "Error submitting transfer request. Please try again.": "提交转运请求时出错。请重试。",
    "✅ *HOME TO HOME TRANSFER CONFIRMED*": "✅ *住家转运已确认*",
    "Your home-to-home transfer request has been received.": "您的住家转运请求已收到。",
    "Our team will contact you to arrange details.": "我们的团队将联系您以安排细节。",
    "*Next Steps:*": "*后续步骤：*",
    "1. Team will verify details": "1. 团队将核实细节",
    "2. You'll receive confirmation call": "2. 您将收到确认电话",
    "3. Transfer schedule will be arranged": "3. 将安排转运日程",
    "Thank you for using AnyHealth Ambulance Service! 🚑": "感谢您使用AnyHealth救护车服务！🚑",
    "🏥 *AMBULANCE SERVICE: HOSPITAL TO HOSPITAL TRANSFER*": "🏥 *救护车服务：医院间转运*",
    "This service helps transfer patients between hospitals for specialized care.": "本服务协助患者在医院间转运以获得专科护理。",
    "We'll collect information for your inter-hospital transfer.": "我们将为您收集医院间转运所需信息。",
    "Please answer the following questions one by one.": "请逐一回答以下问题。",
    "*IMPORTANT:*": "*重要提示：*",
    "• Ensure both hospitals are aware of the transfer": "• 确保双方医院知悉此次转运",
    "• Provide accurate hospital names": "• 提供准确的医院名称",
    "• We'll automatically find hospital addresses": "• 我们将自动查找医院地址",
    "• Have medical files ready for transfer": "• 备好转运所需的医疗文件",
    "---": "---",
    "*QUESTIONS TO FOLLOW:*": "*即将询问：*",
    "1. Patient name": "1. 患者姓名",
    "2. Patient IC number": "2. 患者身份证号码",
    "3. Patient phone number": "3. 患者电话号码",
    "4. Emergency contact name": "4. 紧急联系人姓名",
    "5. Emergency contact phone": "5. 紧急联系电话",
    "6. Current hospital name (we'll find the address)": "6. 当前医院名称（我们将查找地址）",
    "7. Ward number and level (e.g., Ward 5A, Level 3)": "7. 病房号与楼层（例如：5A病房，3楼）",
    "8. Destination hospital name (we'll find the address)": "8. 目的地医院名称（我们将查找地址）",
    "*After these questions, you can upload attachments, add remarks, and schedule the transfer.*": "*这些问题之后，您可以上传附件、添加备注并安排转运。*",
    "You can cancel anytime by typing 'cancel'.": "可随时输入 'cancel' 取消。",
    "6. *Current hospital name*": "6. *当前医院名称*",
    "Please type the name of the current hospital:": "请输入当前医院的名称：",
    "Examples:": "例如：",
    "• Hospital Kuala Lumpur": "• 吉隆坡医院",
    "• Sunway Medical Centre": "• 双威医疗中心",
    "• Pantai Hospital Kuala Lumpur": "• 班台医院吉隆坡",
    "• University Malaya Medical Centre": "• 马来亚大学医疗中心",
    "We'll automatically find the address for you.": "我们将自动为您查找地址。",
    "We found this address for *{hospital_name}*:": "我们为*{hospital_name}*找到此地址：",
    "Is this the correct hospital address?": "这是正确的医院地址吗？",
    "Please type the current hospital address manually:": "请手动输入当前医院地址：",
    "Example:": "例如：",
    "Jalan Pahang, 53000 Kuala Lumpur, Wilayah Persekutuan Kuala Lumpur": "Jalan Pahang, 53000 Kuala Lumpur, Wilayah Persekutuan Kuala Lumpur",
    "Include full address with postcode and state.": "请包含邮编和州属的完整地址。",
    "7. *Ward number and level*": "7. *病房号与楼层*",
    "Please provide the ward number and level:": "请提供病房号与楼层：",
    "Examples:": "例如：",
    "• Ward 5A, Level 3": "• 5A病房，3楼",
    "• ICU, Level 5": "• 加护病房，5楼",
    "• Ward 3B, Ground Floor": "• 3B病房，底层",
    "• Private Suite, Level 2": "• 私人套房，2楼",
    "Enter both ward and level together.": "请同时输入病房和楼层。",
    "8. *Destination hospital name*": "8. *目的地医院名称*",
    "Please type the name of the destination hospital:": "请输入目的地医院的名称：",
    "Examples:": "例如：",
    "• Hospital Kuala Lumpur": "• 吉隆坡医院",
    "• Sunway Medical Centre": "• 双威医疗中心",
    "• Pantai Hospital Kuala Lumpur": "• 班台医院吉隆坡",
    "• University Malaya Medical Centre": "• 马来亚大学医疗中心",
    "We'll automatically find the address for you.": "我们将自动为您查找地址。",
    "We found this address for *{hospital_name}*:": "我们为*{hospital_name}*找到此地址：",
    "Is this the correct hospital address?": "这是正确的医院地址吗？",
    "Please type the destination hospital address manually:": "请手动输入目的地医院地址：",
    "Example:": "例如：",
    "Jalan Pahang, 53000 Kuala Lumpur, Wilayah Persekutuan Kuala Lumpur": "Jalan Pahang, 53000 Kuala Lumpur, Wilayah Persekutuan Kuala Lumpur",
    "Include full address with postcode and state.": "请包含邮编和州属的完整地址。",
    "You can upload attachments (photos/documents) related to this transfer.": "您可以上传与此转运相关的附件（照片/文件）。",
    "Examples:": "例如：",
    "• Medical reports": "• 医疗报告",
    "• Doctor's referral letters": "• 医生转诊信",
    "• Insurance documents": "• 保险文件",
    "• Transfer forms": "• 转运表格",
    "You can upload multiple attachments. When done, click 'Next'.": "您可以上传多个附件。完成后，请点击'下一步'。",
    "Do you have any additional remarks or special instructions?": "您有任何额外备注或特别指示吗？",
    "Examples:": "例如：",
    "• Specific medical equipment needed": "• 需要的特定医疗设备",
    "• Time constraints for transfer": "• 转运时间限制",
    "• Special handling requirements": "• 特殊处理要求",
    "• Additional patient information": "• 额外的患者信息",
    "You can add remarks or skip to continue.": "您可以添加备注或跳过继续。",
    "Please type your remarks or special instructions:": "请输入您的备注或特别指示：",
    "Examples:": "例如：",
    "• Patient requires ventilator during transfer": "• 患者在转运期间需要呼吸机",
    "• Specific route preferred": "• 偏好特定路线",
    "• Need ambulance with ICU facilities": "• 需要配备ICU设施的救护车",
    "• Coordination with specific hospital staff": "• 与特定医院人员协调",
    "Please select the transfer date:": "请选择转运日期：",
    "*Today:*": "*今天：*",
    "*Tomorrow:*": "*明天：*",
    "If you need another date, select 'Others' and enter DD/MM/YYYY format.": "如需其他日期，请选择'其他日期'并按日/月/年格式输入。",
    "Please select AM or PM for the transfer time:": "请选择转运时间的上午或下午：",
    "Please select a 2-hour time slot for the transfer:": "请选择2小时的转运时段：",
    "Selected Date:": "已选日期：",
    "Period:": "时段：",
    "After selecting a slot, you'll choose the exact 15-minute interval.": "选择时段后，您将选择精确的15分钟间隔。",
    "Please select the exact time for the transfer:": "请选择确切的转运时间：",
    "Selected Date:": "已选日期：",
    "Selected Slot:": "已选时段：",
    "Choose your preferred 15-minute interval within this slot.": "请在此时段内选择您偏好的15分钟间隔。",
    "Error starting transfer request. Please try again.": "启动转运请求时出错。请重试。",
    "Could not find address for this hospital. Please provide the address manually.": "无法找到此医院地址。请手动提供地址。",
    "Please enter the transfer date in DD/MM/YYYY format:": "请按日/月/年格式输入转运日期：",
    "Example: 25/12/2024": "例如：2024年12月25日",
    "Error scheduling date. Please try again.": "安排日期时出错。请重试。",
    "Error selecting time interval. Please try again.": "选择时间间隔时出错。请重试。",
    "Hospital transfer cancelled. Returning to main menu.": "医院转运已取消。正在返回主菜单。",
    "Please provide a valid answer.": "请提供有效回答。",
    "❌ *Invalid IC number format*": "❌ *身份证号码格式无效*",
    "IC must be 12 digits.": "身份证必须是12位数字。",
    "Accepted formats:": "可接受的格式：",
    "• 801212-14-5678": "• 801212-14-5678",
    "• 801212145678": "• 801212145678",
    "• 801212 14 5678": "• 801212 14 5678",
    "Please re-enter the patient's IC number:": "请重新输入患者的身份证号码：",
    "Error processing your answer. Please try again.": "处理您的回答时出错。请重试。",
    "Unsupported file type. Please send images (JPEG, PNG) or documents (PDF, DOC) only.": "不支持的文件类型。请仅发送图像（JPEG、PNG）或文档（PDF、DOC）。",
    "Error: Could not get file information. Please try again.": "错误：无法获取文件信息。请重试。",
    "Failed to download file from WhatsApp. Please try sending the file again.": "从WhatsApp下载文件失败。请尝试重新发送文件。",
    "Failed to save attachment. Please try again or click 'Skip' to continue without attachments.": "保存附件失败。请重试，或点击'跳过'继续（不带附件）。",
    "Error processing attachment. Please try again.": "处理附件时出错。请重试。",
    "Invalid selection. Please try again.": "选择无效。请重试。",
    "Date cannot be in the past. Please enter a future date in DD/MM/YYYY format.": "日期不能是过去日期。请按日/月/年格式输入未来日期。",
    "Invalid date format. Please enter date in DD/MM/YYYY format.": "日期格式无效。请按日/月/年格式输入日期。",
    "Example: 25/12/2024": "例如：2024年12月25日",
    "Error submitting transfer request. Please try again.": "提交转运请求时出错。请重试。",
    "✅ *HOSPITAL TO HOSPITAL TRANSFER CONFIRMED*": "✅ *医院间转运已确认*",
    "Your inter-hospital transfer request has been received. Our team will coordinate with both hospitals.": "您的医院间转运请求已收到。我们的团队将与双方医院协调。",
    "*Next Steps:*": "*后续步骤：*",
    "1. Team will contact both hospitals": "1. 团队将联系双方医院",
    "2. You'll receive confirmation call": "2. 您将收到确认电话",
    "3. Transfer schedule will be arranged": "3. 将安排转运日程",
    "Thank you for using AnyHealth Ambulance Service! 🚑": "感谢您使用AnyHealth救护车服务！🚑",
    "I couldn't understand the time format. Please try entering the time again, or let me help you choose from available slots.": "无法理解时间格式。请重新输入时间，或让我帮您从可用时段中选择。",
    "Great! {formatted_display_time} is available. Is this the time you want?": "太好了！{formatted_display_time} 可用。这是您想要的时间吗？",
    "Unfortunately {formatted_display_time} is not available. The closest available time is {formatted_closest} (just {minutes_diff} minutes difference). Would you like to book this instead?": "抱歉，{formatted_display_time} 不可用。最接近的可用时间是 {formatted_closest}（仅差 {minutes_diff} 分钟）。您想预订这个时间吗？",
    "Unfortunately {formatted_display_time} is not available. The closest available time is {formatted_closest}. Would you like to book this instead?": "抱歉，{formatted_display_time} 不可用。最接近的可用时间是 {formatted_closest}。您想预订这个时间吗？",
    "No available slots near {formatted_display_time}. Would you like to try a different time or let me help you choose from available slots?": "{formatted_display_time} 附近没有可用时段。您想尝试其他时间，还是让我帮您从可用时段中选择？",
    "Select a doctor for your appointment or choose 'Any Doctor':": "为您的预约选择医生，或选择'任何医生'：",
    "Select a date for your appointment:": "选择您的预约日期：",
    "Select {duration}min slot for {date} {hour}:": "为 {date} {hour} 选择 {duration} 分钟时段：",
    "What would you like to edit?": "您想编辑什么？",
    "Is this the correct date: {formatted_date}?": "这个日期正确吗：{formatted_date}？",
    "Selected date {formatted_date_short} is not available. Here are the nearest available dates:": "所选日期 {formatted_date_short} 不可用。以下是最接近的可用日期：",
    "Confirm your booking:\n• Service: {}\n• Doctor: {}\n• Date: {}\n• Time: {}\n• Duration: {} min\n• Details: {}\n• Reminder: {}": "确认您的预约：\n• 服务：{}\n• 医生：{}\n• 日期：{}\n• 时间：{}\n• 时长：{} 分钟\n• 详情：{}\n• 提醒：{}",
    "Confirm your booking:\n• Service: {}\n• Doctor: {}\n• Date: {}\n• Time: {}\n• Duration: {} min\n• Details: {}": "确认您的预约：\n• 服务：{}\n• 医生：{}\n• 日期：{}\n• 时间：{}\n• 时长：{} 分钟\n• 详情：{}",
    "Your checkup booking is pending approval by the admin.": "您的检查预约正等待管理员批准。",
    "Your consultation booking is pending approval by the admin.": "您的咨询预约正等待管理员批准。",
    "Your vaccination booking is pending approval by the admin.": "您的疫苗接种预约正等待管理员批准。",
    "Your health screening booking is pending approval by the admin.": "您的健康筛查预约正等待管理员批准。",
    "Error processing time. Please try again.": "处理时间时出错。请重试。",
    "No doctors available. Please contact support.": "没有可用的医生。请联系支持。",
    "Unable to fetch doctors. Please try again.": "无法获取医生信息。请重试。",
    "An error occurred while fetching doctors: {str(e)}. Please try again.": "获取医生信息时出错：{str(e)}。请重试。",
    "Time slot not found. Please try again.": "未找到时段。请重试。",
    "Error confirming time. Please try again.": "确认时间时出错。请重试。",
    "Error processing choice. Please try again.": "处理选择时出错。请重试。",
    "No available dates in the next 14 days. Please {}.": "未来14天内没有可用日期。请{}。",
    "Unable to fetch calendar. Please try again.": "无法获取日历。请重试。",
    "An error occurred while fetching the calendar: {str(e)}. Please try again.": "获取日历时出错：{str(e)}。请重试。",
    "No available hours for this date. Please select another date.": "此日期没有可用小时段。请选择其他日期。",
    "Unable to fetch hours. Please try again.": "无法获取小时段。请重试。",
    "An error occurred while fetching hours: {str(e)}. Please try again.": "获取小时段时出错：{str(e)}。请重试。",
    "Invalid period selection. Please try again.": "时段选择无效。请重试。",
    "No available hours in this period. Please select another date.": "此时段内没有可用小时段。请选择其他日期。",
    "No available time slots.": "没有可用时段。",
    "Error loading slots.": "加载时段时出错。",
    "No doctors available. Please try again later.": "没有可用的医生。请稍后重试。",
    "No doctors available for this time slot. Please select another.": "此时段没有可用的医生。请选择其他时段。",
    "An error occurred while confirming the booking: {str(e)}. Please try again.": "确认预约时出错：{str(e)}。请重试。",
    "Error loading edit options. Please try again.": "加载编辑选项时出错。请重试。",
    "Invalid edit option. Please try again.": "编辑选项无效。请重试。",
    "Error processing edit choice. Please try again.": "处理编辑选择时出错。请重试。",
    "Failed to save booking. Please try again.": "保存预约失败。请重试。",
    "Failed to send confirmation. Booking cancelled. Please try again.": "发送确认失败。预约已取消。请重试。",
    "An error occurred while confirming the booking: {str(e)}. Please try again.": "确认预约时出错：{str(e)}。请重试。",
    "Booking has been cancelled.": "预约已取消。",
    "Invalid date format. Please enter date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:": "日期格式无效。请按日/月/年、日-月-年或日 月 年格式输入日期：",
    "Please select a future date. Enter date as DD/MM/YYYY:": "请选择未来日期。按日/月/年格式输入日期：",
    "Error processing date. Please try again.": "处理日期时出错。请重试。",
    "Date not found. Please try again.": "未找到日期。请重试。",
    "Error confirming date. Please try again.": "确认日期时出错。请重试。",
    "No available dates found near {formatted_date_short}. Please enter a different date as DD/MM/YYYY:": "在 {formatted_date_short} 附近未找到可用日期。请按日/月/年格式输入其他日期：",
    "Monday": "星期一",
    "Tuesday": "星期二",
    "Wednesday": "星期三",
    "Thursday": "星期四",
    "Friday": "星期五",
    "Saturday": "星期六",
    "Sunday": "星期日",
    "Checkup": "检查",
    "Vaccination": "疫苗接种",
    "Consultation": "咨询",
    "Health Screening": "健康筛查",
    "Appointment": "预约",
    "Do you have any remarks for {} ({} min){}?": "您对{}（{}分钟）{}有任何备注吗？",
    "Error: No service selected. Please start over.": "错误：未选择服务。请重新开始。",
    "Please enter your remarks:": "请输入您的备注：",
    "Please enter your preferred date as DD/MM/YYYY, DD-MM-YYYY or DD MM YYYY:": "请输入您希望的日期（格式：日/月/年）：",
    "Please enter your preferred time (e.g., 9:30, 2pm, 1430):": "请输入您希望的时间（例如：9:30、下午2点、1430）：",
    "✅ Your checkup booking has been submitted!\n\nService: {}\nDate: {}\nTime: {}\nDuration: {} minutes\n\nBooking is pending approval. You'll be notified once confirmed.\nBooking ID: {}...": "✅ 您的检查预约已提交！\n\n服务：{}\n日期：{}\n时间：{}\n时长：{} 分钟\n\n预约待批准。确认后您将收到通知。\n预约编号：{}...",
    "Error saving checkup booking. Please try again.": "保存检查预约时出错。请重试。",
    "Invalid input. Please use the buttons provided.": "输入无效。请使用提供的按钮。",
    "Please describe your symptoms or health concerns:": "请描述您的症状或健康问题：",
    "What would you like to do next?": "您接下来想做什么？",
    "Select a profile to view or manage{}:": "选择要查看或管理的档案{}：",
    "What would you like to view?": "您想查看什么？",
    "Select a visit to view documents{}:": "选择就诊记录以查看文件{}：",
    "Select a document to download:": "选择要下载的文件：",
    "Select race:": "选择种族：",
    "Select religion:": "选择宗教：",
    "Select blood type:": "选择血型：",
    "Continue with profile removal?": "继续移除档案吗？",
    "Select a profile to remove:": "选择要移除的档案：",
    "Edit Profiles Menu:": "编辑档案菜单：",
    "Select booking type:": "选择预约类型：",
    "Select a booking to manage or reschedule from {} category:": "从 {} 类别中选择一个预约进行管理或改期：",
    "Selected: {}": "已选择：{}",
    "Selected: {}\n\nDoctor has requested to reschedule this appointment.": "已选择：{}\n\n医生已请求为此预约改期。",
    "Selected: {}\n\nAmbulance bookings cannot be modified via WhatsApp. Please contact the ambulance service directly for any changes.": "已选择：{}\n\n救护车预约无法通过WhatsApp修改。如需任何更改，请直接联系救护车服务。",
    "Selected date: {}. Confirm?": "已选日期：{}。确认吗？",
    "Selected time: {}\n\nConfirm this time slot?": "已选时间：{}\n\n确认此时段吗？",
    "Confirm reschedule:{} \n\nOriginal Booking:\n• Type: {}\n• Date: {}\n• Time: {}\n\nNew Booking:\n• Doctor: {}\n• Date: {}\n• Time: {}\n• Duration: {} min": "确认改期：{} \n\n原预约：\n• 类型：{}\n• 日期：{}\n• 时间：{}\n\n新预约：\n• 医生：{}\n• 日期：{}\n• 时间：{}\n• 时长：{} 分钟",
    "MC, Invoice, Referral letter, Report": "病假单、发票、转诊信、报告",
    "Returning to main menu.": "正在返回主菜单。",
    "Continuing with your previous action.": "继续您之前的操作。",
    "Could not restore previous action. Returning to main menu.": "无法恢复之前操作。正在返回主菜单。",
    "Error registering user. Please try again.": "注册用户时出错。请重试。",
    "Please use the menu buttons provided for selection.": "请使用提供的菜单按钮进行选择。",
    "An error occurred while setting up your booking. Please try again.": "设置您的预约时出错。请重试。",
    "Clinic information not found. Please try again.": "未找到诊所信息。请重试。",
    "Error retrieving clinic information. Please try again.": "检索诊所信息时出错。请重试。",
    "No clinic found with that keyword. Please try a different search.": "未找到包含该关键词的诊所。请尝试其他搜索词。",
    "Error setting language. Please try again.": "设置语言时出错。请重试。",
    "Error storing temp_data:": "存储临时数据时出错：",
    "Invalid input. Returning to main menu.": "输入无效。正在返回主菜单。",
    "An error occurred. Please try again.": "发生错误。请重试。",
    "Please select an option from the menu.": "请从菜单中选择一个选项。",
    "Language set to {selected_language}.": "语言已设为 {selected_language}。",
    "Select a service type:": "选择服务类型：",
    "Please select a clinic:": "请选择诊所：",
    "Please select a {category} service:": "请选择{category}服务：",
    "Please use the menu below to select an option:": "请使用下方菜单选择选项：",
    "SELECT DOCTOR\n\nWhich doctor would you like to book with?": "选择医生\n\n您想预约哪位医生？",
    "SELECT TIME\n\nChoose your preferred time slot:": "选择时间\n\n选择您偏好的时段：",
    "Location received. However, location sharing is not expected in this context. Please use the menu buttons provided for selection.": "位置已收到。但此上下文中不需要分享位置。请使用提供的菜单按钮进行选择。",
    "Error processing location. Please try again.": "处理位置时出错。请重试。",
    "File received. However, file upload is not expected in this context. Please use the menu buttons provided for selection.": "文件已收到。但此上下文中不需要上传文件。请使用提供的菜单按钮进行选择。",
    "Error processing file. Please try again.": "处理文件时出错。请重试。",
    "Error displaying the booking menu. Please try again.": "显示预约菜单时出错。请重试。",
    "Unable to load services. Please try again.": "无法加载服务。请重试。",
    "Unable to load clinics. Please try again.": "无法加载诊所。请重试。",
    "Invalid selection. Please try again.": "选择无效。请重试。",
    "Invalid input. Returning to main menu.": "输入无效。正在返回主菜单。",
    "Invalid button selection. Please try again.": "按钮选择无效。请重试。",
    "{service_name}\n\n{service_description} are coming soon!\n\nWe're working to bring you the best {service_description}. Please check back later or contact our hotline for more information:\n📞 {hotline}": "{service_name}\n\n{service_description} 即将推出！\n\n我们正努力为您带来最好的{service_description}。请稍后再查看或联系我们的热线了解更多信息：\n📞 {hotline}",
    "Your checkup booking is confirmed on {date} at {time}.": "您的检查预约已确认，时间为 {date} {time}。",
    "Your consultation booking is confirmed on {date} at {time}.": "您的咨询预约已确认，时间为 {date} {time}。",
    "Your vaccination booking for {vaccine_type} is confirmed on {date} at {time}.": "您的 {vaccine_type} 疫苗接种预约已确认，时间为 {date} {time}。",
    "Your TCM {booking_type} booking is confirmed on {date} at {time}.": "您的传统医疗{booking_type}预约已确认，时间为 {date} {time}。",
    "Reminder: Your {details} is in {time_desc}": "提醒：您的{details}将在{time_desc}内开始",
    " - {remark}": " - {remark}",
    "Custom reminder: Your {details} is in {reminder_duration} hours": "自定义提醒：您的{details}将在{reminder_duration}小时内开始",
    "Reminder: Your TCM {booking_type} is in {time_desc}": "提醒：您的传统医疗{booking_type}将在{time_desc}内开始",
    "Custom reminder: Your TCM {booking_type} is in {reminder_duration} hours": "自定义提醒：您的传统医疗{booking_type}将在{reminder_duration}小时内开始",
    "Reminder: Your {service_type} for {patient_name} is scheduled tomorrow at {time}.": "提醒：您为 {patient_name} 安排的{service_type}定于明天 {time} 进行。",
    "No new notifications found.": "未找到新通知。",
    "Error: User not found.": "错误：未找到用户。",
    "N/A": "不适用",
    "Error displaying notifications. Please try again.": "显示通知时出错。请重试。",
    "Thank you for acknowledging!": "感谢您的确认！",
    "{len(message_parts)} notification(s) displayed!": "已显示 {len(message_parts)} 条通知！",
    "Appointment": "预约",
    "Vaccination": "疫苗接种",
    "TCM Appointment": "传统医疗预约",
    "consultation": "咨询",
    "Patient": "患者",
    "1 week": "1周",
    "1 day": "1天",
    "{hours} hours": "{hours}小时",
    "Home to Home Transfer": "住家转运",
    "Home to Hospital Transfer": "住家到医院转运",
    "Hospital to Home Discharge": "医院到住家出院转运",
    "Hospital to Hospital Transfer": "医院间转运",
    "Please describe your symptoms:": "请描述您的症状：",
    "Do you have any additional remarks about your symptoms?": "关于您的症状，您有任何额外备注吗？",
    "Please enter your additional remarks:": "请输入您的额外备注：",
    "✅ Your GP consultation booking has been submitted!\n\nDoctor: {doctor}\nDate: {date}\nTime: {time}\nDuration: {duration} minutes\nSymptoms: {symptoms}...\n\nBooking is pending approval. You'll be notified once confirmed.\nBooking ID: {booking_id}...": "✅ 您的全科医生咨询预约已提交！\n\n医生：{doctor}\n日期：{date}\n时间：{time}\n时长：{duration} 分钟\n症状：{symptoms}...\n\n预约待批准。确认后您将收到通知。\n预约编号：{booking_id}...",
    "Error saving booking. Please try again or contact clinic for assistance.": "保存预约时出错。请重试或联系诊所寻求帮助。",
    "Clinic not selected. Please contact support.": "未选择诊所。请联系支持。",
    "Select AM or PM for {}:": "为 {} 选择上午或下午：",
    "Select an hour range for {}:": "为 {} 选择小时范围：",
    "Confirm your TCM booking:": "确认您的传统医疗预约：",
    "• Service: {}": "• 服务：{}",
    "• Method: {}": "• 方式：{}",
    "• Doctor: {}": "• 医生：{}",
    "• Doctor: Assigned by Clinic": "• 医生：由诊所分配",
    "• Date: {}": "• 日期：{}",
    "• Time: {}": "• 时间：{}",
    "• Duration: {} min": "• 时长：{} 分钟",
    "• Details: {}": "• 详情：{}",
    "• Address: {}": "• 地址：{}",
    "• Reminder: {}": "• 提醒：{}",
    "Due to the appointment method allowing for doctor flexibility, the doctor will contact you by 10 AM on the selected date. Note: Your booking may be rescheduled, and you may need to go to 'upcoming bookings' to accept or decline the suggested time after notification has been sent to you.": "由于此预约方式允许医生灵活安排，医生将在选定日期的上午10点前联系您。注意：您的预约可能会被改期，收到通知后，您可能需要前往'即将进行的预约'接受或拒绝建议的时间。",
    "An error occurred while confirming the booking. Please try again.": "确认预约时出错。请重试。",
    "The TCM booking is not placed": "传统医疗预约未成功安排",
    "Doctor selection is not enabled for this clinic. Please contact the clinic directly for doctor changes.": "此诊所未启用医生选择功能。如需更换医生，请直接联系诊所。",
    "Please share your current location or enter your address manually:": "请分享您的当前位置或手动输入您的地址：",
    "Unable to retrieve address from location. Please enter manually:": "无法从位置信息中提取地址。请手动输入：",
    "Is this address correct?\n{}": "这个地址正确吗？\n{}",
    "Please enter a valid address:": "请输入有效地址：",
    "Please edit the address and send it back:": "请编辑地址并发回：",
    "Do you have any remarks for {} ({} min)?": "您对{}（{}分钟）有任何备注吗？",
    "Clinic not found. Please select another clinic.": "未找到诊所。请选择其他诊所。",
    "Now please select a treatment category:": "现在请选择治疗类别：",
    "Unable to load clinic information. Please try again.": "无法加载诊所信息。请重试。",
    "Unable to load TCM services. Please try again.": "无法加载传统医疗服务。请重试。",
    "No {} clinics available at the moment. Please select another service type.": "目前没有可用的{}诊所。请选择其他服务类型。",
    "Unable to load TCM clinics. Please try again.": "无法加载传统医疗诊所。请重试。",
    "No categories available for this clinic. Please select another clinic.": "此诊所没有可用类别。请选择其他诊所。",
    "Unable to load categories. Please try again.": "无法加载类别。请重试。",
    "Error: Clinic or category not selected. Please start over.": "错误：未选择诊所或类别。请重新开始。",
    "No services available in this category. Please select another category.": "此类别中没有可用服务。请选择其他类别。",
    "Unable to load services. Please try again.": "无法加载服务。请重试。",
    "Please select the type of TCM service you need:": "请选择您需要的传统医疗服务类型：",
    "Please select a {} clinic:": "请选择{}诊所：",
    "Please select a treatment category:": "请选择治疗类别：",
    "Please select a treatment service:": "请选择治疗服务：",
    "Patient information not found. Please select a patient first.": "未找到患者信息。请先选择患者。",
    "No details available": "无详细信息",
    "Quantity:": "数量：",
    "Dosage:": "剂量：",
    "Method:": "方法：",
    "Take:": "服用：",
    "before meal": "饭前",
    "after meal": "饭后",
    "with meal": "随餐",
    "on empty stomach": "空腹",
    "Purpose:": "目的：",
    "Note:": "备注：",
    "Duration:": "时长：",
    "Frequency:": "频率：",
    "No medications or items found for any visit.": "任何就诊记录中均未找到药物或物品。",
    "💊 **Medications:**": "💊 **药物：**",
    "🩺 **Equipment:**": "🩺 **设备：**",
    "🛒 **Products:**": "🛒 **产品：**",
    "📞 **Contact your clinic if you have any questions.**": "📞 **如有任何疑问，请联系您的诊所。**",
    "Error loading all medications. Please try again.": "加载所有药物时出错。请重试。",
    "Error loading profiles. Please try again.": "加载档案时出错。请重试。",
    "Patient not found.": "未找到患者。",
    "Account locked. Please contact contact@anyhealth.asia to unlock.": "账户已锁定。请联系 contact@anyhealth.asia 解锁。",
    "Error in verification. Please try again.": "验证过程中出错。请重试。",
    "Verification failed. Please try again.": "验证失败。请重试。",
    "No visits found for {}.": "未找到{}的就诊记录。",
    "Error loading disease information. Please try again.": "加载疾病信息时出错。请重试。",
    "No disease diagnoses found for this patient.": "未找到此患者的疾病诊断。",
    "Diagnosis:": "诊断：",
    "Suspected Disease:": "疑似疾病：",
    "📞 Contact your clinic for more information.": "📞 请联系您的诊所了解更多信息。",
    "Medication & Routine module is currently unavailable. Please try again later.": "药物与日常管理模块目前不可用。请稍后再试。",
    "Error loading medication details. Please try again.": "加载药物详情时出错。请重试。",
    "No visiting history found for {}.": "未找到{}的就诊历史。",
    "Error loading visiting history. Please try again.": "加载就诊历史时出错。请重试。",
    "Error displaying visits. Please try again.": "显示就诊记录时出错。请重试。",
    "No documents available for this visit.": "此就诊记录没有可用文件。",
    "Error loading documents. Please try again.": "加载文件时出错。请重试。",
    "Medical Certificate": "病假单",
    "Invoice": "发票",
    "Referral Letter": "转诊信",
    "Consultation Report": "咨询报告",
    "Document not available. Please select another document.": "文件不可用。请选择其他文件。",
    "Error sending document. Please try again.": "发送文件时出错。请重试。",
    "IC must be 12 digits": "身份证必须是12位数字",
    "Please enter the IC number (12 digits):\nFormat: XXXXXX-XX-XXXX or XXXXXX XX XXXX or XXXXXXXXXXXX\n\nNote: Only Malaysian IC accepted, no passport.": "请输入身份证号码（12位）：\n格式：XXXXXX-XX-XXXX 或 XXXXXX XX XXXX 或 XXXXXXXXXXXX\n\n注意：仅接受马来西亚身份证，不接受护照。",
    "Invalid IC: {}. Please enter a valid 12-digit Malaysian IC:": "身份证无效：{}。请输入有效的12位马来西亚身份证号码：",
    "❌ This IC has reached maximum detachment attempts.\nPlease email contact@anyhealth.asia or visit partner clinics.": "❌ 此身份证已达到最大解绑尝试次数。\n请发送邮件至 contact@anyhealth.asia 或访问合作诊所。",
    "✅ This IC is already registered to your account.": "✅ 此身份证已注册到您的账户。",
    "Please enter the full name:": "请输入全名：",
    "Invalid name. Please enter a valid name (minimum 2 characters):": "姓名无效。请输入有效姓名（至少2个字符）：",
    "Please specify the race:": "请指定种族：",
    "Please specify the religion:": "请指定宗教：",
    "Error: WhatsApp user not found. Please try again.": "错误：未找到WhatsApp用户。请重试。",
    "Error creating profile: {}": "创建档案时出错：{}",
    "No profiles found to remove.": "未找到要移除的档案。",
    "Error loading profiles for removal. Please try again.": "加载要移除的档案时出错。请重试。",
    "⚠️ WARNING: Removing a profile will erase all previous data.\nTo undo this action, you will need to visit our nearest partner clinics.\n\nAre you sure you want to continue?": "⚠️ 警告：移除档案将删除所有先前数据。\n要撤销此操作，您需要访问我们最近合作诊所。\n\n确定要继续吗？",
    "Profile removal cancelled.": "档案移除已取消。",
    "Profile removed successfully.": "档案已成功移除。",
    "Error removing profile. Please try again.": "移除档案时出错。请重试。",
    "⚠️ *CHANGED NUMBERS*": "⚠️ *已更换号码*",
    "Error starting process. Please try again.": "启动流程时出错。请重试。",
    "⚠️ For security, please retype your full phone number starting with 60... (e.g., 601223456789):": "⚠️ 为安全起见，请重新输入以60开头的完整电话号码（例如：601223456789）：",
    "Too many failed attempts. Reset process cancelled.": "失败尝试次数过多。重置流程已取消。",
    "User not found.": "未找到用户。",
    "Phone number does not match. {} attempt(s) left.\nPlease retype your full phone number starting with 60...:": "电话号码不匹配。还剩{}次尝试。\n请重新输入以60开头的完整电话号码：",
    "Phone verification failed. Reset process cancelled.": "电话验证失败。重置流程已取消。",
    "Error verifying phone number. Please try again.": "验证电话号码时出错。请重试。",
    "✅ All profiles have been reset successfully!\n\nYour WhatsApp account has been refreshed with no profiles.": "✅ 所有档案已成功重置！\n\n您的WhatsApp账户已刷新，无任何档案。",
    "Error during reset process. Please try again.": "重置过程中出错。请重试。",
    "Error starting verification. Please try again.": "启动验证时出错。请重试。",
    "Step 1/4: Enter the full name:": "步骤1/4：输入全名：",
    "Error verifying name. Please try again.": "验证姓名时出错。请重试。",
    "Step 2/4: Enter the race (e.g., Malay, Chinese, Indian, etc.):": "步骤2/4：输入种族（例如：马来人、华人、印度人等）：",
    "Error verifying race. Please try again.": "验证种族时出错。请重试。",
    "Step 3/4: Enter the religion:": "步骤3/4：输入宗教：",
    "Error verifying religion. Please try again.": "验证宗教时出错。请重试。",
    "Step 4/4: Enter the blood type (e.g., A+, B-, O+):": "步骤4/4：输入血型（例如：A+、B-、O+）：",
    "✅ Profile detached successfully!\n\nThe profile is now available for reattachment.\nTo add it to your account, please email contact@anyhealth.asia or visit partner clinics.": "✅ 档案解绑成功！\n\n该档案现在可供重新绑定。\n要将其添加到您的账户，请发送邮件至 contact@anyhealth.asia 或访问合作诊所。",
    "❌ Verification failed 3 times.\nProfile is now locked.\nPlease email contact@anyhealth.asia or visit partner clinics.": "❌ 验证失败3次。\n档案现已锁定。\n请发送邮件至 contact@anyhealth.asia 或访问合作诊所。",
    "❌ Verification failed.\nYou have {} attempt(s) left.\nPlease try again or visit partner clinics.": "❌ 验证失败。\n您还剩{}次尝试。\n请重试或访问合作诊所。",
    "Error completing verification. Please try again.": "完成验证时出错。请重试。",
    "❌ IC not found in our system.": "❌ 我们的系统中未找到此身份证。",
    "✅ This IC is not attached to any WhatsApp account.\nYou can add it directly.": "✅ 此身份证未绑定任何WhatsApp账户。\n您可以直接添加。",
    "✅ This IC is already attached to your current account.\nNo need to detach.": "✅ 此身份证已绑定到您当前的账户。\n无需解绑。",
    "❌ This IC has reached maximum detachment attempts (3).\nPlease email contact@anyhealth.asia or visit partner clinics.": "❌ 此身份证已达到最大解绑尝试次数（3次）。\n请发送邮件至 contact@anyhealth.asia 或访问合作诊所。",
    "Detachment cancelled.": "解绑已取消。",
    "⚠️ *RESET ACCOUNT WARNING*": "⚠️ *重置账户警告*",
    "⚠️ *DETACH FROM OLD NUMBER*": "⚠️ *从旧号码解绑*",
    "Please enter the 12-digit IC of the profile to detach:": "请输入要解绑的档案的12位身份证号码：",
    "An error occurred in edit module. Please try again.": "编辑模块中发生错误。请重试。",
    "User not found. Please ensure your number is registered.": "未找到用户。请确保您的号码已注册。",
    "Error fetching user information. Please try again.": "获取用户信息时出错。请重试。",
    "Unknown": "未知",
    "Unknown Clinic": "未知诊所",
    "Unknown TCM Doctor": "未知传统医疗师",
    "Unknown TCM Clinic": "未知传统医疗诊所",
    "Unknown Provider": "未知提供方",
    "You have no upcoming bookings.": "您没有即将进行的预约。",
    "No bookings found in any category.": "任何类别中均未找到预约。",
    "Invalid booking selection. Please try again.": "预约选择无效。请重试。",
    "⚠️ REPEATED VISIT CANCELLATION\n\nThis is part of a repeated visit series. Do you want to cancel just this booking or all future repeated bookings?": "⚠️ 重复就诊取消\n\n这是重复就诊系列的一部分。您想只取消本次预约，还是取消所有未来的重复预约？",
    "❌ CANCELLATION FAILED\n\nBooking not found. It may have already been cancelled.": "❌ 取消失败\n\n未找到预约。可能已被取消。",
    "✅ BOOKING CANCELLED\n\nYour booking has been successfully cancelled.": "✅ 预约已取消\n\n您的预约已成功取消。",
    "❌ ERROR\n\nError cancelling booking. Please try again.": "❌ 错误\n\n取消预约时出错。请重试。",
    "❌ ERROR\n\nReschedule request not found or has invalid data. Please try again.": "❌ 错误\n\n未找到改期请求或数据无效。请重试。",
    "Invalid booking type for reschedule request.": "改期请求的预约类型无效。",
    "✅ ACCEPTED RESCHEDULE\n\nYou have accepted the reschedule. Your {} is now confirmed on {} at {}.": "✅ 已接受改期\n\n您已接受改期。您的{}现确认于{} {}。",
    "✅ DECLINED RESCHEDULE\n\nYou have declined the reschedule request.": "✅ 已拒绝改期\n\n您已拒绝改期请求。",
    "❌ ERROR\n\nError declining reschedule. Please try again.": "❌ 错误\n\n拒绝改期时出错。请重试。",
    "✅ TCM RESCHEDULE ACCEPTED\n\nYou have accepted the reschedule. Your TCM {} is now confirmed on {} at {} with Dr. {}.": "✅ 传统医疗改期已接受\n\n您已接受改期。您的传统医疗{}现确认于{} {}，医生：{}。",
    "❌ ERROR\n\nError accepting TCM reschedule. Please try again.": "❌ 错误\n\n接受传统医疗改期时出错。请重试。",
    "TCM Doctor": "传统医疗师",
    "✅ TCM RESCHEDULE DECLINED\n\nYou have declined the reschedule request. Your TCM {} remains confirmed on {} at {} with Dr. {}.": "✅ 传统医疗改期已拒绝\n\n您已拒绝改期请求。您的传统医疗{}仍确认于{} {}，医生：{}。",
    "✅ TCM RESCHEDULE DECLINED\n\nYou have declined the reschedule request.": "✅ 传统医疗改期已拒绝\n\n您已拒绝改期请求。",
    "❌ ERROR\n\nError declining TCM reschedule. Please try again.": "❌ 错误\n\n拒绝传统医疗改期时出错。请重试。",
    "❌ ERROR\n\nError processing cancellation. Please try again.": "❌ 错误\n\n处理取消时出错。请重试。",
    "✅ ALL REPEATED BOOKINGS CANCELLED\n\nAll repeated bookings in this series have been cancelled.": "✅ 所有重复预约已取消\n\n此系列中的所有重复预约均已取消。",
    "❌ ERROR\n\nError cancelling repeated bookings. Please try again.": "❌ 错误\n\n取消重复预约时出错。请重试。",
    "This is part of a repeated visit series. Only this specific appointment will be rescheduled. Continue?": "这是重复就诊系列的一部分。仅此特定预约将被改期。继续吗？",
    "Error processing reschedule confirmation. Please try again.": "处理改期确认时出错。请重试。",
    "❌ RESCHEDULE CANCELLED\n\nYour booking remains unchanged.": "❌ 改期已取消\n\n您的预约保持不变。",
    "Error confirming reschedule. Please try again.": "确认改期时出错。请重试。",
    "❌ RESCHEDULE FAILED\n\nAn error occurred while processing your reschedule request. Please try again or contact support.": "❌ 改期失败\n\n处理您的改期请求时出错。请重试或联系支持。",
    "❌ ERROR\n\nAn unexpected error occurred. Please try again.": "❌ 错误\n\n发生意外错误。请重试。",
    "❌ SESSION EXPIRED\n\nPlease start the reschedule process again.": "❌ 会话已过期\n\n请重新开始改期流程。",
    "Error fetching default doctor for clinic {}": "获取诊所 {} 的默认医生时出错",
    "❌ UNABLE TO COMPLETE\n\nUnable to complete reschedule. No doctor information available. Please contact support.": "❌ 无法完成\n\n无法完成改期。无医生信息可用。请联系支持。",
    "✅ RESCHEDULE SUCCESSFUL!{}\n\n{} rescheduled to {} at {} with Dr. {}.\n\nStatus: PENDING CONFIRMATION": "✅ 改期成功！{}\n\n{}改期至{} {}，医生：{}。\n\n状态：待确认",
    "❌ DATABASE ERROR\n\nError saving reschedule. Please try again.": "❌ 数据库错误\n\n保存改期时出错。请重试。",
    "Error fetching TCM doctor name: {}": "获取传统医疗师姓名时出错：{}",
    "✅ TCM RESCHEDULE SUCCESSFUL!{}\n\nTCM {} rescheduled to {} at {} with Dr. {}.\n\nStatus: PENDING CONFIRMATION": "✅ 传统医疗改期成功！{}\n\n传统医疗{}改期至{} {}，医生：{}。\n\n状态：待确认",
    "Error fetching updated TCM booking: {}": "获取更新的传统医疗预约时出错：{}",
    "✅ TCM RESCHEDULE SUCCESSFUL!\n\nYour TCM appointment has been rescheduled.\n\nStatus: PENDING CONFIRMATION": "✅ 传统医疗改期成功！\n\n您的传统医疗预约已改期。\n\n状态：待确认",
    "❌ TCM RESCHEDULE FAILED\n\nError rescheduling TCM appointment. Please try again.": "❌ 传统医疗改期失败\n\n传统医疗预约改期时出错。请重试。",
    "❌ RESCHEDULE CANCELLED\n\nYour TCM booking reschedule has been cancelled.": "❌ 改期已取消\n\n您的传统医疗预约改期已取消。",
    "❌ ERROR\n\nError cancelling TCM reschedule. Please try again.": "❌ 错误\n\n取消传统医疗改期时出错。请重试。",
    "Returning to main menu.": "正在返回主菜单。",
    "Ambulance bookings cannot be rescheduled or cancelled via WhatsApp. Please contact the ambulance service directly for any changes.": "救护车预约无法通过WhatsApp改期或取消。如需任何更改，请直接联系救护车服务。",
    "Invalid selection. Please try again.": "选择无效。请重试。",
    "Error processing booking type selection. Please try again.": "处理预约类型选择时出错。请重试。",
    "An unexpected error occurred while fetching upcoming bookings. Please try again.": "获取即将进行的预约时发生意外错误。请重试。",
    "❌ SYSTEM ERROR\n\nAn error occurred in the booking system. Please try again.": "❌ 系统错误\n\n预约系统中发生错误。请重试。",
    "No bookings found in the {} category.": "在{}类别中未找到预约。",
    "Error processing booking selection. Please try again.": "处理预约选择时出错。请重试。",
    "Error processing action. Please try again.": "处理操作时出错。请重试。",
    "Doctor": "医生",
    "Any Doctor": "任何医生",
    "Would you like to book an appointment at this clinic?": "您想在此诊所预约吗？",


    # BUTTON
    "Menu": "菜单",
    "Booking Options": "预约选项",
    "✅ Yes": "✅ 是",
    "❌ No": "❌ 否",
    "Select Service": "选择服务",
    "Noted": "知道了",
    "Select Language": "选择语言",
    "✅ Yes, Book": "✅ 是的，预约",
    "❌ No, Just Browsing": "❌ 不，仅浏览",
    "Back": "返回",
    "More Doctors": "更多医生",
    "Select Option": "选择选项",
    "Yes": "是",
    "No": "否",
    "📍 Share Location": "📍 分享位置",
    "📝 Type Address": "📝 输入地址",
    "✅ Yes, Correct": "✅ 是的，正确",
    "✏️ Edit Address": "✏️ 编辑地址",
    "Next": "下一步",
    "Skip": "跳过",
    "Add Remarks": "添加备注",
    "Today": "今天",
    "Tomorrow": "明天",
    "Others": "其他日期",
    "AM (12am - 11:45am)": "上午 (12am - 11:45am)",
    "PM (12pm - 11:45pm)": "下午 (12pm - 11:45pm)",
    "Select Time Slot": "选择时间段",
    "Select Time": "选择时间",
    "❌ No, Different": "❌ 不，不同",
    "Choose Doctor": "选择医生",
    "Any Doctor": "任何医生",
    "Choose Date": "选择日期",
    "📅 Future Date": "📅 其他日期",
    "AM": "上午",
    "PM": "下午",
    "Choose Hour": "选择小时",
    "Choose Slot": "选择时段",
    "Confirm": "确认",
    "Edit": "编辑",
    "Cancel": "取消",
    "Edit Option": "编辑选项",
    "Change Time": "更改时间",
    "Change Date": "更改日期",
    "Change Doctor": "更改医生",
    "Change Service": "更改服务",
    "Try Again": "重试",
    "Help Me Choose": "帮我选择",
    "Find Another": "查找其他",
    "Try Another Time": "尝试其他时间",
    "Choose Method": "选择方式",
    "🔙 Back to Type Selection": "🔙 返回类型选择",
    "🔙 Back to Clinics": "🔙 返回诊所列表",
    "🔙 Back to Categories": "🔙 返回类别",
    "Select Type": "选择类型",
    "Chiropractic": "脊椎治疗",
    "Physiotherapy": "物理治疗",
    "🔙 Back to Services": "🔙 返回服务列表",
    "Select Clinic": "选择诊所",
    "Select Category": "选择类别",
    "Select Service": "选择服务",
    "🔙 Back to Options": "🔙 返回选项",
    "Manage Profiles": "管理档案",
    "Select Visit": "选择就诊",
    "📄 Another Document": "📄 其他文件",
    "🔙 Back to Edit Menu": "🔙 返回编辑菜单",
    "🔙 Back to Religion": "🔙 返回宗教",
    "Select Profile": "选择档案",
    "➕ Add Profile": "➕ 添加档案",
    "➖ Remove Profile": "➖ 移除档案",
    "🔙 Back to Profiles": "🔙 返回档案列表",
    "Yes, detach": "是的，解绑",
    "No, cancel": "不，取消",
    "Yes, reset": "是的，重置",
    "No, cancel": "不，取消",
    "Select Type": "选择类型",
    "Choose Booking": "选择预约",
    "Accept": "接受",
    "Decline": "拒绝",
    "Back to Home": "返回主页",
    "Reschedule": "改期",
    "Cancel Booking": "取消预约",
    "Choose Another": "选择其他",
    "Confirm Time": "确认时间",
    "Back": "返回",
    "Reschedule One": "改期单次",
    "Back to actions": "返回操作",
    "Cancel This One Only": "仅取消本次",
    "Cancel All Repeated": "取消所有重复",


    # FOOTER
    "Select an option to proceed": "请选择选项继续",
    "Choose an option below": "请在下方选择",
    "Choose a language to proceed": "请选择语言继续",
    "Choose a service to proceed": "请选择服务继续",
    "Choose a clinic to proceed": "请选择诊所继续",
    "Choose a service type to proceed": "请选择服务类型继续",
    "Choose a category to proceed": "请选择类别继续",


    # SECTION TITLES
    "Main Options": "主要选项",
    "Booking Services": "预约服务",
    "Available Services": "可用服务",
    "Languages": "语言",
    "Service Booking": "服务预约",
    "Available Clinics": "可用诊所",
    "Booking Options": "预约选项",
    "Your Profiles": "您的档案",
    "Available Options": "可用选项",
    "Visiting History": "就诊历史",
    "Available Documents": "可用文件",
    "Available Races": "可选种族",
    "Available Religions": "可选宗教",
    "Blood Types": "血型",
    "Booking Categories": "预约类别",
    "{} Bookings": "{}预约",
    "Available Doctors": "可选医生",
    "Available Dates": "可选日期",
    "{period} Hours": "{period}小时段",
    "{}min Slots": "{}分钟时段",
    "Edit Options": "编辑选项",
    "TCM Service Types": "传统医疗服务类型",
    "Available {} Clinics": "可用{}诊所",
    "Treatment Categories": "治疗类别",
    "Available Methods": "可用方式",
    "Available Services": "可用服务",


    # LIST ROW TITLES
    "👤 Profile": "👤 档案",
    "🏥 Service Booking": "🏥 服务预约",
    "📅 Upcoming Booking": "📅 即将进行的预约",
    "❓ Help": "❓ 帮助",
    "🌐 Languages": "🌐 语言",
    "🔔 Notification": "🔔 通知",
    "📞 Clinic Enquiries": "📞 诊所咨询",
    "👨‍⚕️ General GP Visit": "👨‍⚕️ 全科医生看诊",
    "🩺 Checkup & Test": "🩺 检查与测试",
    "💉 Vaccination": "💉 疫苗接种",
    "🔙 Back to Main Menu": "🔙 返回主菜单",
    "🏠 → 🏥 Home to Hosp": "🏠 → 🏥 住家到医院",
    "🏠 → 🏠 Home to Home": "🏠 → 🏠 住家转运",
    "🏥 → 🏠 Hosp to Home": "🏥 → 🏠 医院到住家",
    "🏥 → 🏥 Hosp to Hosp": "🏥 → 🏥 医院间",
    "English": "English",
    "Bahasa Malaysia": "Bahasa Malaysia",
    "中文": "中文",
    "தமிழ்": "தமிழ்",
    "🏥 Clinic Services": "🏥 诊所服务",
    "🌿 TCM Services": "🌿 传统医疗服务",
    "🚑 Ambulance Service": "🚑 救护车服务",
    "💅 Aesthetic": "💅 医美",
    "🏨 Hospital": "🏨 医院",
    "💉 Dialysis": "💉 透析",
    "👴 Elderly Care": "👴 长者护理",
    "🔙 Back to Main": "🔙 返回主页",
    "🔙 Back to Booking": "🔙 返回预约",
    "Health Screening Plan": "健康筛查计划",
    "View Upcoming Bookings": "查看即将进行的预约",
    "📝 Edit Profiles": "📝 编辑档案",
    "🔄 Changed Numbers": "🔄 已更换号码",
    "➡️ Next Page": "➡️ 下一页",
    "⬅️ Previous Page": "⬅️ 上一页",
    "🔙 Back to Menu": "🔙 返回菜单",
    "⚔️ Enemy (Disease)": "⚔️ 病况",
    "💊 Med & Routine": "💊 药物与日常",
    "📄 Report": "📄 报告",
    "🔙 Back to Profiles": "🔙 返回档案",
    "📄 Medical Certificate": "📄 病假单",
    "💰 Bill/Invoice": "💰 账单/发票",
    "📋 Referral Letter": "📋 转诊信",
    "📊 Consultation Report": "📊 咨询报告",
    "Malay": "马来人",
    "Chinese": "华人",
    "Indian": "印度人",
    "Bumiputera Sabah": "沙巴土著",
    "Bumiputera Sarawak": "砂拉越土著",
    "Others": "其他",
    "Muslim": "穆斯林",
    "Buddhist": "佛教徒",
    "Christian": "基督徒",
    "Hindu": "兴都教徒",
    "Sikh": "锡克教徒",
    "🔄 Reset account": "🔄 重置账户",
    "📱 Detach from old": "📱 从旧号码解绑",
    "❌ Cancel": "❌ 取消",
    "Action Required": "需您操作",
    "Confirmed": "已确认",
    "Pending": "待处理",
    "🔙 Back": "🔙 返回",
    "Booking {}": "预约{}",


    # LIST ROW DESCRIPTIONS
    "GP, Checkup, Vaccination, Health Screening": "全科、检查、疫苗接种、健康筛查",
    "Chiro, Physio, Rehab, Traditional Medicine": "脊椎、物理、康复、传统医学",
    "Non-emergency medical transport": "非紧急医疗转运",
    "Coming soon": "即将推出",
    "Coming soon": "即将推出",
    "Coming soon": "即将推出",
    "Coming soon": "即将推出",
    "View diagnosed conditions": "查看诊断病情",
    "View all medications and items": "查看所有药物与物品",
    "Select visit for MC, Invoice, etc.": "选择就诊记录以获取病假单、发票等",
    "Start fresh with new account": "以新账户重新开始",
    "Move profile from old number": "将档案从旧号码移出",
    "{} booking(s) need your action": "{}个预约需您操作",
    "{} confirmed booking(s)": "{}个已确认预约",
    "{} pending booking(s)": "{}个待处理预约",
    "Return to main menu": "返回主菜单",
    "Spinal adjustments, posture correction": "脊椎调整、姿势矫正",
    "Muscle therapy, joint mobilization": "肌肉疗法、关节松动",


    # Existing translation from your example (kept for consistency)
    "Sorry, clinic information is not available at the moment.": "抱歉，目前无法获取诊所信息。",
    "Clinic Enquiries": "诊所咨询",
    "Failed to save booking. Please try again.": "保存预约失败。请重试。",
    "✅ Your TCM booking has been submitted!": "✅ 您的传统医疗预约已提交！",
    "Service: {}": "服务：{}",
    "Date: {}": "日期：{}",
    "Time: {}": "时间：{}",
    "Duration: {} minutes": "时长：{}分钟",
    "Method: {}": "方式：{}",
    "Due to doctor flexibility, the doctor will contact you by 10 AM on the selected date. Your booking may be rescheduled - please check your upcoming bookings to accept or decline suggested times.": "因医生时间灵活，医生将在选定日期上午10点前联系您。您的预约可能会改期 - 请查看即将进行的预约以接受或拒绝建议的时间。",
    "Booking is pending approval. You'll be notified once confirmed.": "预约待批准。确认后您将收到通知。",
    "Booking ID: {}": "预约编号：{}",
    "Failed to send confirmation. Booking cancelled. Please try again.": "发送确认失败。预约已取消。请重试。",
    "An error occurred while confirming the booking: {}. Please try again.": "确认预约时出错：{}。请重试。"
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
                        text_to_translate, source_language="en", target_language="zh-CN", format_="text"
                    )
                    translated_text = html.unescape(google_result["translatedText"]) if google_result and "translatedText" in google_result else text_to_translate
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

