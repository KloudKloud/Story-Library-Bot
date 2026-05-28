"""
library_comments_view.py — paginated view of ALL comments for a story
(chapter comments + global comments), opened from the library Explore dropdown.
"""

import discord
from discord import ui
import datetime
from ui import TimeoutMixin

COMMENTS_PER_PAGE = 5


def build_library_comments_embed(story: dict, comments: list,
                                  page: int, total_pages: int) -> discord.Embed:
    title = story.get("title") or "Story"
    embed = discord.Embed(
        title=f"💬  All Comments  ·  {title}",
        color=discord.Color.blurple()
    )
    embed.description = f"-# Page {page + 1} of {total_pages}  ·  {len(comments)} total comment{'s' if len(comments) != 1 else ''}"

    start = page * COMMENTS_PER_PAGE
    chunk = comments[start:start + COMMENTS_PER_PAGE]

    if not chunk:
        embed.add_field(
            name="No comments yet",
            value="Be the first to leave one on a chapter or through the story stats page!",
            inline=False
        )
        return embed

    for c in chunk:
        try:
            dt   = datetime.datetime.fromisoformat(c["created_at"])
            when = dt.strftime("%b %d, %Y")
        except Exception:
            when = c.get("created_at", "")

        display = c.get("display_name") or c.get("username", "Unknown")

        # Chapter context
        ch_num   = c.get("chapter_number")
        ch_title = c.get("chapter_title")
        if ch_num:
            context = f"Chapter {ch_num}" + (f": {ch_title}" if ch_title else "")
        else:
            context = "Global comment"

        embed.add_field(
            name=f"**{display}**  ·  {when}  ·  *{context}*",
            value=f"> {c['content'][:300]}{'…' if len(c['content']) > 300 else ''}",
            inline=False
        )

    return embed


class LibraryCommentsView(TimeoutMixin, ui.View):

    def __init__(self, story: dict, comments: list,
                 library_view, guild=None):
        super().__init__(timeout=300)
        self.story        = story
        self.comments     = comments
        self.library_view = library_view
        self.guild        = guild
        self.page         = 0
        self.viewer       = library_view.user
        self._update_buttons()

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
        return max(1, (len(self.comments) + COMMENTS_PER_PAGE - 1) // COMMENTS_PER_PAGE)

    def _update_buttons(self):
        self.prev_page.disabled = (self.page == 0)
        self.next_page.disabled = (self.page >= self._total_pages() - 1)

    async def build_embed(self) -> discord.Embed:
        comments = self.comments
        if self.guild:
            start = self.page * COMMENTS_PER_PAGE
            chunk = comments[start:start + COMMENTS_PER_PAGE]
            for c in chunk:
                try:
                    member = self.guild.get_member(int(c["discord_id"]))
                    if not member:
                        member = await self.guild.fetch_member(int(c["discord_id"]))
                    if member:
                        c["display_name"] = member.display_name
                except Exception:
                    pass
        return build_library_comments_embed(
            self.story, self.comments, self.page, self._total_pages()
        )

    @ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary, row=0)
    async def prev_page(self, interaction: discord.Interaction, _):
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=await self.build_embed(), view=self)

    @ui.button(label="📖 Back to Story", style=discord.ButtonStyle.primary, row=0)
    async def back_btn(self, interaction: discord.Interaction, _):
        self.library_view.mode = "story"
        self.library_view.refresh_ui()
        await interaction.response.edit_message(
            embed=self.library_view.generate_detail_embed(self.library_view.current_item),
            view=self.library_view
        )

    @ui.button(emoji="➡️", style=discord.ButtonStyle.secondary, row=0)
    async def next_page(self, interaction: discord.Interaction, _):
        self.page = min(self._total_pages() - 1, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=await self.build_embed(), view=self)