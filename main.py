import os
import sqlite3
import logging
import time
from collections import defaultdict
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ⚠️ SECURITY WARNING: Never hardcode bot tokens directly in your scripts.
TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

if not TOKEN or TOKEN == "YOUR_BOT_TOKEN_HERE":
    raise ValueError(
        "BOT_TOKEN environment variable is missing or using default placeholder! "
        "Set it in your environment before running."
    )

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

DB_PATH = "chat_bot.db"

# --- SPAM SYSTEM SETTINGS ---
# Stores timestamps of media messages per user: {user_id: [timestamp1, timestamp2, ...]}
user_media_timestamps = defaultdict(list)
SPAM_LIMIT = 20  # Max media count
SPAM_WINDOW = 5.0  # Time window in seconds

def is_spamming_media(user_id: int) -> bool:
    """Checks if a user sent more than 20 media items in 5 seconds."""
    current_time = time.time()
    # Filter out timestamps older than 5 seconds
    user_media_timestamps[user_id] = [
        ts for ts in user_media_timestamps[user_id] if current_time - ts <= SPAM_WINDOW
    ]
    
    # Check limit
    if len(user_media_timestamps[user_id]) >= SPAM_LIMIT:
        return True
    
    # Add current timestamp
    user_media_timestamps[user_id].append(current_time)
    return False

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            display_name TEXT NOT NULL,
            message_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            is_admin INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            infinite_sync INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS media_store (
            media_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            sender_name TEXT,
            media_type TEXT NOT NULL,
            file_id TEXT NOT NULL,
            caption TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS service_config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO service_config (key, value) 
        VALUES ('service_msg', 'Welcome to the Anonymous Group Chat & Media Vault! Send any message, photo, or video to broadcast it.')
    """)
    conn.commit()
    conn.close()

def db_execute(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(query, params)
    result = None
    if fetchone:
        result = cursor.fetchone()
    elif fetchall:
        result = cursor.fetchall()
    if commit:
        conn.commit()
    conn.close()
    return result

init_db()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data["waiting_for_storage"] = False
    
    if context.args and context.args[0].startswith("media_"):
        try:
            media_id = int(context.args[0].split("_")[1])
            media_record = db_execute(
                "SELECT sender_name, media_type, file_id, caption, timestamp FROM media_store WHERE media_id = ?",
                (media_id,),
                fetchone=True
            )
            if media_record:
                sender_name, media_type, file_id, caption, timestamp = media_record
                formatted_caption = f"📦 *Stored Media Link*\nFrom *{sender_name}* ({timestamp}):\n{caption}" if caption else f"📦 *Stored Media Link*\nFrom *{sender_name}* ({timestamp})"
                
                await update.message.reply_text("📂 Loading requested shared media...")
                if media_type == "photo":
                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=file_id, caption=formatted_caption, parse_mode="Markdown")
                elif media_type == "video":
                    await context.bot.send_video(chat_id=update.effective_chat.id, video=file_id, caption=formatted_caption, parse_mode="Markdown")
                return
            else:
                await update.message.reply_text("❌ This media link is invalid or the file has been removed.")
        except ValueError:
            pass

    user_record = db_execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if user_record and user_record[0] == 1:
        await update.message.reply_text("⛔ You are banned from using this bot.")
        return

    default_name = f"User_{str(user_id)[-4:]}"
    db_execute(
        "INSERT INTO users (user_id, display_name) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET is_active = 1",
        (user_id, default_name),
        commit=True,
    )
    user_data = db_execute(
        "SELECT display_name FROM users WHERE user_id = ?",
        (user_id,),
        fetchone=True,
    )
    current_name = user_data[0] if user_data else default_name
    
    service_record = db_execute("SELECT value FROM service_config WHERE key = 'service_msg'", fetchone=True)
    admin_service_text = service_record[0] if service_record else "Welcome!"

    welcome_msg = (
        f"📢 *Admin Service Notice*\n"
        f"{admin_service_text}\n\n"
        f"-----------------------------------\n"
        f"👤 Your Display Name: *{current_name}*\n"
        f"🔹 `/setmyname YourName` - Change name\n"
        f"🔹 `/info` - View your profile stats\n"
        f"🔹 `/leaderboard` - View top chatters\n"
        f"🔹 `/syncmedia` - Sync/download shared media\n"
        f"🔹 `/mystorage` - Store media & get a link\n"
        f"🔹 `/help` - Show all commands"
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_for_storage"] = False
    service_record = db_execute("SELECT value FROM service_config WHERE key = 'service_msg'", fetchone=True)
    admin_service_text = service_record[0] if service_record else "No active notice."

    help_text = (
        f"🤖 *Anonymous Chat Bot - Help Menu* 🤖\n\n"
        f"📌 *Admin Service Notice:*\n{admin_service_text}\n\n"
        f"Here are the available commands you can use:\n"
        f"🔹 `/start` - Start the bot & see service notice\n"
        f"🔹 `/setmyname ` - Change your anonymous display name (up to 30 characters)\n"
        f"🔹 `/info` - View your profile stats (messages sent, media shared, status)\n"
        f"🔹 `/leaderboard` - View top chatters and their message counts\n"
        f"🔹 `/syncmedia` - Sync media (Free users get 1 item 5s preview; contact admin for infinite sync)\n"
        f"🔹 `/mystorage` - Open private media vault to store files and generate shareable links\n"
        f"🔹 `/help` - Show this help menu\n\n"
        f"💬 *Broadcasting:* Just send text, photos, or videos normally to broadcast anonymously!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage: `/setmyname YourNewName`", parse_mode="Markdown")
        return
    new_name = " ".join(context.args)
    if len(new_name) > 30:
        await update.message.reply_text("Name must be 30 characters or fewer.")
        return
    db_execute("UPDATE users SET display_name = ? WHERE user_id = ?", (new_name, user_id), commit=True)
    await update.message.reply_text(f"Your name has been updated to: *{new_name}*", parse_mode="Markdown")

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_record = db_execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    if user_record and user_record[0] == 1:
        await update.message.reply_text("⛔ You are banned from using this bot.")
        return

    target_id = user_id
    is_admin = db_execute("SELECT is_admin FROM users WHERE user_id = ? AND is_admin = 1", (user_id,), fetchone=True)
    
    if context.args and is_admin:
        try:
            target_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Invalid user ID.")
            return

    user_data = db_execute("SELECT display_name, message_count, is_banned, infinite_sync FROM users WHERE user_id = ?", (target_id,), fetchone=True)
    if not user_data:
        await update.message.reply_text(f"❌ No records found for user ID `{target_id}`.", parse_mode="Markdown")
        return

    display_name, message_count, is_banned, infinite_sync = user_data
    media_count = db_execute("SELECT COUNT(*) FROM media_store WHERE sender_id = ?", (target_id,), fetchone=True)[0]

    status = "🚫 Banned" if is_banned == 1 else "🟢 Active"
    sync_status = "♾️ Infinite Sync Enabled" if infinite_sync == 1 else "⏱️ Limited (5s/1-Item Sync)"

    info_text = (
        f"📊 *User Information Profile*\n\n"
        f"🆔 User ID: `{target_id}`\n"
        f"👤 Display Name: *{display_name}*\n"
        f"💬 Messages Sent: `{message_count}`\n"
        f"📦 Media Shared: `{media_count}`\n"
        f"📌 Status: {status}\n"
        f"🔄 Sync Tier: {sync_status}"
    )
    await update.message.reply_text(info_text, parse_mode="Markdown")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_users = db_execute("SELECT display_name, message_count FROM users WHERE is_banned = 0 ORDER BY message_count DESC LIMIT 10", fetchall=True)
    if not top_users or top_users[0][1] == 0:
        await update.message.reply_text("No messages sent yet! Be the first to start talking.")
        return
    text = "🏆 *Top Chatters Leaderboard* 🏆\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for index, (name, count) in enumerate(top_users, start=1):
        prefix = medals[index - 1] if index <= 3 else f"`{index}.`"
        text += f"{prefix} *{name}*: {count} messages\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def sync_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_info = db_execute("SELECT infinite_sync FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    has_infinite = user_info and user_info[0] == 1

    media_records = db_execute("SELECT sender_name, media_type, file_id, caption, timestamp FROM media_store ORDER BY timestamp ASC", fetchall=True)
    if not media_records:
        await update.message.reply_text("No media has been shared in this chat yet.")
        return

    if not has_infinite:
        latest_media = media_records[-1]
        sender_name, media_type, file_id, caption, timestamp = latest_media
        formatted_caption = f"⏱️ *Free Sync Preview (5s/1-Item Limit)*\nFrom *{sender_name}* ({timestamp}):\n{caption}" if caption else f"⏱️ *Free Sync Preview (5s/1-Item Limit)*\nFrom *{sender_name}* ({timestamp})"
        
        await update.message.reply_text("📦 Syncing your allowed 1 trial media item...")
        try:
            if media_type == "photo":
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=file_id, caption=formatted_caption, parse_mode="Markdown")
            elif media_type == "video":
                await context.bot.send_video(chat_id=update.effective_chat.id, video=file_id, caption=formatted_caption, parse_mode="Markdown")
        except Exception:
            pass

        upgrade_msg = (
            f"🔒 *Want Infinite Sync Time & All Files?*\n\n"
            f"You have reached your standard sync limit. To unlock **infinite sync time** and download all past files instantly, please contact an admin."
        )
        await update.message.reply_text(upgrade_msg, parse_mode="Markdown")
        return

    await update.message.reply_text(f"♾️ Infinite Sync active. Loading all {len(media_records)} media item(s)...")
    for sender_name, media_type, file_id, caption, timestamp in media_records:
        formatted_caption = f"From *{sender_name}* ({timestamp}):\n{caption}" if caption else f"From *{sender_name}* ({timestamp})"
        try:
            if media_type == "photo":
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=file_id, caption=formatted_caption, parse_mode="Markdown")
            elif media_type == "video":
                await context.bot.send_video(chat_id=update.effective_chat.id, video=file_id, caption=formatted_caption, parse_mode="Markdown")
        except Exception:
            pass

async def mystorage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    storage_help = (
        "📂 *Personal Media Storage Vault*\n\n"
        "Want to store media and turn it into a shareable link?\n\n"
        "Send any photo or video right now with an optional caption, and the bot will generate a custom shareable link for you!"
    )
    context.user_data["waiting_for_storage"] = True
    await update.message.reply_text(storage_help, parse_mode="Markdown")

# --- ADMIN PANEL & SERVICE MESSAGE CONTROL ---

async def admin_set_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = db_execute("SELECT is_admin FROM users WHERE user_id = ? AND is_admin = 1", (user_id,), fetchone=True)
    if not is_admin:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/setservice Your new service message here`", parse_mode="Markdown")
        return

    new_service_msg = " ".join(context.args)
    db_execute("INSERT OR REPLACE INTO service_config (key, value) VALUES ('service_msg', ?)", (new_service_msg,), commit=True)
    await update.message.reply_text(f"✅ Service message successfully updated!\n\n*{new_service_msg}*", parse_mode="Markdown")

async def grant_infinite_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = db_execute("SELECT is_admin FROM users WHERE user_id = ? AND is_admin = 1", (user_id,), fetchone=True)
    if not is_admin:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/infinitesync `", parse_mode="Markdown")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return

    db_execute("UPDATE users SET infinite_sync = 1 WHERE user_id = ?", (target_id,), commit=True)
    try:
        await context.bot.send_message(chat_id=target_id, text="🎉 Your account has been upgraded with **Infinite Sync Time** by the admin team!", parse_mode="Markdown")
    except Exception:
        pass
    await update.message.reply_text(f"✅ User `{target_id}` has been granted Infinite Sync.", parse_mode="Markdown")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if context.args and context.args[0] == "ahadop123":
        db_execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,), commit=True)
        await update.message.reply_text("🎉 Admin authentication successful!")

    admin_data = db_execute("SELECT is_admin FROM users WHERE user_id = ? AND is_admin = 1", (user_id,), fetchone=True)
    if not admin_data:
        await update.message.reply_text("⛔ Unauthorized. Use `/admin ` to log in.", parse_mode="Markdown")
        return

    total_users = db_execute("SELECT COUNT(*) FROM users", fetchone=True)[0]
    active_users = db_execute("SELECT COUNT(*) FROM users WHERE is_active = 1 AND is_banned = 0", fetchone=True)[0]
    banned_users = db_execute("SELECT COUNT(*) FROM users WHERE is_banned = 1", fetchone=True)[0]
    total_msgs = db_execute("SELECT SUM(message_count) FROM users", fetchone=True)[0] or 0
    total_media = db_execute("SELECT COUNT(*) FROM media_store", fetchone=True)[0]
    
    current_service = db_execute("SELECT value FROM service_config WHERE key = 'service_msg'", fetchone=True)[0]

    admin_text = (
        f"🛠 *Admin Control Panel* 🛠\n\n"
        f"👥 Total Users: `{total_users}` | 🟢 Active: `{active_users}` | 🚫 Banned: `{banned_users}`\n"
        f"💬 Total Messages: `{total_msgs}` | 📦 Media Stored: `{total_media}`\n\n"
        f"📢 **Current Service Message:**\n_{current_service}_\n\n"
        f"*Admin Controls & Commands:*\n"
        f"🔹 `/setservice ` - Update bot service message\n"
        f"🔹 `/abroadcast ` - Send official announcement\n"
        f"🔹 `/infinitesync ` - Grant infinite sync\n"
        f"🔹 `/ban ` / `/unban ` - Manage bans\n"
        f"🔹 `/kick ` - Kick/delete user"
    )
    await update.message.reply_text(admin_text, parse_mode="Markdown")

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = db_execute("SELECT is_admin FROM users WHERE user_id = ? AND is_admin = 1", (user_id,), fetchone=True)
    if not is_admin:
        await update.message.reply_text("⛔ You are not authorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/abroadcast Your announcement text here`", parse_mode="Markdown")
        return

    announcement = "📢 *Admin Announcement*:\n\n" + " ".join(context.args)
    all_users = db_execute("SELECT user_id FROM users WHERE is_banned = 0", fetchall=True)
    
    sent_count = 0
    blocked_count = 0

    for (recipient_id,) in all_users:
        try:
            await context.bot.send_message(chat_id=recipient_id, text=announcement, parse_mode="Markdown")
            sent_count += 1
        except Exception:
            blocked_count += 1
            db_execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (recipient_id,), commit=True)

    await update.message.reply_text(f"✅ Broadcast complete!\n📤 Sent: `{sent_count}` | ❌ Failed: `{blocked_count}`", parse_mode="Markdown")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = db_execute("SELECT is_admin FROM users WHERE user_id = ? AND is_admin = 1", (user_id,), fetchone=True)
    if not is_admin or not context.args:
        await update.message.reply_text("Usage: `/ban `", parse_mode="Markdown")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return
    db_execute("UPDATE users SET is_banned = 1, is_active = 0 WHERE user_id = ?", (target_id,), commit=True)
    await update.message.reply_text(f"✅ User `{target_id}` has been banned.", parse_mode="Markdown")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = db_execute("SELECT is_admin FROM users WHERE user_id = ? AND is_admin = 1", (user_id,), fetchone=True)
    if not is_admin or not context.args:
        await update.message.reply_text("Usage: `/unban `", parse_mode="Markdown")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return
    db_execute("UPDATE users SET is_banned = 0, is_active = 1 WHERE user_id = ?", (target_id,), commit=True)
    await update.message.reply_text(f"✅ User `{target_id}` has been unbanned.", parse_mode="Markdown")

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = db_execute("SELECT is_admin FROM users WHERE user_id = ? AND is_admin = 1", (user_id,), fetchone=True)
    if not is_admin or not context.args:
        await update.message.reply_text("Usage: `/kick `", parse_mode="Markdown")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return
    db_execute("DELETE FROM users WHERE user_id = ?", (target_id,), commit=True)
    await update.message.reply_text(f"✅ User `{target_id}` kicked and removed.", parse_mode="Markdown")

# --- BROADCASTING MESSAGES/MEDIA & STORAGE HANDLER ---

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.effective_user.id
    user_record = db_execute("SELECT display_name, is_banned FROM users WHERE user_id = ?", (sender_id,), fetchone=True)
    if user_record and user_record[1] == 1:
        await update.message.reply_text("⛔ You are banned from using this bot.")
        return

    if not user_record:
        sender_name = f"User_{str(sender_id)[-4:]}"
        db_execute("INSERT INTO users (user_id, display_name, message_count, is_active) VALUES (?, ?, 1, 1)", (sender_id, sender_name), commit=True)
    else:
        sender_name = user_record[0]
        db_execute("UPDATE users SET message_count = message_count + 1, is_active = 1 WHERE user_id = ?", (sender_id,), commit=True)

    # 🛑 SPAM PROTECTION CHECK FOR MEDIA 🛑
    if update.message.photo or update.message.video:
        if is_spamming_media(sender_id):
            await update.message.reply_text("⚠️ *Anti-Spam Warning*: You cannot send more than 20 media items in 5 seconds! Please slow down.", parse_mode="Markdown")
            return

    # 📂 FIXED MYSTORAGE VAULT UPLOAD HANDLER
    if context.user_data.get("waiting_for_storage"):
        if update.message.photo or update.message.video:
            media_type = "photo" if update.message.photo else "video"
            file_id = update.message.photo[-1].file_id if media_type == "photo" else update.message.video.file_id
            file_name = update.message.caption if update.message.caption else f"Media_{sender_id}"
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO media_store (sender_id, sender_name, media_type, file_id, caption) VALUES (?, ?, ?, ?, ?)",
                (sender_id, sender_name, media_type, file_id, file_name)
            )
            media_db_id = cursor.lastrowid
            conn.commit()
            conn.close()

            bot_username = context.bot.username
            shareable_link = f"https://t.me/{bot_username}?start=media_{media_db_id}"

            storage_success = (
                f"✅ *Media Stored Successfully!*\n\n"
                f"📌 Title: *{file_name}*\n"
                f"🔗 **Your Shareable Link:**\n`{shareable_link}`"
            )
            context.user_data["waiting_for_storage"] = False
            await update.message.reply_text(storage_success, parse_mode="Markdown")
            return
        else:
            # Clear state if user sends plain text instead of media
            context.user_data["waiting_for_storage"] = False

    active_users = db_execute("SELECT user_id FROM users WHERE is_active = 1 AND is_banned = 0", fetchall=True)
    
    # Broadcast Text Messages
    if update.message.text:
        formatted_msg = f"*{sender_name}*: {update.message.text}"
        for (recipient_id,) in active_users:
            if recipient_id != sender_id:
                try:
                    await context.bot.send_message(chat_id=recipient_id, text=formatted_msg, parse_mode="Markdown")
                except Exception:
                    db_execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (recipient_id,), commit=True)
                    
    # Broadcast Media Messages
    elif update.message.photo or update.message.video:
        media_type = "photo" if update.message.photo else "video"
        file_id = update.message.photo[-1].file_id if media_type == "photo" else update.message.video.file_id
        caption_text = update.message.caption if update.message.caption else ""
        
        db_execute("INSERT INTO media_store (sender_id, sender_name, media_type, file_id, caption) VALUES (?, ?, ?, ?, ?)",
                   (sender_id, sender_name, media_type, file_id, caption_text), commit=True)
        
        caption = f"*{sender_name}*: {caption_text}" if caption_text else f"*{sender_name}*"
        for (recipient_id,) in active_users:
            if recipient_id != sender_id:
                try:
                    if media_type == "photo":
                        await context.bot.send_photo(chat_id=recipient_id, photo=file_id, caption=caption, parse_mode="Markdown")
                    elif media_type == "video":
                        await context.bot.send_video(chat_id=recipient_id, video=file_id, caption=caption, parse_mode="Markdown")
                except Exception:
                    db_execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (recipient_id,), commit=True)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Command Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("setmyname", set_name))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("syncmedia", sync_media))
    app.add_handler(CommandHandler("mystorage", mystorage_command))
    
    # Admin Handlers
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("setservice", admin_set_service))
    app.add_handler(CommandHandler("abroadcast", admin_broadcast))
    app.add_handler(CommandHandler("infinitesync", grant_infinite_sync))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("kick", kick_user))
    
    # Message Handlers
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.VIDEO) & ~filters.COMMAND & filters.ChatType.PRIVATE,
            broadcast_message,
        )
    )
    print("Bot is running with anti-spam rate limiting...")
    app.run_polling()

if __name__ == "__main__":
    main()
