import os
import re
import json
import random
import requests
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from supabase import create_client, Client

# Tải biến môi trường
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
USERS_FILE = 'users.json'

# --- HÀM XỬ LÝ USER (LƯU & ĐỌC JSON) ---
def load_users():
    """Đọc danh sách user đã lưu"""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_user(chat_id, username):
    """Lưu user mới vào file nếu chưa có"""
    users = load_users()
    if str(chat_id) not in users:
        users[str(chat_id)] = username
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=4)

# --- HÀM GỬI TIN NHẮN KHI BOT KHỞI ĐỘNG ---
async def post_init(application: Application):
    """Hàm này tự động chạy 1 lần duy nhất khi bot vừa bật"""
    users = load_users()
    success = 0
    for chat_id, username in users.items():
        try:
            await application.bot.send_message(
                chat_id=chat_id, 
                text=f"👋 Xin chào {username}, bot vừa mới được khởi động lại!"
            )
            success += 1
        except Exception as e:
            print(f"Không thể gửi cho {chat_id}: {e}")
    print(f"Đã gửi tin nhắn chào mừng tới {success}/{len(users)} users.")

# --- HÀM TẠO PASSWORD ---
WORDS = ["Tiger", "Ocean", "River", "Falcon", "Dragon", "Coffee", "Crystal", "Shadow", "Thunder", "Rocket", "Silver", "Golden", "Cosmic", "Quantum", "Cyber", "Ninja", "Phoenix", "Galaxy", "Neon", "Mango"]

def generate_hf_password():
    word1 = random.choice(WORDS)
    word2 = random.choice(WORDS)
    while word1 == word2:
        word2 = random.choice(WORDS)
    number = str(random.randint(10, 999))
    special_char = random.choice("!@#$%^&*")
    return f"{word1}{word2}{number}{special_char}"

# --- HÀM TÌM CODE HIGGSFIELD ---
def find_higgsfield_code(data):
    if isinstance(data, dict):
        for key, value in data.items():
            result = find_higgsfield_code(value)
            if result: return result
    elif isinstance(data, list):
        for item in data:
            result = find_higgsfield_code(item)
            if result: return result
    elif isinstance(data, str):
        if 'higgsfield' in data.lower():
            match = re.search(r'\b\d{6}\b', data)
            if match: return match.group(0)
    return None

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Lưu user khi họ gõ /start
    save_user(update.effective_chat.id, update.effective_user.first_name)
    await update.message.reply_text("👋 Chào bạn! Gửi file .txt để import hoặc gõ /get để lấy tài khoản.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_chat.id, update.effective_user.first_name)
    document = update.message.document
    if not document.file_name.endswith('.txt'):
        return await update.message.reply_text("❌ Vui lòng gửi file .txt")

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
                    "email": parts[0], "password": parts[1],
                    "refresh_token": parts[2], "client_id": parts[3],
                    "is_used": False
                })
        if records_to_insert:
            supabase.table("accounts").insert(records_to_insert).execute()
            await status_msg.edit_text(f"✅ Đã import {len(records_to_insert)} acc.")
        else:
            await status_msg.edit_text("❌ Không tìm thấy dòng đúng định dạng.")
    except Exception as e:
        await status_msg.edit_text(f"❌ Lỗi: {str(e)}")

async def get_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_chat.id, update.effective_user.first_name)
    try:
        response = supabase.table("accounts").select("*").eq("is_used", False).limit(1).execute()
        accounts = response.data
        if not accounts:
            return await update.message.reply_text("⚠️ Hết tài khoản khả dụng!")
            
        acc = accounts[0]
        hf_pass = generate_hf_password()
        
        keyboard = [[InlineKeyboardButton("🚀 Get code Higgsfield", callback_data=f"getcode_{acc['id']}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Form hiển thị mới theo ảnh
        text = (
            f"✅ **Higgsfield**\n\n"
            f"📧 `{acc['email']}`\n"
            f"🔑 `{acc['password']}`\n"
            f"🔐 `{hf_pass}`"
        )
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {str(e)}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Đang lấy mã...")
    
    data = query.data
    if data.startswith("getcode_"):
        acc_id = data.split("_")[1]
        
        # Cập nhật regex để lấy đúng pass Higgsfield theo form mới (tìm sau icon 🔐)
        current_text = query.message.text
        hf_pass_match = re.search(r'🔐\s*(\S+)', current_text)
        hf_pass = hf_pass_match.group(1) if hf_pass_match else generate_hf_password()

        response = supabase.table("accounts").select("*").eq("id", acc_id).execute()
        if not response.data:
            return await query.edit_message_text("❌ Không tìm thấy tài khoản.")
            
        acc = response.data[0]
        api_url = "https://tools.dongvanfb.net/api/get_messages_oauth2"
        payload = {"email": acc['email'], "refresh_token": acc['refresh_token'], "client_id": acc['client_id']}
        
        try:
            api_res = requests.post(api_url, json=payload, timeout=20)
            code = find_higgsfield_code(api_res.json())
            
            if code:
                supabase.table("accounts").update({"is_used": True}).eq("id", acc_id).execute()
                new_text = (
                    f"✅ **Higgsfield**\n\n"
                    f"📧 `{acc['email']}`\n"
                    f"🔑 `{acc['password']}`\n"
                    f"🔐 `{hf_pass}`\n"
                    f"✅ **Code:** `{code}`\n\n"
                    f"*(Acc đã chuyển trạng thái sử dụng)*"
                )
                await query.edit_message_text(new_text, parse_mode='Markdown')
            else:
                current_time = datetime.now().strftime("%H:%M:%S")
                keyboard = [[InlineKeyboardButton("🔄 Thử lại", callback_data=f"getcode_{acc_id}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    f"✅ **Higgsfield**\n\n"
                    f"📧 `{acc['email']}`\n"
                    f"🔑 `{acc['password']}`\n"
                    f"🔐 `{hf_pass}`\n\n"
                    f"⚠️ *Chưa thấy mã. Lần check: {current_time}*",
                    reply_markup=reply_markup, parse_mode='Markdown'
                )
        except requests.exceptions.RequestException as e:
            current_time = datetime.now().strftime("%H:%M:%S")
            keyboard = [[InlineKeyboardButton("🔄 Thử lại", callback_data=f"getcode_{acc_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"✅ **Higgsfield**\n\n"
                f"📧 `{acc['email']}`\n"
                f"🔑 `{acc['password']}`\n"
                f"🔐 `{hf_pass}`\n\n"
                f"❌ *Lỗi API. Lần check: {current_time}*", 
                reply_markup=reply_markup, parse_mode='Markdown'
            )

def main():
    # Thêm hàm post_init vào quá trình build
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("get", get_account))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("🤖 Bot đang hoạt động...")
    app.run_polling()

if __name__ == "__main__":
    main()