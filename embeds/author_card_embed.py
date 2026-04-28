"""
author_card_embed.py
──────────────────────────────────────────────────────────────────────────────
Author Profile Card embed — CTC-style layout for author profile cards.

Public API:
    build_author_card_embed(author, viewer_uid, *, index=1, total=1) → discord.Embed
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import random
import discord

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


def _author_color(author_id: int) -> discord.Color:
    rng = random.Random(author_id + 20000)
    r, g, b = rng.choice(_PALETTE)
    return discord.Color.from_rgb(r, g, b)


def _div() -> str:
    return "── ✦ ──────────────────── ✦ ──"


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


def build_author_card_embed(
    author:     dict,
    viewer_uid: int,
    *,
    index: int = 1,
    total: int = 1,
) -> discord.Embed:
    """Build a CTC-style author profile card embed. Returns a discord.Embed."""
    author_id   = author.get("id", 0)
    name        = author.get("name") or author.get("username") or "Unknown Author"
    bio         = author.get("bio") or ""
    pronouns    = author.get("pronouns") or ""
    fav_pokemon = author.get("favorite_pokemon") or ""
    hobbies     = author.get("hobbies") or ""
    fun_fact    = author.get("fun_fact") or ""
    story_count = author.get("story_count") or 0
    image_url   = author.get("image_url") or _get_placeholder()

    # Fetch story titles for this author
    story_list  = ""
    try:
        from database import get_connection
        conn = get_connection()
        rows = conn.execute(
            "SELECT title FROM stories WHERE user_id=? AND (is_dummy=0 OR is_dummy IS NULL) ORDER BY title",
            (author_id,)
        ).fetchall()
        conn.close()
        if rows:
            story_list = "\n".join(f"· {r['title']}" for r in rows)
    except Exception:
        pass

    try:
        from database import get_author_card_owner_count
        owner_cnt = get_author_card_owner_count(author_id)
    except Exception:
        owner_cnt = 0

    color = _author_color(author_id)
    div   = _div()

    title     = f"✧･ﾟ: ✦  {name.upper()}  ✦ :･ﾟ✧"
    name_line = f"✍️ **{name}**"
    if pronouns:
        name_line += f"  ·  *{pronouns}*"

    desc_lines = [
        f"-# 📝 **AUTHOR PROFILE CARD**",
        name_line,
        div,
    ]

    embed = discord.Embed(
        title       = title,
        description = "\n".join(desc_lines),
        color       = color,
    )

    if image_url and image_url.startswith("http"):
        embed.set_image(url=image_url)

    # ── Bio ───────────────────────────────────────────────────────────────────
    if bio:
        embed.add_field(name="📝 𝐁𝐈𝐎", value=bio[:1024], inline=False)
    else:
        embed.add_field(
            name  = "📝 𝐁𝐈𝐎",
            value = f"*{name} hasn't written a bio yet.*",
            inline=False,
        )

    embed.add_field(name="\u200b", value=div, inline=False)

    # ── Fun facts row ─────────────────────────────────────────────────────────
    if fav_pokemon:
        embed.add_field(name="🐾 Fav Pokémon", value=fav_pokemon[:256], inline=True)
    if hobbies:
        embed.add_field(name="🎨 Hobbies", value=hobbies[:256], inline=True)
    if fun_fact:
        embed.add_field(name="💫 Fun Fact", value=fun_fact[:256], inline=True)

    # ── Stories ───────────────────────────────────────────────────────────────
    embed.add_field(name="\u200b", value=div, inline=False)
    stories_val = story_list if story_list else f"*{story_count} {'story' if story_count == 1 else 'stories'} in the library*"
    embed.add_field(
        name  = f"📚 𝐒𝐓𝐎𝐑𝐈𝐄𝐒  ·  {story_count}",
        value = stories_val[:1024],
        inline= False,
    )

    # ── Card info ─────────────────────────────────────────────────────────────
    embed.add_field(name="\u200b", value=div, inline=False)
    embed.add_field(
        name  = "✍️ 𝐀𝐔𝐓𝐇𝐎𝐑 𝐂𝐀𝐑𝐃",
        value = (
            f"-# 🃏 Author card  ·  **{index}** of **{total}**\n"
            f"-# 👥 {'Uncollected — be the first!' if owner_cnt == 0 else f'{owner_cnt} collector{'' if owner_cnt == 1 else 's'}'}"
        ),
        inline=True,
    )

    embed.set_footer(text=f"Author Profile  ·  {name}")
    return embed
