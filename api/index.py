import os
import telebot
from telebot import types
from flask import Flask, request

# === CONFIG (Using Environment Variables) ===
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PUBLIC_CHANNEL = os.getenv("PUBLIC_CHANNEL")
PRIVATE_CHANNEL_ID = int(os.getenv("PRIVATE_CHANNEL_ID", "0"))

bot = telebot.TeleBot(TOKEN, threaded=False)
user_data = {}

# === Force Join System ===
def is_user_joined(chat_id):
    if chat_id == ADMIN_ID:
        return True
    try:
        pub_status = bot.get_chat_member(PUBLIC_CHANNEL, chat_id).status
        if pub_status not in ['member', 'administrator', 'creator']:
            return False
        priv_status = bot.get_chat_member(PRIVATE_CHANNEL_ID, chat_id).status
        return priv_status in ['member', 'administrator', 'creator']
    except Exception as e:
        print("Join Check Error:", e)
        return False

def send_force_join(chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("📢 Join 1", url=f"https://t.me/{PUBLIC_CHANNEL.strip('@')}"),
        types.InlineKeyboardButton("🔐 Join 2", url="https://t.me/+h1s1jG6XizAxMzQ1" + str(PRIVATE_CHANNEL_ID)[4:])
    )
    markup.add(types.InlineKeyboardButton("✅ JOINED", callback_data="check_join"))
    bot.send_message(chat_id, "🚫 To use this bot, please join both channels first:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def recheck_join(call):
    chat_id = call.message.chat.id
    if is_user_joined(chat_id):
        bot.answer_callback_query(call.id, "✅ You're now verified!")
        start_handler(call.message)
    else:
        bot.answer_callback_query(call.id, "❌ Still not joined both channels.", show_alert=True)

# === Save Users & Files Count ===
def save_user(user_id):
    if not os.path.exists("/tmp/users.txt"):
        with open("/tmp/users.txt", "w") as f:
            f.write(f"{user_id}\n")
    else:
        with open("/tmp/users.txt", "r") as f:
            users = f.read().splitlines()
        if str(user_id) not in users:
            with open("/tmp/users.txt", "a") as f:
                f.write(f"{user_id}\n")

def increment_file_count():
    path = "/tmp/files_count.txt"
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write("1")
    else:
        with open(path, "r+") as f:
            count_data = f.read()
            count = int(count_data) if count_data else 0
            f.seek(0)
            f.write(str(count + 1))
            f.truncate()

def get_file_count():
    path = "/tmp/files_count.txt"
    if not os.path.exists(path):
        return 0
    with open(path, "r") as f:
        data = f.read()
        return int(data) if data else 0

# === Start Handler ===
@bot.message_handler(commands=['start'])
def start_handler(message):
    chat_id = message.chat.id
    if not is_user_joined(chat_id):
        send_force_join(chat_id)
        return
    save_user(chat_id)
    bot.reply_to(message, "👋 Welcome! Please send me the 📄 *file* you want to attach a 📸 *thumbnail* to.", parse_mode="Markdown")

# === File Handler ===
@bot.message_handler(content_types=['document'])
def handle_file(message):
    chat_id = message.chat.id
    save_user(chat_id)
    if not is_user_joined(chat_id):
        send_force_join(chat_id)
        return
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    file_name = message.document.file_name
    file_path = f"/tmp/{chat_id}_{file_name}"
    with open(file_path, 'wb') as f:
        f.write(downloaded_file)
    user_data[chat_id] = {
        "file_path": file_path,
        "file_name": file_name,
        "file_size": message.document.file_size,
        "mime_type": message.document.mime_type
    }
    bot.send_message(chat_id, "✅ File received!\nNow please send a 🖼️ *thumbnail image*.", parse_mode="Markdown")

# === Thumbnail Handler ===
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id
    save_user(chat_id)
    if not is_user_joined(chat_id):
        send_force_join(chat_id)
        return
    if chat_id not in user_data:
        bot.reply_to(message, "⚠️ Please send a file first before sending an image.")
        return
    photo_file = message.photo[-1]
    photo_info = bot.get_file(photo_file.file_id)
    downloaded_photo = bot.download_file(photo_info.file_path)
    image_path = f"/tmp/{chat_id}_thumb.jpg"
    with open(image_path, 'wb') as img:
        img.write(downloaded_photo)
    user_data[chat_id]["thumbnail"] = image_path
    data = user_data[chat_id]
    caption = (f"📁 **File Info**\n\n📦 *File Name:* `{data['file_name']}`\n📏 *File Size:* `{data['file_size']}`\n📄 *File Type:* `{data['mime_type']}`")
    with open(data['file_path'], 'rb') as f, open(image_path, 'rb') as thumb:
        bot.send_document(chat_id, document=(data['file_name'], f), caption=caption, thumb=thumb, parse_mode="Markdown")
    increment_file_count()
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✏️ Rename File", callback_data="rename"))
    bot.send_message(chat_id, "🔧 Do you want to rename the file?", reply_markup=markup)

# === Rename Flow ===
@bot.callback_query_handler(func=lambda call: call.data == "rename")
def ask_new_name(call):
    bot.send_message(call.message.chat.id, "📝 Send the *new name* for the file (with extension, e.g. `example.py`)", parse_mode="Markdown")
    bot.register_next_step_handler(call.message, rename_file)

def rename_file(message):
    chat_id = message.chat.id
    new_name = message.text.strip()
    if chat_id not in user_data or "thumbnail" not in user_data[chat_id]:
        bot.send_message(chat_id, "⚠️ Session expired. Please send the file and thumbnail again.")
        return
    data = user_data[chat_id]
    old_path = data["file_path"]
    new_path = f"/tmp/{chat_id}_{new_name}"
    os.rename(old_path, new_path)
    with open(new_path, 'rb') as f, open(data["thumbnail"], 'rb') as thumb:
        bot.send_document(chat_id, document=(new_name, f), caption=f"✅ *Renamed and sent:* `{new_name}`", thumb=thumb, parse_mode="Markdown")
    if os.path.exists(new_path): os.remove(new_path)
    if os.path.exists(data["thumbnail"]): os.remove(data["thumbnail"])
    user_data.pop(chat_id, None)

# === Admin Commands ===
@bot.message_handler(commands=['broadcast'])
def broadcast_handler(message):
    if message.chat.id != ADMIN_ID: return
    bot.send_message(ADMIN_ID, "📢 Send the broadcast message now.")
    bot.register_next_step_handler(message, process_broadcast)

def process_broadcast(message):
    if not os.path.exists("/tmp/users.txt"): return
    with open("/tmp/users.txt", "r") as f:
        users = f.read().splitlines()
    for user_id in users:
        try: bot.send_message(int(user_id), f"📢 *Broadcast:*\n\n{message.text}", parse_mode="Markdown")
        except: continue
    bot.send_message(ADMIN_ID, "✅ Broadcast complete.")

@bot.message_handler(commands=['stats'])
def stats_handler(message):
    if message.chat.id != ADMIN_ID: return
    total_users = 0
    if os.path.exists("/tmp/users.txt"):
        with open("/tmp/users.txt", "r") as f: total_users = len(f.read().splitlines())
    bot.send_message(ADMIN_ID, f"📊 Stats:\n👤 Users: {total_users}\n📁 Files: {get_file_count()}", parse_mode="Markdown")

# === Vercel App ===
app = Flask(__name__)
@app.route('/api/index', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'Forbidden', 403

@app.route('/')
def index(): return "Bot is alive"
