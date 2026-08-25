import os
import re
import asyncio
import tempfile
import threading
from pathlib import Path

import yt_dlp
from flask import Flask
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")


# =========================================================
# RENDER WEB SERVER
# =========================================================

web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "Social Downloader Bot is running! 🤖"


@web_app.route("/health")
def health():
    return "OK"


def run_web_server():
    port = int(os.environ.get("PORT", 10000))

    web_app.run(
        host="0.0.0.0",
        port=port,
        threaded=True
    )


# =========================================================
# URL DETECTION
# =========================================================

URL_PATTERN = re.compile(
    r"https?://[^\s<>]+",
    re.IGNORECASE
)


# =========================================================
# /START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    name = user.first_name if user and user.first_name else "Friend"

    text = (
        f"👋 <b>Hello {name}!</b>\n\n"
        "🤖 <b>Social Downloader Bot</b>\n\n"
        "🎬 Send me a public video/post URL and "
        "I'll try to download it for you.\n\n"
        "📌 <b>How to use:</b>\n"
        "1️⃣ Copy a public video/post link\n"
        "2️⃣ Send the link here\n"
        "3️⃣ Wait while I process it ⏳\n"
        "4️⃣ I'll send the downloaded video 📥\n\n"
        "⚠️ Private, login-required or unsupported links "
        "may not work."
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


# =========================================================
# DOWNLOAD MEDIA
# =========================================================

async def download_media(url: str, folder: str):

    output = str(
        Path(folder) / "%(title).80s.%(ext)s"
    )

    options = {
        "outtmpl": output,

        # Best available video + audio
        "format": "best[ext=mp4]/best",

        "merge_output_format": "mp4",

        # Playlist off
        "noplaylist": True,

        # Less console output
        "quiet": True,
        "no_warnings": True,

        # Safe filenames
        "restrictfilenames": True,

        # Telegram Bot API upload limit
        "max_filesize": 50 * 1024 * 1024,
    }

    def run():
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])

    await asyncio.to_thread(run)

    files = [
        p for p in Path(folder).glob("*")
        if p.is_file()
    ]

    return files[0] if files else None


# =========================================================
# HANDLE URL MESSAGE
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    match = URL_PATTERN.search(text)

    if not match:
        await update.message.reply_text(
            "🔗 <b>Please send a valid public video/post URL.</b>\n\n"
            "Example:\n"
            "<code>https://example.com/video</code>",
            parse_mode="HTML"
        )
        return

    # Remove Telegram/Chat punctuation after URL
    url = match.group(0).rstrip(".,!?;:)]}\"'")

    status = await update.message.reply_text(
        "⏳ <b>Processing your link...</b>\n\n"
        "Please wait while I download the media.",
        parse_mode="HTML"
    )

    try:

        # Show upload/download action
        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action=ChatAction.UPLOAD_VIDEO
            )
        except Exception:
            pass

        # Temporary folder
        with tempfile.TemporaryDirectory() as folder:

            await status.edit_text(
                "⬇️ <b>Downloading video...</b>\n\n"
                "Please wait...",
                parse_mode="HTML"
            )

            file_path = await download_media(
                url,
                folder
            )

            # Download failed
            if not file_path:

                await status.edit_text(
                    "❌ <b>Download failed.</b>\n\n"
                    "The link may be unsupported, private, "
                    "unavailable or temporarily blocked.\n\n"
                    "💡 Please try another public link.",
                    parse_mode="HTML"
                )

                return

            # Check size
            file_size = file_path.stat().st_size

            if file_size > 50 * 1024 * 1024:

                await status.edit_text(
                    "⚠️ <b>Video is too large.</b>\n\n"
                    "The downloaded file is larger than "
                    "Telegram's bot upload limit.",
                    parse_mode="HTML"
                )

                return

            await status.edit_text(
                "📤 <b>Uploading video...</b>\n\n"
                "Almost done! ⏳",
                parse_mode="HTML"
            )

            # Upload
            with open(file_path, "rb") as video:

                await update.message.reply_video(
                    video=video,
                    caption="✅ <b>Downloaded successfully!</b>\n\n"
                            "🤖 Social Downloader Bot",
                    parse_mode="HTML",
                    supports_streaming=True
                )

            # Delete status
            try:
                await status.delete()
            except Exception:
                pass

    except Exception as e:

        print("Download error:", repr(e))

        try:
            await status.edit_text(
                "❌ <b>Download failed.</b>\n\n"
                "The URL may be unsupported, private, "
                "unavailable or temporarily blocked.\n\n"
                "🔗 Please try another public link.",
                parse_mode="HTML"
            )
        except Exception:
            pass


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    print(
        "Bot error:",
        repr(context.error)
    )


# =========================================================
# MAIN BOT
# =========================================================

def main():

    print("🤖 Starting Telegram bot...")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # /start
    application.add_handler(
        CommandHandler("start", start)
    )

    # Text messages containing URLs
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    # Error handler
    application.add_error_handler(
        error_handler
    )

    print("✅ Telegram bot is running!")

    # Telegram long polling
    application.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# START EVERYTHING
# =========================================================

if __name__ == "__main__":

    # Start Render's HTTP server
    web_thread = threading.Thread(
        target=run_web_server,
        daemon=True
    )

    web_thread.start()

    print("🌐 Web server started.")

    # Start Telegram bot
    main()
