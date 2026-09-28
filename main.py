import os
import sqlite3
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TOKEN = os.environ.get("BOT_TOKEN", "8814653206:AAHUY9SBLo9rvfG1-p8bjaO_lJ-8c0Ges7Y")

if not TOKEN:
    raise ValueError(
        "BOT_TOKEN environment variable is missing! "
        "Set it before running (do NOT hardcode it in the script)."
    )

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

def init_db():
    conn = sqlite3.connect("chat_bot.db")
    cursor = conn.cursor()
    # Table for users with added is_admin and is_banned flags
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            display_name TEXT NOT NULL,
            message_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            is_admin INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0
        )
    """)
    # Table for storing media files sent to the bot
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
    conn.commit()
    conn.close()

def db_execute(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect("chat_bot.db")
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
    
    # Check if user is banned
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
    welcome_msg = (
        f"Welcome to the Anonymous Group Chat!\n\n"
        f"Your current display name is: *{current_name}*\n"
        f"To change it, use: `/setmyname YourName`\n"
        f"To view your stats, use: `/info`\n"
        f"To view chat statistics, use: `/leaderboard`\n"
        f"To sync/download all shared media, use: `/syncmedia`\n"
        f"To see all commands, use: `/help`\n\n"
        f"Just send any message, photo, or video here, and it will be broadcasted to everyone."
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays a list of all available commands and their descriptions."""
    help_text = (
        "🤖 *Anonymous Chat Bot - Help Menu* 🤖\n\n"
        "Here are the available commands you can use:\n\n"
        "🔹 `/start` - Start the bot, register your profile, and see your current display name.\n"
        "🔹 `/setmyname <NewName>` - Change your anonymous display name (up to 30 characters).\n"
        "🔹 `/info` - View your profile stats (messages sent, media shared, account status).\n"
        "🔹 `/leaderboard` - View the top chatters and their message counts.\n"
        "🔹 `/syncmedia` - Retrieve and download all photos and videos shared in the chat.\n"
        "🔹 `/help` - Show this help menu with all command descriptions.\n\n"
        "💬 *Broadcasting:* Just send any text, photo, or video normally, and it will be broadcasted anonymously to all active chat members!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(
            "Usage: `/setmyname YourNewName`", parse_mode="Markdown"
        )
        return
    new_name = " ".join(context.args)
    if len(new_name) > 30:
        await update.message.reply_text("Name must be 30 characters or fewer.")
        return
    db_execute(
        "UPDATE users SET display_name = ? WHERE user_id = ?",
        (new_name, user_id),
        commit=True,
    )
    await update.message.reply_text(
        f"Your name has been updated to: *{new_name}*", parse_mode="Markdown"
    )

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays statistics for the user or a target user (if admin)."""
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

    user_data = db_execute(
        "SELECT display_name, message_count, is_banned FROM users WHERE user_id = ?",
        (target_id,),
        fetchone=True
    )
    
    if not user_data:
        await update.message.reply_text(f"❌ No records found for user ID `{target_id}`.", parse_mode="Markdown")
        return

    display_name, message_count, is_banned = user_data

    media_count = db_execute(
        "SELECT COUNT(*) FROM media_store WHERE sender_id = ?",
        (target_id,),
        fetchone=True
    )[0]

    status = "🚫 Banned" if is_banned == 1 else "🟢 Active"

    info_text = (
        f"📊 *User Information Profile*\n\n"
        f"🆔 User ID: `{target_id}`\n"
        f"👤 Display Name: *{display_name}*\n"
        f"💬 Messages Sent: `{message_count}`\n"
        f"📦 Media Shared: `{media_count}`\n"
        f"📌 Status: {status}"
    )
    
    await update.message.reply_text(info_text, parse_mode="Markdown")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_users = db_execute(
        "SELECT display_name, message_count FROM users WHERE is_banned = 0 "
        "ORDER BY message_count DESC LIMIT 10",
        fetchone=False, fetchall=True,
    )
    if not top_users or top_users[0][1] == 0:
        await update.message.reply_text(
            "No messages sent yet! Be the first to start talking."
        )
        return
    text = "🏆 *Top Chatters Leaderboard* 🏆\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for index, (name, count) in enumerate(top_users, start=1):
        prefix = medals[index - 1] if index <= 3 else f"`{index}.`"
        text += f"{prefix} *{name}*: {count} messages\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def sync_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends back all media files saved in the bot's database to the requesting user."""
    media_records = db_execute(
        "SELECT sender_name, media_type, file_id, caption, timestamp FROM media_store ORDER BY timestamp ASC",
        fetchone=False, fetchall=True,
    )
    if not media_records:
        await update.message.reply_text("No media has been shared in this chat yet.")
        return

    await update.message.reply_text(f"📦 Syncing {len(media_records)} media item(s)...")
    
    for sender_name, media_type, file_id, caption, timestamp in media_records:
        formatted_caption = f"From *{sender_name}* ({timestamp}):\n{caption}" if caption else f"From *{sender_name}* ({timestamp})"
        try:
            if media_type == "photo":
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=file_id,
                    caption=formatted_caption,
                    parse_mode="Markdown",
                )
            elif media_type == "video":
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=file_id,
                    caption=formatted_caption,
                    parse_mode="Markdown",
                )
        except Exception:
            await update.message.reply_text(f"⚠️ Could not load media from *{sender_name}* (expired or deleted).")

# --- ADMIN PANEL & CONTROLS ---

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if context.args and context.args[0] == "ahadop123":
        db_execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,), commit=True)
        await update.message.reply_text("🎉 Admin authentication successful!")

    admin_data = db_execute("SELECT is_admin FROM users WHERE user_id = ? AND is_admin = 1", (user_id,), fetchone=True)
    if not admin_data:
        await update.message.reply_text("⛔ Unauthorized. Use `/admin ahadop123` to log in.", parse_mode="Markdown")
        return

    total_users = db_execute("SELECT COUNT(*) FROM users", fetchone=True)[0]
    active_users = db_execute("SELECT COUNT(*) FROM users WHERE is_active = 1 AND is_banned = 0", fetchone=True)[0]
    banned_users = db_execute("SELECT COUNT(*) FROM users WHERE is_banned = 1", fetchone=True)[0]
    total_msgs = db_execute("SELECT SUM(message_count) FROM users", fetchone=True)[0] or 0
    total_media = db_execute("SELECT COUNT(*) FROM media_store", fetchone=True)[0]

    admin_text = (
        f"🛠 *Admin Control Panel* 🛠\n\n"
        f"👥 Total Registered Users: `{total_users}`\n"
        f"🟢 Active Users: `{active_users}`\n"
        f"🚫 Banned Users: `{banned_users}`\n"
        f"💬 Total Messages Sent: `{total_msgs}`\n"
        f"📦 Total Media Stored: `{total_media}`\n\n"
        f"*Admin Commands:*\n"
        f"🔹 `/abroadcast <text>` - Send an official announcement\n"
        f"🔹 `/ban <user_id>` - Ban a user\n"
        f"🔹 `/unban <user_id>` - Unban a user\n"
        f"🔹 `/kick <user_id>` - Kick/remove a user"
    )
    await update.message.reply_text(admin_text, parse_mode="Markdown")

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = db_execute("SELECT is_admin FROM users WHERE user_id = ? AND is_admin = 1", (user_id,), fetchone=True)
    if not is_admin:
        await update.message.reply_text("⛔ You are not authorized to use this command.")
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
            await context.bot.send_message(
                chat_id=recipient_id,
                text=announcement,
                parse_mode="Markdown"
            )
            sent_count += 1
        except Exception:
            blocked_count += 1
            db_execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (recipient_id,), commit=True)

    await update.message.reply_text(
        f"✅ Broadcast complete!\n"
        f"📤 Successfully sent: `{sent_count}`\n"
        f"❌ Failed (Blocked/Inactive): `{blocked_count}`",
        parse_mode="Markdown"
    )

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = db_execute("SELECT is_admin FROM users WHERE user_id = ? AND is_admin = 1", (user_id,), fetchone=True)
    if not is_admin:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/ban <user_id>`", parse_mode="Markdown")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return

    db_execute("UPDATE users SET is_banned = 1, is_active = 0 WHERE user_id = ?", (target_id,), commit=True)
    try:
        await context.bot.send_message(chat_id=target_id, text="❌ You have been banned from using this bot by an admin.")
    except Exception:
        pass
    await update.message.reply_text(f"✅ User `{target_id}` has been banned successfully.", parse_mode="Markdown")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = db_execute("SELECT is_admin FROM users WHERE user_id = ? AND is_admin = 1", (user_id,), fetchone=True)
    if not is_admin:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/unban <user_id>`", parse_mode="Markdown")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return

    db_execute("UPDATE users SET is_banned = 0, is_active = 1 WHERE user_id = ?", (target_id,), commit=True)
    try:
        await context.bot.send_message(chat_id=target_id, text="✅ Your ban has been lifted by an admin.")
    except Exception:
        pass
    await update.message.reply_text(f"✅ User `{target_id}` has been unbanned.", parse_mode="Markdown")

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = db_execute("SELECT is_admin FROM users WHERE user_id = ? AND is_admin = 1", (user_id,), fetchone=True)
    if not is_admin:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/kick <user_id>`", parse_mode="Markdown")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return

    db_execute("DELETE FROM users WHERE user_id = ?", (target_id,), commit=True)
    try:
        await context.bot.send_message(chat_id=target_id, text="👢 You have been kicked and removed from the bot.")
    except Exception:
        pass
    await update.message.reply_text(f"✅ User `{target_id}` has been kicked and deleted from database.", parse_mode="Markdown")

# --- BROADCASTING MESSAGES/MEDIA ---

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.effective_user.id
    
    user_record = db_execute("SELECT display_name, is_banned FROM users WHERE user_id = ?", (sender_id,), fetchone=True)
    if user_record and user_record[1] == 1:
        await update.message.reply_text("⛔ You are banned from using this bot.")
        return

    if not user_record:
        sender_name = f"User_{str(sender_id)[-4:]}"
        db_execute(
            "INSERT INTO users (user_id, display_name, message_count, is_active) "
            "VALUES (?, ?, 1, 1)",
            (sender_id, sender_name),
            commit=True,
        )
    else:
        sender_name = user_record[0]
        db_execute(
            "UPDATE users SET message_count = message_count + 1, is_active = 1 "
            "WHERE user_id = ?",
            (sender_id,),
            commit=True,
        )
    
    active_users = db_execute(
        "SELECT user_id FROM users WHERE is_active = 1 AND is_banned = 0", fetchall=True
    )
    
    if update.message.text:
        formatted_msg = f"*{sender_name}*: {update.message.text}"
        for (recipient_id,) in active_users:
            if recipient_id != sender_id:
                try:
                    await context.bot.send_message(
                        chat_id=recipient_id,
                        text=formatted_msg,
                        parse_mode="Markdown",
                    )
                except Exception:
                    db_execute(
                        "UPDATE users SET is_active = 0 WHERE user_id = ?",
                        (recipient_id,),
                        commit=True,
                    )
                    
    elif update.message.photo or update.message.video:
        if update.message.photo:
            media_type = "photo"
            file_id = update.message.photo[-1].file_id
        else:
            media_type = "video"
            file_id = update.message.video.file_id

        caption_text = update.message.caption if update.message.caption else ""
        
        db_execute(
            "INSERT INTO media_store (sender_id, sender_name, media_type, file_id, caption) VALUES (?, ?, ?, ?, ?)",
            (sender_id, sender_name, media_type, file_id, caption_text),
            commit=True,
        )
        
        caption = (
            f"*{sender_name}*: {caption_text}"
            if caption_text
            else f"*{sender_name}*"
        )
        for (recipient_id,) in active_users:
            if recipient_id != sender_id:
                try:
                    if media_type == "photo":
                        await context.bot.send_photo(
                            chat_id=recipient_id,
                            photo=file_id,
                            caption=caption,
                            parse_mode="Markdown",
                        )
                    elif media_type == "video":
                        await context.bot.send_video(
                            chat_id=recipient_id,
                            video=file_id,
                            caption=caption,
                            parse_mode="Markdown",
                        )
                except Exception:
                    db_execute(
                        "UPDATE users SET is_active = 0 WHERE user_id = ?",
                        (recipient_id,),
                        commit=True,
                    )

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("setmyname", set_name))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("syncmedia", sync_media))
    
    # Admin Handlers
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("abroadcast", admin_broadcast))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("kick", kick_user))
    
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.VIDEO) & ~filters.COMMAND & filters.ChatType.PRIVATE,
            broadcast_message,
        )
    )
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
