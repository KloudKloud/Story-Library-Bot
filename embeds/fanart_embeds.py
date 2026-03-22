import discord
import random


# ═══════════════════════════════════════════════════════════════
# PALETTE & DECORATION POOLS
# ═══════════════════════════════════════════════════════════════

FANART_COLORS = [
    discord.Color.from_rgb(255, 183, 197),
    discord.Color.from_rgb(186, 104, 200),
    discord.Color.from_rgb(121, 134, 203),
    discord.Color.from_rgb(100, 181, 246),
    discord.Color.from_rgb(129, 199, 132),
    discord.Color.from_rgb(255, 202, 40),
    discord.Color.from_rgb(240, 98, 146),
    discord.Color.from_rgb(77, 182, 172),
    discord.Color.from_rgb(255, 138, 101),
    discord.Color.from_rgb(149, 117, 205),
    discord.Color.from_rgb(79, 195, 247),
    discord.Color.from_rgb(174, 213, 129),
    discord.Color.from_rgb(255, 167, 38),
    discord.Color.from_rgb(236, 64, 122),
    discord.Color.from_rgb(38, 198, 218),
    discord.Color.from_rgb(171, 71, 188),
    discord.Color.from_rgb(102, 187, 106),
    discord.Color.from_rgb(92, 107, 192),
    discord.Color.from_rgb(255, 112, 67),
    discord.Color.from_rgb(236, 100, 180),
]

BORDERS = [
    "\u2500\u2500\u2500 \u2726 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 \u2726 \u2500\u2500\u2500",
    "\u2501\u2501\u2501 \u2727 \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501 \u2727 \u2501\u2501\u2501",
    "\u00b7 \u00b7 \u00b7 \u00b7 \u2726 \u00b7 \u00b7 \u00b7 \u00b7 \u00b7 \u00b7 \u00b7 \u2726 \u00b7 \u00b7 \u00b7 \u00b7",
    "\u2726 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 \u2726",
    "\u22b1 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 \u22b0",
    "\u25c8 \u2500\u2500 \u25c7 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 \u25c7 \u2500\u2500 \u25c8",
    "\u2736 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 \u2726 \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 \u2736",
]

TITLE_SPARKS = [
    ("\u2728", "\u2728"), ("\U0001f338", "\U0001f338"), ("\u2b50", "\u2b50"),
    ("\U0001f48e", "\U0001f48e"), ("\U0001f33a", "\U0001f33a"), ("\U0001f52e", "\U0001f52e"),
    ("\U0001f4ab", "\U0001f4ab"), ("\U0001f319", "\U0001f319"), ("\U0001fab7", "\U0001fab7"),
    ("\u274b", "\u274b"), ("\u2735", "\u2735"), ("\u2740", "\u2740"),
]



def _display_tags(fanart: dict) -> list:
    """
    Returns the vibe tags for display, stripping the hidden title tag
    that is automatically stored on every piece for search purposes.
    """
    from utils.tag_parser import split_tags, normalize_tags
    raw = fanart.get("tags") or ""
    title_tag = normalize_tags(fanart.get("title", ""))
    return [t for t in split_tags(raw) if t != title_tag]



def extract_name(obj):
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (list, tuple)):
        for item in reversed(obj):
            if isinstance(item, str) and item.strip():
                return item
        return str(obj[-1])
    return str(obj)


def _get_cover(fanart):
    cover_url = fanart.get("cover_url")
    if not cover_url and fanart.get("story_id"):
        try:
            from database import get_story_by_id
            story = get_story_by_id(fanart["story_id"])
            if story:
                cover_url = (
                    story["cover_url"] if isinstance(story, dict)
                    else (story[10] if len(story) > 10 else None)
                )
        except Exception:
            pass
    return cover_url if (cover_url and isinstance(cover_url, str) and cover_url.startswith("http")) else None


# ═══════════════════════════════════════════════════════════════
# GALLERY EMBED
# ═══════════════════════════════════════════════════════════════

def build_fanart_embed(fanart, index=1, total=1, characters=None, ships=None):
    fid         = fanart.get("id") or 0
    title       = fanart.get("title", "Untitled")
    desc        = fanart.get("description")
    scene_ref   = fanart.get("scene_ref")
    story_title = fanart.get("story_title")
    tags        = fanart.get("tags")
    artist_name = fanart.get("artist_name")
    artist_link = fanart.get("artist_link")
    canon_au    = fanart.get("canon_au") or "canon"
    music_url   = fanart.get("music_url")
    origin      = fanart.get("origin")
    author      = fanart.get("author")
    image_url   = fanart.get("image_url") or fanart.get("image") or fanart.get("url")

    _local_rng = random.Random(fid)
    color  = _local_rng.choice(FANART_COLORS)
    border = _local_rng.choice(BORDERS)
    spark  = _local_rng.choice(TITLE_SPARKS)
    is_au  = (canon_au == "au")

    # ── Resolve names ─────────────────────────────────────────────
    char_names = []
    if characters:
        for c in characters:
            if isinstance(c, dict):            char_names.append(c.get("name", "?"))
            elif isinstance(c, (list, tuple)): char_names.append(str(c[1]))
            else:                              char_names.append(str(c))

    ship_names = []
    if ships:
        for s in ships:
            if isinstance(s, dict):            ship_names.append(s.get("name", "?"))
            elif isinstance(s, (list, tuple)): ship_names.append(str(s[1]))
            else:                              ship_names.append(str(s))

    # ── Header (always shown) ─────────────────────────────────────
    d = [f"# {spark[0]} {title} {spark[1]}", f"-# {border}"]
    embed = discord.Embed(description="\n".join(d), color=color)

    # ── Images (always shown) ─────────────────────────────────────
    cover = _get_cover(fanart)
    if cover:
        embed.set_thumbnail(url=cover)
    if image_url and isinstance(image_url, str) and image_url.startswith("http"):
        embed.set_image(url=image_url)

    # ── Pristine check: nothing filled in yet ─────────────────────
    display_tags = _display_tags(fanart)
    any_built = any([desc, scene_ref, display_tags, artist_name, music_url, origin,
                     char_names, canon_au not in (None, "canon")])
    if not any_built:
        embed.add_field(
            name="✨ Waiting to bloom…",
            value=(
                "Nothing here yet!\n"
                "*Use `/fanart build` to add details, tag characters, credit the artist & more!*"
            ),
            inline=False
        )
        embed.set_footer(text=f"{spark[0]} {index} of {total}")
        return embed

    # ── Ships row (full width, only if tagged) ────────────────────
    if ship_names:
        embed.add_field(
            name="💞  Ships",
            value="  ✦  ".join(f"*{n}*" for n in ship_names),
            inline=False
        )

    # ── Row: Story · Canon/AU · Artist ───────────────────────────
    artist_val = (f"[{artist_name}]({artist_link})" if artist_link else f"**{artist_name}**") if artist_name else "*unknown*"
    embed.add_field(name="📚  Story",    value=f"**{story_title}**" if story_title else "*unlinked*", inline=True)
    embed.add_field(name="🌀  Canon/AU", value="🌀 **Alt Universe**" if is_au else "✦ **Canon**",    inline=True)
    embed.add_field(name="🎨  Art by",   value=artist_val,                                           inline=True)

    # ── Row: Origin · The Vibe · Characters ──────────────────────
    embed.add_field(
        name="💸  Origin",
        value=origin if origin else "*Artwork*",
        inline=True
    )
    embed.add_field(
        name="🎵  The Vibe",
        value=f"[Listen while you look]({music_url})" if music_url else "*Nothing to vibe yet*",
        inline=True
    )
    embed.add_field(
        name="🧬  Characters",
        value="  ✦  ".join(f"**{n}**" for n in char_names) if char_names else "*Nothing*",
        inline=True
    )

    # ── Vibe Tags ─────────────────────────────────────────────────
    display_tags = _display_tags(fanart)
    if display_tags:
        embed.add_field(
            name="✨  Vibe Tags",
            value="  ".join(f"`{t}`" for t in display_tags[:20]),
            inline=False
        )
    else:
        embed.add_field(
            name="✨  Vibe Tags",
            value="`no_tags_to_report`",
            inline=False
        )

    # ── Excerpt (only if set) ─────────────────────────────────────
    if scene_ref:
        embed.add_field(
            name="📖  Excerpt",
            value="\n".join(f"> *{line.strip()}*" for line in scene_ref.splitlines() if line.strip()),
            inline=False
        )

    # ── Scene ─────────────────────────────────────────────────────
    if desc:
        embed.add_field(
            name="🎬  Scene",
            value=desc[:700] + ("…" if len(desc) > 700 else ""),
            inline=False
        )
    else:
        uploader = author or "the author"
        embed.add_field(
            name="🎬  Scene",
            value=f"*Uploaded by {uploader}*",
            inline=False
        )

    # ── Footer ────────────────────────────────────────────────────
    footer = []
    if story_title:
        footer.append(f"📚 {story_title}")
    if artist_name:
        footer.append(f"🎨 {artist_name}")
    footer.append(f"{spark[0]} {index} of {total}")
    embed.set_footer(text="  ✦  ".join(footer))

    return embed

# ═══════════════════════════════════════════════════════════════
# EDITOR / WORKSHOP EMBED
# ═══════════════════════════════════════════════════════════════

def build_fanart_editor_embed(fanart, characters=None, ships=None):
    characters = characters or []
    ships      = ships or []

    fid         = fanart.get("id") or 0
    title       = fanart.get("title", "Untitled")
    desc        = fanart.get("description")
    image_url   = fanart.get("image_url")
    story_title = fanart.get("story_title")
    tags        = fanart.get("tags")
    scene_ref   = fanart.get("scene_ref")
    artist_name = fanart.get("artist_name")
    artist_link = fanart.get("artist_link")
    canon_au    = fanart.get("canon_au") or "canon"
    music_url   = fanart.get("music_url")
    origin      = fanart.get("origin")

    _local_rng = random.Random(fid)
    color  = _local_rng.choice(FANART_COLORS)
    border = _local_rng.choice(BORDERS)
    spark  = _local_rng.choice(TITLE_SPARKS)
    is_au  = (canon_au == "au")

    # ── Progress bar ──────────────────────────────────────────────
    checks = [story_title, artist_name, characters, ships, tags, scene_ref, desc, image_url, music_url, origin]
    done   = sum(1 for c in checks if c)
    total  = len(checks)
    pct    = int((done / total) * 100)
    seg    = 10
    filled = int((done / total) * seg)
    if filled >= seg:
        bar = ("✦ " * seg).rstrip() + " ✨"
    elif filled == 0:
        bar = "· " * seg
    else:
        bar = "✦ " * filled + "✨ " + "· " * (seg - filled)

    d = [
        f"# {spark[0]} {title} {spark[1]}",
        f"-# {border}",
        f"{bar.strip()}  **{pct}%**",
        f"-# {done} / {total} fields complete",
    ]
    embed = discord.Embed(description="\n".join(d), color=color)

    # ── Row 0: Ships (full width, first) ─────────────────────────
    if ships:
        ship_names = [s.get("name", "?") if isinstance(s, dict) else str(s) for s in ships]
        embed.add_field(
            name="💞  Ships ✔",
            value="  ✦  ".join(f"*{n}*" for n in ship_names[:10]),
            inline=False
        )
    else:
        embed.add_field(name="💞  Ships", value="*none tagged*", inline=False)

    # ── Row 1: Story · Canon/AU · Artist ─────────────────────────
    artist_val = (
        (f"[{artist_name}]({artist_link})" if artist_link else f"**{artist_name}**") + " ✔"
        if artist_name else "*not credited*"
    )
    embed.add_field(name="📚  Story",    value=f"**{story_title}** ✔" if story_title else "*not linked*", inline=True)
    embed.add_field(name="🌀  Canon/AU", value="🌀 **Alt Universe**" if is_au else "✦ **Canon**",         inline=True)
    embed.add_field(name="🎨  Artist",   value=artist_val,                                                inline=True)

    # ── Row 2: Origin · The Vibe · Characters ────────────────────
    char_names = [c.get("name", "?") if isinstance(c, dict) else str(c) for c in characters]
    embed.add_field(
        name="💸  Origin",
        value=(origin + " ✔") if origin else "*not set*",
        inline=True
    )
    embed.add_field(
        name="🎵  The Vibe",
        value=f"[song linked]({music_url}) ✔" if music_url else "*no song yet*",
        inline=True
    )
    embed.add_field(
        name="🧬  Characters ✔" if char_names else "🧬  Characters",
        value="  ·  ".join(char_names[:15]) if char_names else "*none tagged*",
        inline=True
    )

    # ── Vibe Tags ─────────────────────────────────────────────────
    display_tags = _display_tags(fanart)
    if display_tags:
        embed.add_field(
            name="✨  Vibe Tags ✔",
            value="  ".join(f"`{t}`" for t in display_tags[:20]),
            inline=False
        )
    else:
        embed.add_field(
            name="✨  Vibe Tags",
            value="-# *e.g.* `soft`  `rain`  `enemies-to-lovers`  `crying-in-the-car`",
            inline=False
        )

    # ── Excerpt ───────────────────────────────────────────────────
    if scene_ref:
        embed.add_field(
            name="📖  Excerpt ✔",
            value="\n".join(f"> *{line.strip()}*" for line in scene_ref.splitlines() if line.strip()),
            inline=False
        )
    else:
        embed.add_field(
            name="📖  Excerpt",
            value="-# *paste a quote from the moment this art depicts*",
            inline=False
        )

    # ── Scene description ─────────────────────────────────────────
    if desc:
        embed.add_field(
            name="🎬  Scene ✔",
            value=desc[:700] + ("…" if len(desc) > 700 else ""),
            inline=False
        )
    else:
        embed.add_field(
            name="🎬  Scene",
            value="-# *set the scene — what\'s happening in this moment?*",
            inline=False
        )

    # ── Images ───────────────────────────────────────────────────
    cover = _get_cover(fanart)
    if cover:
        embed.set_thumbnail(url=cover)
    if image_url and isinstance(image_url, str) and image_url.startswith("http"):
        embed.set_image(url=image_url)

    embed.set_footer(
        text=f"✦ Workshop  ·  {story_title or 'no story linked'}  ·  {spark[0]} {pct}% done"
    )

    return embed