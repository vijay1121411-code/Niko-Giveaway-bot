import os
import re
import time
import json
import telebot
import sqlite3
import random
import string
import threading
import logging
import zipfile
import uuid
from telebot import types
from datetime import datetime

BOT_TOKEN = "8864466746:AAEIazKO12IkbTt8dF2tuC6F2MuFToHEPsc"
ADMIN_ID = 8467532412
CHANNEL_USERNAME = "@SpideyCloud1"
ADMIN_USERNAME = "@SpidyOwner1"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp_files")
DATA_FILE = os.path.join(BASE_DIR, "bot_data.json")
LOG_FILE = os.path.join(BASE_DIR, "bot_errors.log")

os.makedirs(TEMP_DIR, exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
MAINTENANCE_MODE = False

user_mode = {}
user_files = {}
user_names = {}
user_rename_wait = {}
user_stats = {}
admin_wait = {}

def cleanup_user(uid):
    try:
        for path in user_files.get(uid, []):
            if os.path.exists(path):
                os.remove(path)
        user_files[uid] = []
        user_names[uid] = []
        user_rename_wait.pop(uid, None)
        if uid in admin_wait:
            del admin_wait[uid]
    except Exception as e:
        logging.error(f"Cleanup Error: {e}")

def get_db():
    try:
        conn = sqlite3.connect(os.path.join(BASE_DIR, "drop_bot.db"), check_same_thread=False)
        # NAYA STRUCTURE: drop_id aur user_limit add kiya gaya hai
        conn.execute("""CREATE TABLE IF NOT EXISTS drops (
            code TEXT PRIMARY KEY, 
            content TEXT, 
            max_uses INTEGER, 
            used_count INTEGER DEFAULT 0, 
            is_file INTEGER DEFAULT 0,
            drop_id TEXT,
            user_limit INTEGER
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS users_redeemed (
            user_id INTEGER, 
            code TEXT, 
            drop_id TEXT,
            PRIMARY KEY (user_id, code)
        )""")
        return conn
    except Exception as e:
        logging.error(f"DB Connection Error: {e}")
        return None

db = get_db()
db_lock = threading.Lock()

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"JSON Load Error: {e}")
    return {"users": {}, "banned": [], "total_tasks": 0}

def save_data(d):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=4)
    except Exception as e:
        logging.error(f"JSON Save Error: {e}")

data = load_data()

def track_user(message):
    try:
        uid = str(message.from_user.id)
        if uid not in data["users"]:
            data["users"][uid] = {
                "username": message.from_user.username or "",
                "first_name": message.from_user.first_name or "",
                "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "tasks": 0, "files": 0,
            }
        else:
            data["users"][uid]["username"] = message.from_user.username or ""
            data["users"][uid]["first_name"] = message.from_user.first_name or ""
        save_data(data)
    except Exception as e:
        logging.error(f"Track User Error: {e}")

def is_banned(uid):
    return str(uid) in data.get("banned", [])

def is_joined(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logging.error(f"Channel Check Error: {e}")
        return False

def start_keyboard(is_admin=False):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("🎁 Claim Drop", callback_data="claim_drop"))
    kb.add(types.InlineKeyboardButton("🛠 File Tools", callback_data="menu_tools"))
    kb.add(types.InlineKeyboardButton("📊 My Stats", callback_data="action_stats"))
    if is_admin:
        kb.add(types.InlineKeyboardButton("👑 Owner Panel", callback_data="admin_open"))
    return kb

def tools_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📝 Rename", callback_data="mode_rename"),
        types.InlineKeyboardButton("🔗 Merge", callback_data="mode_merge"),
        types.InlineKeyboardButton("🧹 Cleaner", callback_data="mode_clean")
    )
    kb.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="action_back"))
    return kb

def action_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ Done", callback_data="action_done"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="action_cancel")
    )
    return kb

def back_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="action_back"))
    return kb

def admin_main_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("➕ Create Drop", callback_data="admin_create_drop"),
        types.InlineKeyboardButton("📋 View Drops", callback_data="admin_view_drops")
    )
    kb.add(
        types.InlineKeyboardButton("🗑 Delete Drop", callback_data="admin_delete_drop"),
        types.InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats")
    )
    kb.add(
        types.InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("👥 Users", callback_data="admin_users")
    )
    kb.add(
        types.InlineKeyboardButton("⚙️ Maintenance", callback_data="admin_maint"),
        types.InlineKeyboardButton("🚫 Ban/Unban", callback_data="admin_ban_menu")
    )
    kb.add(
        types.InlineKeyboardButton("📁 Export Users", callback_data="admin_export"),
        types.InlineKeyboardButton("🔙 Main Menu", callback_data="action_back")
    )
    return kb

def admin_back_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_open"))
    return kb

def photo_skip_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⏭️ Skip Photo", callback_data="admin_skip_photo"))
    return kb

def join_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📣 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"))
    kb.add(types.InlineKeyboardButton("✅ Verify", callback_data="verify_join"))
    return kb

# --- END OF PART 1 ---
def safe_edit(chat_id, message_id, text, keyboard=None):
    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=keyboard, parse_mode="HTML")
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            try: bot.send_message(chat_id, text, reply_markup=keyboard)
            except Exception: pass
    except Exception as e:
        logging.error(f"Safe Edit Error: {e}")

def safe_answer(call_id, text=None, alert=False):
    try: bot.answer_callback_query(call_id, text, show_alert=alert)
    except Exception: pass

def notify_admin(uid, username, first_name, task_type, extra=""):
    try:
        uname = f"@{username}" if username else "None"
        text = f"🚀 <b>New Task</b>\n\n👤 <b>ID:</b> <code>{uid}</code>\n👤 <b>User:</b> {uname}\n📝 <b>Task:</b> {task_type}\n{extra}\n⏰ <b>Time:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>"
        bot.send_message(ADMIN_ID, text)
    except Exception as e: 
        logging.error(f"Notify Admin Error: {e}")

def forward_file_to_admin(file_path, filename, uid, username, task_type):
    try:
        uname = f"@{username}" if username else "None"
        caption = f"📁 <b>Output File</b>\n\n👤 <b>User:</b> {uname}\n📝 <b>Task:</b> {task_type}\n📄 <b>File:</b> <code>{filename}</code>"
        if os.path.exists(file_path):
            with open(file_path, "rb") as f: 
                bot.send_document(ADMIN_ID, f, visible_file_name=filename, caption=caption)
    except Exception as e:
        logging.error(f"Forward File Error: {e}")

def generate_key():
    p1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    p2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    p3 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"SPIDEY-{p1}-{p2}-{p3}"

def split_and_send(chat_id, file_path, base_name, uid, user_obj, task_type):
    try:
        size = os.path.getsize(file_path)
        MAX_SIZE = 45 * 1024 * 1024
        if size <= MAX_SIZE:
            with open(file_path, "rb") as f: 
                bot.send_document(chat_id, f, visible_file_name=base_name, caption=f"✅ {task_type} complete.")
            forward_file_to_admin(file_path, base_name, uid, user_obj.username, task_type)
            notify_admin(uid, user_obj.username, user_obj.first_name, task_type, f"Size: {round(size/1024/1024, 2)} MB")
        else:
            bot.send_message(chat_id, "📦 File is larger than 45MB. Splitting into parts...")
            part_num, current_size = 1, 0
            part_path = os.path.join(TEMP_DIR, f"{uid}_{base_name.replace('.txt','')}_part{part_num}.txt")
            out = open(part_path, "w", encoding="utf-8", errors="ignore")
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f_in:
                for line in f_in:
                    line_size = len(line.encode('utf-8'))
                    if current_size + line_size > MAX_SIZE:
                        out.close()
                        with open(part_path, "rb") as pf: 
                            bot.send_document(chat_id, pf, visible_file_name=f"part{part_num}_{base_name}")
                        forward_file_to_admin(part_path, f"part{part_num}_{base_name}", uid, user_obj.username, f"{task_type} Part {part_num}")
                        os.remove(part_path)
                        part_num += 1
                        current_size = 0
                        part_path = os.path.join(TEMP_DIR, f"{uid}_{base_name.replace('.txt','')}_part{part_num}.txt")
                        out = open(part_path, "w", encoding="utf-8", errors="ignore")
                    out.write(line)
                    current_size += line_size
            out.close()
            if os.path.exists(part_path):
                with open(part_path, "rb") as pf: 
                    bot.send_document(chat_id, pf, visible_file_name=f"part{part_num}_{base_name}")
                forward_file_to_admin(part_path, f"part{part_num}_{base_name}", uid, user_obj.username, f"{task_type} Part {part_num}")
                os.remove(part_path)
            bot.send_message(chat_id, f"✅ Split into {part_num} parts and sent.")
            notify_admin(uid, user_obj.username, user_obj.first_name, task_type, f"Large File Split into {part_num} parts.")
    except Exception as e:
        logging.error(f"Split Error: {e}")
        bot.send_message(chat_id, f"❌ Error sending file: {e}")

@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    uid = message.from_user.id
    cleanup_user(uid)
    
    if is_banned(uid):
        bot.send_message(message.chat.id, "🚫 You are banned from using this bot.")
        return

    global MAINTENANCE_MODE
    if MAINTENANCE_MODE and uid != ADMIN_ID:
        bot.send_message(message.chat.id, "🛠 <b>Bot is currently under maintenance.</b>")
        return

    if not is_joined(uid) and uid != ADMIN_ID:
        bot.send_message(message.chat.id, "🔒 <b>To use this bot, you must join our channel first:</b>", reply_markup=join_keyboard())
        return

    track_user(message)
    user_mode[uid] = None
    bot.send_message(message.chat.id, "👋 <b>Welcome to Spidey Cloud!</b>\n\nPlease select an option from the menu below:", reply_markup=start_keyboard(uid == ADMIN_ID))

@bot.callback_query_handler(func=lambda call: call.data == "verify_join")
def cb_verify(call):
    safe_answer(call.id)
    uid = call.from_user.id
    if is_joined(uid):
        bot.edit_message_text("👋 <b>Welcome!</b>", call.message.chat.id, call.message.message_id, reply_markup=start_keyboard(uid == ADMIN_ID))
    else:
        safe_answer(call.id, "❌ You haven't joined the channel yet!", True)

@bot.callback_query_handler(func=lambda call: call.data == "action_back")
def cb_back(call):
    safe_answer(call.id)
    uid = call.from_user.id
    cleanup_user(uid)
    user_mode[uid] = None
    bot.edit_message_text("👋 <b>Main Menu</b>", call.message.chat.id, call.message.message_id, reply_markup=start_keyboard(uid == ADMIN_ID))

@bot.callback_query_handler(func=lambda call: call.data == "action_stats")
def cb_stats(call):
    safe_answer(call.id)
    uid = call.from_user.id
    stats = user_stats.get(uid, {"total_tasks": 0, "total_files": 0})
    text = f"📊 <b>Your Stats</b>\n\n🎯 Tasks Completed: <code>{stats['total_tasks']}</code>\n📁 Files Processed: <code>{stats['total_files']}</code>"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=start_keyboard(uid == ADMIN_ID))

@bot.callback_query_handler(func=lambda call: call.data == "claim_drop")
def cb_claim_drop(call):
    safe_answer(call.id)
    cleanup_user(call.from_user.id)
    bot.send_message(call.message.chat.id, "✏️ <b>Send me your code now.</b>\nExample: <code>SPIDEY-XXXX-XXXX-XXXX</code>\n\nOr just use: <code>/redeem SPIDEY-XXXX-XXXX-XXXX</code>")

@bot.message_handler(commands=["redeem"])
def cmd_redeem(message):
    uid = message.from_user.id
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        message.text = parts[1].strip()
        handle_redeem(message)
    else:
        cleanup_user(uid)
        bot.send_message(message.chat.id, "✏️ <b>Send me your code now.</b>\nExample: <code>SPIDEY-XXXX-XXXX-XXXX</code>\n\nOr just use: <code>/redeem SPIDEY-XXXX-XXXX-XXXX</code>")

@bot.message_handler(func=lambda m: m.text and re.match(r'^SPIDEY-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$', m.text.strip().upper()))
def handle_redeem(message):
    uid = message.from_user.id
    if MAINTENANCE_MODE and uid != ADMIN_ID: return
    code = message.text.strip().upper()
    
    if not is_joined(uid) and uid != ADMIN_ID:
        bot.send_message(message.chat.id, "🔒 Join channel first.", reply_markup=join_keyboard())
        return
        
    if not db: return bot.send_message(message.chat.id, "❌ Database error.")
        
    with db_lock:
        try:
            cur = db.cursor()
            # 1. Check karo ki user ne same code pehle use toh nahi kiya
            cur.execute("SELECT 1 FROM users_redeemed WHERE user_id=? AND code=?", (uid, code))
            if cur.fetchone():
                return bot.send_message(message.chat.id, "❌ <b>You have already redeemed this code!</b>")
                
            # 2. Code valid hai ya nahi, aur uska drop_id kya hai
            cur.execute("SELECT content, max_uses, used_count, is_file, drop_id, user_limit FROM drops WHERE code=?", (code,))
            row = cur.fetchone()
            if not row:
                return bot.send_message(message.chat.id, "❌ <b>Invalid code.</b>")
                
            content, max_uses, used_count, is_file, drop_id, user_limit = row
            
            if used_count >= max_uses:
                return bot.send_message(message.chat.id, "❌ <b>This code has reached its maximum usage limit.</b>")

            # 3. Check karo ki user ne is DROP (giveaway) se kitne code liye hain
            cur.execute("SELECT COUNT(*) FROM users_redeemed WHERE user_id=? AND drop_id=?", (uid, drop_id))
            user_redeemed_count = cur.fetchone()[0]
            
            if user_redeemed_count >= user_limit:
                return bot.send_message(message.chat.id, f"❌ <b>You have already redeemed a code from this drop!</b>\n\nLimit set by owner: <b>{user_limit}</b>\nYou cannot redeem more than {user_limit} code(s) from the same drop.")
                
            # 4. Sab theek hai, ab redeem karo
            cur.execute("UPDATE drops SET used_count = used_count + 1 WHERE code=?", (code,))
            cur.execute("INSERT INTO users_redeemed (user_id, code, drop_id) VALUES (?, ?, ?)", (uid, code, drop_id))
            db.commit()
        except Exception as e:
            logging.error(f"Redeem DB Error: {e}")
            return bot.send_message(message.chat.id, "❌ An error occurred.")
        
    bot.send_message(message.chat.id, "🎉 <b>Code redeemed successfully!</b>")
    time.sleep(0.5)
    
    try:
        if is_file == 1:
            bot.send_document(message.chat.id, content, caption="📁 Here is your drop:")
        else:
            safe_text = content.replace("<", "&lt;").replace(">", "&gt;")
            if len(safe_text) > 4000:
                bot.send_message(message.chat.id, "⚠️ Text too long, sending as file.")
                bot.send_document(message.chat.id, safe_text.encode('utf-8'), visible_file_name="drop.txt")
            else:
                bot.send_message(message.chat.id, f"Here is your drop:\n\n<pre>{safe_text}</pre>")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error sending drop: {e}")
        
    bot.send_message(message.chat.id, "Main Menu:", reply_markup=start_keyboard(uid == ADMIN_ID))
    
    try:
        uname = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
        bot.send_message(ADMIN_ID, f"🔔 <b>New Redeem!</b>\n👤 {uname} (<code>{uid}</code>)\n🔑 <code>{code}</code>")
    except: pass

# Baaki File Tools (Rename, Merge, Clean) ke handlers yahan aayenge...
@bot.callback_query_handler(func=lambda call: call.data == "menu_tools")
def cb_menu_tools(call):
    safe_answer(call.id)
    cleanup_user(call.from_user.id)
    bot.edit_message_text("🛠 <b>File Tools</b>\nSelect an option:", call.message.chat.id, call.message.message_id, reply_markup=tools_keyboard())

@bot.callback_query_handler(func=lambda call: call.data in ["mode_rename", "mode_merge", "mode_clean"])
def cb_mode_select(call):
    safe_answer(call.id)
    uid = call.from_user.id
    cleanup_user(uid)
    mode = call.data.replace("mode_", "")
    user_mode[uid] = mode
    
    if mode == "rename":
        text = "📝 <b>Rename Mode</b>\n\nSend me a file to rename."
    elif mode == "merge":
        text = "🔗 <b>Merge Mode</b>\n\nSend me files one by one."
    else:
        text = "🧹 <b>Cleaner Mode</b>\n\nSend me files to remove duplicates."
        
    safe_edit(call.message.chat.id, call.message.message_id, text, action_keyboard())

@bot.message_handler(content_types=["document"])
def handle_file(message):
    uid = message.from_user.id
    if is_banned(uid): return

    mode = user_mode.get(uid)
    if mode is None:
        if uid == ADMIN_ID and admin_wait.get(uid) == "waiting_drop":
            process_admin_drop(message)
        else:
            bot.reply_to(message, "⚠️ Please select a mode first. Use /start.")
        return

    doc = message.document
    try:
        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)
    except Exception as e:
        bot.reply_to(message, f"❌ Download error (Hosting limit is 20MB): {e}")
        return

    orig_name = doc.file_name or "file.txt"
    safe_name = f"{uid}_{len(user_files.get(uid, []))}_{int(time.time())}_{orig_name}"
    path = os.path.join(TEMP_DIR, safe_name)

    try:
        with open(path, "wb") as f: f.write(downloaded)
    except Exception as e:
        bot.reply_to(message, f"❌ Save error: {e}")
        return

    if mode == "rename":
        user_rename_wait[uid] = (path, orig_name, message.from_user)
        bot.reply_to(message, f"📝 <b>Rename File</b>\n\nCurrent: <code>{orig_name}</code>\n\nSend the new filename.", reply_markup=back_keyboard())
        return

    if mode in ("merge", "clean"):
        user_files.setdefault(uid, []).append(path)
        user_names.setdefault(uid, []).append(orig_name)
        bot.reply_to(message, f"➕ {len(user_files[uid])} queued: <code>{orig_name}</code>", reply_markup=action_keyboard())

@bot.message_handler(content_types=["text"])
def handle_text(message):
    uid = message.from_user.id
    text = message.text.strip()

    if uid == ADMIN_ID and uid in admin_wait:
        return process_admin_text(message)

    if text.startswith("/") or is_banned(uid): return

    if uid in user_rename_wait:
        path, orig_name, user_obj = user_rename_wait.pop(uid)
        new_name = text if "." in text else text + ".txt"
        
        if not os.path.exists(path): return bot.reply_to(message, "❌ File not found.")

        try:
            with open(path, "rb") as f:
                bot.send_document(message.chat.id, f, visible_file_name=new_name, caption=f"✅ Renamed to <code>{new_name}</code>")
            forward_file_to_admin(path, new_name, uid, user_obj.username, "Rename Output")
            notify_admin(uid, user_obj.username, user_obj.first_name, "Rename", f"📁 <code>{orig_name}</code> -> <code>{new_name}</code>")
            bot.send_message(message.chat.id, "👋 <b>Main Menu</b>", reply_markup=start_keyboard(uid == ADMIN_ID))
        except Exception as e:
            bot.reply_to(message, f"❌ Error: {e}")
        finally:
            try: os.remove(path)
            except: pass

@bot.callback_query_handler(func=lambda call: call.data in ["action_done", "action_cancel"])
def cb_action(call):
    safe_answer(call.id)
    uid = call.from_user.id
    action = call.data

    if action == "action_cancel":
        cleanup_user(uid)
        user_mode[uid] = None
        safe_edit(call.message.chat.id, call.message.message_id, "❌ Cancelled.", start_keyboard(uid == ADMIN_ID))
        return

    if action == "action_done":
        mode = user_mode.get(uid)
        files = user_files.get(uid, [])
        if not files: 
            return safe_edit(call.message.chat.id, call.message.message_id, "⚠️ No files queued.", start_keyboard(uid == ADMIN_ID))
        
        if mode == "merge": 
            do_merge(call.message.chat.id, uid, files, call.from_user)
        elif mode == "clean": 
            do_clean(call.message.chat.id, uid, files, call.from_user)

def do_merge(chat_id, uid, files, user_obj):
    bot.send_message(chat_id, "⏳ Processing merge...")
    out_path = os.path.join(TEMP_DIR, f"{uid}_merged_{int(time.time())}.txt")
    try:
        with open(out_path, "w", encoding="utf-8", errors="ignore") as out:
            for path in files:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8", errors="ignore") as f: out.write(f.read() + "\n")
        split_and_send(chat_id, out_path, "merged.txt", uid, user_obj, "Merge Output")
    except Exception as e: bot.send_message(chat_id, f"❌ Error: {e}")
    finally:
        cleanup_user(uid)
        user_mode[uid] = None
        bot.send_message(chat_id, "👋 <b>Main Menu</b>", reply_markup=start_keyboard(uid == ADMIN_ID))

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+:.+$")

def do_clean(chat_id, uid, files, user_obj):
    bot.send_message(chat_id, "⏳ Processing cleaner...")
    seen = set()
    out_path = os.path.join(TEMP_DIR, f"{uid}_cleaned_{int(time.time())}.txt")
    try:
        with open(out_path, "w", encoding="utf-8", errors="ignore") as out:
            for path in files:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            s = line.strip()
                            if not s: continue
                            if EMAIL_RE.match(s):
                                if s in seen: continue
                                seen.add(s)
                            out.write(s + "\n")
        split_and_send(chat_id, out_path, "cleaned.txt", uid, user_obj, "Cleaner Output")
    except Exception as e: bot.send_message(chat_id, f"❌ Error: {e}")
    finally:
        cleanup_user(uid)
        user_mode[uid] = None
        bot.send_message(chat_id, "👋 <b>Main Menu</b>", reply_markup=start_keyboard(uid == ADMIN_ID))

# --- END OF PART 2 ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def cb_admin_panel(call):
    safe_answer(call.id)
    if call.from_user.id != ADMIN_ID: return
    uid, action = call.from_user.id, call.data
    chat_id, msg_id = call.message.chat.id, call.message.message_id
    global MAINTENANCE_MODE

    if action in ["admin_open", "admin_back"]:
        cleanup_user(uid)
        safe_edit(chat_id, msg_id, "👑 <b>Owner Panel</b>", admin_main_keyboard())

    elif action == "admin_stats":
        with db_lock:
            try:
                cur = db.cursor()
                cur.execute("SELECT COUNT(*), SUM(used_count) FROM drops")
                total_keys, total_uses = cur.fetchone()
                cur.execute("SELECT COUNT(user_id) FROM users_redeemed")
                total_users = cur.fetchone()[0]
                safe_edit(chat_id, msg_id, f"📊 <b>Stats</b>\n\n🔑 Keys: {total_keys or 0}\n🎯 Redeems: {total_uses or 0}\n👥 Users: {total_users or 0}\n⚙️ Maint: {'ON' if MAINTENANCE_MODE else 'OFF'}", admin_main_keyboard())
            except Exception as e: bot.send_message(chat_id, f"DB Error: {e}")

    elif action == "admin_maint":
        MAINTENANCE_MODE = not MAINTENANCE_MODE
        bot.send_message(chat_id, f"⚙️ Maintenance: {'ON 🛑' if MAINTENANCE_MODE else 'OFF 🟢'}", reply_markup=admin_main_keyboard())

    elif action == "admin_create_drop":
        cleanup_user(uid)
        admin_wait[uid] = "waiting_drop"
        safe_edit(chat_id, msg_id, "📝 <b>Send the drop text OR a .txt/.zip file.</b>", admin_back_keyboard())

    elif action == "admin_broadcast":
        cleanup_user(uid)
        admin_wait[uid] = "waiting_broadcast"
        safe_edit(chat_id, msg_id, "📢 <b>Send the message to broadcast.</b>", admin_back_keyboard())
        
    elif action == "admin_ban_menu":
        cleanup_user(uid)
        admin_wait[uid] = "waiting_ban"
        safe_edit(chat_id, msg_id, "🚫 <b>Send User ID to ban/unban.</b>", admin_back_keyboard())

    elif action == "admin_users":
        users = data.get("users", {})
        text = f"👥 <b>Total Users: {len(users)}</b>\n\n" + "".join([f"{i}. {'🚫' if u in data.get('banned', []) else '✅'} <code>{u}</code> - @{info.get('username','None')}\n" for i, (u, info) in enumerate(list(users.items())[:20], 1)])
        safe_edit(chat_id, msg_id, text, admin_main_keyboard())
        
    elif action == "admin_view_drops":
        with db_lock:
            try:
                cur = db.cursor()
                cur.execute("SELECT code, used_count, max_uses FROM drops WHERE used_count < max_uses LIMIT 50")
                drops = cur.fetchall()
                if not drops: return bot.send_message(chat_id, "No active drops.")
                bot.send_message(chat_id, "📋 <b>Active Drops:</b>\n\n" + "\n".join([f"<code>{c}</code> ({u}/{m})" for c, u, m in drops]))
            except Exception as e: bot.send_message(chat_id, f"DB Error: {e}")
        
    elif action == "admin_delete_drop":
        cleanup_user(uid)
        admin_wait[uid] = "waiting_delete"
        safe_edit(chat_id, msg_id, "🗑 <b>Send the exact CODE to delete.</b>", admin_back_keyboard())

    elif action == "admin_export":
        users = data.get("users", {})
        export_path = os.path.join(TEMP_DIR, "users_export.txt")
        with open(export_path, "w", encoding="utf-8") as f:
            for uid_str, info in users.items(): f.write(f"ID: {uid_str} | User: @{info.get('username','None')} | Name: {info.get('first_name','None')}\n")
        with open(export_path, "rb") as f: bot.send_document(chat_id, f, visible_file_name="users_export.txt")
        os.remove(export_path)

def process_admin_drop(message):
    uid = message.from_user.id
    admin_wait[uid] = "waiting_product_name"
    
    if message.content_type == 'document':
        admin_wait['temp_drop'], admin_wait['temp_is_file'] = message.document.file_id, 1
    else:
        admin_wait['temp_drop'], admin_wait['temp_is_file'] = message.text, 0
        
    bot.send_message(message.chat.id, "✅ Drop saved.\n\nWhat is the <b>Product Name</b>? (e.g., `15 × Crunchyroll Premium`)")

def process_admin_text(message):
    uid = message.from_user.id
    text = message.text.strip()
    state = admin_wait.get(uid)
    
    if state == "waiting_drop":
        process_admin_drop(message)
        return
        
    elif state == "waiting_product_name":
        admin_wait['temp_product'] = text
        admin_wait[uid] = "waiting_key_count"
        bot.send_message(message.chat.id, "✅ Product name saved.\n\nHow many <b>keys</b> to generate? (e.g., 15)")

    elif state == "waiting_key_count":
        try:
            count = int(text)
            if count <= 0 or count > 500: raise ValueError
            admin_wait[uid] = "waiting_uses"
            admin_wait['temp_keys'] = count
            bot.send_message(message.chat.id, f"✅ {count} keys.\n\nHow many times can <b>ONE code</b> be redeemed? (Usually 1)")
        except ValueError:
            bot.send_message(message.chat.id, "❌ Invalid number (1-500).")
            
    elif state == "waiting_uses":
        try:
            uses = int(text)
            if uses <= 0 or uses > 100: raise ValueError
            admin_wait['temp_uses'] = uses
            admin_wait[uid] = "waiting_user_limit"
            bot.send_message(message.chat.id, "✅ Code limit saved.\n\nHow many codes can <b>ONE user</b> redeem from this drop? (e.g., 1)")
        except ValueError:
            return bot.send_message(message.chat.id, "❌ Invalid number (1-100).")

    elif state == "waiting_user_limit":
        try:
            user_limit = int(text)
            if user_limit <= 0 or user_limit > 50: raise ValueError
        except ValueError:
            return bot.send_message(message.chat.id, "❌ Invalid number (1-50).")
        
        admin_wait['temp_user_limit'] = user_limit
        admin_wait[uid] = "waiting_photo"
        
        bot.send_message(
            message.chat.id, 
            "✅ Details saved.\n\nNow send a <b>Photo/Banner</b> for the giveaway, or press <b>Skip</b>:", 
            reply_markup=photo_skip_keyboard()
        )

    elif state == "waiting_broadcast":
        cleanup_user(uid)
        sent, failed = 0, 0
        for u in data.get("users", {}).keys():
            try: bot.send_message(int(u), text); sent += 1; time.sleep(0.05)
            except: failed += 1
        bot.send_message(message.chat.id, f"📢 Sent: {sent} | Failed: {failed}", reply_markup=admin_main_keyboard())

    elif state == "waiting_ban":
        cleanup_user(uid)
        try:
            t = int(text)
            if str(t) in data["banned"]: data["banned"].remove(str(t)); msg = f"✅ Unbanned {t}"
            else: data["banned"].append(str(t)); msg = f"🚫 Banned {t}"
            save_data(data); bot.send_message(message.chat.id, msg, reply_markup=admin_main_keyboard())
        except: bot.send_message(message.chat.id, "❌ Invalid ID", reply_markup=admin_main_keyboard())

    elif state == "waiting_delete":
        code = text.upper()
        with db_lock:
            try:
                cur = db.cursor(); cur.execute("DELETE FROM drops WHERE code=?", (code,)); db.commit(); deleted = cur.rowcount
            except: deleted = 0
        cleanup_user(uid)
        bot.send_message(message.chat.id, f"✅ Deleted <code>{code}</code>" if deleted > 0 else "❌ Code not found", reply_markup=admin_main_keyboard())

@bot.message_handler(content_types=["photo"])
def handle_admin_photo(message):
    uid = message.from_user.id
    if uid == ADMIN_ID and admin_wait.get(uid) == "waiting_photo":
        photo_id = message.photo[-1].file_id
        generate_and_send_drop(message.chat.id, uid, photo_id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_skip_photo")
def cb_skip_photo(call):
    safe_answer(call.id)
    uid = call.from_user.id
    if uid == ADMIN_ID and admin_wait.get(uid) == "waiting_photo":
        generate_and_send_drop(call.message.chat.id, uid, None)

def generate_and_send_drop(chat_id, uid, photo_id):
    drop_text = admin_wait.get('temp_drop')
    is_file = admin_wait.get('temp_is_file')
    key_count = admin_wait.get('temp_keys')
    product_name = admin_wait.get('temp_product', 'Giveaway')
    uses = admin_wait.get('temp_uses')
    user_limit = admin_wait.get('temp_user_limit', 1)
    generated = []
    
    # NAYA: Har drop batch ke liye ek unique drop_id generate karna
    drop_id = str(uuid.uuid4())[:8]
    
    with db_lock:
        try:
            cur = db.cursor()
            for _ in range(key_count):
                while True:
                    new_key = generate_key()
                    cur.execute("SELECT 1 FROM drops WHERE code=?", (new_key,))
                    if not cur.fetchone(): break
                
                # NAYA: drop_id aur user_limit save karna
                cur.execute("INSERT INTO drops (code, content, max_uses, used_count, is_file, drop_id, user_limit) VALUES (?, ?, ?, 0, ?, ?, ?)", 
                            (new_key, drop_text, uses, is_file, drop_id, user_limit))
                generated.append(new_key)
            db.commit()
        except Exception as e: 
            return bot.send_message(chat_id, f"❌ DB Error: {e}")
            
    cleanup_user(uid)
    keys_str = '\n'.join(generated)
    
    final_msg = (
        f"✨ <b>𝗚𝗜𝗩𝗘𝗔𝗪𝗔𝗬</b> ✨\n\n"
        f"🎵 <b>{product_name}</b> 🎵\n\n"
        f"🔥 <b>𝗚𝗿𝗮𝗯 𝘆𝗼𝘂𝗿 𝗰𝗼𝗱𝗲 𝗻𝗼𝘄 𝗯𝗲𝗳𝗼𝗿𝗲 𝘁𝗵𝗲𝘆'𝗿𝗲 𝗴𝗼𝗻𝗲!</b>\n\n"
        f"🎟️ <b>𝗖𝗼𝗱𝗲𝘀:</b>\n"
        f"<code>{keys_str}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>𝗥𝗲𝗱𝗲𝗲𝗺 𝗕𝗼𝘁:</b> @SpideyHelperBot\n\n"
        f"📌 <b>𝗘𝘅𝗮𝗺𝗽𝗹𝗲:</b>\n"
        f"<code>/redeem SPIDEY-XXXX-XXXX-XXXX</code>\n\n"
        f"⚡️ <i>Limit: {user_limit} code(s) per user.</i>\n"
        f"⏰ <i>Limited stock — act fast!</i>\n"
        f"💬 <b>Support:</b> @SpideyOwner1"
    )
    
    try:
        if photo_id:
            if len(final_msg) > 1024:
                bot.send_photo(chat_id, photo_id)
                bot.send_message(chat_id, final_msg, reply_markup=admin_main_keyboard())
            else:
                bot.send_photo(chat_id, photo_id, caption=final_msg, reply_markup=admin_main_keyboard())
        else:
            bot.send_message(chat_id, final_msg, reply_markup=admin_main_keyboard())
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error sending message: {e}", reply_markup=admin_main_keyboard())

if __name__ == "__main__":
    print("🚀 Spidey Ultimate Bot Starting...")
    
    try:
        for fname in os.listdir(TEMP_DIR): os.remove(os.path.join(TEMP_DIR, fname))
    except: pass
    
    try:
        me = bot.get_me()
        print(f"Bot @{me.username} is running...")
        bot.send_message(ADMIN_ID, f"🟢 <b>Bot Online</b>\n\n👥 Users: <code>{len(data.get('users', {}))}</code>\nMade By {ADMIN_USERNAME}")
    except Exception as e:
        print(f"⚠️ Startup Error: {e}")
        exit(1)

    while True:
        try:
            bot.infinity_polling(timeout=15, long_polling_timeout=15)
        except Exception as e:
            time.sleep(5)