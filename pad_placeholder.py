"""
pad_placeholder.py
──────────────────────────────────────────────────────────────────────────────
Downloads the "No Image Available" placeholder, runs it through the same
_pad_image_bytes pipeline used for character card artwork, uploads the result
to a designated Discord channel once, and caches the CDN URL.

Usage in bot.py on_ready:
    from pad_placeholder import ensure_padded_placeholder
    await ensure_padded_placeholder(bot, LOG_CHANNEL_ID)

The padded URL is then available as:
    from pad_placeholder import PADDED_PLACEHOLDER_URL

ctc_card_embed.py and character_embeds.py both import this and fall back to
the original URL if it hasn't been set yet.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations
import os

# Filled in by ensure_padded_placeholder() at startup.
# Falls back to the raw URL if startup hasn't run yet.
_RAW_URL = (
"https://media.discordapp.net/attachments/1478560442723864737/1484845369644028036/no-image-vector-symbol-missing-available-icon-no-gallery-for-this-moment-placeholder.png?ex=69bfb583&is=69be6403&hm=dba7a6a9b8c853041ef330d0d4a8f0dde08b7909656244ff4f2ea657a8a74aad&=&format=webp&quality=lossless&width=673&height=673"
)

# Cache file so we only upload once across restarts
_CACHE_FILE = os.path.join(os.path.dirname(__file__), ".padded_placeholder_url")

PADDED_PLACEHOLDER_URL: str = _RAW_URL   # overwritten at startup


def get_placeholder_url() -> str:
    """Always returns the current placeholder URL (safe to call after on_ready)."""
    return PADDED_PLACEHOLDER_URL


def is_placeholder(url: str | None) -> bool:
    """Returns True if the URL is any known placeholder variant."""
    if not url:
        return True
    return (
        "no_image_padded" in url
        or "no-image-vector-symbol" in url
        or url.split("?")[0] == _RAW_URL.split("?")[0]
    )


def _load_cache() -> str | None:
    try:
        if os.path.exists(_CACHE_FILE):
            url = open(_CACHE_FILE).read().strip()
            if url.startswith("http"):
                return url
    except Exception:
        pass
    return None


async def ensure_padded_placeholder(bot, upload_channel_id: int) -> None:
    """
    Call once inside on_ready.  Downloads the placeholder, pads it, uploads
    it to upload_channel_id, and writes the CDN URL to a local cache file so
    subsequent restarts skip the upload.
    """
    global PADDED_PLACEHOLDER_URL

    # 1 — Use cached URL if we already uploaded before
    cached = _load_cache()
    if cached:
        PADDED_PLACEHOLDER_URL = cached
        print(f"✅ Placeholder already padded: {cached[:60]}…")
        return

    # 2 — Download the raw image
    try:
        import aiohttp, io
        async with aiohttp.ClientSession() as session:
            async with session.get(_RAW_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    print(f"⚠️  Could not download placeholder (HTTP {resp.status})")
                    return
                raw_bytes = await resp.read()
    except Exception as e:
        print(f"⚠️  Placeholder download failed: {e}")
        return

    # 3 — Pad the image (inline — avoids importing bot.py in an async context)
    try:
        from PIL import Image
        import io as _io

        TARGET_RATIO = 16 / 9
        MAX_PAD_FRAC = 0.25

        src = Image.open(_io.BytesIO(raw_bytes)).convert("RGBA")
        ow, oh = src.size

        if ow / oh >= TARGET_RATIO:
            padded = raw_bytes
        else:
            ideal_canvas_w = int(oh * TARGET_RATIO)
            max_pad_px     = int(ow * MAX_PAD_FRAC)
            actual_pad_px  = min((ideal_canvas_w - ow) // 2, max_pad_px)
            canvas_w       = ow + actual_pad_px * 2

            canvas = Image.new("RGBA", (canvas_w, oh), (0, 0, 0, 0))
            canvas.paste(src, (actual_pad_px, 0), src)

            out = _io.BytesIO()
            canvas.save(out, format="PNG", optimize=True)
            padded = out.getvalue()
    except Exception as e:
        print(f"⚠️  Placeholder padding failed: {e}")
        padded = raw_bytes

    # 4 — Upload to Discord to get a stable CDN URL
    try:
        import discord
        channel = bot.get_channel(upload_channel_id)
        if channel is None:
            channel = await bot.fetch_channel(upload_channel_id)
        msg = await channel.send(
            "*(placeholder image — do not delete)*",
            file=discord.File(io.BytesIO(padded), filename="no_image_padded.png"),
        )
        url = msg.attachments[0].url
        # Strip the expiry params for a cleaner permanent-ish URL
        url = url.split("?")[0]
    except Exception as e:
        print(f"⚠️  Placeholder upload failed: {e}")
        return

    # 5 — Cache and set globally
    try:
        open(_CACHE_FILE, "w").write(url)
    except Exception:
        pass

    PADDED_PLACEHOLDER_URL = url
    print(f"✅ Padded placeholder uploaded: {url}")