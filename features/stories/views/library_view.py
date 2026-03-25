import discord
from discord import ui
from bs4 import BeautifulSoup
import asyncio

from ui.base_list_view import BaseListView
from embeds.character_embeds import build_character_card
from features.characters.views.characters_view import StoryCharactersView
from features.stories.views.showcase_view import ShowcaseView
from embeds.story_notes_embed import build_story_notes_embed
from database import get_story_by_id

from database import (
    get_all_stories_sorted,
    get_user_id,
    get_story_progress,
    set_story_progress,
    get_characters_by_story,
    get_chapters_by_story,
    get_discord_id_by_story,
    get_stories_by_discord_user,
    get_tags_by_story,
    has_story_badge,
    update_story_badge,
    get_fanart_by_story
)


# =====================================================
# HELPERS
# =====================================================

def story_to_dict(row):
    """
    Convert sqlite Row or tuple into a consistent dict
    so the rest of the UI never depends on tuple indexes.
    """
    if isinstance(row, dict):
        return row

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
        "music_url":         row[14] if len(row) > 14 else None,
        "rating":            row[15] if len(row) > 15 else None,
        "platform":          row[16] if len(row) > 16 else None,
        "wattpad_reads":     row[17] if len(row) > 17 else None,
        "wattpad_votes":     row[18] if len(row) > 18 else None,
        "wattpad_comments":  row[19] if len(row) > 19 else None,
        "ao3_hits":          row[20] if len(row) > 20 else None,
        "ao3_kudos":         row[21] if len(row) > 21 else None,
        "ao3_comments":      row[22] if len(row) > 22 else None,
        "ao3_bookmarks":     row[23] if len(row) > 23 else None,
    }

class ContinueReadingView(ui.View):

    def __init__(self, url=None, chapter_links=None, label=None):
        """
        chapter_links: list of (label, url) tuples from chapbuild, or None.
        url: fallback link.
        label: button label for the fallback link.
        """
        super().__init__(timeout=60)

        if chapter_links:
            for lbl, link_url in chapter_links:
                self.add_item(
                    ui.Button(
                        label=f"▶ {lbl}",
                        style=discord.ButtonStyle.link,
                        url=link_url,
                    )
                )
        elif url:
            self.add_item(
                ui.Button(
                    label=label or "▶ Open AO3",
                    style=discord.ButtonStyle.link,
                    url=url,
                )
            )

def build_progress_bar(percent, length=10):
    filled = int((percent / 100) * length)
    empty = length - filled

    return "▰" * filled + "▱" * empty

def clean_summary(summary):
    if not summary:
        return "No summary."
    soup = BeautifulSoup(summary, "html.parser")
    return soup.get_text("\n", strip=True)


def build_continue_reading_link(ao3_url, progress, total):

    work_id = ao3_url.rstrip("/").split("/")[-1]

    # if finished → go to top of full work
    if progress >= total:
        return (
            f"https://archiveofourown.org/works/"
            f"{work_id}?view_full_work=true"
        )

    # next chapter anchor
    next_chapter = progress + 1

    return (
        f"https://archiveofourown.org/works/"
        f"{work_id}?view_full_work=true"
        f"#chapter-{next_chapter}"
    )

# =====================================================
# LIBRARY JUMP MODAL
# =====================================================

class _LibraryJumpModal(discord.ui.Modal, title="Jump to Page"):
    page_num = discord.ui.TextInput(
        label="Page number",
        placeholder="e.g. 3",
        max_length=4,
        required=True,
    )

    def __init__(self, library_view):
        super().__init__()
        self.library_view = library_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            num = int(self.page_num.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid page number.", ephemeral=True, delete_after=4
            )
            return
        total = self.library_view.total_pages
        if num < 1 or num > total:
            await interaction.response.send_message(
                f"❌ Page must be between 1 and {total}.", ephemeral=True, delete_after=4
            )
            return
        self.library_view.page = num - 1
        self.library_view.mode = "browse"
        self.library_view.current_item = None
        self.library_view.refresh_items()
        self.library_view.refresh_ui()
        await interaction.response.edit_message(
            embed=self.library_view.generate_list_embed(),
            view=self.library_view,
        )


# =====================================================
# LIBRARY VIEW
# =====================================================

class LibraryView(BaseListView):

    def __init__(self, stories, title, user, per_page=5, filtered_stories=None, tag_stories=None, tag_title=None):

        self.title = title
        self.mode = "browse"
        self.sort_type = "alphabetical"

        # If this is a tag-filtered view, store the filtered set separately
        # so sort/pagination always operates within it, not the full library.
        # filtered_stories=None means "show everything" (normal /library).
        self.filtered_stories = filtered_stories

        # For libsearch flip-flop: remember the original tag results + title
        # so "Back to Tags" can return to them after "Full Library" is clicked.
        self.tag_stories = tag_stories      # the tag-filtered story list
        self.tag_title = tag_title          # e.g. "📚 Stories tagged: romance"
        self.showing_full_library = False   # are we currently in full-library mode?

        super().__init__(stories, user, per_page)

        # ⭐ create UI components ONCE
        self.story_select = self.StorySelect(self)
        self.explore_select = self.ExploreSelect(self)

        self.refresh_ui()
        self.toggle_progress_buttons(False)

    # ---------- UI ----------
    def refresh_ui(self):

        self.clear_items()
        self.build_rows()

        # ==========================
        # BROWSE MODE
        # ==========================
        if self.mode == "browse":

            # Row 0 — dropdown (rebuild every refresh so page contents stay current)
            self.story_select = self.StorySelect(self)
            self.story_select.row = 0
            self.add_item(self.story_select)

            # Row 1 — navigation buttons
            self.add_item(self.prev)
            self.add_item(self.sort_button)
            if self.filtered_stories is not None:
                self.add_item(self.full_library_button)
            elif self.showing_full_library and self.tag_stories is not None:
                self.add_item(self.back_to_tags_button)
            self.add_item(self.jump_button)
            self.add_item(self.next)

        # ==========================
        # STORY MODE
        # ==========================

        elif self.mode == "story":

            # ---------- CHARACTER COUNT LABEL ----------
            if self.current_item:
                story = story_to_dict(self.current_item)
                story_id = story["id"]
                chars = get_characters_by_story(story_id)
                count = len(chars)
                fanart_count = len(get_fanart_by_story(story_id))
                from database import get_all_comments_unified
                comment_count = len(get_all_comments_unified(story_id))
            else:
                count = 0
                fanart_count = 0
                comment_count = 0

            self.story_characters.label = f"🧬 Cast ({count})"

            # rebuild dropdown every refresh so the fanart count stays current
            self.explore_select = self.ExploreSelect(self, fanart_count=fanart_count, comment_count=comment_count)

            # ---------- ROW 0: +  -  Resume ----------
            self.add_progress.row = 0
            self.minus_progress.row = 0
            self.continue_reading.row = 0

            self.add_item(self.add_progress)
            self.add_item(self.minus_progress)
            self.add_item(self.continue_reading)

            # ---------- ROW 1 ----------
            self.explore_select.row = 1
            self.add_item(self.explore_select)

            # ---------- ROW 2 ----------
            self.story_characters.row = 2
            self.view_chapters.row = 2
            self.view_author.row = 2
            self.return_to_library.row = 2

            self.add_item(self.story_characters)
            self.add_item(self.view_chapters)
            self.add_item(self.view_author)
            self.add_item(self.return_to_library)

        self.update_buttons()

    def update_buttons(self):
        for item in self.children:
            if isinstance(item, ui.Button):
                if item.label == "⬅️":
                    item.disabled = self.page == 0
                if item.label == "➡️":
                    item.disabled = self.page >= self.total_pages - 1
                if item.label == "Jump to...":
                    item.disabled = self.total_pages <= 1

    # ---------- DATA ----------
    def refresh_items(self):

        if self.filtered_stories is not None:
            # Tag-filtered mode: sort within the filtered set only
            self.items = list(self.filtered_stories)
        else:
            self.items = get_all_stories_sorted("alphabetical")
        self.total_pages = max(1, ((len(self.items)-1)//self.per_page)+1)

        uid = get_user_id(str(self.user.id))

        if self.sort_type == "most_completed":

            self.items.sort(
                key=lambda s: (
                    get_story_progress(uid, story_to_dict(s)["id"]) /
                    story_to_dict(s)["chapter_count"]
                    if story_to_dict(s)["chapter_count"] else 0
                ),
                reverse=True
            )

        elif self.sort_type == "reverse_alphabetical":
            self.items.sort(
                key=lambda s: story_to_dict(s)["title"].lower(),
                reverse=True
            )
        
        elif self.sort_type == "most_words":
            self.items.sort(
                key=lambda s: story_to_dict(s)["word_count"] or 0,
                reverse=True
            )

        elif self.sort_type == "least_words":
            self.items.sort(
                key=lambda s: story_to_dict(s)["word_count"] or 00
            )

        elif self.sort_type == "least_completed":

            self.items.sort(
                key=lambda s: (
                    get_story_progress(uid, story_to_dict(s)["id"]) /
                    story_to_dict(s)["chapter_count"]
                    if story_to_dict(s)["chapter_count"] else 0
                ),
                reverse=True
            )

        # ⭐ safety
        if self.page >= self.total_pages:
            self.page = max(0, self.total_pages - 1)

    def build_rows(self):

        if self.mode == "browse":

            self.story_select.row = 0

            self.prev.row = 1
            self.sort_button.row = 1
            self.full_library_button.row = 1
            self.back_to_tags_button.row = 1
            self.jump_button.row = 1
            self.next.row = 1

        elif self.mode == "story":

            # ROW 0 — Progress + Resume
            self.add_progress.row = 0
            self.minus_progress.row = 0
            self.continue_reading.row = 0

            # ROW 1 — Explore
            self.explore_select.row = 1

            # ROW 2 — Navigation
            self.story_characters.row = 2
            self.view_author.row = 2
            self.return_to_library.row = 2

    # ---------- EMBEDS ----------
    def generate_list_embed(self):

        self.refresh_items()

        embed = discord.Embed(
            title=self.title,
            color=discord.Color.blurple()
        )

        embed.set_thumbnail(url="https://images-wixmp-ed30a86b8c4ca887773594c2.wixmp.com/f/889ced1b-f394-4def-924c-4f920c92e0ac/dkvyphd-38e7fc4c-a349-4f24-bbbc-90d96dbb602b.png?token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1cm46YXBwOjdlMGQxODg5ODIyNjQzNzNhNWYwZDQxNWVhMGQyNmUwIiwiaXNzIjoidXJuOmFwcDo3ZTBkMTg4OTgyMjY0MzczYTVmMGQ0MTVlYTBkMjZlMCIsIm9iaiI6W1t7InBhdGgiOiIvZi84ODljZWQxYi1mMzk0LTRkZWYtOTI0Yy00ZjkyMGM5MmUwYWMvZGt2eXBoZC0zOGU3ZmM0Yy1hMzQ5LTRmMjQtYmJiYy05MGQ5NmRiYjYwMmIucG5nIn1dXSwiYXVkIjpbInVybjpzZXJ2aWNlOmZpbGUuZG93bmxvYWQiXX0.CJlMPo-23sO7fwEZGNureydkCtLf5Ma8ZkDXzXOYocU")

        start = self.page * self.per_page
        chunk = self.items[start:start+self.per_page]
        uid = get_user_id(str(self.user.id))

        for idx, (i, s) in enumerate(zip(range(start + 1, start + len(chunk) + 1), chunk)):

            story = story_to_dict(s)

            title = story["title"]
            ch = story["chapter_count"]
            upd = story["library_updated"]
            words = story["word_count"]
            summ = story["summary"]
            ao3 = story["ao3_url"]
            user = story["author"]
            cover = story["cover_url"]
            sid = story["id"]

            progress = get_story_progress(uid, sid) or 0
            percent = int((progress / ch) * 100) if ch else 0

            if percent == 100:
                bar = "✨ " + build_progress_bar(percent) + " ✨"
            else:
                bar = build_progress_bar(percent)

            # ⭐ Badge check
            badge = " 🏅✨" if has_story_badge(uid, sid) else ""

            preview = (summ[:120] + "...") if summ else "No summary."

            is_last = idx == len(chunk) - 1
            divider = "" if is_last else "\n\n💖 ── ✦ ─────────────── ✦ ── 💖\n"

            embed.add_field(
                name=f"**{i}.** 📚 {title}{badge} — {percent}% Complete",
                value=(
                    f"⚡ {ch} chapters • {words:,} words\n"
                    f"🧩 Uploaded by: {user}\n"
                    f"📝 *{preview}*\n{bar}{divider}"
                ),
                inline=False
            )

        embed.set_footer(text=f"Page {self.page+1}/{self.total_pages}")
        return embed
        

    def generate_detail_embed(self, story):

        story = story_to_dict(story)

        uid = get_user_id(str(self.user.id))

        progress = get_story_progress(uid, story["id"]) or 0
        percent = int((progress / story["chapter_count"]) * 100) if story["chapter_count"] else 0

        if percent == 100:
            bar = "✨ " + build_progress_bar(percent) + " ✨"
        else:
            bar = build_progress_bar(percent)

        title = story["title"]
        badge = "🏅 " if has_story_badge(uid, story["id"]) else ""
        ch = story["chapter_count"]
        upd = story["library_updated"]
        words = story["word_count"]
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

        # ---------- WATTPAD STATS ----------
        wp_reads    = story.get("wattpad_reads")
        wp_votes    = story.get("wattpad_votes")
        wp_comments = story.get("wattpad_comments")

        if any(v is not None for v in (wp_reads, wp_votes, wp_comments)):
            parts = []
            if wp_reads    is not None: parts.append(f"👁️ **{wp_reads:,}** reads")
            if wp_votes    is not None: parts.append(f"🩷 **{wp_votes:,}** votes")
            if wp_comments is not None: parts.append(f"💬 **{wp_comments:,}** comments")
            embed.add_field(
                name="\u200b",
                value="  ·  ".join(parts) + "\n─── ✦ ───",
                inline=False,
            )

        # ---------- AO3 STATS ----------
        ao3_hits     = story.get("ao3_hits")
        ao3_kudos    = story.get("ao3_kudos")
        ao3_comments = story.get("ao3_comments")

        if any(v is not None for v in (ao3_hits, ao3_kudos, ao3_comments)):
            parts = []
            if ao3_hits     is not None: parts.append(f"👁️ **{ao3_hits:,}** hits")
            if ao3_kudos    is not None: parts.append(f"🩷 **{ao3_kudos:,}** kudos")
            if ao3_comments is not None: parts.append(f"💬 **{ao3_comments:,}** comments")
            embed.add_field(
                name="\u200b",
                value="  ·  ".join(parts) + "\n─── ✦ ───",
                inline=False,
            )

        # ---------- SUMMARY ----------
        summary_text = clean_summary(summ) or "No summary available."

        embed.add_field(
            name="✨ Summary",
            value="\n".join([f"> {line}" for line in summary_text.split("\n")]),
            inline=False
        )

        # ---------- TAGS ----------
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

        # ---------- RATING ----------
        rating = story.get("rating")

        if rating:

            embed.add_field(
                name="🔞 Rating",
                value=f"`{rating}`",
                inline=False
            )

        # ---------- STORY INFO ----------
        platform = story.get("platform") or ("wattpad" if story.get("wattpad_url") else "ao3")
        platform_label = "Wattpad" if platform == "wattpad" else "AO3"

        embed.add_field(
            name="🌸 Story Info",
            value=(
                f"**Author** • {author}\n"
                f"**Platform** • {platform_label}\n"
                f"**Chapters** • {ch}\n"
                f"**Words** • {words:,}"
            ),
            inline=True
        )

        badge_line = "\n> 🏅 Badge Earned" if has_story_badge(uid, story["id"]) else ""

        # ---------- PROGRESS ----------
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
        link_list = []

        if platform == "wattpad":
            wattpad_url = story.get("wattpad_url")
            if wattpad_url:
                link_list.append(f"[Wattpad]({wattpad_url})")
        elif ao3:
            link_list.append(f"[AO3]({ao3})")

        extra1_title = story["extra_link_title"]
        extra1_url = story["extra_link_url"]

        extra2_title = story["extra_link2_title"]
        extra2_url = story["extra_link2_url"]

        if extra1_title and extra1_url:
            link_list.append(f"[{extra1_title}]({extra1_url})")

        if extra2_title and extra2_url:
            link_list.append(f"[{extra2_title}]({extra2_url})")

        links = " ✦ ".join(link_list)

        embed.add_field(
            name="🔗 Read",
            value=links,
            inline=False
        )

        # ---------- MUSIC PLAYLIST ----------
        if music:
            embed.add_field(
                name="🎵 Music Playlist",
                value=f"[Listen While Reading]({music})",
                inline=True
            )

        # ---------- COVER IMAGE ----------
        from pad_placeholder import is_placeholder, get_placeholder_url
        no_cover = is_placeholder(cover)
        if not no_cover:
            embed.set_image(url=cover)
        else:
            embed.set_image(url=get_placeholder_url())
            embed.add_field(
                name="\u200b",
                value=(
                    "─── ✦ ───\n"
                    "-# 🖼️ No cover added yet! Use `/fic build` to add a cover image."
                ),
                inline=False,
            )

        embed.set_footer(
            text=f"Last Updated • {upd}"
        )

        return embed

    # ---------- BUTTON HELPERS ----------
    def toggle_progress_buttons(self, enabled):
        for item in self.children:
            if isinstance(item, ui.Button):
                if item.label in ["➕", "➖", "▶ Resume"]:
                    item.disabled = not enabled

    # ---------- BUTTONS ----------
    @ui.button(label="➕", style=discord.ButtonStyle.primary)
    async def add_progress(self, interaction, button):
        if not self.current_item:
            await interaction.response.send_message("Select a story first.", ephemeral=True)
            return

        s = self.current_item
        uid = get_user_id(str(interaction.user.id))

        if not uid:
            await interaction.response.send_message(
                "User profile missing. Try reopening /library.",
                ephemeral=True
            )
            return
        
        story = story_to_dict(s)

        cur = get_story_progress(uid, story["id"]) or 0
        had_badge = has_story_badge(uid, story["id"])

        # Don't grant credits if already at the last chapter
        if cur >= story["chapter_count"]:
            await interaction.response.edit_message(
                embed=self.generate_detail_embed(s),
                view=self
            )
            return

        new_chapter_num = cur + 1
        set_story_progress(uid, story["id"], new_chapter_num)
        update_story_badge(uid, story["id"])

        earned_badge = has_story_badge(uid, story["id"]) and not had_badge

        # ── Crystal reward — once per unique chapter ever ──
        from database import get_chapter_id_by_number, grant_chapter_read_credit
        chapter_id = get_chapter_id_by_number(story["id"], new_chapter_num)
        crystal_msg = ""
        if chapter_id:
            granted, new_balance = grant_chapter_read_credit(uid, chapter_id)
            if granted:
                crystal_msg = f"💎 +250 crystals earned  ·  {new_balance:,} total"

        await interaction.response.edit_message(
            embed=self.generate_detail_embed(s),
            view=self
        )

        if earned_badge or crystal_msg:
            lines = []
            if earned_badge:
                lines.append(f"🏅 **Badge Earned!**  You completed **{story['title']}**!")
            if crystal_msg:
                lines.append(f"-# {crystal_msg}")

            msg = await interaction.followup.send(
                "\n".join(lines),
                ephemeral=True
            )

            await asyncio.sleep(1)

            try:
                await msg.delete()
            except:
                pass

    @ui.button(
        label="📖 Library",
        style=discord.ButtonStyle.success
    )
    async def return_to_library(self, interaction, button):

        # switch mode
        self.mode = "browse"

        # clear selected story
        self.current_item = None

        # rebuild layout
        self.refresh_items()
        self.refresh_ui()

        await interaction.response.edit_message(
            embed=self.generate_list_embed(),
            view=self
        )

    @ui.button(label="🔤 Sort: A-Z", style=discord.ButtonStyle.primary)
    async def sort_button(self, interaction, button):

        # cycle modes
        if self.sort_type == "alphabetical":
            self.sort_type = "reverse_alphabetical"

        elif self.sort_type == "reverse_alphabetical":
            self.sort_type = "most_completed"

        elif self.sort_type == "most_completed":
            self.sort_type = "least_completed"

        elif self.sort_type == "least_completed":
            self.sort_type = "most_words"

        elif self.sort_type == "most_words":
            self.sort_type = "least_words"

        else:
            self.sort_type = "alphabetical"

        # update label (⭐ important)
        if self.sort_type == "alphabetical":
            button.label = "🔤 Sort: A-Z"

        elif self.sort_type == "reverse_alphabetical":
            button.label = "🔠 Sort: Z-A"

        elif self.sort_type == "most_completed":
            button.label = "📈 Sort: Most read"

        elif self.sort_type == "least_completed":
            button.label = "📉 Sort: Least read"

        elif self.sort_type == "most_words":
            button.label = "📝 Sort: Most words"

        else:
            button.label = "✂️ Sort: Least words"

        self.mode = "browse"
        self.refresh_items()
        self.refresh_ui()

        await interaction.response.edit_message(
            embed=self.generate_list_embed(),
            view=self
        )

    @ui.button(label="Jump to...", style=discord.ButtonStyle.success)
    async def jump_button(self, interaction, button):
        await interaction.response.send_modal(_LibraryJumpModal(self))

    @ui.button(label="📚 Full Library", style=discord.ButtonStyle.success)
    async def full_library_button(self, interaction, button):
        """Switch from a tag-filtered view to the full library (flip-flop aware)."""
        # Remember the tag context so we can return to it
        self.showing_full_library = True
        self.filtered_stories = None
        self.title = "📚 Global Library"
        self.sort_type = "alphabetical"
        self.page = 0
        self.mode = "browse"
        self.refresh_items()
        self.refresh_ui()

        await interaction.response.edit_message(
            embed=self.generate_list_embed(),
            view=self
        )

    @ui.button(label="🏷️ Back to Tags", style=discord.ButtonStyle.secondary)
    async def back_to_tags_button(self, interaction, button):
        """Return to the tag-filtered view from the full library."""
        self.showing_full_library = False
        self.filtered_stories = self.tag_stories
        self.title = self.tag_title
        self.sort_type = "alphabetical"
        self.page = 0
        self.mode = "browse"
        self.refresh_items()
        self.refresh_ui()

        await interaction.response.edit_message(
            embed=self.generate_list_embed(),
            view=self
        )

    @ui.button(label="🧬 Characters", style=discord.ButtonStyle.primary)
    async def story_characters(self, interaction, button):

        if not self.current_item:
            await interaction.response.send_message(
                "Open a story first.",
                ephemeral=True
            )
            return

        story = story_to_dict(self.current_item)
        story_id = story["id"]

        chars = get_characters_by_story(story_id)

        if not chars:
            await interaction.response.send_message(
                "No characters to report.",
                ephemeral=True
            )
            return

        view = StoryCharactersView(
            chars,
            self,
            story_title=story["title"],
            viewer=self.user
        )

        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view
        )

    @ui.button(label="👤 Author", style=discord.ButtonStyle.primary)
    async def view_author(self, interaction, button):

        if not self.current_item:
            await interaction.response.send_message(
                "Open a story first.",
                ephemeral=True
            )
            return

        story = story_to_dict(self.current_item)
        story_id = story["id"]

        # get author's discord id from DB
        discord_id = get_discord_id_by_story(story_id)

        if not discord_id:
            await interaction.response.send_message(
                "Author profile not found.",
                ephemeral=True
            )
            return

        # ⭐ get LIVE Discord member
        target_user = interaction.guild.get_member(int(discord_id))

        # fallback — fetch from API
        if not target_user:
            try:
                target_user = await interaction.guild.fetch_member(
                    int(discord_id)
                )
            except discord.NotFound:
                await interaction.response.send_message(
                    "Author is not in this server.",
                    ephemeral=True
                )
                return

        stories = get_stories_by_discord_user(discord_id)

        if not stories:
            await interaction.response.send_message(
                "This author has no showcase.",
                ephemeral=True
            )
            return

        # ⭐ create showcase view (LIBRARY CONTEXT)
        view = ShowcaseView(
            stories,
            interaction.user,
            target_user,
            source="library"   # ← IMPORTANT
        )

        # ⭐ allow back navigation
        view.parent_view = self

        await interaction.response.edit_message(
            embed=view.generate_current_embed(),
            view=view
        )

    @ui.button(label="✔️", style=discord.ButtonStyle.success)
    async def mark_finished(self, interaction, button):
        s = self.current_item
        uid = get_user_id(str(interaction.user.id))

        if not uid:
            await interaction.response.send_message(
                "User profile missing. Try reopening /library.",
                ephemeral=True
            )
            return
        
        story = story_to_dict(s)

        had_badge = has_story_badge(uid, story["id"])

        set_story_progress(
            uid,
            story["id"],
            story["chapter_count"]
        )

        update_story_badge(uid, story["id"])

        earned_badge = has_story_badge(uid, story["id"]) and not had_badge

        await interaction.response.edit_message(
            embed=self.generate_detail_embed(s),
            view=self
        )

        if earned_badge:

            msg = await interaction.followup.send(
                f"🏅 **Badge Earned!**\nYou completed **{story['title']}**!",
                ephemeral=True
            )

            await asyncio.sleep(3)

            try:
                await msg.delete()
            except:
                pass

    @ui.button(label="🔄", style=discord.ButtonStyle.success)
    async def reset_progress(self, interaction, button):

        s = self.current_item
        uid = get_user_id(str(interaction.user.id))

        if not uid:
            await interaction.response.send_message(
                "User profile missing. Try reopening /library.",
                ephemeral=True
            )
            return
        
        story = story_to_dict(s)

        set_story_progress(
            uid,
            story["id"],
            0
        )
        update_story_badge(uid, story["id"])

        await interaction.response.edit_message(
            embed=self.generate_detail_embed(s),
            view=self
        )

    @ui.button(label="📖 Chapters", style=discord.ButtonStyle.primary)
    async def view_chapters(self, interaction, button):

        if not self.current_item:
            await interaction.response.send_message("Select a story first.", ephemeral=True)
            return

        from features.chapters.chapter_view import ChapterScrollView
        from database import get_chapters_full

        story = story_to_dict(self.current_item)
        chapters = get_chapters_full(story["id"])

        if not chapters:
            await interaction.response.send_message(
                "No chapters found for this story yet.", ephemeral=True
            )
            return

        # Start from where the reader left off
        uid  = get_user_id(str(interaction.user.id))
        prog = get_story_progress(uid, story["id"]) or 0
        start = max(0, min(prog, len(chapters) - 1))

        view = ChapterScrollView(
            story["id"], story["title"], chapters,
            interaction.user, parent_view=self, start_index=start,
            cover_url=story.get("cover_url")
        )
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    @ui.button(label="▶ Resume", style=discord.ButtonStyle.success)
    async def continue_reading(self, interaction, button):

        if not self.current_item:
            await interaction.response.send_message(
                "Select a story first.",
                ephemeral=True
            )
            return

        s = self.current_item
        uid = get_user_id(str(interaction.user.id))

        story = story_to_dict(s)
        prog = get_story_progress(uid, story["id"]) or 0
        chapter_num = min(prog + 1, story["chapter_count"])

        # ── Resolve target chapter and build dual-platform links ─────────────
        chapter_links = []
        target_ch = None
        try:
            from database import get_chapters_full
            chapters = get_chapters_full(story["id"])
            target_ch = next(
                (c for c in chapters if c.get("chapter_number") == chapter_num), None
            )
            if target_ch is None and chapters:
                idx = min(chapter_num - 1, len(chapters) - 1)
                target_ch = chapters[idx]
        except Exception:
            pass

        _platform = story.get("platform") or ("wattpad" if story.get("wattpad_url") else "ao3")
        ch_title  = (target_ch.get("chapter_title") or "") if target_ch else ""

        if _platform == "wattpad":
            # Primary: Wattpad deep link (auto-stored part URL or story root)
            wp_url = (
                (target_ch.get("chapter_url") if target_ch else None)
                or story.get("wattpad_url")
            )
            if wp_url:
                lbl = f"Wattpad — {ch_title}"[:75] if ch_title else "Wattpad"
                chapter_links.append((lbl, wp_url))
            # Alt: AO3 chapter URL (auto-stored when AO3 mirror linked or from chapbuild)
            ao3_ch_url = target_ch.get("chapter_ao3_url") if target_ch else None
            if ao3_ch_url:
                lbl = f"AO3 — {ch_title}"[:75] if ch_title else "AO3"
                chapter_links.append((lbl, ao3_ch_url))
        else:
            # Primary: AO3 chapter deep link (auto-stored) or chapter-offset URL
            ao3_ch_url = target_ch.get("chapter_url") if target_ch else None
            ao3_url    = story.get("ao3_url")
            if ao3_ch_url:
                lbl = f"AO3 — {ch_title}"[:75] if ch_title else "AO3"
                chapter_links.append((lbl, ao3_ch_url))
            elif ao3_url:
                fallback = build_continue_reading_link(ao3_url, prog, story["chapter_count"])
                if fallback:
                    lbl = f"AO3 — {ch_title}"[:75] if ch_title else "AO3"
                    chapter_links.append((lbl, fallback))
            # Alt: Wattpad chapter URL (auto-stored when Wattpad mirror linked or from chapbuild)
            wp_ch_url = target_ch.get("chapter_wattpad_url") if target_ch else None
            if wp_ch_url:
                lbl = f"Wattpad — {ch_title}"[:75] if ch_title else "Wattpad"
                chapter_links.append((lbl, wp_ch_url))

        await interaction.response.send_message(
            f"📖 Continuing at **Chapter {chapter_num}**…\n"
            "⚡ Jump back into the story!",
            view=ContinueReadingView(chapter_links=chapter_links or None),
            ephemeral=True,
            delete_after=7,
        )

    @ui.button(label="➖", style=discord.ButtonStyle.primary)
    async def minus_progress(self, interaction, button):

        if not self.current_item:
            return

        s = self.current_item
        uid = get_user_id(str(interaction.user.id))

        if not uid:
            await interaction.response.send_message(
                "User profile missing. Try reopening /library.",
                ephemeral=True
            )
            return

        story = story_to_dict(s)

        cur = get_story_progress(uid, story["id"]) or 0
        set_story_progress(
            uid,
            story["id"],
            max(cur - 1, 0)
        )
        update_story_badge(uid, story["id"])

        await interaction.response.edit_message(
            embed=self.generate_detail_embed(s),
            view=self
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:

        # only allow the original user
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This library session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False

        return True
    
    async def on_timeout(self):

        # disable ALL components
        for item in self.children:
            item.disabled = True

        # safely edit original message
        try:
            await self.message.edit(view=self)
        except Exception:
            pass

    # ---------- DROPDOWNS ----------
    
    class StorySelect(ui.Select):
        def __init__(self, view_ref):
            self.view_ref = view_ref
            start = view_ref.page * view_ref.per_page
            chunk = view_ref.items[start:start+view_ref.per_page]

            options = [
                discord.SelectOption(
                    label=story_to_dict(s)["title"][:100],
                    value=str(i)  # local index within the current page
                )
                for i, s in enumerate(chunk)
            ]

            super().__init__(placeholder="🎉 Dive Into a Fic...", options=options)

        async def callback(self, interaction):

            local_index = int(self.values[0])
            start = self.view_ref.page * self.view_ref.per_page
            story = self.view_ref.items[start + local_index]

            # store selected story
            self.view_ref.current_item = story

            # ⭐ enter story mode
            self.view_ref.mode = "story"
            self.view_ref.refresh_ui()

            await interaction.response.edit_message(
                embed=self.view_ref.generate_detail_embed(story),
                view=self.view_ref
            )
    class ExploreSelect(ui.Select):

        def __init__(self, view_ref, fanart_count=0, comment_count=0):
            self.view_ref = view_ref

            fanart_label  = f"🎨 Fanart Gallery ({fanart_count})"  if fanart_count  > 0 else "🎨 Fanart Gallery"
            comment_label = f"💬 View Comments ({comment_count})"  if comment_count >= 0 else "💬 View Comments"

            options = [
                discord.SelectOption(
                    label="🎬 Extra Story Notes",
                    value="details"
                ),
                discord.SelectOption(
                    label=comment_label,
                    value="comments"
                ),
                discord.SelectOption(
                    label=fanart_label,
                    value="fanart"
                ),
            ]

            super().__init__(
                placeholder="✨ Explore Book...",
                options=options
            )

        async def callback(self, interaction):

            choice = self.values[0]

            story = story_to_dict(self.view_ref.current_item)

            # ---------- STORY NOTES ----------
            if choice == "details":

                from features.stories.views.story_extras_view import StoryExtrasView

                view = StoryExtrasView(
                    story_id=story["id"],
                    library_view=self.view_ref,
                    viewer=self.view_ref.user
                )

                await interaction.response.edit_message(
                    embed=view.build_embed(),
                    view=view
                )

            # ---------- COMMENTS ----------
            elif choice == "comments":

                from database import get_all_comments_unified
                from features.stories.views.library_comments_view import LibraryCommentsView

                all_comments = get_all_comments_unified(story["id"])

                view = LibraryCommentsView(
                    story=story,
                    comments=all_comments,
                    library_view=self.view_ref,
                    guild=interaction.guild
                )

                await interaction.response.edit_message(
                    embed=await view.build_embed(),
                    view=view
                )

            # ---------- FANART GALLERY ----------
            elif choice == "fanart":

                from database import get_fanart_by_story
                from features.fanart.views.library_fanart_view import LibraryFanartDetailView, LibraryFanartRosterDummy

                fanart = get_fanart_by_story(story["id"])

                if not fanart:
                    await interaction.response.defer()
                    msg = await interaction.followup.send(
                        "🎨 No fanart has been tagged for this story yet.",
                        ephemeral=True,
                        wait=True
                    )
                    await asyncio.sleep(3)
                    await msg.delete()
                    return

                detail = LibraryFanartDetailView(
                    fanarts=fanart,
                    index=0,
                    viewer=interaction.user,
                    library_view=self.view_ref
                )

                await interaction.response.edit_message(
                    embed=detail.build_embed(),
                    view=detail
                )