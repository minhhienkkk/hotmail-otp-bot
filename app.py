import os
import re
import json
import random
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
from supabase import create_client, Client

# Tải biến môi trường
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PROXY_URL = os.getenv("PROXY_URL") # Hỗ trợ Proxy nếu chạy trên Railway bị chặn IP

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CẤU HÌNH ADMIN ---
ADMIN_ID = 7965479456  
APPROVED_USERS_FILE = "approved_users.json"

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
        BotCommand("export", "📥 Xuất file tài khoản (.txt)"),
        BotCommand("clean", "🧹 Xóa acc (Đã dùng/Chưa dùng)"),
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
            clean_text = re.sub(r'<[^>]+>', ' ', data)
            match = re.search(r'\b\d{6}\b', clean_text)
            if match: return match.group(0)
    return None

# --- HANDLERS DÀNH CHO USER ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_allowed(user_id):
        text = (
            "👋 **Hệ thống Quản lý Higgsfield Bot**\n\n"
            "Các lệnh hỗ trợ:\n"
            "📎 Gửi file `.txt` để import acc.\n"
            "📥 `/get` - Lấy 1 tài khoản mới.\n"
            "🔍 `/search <email>` - Tìm nhanh acc.\n"
            "📊 `/stats` - Xem thống kê.\n"
            "📥 `/export <all/used/unused>` - Xuất file.\n"
            "🧹 `/clean <used/unused>` - Xóa dữ liệu.\n"
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

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id): return
    document = update.message.document
    if not document.file_name.endswith('.txt'): return await update.message.reply_text("❌ Vui lòng gửi file .txt")

    status_msg = await update.message.reply_text("⏳ Đang xử lý file...")
    try:
        file = await context.bot.get_file(document.file_id)
        content = (await file.download_as_bytearray()).decode('utf-8').splitlines()
        
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
        response = supabase.table("accounts").select("*").eq("is_used", False).order("id").limit(1).execute()
        if not response.data: return await update.message.reply_text("⚠️ Hết tài khoản khả dụng!")
            
        acc = response.data[0]
        
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

async def search_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id): return
    if not context.args: return await update.message.reply_text("⚠️ Vui lòng nhập từ khóa.\n👉 Cú pháp: `/search <từ_khóa>`")

    keyword = context.args[0]
    try:
        response = supabase.table("accounts").select("*").ilike("email", f"{keyword}%").limit(1).execute()
        if not response.data: return await update.message.reply_text(f"❌ Không tìm thấy email nào bắt đầu bằng `{keyword}`")

        acc = response.data[0]
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

# --- LỆNH XUẤT FILE (EXPORT) ---
async def export_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id): return
    if not context.args or context.args[0] not in ['used', 'unused', 'all']:
        text = "⚠️ **Vui lòng chọn loại tài khoản muốn xuất:**\n👉 `/export unused` (Chưa dùng)\n👉 `/export used` (Đã dùng)\n👉 `/export all` (Tất cả)"
        return await update.message.reply_text(text, parse_mode='Markdown')

    export_type = context.args[0]
    status_msg = await update.message.reply_text("⏳ Đang trích xuất dữ liệu, vui lòng chờ...")

    try:
        if export_type == 'unused':
            response = supabase.table("accounts").select("*").eq("is_used", False).execute()
        elif export_type == 'used':
            response = supabase.table("accounts").select("*").eq("is_used", True).execute()
        else:
            response = supabase.table("accounts").select("*").execute()

        accounts = response.data
        if not accounts: return await status_msg.edit_text(f"📂 Không có tài khoản nào trong danh mục `{export_type}`.", parse_mode='Markdown')

        lines = [f"{acc['email']}|{acc['password']}|{acc['refresh_token']}|{acc['client_id']}" for acc in accounts]
        file_content = "\n".join(lines)
        
        vn_tz = timezone(timedelta(hours=7))
        time_str = datetime.now(vn_tz).strftime('%d%m%Y_%H%M%S')
        file_name = f"Export_{export_type}_{time_str}.txt"

        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(file_content)

        await update.message.reply_document(
            document=open(file_name, 'rb'),
            filename=file_name,
            caption=f"✅ Đã xuất thành công **{len(accounts)}** tài khoản ({export_type}).",
            parse_mode='Markdown'
        )
        os.remove(file_name)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ Lỗi xuất file: {str(e)}")

# --- LỆNH DỌN DẸP (CLEAN) ---
async def clean_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id): return
    if not context.args or context.args[0] not in ['used', 'unused']:
        text = "⚠️ **Vui lòng chọn loại tài khoản cần xóa:**\n👉 `/clean unused` (Xóa sạch acc CHƯA DÙNG)\n👉 `/clean used` (Xóa sạch acc ĐÃ DÙNG)"
        return await update.message.reply_text(text, parse_mode='Markdown')

    clean_type = context.args[0]
    is_used_val = True if clean_type == 'used' else False
    status_msg = await update.message.reply_text("⏳ Đang tiến hành dọn dẹp Database...")

    try:
        # Lấy số lượng trước khi xóa để báo cáo
        res = supabase.table("accounts").select("id", count="exact").eq("is_used", is_used_val).execute()
        count = res.count if res.count else 0

        if count == 0:
            return await status_msg.edit_text(f"📂 Không có tài khoản `{clean_type}` nào để xóa.")

        # Gọi API xóa hàng loạt
        supabase.table("accounts").delete().eq("is_used", is_used_val).execute()
        
        status_vn = "CHƯA DÙNG" if not is_used_val else "ĐÃ DÙNG"
        await status_msg.edit_text(f"✅ Đã xóa vĩnh viễn **{count}** tài khoản {status_vn} khỏi Database.")
    except Exception as e:
        await status_msg.edit_text(f"❌ Lỗi khi xóa: {str(e)}")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return await update.message.reply_text("⛔ Chỉ Admin mới có quyền sử dụng lệnh này.")
    users = load_approved_users()
    if not users: return await update.message.reply_text("📂 Hiện tại chưa có ai trong danh sách phê duyệt.")
    text = "👥 **DANH SÁCH THÀNH VIÊN ĐƯỢC DUYỆT:**\n\n"
    for idx, u_id in enumerate(users, 1): text += f"{idx}. ID: `{u_id}`\n"
    await update.message.reply_text(text, parse_mode='Markdown')

# --- XỬ LÝ NÚT BẤM (CÓ UTC+7 VÀ BẮT LỖI MẠNG) ---
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
            
            if api_res.status_code != 200:
                raise requests.exceptions.RequestException(f"Lỗi {api_res.status_code}")
                
            code = find_higgsfield_code(api_res.json())
            
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
            vn_tz = timezone(timedelta(hours=7))
            current_time = datetime.now(vn_tz).strftime("%H:%M:%S")
            
            keyboard = [[InlineKeyboardButton("🔄 Thử lại", callback_data=f"getcode_{acc_id}")],
                        [InlineKeyboardButton("📋 Copy Email & Pass", callback_data=f"copyep_{acc_id}")]]
            await query.edit_message_text(f"✅ **Higgsfield**\n\n📧 `{acc['email']}`\n🔑 `{acc['password']}`\n🔐 `{hf_pass}`\n\n"
                                          f"❌ *Lỗi kết nối API. Lần check: {current_time}*", 
                                          reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

def main():
    # Cấu hình mạng lỏng hơn và gắn Proxy (Nếu có) để chống Timeout
    trequest = HTTPXRequest(
        connection_pool_size=8,
        read_timeout=30, write_timeout=30, connect_timeout=30, pool_timeout=30,
        proxy_url=PROXY_URL if PROXY_URL else None
    )
    
    app = Application.builder().token(BOT_TOKEN).request(trequest).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("get", get_account))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("search", search_account))
    app.add_handler(CommandHandler("users", list_users))
    
    # KÍCH HOẠT LỆNH MỚI
    app.add_handler(CommandHandler("export", export_accounts))
    app.add_handler(CommandHandler("clean", clean_accounts))
    
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("🤖 Bot đang hoạt động với cấu hình mạng mới...")
    # Thêm drop_pending_updates để xóa kẹt lệnh lúc sập server
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()