"""
world_search_view.py  —  /world search roster + detail views.

Roster:
  Row 0: 1️⃣–5️⃣ index buttons (blue)
  Row 1: ⬅️  sort (blue)  Jump to...  ➡️

Detail:
  Row 0: ⬅️  ✨ Shiny  📜 Lore  ↩️ Return  ➡️
  Row 1: ✨ More [world name]... dropdown
"""

import discord
from discord import ui
from ui import TimeoutMixin, IdleTimeoutMixin

from database import (
    get_world_card_by_id,
    get_user_id,
    get_world_card_owner_count,
)

PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

SORT_CYCLE  = ["alpha", "collected", "recent", "alpha_z"]
SORT_LABELS = {
    "alpha":     "🔤 A–Z",
    "alpha_z":   "🔤 Z–A",
    "collected": "🃏 Most",
    "recent":    "🕐 Newest",
}

_SPARKS   = ["🌍", "🌸", "⭐", "💎", "🌺", "✨", "🔮", "💫"]
_DIVIDERS = [
    "✦ · · ✦ · · ✦ · · ✦",
    "· ˖ ✦ ˖ · ˖ ✦ ˖ ·",
    "⋆ ˚ ✦ ˚ ⋆ · ⋆ ˚ ✦",
    "─ ✦ ─────────── ✦ ─",
]
_COLORS = [
    (100, 200, 230), (186, 104, 200), (121, 134, 203), (100, 181, 246),
    ( 77, 182, 172), (149, 117, 205), (140, 158, 255), (100, 220, 180),
]


# ─────────────────────────────────────────────────
# Sort helper
# ─────────────────────────────────────────────────

def _sort_worlds(worlds: list, sort: str) -> list:
    if sort == "collected":
        return sorted(worlds, key=lambda w: get_world_card_owner_count(w["id"]), reverse=True)
    if sort == "recent":
        return sorted(worlds, key=lambda w: w["id"], reverse=True)
    if sort == "alpha_z":
        return sorted(worlds, key=lambda w: (w.get("name") or "").lower(), reverse=True)
    return sorted(worlds, key=lambda w: (w.get("name") or "").lower())


# ─────────────────────────────────────────────────
# Jump modal
# ─────────────────────────────────────────────────

class WorldSearchJumpModal(discord.ui.Modal):
    page_num = discord.ui.TextInput(
        label="Page number", placeholder="e.g. 3", max_length=4, required=True
    )

    def __init__(self, roster: "WorldSearchRosterView"):
        super().__init__(title="Jump to Page")
        self.roster = roster

    async def on_submit(self, interaction: discord.Interaction):
        try:
            p = max(0, min(int(self.page_num.value) - 1, self.roster.total_pages() - 1))
        except ValueError:
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
# Roster embed builder
# ─────────────────────────────────────────────────

def build_world_search_embed(worlds: list, page: int, total_pages: int, sort: str) -> discord.Embed:
    import random
    start   = page * PAGE_SIZE
    chunk   = worlds[start:start + PAGE_SIZE]
    spark   = _SPARKS[page % len(_SPARKS)]
    divider = _DIVIDERS[page % len(_DIVIDERS)]

    _rng    = random.Random(page + len(worlds))
    r, g, b = _rng.choice(_COLORS)
    color   = discord.Color.from_rgb(r, g, b)

    entry_sep = "-# · · · · · · · · · ·"
    lines = [f"-# {divider}"]

    for i, w in enumerate(chunk):
        name       = w.get("name", "?")
        author     = w.get("author") or "?"
        world_type = w.get("world_type") or "World Card"
        card_count = get_world_card_owner_count(w["id"])
        if w.get("is_dummy"):
            story = f"*{author}'s private collection*"
        else:
            story = w.get("story_title") or "?"
        lines.append(
            f"{NUMBER_EMOJIS[i]}  **{name}**  ✦  *{world_type}*\n"
            f"-# 📖 {story}  ·  ✍️ {author}  ·  🃏 {card_count} collected"
        )
        if i < len(chunk) - 1:
            lines.append(entry_sep)

    lines.append(f"-# {divider}")

    embed = discord.Embed(
        title=f"{spark}  World Card Search  {spark}",
        description="\n".join(lines),
        color=color,
    )
    embed.set_footer(
        text=f"Page {page+1} of {total_pages}  ·  {len(worlds)} world card{'s' if len(worlds) != 1 else ''}  ·  {SORT_LABELS[sort]}"
    )
    return embed


# ─────────────────────────────────────────────────
# Roster view
# ─────────────────────────────────────────────────

class WorldSearchRosterView(IdleTimeoutMixin, TimeoutMixin, ui.View):

    def __init__(self, worlds: list, viewer: discord.Member):
        super().__init__(timeout=None)
        self.all_worlds = worlds
        self.viewer     = viewer
        self.sort       = "alpha"
        self.page       = 0
        self._sorted    = _sort_worlds(worlds, self.sort)
        self._rebuild_ui()
        self._idle_init()

    def total_pages(self):
        return max(1, (len(self._sorted) + PAGE_SIZE - 1) // PAGE_SIZE)

    def build_embed(self):
        return build_world_search_embed(self._sorted, self.page, self.total_pages(), self.sort)

    def _page_items(self):
        start = self.page * PAGE_SIZE
        return self._sorted[start:start + PAGE_SIZE]

    def _rebuild_ui(self):
        self.clear_items()
        chunk = self._page_items()

        # Row 0: blue index buttons
        for i in range(len(chunk)):
            btn = ui.Button(emoji=NUMBER_EMOJIS[i], style=discord.ButtonStyle.primary, row=0)
            btn.callback = self._make_open(self.page * PAGE_SIZE + i)
            self.add_item(btn)

        # Row 1: ⬅️  sort  Jump to...  ➡️
        prev_btn = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary,
            row=1, disabled=(self.page == 0),
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        sort_btn = ui.Button(
            label=SORT_LABELS[self.sort], style=discord.ButtonStyle.primary, row=1
        )
        sort_btn.callback = self._cycle_sort
        self.add_item(sort_btn)

        jump_btn = ui.Button(label="Jump to...", style=discord.ButtonStyle.success, row=1)
        jump_btn.callback = self._jump
        self.add_item(jump_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=1, disabled=(self.page >= self.total_pages() - 1),
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

    def _make_open(self, global_index: int):
        async def callback(interaction: discord.Interaction):
            if global_index >= len(self._sorted):
                await interaction.response.send_message("Not found.", ephemeral=True)
                return
            detail = WorldSearchDetailView(
                worlds=self._sorted,
                index=global_index,
                viewer=self.viewer,
                roster=self,
                return_page=self.page,
            )
            await interaction.response.edit_message(embed=detail.build_embed(), view=detail)
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

    async def _cycle_sort(self, interaction: discord.Interaction):
        idx          = SORT_CYCLE.index(self.sort)
        self.sort    = SORT_CYCLE[(idx + 1) % len(SORT_CYCLE)]
        self._sorted = _sort_worlds(self.all_worlds, self.sort)
        self.page    = 0
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _jump(self, interaction: discord.Interaction):
        await interaction.response.send_modal(WorldSearchJumpModal(self))


# ─────────────────────────────────────────────────
# Detail view
# Row 0: ⬅️  ↩️ Return  ➡️
# Row 1: ✨ More [world name]... dropdown
# ─────────────────────────────────────────────────

class WorldSearchDetailView(IdleTimeoutMixin, TimeoutMixin, ui.View):

    def __init__(self, worlds: list, index: int,
                 viewer: discord.Member,
                 roster: WorldSearchRosterView = None,
                 return_page: int = 0):
        super().__init__(timeout=None)
        self.worlds      = worlds
        self.index       = index
        self.viewer      = viewer
        self.roster      = roster
        self.return_page = return_page
        self._rebuild_ui()
        self._idle_init()

    def current(self):
        return self.worlds[self.index]

    def _hydrated(self) -> dict:
        """Return full world card dict, hydrating if needed."""
        w = self.current()
        if w.get("description") is not None or w.get("image_url") is not None:
            return w
        full = get_world_card_by_id(w["id"])
        if full:
            full["story_title"] = w.get("story_title")
            full["author"]      = w.get("author")
            full["is_dummy"]    = w.get("is_dummy", False)
        return full or w

    def build_embed(self) -> discord.Embed:
        from embeds.world_card_embed import build_world_card_embed
        uid = get_user_id(str(self.viewer.id))
        return build_world_card_embed(
            self._hydrated(),
            uid,
            index=self.index + 1,
            total=len(self.worlds),
        )

    def _rebuild_ui(self):
        self.clear_items()
        w     = self._hydrated()
        total = len(self.worlds)

        prev_btn = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index == 0),
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        if self.roster:
            return_btn = ui.Button(label="↩️ Return", style=discord.ButtonStyle.success, row=0)
            return_btn.callback = self._return
            self.add_item(return_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index >= total - 1),
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

        # ── Row 1: More [world name]... dropdown ──────────────────
        world_name  = w.get("name", "this world")
        story_id    = w.get("story_id")
        author_name = w.get("author") or "the author"

        options = []
        if story_id and not w.get("is_dummy"):
            options.append(discord.SelectOption(
                label=f"See {world_name}'s story"[:100],
                emoji="📖",
                value=f"story:{story_id}",
            ))
        if story_id:
            options.append(discord.SelectOption(
                label=f"See {author_name}'s profile"[:100],
                emoji="✍️",
                value=f"author:{story_id}",
            ))

        if options:
            more_select = ui.Select(
                placeholder=f"✨ More {world_name}...",
                options=options,
                row=1,
            )
            more_select.callback = self._more
            self.add_item(more_select)

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
        self.index -= 1
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.index += 1
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _more(self, interaction: discord.Interaction):
        select = next((c for c in self.children if isinstance(c, ui.Select)), None)
        value  = select.values[0] if select and select.values else ""

        if value.startswith("story:"):
            story_id = int(value.split(":")[1])
            from features.fanart.views.fanart_search_view import SearchStoryView
            view  = SearchStoryView(story_id=story_id, viewer=interaction.user, back_detail=self)
            embed = view.build_story_embed()
            if not embed:
                await interaction.response.send_message("Story not found.", ephemeral=True, delete_after=3)
                return
            await interaction.response.edit_message(embed=embed, view=view)
            return

        if value.startswith("author:"):
            story_id   = int(value.split(":")[1])
            from database import get_discord_id_by_story, get_stories_by_discord_user
            discord_id = get_discord_id_by_story(story_id)
            if not discord_id:
                await interaction.response.send_message("Author not found.", ephemeral=True, delete_after=3)
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
            stories = get_stories_by_discord_user(discord_id)
            from features.fanart.views.fanart_search_view import SearchAuthorView
            view = SearchAuthorView(
                stories=stories, viewer=interaction.user,
                target_user=target, back_detail=self,
            )
            await interaction.response.edit_message(embed=view.generate_bio_embed(), view=view)
            return

    async def _return(self, interaction: discord.Interaction):
        self.roster.page = self.return_page
        self.roster._rebuild_ui()
        await interaction.response.edit_message(embed=self.roster.build_embed(), view=self.roster)
