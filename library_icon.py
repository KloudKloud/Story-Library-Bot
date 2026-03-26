"""
library_icon.py
───────────────────────────────────────────────────────────────────────────
Uploads library.png to Discord once, caches the CDN URL, and exposes it as
get_library_icon_url().  This avoids sending library.png as a file attachment
on every /library command, which caused it to appear visibly on story detail
embeds when the message was edited.

Call ensure_library_icon(bot, channel_id) once inside on_ready.
"""

from __future__ import annotations
import os

_CACHE_FILE = os.path.join(os.path.dirname(__file__), ".library_icon_url")
_LIBRARY_ICON_URL: str | None = None


def get_library_icon_url() -> str | None:
    return _LIBRARY_ICON_URL


def _load_cache() -> str | None:
    try:
        if os.path.exists(_CACHE_FILE):
            url = open(_CACHE_FILE).read().strip()
            if url.startswith("http"):
                return url
    except Exception:
        pass
    return None


async def ensure_library_icon(bot, upload_channel_id: int) -> None:
    global _LIBRARY_ICON_URL

    cached = _load_cache()
    if cached:
        _LIBRARY_ICON_URL = cached
        print(f"✅ Library icon cached: {cached[:60]}…")
        return

    try:
        import discord
        channel = bot.get_channel(upload_channel_id)
        if channel is None:
            channel = await bot.fetch_channel(upload_channel_id)
        msg = await channel.send(
            "*(library icon — do not delete)*",
            file=discord.File("library.png", filename="library.png"),
        )
        url = msg.attachments[0].url.split("?")[0]
    except Exception as e:
        print(f"⚠️  Library icon upload failed: {e}")
        return

    try:
        open(_CACHE_FILE, "w").write(url)
    except Exception:
        pass

    _LIBRARY_ICON_URL = url
    print(f"✅ Library icon uploaded: {url}")
