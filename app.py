import os
import re
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
    text = (
        "👋 **Hệ thống Quản lý Higgsfield Bot**\n\n"
        "Các lệnh hỗ trợ:\n"
        "📎 Gửi file `.txt` để import acc.\n"
        "📥 `/get` - Lấy 1 tài khoản mới.\n"
        "📊 `/stats` - Xem thống kê kho acc.\n"
        "🔍 `/search <email>` - Tìm nhanh acc."
    )
    await update.message.reply_text(text, parse_mode='Markdown')

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Thống kê lượng tài khoản trong Database"""
    try:
        res_all = supabase.table("accounts").select("id").execute()
        res_used = supabase.table("accounts").select("id").eq("is_used", True).execute()
        res_unused = supabase.table("accounts").select("id").eq("is_used", False).execute()
        
        total = len(res_all.data) if res_all.data else 0
        used = len(res_used.data) if res_used.data else 0
        unused = len(res_unused.data) if res_unused.data else 0

        text = (
            f"📊 **THỐNG KÊ KHO TÀI KHOẢN**\n\n"
            f"🔹 Tổng số acc: `{total}`\n"
            f"🟢 Chưa dùng: `{unused}`\n"
            f"🔴 Đã dùng: `{used}`"
        )
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi truy xuất thống kê: {str(e)}")

async def search_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tìm kiếm tài khoản bằng vài chữ cái đầu của email"""
    if not context.args:
        await update.message.reply_text("⚠️ Vui lòng nhập từ khóa tìm kiếm.\n👉 Cú pháp: `/search <từ_khóa>`")
        return

    keyword = context.args[0]
    try:
        response = supabase.table("accounts").select("*").ilike("email", f"{keyword}%").limit(1).execute()
        accounts = response.data

        if not accounts:
            await update.message.reply_text(f"❌ Không tìm thấy email nào bắt đầu bằng `{keyword}`")
            return

        acc = accounts[0]
        status = "🔴 Đã sử dụng" if acc['is_used'] else "🟢 Chưa sử dụng"
        
        keyboard = [[InlineKeyboardButton("📋 Lấy định dạng Copy gốc", callback_data=f"raw_{acc['id']}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = (
            f"🔍 **KẾT QUẢ TÌM KIẾM**\n\n"
            f"📧 `{acc['email']}`\n"
            f"🔑 `{acc['password']}`\n"
            f"📌 Trạng thái: {status}"
        )
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi tìm kiếm: {str(e)}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    try:
        response = supabase.table("accounts").select("*").eq("is_used", False).limit(1).execute()
        accounts = response.data
        if not accounts:
            return await update.message.reply_text("⚠️ Hết tài khoản khả dụng!")
            
        acc = accounts[0]
        hf_pass = generate_hf_password()
        
        keyboard = [
            [InlineKeyboardButton("🚀 Get code Higgsfield", callback_data=f"getcode_{acc['id']}")],
            [InlineKeyboardButton("📋 Copy Email & Pass", callback_data=f"copyep_{acc['id']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
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
    data = query.data

    # --- Nút Copy Email & Pass (chạm để copy) ---

    if data.startswith("copyep_"):
        await query.answer("Đang tạo đoạn copy...")
        acc_id = data.split("_")[1]
        
        response = supabase.table("accounts").select("email, password").eq("id", acc_id).execute()
        if not response.data:
            return await query.message.reply_text("❌ Không tìm thấy tài khoản.")
            
        acc = response.data[0]
        
        # Dùng 3 dấu ` (triple backticks) để bọc toàn bộ thành 1 khối copy duy nhất
        copy_text = f"```text\n📧 {acc['email']}\n🔑 {acc['password']}\n```"
        
        await query.message.reply_text(copy_text, parse_mode='MarkdownV2')
        return
    # --- Nút Lấy định dạng copy nguyên bản (từ lệnh /search) ---
    if data.startswith("raw_"):
        await query.answer("Đang lấy dữ liệu...")
        acc_id = data.split("_")[1]
        response = supabase.table("accounts").select("*").eq("id", acc_id).execute()
        
        if not response.data:
            return await query.message.reply_text("❌ Không tìm thấy tài khoản.")
            
        acc = response.data[0]
        raw_format = f"{acc['email']}|{acc['password']}|{acc['refresh_token']}|{acc['client_id']}"
        await query.message.reply_text(f"`{raw_format}`", parse_mode='Markdown')
        return

    # --- Nút Lấy code Higgsfield ---
    if data.startswith("getcode_"):
        await query.answer("Đang lấy mã...")
        acc_id = data.split("_")[1]
        
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
                keyboard = [[InlineKeyboardButton("📋 Copy Email & Pass", callback_data=f"copyep_{acc_id}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(new_text, reply_markup=reply_markup, parse_mode='Markdown')
                
            else:
                current_time = datetime.now().strftime("%H:%M:%S")
                keyboard = [
                    [InlineKeyboardButton("🔄 Thử lại", callback_data=f"getcode_{acc_id}")],
                    [InlineKeyboardButton("📋 Copy Email & Pass", callback_data=f"copyep_{acc_id}")]
                ]
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
            keyboard = [
                [InlineKeyboardButton("🔄 Thử lại", callback_data=f"getcode_{acc_id}")],
                [InlineKeyboardButton("📋 Copy Email & Pass", callback_data=f"copyep_{acc_id}")]
            ]
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
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("get", get_account))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("search", search_account))
    
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("🤖 Bot đang hoạt động...")
    app.run_polling()

if __name__ == "__main__":
    main()