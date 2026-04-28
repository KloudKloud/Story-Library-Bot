import discord
from discord import ui
import asyncio
import datetime

from database import (
    get_chapters_full,
    get_comment_count_for_chapter,
    get_comments_for_chapter,
    add_comment,
    user_has_commented,
    get_user_id,
    grant_chapter_read_credit,
)
from ui import TimeoutMixin


# ─────────────────────────────────────────────────
# Chapter card embed builder
# ─────────────────────────────────────────────────

def build_chapter_embed(chapter: dict, story_title: str,
                        index: int, total: int,
                        comment_count: int,
                        cover_url: str = None) -> discord.Embed:

    num          = chapter.get("chapter_number", index)
    title        = chapter.get("chapter_title") or f"Chapter {num}"
    summary      = chapter.get("chapter_summary")
    image        = chapter.get("chapter_image_url")
    wattpad_url  = chapter.get("chapter_wattpad_url")
    direct_ao3   = chapter.get("chapter_ao3_url")
    auto_ao3     = chapter.get("chapter_url")

    embed = discord.Embed(
        title=f"📖  Chapter {num}  ·  {title}",
        color=discord.Color.dark_teal()
    )

    embed.description = f"-# 📚 {story_title}"

    # ── Summary ───────────────────────────────────
    if summary:
        embed.add_field(
            name="✨  Author's Note",
            value=(
                "\n\n".join(f"> {line}" for line in summary.splitlines() if line.strip())
                
            ),
            inline=False
        )

    # ── Read links ────────────────────────────────
    links = []
    if wattpad_url:
        links.append(f"[📖 Wattpad]({wattpad_url})")
    if direct_ao3:
        links.append(f"[🔗 AO3]({direct_ao3})")
    elif auto_ao3 and not wattpad_url:
        links.append(f"[🔗 AO3]({auto_ao3})")

    if links:
        embed.add_field(
            name="🔗  Read",
            value="  ·  ".join(links),
            inline=True
        )

    # ── Comments count ────────────────────────────
    embed.add_field(
        name="💬  Comments",
        value=str(comment_count),
        inline=True
    )

    # ── Reference image ───────────────────────────
    if image and image.startswith("http"):
        embed.set_image(url=image)

    if cover_url and cover_url.startswith("http"):
        embed.set_thumbnail(url=cover_url)

    embed.set_footer(text=f"Chapter {index} of {total}  ·  {story_title}")
    return embed


# ─────────────────────────────────────────────────
# Comment modal
# ─────────────────────────────────────────────────

class CommentModal(discord.ui.Modal, title="Leave a Comment"):

    content = discord.ui.TextInput(
        label="Your comment",
        style=discord.TextStyle.paragraph,
        placeholder="Share your thoughts on this chapter...",
        max_length=1000,
        required=True
    )

    def __init__(self, chapter_view: "ChapterScrollView"):
        super().__init__()
        self.chapter_view = chapter_view

    async def on_submit(self, interaction: discord.Interaction):
        cv  = self.chapter_view
        uid = get_user_id(str(interaction.user.id))
        ch  = cv.current_chapter()

        if not uid:
            await interaction.response.send_message(
                "No account found.", ephemeral=True
            )
            return

        add_comment(uid, cv.story_id, ch["id"], self.content.value)

        # Credit reward — once per chapter per user
        crystal_msg = ""
        granted, new_balance = grant_chapter_read_credit(uid, ch["id"])
        if granted:
            crystal_msg = f"\n-# 💎 +250 crystals earned  ·  {new_balance:,} total"

        await interaction.response.send_message(
            f"💬 Comment posted!{crystal_msg}",
            ephemeral=True,
            delete_after=1.5
        )

        # Refresh the chapter card to update comment count
        await cv.refresh(interaction)


# ─────────────────────────────────────────────────
# Comments list embed
# ─────────────────────────────────────────────────

def build_comments_embed(chapter: dict, story_title: str,
                         comments: list, page: int, total_pages: int) -> discord.Embed:

    num    = chapter.get("chapter_number")
    ctitle = chapter.get("chapter_title") or f"Chapter {num}"

    embed = discord.Embed(
        title=f"💬  Comments  ·  Chapter {num}: {ctitle}",
        color=discord.Color.blurple()
    )
    embed.description = f"-# 📚 {story_title}  ·  Page {page + 1} of {total_pages}"

    if not comments:
        embed.add_field(
            name="No comments yet",
            value="Be the first to leave a comment!",
            inline=False
        )
        return embed

    for c in comments:
        try:
            dt   = datetime.datetime.fromisoformat(c["created_at"])
            when = dt.strftime("%b %d, %Y")
        except Exception:
            when = c["created_at"]

        # display_name may be pre-resolved by the async caller, falls back to username
        display_name = c.get("display_name") or c["username"]

        embed.add_field(
            name=f"**{display_name}**  ·  {when}",
            value=f"> {c['content'][:300]}{'…' if len(c['content']) > 300 else ''}",
            inline=False
        )

    return embed


COMMENTS_PER_PAGE = 5


class CommentsView(TimeoutMixin, ui.View):
    """Read-only paginated comment browser for a single chapter."""

    def __init__(self, chapter: dict, story_title: str,
                 parent_view: "ChapterScrollView", guild=None):
        super().__init__(timeout=180)
        self.chapter      = chapter
        self.story_title  = story_title
        self.parent_view  = parent_view
        self.guild        = guild
        self.page         = 0
        self.viewer       = parent_view.viewer
        self._update()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    def _all_comments(self):
        return get_comments_for_chapter(self.chapter["id"])

    def _page_comments(self):
        all_c = self._all_comments()
        start = self.page * COMMENTS_PER_PAGE
        return all_c[start:start + COMMENTS_PER_PAGE]

    def _total_pages(self):
        all_c = self._all_comments()
        return max(1, (len(all_c) + COMMENTS_PER_PAGE - 1) // COMMENTS_PER_PAGE)

    def _update(self):
        tp = self._total_pages()
        self.prev_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= tp - 1

    async def build_embed(self) -> discord.Embed:
        comments = self._page_comments()

        # Resolve server display names via fetch_member (guaranteed, not cache-only)
        if self.guild:
            for c in comments:
                try:
                    member = self.guild.get_member(int(c["discord_id"]))
                    if not member:
                        member = await self.guild.fetch_member(int(c["discord_id"]))
                    if member:
                        c["display_name"] = member.display_name
                except Exception:
                    pass

        return build_comments_embed(
            self.chapter, self.story_title,
            comments, self.page, self._total_pages()
        )

    @ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary, row=0)
    async def prev_page(self, interaction: discord.Interaction, _):
        self.page = max(0, self.page - 1)
        self._update()
        await interaction.response.edit_message(embed=await self.build_embed(), view=self)

    @ui.button(label="📖 Back to Chapter", style=discord.ButtonStyle.primary, row=0)
    async def back_btn(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )

    @ui.button(emoji="➡️", style=discord.ButtonStyle.secondary, row=0)
    async def next_page(self, interaction: discord.Interaction, _):
        self.page = min(self._total_pages() - 1, self.page + 1)
        self._update()
        await interaction.response.edit_message(embed=await self.build_embed(), view=self)


# ─────────────────────────────────────────────────
# Jump to chapter modal
# ─────────────────────────────────────────────────

class JumpToChapterModal(discord.ui.Modal, title="Jump to Chapter"):

    chapter_num = discord.ui.TextInput(
        label="Chapter number",
        placeholder="e.g. 12",
        max_length=4,
        required=True
    )

    def __init__(self, scroll_view: "ChapterScrollView"):
        super().__init__()
        self.scroll_view = scroll_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            num = int(self.chapter_num.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid chapter number.", ephemeral=True, delete_after=4
            )
            return

        total = len(self.scroll_view.chapters)
        if num < 1 or num > total:
            await interaction.response.send_message(
                f"❌ Chapter must be between 1 and {total}.", ephemeral=True, delete_after=4
            )
            return

        self.scroll_view.index = num - 1
        self.scroll_view._rebuild_ui()
        await interaction.response.edit_message(
            embed=self.scroll_view.build_embed(),
            view=self.scroll_view
        )


# ─────────────────────────────────────────────────
# Main chapter scroll view
# ─────────────────────────────────────────────────

class ChapterScrollView(TimeoutMixin, ui.View):

    def __init__(self, story_id: int, story_title: str,
                 chapters: list, viewer: discord.Member,
                 parent_view=None, start_index: int = 0,
                 cover_url: str = None,
                 hide_comment: bool = False,
                 story_btn_label: str = "📕 Story"):
        super().__init__(timeout=300)
        self.story_id       = story_id
        self.story_title    = story_title
        self.chapters       = chapters
        self.viewer         = viewer
        self.parent_view    = parent_view
        self.index          = start_index
        self.cover_url      = cover_url
        self.hide_comment   = hide_comment
        self.story_btn_label = story_btn_label
        self._rebuild_ui()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    def current_chapter(self) -> dict:
        return self.chapters[self.index]

    def build_embed(self) -> discord.Embed:
        ch    = self.current_chapter()
        count = get_comment_count_for_chapter(ch["id"])
        return build_chapter_embed(
            ch, self.story_title,
            index=self.index + 1,
            total=len(self.chapters),
            comment_count=count,
            cover_url=self.cover_url
        )

    async def refresh(self, interaction: discord.Interaction):
        """Re-renders the current chapter card after a comment is posted."""
        self._rebuild_ui()
        try:
            await interaction.message.edit(embed=self.build_embed(), view=self)
        except Exception:
            pass

    def _rebuild_ui(self):
        self.clear_items()

        total = len(self.chapters)
        uid   = get_user_id(str(self.viewer.id))
        ch    = self.current_chapter()

        # ── Row 0: ⬅️  💬  🔢 Jump to...  📕 Story  ➡️ ─────────────
        prev = ui.Button(emoji="⬅️", style=discord.ButtonStyle.secondary,
                         row=0, disabled=self.index == 0)
        prev.callback = self._prev
        self.add_item(prev)

        if not self.hide_comment:
            already = user_has_commented(uid, ch["id"]) if uid else False
            comment_btn = ui.Button(
                emoji="💬",
                style=discord.ButtonStyle.primary,
                row=0
            )
            comment_btn.callback = self._comment
            self.add_item(comment_btn)

        jump_btn = ui.Button(
            label="🔢 Jump to...",
            style=discord.ButtonStyle.success,
            row=0
        )
        jump_btn.callback = self._jump
        self.add_item(jump_btn)

        if self.parent_view:
            back = ui.Button(label=self.story_btn_label, style=discord.ButtonStyle.primary, row=0)
            back.callback = self._back
            self.add_item(back)

        nxt = ui.Button(emoji="➡️", style=discord.ButtonStyle.secondary,
                        row=0, disabled=self.index >= total - 1)
        nxt.callback = self._next
        self.add_item(nxt)

        # ── Row 1: View Comments (only when comments exist) ──────────
        count = get_comment_count_for_chapter(ch["id"])
        is_last = (self.index >= total - 1)

        if is_last:
            # On the last chapter, also check for global comments
            from database import get_global_comment_count_for_story
            global_count = get_global_comment_count_for_story(self.story_id)
            if global_count > 0:
                global_btn = ui.Button(
                    label=f"🌐 Global Comments ({global_count})",
                    style=discord.ButtonStyle.success,
                    row=1
                )
                global_btn.callback = self._view_global_comments
                self.add_item(global_btn)

        if count > 0:
            view_comments_btn = ui.Button(
                label=f"👁️ View Comments ({count})",
                style=discord.ButtonStyle.success,
                row=1
            )
            view_comments_btn.callback = self._view_comments
            self.add_item(view_comments_btn)

    async def _prev(self, interaction: discord.Interaction):
        self.index = max(0, self.index - 1)
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.index = min(len(self.chapters) - 1, self.index + 1)
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _back(self, interaction: discord.Interaction):
        if self.parent_view:
            await interaction.response.edit_message(
                embed=self.parent_view.generate_detail_embed(self.parent_view.current_item),
                view=self.parent_view
            )

    async def _jump(self, interaction: discord.Interaction):
        await interaction.response.send_modal(JumpToChapterModal(self))

    async def _comment(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CommentModal(self))

    async def _view_comments(self, interaction: discord.Interaction):
        ch   = self.current_chapter()
        view = CommentsView(ch, self.story_title, parent_view=self, guild=interaction.guild)
        await interaction.response.edit_message(embed=await view.build_embed(), view=view)

    async def _view_global_comments(self, interaction: discord.Interaction):
        from database import get_global_comments_for_story
        comments = get_global_comments_for_story(self.story_id)
        view = GlobalCommentsView(
            comments, self.story_title, parent_view=self, guild=interaction.guild
        )
        await interaction.response.edit_message(embed=await view.build_embed(), view=view)

# ─────────────────────────────────────────────────
# Global comments browser (chapter_view internal)
# ─────────────────────────────────────────────────

def _build_global_comments_embed(comments: list, story_title: str,
                                  page: int, total_pages: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"🌐  Global Comments  ·  {story_title}",
        color=discord.Color.blurple()
    )
    embed.description = f"-# Page {page + 1} of {total_pages}"

    if not comments:
        embed.add_field(name="No global comments yet", value="Be the first!", inline=False)
        return embed

    COMMENTS_PER_PAGE = 7
    start   = page * COMMENTS_PER_PAGE
    chunk   = comments[start:start + COMMENTS_PER_PAGE]

    for c in chunk:
        try:
            import datetime
            dt   = datetime.datetime.fromisoformat(c["created_at"])
            when = dt.strftime("%b %d, %Y")
        except Exception:
            when = c["created_at"]
        display = c.get("display_name") or c["username"]
        embed.add_field(
            name=f"**{display}**  ·  {when}",
            value=f"> {c['content'][:300]}{'…' if len(c['content']) > 300 else ''}",
            inline=False
        )
    return embed


GLOBAL_COMMENTS_PER_PAGE = 7


class GlobalCommentsView(TimeoutMixin, ui.View):
    """Read-only global comments browser, opened from last chapter."""

    def __init__(self, comments: list, story_title: str,
                 parent_view, guild=None):
        super().__init__(timeout=180)
        self.comments    = comments
        self.story_title = story_title
        self.parent_view = parent_view
        self.guild       = guild
        self.page        = 0
        self.viewer      = parent_view.viewer
        self._update()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    def _total_pages(self):
        return max(1, (len(self.comments) + GLOBAL_COMMENTS_PER_PAGE - 1) // GLOBAL_COMMENTS_PER_PAGE)

    def _update(self):
        self.prev_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= self._total_pages() - 1

    async def build_embed(self) -> discord.Embed:
        if self.guild:
            start = self.page * GLOBAL_COMMENTS_PER_PAGE
            chunk = self.comments[start:start + GLOBAL_COMMENTS_PER_PAGE]
            for c in chunk:
                try:
                    member = self.guild.get_member(int(c["discord_id"]))
                    if not member:
                        member = await self.guild.fetch_member(int(c["discord_id"]))
                    if member:
                        c["display_name"] = member.display_name
                except Exception:
                    pass
        return _build_global_comments_embed(
            self.comments, self.story_title, self.page, self._total_pages()
        )

    @ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary, row=0)
    async def prev_page(self, interaction: discord.Interaction, _):
        self.page = max(0, self.page - 1)
        self._update()
        await interaction.response.edit_message(embed=await self.build_embed(), view=self)

    @ui.button(label="📖 Back to Chapter", style=discord.ButtonStyle.primary, row=0)
    async def back_btn(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )

    @ui.button(emoji="➡️", style=discord.ButtonStyle.secondary, row=0)
    async def next_page(self, interaction: discord.Interaction, _):
        self.page = min(self._total_pages() - 1, self.page + 1)
        self._update()
        await interaction.response.edit_message(embed=await self.build_embed(), view=self)