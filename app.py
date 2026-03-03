import os
import re
import requests
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from supabase import create_client, Client
from datetime import datetime
import random

# Danh sách các từ có nghĩa để ghép mật khẩu
WORDS = ["Tiger", "Ocean", "River", "Falcon", "Dragon", "Coffee", "Crystal", "Shadow", "Thunder", "Rocket", "Silver", "Golden", "Cosmic", "Quantum", "Cyber", "Ninja", "Phoenix", "Galaxy", "Neon", "Mango"]

def generate_hf_password():
    """Tạo password > 10 kí tự: 2 từ có nghĩa + số + kí tự đặc biệt"""
    word1 = random.choice(WORDS)
    word2 = random.choice(WORDS)
    while word1 == word2: # Đảm bảo 2 từ không bị trùng nhau
        word2 = random.choice(WORDS)
    
    number = str(random.randint(10, 999)) # 2 đến 3 số ngẫu nhiên
    special_char = random.choice("!@#$%^&*")
    
    return f"{word1}{word2}{number}{special_char}"

# Tải các biến môi trường từ file .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Khởi tạo Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /start"""
    await update.message.reply_text(
        "👋 Chào bạn!\n\n"
        "📎 Gửi file .txt (định dạng `email|pass|token|client_id`) để import.\n"
        "📥 Gõ /get để lấy tài khoản chưa sử dụng."
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý file .txt người dùng gửi lên"""
    document = update.message.document
    
    # Chỉ nhận file .txt
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Vui lòng gửi file có định dạng .txt")
        return

    status_msg = await update.message.reply_text("⏳ Đang xử lý file...")
    
    try:
        file = await context.bot.get_file(document.file_id)
        file_bytes = await file.download_as_bytearray()
        content = file_bytes.decode('utf-8').splitlines()
        
        records_to_insert = []
        for line in content:
            parts = line.strip().split('|')
            if len(parts) == 4:
                records_to_insert.append({
                    "email": parts[0],
                    "password": parts[1],
                    "refresh_token": parts[2],
                    "client_id": parts[3],
                    "is_used": False
                })
                
        if records_to_insert:
            # Thêm dữ liệu vào Supabase
            supabase.table("accounts").insert(records_to_insert).execute()
            await status_msg.edit_text(f"✅ Đã import thành công {len(records_to_insert)} tài khoản vào cơ sở dữ liệu.")
        else:
            await status_msg.edit_text("❌ Không tìm thấy dòng nào đúng định dạng (email|pass|token|client_id).")
            
    except Exception as e:
        await status_msg.edit_text(f"❌ Lỗi khi xử lý: {str(e)}")

async def get_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /get"""
    try:
        # Lấy 1 tài khoản chưa sử dụng
        response = supabase.table("accounts").select("*").eq("is_used", False).limit(1).execute()
        accounts = response.data
        
        if not accounts:
            await update.message.reply_text("⚠️ Đã hết tài khoản khả dụng trong hệ thống!")
            return
            
        acc = accounts[0]
        
        # Tạo password Higgsfield mới
        hf_pass = generate_hf_password()
        
        # Nút bấm lấy code
        keyboard = [
            [InlineKeyboardButton("🚀 Get code Higgsfield", callback_data=f"getcode_{acc['id']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            f"📧 **Email:** `{acc['email']}`\n"
            f"🔑 **Password Email:** `{acc['password']}`\n"
            f"🔐 **Password Higgsfield:** `{hf_pass}`"
        )
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi truy xuất DB: {str(e)}")
def find_higgsfield_code(data):
    """
    Hàm lục lọi toàn bộ cấu trúc JSON.
    Nếu tìm thấy chuỗi nào chứa chữ 'higgsfield' (không phân biệt hoa thường),
    nó sẽ dùng regex để bóc tách 6 số trong chuỗi đó.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            result = find_higgsfield_code(value)
            if result: 
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_higgsfield_code(item)
            if result: 
                return result
    elif isinstance(data, str):
        # Chuyển string về chữ thường để dễ so sánh
        text_lower = data.lower()
        if 'higgsfield' in text_lower:
            # Nếu tin nhắn này của Higgsfield, mới bắt đầu tìm 6 số
            match = re.search(r'\b\d{6}\b', data)
            if match:
                return match.group(0)
    return None

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý nút bấm lấy code"""
    query = update.callback_query
    await query.answer("Đang request API lấy code, vui lòng chờ...")
    
    data = query.data
    if data.startswith("getcode_"):
        acc_id = data.split("_")[1]
        
        # --- PHẦN MỚI: Trích xuất lại mật khẩu Higgsfield cũ từ tin nhắn để không bị đổi ---
        current_text = query.message.text
        hf_pass_match = re.search(r'Password Higgsfield:\s*(\S+)', current_text)
        hf_pass = hf_pass_match.group(1) if hf_pass_match else generate_hf_password()
        # ----------------------------------------------------------------------------------

        # Lấy lại thông tin acc để lấy token và client_id
        response = supabase.table("accounts").select("*").eq("id", acc_id).execute()
        if not response.data:
            await query.edit_message_text("❌ Không tìm thấy tài khoản này trong hệ thống.")
            return
            
        acc = response.data[0]
        
        # Gọi API
        api_url = "https://tools.dongvanfb.net/api/get_messages_oauth2"
        payload = {
            "email": acc['email'],
            "refresh_token": acc['refresh_token'],
            "client_id": acc['client_id']
        }
        
        try:
            api_res = requests.post(api_url, json=payload, timeout=20)
            result_json = api_res.json()
            
            # Sử dụng hàm quét thông minh thay vì regex toàn bộ
            code = find_higgsfield_code(result_json)
            
            if code:
                # Đánh dấu đã sử dụng
                supabase.table("accounts").update({"is_used": True}).eq("id", acc_id).execute()
                
                new_text = (
                    f"📧 **Email:** `{acc['email']}`\n"
                    f"🔑 **Password Email:** `{acc['password']}`\n"
                    f"🔐 **Password Higgsfield:** `{hf_pass}`\n"
                    f"✅ **Code:** `{code}`\n\n"
                    f"*(Tài khoản đã được cập nhật thành 'đã sử dụng')*"
                )
                await query.edit_message_text(new_text, parse_mode='Markdown')
            else:
                # Lấy thời gian hiện tại
                current_time = datetime.now().strftime("%H:%M:%S")
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Thử lại", callback_data=f"getcode_{acc_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"📧 **Email:** `{acc['email']}`\n"
                    f"🔑 **Password Email:** `{acc['password']}`\n"
                    f"🔐 **Password Higgsfield:** `{hf_pass}`\n"
                    f"⚠️ **Trạng thái:** Chưa tìm thấy mã 6 số từ Higgsfield.\n"
                    f"⏳ *Email có thể đến chậm, vui lòng đợi vài giây rồi bấm thử lại.*\n\n"
                    f"⏱️ *Lần check cuối: {current_time}*",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                
        except requests.exceptions.RequestException as e:
            current_time = datetime.now().strftime("%H:%M:%S")
            keyboard = [
                [InlineKeyboardButton("🔄 Thử lại", callback_data=f"getcode_{acc_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"❌ Call API thất bại: {str(e)}\n"
                f"🔐 **Password Higgsfield:** `{hf_pass}`\n\n"
                f"⏱️ *Lần check cuối: {current_time}*", 
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
                
        except requests.exceptions.RequestException as e:
            keyboard = [
                [InlineKeyboardButton("🔄 Thử lại", callback_data=f"getcode_{acc_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"❌ Call API thất bại: {str(e)}\n🔐 **Password Higgsfield:** `{hf_pass}`", 
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("get", get_account))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("🤖 Bot Telegram đang hoạt động...")
    app.run_polling()

if __name__ == "__main__":
    main()