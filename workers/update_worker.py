import asyncio
import discord
from discord import ui
from datetime import datetime

from ao3_parser import fetch_ao3_metadata
from database import (
    get_story_by_id,
    get_chapters_by_story,
    delete_chapters_by_story,
    add_chapter,
    update_story_metadata,
    get_connection,
    get_announcement_channel,
)


# =====================================================
# HELPERS
# =====================================================

def _clear_story_tags(story_id):
    """Delete all tag links for a story so they can be rebuilt."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM story_tags WHERE story_id = ?", (story_id,))
    conn.commit()
    conn.close()


def _rebuild_story_tags(story_id, tags):
    """Re-insert tags after clearing. Reuses the same logic as add_story."""
    from database import add_story_tags, get_connection
    conn = get_connection()
    cursor = conn.cursor()
    add_story_tags(cursor, story_id, tags)
    conn.commit()
    conn.close()


def _chapters_to_dict(rows):
    """Convert DB chapter rows → {number: title} dict."""
    return {row["chapter_number"]: row["chapter_title"] for row in rows}


# =====================================================
# CONFIRMATION VIEW (for removed chapters)
# =====================================================

class ConfirmRemovedChaptersView(ui.View):
    """
    Shown when the new fetch has FEWER chapters than the DB.
    Lets the author confirm the removal is intentional before
    the update is committed.
    """

    def __init__(self, story_id, data, old_story, removed_chapters, status_msg):
        super().__init__(timeout=120)
        self.story_id = story_id
        self.data = data
        self.old_story = old_story
        self.removed_chapters = removed_chapters   # list of (num, title)
        self.status_msg = status_msg

    @ui.button(label="✅ Yes, apply update", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        await _apply_update(
            interaction,
            self.story_id,
            self.data,
            self.old_story,
            self.status_msg,
            confirmed_removal=True
        )
        self.stop()

    @ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(
            content=(
                "🚫 **Update cancelled.**\n"
                "No changes were made. You can review your story on AO3 and try again."
            ),
            view=None
        )
        self.stop()


# =====================================================
# APPLY THE ACTUAL UPDATE (shared by worker + confirm)
# =====================================================

async def _apply_update(interaction, story_id, data, old_story, status_msg, confirmed_removal=False):
    """
    Commits all changes to the DB and reports what changed.
    Called both directly (no chapter removal) and after confirmation.
    """

    old_chapters_db  = get_chapters_by_story(story_id)
    old_chapter_map  = _chapters_to_dict(old_chapters_db)
    old_chapter_count = old_story["chapter_count"] or 0
    old_words        = old_story["word_count"] or 0
    old_summary      = (old_story["summary"] or "").strip()

    new_chapter_count = data["chapter_count"]
    new_words         = data["word_count"]
    new_summary       = (data["summary"] or "").strip()
    new_chapter_map   = {ch["number"]: ch["title"] for ch in data["chapters"]}

    # ── Save chapters ──────────────────────────────────────
    delete_chapters_by_story(story_id)
    for ch in data["chapters"]:
        add_chapter(story_id, ch["number"], ch["title"], None, ch.get("summary"))

    # ── Save story metadata ─────────────────────────────────
    library_updated = datetime.utcnow().strftime("%Y-%m-%d")
    update_story_metadata(
        story_id,
        title        = data["title"],
        chapter_count= new_chapter_count,
        last_updated = data["last_updated"],
        word_count   = new_words,
        summary      = new_summary,
        library_updated = library_updated,
        rating       = data.get("rating")
    )

    # ── Rebuild tags ────────────────────────────────────────
    if data.get("tags"):
        _clear_story_tags(story_id)
        _rebuild_story_tags(story_id, data["tags"])

    # ── Build change report ─────────────────────────────────
    changes = []

    # New chapters
    added = [
        (num, title)
        for num, title in sorted(new_chapter_map.items())
        if num not in old_chapter_map
    ]
    for num, title in added:
        changes.append(f"📖 **New chapter detected!**\nChapter {num}: *{title}*")

    # Removed chapters (already confirmed by this point)
    removed = [
        (num, title)
        for num, title in sorted(old_chapter_map.items())
        if num not in new_chapter_map
    ]
    if removed and confirmed_removal:
        for num, title in removed:
            changes.append(f"🗑️ **Chapter removed:** Chapter {num}: *{title}*")

    # Renamed chapters
    renamed = [
        (num, old_chapter_map[num], new_chapter_map[num])
        for num in old_chapter_map
        if num in new_chapter_map and old_chapter_map[num] != new_chapter_map[num]
    ]
    for num, old_title, new_title in renamed:
        changes.append(f"✏️ **Chapter {num} renamed:** *{old_title}* → *{new_title}*")

    # Word count changed
    if new_words != old_words:
        diff = new_words - old_words
        sign = "+" if diff > 0 else ""
        changes.append(
            f"📝 **New word count:** {new_words:,} "
            f"({sign}{diff:,})"
        )

    # Summary changed
    if new_summary != old_summary:
        changes.append("💬 **Summary updated.**")

    # ── Format final message ────────────────────────────────
    if changes:
        report = "\n\n".join(changes)
        final = (
            f"✅ **{data['title']} updated!**\n\n"
            f"{report}"
        )
    else:
        final = (
            f"✅ **{data['title']}** is already up to date — no changes detected."
        )

    try:
        await status_msg.edit(content=final, view=None)
    except Exception:
        pass

    # ── Send announcements for new chapters ──────────────
    if added:
        await _send_announcement(interaction, data, old_story, added)


# =====================================================
# MAIN UPDATE LOGIC  (called from bot command)
# =====================================================

async def run_update(interaction: discord.Interaction, story_id: int):
    """
    Entry point called by the /updatefic command.
    Handles the full download → diff → confirm/apply flow.
    """

    await interaction.response.defer(ephemeral=True)

    status_msg = await interaction.followup.send(
        "⏳ **Starting update…**\n"
        "⬇️ Downloading HTML export…",
        ephemeral=True
    )

    try:
        # ── Load current DB state ───────────────────────────
        old_story = get_story_by_id(story_id)

        if not old_story:
            await status_msg.edit(content="❌ Story not found.")
            return

        ao3_url           = old_story["ao3_url"]
        old_chapter_count = old_story["chapter_count"] or 0

        # ── Fetch fresh data ────────────────────────────────
        await status_msg.edit(
            content="⏳ **Starting update…**\n"
                    "⬇️ Downloading HTML export…\n"
                    "📖 Parsing chapters…"
        )

        data = await asyncio.to_thread(fetch_ao3_metadata, ao3_url)

        await status_msg.edit(
            content="⏳ **Starting update…**\n"
                    "⬇️ Downloading HTML export…\n"
                    "📖 Parsing chapters…\n"
                    "🔍 Comparing with library…"
        )

        new_chapter_count = data["chapter_count"]

        # ── Load old chapter map ────────────────────────────
        old_chapters_db = get_chapters_by_story(story_id)
        old_chapter_map = _chapters_to_dict(old_chapters_db)
        new_chapter_map = {ch["number"]: ch["title"] for ch in data["chapters"]}

        removed = [
            (num, title)
            for num, title in sorted(old_chapter_map.items())
            if num not in new_chapter_map
        ]

        # ── Chapter removal → ask for confirmation ──────────
        if removed:
            removed_lines = "\n".join(
                f"• Chapter {num}: *{title}*"
                for num, title in removed
            )

            confirm_view = ConfirmRemovedChaptersView(
                story_id, data, old_story, removed, status_msg
            )

            await status_msg.edit(
                content=(
                    f"⚠️ **Heads up!**\n\n"
                    f"The following chapter(s) were **not found** in the new download:\n"
                    f"{removed_lines}\n\n"
                    f"Did you remove or un-publish these? "
                    f"If yes, confirm below and the library will be updated. "
                    f"If not, cancel and check your AO3 post first."
                ),
                view=confirm_view
            )
            return

        # ── No removals → apply immediately ─────────────────
        await status_msg.edit(content="💾 Saving updates…")
        await _apply_update(
            interaction,
            story_id,
            data,
            old_story,
            status_msg,
            confirmed_removal=False
        )

    except Exception as e:
        try:
            await status_msg.edit(content=f"❌ Update failed:\n`{e}`", view=None)
        except Exception:
            pass


# =====================================================
# ANNOUNCEMENT
# =====================================================

async def _send_announcement(interaction, data, old_story, added_chapters):
    """
    Send a story-update announcement to the user's configured channel.
    Silently skips if no channel is set or the bot can't reach it.
    """
    from database import get_user_id

    bot = interaction.client
    uid = get_user_id(str(interaction.user.id))
    if not uid:
        return

    channel_id = get_announcement_channel(uid)
    if not channel_id:
        return

    try:
        channel = bot.get_channel(int(channel_id))
        if channel is None:
            channel = await bot.fetch_channel(int(channel_id))
    except Exception:
        return

    # Build the announcement
    chapter_lines = "\n".join(
        f"📖 **Chapter {num}:** *{title}*"
        for num, title in added_chapters
    )

    ao3_url = old_story.get("ao3_url", "")
    link_line = f"\n🔗 [Read on AO3]({ao3_url})" if ao3_url else ""

    embed = discord.Embed(
        title=f"📚 {data['title']} — New Update!",
        description=(
            f"**{interaction.user.display_name}** just uploaded a new chapter!\n\n"
            f"{chapter_lines}"
            f"{link_line}"
        ),
        color=discord.Color.from_rgb(100, 200, 255)
    )

    cover = old_story.get("cover_url")
    if cover:
        embed.set_thumbnail(url=cover)

    try:
        await channel.send(embed=embed)
    except Exception:
        pass
