import discord
from bs4 import BeautifulSoup

from database import (
    get_user_id,
    get_story_progress,
    get_tags_by_story,
    has_story_badge
)

# =====================================================
# HELPERS
# =====================================================

def story_to_dict(row):
    """
    Converts sqlite Row or tuple into a consistent dict.
    Works with both SELECT * and ordered SELECT queries.
    """

    if row is None:
        return None

    # sqlite Row supports key access
    if hasattr(row, "keys"):
        return {
            "id": row["id"],
            "title": row["title"],
            "chapter_count": row["chapter_count"],
            "library_updated": row["library_updated"],
            "word_count": row["word_count"],
            "summary": row["summary"],
            "ao3_url": row["ao3_url"],
            "author": row["author"],
            "cover_url": row["cover_url"],
            "wattpad_url": row["wattpad_url"],
            "extra_link_title": row["extra_link_title"],
            "extra_link_url": row["extra_link_url"],
            "extra_link2_title": row["extra_link2_title"],
            "extra_link2_url": row["extra_link2_url"],
            "music_url": row["playlist_url"],
            "rating": row["rating"]
        }

    # fallback (tuple structure like library query)
    return {
        "title": row[0],
        "chapter_count": row[1],
        "library_updated": row[2],
        "word_count": row[3],
        "summary": row[4],
        "ao3_url": row[5],
        "author": row[6],
        "wattpad_url": row[7],
        "cover_url": row[8],
        "id": row[9],
        "extra_link_title": row[10] if len(row) > 10 else None,
        "extra_link_url": row[11] if len(row) > 11 else None,
        "extra_link2_title": row[12] if len(row) > 12 else None,
        "extra_link2_url": row[13] if len(row) > 13 else None,
        "music_url": row[14] if len(row) > 14 else None,
        "rating": row[15] if len(row) > 15 else None,
    }


def build_progress_bar(percent, length=10):
    filled = int((percent / 100) * length)
    empty = length - filled
    return "▰" * filled + "▱" * empty


def clean_summary(summary):

    if not summary:
        return "No summary."

    soup = BeautifulSoup(summary, "html.parser")
    return soup.get_text("\n", strip=True)


# =====================================================
# MAIN EMBED BUILDER
# =====================================================

def build_story_embed(story_row, user):

    story = story_to_dict(story_row)

    uid = get_user_id(str(user.id))
    progress = get_story_progress(uid, story["id"]) or 0

    ch = story["chapter_count"] or 0

    percent = int((progress / ch) * 100) if ch else 0

    if percent == 100:
        bar = "✨ " + build_progress_bar(percent) + " ✨"
    else:
        bar = build_progress_bar(percent)

    title = story["title"]
    badge = "🏅 " if has_story_badge(uid, story["id"]) else ""
    upd = story["library_updated"]
    words = story["word_count"] or 0
    summ = story["summary"]
    ao3 = story["ao3_url"]
    author = story["author"]
    cover = story["cover_url"]
    music = story.get("music_url")

    color = discord.Color.gold() if has_story_badge(uid, story["id"]) else discord.Color.dark_teal()

    embed = discord.Embed(
        title=f"{badge}📖 {title} • ✨ {percent}% Complete",
        description=bar,
        color=color
    )

    # ---------- COVER THUMB ----------
    if cover:
        embed.set_thumbnail(url=cover)

    # ---------- SUMMARY ----------
    summary_text = clean_summary(summ)

    embed.add_field(
        name="✨ Summary",
        value="\n".join(
            f"> {line}" for line in summary_text.split("\n")
        ),
        inline=False
    )

    # ---------- TAGS ----------
    tags = sorted(get_tags_by_story(story["id"]))

    if tags:

        MAX_TAGS = 30
        total_tags = len(tags)
        visible_tags = tags[:MAX_TAGS]

        tag_string = " ".join(
            f"`{tag.title()}`" for tag in visible_tags
        )

        if total_tags > MAX_TAGS:
            tag_string += " • ..."

        embed.add_field(
            name=f"🏷️ Tags ({len(visible_tags)}/{total_tags})",
            value=f"> {tag_string}",
            inline=False
        )

    # ---------- RATING ----------
    rating = story.get("rating")

    if rating:
        embed.add_field(
            name="🔞 Rating",
            value=f"`{rating}`",
            inline=False
        )

    # ---------- STORY INFO ----------
    embed.add_field(
        name="🌸 Story Info",
        value=(
            f"**Author** • {author}\n"
            f"**Chapters** • {ch}\n"
            f"**Words** • {int(words):,}"
        ),
        inline=True
    )



    # ---------- PROGRESS ----------
    badge_line = "\n> 🏅 Badge Earned" if has_story_badge(uid, story["id"]) else ""

    embed.add_field(
        name="📖 Your Progress",
        value=(
            f"**Progress** • {progress}/{ch}\n"
            f"**Completion** • {percent}%"
            f"{badge_line}"
        ),
        inline=True
    )

    # ---------- LINKS ----------
    links = [f"[AO3]({ao3})"]

    if story["extra_link_title"] and story["extra_link_url"]:
        links.append(
            f"[{story['extra_link_title']}]({story['extra_link_url']})"
        )

    if story["extra_link2_title"] and story["extra_link2_url"]:
        links.append(
            f"[{story['extra_link2_title']}]({story['extra_link2_url']})"
        )

    embed.add_field(
        name="🔗 Read",
        value=" ✦ ".join(links),
        inline=False
    )

    # ---------- MUSIC ----------
    if music:
        embed.add_field(
            name="🎵 Music Playlist",
            value=f"[Listen While Reading]({music})",
            inline=True
        )

    # ---------- COVER IMAGE ----------
    if cover:
        embed.set_image(url=cover)

    embed.set_footer(
        text=f"Last Updated • {upd}"
    )

    return embed