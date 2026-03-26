import discord

from database import (
    get_story_by_id,
    get_user_id,
    get_story_progress,
    get_tags_by_story
)

from features.stories.views.library_view import (
    story_to_dict,
    build_progress_bar,
    clean_summary
)


def build_story_embed(story_id, user):

    story_row = get_story_by_id(story_id)

    if not story_row:
        return discord.Embed(
            title="Story not found.",
            color=discord.Color.red()
        )

    story = story_to_dict(story_row)

    uid = get_user_id(str(user.id))
    progress = get_story_progress(uid, story["id"]) or 0

    ch = story["chapter_count"]
    percent = int((progress / ch) * 100) if ch else 0
    bar = build_progress_bar(percent)

    title = story["title"]
    upd = story["library_updated"]
    words = story["word_count"]
    summ = story["summary"]
    ao3 = story["ao3_url"]
    author = story["author"]
    cover = story["cover_url"]
    music = story.get("music_url")

    embed = discord.Embed(
        title=f"📖 {title} • ✨ {percent}% Complete",
        description=bar,
        color=discord.Color.dark_teal()
    )

    if cover:
        embed.set_thumbnail(url=cover)

    summary_text = clean_summary(summ, author)

    embed.add_field(
        name="✨ Summary",
        value="\n".join(f"> {line}" for line in summary_text.split("\n")),
        inline=False
    )

    tags = sorted(get_tags_by_story(story["id"]))

    if tags:
        MAX_TAGS = 30
        total_tags = len(tags)
        visible_tags = tags[:MAX_TAGS]

        tag_string = " ".join(f"`{tag.title()}`" for tag in visible_tags)

        if total_tags > MAX_TAGS:
            tag_string += " • ..."

        embed.add_field(
            name=f"🏷️ Tags ({len(visible_tags)}/{total_tags})",
            value=f"> {tag_string}",
            inline=False
        )

    embed.add_field(
        name="🌸 Story Info",
        value=(
            f"**Author** • {author}\n"
            f"**Chapters** • {ch}\n"
            f"**Words** • {words:,}"
        ),
        inline=True
    )

    embed.add_field(
        name="📖 Your Progress",
        value=(
            f"**Progress** • {progress}/{ch}\n"
            f"**Completion** • {percent}%"
        ),
        inline=True
    )

    links = [f"[AO3]({ao3})"]

    if story["extra_link_title"] and story["extra_link_url"]:
        links.append(f"[{story['extra_link_title']}]({story['extra_link_url']})")

    if story["extra_link2_title"] and story["extra_link2_url"]:
        links.append(f"[{story['extra_link2_title']}]({story['extra_link2_url']})")

    embed.add_field(
        name="🔗 Read",
        value=" ✦ ".join(links),
        inline=False
    )

    if music:
        embed.add_field(
            name="🎵 Music Playlist",
            value=f"[Listen while reading]({music})",
            inline=True
        )

    if cover:
        embed.set_image(url=cover)

    embed.set_footer(text=f"Last Updated • {upd}")

    return embed