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

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CẤU HÌNH ADMIN VÀ VOLUME ---
ADMIN_ID = 7965479456  
# Đã đổi sang đường dẫn Volume của Railway để lưu vĩnh viễn
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
        # Đảm bảo thư mục tồn tại trước khi lưu
        os.makedirs(os.path.dirname(APPROVED_USERS_FILE), exist_ok=True)
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

# --- HÀM TẠO PASSWORD & TÌM CODE (HỖ TRỢ ĐỘ DÀI CODE KHÁC NHAU) ---
WORDS = ["Tiger", "Ocean", "River", "Falcon", "Dragon", "Coffee", "Crystal", "Shadow", "Thunder", "Rocket", "Silver", "Golden", "Cosmic", "Quantum", "Cyber", "Ninja", "Phoenix", "Galaxy", "Neon", "Mango"]

def generate_hf_password():
    word1, word2 = random.sample(WORDS, 2)
    number = str(random.randint(10, 999))
    special_char = random.choice("!@#$%^&*")
    return f"{word1}{word2}{number}{special_char}"

def find_otp_code(data, keyword, code_length):
    """Tìm mã theo độ dài quy định của từng web"""
    if isinstance(data, dict):
        for value in data.values():
            result = find_otp_code(value, keyword, code_length)
            if result: return result
    elif isinstance(data, list):
        for item in data:
            result = find_otp_code(item, keyword, code_length)
            if result: return result
    elif isinstance(data, str):
        text_lower = data.lower()
        if keyword in text_lower:
            clean_text = re.sub(r'<[^>]+>', ' ', data)
            # Biến số lượng số (ví dụ: \b\d{8}\b cho Krea, \b\d{6}\b cho Higgsfield)
            match = re.search(rf'\b\d{{{code_length}}}\b', clean_text)
            if match: return match.group(0)
    return None

# --- HANDLERS DÀNH CHO USER ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_allowed(user_id):
        text = (
            "👋 **Hệ thống Quản lý OTP Đa Nền Tảng Bot**\n\n"
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
            await status_msg.edit_text(f"✅ Đã import {len(records_to_insert)} acc kèm Password.")
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
            [InlineKeyboardButton("🚀 Code Higgsfield", callback_data=f"gethf_{acc['id']}")],
            [InlineKeyboardButton("🎨 Code Krea", callback_data=f"getkrea_{acc['id']}"),
             InlineKeyboardButton("🧊 Code Meshy", callback_data=f"getmeshy_{acc['id']}")],
            [InlineKeyboardButton("📋 Copy Email & Pass", callback_data=f"copyep_{acc['id']}")]
        ]
        
        text = f"✅ **TÀI KHOẢN MỚI**\n\n📧 `{acc['email']}`\n🔑 `{acc['password']}`\n🔐 `{hf_pass}`"
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
            [InlineKeyboardButton("🚀 Higgsfield", callback_data=f"gethf_{acc['id']}"),
             InlineKeyboardButton("🎨 Krea", callback_data=f"getkrea_{acc['id']}"),
             InlineKeyboardButton("🧊 Meshy", callback_data=f"getmeshy_{acc['id']}")],
            [InlineKeyboardButton("📋 Copy Email & Pass", callback_data=f"copyep_{acc['id']}")],
            [InlineKeyboardButton("📋 Lấy định dạng Copy gốc", callback_data=f"raw_{acc['id']}")]
        ]
        
        if acc['is_used']:
            keyboard.append([InlineKeyboardButton("🔄 Trả về trạng thái CHƯA DÙNG", callback_data=f"unuse_{acc['id']}")])
        
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

async def clean_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id): return
    if not context.args or context.args[0] not in ['used', 'unused']:
        text = "⚠️ **Vui lòng chọn loại tài khoản cần xóa:**\n👉 `/clean unused` (Xóa sạch acc CHƯA DÙNG)\n👉 `/clean used` (Xóa sạch acc ĐÃ DÙNG)"
        return await update.message.reply_text(text, parse_mode='Markdown')

    clean_type = context.args[0]
    is_used_val = True if clean_type == 'used' else False
    status_msg = await update.message.reply_text("⏳ Đang tiến hành dọn dẹp Database...")

    try:
        res = supabase.table("accounts").select("id", count="exact").eq("is_used", is_used_val).execute()
        count = res.count if res.count else 0

        if count == 0:
            return await status_msg.edit_text(f"📂 Không có tài khoản `{clean_type}` nào để xóa.")

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

# --- XỬ LÝ NÚT BẤM ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id

    if data.startswith(("gethf_", "getkrea_", "getmeshy_")):
        await query.answer("Đang check Email...")
        prefix, acc_id = data.split("_")
        
        # Cấu hình Web Name, Từ khóa tìm kiếm, Độ dài Code
        site_map = {
            "gethf": ("Higgsfield", "higgsfield", 6),
            "getkrea": ("Krea.AI", "krea", 8),
            "getmeshy": ("Meshy.AI", "meshy", 6)
        }
        site_name, keyword, code_length = site_map[prefix]
        
        response = supabase.table("accounts").select("*").eq("id", acc_id).execute()
        if not response.data: return await query.edit_message_text("❌ Không tìm thấy tài khoản.")
        acc = response.data[0]
        
        hf_pass = acc.get('hf_password') or generate_hf_password()

        try:
            code = None
            api_error = False
            api_source = ""
            
            # Bắt đầu bấm giờ
            start_time = datetime.now()

            # --- 1. GỌI API CHÍNH (getcode.khommo.vn) ---
            try:
                primary_url = "https://getcode.khommo.vn/api/v1/read-mail"
                primary_payload = {
                    "email": acc['email'],
                    "refreshToken": acc['refresh_token'],
                    "clientId": acc['client_id'],
                    "mode": "imap",
                    "server": "server2"
                }
                res_primary = requests.post(primary_url, json=primary_payload, timeout=20)
                
                if res_primary.status_code == 200:
                    data_primary = res_primary.json()
                    if data_primary.get("success"):
                        code = find_otp_code(data_primary.get("messages", []), keyword, code_length)
                        if code:
                            api_source = "Khommo (imap)"
                    else:
                        # Fallback mode 'graph' nếu 'imap' lỗi kết nối
                        primary_payload["mode"] = "graph"
                        res_graph = requests.post(primary_url, json=primary_payload, timeout=20)
                        if res_graph.status_code == 200 and res_graph.json().get("success"):
                            code = find_otp_code(res_graph.json().get("messages", []), keyword, code_length)
                            if code:
                                api_source = "Khommo (graph)"
            except Exception as e:
                print(f"Lỗi API chính (khommo.vn): {e}")

            # --- 2. GỌI API PHỤ (dongvanfb) NẾU API CHÍNH KHÔNG TÌM THẤY CODE ---
            if not code:
                try:
                    sec_url = "https://tools.dongvanfb.net/api/get_messages_oauth2"
                    sec_payload = {
                        "email": acc['email'], 
                        "refresh_token": acc['refresh_token'], 
                        "client_id": acc['client_id']
                    }
                    res_sec = requests.post(sec_url, json=sec_payload, timeout=20)
                    if res_sec.status_code == 200:
                        code = find_otp_code(res_sec.json(), keyword, code_length)
                        if code:
                            api_source = "Dongvanfb"
                    else:
                        api_error = True
                except Exception as e:
                    print(f"Lỗi API phụ (dongvanfb): {e}")
                    api_error = True

            # Kết thúc bấm giờ và tính số giây đã trôi qua
            elapsed_time = (datetime.now() - start_time).total_seconds()

            # --- CẬP NHẬT GIAO DIỆN SAU KHI CÓ KẾT QUẢ ---
            vn_tz = timezone(timedelta(hours=7))
            current_time = datetime.now(vn_tz).strftime("%H:%M:%S")
            
            keyboard = [
                [InlineKeyboardButton(f"🔄 Lấy mã {site_name} lần nữa", callback_data=f"{prefix}_{acc_id}")],
                [InlineKeyboardButton("🚀 Higgsfield", callback_data=f"gethf_{acc_id}"),
                 InlineKeyboardButton("🎨 Krea", callback_data=f"getkrea_{acc_id}"),
                 InlineKeyboardButton("🧊 Meshy", callback_data=f"getmeshy_{acc_id}")],
                [InlineKeyboardButton("📋 Copy Email & Pass", callback_data=f"copyep_{acc_id}")]
            ]
            
            if code:
                supabase.table("accounts").update({"is_used": True}).eq("id", acc_id).execute()
                new_text = (f"✅ **{site_name}**\n\n"
                            f"📧 `{acc['email']}`\n"
                            f"🔑 `{acc['password']}`\n"
                            f"🔐 `{hf_pass}`\n"
                            f"✅ **Code:** `{code}`\n\n"
                            f"⚡ *Được cấp bởi {api_source} trong {elapsed_time:.1f}s*\n"
                            f"⏱️ *Cập nhật lúc: {current_time}*")
                await query.edit_message_text(new_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            elif api_error:
                # Nếu cả 2 API đều dính lỗi timeout hoặc không truy cập được
                keyboard = [[InlineKeyboardButton("🔄 Thử lại", callback_data=f"{prefix}_{acc_id}")],
                            [InlineKeyboardButton("📋 Copy Email & Pass", callback_data=f"copyep_{acc_id}")]]
                await query.edit_message_text(f"✅ **{site_name}**\n\n📧 `{acc['email']}`\n🔑 `{acc['password']}`\n🔐 `{hf_pass}`\n\n"
                                              f"❌ *Lỗi kết nối API. Lần check: {current_time}*", 
                                              reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            else:
                await query.edit_message_text(f"✅ **{site_name}**\n\n📧 `{acc['email']}`\n🔑 `{acc['password']}`\n🔐 `{hf_pass}`\n\n"
                                              f"⚠️ *Chưa thấy mã. Lần check: {current_time}*",
                                              reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
                
        except Exception as e:
            print(f"Lỗi toàn cục khi get code: {e}")
            vn_tz = timezone(timedelta(hours=7))
            current_time = datetime.now(vn_tz).strftime("%H:%M:%S")
            
            keyboard = [[InlineKeyboardButton("🔄 Thử lại", callback_data=f"{prefix}_{acc_id}")],
                        [InlineKeyboardButton("📋 Copy Email & Pass", callback_data=f"copyep_{acc_id}")]]
            await query.edit_message_text(f"✅ **{site_name}**\n\n📧 `{acc['email']}`\n🔑 `{acc['password']}`\n🔐 `{hf_pass}`\n\n"
                                          f"❌ *Lỗi hệ thống ngoại lệ. Lần check: {current_time}*", 
                                          reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

def main():
    trequest = HTTPXRequest(
        connection_pool_size=8,
        read_timeout=30, write_timeout=30, connect_timeout=30, pool_timeout=30
    )
    
    app = Application.builder().token(BOT_TOKEN).request(trequest).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("get", get_account))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("search", search_account))
    app.add_handler(CommandHandler("users", list_users))
    app.add_handler(CommandHandler("export", export_accounts))
    app.add_handler(CommandHandler("clean", clean_accounts))
    
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("🤖 Bot đang hoạt động với cấu hình mạng mới...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()