import discord
import random

from database import (
    get_story_by_character,
    get_user_id,
    is_favorite_character
)


# =====================================================
# INTERNAL HELPER (VERY IMPORTANT)
# =====================================================

CARD_COLORS = [
    discord.Color.from_rgb(186, 104, 200),  # soft purple
    discord.Color.from_rgb(149, 117, 205),  # lavender
    discord.Color.from_rgb(121, 134, 203),  # indigo
    discord.Color.from_rgb(100, 181, 246),  # sky blue
    discord.Color.from_rgb(77, 182, 172),   # teal
    discord.Color.from_rgb(129, 199, 132),  # soft green
    discord.Color.from_rgb(244, 143, 177),  # pink glow
    discord.Color.from_rgb(179, 157, 219),  # pastel violet
    discord.Color.from_rgb(140, 158, 255),  # dreamy blue
    discord.Color.from_rgb(255, 138, 128),  # coral
    discord.Color.from_rgb(240, 98, 146),   # rose
    discord.Color.from_rgb(66, 165, 245),   # bright blue
    discord.Color.from_rgb(38, 166, 154),   # aqua
    discord.Color.from_rgb(171, 71, 188),   # orchid
]

# =====================================================
# GLOBAL CHARACTER EMBED HELPER
# =====================================================


def parse_character_tuple(character):
    """
    Supports BOTH formats:

    OLD:
    (id, name, gender, personality, image_url)

    NEW:
    (id, story_id, name, gender, personality, image_url)
    """

    if len(character) == 5:
        cid, name, gender, personality, image_url = character
        story_id = None

    elif len(character) == 6:
        cid, story_id, name, gender, personality, image_url = character

    else:
        raise ValueError(f"Unexpected character tuple: {character}")

    return cid, story_id, name, gender, personality, image_url


# =====================================================
# LIST EMBED
# =====================================================
def build_character_list_embed(characters):

    embed = discord.Embed(
        title="🧍 Characters",
        color=discord.Color.blurple()
    )

    for i, c in enumerate(characters, start=1):

        _, _, name, gender, personality, _ = parse_character_tuple(c)

        preview = (
            personality[:120] + "..."
            if personality else "No personality."
        )

        embed.add_field(
            name=f"{i}. {name}",
            value=f"⚧️ {gender or 'Unknown'}\n📝 *{preview}*",
            inline=False
        )

    return embed


# =====================================================
# DETAIL EMBED
# =====================================================
def build_character_detail_embed(character):

    _, _, name, gender, personality, image = parse_character_tuple(character)

    embed = discord.Embed(
        title=f"🧍 {name}",
        color=discord.Color.dark_teal()
    )

    embed.description = (
        f"⚧️ **Gender:** {gender or 'Unknown'}\n\n"
        f"🧠 **Personality:**\n{personality or 'No description.'}"
    )

    if image and image.startswith("http"):
        embed.set_image(url=image)
    else:
        try:
            from pad_placeholder import PADDED_PLACEHOLDER_URL
            embed.set_image(url=PADDED_PLACEHOLDER_URL)
        except ImportError:
            pass

    return embed

# =====================================================
# CHARACTER UNPACK HELPER (NEW)
# =====================================================

def unpack_character(character):

    # base structure (guarantees every key exists)
    char = {
        "id": None,
        "story_id": None,
        "name": None,
        "gender": None,
        "personality": None,
        "image_url": None,
        "quote": None,
        "age": None,
        "height": None,
        "physical_features": None,
        "relationships": None,
        "lore": None,
        "music_url": None,
        "species": None,
    }

    # ---------------------------
    # dict rows (modern DB)
    # ---------------------------
    if isinstance(character, dict):

        for key in char:
            char[key] = character.get(key)

        # Normalize blank image URLs to None so embeds fall back to placeholder
        for field in ("image_url", "shiny_image_url"):
            if char.get(field) == "":
                char[field] = None

        return char

    # ---------------------------
    # tuple rows (legacy DB)
    # ---------------------------
    if isinstance(character, (tuple, list)):

        try:
            char["id"] = character[0]
            char["story_id"] = character[1]
            char["name"] = character[2]
            char["gender"] = character[3]
            char["personality"] = character[4]
            char["image_url"] = character[5]
            char["quote"] = character[6] if len(character) > 6 else None
            char["age"] = character[7] if len(character) > 7 else None
            char["height"] = character[8] if len(character) > 8 else None
            char["physical_features"] = character[9] if len(character) > 9 else None
            char["relationships"] = character[10] if len(character) > 10 else None
            char["lore"] = character[11] if len(character) > 11 else None
            char["music_url"] = character[12] if len(character) > 12 else None
            char["species"] = character[13] if len(character) > 13 else None
        except Exception:
            pass

        # Normalize blank image URLs to None so embeds fall back to placeholder
        if char.get("image_url") == "":
            char["image_url"] = None

        return char

    return char

# =====================================================
# STORY SLIDESHOW CARD (FANCY VERSION)
# =====================================================

def build_character_card(
    character,
    viewer=None,
    user_id=None,
    index=1,
    total=1,
    story_title=None,
    builder_mode=False
):
    """
    Character tuple expected:
    (id, name, gender, personality, image_url)
    """

    # =====================================================
    # SAFE UNPACK (supports older/newer DB layouts)
    # =====================================================

    # Possible tuple shapes:
    # (id, name, gender, personality, image_url)
    # (id, name, gender, personality, image_url, quote)
    # (id, story_id, name, gender, personality, image_url, quote)

    # SAFE FLEXIBLE UNPACK (future-proof)
    char = unpack_character(character)

    cid = char["id"]
    name = char["name"]
    gender = char["gender"]
    personality = char["personality"]
    image_url = char["image_url"]
    quote = char["quote"]
    age = char.get("age")
    height = char.get("height")
    physical = char.get("physical_features")
    relationships = char.get("relationships")
    music_url = char.get("music_url")
    species = char.get("species")

    # =====================================================
# FAVORITE CHECK
# =====================================================

    is_favorite = False

    try:
        if user_id:
            is_favorite = is_favorite_character(user_id, cid)
        elif viewer:
            uid = get_user_id(str(viewer.id))
            if uid:
                is_favorite = is_favorite_character(uid, cid)
    except:
        pass


    # =====================================================
    # SMART DEFAULTS (unfinished card look)
    # =====================================================

    gender = gender or "Unknown"
    personality = personality or (
        "✨ Personality not written yet.\n"
        "Use `/charbuild` to build your character!"
    )
    quote = quote or "💬 No quote yet — give them a voice with `/charbuild`!"

    # =====================================================
    # CARD STYLE (finished vs unfinished)
    # =====================================================

    has_image = bool(image_url)

    if builder_mode:
        embed = discord.Embed(
            title=f"🛠 {name}",
            color=discord.Color.blurple()
        )
    else:
        if is_favorite:
            card_title = f"✨ ★ {name.upper()} ★ ✨"
            card_color = discord.Color.gold()
        elif has_image:
            card_title = f"✧･ﾟ: ✦ {name.upper()} ✦ ✨ :･ﾟ✧"
            card_color = random.choice(CARD_COLORS)
        else:
            card_title = f"✧･ﾟ: ✦ {name.upper()} ✦ :･ﾟ✧"
            card_color = discord.Color.purple()

        embed = discord.Embed(
            title=card_title,
            color=card_color
        )

        if is_favorite:
            embed.description = "⋆｡‧˚ʚ 💛 ɞ˚‧｡⋆  **Favorited Character**  ⋆｡‧˚ʚ 💛 ɞ˚‧｡⋆"
        else:
            embed.description = "✦ ━━━━━━━━━━━━━━━━━━ ✦"

    # ---------- STORY HEADER ----------
    if story_title:
        embed.description = (
            f"✦ **{story_title}** ✦\n"
            f"━━━━━━━━━━━━━━━━━━"
        )

    # ---------- CHARACTER PROFILE ----------
    if not builder_mode:

        # ─────────────────────────────
        # DIVIDER — gold sparkle for favs, standard otherwise
        # ─────────────────────────────
        divider = "✨ ━━━━━━━━━━━━━━━ ✨" if is_favorite else "✦ ━━━━━━━━━━━━━━━━━ ✦"

        # ─────────────────────────────
        # PROFILE HEADER
        # ─────────────────────────────
        embed.add_field(
            name="",
            value=(
                f"♢ **Gender**  ·  {gender}\n"
                f"♢ **Age**  ·  {age or 'Unknown'}\n"
                f"♢ **Height**  ·  {height or 'Unknown'}\n"
                + (f"♢ **Species**  ·  {species}\n" if species else "")
                + f"\n{divider}"
            ),
            inline=False
        )

        # ─────────────────────────────
        # RELATIONSHIPS
        # ─────────────────────────────
        relationships = relationships

        if relationships:
            rel_lines = "\n".join(f"> {line}" if line.strip() else ">" for line in relationships.splitlines())
            embed.add_field(
                name="💞 𝐑𝐄𝐋𝐀𝐓𝐈𝐎𝐍𝐒𝐇𝐈𝐏𝐒",
                value=rel_lines,
                inline=False
            )

        # ─────────────────────────────
        # PHYSICAL FEATURES
        # ─────────────────────────────
        physical = physical

        if physical:
            phys_lines = "\n".join(f"> {line}" if line.strip() else ">" for line in physical.splitlines())
            embed.add_field(
                name="✨ 𝐏𝐇𝐘𝐒𝐈𝐂𝐀𝐋 𝐅𝐄𝐀𝐓𝐔𝐑𝐄𝐒",
                value=phys_lines,
                inline=False
            )

        # ─────────────────────────────
        # PERSONALITY
        # ─────────────────────────────
        bio_lines = "\n".join(f"> {line}" if line.strip() else "> \u200b" for line in personality.splitlines())
        embed.add_field(
            name="📜 𝐁𝐈𝐎𝐆𝐑𝐀𝐏𝐇𝐘",
            value=bio_lines,
            inline=False
        )

        # ─────────────────────────────
        # THEME SONG
        # ─────────────────────────────
        if music_url:
            embed.add_field(
                name="🎵 𝐓𝐇𝐄𝐌𝐄 𝐒𝐎𝐍𝐆",
                value=f"[♪ Listen Here]({music_url})",
                inline=False
            )

    # ---------- IMAGE ----------
    try:
        from pad_placeholder import PADDED_PLACEHOLDER_URL as _NO_IMAGE
    except ImportError:
        _NO_IMAGE = (
            "https://cdn.discordapp.com/attachments/1478560442723864737/1484845369644028036/"
            "no-image-vector-symbol-missing-available-icon-no-gallery-for-this-moment-placeholder.png"
            "?ex=69bfb583&is=69be6403&hm=dba7a6a9b8c853041ef330d0d4a8f0dde08b7909656244ff4f2ea657a8a74aad&"
        )
    if image_url:
        if builder_mode:
            embed.set_thumbnail(url=image_url)
        else:
            embed.set_image(url=image_url)
    else:
        if not builder_mode:
            embed.set_image(url=_NO_IMAGE)

    # -------------------------------------------------
    # CHARACTER IMAGE (THUMBNAIL)
    # -------------------------------------------------

    # -------------------------------------------------
    # STORY COVER (THUMBNAIL)
    # -------------------------------------------------

    story = get_story_by_character(character["id"])

    if story:

        cover_url = story["cover_url"]

        if cover_url:
            embed.set_thumbnail(url=cover_url)

    # ---------- OWNER COUNT ----------
    try:
        from database import get_card_owner_count
        owner_count = get_card_owner_count(cid)
        if owner_count > 0:
            owner_label = "collector" if owner_count == 1 else "collectors"
            own_verb    = "owns" if owner_count == 1 else "own"
            embed.add_field(
                name="💎 𝐂𝐓𝐂 𝐂𝐀𝐑𝐃",
                value=f"-# **{owner_count} {owner_label} {own_verb} this card**",
                inline=False
            )
    except Exception:
        pass

    # ---------- FOOTER ----------
    if is_favorite:
        fav_tag = "💛 Favorited  ✦  "
    else:
        fav_tag = ""

    if quote:
        embed.set_footer(
            text=f"{fav_tag}✦ {quote} ✦\n ✦ Character Card {index}/{total} ✦"
        )
    else:
        embed.set_footer(
            text=f"{fav_tag}✦ Character Card {index}/{total} ✦"
        )

    return embed