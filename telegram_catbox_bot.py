"""
Telegram -> Catbox.moe uploader bot

Install:
    python -m pip install python-telegram-bot requests

Set environment variables (use a NEW token from @BotFather):
Windows CMD:
    set TELEGRAM_BOT_TOKEN=YOUR_NEW_TOKEN
    set OWNER_ID=8453512335
    python telegram_catbox_bot.py

macOS/Linux:
    export TELEGRAM_BOT_TOKEN='YOUR_NEW_TOKEN'
    export OWNER_ID='8453512335'
    python telegram_catbox_bot.py

Security: revoke any token previously pasted into a chat with @BotFather (/revoke).
Catbox URLs may be publicly accessible; don't upload private/sensitive media.
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

CATBOX_API = "https://catbox.moe/user/api.php"
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
OWNER_ID = int(os.environ.get("OWNER_ID", "8453512335"))
MAX_UPLOAD_BYTES = 200 * 1024 * 1024

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if user.id != OWNER_ID:
        await msg.reply_text("यह bot निजी है और केवल owner इस्तेमाल कर सकता है।")
        return
    await msg.reply_text(
        "नमस्ते! 👋\n\nअब इसी chat में फोटो या वीडियो सामान्य तरीके से भेजें। "
        "मैं उसे Catbox.moe पर अपलोड करके उसका URL यहीं भेज दूँगा।"
    )


def upload_to_catbox(file_path: str, upload_name: str) -> str:
    with open(file_path, "rb") as media:
        response = requests.post(
            CATBOX_API,
            data={"reqtype": "fileupload"},
            files={"fileToUpload": (upload_name, media)},
            timeout=(20, 600),
        )
    response.raise_for_status()
    result = response.text.strip()
    if not result.startswith("https://files.catbox.moe/"):
        raise RuntimeError(f"Catbox ने URL नहीं लौटाया: {result[:400]}")
    return result


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if user.id != OWNER_ID:
        await msg.reply_text("यह bot निजी है और केवल owner इस्तेमाल कर सकता है।")
        return

    media_obj = None
    filename = "media.bin"
    if msg.photo:
        media_obj = msg.photo[-1]
        filename = "telegram_photo.jpg"
    elif msg.video:
        media_obj = msg.video
        filename = msg.video.file_name or "telegram_video.mp4"
    elif msg.animation:
        media_obj = msg.animation
        filename = msg.animation.file_name or "telegram_animation.mp4"
    elif msg.document:
        mime = (msg.document.mime_type or "").lower()
        if not (mime.startswith("image/") or mime.startswith("video/")):
            await msg.reply_text("कृपया फोटो या वीडियो भेजें।")
            return
        media_obj = msg.document
        filename = msg.document.file_name or "uploaded_media"

    if media_obj is None:
        return
    if media_obj.file_size and media_obj.file_size > MAX_UPLOAD_BYTES:
        await msg.reply_text("यह फाइल 200 MB से बड़ी है। कृपया छोटी फाइल भेजें।")
        return

    status = await msg.reply_text("⏳ डाउनलोड और Catbox पर अपलोड हो रहा है…")
    temp_path = None
    try:
        telegram_file = await media_obj.get_file()
        suffix = Path(filename).suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp_path = temp.name

        await telegram_file.download_to_drive(custom_path=temp_path)
        if os.path.getsize(temp_path) > MAX_UPLOAD_BYTES:
            await status.edit_text("यह फाइल 200 MB से बड़ी है। कृपया छोटी फाइल भेजें।")
            return

        url = await asyncio.to_thread(upload_to_catbox, temp_path, Path(filename).name)
        await status.edit_text(f"✅ अपलोड पूरा!\n\n{url}")
    except Exception as exc:
        logger.exception("Upload failed")
        details = str(exc).replace(BOT_TOKEN, "[hidden]") if BOT_TOKEN else str(exc)
        await status.edit_text(
            "❌ अपलोड नहीं हो पाया। इंटरनेट या फाइल की सीमा जाँचकर फिर कोशिश करें।\n"
            f"विवरण: {details[:400]}"
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN सेट नहीं है। @BotFather से नया token बनाकर environment variable में डालें।"
        )
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(
            filters.PHOTO
            | filters.VIDEO
            | filters.ANIMATION
            | filters.Document.IMAGE
            | filters.Document.VIDEO,
            handle_media,
        )
    )
    logger.info("Bot starting")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
