import asyncio
import discord
from discord import ui
from datetime import datetime

from ao3_parser import fetch_ao3_metadata, normalize_ao3_url
from wattpad_parser import fetch_wattpad_metadata, WattpadError, normalize_wattpad_url
from database import (
    get_story_by_id,
    get_chapters_by_story,
    delete_chapters_by_story,
    add_chapter,
    update_story_metadata,
    get_tags_by_story,
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
    platform = data.get("_platform", "ao3")
    delete_chapters_by_story(story_id)
    for ch in data["chapters"]:
        ch_url = (
            f"https://www.wattpad.com/{ch['id']}"
            if platform == "wattpad" and ch.get("id")
            else None
        )
        add_chapter(
            story_id,
            ch["number"],
            ch["title"],
            ch_url,
            ch.get("summary"),
            wattpad_comment_count=ch.get("comment_count") if platform == "wattpad" else None,
        )

    # ── Save story metadata ─────────────────────────────────
    library_updated = datetime.utcnow().strftime("%Y-%m-%d")
    meta = dict(
        title           = data["title"],
        chapter_count   = new_chapter_count,
        last_updated    = data["last_updated"],
        word_count      = new_words,
        summary         = new_summary,
        library_updated = library_updated,
        rating          = data.get("rating"),
    )
    if platform == "wattpad":
        if data.get("reads")    is not None: meta["wattpad_reads"]    = data["reads"]
        if data.get("votes")    is not None: meta["wattpad_votes"]    = data["votes"]
        if data.get("comments") is not None: meta["wattpad_comments"] = data["comments"]
    else:
        if data.get("hits")      is not None: meta["ao3_hits"]      = data["hits"]
        if data.get("kudos")     is not None: meta["ao3_kudos"]     = data["kudos"]
        if data.get("comments")  is not None: meta["ao3_comments"]  = data["comments"]
        if data.get("bookmarks") is not None: meta["ao3_bookmarks"] = data["bookmarks"]
    update_story_metadata(story_id, **meta)

    # ── Rebuild tags (snapshot first for diff) ──────────────
    old_tags = set(get_tags_by_story(story_id))
    new_tags = set(t.lower() for t in data.get("tags", []))
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

    # Tag changes
    added_tags   = new_tags - old_tags
    removed_tags = old_tags - new_tags
    if added_tags:
        changes.append(
            f"🏷️ **New tags added:** {', '.join(sorted(added_tags))}"
        )
    if removed_tags:
        changes.append(
            f"🏷️ **Tags removed:** {', '.join(sorted(removed_tags))}"
        )

    # Stat changes (reads/hits, votes/kudos, comments)
    if platform == "wattpad":
        stat_defs = [
            ("👁️", "reads",    old_story["wattpad_reads"],    data.get("reads")),
            ("🩷", "votes",    old_story["wattpad_votes"],    data.get("votes")),
            ("💬", "comments", old_story["wattpad_comments"], data.get("comments")),
        ]
    else:
        stat_defs = [
            ("👁️", "hits",     old_story["ao3_hits"],     data.get("hits")),
            ("🩷", "kudos",    old_story["ao3_kudos"],    data.get("kudos")),
            ("💬", "comments", old_story["ao3_comments"], data.get("comments")),
        ]

    for emoji, label, old_val, new_val in stat_defs:
        if new_val is not None:
            old_v = old_val or 0
            if new_val > old_v:
                diff = new_val - old_v
                changes.append(
                    f"{emoji} **{diff:,} new {label}!** "
                    f"({old_v:,} → {new_val:,})"
                )

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

        platform = old_story["platform"] or "ao3"
        old_chapter_count = old_story["chapter_count"] or 0

        # ── Fetch fresh data ────────────────────────────────
        if platform == "wattpad":
            wattpad_url = old_story["wattpad_url"]
            await status_msg.edit(
                content="⏳ **Starting update…**\n"
                        "⬇️ Fetching from Wattpad…\n"
                        "📖 Counting words & parsing chapters…"
            )
            try:
                data = await asyncio.to_thread(fetch_wattpad_metadata, wattpad_url)
            except WattpadError as e:
                await status_msg.edit(content=f"❌ {e.user_message}")
                return
            # Normalise field names to match the shared update path
            data["summary"] = data.get("description", "No summary available.")
            data["rating"]  = "Mature" if data.get("mature") else None
        else:
            ao3_url = old_story["ao3_url"]
            await status_msg.edit(
                content="⏳ **Starting update…**\n"
                        "⬇️ Downloading HTML export…\n"
                        "📖 Parsing chapters…"
            )
            data = await asyncio.to_thread(fetch_ao3_metadata, ao3_url)

        # Stash platform so _apply_update can access it without extra args
        data["_platform"] = platform

        await status_msg.edit(
            content="⏳ **Starting update…**\n"
                    "⬇️ Downloading…\n"
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
# /fic swapdomain — swap a story's link / platform
# =====================================================

def _detect_platform(url):
    u = url.lower()
    if "archiveofourown.org" in u: return "ao3"
    if "wattpad.com" in u:         return "wattpad"
    return None


async def _apply_swapdomain(story_id, data, old_story, status_msg):
    """Commit the domain swap: update URL, platform, metadata, chapters, tags."""

    new_platform = data["_platform"]
    new_url      = data["_new_url"]
    old_platform = old_story["platform"] or "ao3"
    old_label    = "Wattpad" if old_platform == "wattpad" else "AO3"
    new_label    = "Wattpad" if new_platform == "wattpad" else "AO3"
    old_url      = old_story["wattpad_url"] if old_platform == "wattpad" else old_story["ao3_url"]

    library_updated = datetime.utcnow().strftime("%Y-%m-%d")

    meta = dict(
        title           = data["title"],
        author          = data["author"],
        chapter_count   = data["chapter_count"],
        last_updated    = data["last_updated"],
        word_count      = data["word_count"],
        summary         = data.get("summary") or "No summary available.",
        library_updated = library_updated,
        rating          = data.get("rating"),
        platform        = new_platform,
    )

    if new_platform == "wattpad":
        meta["wattpad_url"] = new_url
        if old_platform == "ao3":
            meta["ao3_url"]       = None
            meta["ao3_hits"]      = None
            meta["ao3_kudos"]     = None
            meta["ao3_comments"]  = None
            meta["ao3_bookmarks"] = None
        if data.get("reads")    is not None: meta["wattpad_reads"]    = data["reads"]
        if data.get("votes")    is not None: meta["wattpad_votes"]    = data["votes"]
        if data.get("comments") is not None: meta["wattpad_comments"] = data["comments"]
    else:
        meta["ao3_url"] = new_url
        if old_platform == "wattpad":
            meta["wattpad_url"]      = None
            meta["wattpad_reads"]    = None
            meta["wattpad_votes"]    = None
            meta["wattpad_comments"] = None
        if data.get("hits")      is not None: meta["ao3_hits"]      = data["hits"]
        if data.get("kudos")     is not None: meta["ao3_kudos"]     = data["kudos"]
        if data.get("comments")  is not None: meta["ao3_comments"]  = data["comments"]
        if data.get("bookmarks") is not None: meta["ao3_bookmarks"] = data["bookmarks"]

    update_story_metadata(story_id, **meta)

    # Rebuild chapters
    delete_chapters_by_story(story_id)
    for ch in data["chapters"]:
        ch_url = (
            f"https://www.wattpad.com/{ch['id']}"
            if new_platform == "wattpad" and ch.get("id")
            else None
        )
        add_chapter(
            story_id,
            ch["number"],
            ch["title"],
            ch_url,
            ch.get("summary"),
            wattpad_comment_count=ch.get("comment_count") if new_platform == "wattpad" else None,
        )

    # Rebuild tags
    _clear_story_tags(story_id)
    if data.get("tags"):
        _rebuild_story_tags(story_id, data["tags"])

    # Success message
    if old_platform != new_platform:
        final = (
            f"✅ **{data['title']}** has been moved from **{old_label}** to **{new_label}**!\n"
            f"-# All metadata refreshed. Characters and fanart preserved."
        )
    else:
        final = (
            f"✅ Updated your **{new_label}** link for **{data['title']}**!\n"
            f"**Before:** {old_url}\n"
            f"**After:** {new_url}\n"
            f"-# Metadata refreshed. Characters and fanart preserved."
        )

    try:
        await status_msg.edit(content=final, embed=None, view=None)
    except Exception:
        pass


class SwapDomainConfirmView(ui.View):

    def __init__(self, story_id, data, old_story, status_msg):
        super().__init__(timeout=120)
        self.story_id  = story_id
        self.data      = data
        self.old_story = old_story
        self.status_msg = status_msg

    @ui.button(label="✅ Confirm swap", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        await _apply_swapdomain(self.story_id, self.data, self.old_story, self.status_msg)
        self.stop()

    @ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(
            content="🚫 Swap cancelled. No changes were made.",
            embed=None,
            view=None,
        )
        self.stop()


async def run_swapdomain(interaction: discord.Interaction, story_id: int, new_url: str):
    """Entry point for /fic swapdomain."""

    await interaction.response.defer(ephemeral=True)
    status_msg = await interaction.followup.send("⏳ Looking up link…", ephemeral=True)

    try:
        old_story = get_story_by_id(story_id)
        if not old_story:
            await status_msg.edit(content="❌ Story not found.")
            return

        # Detect platform
        new_platform = _detect_platform(new_url)
        if not new_platform:
            await status_msg.edit(
                content="❌ That doesn't look like a valid AO3 or Wattpad link."
            )
            return

        # Normalize URL
        new_normalized = (
            normalize_wattpad_url(new_url)
            if new_platform == "wattpad"
            else normalize_ao3_url(new_url)
        )

        # Same-URL guard
        existing_url = (
            old_story["wattpad_url"] if new_platform == "wattpad"
            else old_story["ao3_url"]
        )
        if existing_url and existing_url == new_normalized:
            await status_msg.edit(
                content="❌ That's already the link saved for this story — nothing to change!"
            )
            return

        # Fetch metadata
        new_label = "Wattpad" if new_platform == "wattpad" else "AO3"
        await status_msg.edit(content=f"⏳ Fetching from {new_label}…")

        _safe_note = "\n-# Your story data has not been changed."
        if new_platform == "wattpad":
            try:
                data = await asyncio.to_thread(fetch_wattpad_metadata, new_normalized)
            except WattpadError as e:
                await status_msg.edit(content=f"❌ {e.user_message}{_safe_note}")
                return
            data["summary"] = data.get("description", "No summary available.")
            data["rating"]  = "Mature" if data.get("mature") else None
        else:
            try:
                data = await asyncio.to_thread(fetch_ao3_metadata, new_normalized)
            except Exception as e:
                await status_msg.edit(content=f"❌ Couldn't fetch that AO3 link:\n`{e}`{_safe_note}")
                return

        data["_platform"] = new_platform
        data["_new_url"]  = new_normalized

        # Build confirm embed
        old_platform = old_story["platform"] or "ao3"
        old_label    = "Wattpad" if old_platform == "wattpad" else "AO3"
        old_url      = old_story["wattpad_url"] if old_platform == "wattpad" else old_story["ao3_url"]

        if old_platform != new_platform:
            desc = (
                f"This will move **{data['title']}** from **{old_label}** to **{new_label}**.\n\n"
                f"All metadata will be refreshed from the new link.\n"
                f"-# Characters and fanart are preserved."
            )
        else:
            desc = (
                f"This will update the **{old_label}** link for **{data['title']}**.\n\n"
                f"**Before:** {old_url}\n"
                f"**After:** {new_normalized}\n\n"
                f"-# Metadata will be refreshed. Characters and fanart are preserved."
            )

        embed = discord.Embed(
            title="🔄 Confirm Domain Swap",
            description=desc,
            color=discord.Color.orange(),
        )

        confirm_view = SwapDomainConfirmView(story_id, data, old_story, status_msg)
        await status_msg.edit(content=None, embed=embed, view=confirm_view)

    except Exception as e:
        try:
            await status_msg.edit(
                content=f"❌ Error:\n`{e}`\n-# Your story data has not been changed.",
                embed=None, view=None
            )
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

    _platform = data.get("_platform") or old_story["platform"] or "ao3"
    if _platform == "wattpad":
        story_url = old_story["wattpad_url"] or ""
        link_line = f"\n🔗 [Read on Wattpad]({story_url})" if story_url else ""
    else:
        story_url = old_story["ao3_url"] or ""
        link_line = f"\n🔗 [Read on AO3]({story_url})" if story_url else ""

    embed = discord.Embed(
        title=f"📚 {data['title']} — New Update!",
        description=(
            f"**{interaction.user.display_name}** just uploaded a new chapter!\n\n"
            f"{chapter_lines}"
            f"{link_line}"
        ),
        color=discord.Color.from_rgb(100, 200, 255)
    )

    cover = old_story["cover_url"]
    if cover:
        embed.set_thumbnail(url=cover)

    try:
        await channel.send(embed=embed)
    except Exception:
        pass
