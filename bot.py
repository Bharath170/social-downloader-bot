import os
import re
import asyncio
import tempfile
from pathlib import Path

import yt_dlp
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

URL_PATTERN = re.compile(
    r"https?://[^\s]+",
    re.IGNORECASE
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.first_name or "Friend"

    text = (
        f"👋 <b>Hello {name}!</b>\n\n"
        "🎬 <b>Social Downloader Bot</b>\n\n"
        "Send me a <b>public video/post URL</b> and I'll try to download it.\n\n"
        "✨ <b>How to use:</b>\n"
        "1️⃣ Copy a public video/post link\n"
        "2️⃣ Send the link here\n"
        "3️⃣ Wait while I process it\n\n"
        "⚠️ Private or login-required links are not supported."
    )

    await update.message.reply_text(text, parse_mode="HTML")


async def download_media(url: str, folder: str):
    output = str(Path(folder) / "%(title).80s.%(ext)s")

    options = {
        "outtmpl": output,
        "format": "best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "max_filesize": 50 * 1024 * 1024,
    }

    def run():
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])

    await asyncio.to_thread(run)

    files = list(Path(folder).glob("*"))
    files = [f for f in files if f.is_file()]

    return files[0] if files else None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    match = URL_PATTERN.search(text)

    if not match:
        await update.message.reply_text(
            "🔗 Please send a valid public video/post URL."
        )
        return

    url = match.group(0).rstrip(".,!?)]}")

    status = await update.message.reply_text(
        "⏳ <b>Processing your link...</b>\n\n"
        "Please wait.",
        parse_mode="HTML",
    )

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.UPLOAD_VIDEO,
    )

    try:
        with tempfile.TemporaryDirectory() as folder:
            file_path = await download_media(url, folder)

            if not file_path:
                await status.edit_text(
                    "❌ I couldn't download media from this link.\n\n"
                    "Make sure it is a public supported URL."
                )
                return

            if file_path.stat().st_size > 50 * 1024 * 1024:
                await status.edit_text(
                    "⚠️ The downloaded file is larger than Telegram's "
                    "Bot API upload limit."
                )
                return

            await status.edit_text("📤 Uploading your video...")

            with open(file_path, "rb") as video:
                await update.message.reply_video(
                    video=video,
                    caption="✅ Downloaded successfully!",
                    supports_streaming=True,
                )

            await status.delete()

    except Exception as e:
        print("Download error:", repr(e))

        try:
            await status.edit_text(
                "❌ <b>Download failed.</b>\n\n"
                "The URL may be unsupported, private, unavailable, "
                "or temporarily blocked.",
                parse_mode="HTML",
            )
        except Exception:
            pass


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is missing.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
