import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, Message

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
API_BASE_URL = os.getenv("TERABOX_API_URL", "").rstrip("/")
MAX_DOWNLOAD_MB = int(os.getenv("MAX_DOWNLOAD_MB", "45"))
MAX_DOWNLOAD_BYTES = MAX_DOWNLOAD_MB * 1024 * 1024
DOWNLOAD_TIMEOUT = float(os.getenv("DOWNLOAD_TIMEOUT", "180"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it in Railway Variables.")
if not API_BASE_URL:
    raise RuntimeError("TERABOX_API_URL is missing. Add your deployed API base URL in Railway Variables.")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("terabox-bot")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
TERABOX_HOSTS = {
    "terabox.com", "www.terabox.com", "1024terabox.com", "www.1024terabox.com",
    "teraboxapp.com", "www.teraboxapp.com", "terabox.app", "www.terabox.app",
    "teraboxlink.com", "www.teraboxlink.com",
}

def get_supported_link(text: str) -> str | None:
    match = re.search(r"https?://[^\s<>]+", text or "")
    if not match:
        return None
    url = match.group(0).rstrip(".,);]")
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in TERABOX_HOSTS:
        return None
    return url

@dp.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        "👋 Welcome!\n\nSend a public TeraBox share link and I'll try to fetch the video.\n"
        "Only send links you have permission to access. Large files may exceed the current upload limit."
    )

@dp.message(F.text)
async def handle_link(message: Message) -> None:
    url = get_supported_link(message.text or "")
    if not url:
        await message.answer("Please send a supported HTTPS TeraBox share link.")
        return

    status = await message.answer("⏳ Processing your TeraBox link…")
    temp_path: Path | None = None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{API_BASE_URL}/extract", json={"url": url})
            if response.status_code >= 400:
                try:
                    detail = response.json().get("detail", "Extraction failed.")
                except Exception:
                    detail = "Extraction failed."
                await status.edit_text(f"❌ {str(detail)[:700]}")
                return
            info = response.json()

        download_url = info.get("download_url")
        filename = str(info.get("filename") or "video.mp4")
        # Avoid accepting local/private URLs or unexpected protocols from an extractor.
        parsed = urlparse(download_url or "")
        if parsed.scheme != "https" or not parsed.hostname:
            await status.edit_text("❌ The extraction service returned an invalid download URL.")
            return

        safe_name = Path(filename).name[:120] or "video.mp4"
        with tempfile.NamedTemporaryFile(prefix="tb_", suffix=Path(safe_name).suffix or ".mp4", delete=False) as tmp:
            temp_path = Path(tmp.name)

        await status.edit_text("⬇️ Downloading video…")
        downloaded = 0
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            async with client.stream("GET", download_url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" in content_type:
                    raise ValueError("The download URL returned a webpage, not a video file.")
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
                    raise ValueError(f"Video exceeds this bot's configured {MAX_DOWNLOAD_MB} MB limit.")
                with temp_path.open("wb") as file:
                    async for chunk in response.aiter_bytes(1024 * 256):
                        downloaded += len(chunk)
                        if downloaded > MAX_DOWNLOAD_BYTES:
                            raise ValueError(f"Video exceeds this bot's configured {MAX_DOWNLOAD_MB} MB limit.")
                        file.write(chunk)

        if downloaded == 0:
            raise ValueError("The downloaded file was empty.")

        await status.edit_text("📤 Uploading video to Telegram…")
        await message.answer_video(
            video=FSInputFile(temp_path, filename=safe_name),
            caption=f"✅ {safe_name}",
            supports_streaming=True,
        )
        await status.delete()
    except Exception as exc:
        log.exception("Link processing failed")
        try:
            await status.edit_text(f"❌ Couldn't send this video: {str(exc)[:500]}")
        except Exception:
            pass
    finally:
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                log.warning("Could not remove temporary file")

async def main() -> None:
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
