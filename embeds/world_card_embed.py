"""
world_card_embed.py
──────────────────────────────────────────────────────────────────────────────
World / Support card embed  —  CTC-style layout for world-building cards.

These are "support cards" (locations, artifacts, organizations, concepts, etc.)
as opposed to the character cards.

Public API:
    build_world_card_embed(world, viewer_uid, *, ...) → discord.Embed
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import random
from typing import Optional

import discord


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_placeholder() -> str:
    try:
        from pad_placeholder import PADDED_PLACEHOLDER_URL
        return PADDED_PLACEHOLDER_URL
    except ImportError:
        return (
            "https://cdn.discordapp.com/attachments/1478560442723864737/1484845369644028036/"
            "no-image-vector-symbol-missing-available-icon-no-gallery-for-this-moment-placeholder.png"
            "?ex=69bfb583&is=69be6403&hm=dba7a6a9b8c853041ef330d0d4a8f0dde08b7909656244ff4f2ea657a8a74aad&"
        )


# Same palette as ctc_card_embed — no gold/amber/orange/yellow
_PALETTE = [
    (186, 104, 200), (149, 117, 205), (121, 134, 203), (100, 181, 246),
    ( 77, 182, 172), (129, 199, 132), (244, 143, 177), (179, 157, 219),
    (140, 158, 255), (240,  98, 146), ( 66, 165, 245), ( 38, 166, 154),
    (171,  71, 188), ( 80, 200, 230), (160, 120, 255), (100, 220, 180),
    (220, 100, 180), ( 90, 180, 255), (130, 220, 120), (200,  80, 130),
    (255,  80, 200), ( 80, 160, 255), (170,  60, 210), ( 60, 200, 210),
    (120, 220, 120), ( 80, 210,  90), ( 50, 190, 255), (120,  80, 255),
    (200, 150, 255), ( 70, 220, 150), (150, 100, 255), (100, 255, 200),
    (255,  90, 150), ( 90, 200, 100), (100, 150, 255), (160, 255, 180),
    (210, 100, 255), ( 80, 230, 200), (180, 100, 255), ( 60, 170, 240),
    (255, 120, 180), (100, 200, 255), ( 80, 255, 180), (200,  80, 200),
    (120, 255, 210), ( 60, 140, 255), (255, 100, 200), (140, 255, 160),
    (190,  80, 255), ( 70, 210, 190),
]

_TYPE_EMOJIS = {
    "location":     "🗺️",
    "organization": "🏛️",
    "org":          "🏛️",
    "artifact":     "⚔️",
    "concept":      "📖",
    "realm":        "🌌",
    "world":        "🌍",
    "phenomenon":   "🧪",
    "event":        "🌟",
    "creature":     "🐉",
    "faction":      "⚜️",
    "magic":        "🔮",
    "item":         "💎",
    "place":        "📍",
}


def _world_color(world_id: int, shiny: bool) -> discord.Color:
    if shiny:
        return discord.Color.gold()
    rng = random.Random(world_id + 10000)  # offset to differ from char palette
    r, g, b = rng.choice(_PALETTE)
    return discord.Color.from_rgb(r, g, b)


def _type_emoji(world_type: str | None) -> str:
    if not world_type:
        return "🌍"
    return _TYPE_EMOJIS.get(world_type.lower().strip(), "🌍")


def _div() -> str:
    return "── ✦ ──────────────────── ✦ ──"


# ─────────────────────────────────────────────────────────────────────────────
# Core embed builder
# ─────────────────────────────────────────────────────────────────────────────

def build_world_card_embed(
    world:    dict,
    viewer_uid: int,
    *,
    shiny:   bool = False,
    index:   int  = 1,
    total:   int  = 1,
) -> discord.Embed:
    """
    Build a CTC-style world/support card embed.
    Returns a discord.Embed.
    """
    world_id   = world.get("id", 0)
    name       = world.get("name") or "Unknown"
    story      = world.get("story_title") or world.get("story") or "Unknown Story"
    author     = world.get("author") or "Unknown Author"
    world_type = world.get("world_type") or "World Card"
    description = world.get("description")
    lore        = world.get("lore")
    quote       = world.get("quote")
    music_url   = world.get("music_url")

    image_url = world.get("image_url") or _get_placeholder()
    if shiny:
        shiny_img = world.get("shiny_image_url")
        if shiny_img and shiny_img.startswith("http"):
            image_url = shiny_img

    cover_url = world.get("cover_url")

    color      = _world_color(world_id, shiny)
    type_emoji = _type_emoji(world_type)
    div        = _div()

    # ── Title ─────────────────────────────────────────────────────────────────
    if shiny:
        title = f"✨ ★  {name.upper()}  ★ ✨"
    else:
        title = f"✧･ﾟ: ✦  {name.upper()}  ✦ :･ﾟ✧"

    # ── Description block ─────────────────────────────────────────────────────
    desc_lines = []
    if shiny:
        desc_lines.append("⋆｡‧˚ʚ ✨ ɞ˚‧｡⋆  **✦ SHINY CARD ✦**  ⋆｡‧˚ʚ ✨ ɞ˚‧｡⋆")
    desc_lines.append(f"-# {type_emoji} **{world_type.upper()}**")
    desc_lines.append(f"⭐ **{story}**  ·  *by {author}* ⭐")
    desc_lines.append(div)

    embed = discord.Embed(title=title, description="\n".join(desc_lines), color=color)
    embed.set_image(url=image_url)

    if cover_url and cover_url.startswith("http"):
        embed.set_thumbnail(url=cover_url)

    # ── About / Description ───────────────────────────────────────────────────
    embed.add_field(name="\u200b", value=div, inline=False)
    if description:
        desc_display = "\n".join(
            f"> {line}" if line.strip() else "> \u200b"
            for line in description.splitlines()
        )
        desc_display = desc_display[:1024]
    else:
        desc_display = f"> *No description has been written for **{name}** yet.*"
    embed.add_field(name=f"{type_emoji} 𝐀𝐁𝐎𝐔𝐓", value=desc_display, inline=False)

    # ── Lore (NOT spoilered — world lore is public) ───────────────────────────
    embed.add_field(name="\u200b", value=div, inline=False)
    if lore:
        lore_display = f"*{lore[:1018]}*"
    else:
        lore_display = (
            f"*No lore has been written for **{name}** yet. "
            "The history of this world is still being uncovered…*"
        )
    embed.add_field(name="❋ ❋ ❋  𝐋𝐎𝐑𝐄", value=lore_display, inline=False)

    # ── Outro ─────────────────────────────────────────────────────────────────
    embed.add_field(name="\u200b", value=div, inline=False)
    embed.add_field(
        name  = "🎵 𝐓𝐇𝐄𝐌𝐄 𝐒𝐎𝐍𝐆",
        value = f"[♪ Listen Here]({music_url})" if music_url else "-# *No theme set*",
        inline=True,
    )
    embed.add_field(
        name  = "🌍 𝐒𝐔𝐏𝐏𝐎𝐑𝐓 𝐂𝐀𝐑𝐃",
        value = f"-# 🃏 World card  ·  **{index}** of **{total}**",
        inline=True,
    )

    # ── Footer ────────────────────────────────────────────────────────────────
    if quote:
        embed.set_footer(text=f'"{quote[:200]}"')
    else:
        embed.set_footer(text=f"World Card  ·  {story}")

    return embed
