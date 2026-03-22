import discord
from discord import ui
import asyncio
import datetime

from embeds.fanart_embeds import build_fanart_embed
from database import (
    get_fanart_characters,
    get_fanart_ships,
    get_fanart_like_count,
    get_fanart_comment_count,
    get_fanart_comments,
    get_user_id,
    user_has_liked_fanart,
    toggle_fanart_like,
    add_fanart_comment,
)

PAGE_SIZE        = 5
COMMENTS_PER_PAGE = 5

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


# ─────────────────────────────────────────────────
# Comment modal
# ─────────────────────────────────────────────────

class FanartCommentModal(discord.ui.Modal, title="Leave a Comment"):

    content = discord.ui.TextInput(
        label="Your comment",
        style=discord.TextStyle.paragraph,
        placeholder="Share your thoughts on this piece...",
        max_length=1000,
        required=True
    )

    def __init__(self, detail_view: "MyFanartDetailView"):
        super().__init__()
        self.detail_view = detail_view

    async def on_submit(self, interaction: discord.Interaction):
        uid = get_user_id(str(interaction.user.id))
        if not uid:
            await interaction.response.send_message(
                "No account found.", ephemeral=True, delete_after=4
            )
            return

        add_fanart_comment(uid, self.detail_view.current()["id"], self.content.value)
        self.detail_view._rebuild_ui()

        await interaction.response.send_message(
            "💬 Comment posted!", ephemeral=True, delete_after=3
        )
        await self.detail_view._refresh_message()


# ─────────────────────────────────────────────────
# Fanart comments list embed + view
# ─────────────────────────────────────────────────

def build_fanart_comments_embed(fanart: dict, comments: list,
                                 page: int, total_pages: int) -> discord.Embed:
    title = fanart.get("title", "Untitled")
    embed = discord.Embed(
        title=f"💬  Comments  ·  {title}",
        color=discord.Color.blurple()
    )
    embed.description = f"-# Page {page + 1} of {total_pages}"

    if not comments:
        embed.add_field(
            name="No comments yet",
            value="Be the first to leave one!",
            inline=False
        )
        return embed

    for c in comments:
        try:
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


class FanartCommentsView(ui.View):

    def __init__(self, fanart: dict, parent_view: "MyFanartDetailView", guild=None):
        super().__init__(timeout=180)
        self.fanart      = fanart
        self.parent_view = parent_view
        self.guild       = guild
        self.viewer      = getattr(parent_view, 'viewer', None)
        self.page        = 0
        self._update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.viewer and interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    def _all_comments(self):
        return get_fanart_comments(self.fanart["id"])

    def _page_comments(self):
        all_c = self._all_comments()
        start = self.page * COMMENTS_PER_PAGE
        return all_c[start:start + COMMENTS_PER_PAGE]

    def _total_pages(self):
        return max(1, (len(self._all_comments()) + COMMENTS_PER_PAGE - 1) // COMMENTS_PER_PAGE)

    def _update_buttons(self):
        self.prev_page.disabled = (self.page == 0)
        self.next_page.disabled = (self.page >= self._total_pages() - 1)

    async def build_embed(self) -> discord.Embed:
        comments = self._page_comments()
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
        return build_fanart_comments_embed(
            self.fanart, comments, self.page, self._total_pages()
        )

    @ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary, row=0)
    async def prev_page(self, interaction: discord.Interaction, _):
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=await self.build_embed(), view=self)

    @ui.button(label="🎨 Back to Piece", style=discord.ButtonStyle.primary, row=0)
    async def back_btn(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )

    @ui.button(emoji="➡️", style=discord.ButtonStyle.secondary, row=0)
    async def next_page(self, interaction: discord.Interaction, _):
        self.page = min(self._total_pages() - 1, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=await self.build_embed(), view=self)


# ─────────────────────────────────────────────────
# Jump modal
# ─────────────────────────────────────────────────

class JumpToFanartModal(discord.ui.Modal, title="Jump to Page"):

    page_num = discord.ui.TextInput(
        label="Page number",
        placeholder="e.g. 3",
        max_length=4,
        required=True
    )

    def __init__(self, roster_view: "MyFanartRosterView"):
        super().__init__()
        self.roster_view = roster_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            p = int(self.page_num.value) - 1
            p = max(0, min(p, self.roster_view.total_pages() - 1))
        except ValueError:
            await interaction.response.send_message(
                "❌ Enter a valid page number.", ephemeral=True, delete_after=3
            )
            return
        self.roster_view.page = p
        self.roster_view._rebuild_ui()
        await interaction.response.edit_message(
            embed=self.roster_view.build_embed(),
            view=self.roster_view
        )


# ─────────────────────────────────────────────────
# Roster view  (5 pieces per page, index buttons)
# ─────────────────────────────────────────────────

def build_roster_embed(fanarts: list, page: int, total_pages: int,
                        owner_name: str) -> discord.Embed:
    import random
    from embeds.fanart_embeds import BORDERS, TITLE_SPARKS, FANART_COLORS

    start = page * PAGE_SIZE
    chunk = fanarts[start:start + PAGE_SIZE]

    _local_rng = random.Random(hash(owner_name) & 0xFFFFFF)
    color  = _local_rng.choice(FANART_COLORS)
    border = random.choice(BORDERS)
    spark  = random.choice(TITLE_SPARKS)

    embed = discord.Embed(
        title=f"{spark[0]}  {owner_name}'s Gallery  {spark[1]}",
        description=(
            f"-# {border}\n"
            f"-# Page {page + 1} of {total_pages}  ✦  {len(fanarts)} piece{'s' if len(fanarts) != 1 else ''}"
        ),
        color=color
    )

    for i, f in enumerate(chunk, 1):
        title     = f.get("title", "Untitled")
        likes     = get_fanart_like_count(f["id"])
        comments  = get_fanart_comment_count(f["id"])
        chars     = get_fanart_characters(f["id"])
        char_text = "  ✦  ".join(c["name"] for c in chars[:3]) if chars else "*no characters tagged*"
        embed.add_field(
            name=f"{NUMBER_EMOJIS[i-1]}  {title}",
            value=f"-# 👍 {likes}  ·  💬 {comments}  ·  🧬 {char_text}",
            inline=False
        )

    embed.set_footer(text=f"{spark[0]} {owner_name}'s fanart collection")
    return embed


class MyFanartRosterView(ui.View):

    def __init__(self, fanarts: list, viewer: discord.Member, owner_name: str):
        super().__init__(timeout=300)
        self.fanarts    = fanarts
        self.viewer     = viewer
        self.owner_name = owner_name
        self.page       = 0
        self._message   = None
        self._rebuild_ui()

    def total_pages(self):
        return max(1, (len(self.fanarts) + PAGE_SIZE - 1) // PAGE_SIZE)

    def build_embed(self):
        return build_roster_embed(self.fanarts, self.page, self.total_pages(), self.owner_name)

    def _page_items(self):
        start = self.page * PAGE_SIZE
        return self.fanarts[start:start + PAGE_SIZE]

    def _rebuild_ui(self):
        self.clear_items()
        chunk = self._page_items()

        # Row 0: index buttons (blue)
        for i, fanart in enumerate(chunk):
            btn = ui.Button(
                emoji=NUMBER_EMOJIS[i],
                style=discord.ButtonStyle.primary,
                row=0
            )
            btn.callback = self._make_open_callback(self.page * PAGE_SIZE + i)
            self.add_item(btn)

        # Row 1: ◀ Jump to... ▶  (always shown for consistency)
        prev_btn = ui.Button(
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=1,
            disabled=(self.page == 0)
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        jump_btn = ui.Button(
            label="Jump to...",
            style=discord.ButtonStyle.success,
            row=1
        )
        jump_btn.callback = self._jump
        self.add_item(jump_btn)

        next_btn = ui.Button(
            emoji="➡️",
            style=discord.ButtonStyle.secondary,
            row=1,
            disabled=(self.page >= self.total_pages() - 1)
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

    def _make_open_callback(self, global_index: int):
        async def callback(interaction: discord.Interaction):
            if global_index >= len(self.fanarts):
                await interaction.response.send_message("Not found.", ephemeral=True)
                return
            detail = MyFanartDetailView(
                fanarts=self.fanarts,
                index=global_index,
                viewer=self.viewer,
                roster=self,
                return_page=self.page
            )
            self._message = interaction.message
            await interaction.response.edit_message(
                embed=detail.build_embed(),
                view=detail
            )
        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.", ephemeral=True, delete_after=5
            )
            return False
        return True

    async def _prev(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.page = min(self.total_pages() - 1, self.page + 1)
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _jump(self, interaction: discord.Interaction):
        await interaction.response.send_modal(JumpToFanartModal(self))


# ─────────────────────────────────────────────────
# Detail view  (single fanart embed)
# Row 0: ⬅️  👍  💬 (N)  Return  ➡️
# ─────────────────────────────────────────────────

class MyFanartDetailView(ui.View):

    def __init__(self, fanarts: list, index: int,
                 viewer: discord.Member,
                 roster: MyFanartRosterView,
                 return_page: int):
        super().__init__(timeout=300)
        self.fanarts     = fanarts
        self.index       = index
        self.viewer      = viewer
        self.roster      = roster
        self.return_page = return_page
        self._message    = None
        self._rebuild_ui()

    def current(self):
        return self.fanarts[self.index]

    def build_embed(self) -> discord.Embed:
        f     = self.current()
        chars = get_fanart_characters(f["id"])
        ships = get_fanart_ships(f["id"])
        likes = get_fanart_like_count(f["id"])
        embed = build_fanart_embed(
            f,
            index=self.index + 1,
            total=len(self.fanarts),
            characters=chars,
            ships=ships
        )
        existing = embed.footer.text or ""
        embed.set_footer(text=f"{existing}  ·  👍 {likes}" if existing else f"👍 {likes}")
        return embed

    def _rebuild_ui(self):
        self.clear_items()
        f         = self.current()
        total     = len(self.fanarts)
        uid       = get_user_id(str(self.viewer.id))
        liked     = user_has_liked_fanart(uid, f["id"]) if uid else False
        n_comments = get_fanart_comment_count(f["id"])

        # ── Row 0 ─────────────────────────────────
        prev_btn = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index == 0)
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        like_btn = ui.Button(
            emoji="👍",
            style=discord.ButtonStyle.success if liked else discord.ButtonStyle.secondary,
            row=0
        )
        like_btn.callback = self._like
        self.add_item(like_btn)

        comment_btn = ui.Button(
            label=f"View 💬 {n_comments}",
            style=discord.ButtonStyle.primary,
            row=0
        )
        comment_btn.callback = self._comment
        self.add_item(comment_btn)

        return_btn = ui.Button(
            label="↩️ Return",
            style=discord.ButtonStyle.success,
            row=0
        )
        return_btn.callback = self._return
        self.add_item(return_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index >= total - 1)
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

    async def _refresh_message(self):
        if self._message:
            try:
                await self._message.edit(embed=self.build_embed(), view=self)
            except Exception:
                pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.", ephemeral=True, delete_after=5
            )
            return False
        return True

    async def _prev(self, interaction: discord.Interaction):
        self.index = max(0, self.index - 1)
        self._rebuild_ui()
        self._message = interaction.message
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.index = min(len(self.fanarts) - 1, self.index + 1)
        self._rebuild_ui()
        self._message = interaction.message
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _like(self, interaction: discord.Interaction):
        uid = get_user_id(str(interaction.user.id))
        if not uid:
            await interaction.response.send_message("❌ Profile not found.", ephemeral=True)
            return
        toggle_fanart_like(uid, self.current()["id"])
        self._rebuild_ui()
        self._message = interaction.message
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _comment(self, interaction: discord.Interaction):
        n = get_fanart_comment_count(self.current()["id"])
        if n == 0:
            await interaction.response.send_message(
                "✦ No comments left on this piece yet.",
                ephemeral=True,
                delete_after=3
            )
            return
        cv = FanartCommentsView(self.current(), self, guild=interaction.guild)
        self._message = interaction.message
        await interaction.response.edit_message(
            embed=await cv.build_embed(),
            view=cv
        )

    async def _return(self, interaction: discord.Interaction):
        self.roster.page = self.return_page
        self.roster._rebuild_ui()
        await interaction.response.edit_message(
            embed=self.roster.build_embed(),
            view=self.roster
        )