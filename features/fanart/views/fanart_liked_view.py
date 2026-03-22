"""
fanart_liked_view.py  —  /fanart liked roster + detail views.

Roster:
  Row 0: 1️⃣–5️⃣ index buttons (blue)
  Row 1: ⬅️  Jump to...  ➡️

Detail:
  Row 0: ⬅️  👍 (green/unlike warning)  💬 (post comment)  ↩️ Return  ➡️
  Row 1: "Explore More Fanart..." dropdown (View Comments + all search options)
"""

import discord
from discord import ui
import datetime

from embeds.fanart_embeds import build_fanart_embed, BORDERS, TITLE_SPARKS, FANART_COLORS
from database import (
    get_fanart_characters,
    get_fanart_ships,
    get_fanart_like_count,
    get_fanart_comment_count,
    get_user_id,
    toggle_fanart_like,
    add_fanart_comment,
    get_character_by_id,
    get_characters_by_ids,
)
import random
from ui import TimeoutMixin

PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


# ─────────────────────────────────────────────────
# Jump modal
# ─────────────────────────────────────────────────

class LikedJumpModal(discord.ui.Modal, title="Jump to Page"):

    page_num = discord.ui.TextInput(
        label="Page number", placeholder="e.g. 3", max_length=4, required=True
    )

    def __init__(self, roster: "LikedFanartRosterView"):
        super().__init__()
        self.roster = roster

    async def on_submit(self, interaction: discord.Interaction):
        try:
            p = int(self.page_num.value) - 1
            p = max(0, min(p, self.roster.total_pages() - 1))
        except Exception:
            await interaction.response.send_message(
                "❌ Enter a valid page number.", ephemeral=True, delete_after=3
            )
            return
        self.roster.page = p
        self.roster._rebuild_ui()
        await interaction.response.edit_message(
            embed=self.roster.build_embed(), view=self.roster
        )


# ─────────────────────────────────────────────────
# Comment modal
# ─────────────────────────────────────────────────

class LikedCommentModal(discord.ui.Modal, title="Leave a Comment"):

    content = discord.ui.TextInput(
        label="Your comment",
        style=discord.TextStyle.paragraph,
        placeholder="Share your thoughts on this piece...",
        max_length=1000,
        required=True
    )

    def __init__(self, detail_view: "LikedFanartDetailView"):
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
        if self.detail_view._message:
            try:
                await self.detail_view._message.edit(
                    embed=self.detail_view.build_embed(),
                    view=self.detail_view
                )
            except Exception:
                pass


# ─────────────────────────────────────────────────
# Unlike confirmation view
# ─────────────────────────────────────────────────

class UnlikeConfirmView(TimeoutMixin, ui.View):

    def __init__(self, detail_view: "LikedFanartDetailView"):
        super().__init__(timeout=15)
        self.detail_view = detail_view
        self.viewer = getattr(detail_view, 'viewer', None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if self.viewer and interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    @ui.button(label="Yes, unlike", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        uid = get_user_id(str(interaction.user.id))
        if uid:
            toggle_fanart_like(uid, self.detail_view.current()["id"])
            # Remove from the liked list and go back to roster
            fid = self.detail_view.current()["id"]
            self.detail_view.fanarts = [f for f in self.detail_view.fanarts if f["id"] != fid]
            self.detail_view.roster.fanarts = self.detail_view.fanarts
            # Clamp index
            self.detail_view.index = min(
                self.detail_view.index, max(0, len(self.detail_view.fanarts) - 1)
            )
        await interaction.response.edit_message(
            content=None,
            embed=self.detail_view.roster.build_embed(),
            view=self.detail_view.roster
        )

    @ui.button(label="No, keep it", style=discord.ButtonStyle.success)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        self.detail_view._rebuild_ui()
        await interaction.response.edit_message(
            content=None,
            embed=self.detail_view.build_embed(),
            view=self.detail_view
        )


# ─────────────────────────────────────────────────
# Roster embed
# ─────────────────────────────────────────────────

_LIKED_SPARKS   = ["💖", "🌸", "⭐", "💎", "🌺", "✨", "🎨", "🖼️"]
_LIKED_DIVIDERS = [
    "✦ · · ✦ · · ✦ · · ✦",
    "· ˖ ✦ ˖ · ˖ ✦ ˖ ·",
    "⋆ ˚ ✦ ˚ ⋆ · ⋆ ˚ ✦",
    "─ ✦ ─────────── ✦ ─",
]
_LIKED_COLORS = [
    (255, 182, 193), (255, 218, 185), (179, 255, 179), (153, 229, 255),
    (204, 153, 255), (255, 179, 255), (255, 204, 153), (153, 255, 229),
    (255,  92,  92), (255, 160,  50), ( 80, 220, 100), ( 50, 200, 255),
    (130,  80, 255), (255,  80, 200), (255, 215,   0), (100, 149, 237),
]

def build_liked_roster_embed(fanarts: list, page: int, total_pages: int,
                              viewer_name: str) -> discord.Embed:

    start   = page * PAGE_SIZE
    chunk   = fanarts[start:start + PAGE_SIZE]
    spark   = _LIKED_SPARKS[page % len(_LIKED_SPARKS)]
    divider = _LIKED_DIVIDERS[page % len(_LIKED_DIVIDERS)]

    _local_rng = random.Random(page + hash(viewer_name) % 997)
    r, g, b = _local_rng.choice(_LIKED_COLORS)
    color   = discord.Color.from_rgb(r, g, b)

    entry_sep = "-# · · · · · · · · · ·"
    lines = [f"-# {divider}"]

    for i, f in enumerate(chunk):
        global_num = page * PAGE_SIZE + i + 1
        title      = f.get("title", "Untitled")
        author     = f.get("display_name") or f.get("author") or f.get("username") or "unknown"
        likes      = get_fanart_like_count(f["id"])
        comments   = get_fanart_comment_count(f["id"])
        chars      = get_fanart_characters(f["id"])
        char_text  = "  ✦  ".join(c["name"] for c in chars[:3]) if chars else "no characters"
        lines.append(
            f"{NUMBER_EMOJIS[i]}  **{title}**\n"
            f"-# 🎨 by {author}  ·  👍 {likes}  ·  💬 {comments}  ·  🧬 {char_text}  ·  #{global_num}"
        )
        if i < len(chunk) - 1:
            lines.append(entry_sep)

    lines.append(f"-# {divider}")

    embed = discord.Embed(
        title=f"{spark}  {viewer_name}'s Liked Fanart  {spark}",
        description="\n".join(lines),
        color=color
    )
    embed.set_footer(
        text=f"Page {page+1} of {total_pages}  ·  {len(fanarts)} piece{'s' if len(fanarts) != 1 else ''} liked"
    )
    return embed


# ─────────────────────────────────────────────────
# Roster view
# ─────────────────────────────────────────────────

class LikedFanartRosterView(TimeoutMixin, ui.View):

    def __init__(self, fanarts: list, viewer: discord.Member):
        super().__init__(timeout=300)
        self.fanarts     = fanarts
        self.viewer      = viewer
        self.page        = 0
        self._rebuild_ui()

    def total_pages(self):
        return max(1, (len(self.fanarts) + PAGE_SIZE - 1) // PAGE_SIZE)

    def build_embed(self):
        return build_liked_roster_embed(
            self.fanarts, self.page, self.total_pages(), self.viewer.display_name
        )

    def _page_items(self):
        start = self.page * PAGE_SIZE
        return self.fanarts[start:start + PAGE_SIZE]

    def _rebuild_ui(self):
        self.clear_items()
        chunk = self._page_items()

        # Row 0: blue index buttons
        for i, _ in enumerate(chunk):
            btn = ui.Button(
                emoji=NUMBER_EMOJIS[i],
                style=discord.ButtonStyle.primary,
                row=0
            )
            btn.callback = self._make_open(self.page * PAGE_SIZE + i)
            self.add_item(btn)

        # Row 1: ⬅️  Jump to...  ➡️
        prev_btn = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary,
            row=1, disabled=(self.page == 0)
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        jump_btn = ui.Button(
            label="Jump to...", style=discord.ButtonStyle.success, row=1
        )
        jump_btn.callback = self._jump
        self.add_item(jump_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=1, disabled=(self.page >= self.total_pages() - 1)
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

    def _make_open(self, global_index: int):
        async def callback(interaction: discord.Interaction):
            if global_index >= len(self.fanarts):
                await interaction.response.send_message("Not found.", ephemeral=True)
                return
            detail = LikedFanartDetailView(
                fanarts=self.fanarts,
                index=global_index,
                viewer=self.viewer,
                roster=self,
                return_page=self.page
            )
            await interaction.response.edit_message(
                embed=detail.build_embed(), view=detail
            )
            detail._message = interaction.message
        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
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
        await interaction.response.send_modal(LikedJumpModal(self))


# ─────────────────────────────────────────────────
# Detail view
# Row 0: ⬅️  👍 (unlike warning)  💬  ↩️ Return  ➡️
# Row 1: Explore More Fanart... dropdown
# ─────────────────────────────────────────────────

class LikedFanartDetailView(TimeoutMixin, ui.View):

    def __init__(self, fanarts: list, index: int,
                 viewer: discord.Member,
                 roster: LikedFanartRosterView,
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
            f, index=self.index + 1, total=len(self.fanarts),
            characters=chars, ships=ships
        )
        existing = embed.footer.text or ""
        embed.set_footer(text=f"{existing}  ·  👍 {likes}" if existing else f"👍 {likes}")
        return embed

    def _rebuild_ui(self):
        self.clear_items()
        f        = self.current()
        total    = len(self.fanarts)
        chars    = get_fanart_characters(f["id"])
        ships    = get_fanart_ships(f["id"])
        story_id = f.get("story_id")

        # ── Row 0 ──────────────────────────────────────────────────
        prev_btn = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index == 0)
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        # Like button always green (this is the liked list)
        like_btn = ui.Button(
            emoji="👍", style=discord.ButtonStyle.success, row=0
        )
        like_btn.callback = self._unlike_prompt
        self.add_item(like_btn)

        comment_btn = ui.Button(
            emoji="💬", style=discord.ButtonStyle.primary, row=0
        )
        comment_btn.callback = self._comment
        self.add_item(comment_btn)

        return_btn = ui.Button(
            label="↩️ Return", style=discord.ButtonStyle.success, row=0
        )
        return_btn.callback = self._return
        self.add_item(return_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index >= total - 1)
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

        # ── Row 1: Explore dropdown ────────────────────────────────
        options = []

        # View Comments (always first)
        n_comments = get_fanart_comment_count(f["id"])
        options.append(discord.SelectOption(
            label=f"View Comments ({n_comments})",
            emoji="💬",
            value="view_comments"
        ))

        # Characters
        if chars:
            names = [c["name"] for c in chars]
            char_label = ", ".join(names[:3]) + (" and more" if len(names) > 3 else "")
            char_ids   = "|".join(str(c["id"]) for c in chars)
            options.append(discord.SelectOption(
                label=f"View {char_label} character cards"[:100],
                emoji="🧬",
                value=f"chars:{char_ids}"
            ))

        # Story
        if story_id:
            story_title = f.get("story_title") or "linked story"
            options.append(discord.SelectOption(
                label=f"View {story_title}"[:100],
                emoji="📖",
                value=f"story:{story_id}"
            ))

        # Author
        if story_id:
            author_name = f.get("author") or "the author"
            options.append(discord.SelectOption(
                label=f"✍️ {author_name}"[:100],
                emoji="✍️",
                value=f"author:{story_id}"
            ))

        # See more by character
        # ── Ships: see more fanart per ship ──────────────────────────
        for s in ships[:3]:
            options.append(discord.SelectOption(
                label=f"See more {s['name']} fanart"[:100],
                emoji="💞",
                value=f"more_ship:{s['name']}"
            ))


        for c in chars[:3]:
            options.append(discord.SelectOption(
                label=f"See more {c['name']} fanart"[:100],
                emoji="🖼️",
                value=f"more_char:{c['name']}"
            ))

        # See more from story
        if story_id:
            story_title = f.get("story_title") or "this story"
            options.append(discord.SelectOption(
                label=f"See more from {story_title}"[:100],
                emoji="📚",
                value=f"more_story:{story_id}"
            ))

        explore = ui.Select(
            placeholder="✨ Explore More Fanart...",
            options=options[:25],
            row=1
        )
        explore.callback = self._explore
        self.add_item(explore)

    # ── Callbacks ──────────────────────────────────────────────────

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
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

    async def _unlike_prompt(self, interaction: discord.Interaction):
        title = self.current().get("title", "this piece")
        await interaction.response.edit_message(
            content=(
                f"💔 Are you sure you want to unlike **{title}**?\n"
                f"-# This will remove it from your liked collection."
            ),
            embed=None,
            view=UnlikeConfirmView(self)
        )

    async def _comment(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LikedCommentModal(self))

    async def _return(self, interaction: discord.Interaction):
        self.roster.page = self.return_page
        self.roster._rebuild_ui()
        await interaction.response.edit_message(
            content=None,
            embed=self.roster.build_embed(),
            view=self.roster
        )

    async def _explore(self, interaction: discord.Interaction):
        select = next((c for c in self.children if isinstance(c, ui.Select)), None)
        value  = select.values[0] if select and select.values else ""

        if value == "view_comments":
            from features.fanart.views.my_fanart_view import FanartCommentsView
            n = get_fanart_comment_count(self.current()["id"])
            if n == 0:
                await interaction.response.send_message(
                    "✦ No comments on this piece yet. Be the first!",
                    ephemeral=True, delete_after=3
                )
                return
            cv = FanartCommentsView(self.current(), self, guild=interaction.guild)
            self._message = interaction.message
            await interaction.response.edit_message(
                embed=await cv.build_embed(), view=cv
            )
            return

        if value.startswith("chars:"):
            char_ids   = [int(x) for x in value.split(":")[1].split("|") if x]
            characters = get_characters_by_ids(char_ids)
            if not characters:
                await interaction.response.send_message(
                    "Characters not found.", ephemeral=True, delete_after=3
                )
                return
            from features.fanart.views.fanart_search_view import SearchCharSlideView
            view = SearchCharSlideView(characters=characters, viewer=self.viewer, back_detail=self)
            await interaction.response.edit_message(embed=view.build_embed(), view=view)
            return

        if value.startswith("story:"):
            story_id = int(value.split(":")[1])
            from features.fanart.views.fanart_search_view import SearchStoryView
            view = SearchStoryView(story_id=story_id, viewer=interaction.user, back_detail=self)
            embed = view.build_story_embed()
            if not embed:
                await interaction.response.send_message(
                    "Story not found.", ephemeral=True, delete_after=3
                )
                return
            await interaction.response.edit_message(embed=embed, view=view)
            return

        if value.startswith("author:"):
            story_id = int(value.split(":")[1])
            from database import get_discord_id_by_story, get_stories_by_discord_user
            discord_id = get_discord_id_by_story(story_id)
            if not discord_id:
                await interaction.response.send_message(
                    "Author not found.", ephemeral=True, delete_after=3
                )
                return
            target = interaction.guild.get_member(int(discord_id))
            if not target:
                try:
                    target = await interaction.guild.fetch_member(int(discord_id))
                except Exception:
                    pass
            if not target:
                await interaction.response.send_message(
                    "Couldn't find that author in this server.", ephemeral=True, delete_after=3
                )
                return
            from database import get_stories_by_discord_user
            stories = get_stories_by_discord_user(discord_id)
            from features.fanart.views.fanart_search_view import SearchAuthorView
            view = SearchAuthorView(
                stories=stories, viewer=interaction.user,
                target_user=target, back_detail=self
            )
            await interaction.response.edit_message(
                embed=view.generate_bio_embed(), view=view
            )
            return

        if value.startswith("more_char:"):
            char_name = value.split(":", 1)[1]
            from database import search_fanart
            results = search_fanart(character=char_name)
            if not results:
                await interaction.response.send_message(
                    f"No fanart found featuring {char_name}.",
                    ephemeral=True, delete_after=3
                )
                return
            from features.fanart.views.fanart_search_view import SearchFanartDetailView, FanartSearchRosterView
            dummy_roster = FanartSearchRosterView(results, self.viewer, [], guild=interaction.guild)
            new_view = SearchFanartDetailView(
                fanarts=results, index=0, viewer=self.viewer,
                roster=dummy_roster, return_page=0
            )
            await interaction.response.edit_message(embed=new_view.build_embed(), view=new_view)
            new_view._message = interaction.message
            return

        # ── See more fanart by ship ───────────────────────────────────
        if value.startswith("more_ship:"):
            ship_name = value.split(":", 1)[1]
            from database import search_fanart
            results = search_fanart(ship=ship_name)
            if not results:
                await interaction.response.send_message(
                    f"No fanart found featuring {ship_name}.",
                    ephemeral=True, delete_after=3
                )
                return
            from features.fanart.views.fanart_search_view import SearchFanartDetailView, FanartSearchRosterView
            dummy_roster = FanartSearchRosterView(results, self.viewer, [], guild=interaction.guild)
            new_view = SearchFanartDetailView(
                fanarts=results, index=0, viewer=self.viewer,
                roster=dummy_roster, return_page=0
            )
            await interaction.response.edit_message(embed=new_view.build_embed(), view=new_view)
            new_view._message = interaction.message
            return

        if value.startswith("more_story:"):
            story_id = int(value.split(":")[1])
            from database import get_fanart_by_story
            results = get_fanart_by_story(story_id)
            if not results:
                await interaction.response.send_message(
                    "No fanart found for that story.", ephemeral=True, delete_after=3
                )
                return
            from features.fanart.views.fanart_search_view import SearchFanartDetailView, FanartSearchRosterView
            dummy_roster = FanartSearchRosterView(results, self.viewer, [], guild=interaction.guild)
            new_view = SearchFanartDetailView(
                fanarts=results, index=0, viewer=self.viewer,
                roster=dummy_roster, return_page=0
            )
            await interaction.response.edit_message(embed=new_view.build_embed(), view=new_view)
            new_view._message = interaction.message
            return