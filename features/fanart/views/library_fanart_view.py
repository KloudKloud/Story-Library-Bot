"""
library_fanart_view.py  —  fanart detail view opened from /library Explore → Fanart Gallery.

Row 0: ⬅️  👍  💬 (post comment)  📖 Library  ➡️
Row 1: Explore More Fanart... dropdown (full options matching search/liked/story views)
"""

import discord
from discord import ui

from embeds.fanart_embeds import build_fanart_embed
from database import (
    get_fanart_characters,
    get_fanart_ships,
    get_fanart_like_count,
    get_fanart_comment_count,
    get_user_id,
    user_has_liked_fanart,
    toggle_fanart_like,
    add_fanart_comment,
    get_character_by_id,
)


# ─────────────────────────────────────────────────
# Dummy roster (used by SearchCharSlideView / SearchStoryView back_detail)
# ─────────────────────────────────────────────────

class LibraryFanartRosterDummy:
    """Minimal stand-in so SearchCharSlideView back_detail works."""
    pass


# ─────────────────────────────────────────────────
# Comment modal
# ─────────────────────────────────────────────────

class LibraryFanartCommentModal(discord.ui.Modal, title="Leave a Comment"):

    content = discord.ui.TextInput(
        label="Your comment",
        style=discord.TextStyle.paragraph,
        placeholder="Share your thoughts on this piece...",
        max_length=1000,
        required=True
    )

    def __init__(self, detail_view: "LibraryFanartDetailView"):
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
# Detail view
# ─────────────────────────────────────────────────

class LibraryFanartDetailView(ui.View):

    def __init__(self, fanarts: list, index: int,
                 viewer: discord.Member, library_view):
        super().__init__(timeout=300)
        self.fanarts      = fanarts
        self.index        = index
        self.viewer       = viewer
        self.library_view = library_view
        self._message     = None
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
        uid      = get_user_id(str(self.viewer.id))
        liked    = user_has_liked_fanart(uid, f["id"]) if uid else False
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

        like_btn = ui.Button(
            emoji="👍",
            style=discord.ButtonStyle.success if liked else discord.ButtonStyle.secondary,
            row=0
        )
        like_btn.callback = self._like
        self.add_item(like_btn)

        comment_btn = ui.Button(
            emoji="💬", style=discord.ButtonStyle.primary, row=0
        )
        comment_btn.callback = self._comment
        self.add_item(comment_btn)

        library_btn = ui.Button(
            label="📖 Library", style=discord.ButtonStyle.success, row=0
        )
        library_btn.callback = self._return_library
        self.add_item(library_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index >= total - 1)
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

        # ── Row 1: Explore More Fanart... dropdown ─────────────────
        options = []

        # View Comments (always first)
        n_comments = get_fanart_comment_count(f["id"])
        options.append(discord.SelectOption(
            label=f"View Comments ({n_comments})",
            emoji="💬",
            value="view_comments"
        ))

        # Characters: ONE combined option
        if chars:
            names      = [c["name"] for c in chars]
            char_label = ", ".join(names[:3]) + (" and more" if len(names) > 3 else "")
            char_ids   = "|".join(str(c["id"]) for c in chars)
            options.append(discord.SelectOption(
                label=f"View {char_label} character cards"[:100],
                emoji="🧬",
                value=f"chars:{char_ids}"
            ))

        # Ships
        for s in ships[:3]:
            options.append(discord.SelectOption(
                label=f"See more {s['name']} fanart"[:100],
                emoji="💞",
                value=f"more_ship:{s['name']}"
            ))

        # See more by character
        for c in chars[:3]:
            options.append(discord.SelectOption(
                label=f"See more {c['name']} fanart"[:100],
                emoji="🖼️",
                value=f"more_char:{c['name']}"
            ))



        if not options:
            options.append(discord.SelectOption(
                label="No related fanart available", value="none", emoji="🌙"
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
        f = self.current()
        was_liked = user_has_liked_fanart(uid, f["id"])
        toggle_fanart_like(uid, f["id"])
        self._rebuild_ui()
        self._message = interaction.message
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        import asyncio
        msg = await interaction.followup.send(
            f"💔 Removed **{f.get('title', 'this piece')}** from liked!" if was_liked
            else f"👍 Added **{f.get('title', 'this piece')}** to your likes!",
            ephemeral=True, wait=True
        )
        await asyncio.sleep(2)
        try:
            await msg.delete()
        except Exception:
            pass

    async def _comment(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LibraryFanartCommentModal(self))

    async def _return_library(self, interaction: discord.Interaction):
        self.library_view.mode = "story"
        self.library_view.refresh_ui()
        await interaction.response.edit_message(
            embed=self.library_view.generate_detail_embed(self.library_view.current_item),
            view=self.library_view
        )

    async def _explore(self, interaction: discord.Interaction):
        select = next((c for c in self.children if isinstance(c, ui.Select)), None)
        value  = select.values[0] if select and select.values else ""

        if value == "none":
            await interaction.response.send_message(
                "No related fanart found.", ephemeral=True, delete_after=3
            )
            return

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
            await interaction.response.edit_message(embed=await cv.build_embed(), view=cv)
            return

        if value.startswith("chars:"):
            char_ids   = [int(x) for x in value.split(":")[1].split("|") if x]
            characters = [get_character_by_id(cid) for cid in char_ids]
            characters = [c for c in characters if c]
            if not characters:
                await interaction.response.send_message(
                    "Characters not found.", ephemeral=True, delete_after=3
                )
                return
            from features.fanart.views.fanart_search_view import SearchCharSlideView
            view = SearchCharSlideView(characters=characters, viewer=self.viewer, back_detail=self)
            await interaction.response.edit_message(embed=view.build_embed(), view=view)
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