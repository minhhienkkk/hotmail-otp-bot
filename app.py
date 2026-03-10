import os
import re
import json
import random
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from supabase import create_client, Client

# Tải biến môi trường
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CẤU HÌNH ADMIN ---
ADMIN_ID = 7965479456  
APPROVED_USERS_FILE = "approved_users.json" # Nếu dùng Railway Volume: "/app/data/approved_users.json"

def load_approved_users():
    if os.path.exists(APPROVED_USERS_FILE):
        with open(APPROVED_USERS_FILE, "r") as f:
            return json.load(f)
    return []

def save_approved_user(user_id):
    users = load_approved_users()
    if user_id not in users:
        users.append(user_id)
        with open(APPROVED_USERS_FILE, "w") as f:
            json.dump(users, f)

def is_allowed(user_id):
    return user_id == ADMIN_ID or user_id in load_approved_users()

# --- HÀM TẠO MENU CHO BOT ---
async def post_init(application: Application):
    commands = [
        BotCommand("start", "Khởi động & Xem hướng dẫn"),
        BotCommand("get", "Lấy 1 tài khoản mới"),
        BotCommand("search", "Tìm tài khoản theo email"),
        BotCommand("stats", "Xem thống kê kho acc"),
        BotCommand("users", "🔑 Admin: Xem list người được duyệt")
    ]
    await application.bot.set_my_commands(commands)
    print("✅ Đã cập nhật Menu lệnh cho Bot thành công!")

# --- HÀM TẠO PASSWORD & TÌM CODE ---
WORDS = ["Tiger", "Ocean", "River", "Falcon", "Dragon", "Coffee", "Crystal", "Shadow", "Thunder", "Rocket", "Silver", "Golden", "Cosmic", "Quantum", "Cyber", "Ninja", "Phoenix", "Galaxy", "Neon", "Mango"]

def generate_hf_password():
    word1, word2 = random.sample(WORDS, 2)
    number = str(random.randint(10, 999))
    special_char = random.choice("!@#$%^&*")
    return f"{word1}{word2}{number}{special_char}"

def find_higgsfield_code(data):
    if isinstance(data, dict):
        for value in data.values():
            result = find_higgsfield_code(value)
            if result: return result
    elif isinstance(data, list):
        for item in data:
            result = find_higgsfield_code(item)
            if result: return result
    elif isinstance(data, str):
        text_lower = data.lower()
        if 'higgsfield' in text_lower:
            clean_text = re.sub(r'<[^>]+>', ' ', data) # Xóa mã HTML rác
            match = re.search(r'\b\d{6}\b', clean_text)
            if match: return match.group(0)
    return None

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_allowed(user_id):
        text = (
            "👋 **Hệ thống Quản lý Higgsfield Bot**\n\n"
            "Các lệnh hỗ trợ:\n"
            "📎 Gửi file `.txt` để import acc.\n"
            "📥 `/get` - Lấy 1 tài khoản mới.\n"
            "📊 `/stats` - Xem thống kê kho acc.\n"
            "🔍 `/search <email>` - Tìm nhanh acc.\n"
            "👥 `/users` - (Admin) Xem danh sách duyệt."
        )
        return await update.message.reply_text(text, parse_mode='Markdown')
    
    await update.message.reply_text("⏳ Bạn chưa được cấp quyền sử dụng bot. Đã gửi yêu cầu đến Admin, vui lòng chờ duyệt!")
    
    keyboard = [
        [InlineKeyboardButton("✅ Duyệt", callback_data=f"approve_{user_id}"),
         InlineKeyboardButton("❌ Từ chối", callback_data=f"reject_{user_id}")]
    ]
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔔 **CÓ YÊU CẦU TRUY CẬP MỚI**\n\n👤 Tên: {update.effective_user.full_name}\n🆔 ID: `{user_id}`\n🔗 Username: @{update.effective_user.username}\n\nBạn có muốn cấp quyền không?",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Lỗi: {e}")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Chỉ Admin mới có quyền sử dụng lệnh này.")
    users = load_approved_users()
    if not users:
        return await update.message.reply_text("📂 Hiện tại chưa có ai trong danh sách phê duyệt.")
    text = "👥 **DANH SÁCH THÀNH VIÊN ĐƯỢC DUYỆT:**\n\n"
    for idx, u_id in enumerate(users, 1):
        text += f"{idx}. ID: `{u_id}`\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id): return
    try:
        res_all = supabase.table("accounts").select("id", count="exact").execute()
        res_used = supabase.table("accounts").select("id", count="exact").eq("is_used", True).execute()
        res_unused = supabase.table("accounts").select("id", count="exact").eq("is_used", False).execute()
        
        text = f"📊 **THỐNG KÊ KHO TÀI KHOẢN**\n\n🔹 Tổng số acc: `{res_all.count}`\n🟢 Chưa dùng: `{res_unused.count}`\n🔴 Đã dùng: `{res_used.count}`"
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {str(e)}")

async def search_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id): return
    if not context.args: return await update.message.reply_text("⚠️ Vui lòng nhập từ khóa.\n👉 Cú pháp: `/search <từ_khóa>`")

    keyword = context.args[0]
    try:
        response = supabase.table("accounts").select("*").ilike("email", f"{keyword}%").limit(1).execute()
        if not response.data: return await update.message.reply_text(f"❌ Không tìm thấy email nào bắt đầu bằng `{keyword}`")

        acc = response.data[0]
        
        # Kiểm tra và bù đắp pass nếu acc cũ chưa có
        hf_pass = acc.get('hf_password')
        if not hf_pass:
            hf_pass = generate_hf_password()
            supabase.table("accounts").update({"hf_password": hf_pass}).eq("id", acc['id']).execute()
            
        status = "🔴 Đã sử dụng" if acc['is_used'] else "🟢 Chưa sử dụng"
        keyboard = [
            [InlineKeyboardButton("🚀 Get code Higgsfield", callback_data=f"getcode_{acc['id']}")],
            [InlineKeyboardButton("📋 Copy Email & Pass", callback_data=f"copyep_{acc['id']}")],
            [InlineKeyboardButton("📋 Lấy định dạng Copy gốc", callback_data=f"raw_{acc['id']}")]
        ]
        
        text = f"🔍 **KẾT QUẢ TÌM KIẾM**\n\n📧 `{acc['email']}`\n🔑 `{acc['password']}`\n🔐 `{hf_pass}`\n\n📌 Trạng thái: {status}"
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {str(e)}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id): return
    document = update.message.document
    if not document.file_name.endswith('.txt'): return await update.message.reply_text("❌ Vui lòng gửi file .txt")

    status_msg = await update.message.reply_text("⏳ Đang xử lý file...")
    try:
        file = await context.bot.get_file(document.file_id)
        content = (await file.download_as_bytearray()).decode('utf-8').splitlines()
        
        # Tự động tạo pass Higgsfield ngay lúc import acc
        records_to_insert = [
            {"email": p[0], "password": p[1], "refresh_token": p[2], "client_id": p[3], "is_used": False, "hf_password": generate_hf_password()}
            for line in content if len(p := line.strip().split('|')) == 4
        ]
        
        if records_to_insert:
            supabase.table("accounts").insert(records_to_insert).execute()
            await status_msg.edit_text(f"✅ Đã import {len(records_to_insert)} acc kèm Password Higgsfield.")
        else:
            await status_msg.edit_text("❌ Không tìm thấy dòng đúng định dạng.")
    except Exception as e:
        await status_msg.edit_text(f"❌ Lỗi: {str(e)}")

async def get_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id): return
    try:
        response = supabase.table("accounts").select("*").eq("is_used", False).limit(1).execute()
        if not response.data: return await update.message.reply_text("⚠️ Hết tài khoản khả dụng!")
            
        acc = response.data[0]
        
        # Kiểm tra và bù đắp pass nếu acc cũ chưa có
        hf_pass = acc.get('hf_password')
        if not hf_pass:
            hf_pass = generate_hf_password()
            supabase.table("accounts").update({"hf_password": hf_pass}).eq("id", acc['id']).execute()
        
        keyboard = [
            [InlineKeyboardButton("🚀 Get code Higgsfield", callback_data=f"getcode_{acc['id']}")],
            [InlineKeyboardButton("📋 Copy Email & Pass", callback_data=f"copyep_{acc['id']}")]
        ]
        
        text = f"✅ **Higgsfield**\n\n📧 `{acc['email']}`\n🔑 `{acc['password']}`\n🔐 `{hf_pass}`"
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {str(e)}")

# --- XỬ LÝ NÚT BẤM ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id

    if data.startswith("approve_") or data.startswith("reject_"):
        if user_id != ADMIN_ID: return await query.answer("⛔ Bạn không phải Admin!", show_alert=True)
        target_id = int(data.split("_")[1])
        if data.startswith("approve_"):
            save_approved_user(target_id)
            await query.edit_message_text(f"✅ Đã cấp quyền sử dụng cho ID: `{target_id}`", parse_mode='Markdown')
            try: await context.bot.send_message(chat_id=target_id, text="🎉 **Admin đã phê duyệt!**\nBạn có thể bắt đầu sử dụng bot bằng cách gõ /start", parse_mode='Markdown')
            except: pass
        elif data.startswith("reject_"):
            await query.edit_message_text(f"❌ Đã từ chối cấp quyền cho ID: `{target_id}`", parse_mode='Markdown')
        return

    if not is_allowed(user_id): return await query.answer("⛔ Bạn chưa được cấp quyền dùng bot!", show_alert=True)

    if data.startswith("copyep_"):
        await query.answer("Đang tạo đoạn copy...")
        acc_id = data.split("_")[1]
        response = supabase.table("accounts").select("email, password").eq("id", acc_id).execute()
        if not response.data: return await query.message.reply_text("❌ Không tìm thấy tài khoản.")
        acc = response.data[0]
        await query.message.reply_text(f"```text\n📧 {acc['email']}\n🔑 {acc['password']}\n```", parse_mode='MarkdownV2')
        return

    if data.startswith("raw_"):
        await query.answer("Đang lấy dữ liệu...")
        acc_id = data.split("_")[1]
        response = supabase.table("accounts").select("*").eq("id", acc_id).execute()
        if not response.data: return await query.message.reply_text("❌ Không tìm thấy tài khoản.")
        acc = response.data[0]
        await query.message.reply_text(f"`{acc['email']}|{acc['password']}|{acc['refresh_token']}|{acc['client_id']}`", parse_mode='Markdown')
        return

    if data.startswith("getcode_"):
        await query.answer("Đang lấy mã...")
        acc_id = data.split("_")[1]
        
        response = supabase.table("accounts").select("*").eq("id", acc_id).execute()
        if not response.data: return await query.edit_message_text("❌ Không tìm thấy tài khoản.")
        acc = response.data[0]
        
        hf_pass = acc.get('hf_password')
        if not hf_pass:
            hf_pass = generate_hf_password()
            supabase.table("accounts").update({"hf_password": hf_pass}).eq("id", acc_id).execute()

        api_url = "https://tools.dongvanfb.net/api/get_messages_oauth2"
        payload = {"email": acc['email'], "refresh_token": acc['refresh_token'], "client_id": acc['client_id']}
        
        try:
            api_res = requests.post(api_url, json=payload, timeout=20)
            code = find_higgsfield_code(api_res.json())
            
            # Khởi tạo múi giờ UTC+7
            vn_tz = timezone(timedelta(hours=7))
            current_time = datetime.now(vn_tz).strftime("%H:%M:%S")
            
            keyboard = [
                [InlineKeyboardButton("🔄 Lấy mã lần nữa", callback_data=f"getcode_{acc_id}")],
                [InlineKeyboardButton("📋 Copy Email & Pass", callback_data=f"copyep_{acc_id}")]
            ]
            
            if code:
                supabase.table("accounts").update({"is_used": True}).eq("id", acc_id).execute()
                new_text = (f"✅ **Higgsfield**\n\n📧 `{acc['email']}`\n🔑 `{acc['password']}`\n🔐 `{hf_pass}`\n"
                            f"✅ **Code:** `{code}`\n\n⏱️ *Cập nhật lúc: {current_time}*")
                await query.edit_message_text(new_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            else:
                await query.edit_message_text(f"✅ **Higgsfield**\n\n📧 `{acc['email']}`\n🔑 `{acc['password']}`\n🔐 `{hf_pass}`\n\n"
                                              f"⚠️ *Chưa thấy mã. Lần check: {current_time}*",
                                              reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
                
        except requests.exceptions.RequestException as e:
            # Khởi tạo múi giờ UTC+7 cho khối lỗi
            vn_tz = timezone(timedelta(hours=7))
            current_time = datetime.now(vn_tz).strftime("%H:%M:%S")
            
            keyboard = [[InlineKeyboardButton("🔄 Thử lại", callback_data=f"getcode_{acc_id}")],
                        [InlineKeyboardButton("📋 Copy Email & Pass", callback_data=f"copyep_{acc_id}")]]
            await query.edit_message_text(f"✅ **Higgsfield**\n\n📧 `{acc['email']}`\n🔑 `{acc['password']}`\n🔐 `{hf_pass}`\n\n"
                                          f"❌ *Lỗi API. Lần check: {current_time}*", 
                                          reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("get", get_account))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("search", search_account))
    app.add_handler(CommandHandler("users", list_users))
    
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("🤖 Bot đang hoạt động...")
    app.run_polling()

if __name__ == "__main__":
    main()