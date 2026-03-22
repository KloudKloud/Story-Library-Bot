import discord
from bs4 import BeautifulSoup


# =====================================================
# HELPERS
# =====================================================

def clean_summary(summary):
    if not summary:
        return "No summary."

    soup = BeautifulSoup(summary, "html.parser")
    return soup.get_text("\n", strip=True)

# =====================================================
# LIST EMBED
# =====================================================

def build_story_list_embed(title, stories, page, per_page, total_pages):

    embed = discord.Embed(
        title=title,
        color=discord.Color.blurple()
    )

    start = page * per_page
    chunk = stories[start:start + per_page]

    for i, s in enumerate(chunk, start=1):
        story_title, ch, upd, words, summ, ao3, user, watt, cover, sid = s

        preview = (summ[:120] + "...") if summ else "No summary."

        embed.add_field(
            name=f"{i}. {story_title}",
            value=(
                f"❤️ Chapters: {ch} | Words: {words:,}\n"
                f"💚 Author: {user}\n"
                f"*{preview}*"
            ),
            inline=False
        )

    embed.set_footer(text=f"Page {page+1}/{total_pages}")
    return embed


# =====================================================
# DETAIL EMBED
# =====================================================

def build_story_detail_embed(story, progress_percent, progress_value):

    title = story["title"]
    ch = story["chapter_count"]
    upd = story["updated_at"]
    words = story["word_count"]
    summ = story["summary"]
    ao3 = story["ao3_url"]
    user = story["author"]
    watt = story["wattpad_url"]
    cover = story["cover_url"]
    sid = story["id"]

    embed = discord.Embed(
        title=f"📖📘 {title} ✏️ ({progress_percent}% COMPLETED)",
        color=discord.Color.dark_teal()
    )

    embed.description = (
        f"💚 **Author:** {user}\n"
        f"❤️ **Chapters:** {ch}\n\n"
        f"*{clean_summary(summ)}*\n\n"
        f"**Word Count:** {words:,}\n"
        f"**Last Updated:** {upd}\n"
        f"**Progress:** {progress_value}/{ch}\n"
        f"**Links:** [AO3]({ao3})"
    )

    if watt:
        embed.description += f" | [Wattpad]({watt})"

    if cover:
        embed.set_image(url=cover)

    return embed