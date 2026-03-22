import discord

from features.stories.story_service import unpack_story
from database import (
    has_story_badge,
    get_user_id,
    get_story_ribbon_count,
    get_top_story_characters
)


def build_story_notes_embed(story, viewer=None, stats=None):
    """
    stats (optional dict): if provided, enriches the embed with live community data.
    Keys: chars, fanarts, comments, chapters_built, ch_count,
          commented_chapters, global_comment_count
    """

    story = unpack_story(story)

    title        = story["title"]
    story_id     = story["id"]
    cover        = story["cover_url"]
    ch_count     = story.get("chapter_count") or 0

    inspirations = story.get("story_notes") or story.get("inspiration")
    playlist     = story.get("playlist_url")
    roadmap      = story.get("roadmap")
    appreciation = story.get("appreciation")
    words        = story.get("word_count")

    # ── Badge check ──────────────────────────────────
    badge = False
    if viewer:
        uid = get_user_id(str(viewer.id))
        if uid:
            badge = has_story_badge(uid, story_id)

    color = discord.Color.gold() if badge else discord.Color.from_rgb(105, 185, 255)

    # ── Reading time ─────────────────────────────────
    reading_time = "Unknown"
    if words:
        minutes      = int(words / 200)
        hours        = minutes // 60
        mins         = minutes % 60
        reading_time = f"{hours}h {mins}m" if hours else f"{mins} min"

    # ── Ribbons ──────────────────────────────────────
    ribbons = get_story_ribbon_count(story_id)

    # ── Top characters ───────────────────────────────
    top_chars = get_top_story_characters(story_id)
    char_text = "*No favorites yet.*"
    if top_chars:
        medals = ["✦", "✦"]
        lines  = []
        for i, c in enumerate(top_chars):
            medal = medals[i] if i < len(medals) else "✦"
            lines.append(
                f"{medal} **{c['name']}** • {c['votes']} vote{'s' if c['votes'] != 1 else ''} ({c['percent']}%)"
            )
        char_text = "\n".join(lines)

    # ── Build embed ──────────────────────────────────
    title_line = f"🏅 {title} — Story Dex" if badge else f"✦ {title} — Story Dex"

    embed = discord.Embed(
        title=title_line,
        description=(
            "✦ *Badge Holder — you finished this one!*"
            if badge else
            "✦ *Behind-the-scenes for this story.*"
        ),
        color=color
    )

    if cover:
        embed.set_thumbnail(url=cover)

    # ── Pokédex Stats Panel ──────────────────────────
    # Row 1: Word Count & Reading Time (inline side by side)
    embed.add_field(
        name="📝  Word Count",
        value=f"`{words:,}`" if words else "`Unknown`",
        inline=True
    )
    embed.add_field(
        name="⏱  Reading Time",
        value=f"`{reading_time}`",
        inline=True
    )
    embed.add_field(
        name="🎗  Reader Ribbons",
        value=f"`{ribbons} earned`",
        inline=True
    )

    # Row 2: Community stats (inline, only when stats provided)
    if stats:
        embed.add_field(
            name="🧬  Characters",
            value=f"`{stats.get('chars', 0)}`",
            inline=True
        )
        embed.add_field(
            name="🎨  Fanart Pieces",
            value=f"`{stats.get('fanarts', 0)}`",
            inline=True
        )
        embed.add_field(
            name="💬  Comments",
            value=f"`{stats.get('comments', 0)}`",
            inline=True
        )

    # ── Chapter Activity (only when stats provided) ──
    if stats:
        ch_total  = stats.get("ch_count", ch_count)
        built     = stats.get("chapters_built", 0)
        commented = stats.get("commented_chapters", 0)
        global_c  = stats.get("global_comment_count", 0)

        embed.add_field(
            name="🛠️  Pages Built",
            value=f"`{built} / {ch_total}`",
            inline=True
        )
        embed.add_field(
            name="💬  Commented Chapters",
            value=f"`{commented}`",
            inline=True
        )
        embed.add_field(
            name="🌐  Global Comments",
            value=f"`{global_c}`",
            inline=True
        )

    # ── Fan Favorites ────────────────────────────────
    embed.add_field(
        name="💞 Fan Favorites",
        value=char_text,
        inline=False
    )

    # ── Pending hint ─────────────────────────────────
    has_any_content = any([inspirations, appreciation, playlist, roadmap])
    if not has_any_content:
        embed.add_field(
            name="· · · · · · · · · · · · · · · · · · · · · · · · ·",
            value=(
                "🌀 **Dex entry pending!** No behind-the-scenes content yet.\n"
                "*Authors: use `/fic build` to add a playlist, inspirations, roadmap & more!*\n"
                "· · · · · · · · · · · · · · · · · · · · · · · · ·"
            ),
            inline=False
        )

    # ── Creator Notes ────────────────────────────────────────────
    def blockquote(text):
        return "\n".join(f"> {line}" for line in text.splitlines())

    insp_text = blockquote(inspirations) if inspirations else "*No inspirations shared yet.*"
    appr_text = blockquote(appreciation) if appreciation else "*No message from the author yet.*"

    embed.add_field(
        name="◈ ─── Creator Notes ─── ◈",
        value=(
            f"💡 **Inspirations**\n"
            f"{insp_text}\n\n"
            f"💖 **Author Appreciation**\n"
            f"{appr_text}"
        ),
        inline=False
    )

    # ── Creative Extras ──────────────────────────────
    playlist_text = (
        f"[Listen While Reading]({playlist})"
        if playlist else
        "*No playlist available.*"
    )

    embed.add_field(
        name="◈ ─── Creative Extras ─── ◈",
        value=(
            f"🎵 **Writing Playlist**\n"
            f"{playlist_text}\n\n"
            f"🗺 **Story Roadmap**\n"
            f"{roadmap or '*No roadmap update yet.*'}"
        ),
        inline=False
    )

    # ── Footer ───────────────────────────────────────
    embed.set_footer(
        text=(
            "🏅 Badge Earned • You finished this story! Gotta read 'em all~"
            if badge else
            "📖 Story Dex • Gotta read 'em all~"
        )
    )

    return embed