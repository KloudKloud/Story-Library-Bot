import discord
from discord import ui

from database import get_user_id, get_world_card_owner_count
from ui import TimeoutMixin


PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

SORT_CYCLE  = ["alpha", "alpha_z", "newest", "collected"]
SORT_LABELS = {
    "alpha":     "🔤 A–Z",
    "alpha_z":   "🔤 Z–A",
    "newest":    "🕐 Newest",
    "collected": "🃏 Most",
}

_PAGE_SPARKS = ["✨", "🌸", "⭐", "💎", "🌺", "🔮", "💫"]
_DIVIDERS    = [
    "✦ · · ✦ · · ✦ · · ✦",
    "· ˖ ✦ ˖ · ˖ ✦ ˖ ·",
    "⋆ ˚ ✦ ˚ ⋆ · ⋆ ˚ ✦",
]


def _sort_worlds(worlds: list, sort: str) -> list:
    if sort == "alpha_z":
        return sorted(worlds, key=lambda w: (w.get("name") or "").lower(), reverse=True)
    if sort == "newest":
        return sorted(worlds, key=lambda w: w.get("id", 0), reverse=True)
    if sort == "collected":
        return sorted(worlds, key=lambda w: get_world_card_owner_count(w["id"]), reverse=True)
    return sorted(worlds, key=lambda w: (w.get("name") or "").lower())


# ─────────────────────────────────────────────────
# Roster embed
# ─────────────────────────────────────────────────

def build_roster_embed(worlds, page, total_pages, viewer_name, viewer_discord_id=None):
    from database import get_profile_by_discord_id

    start       = page * PAGE_SIZE
    page_worlds = worlds[start:start + PAGE_SIZE]
    spark       = _PAGE_SPARKS[page % len(_PAGE_SPARKS)]
    divider     = _DIVIDERS[page % len(_DIVIDERS)]

    embed = discord.Embed(
        title=f"{spark}  {viewer_name}'s World Cards  {spark}",
        color=discord.Color.from_rgb(100, 200, 230),
    )

    entry_sep = "-# · · · · · · · · · ·"
    lines = [f"-# {divider}"]

    for i, w in enumerate(page_worlds):
        global_num  = start + i + 1
        story       = w.get("story_title") or "Unknown Story"
        world_type  = w.get("world_type") or "World Card"
        card_count  = get_world_card_owner_count(w["id"])
        has_shiny   = bool(w.get("shiny_image_url"))
        shiny_tag   = "  · 💠 Shiny" if has_shiny else ""

        lines.append(
            f"{NUMBER_EMOJIS[i]}  **{w['name']}**  ✦  *{world_type}*{shiny_tag}\n"
            f"-# 📚 {story}  ·  🃏 {card_count} collected  ·  #{global_num}"
        )
        if i < len(page_worlds) - 1:
            lines.append(entry_sep)

    lines.append(f"-# {divider}")
    embed.description = "\n".join(lines)

    if viewer_discord_id:
        try:
            profile = get_profile_by_discord_id(viewer_discord_id)
            img = profile.get("image_url") if profile else None
            if img and img.startswith("http"):
                embed.set_thumbnail(url=img)
        except Exception:
            pass

    embed.set_footer(
        text=f"Page {page + 1} of {total_pages}  ·  {len(worlds)} world card{'s' if len(worlds) != 1 else ''} total"
    )
    return embed


# ─────────────────────────────────────────────────
# Jump-to-page modal
# ─────────────────────────────────────────────────

class _WorldsJumpToPageModal(discord.ui.Modal, title="Jump to Page"):
    page_num = discord.ui.TextInput(
        label="Page number",
        placeholder="e.g. 3",
        max_length=4,
        required=True,
    )

    def __init__(self, roster_view):
        super().__init__()
        self.roster_view = roster_view

    async def on_submit(self, interaction):
        try:
            num = int(self.page_num.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid page number.", ephemeral=True, delete_after=4
            )
            return
        total = self.roster_view.total_pages()
        if num < 1 or num > total:
            await interaction.response.send_message(
                f"❌ Page must be between 1 and {total}.", ephemeral=True, delete_after=4
            )
            return
        self.roster_view.page = num - 1
        self.roster_view._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_roster_embed(
                self.roster_view.worlds,
                self.roster_view.page,
                total,
                interaction.user.display_name,
                viewer_discord_id=str(interaction.user.id),
            ),
            view=self.roster_view,
        )


# ─────────────────────────────────────────────────
# World card detail view (single card with Return)
# ─────────────────────────────────────────────────

class MyWorldDetailView(TimeoutMixin, ui.View):

    def __init__(self, worlds, world_index, viewer, return_page):
        super().__init__(timeout=300)
        self.worlds      = worlds
        self.world_index = world_index
        self.viewer      = viewer
        self.return_page = return_page
        self.shiny       = False
        self._rebuild_ui()

    def current_world(self):
        return self.worlds[self.world_index]

    def _has_shiny(self):
        return bool(self.current_world().get("shiny_image_url"))

    def build_embed(self):
        from embeds.world_card_embed import build_world_card_embed
        uid = get_user_id(str(self.viewer.id))
        return build_world_card_embed(
            self.current_world(),
            uid,
            shiny=self.shiny,
            index=self.world_index + 1,
            total=len(self.worlds),
        )

    def _rebuild_ui(self):
        self.clear_items()

        prev = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.world_index == 0),
        )
        prev.callback = self._prev
        self.add_item(prev)

        if self._has_shiny():
            shiny_btn = ui.Button(
                label="🖼️ Normal" if self.shiny else "✨ Shiny",
                style=discord.ButtonStyle.primary,
                row=0,
            )
            shiny_btn.callback = self._toggle_shiny
            self.add_item(shiny_btn)

        back_btn = ui.Button(label="↩️ Return", style=discord.ButtonStyle.success, row=0)
        back_btn.callback = self._back
        self.add_item(back_btn)

        nxt = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.world_index >= len(self.worlds) - 1),
        )
        nxt.callback = self._next
        self.add_item(nxt)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.", ephemeral=True, delete_after=5
            )
            return False
        return True

    async def _toggle_shiny(self, interaction):
        self.shiny = not self.shiny
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _prev(self, interaction):
        self.world_index -= 1
        self.shiny = False
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction):
        self.world_index += 1
        self.shiny = False
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _back(self, interaction):
        total_pages = (len(self.worlds) + PAGE_SIZE - 1) // PAGE_SIZE
        roster = MyWorldsRosterView(self.worlds, self.viewer, start_page=self.return_page)
        await interaction.response.edit_message(
            embed=build_roster_embed(
                self.worlds, self.return_page, total_pages,
                interaction.user.display_name,
                viewer_discord_id=str(interaction.user.id),
            ),
            view=roster,
        )


# ─────────────────────────────────────────────────
# Roster view
# ─────────────────────────────────────────────────

class MyWorldsRosterView(TimeoutMixin, ui.View):

    def __init__(self, worlds, viewer, start_page=0):
        super().__init__(timeout=300)
        self.all_worlds = worlds
        self.viewer     = viewer
        self.viewer_did = str(viewer.id)
        self.sort       = "alpha"
        self.worlds     = _sort_worlds(worlds, self.sort)
        self.page       = start_page
        self._rebuild_ui()

    def total_pages(self):
        return max(1, (len(self.worlds) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _page_worlds(self):
        start = self.page * PAGE_SIZE
        return self.worlds[start:start + PAGE_SIZE]

    def _rebuild_ui(self):
        self.clear_items()
        page_worlds = self._page_worlds()

        # Row 0: index buttons 1–5
        for i in range(min(len(page_worlds), PAGE_SIZE)):
            btn = ui.Button(emoji=NUMBER_EMOJIS[i], style=discord.ButtonStyle.primary, row=0)
            btn.callback = self._make_open_callback(i)
            self.add_item(btn)

        # Row 1: ⬅️  sort  Jump to...  ➡️
        prev_btn = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary,
            row=1, disabled=(self.page == 0),
        )
        prev_btn.callback = self._roster_prev
        self.add_item(prev_btn)

        sort_btn = ui.Button(
            label=SORT_LABELS[self.sort],
            style=discord.ButtonStyle.primary,
            row=1,
        )
        sort_btn.callback = self._cycle_sort
        self.add_item(sort_btn)

        jump_btn = ui.Button(label="Jump to...", style=discord.ButtonStyle.success, row=1)
        jump_btn.callback = self._roster_jump
        self.add_item(jump_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=1, disabled=(self.page >= self.total_pages() - 1),
        )
        next_btn.callback = self._roster_next
        self.add_item(next_btn)

    def _make_open_callback(self, slot_index):
        async def callback(interaction):
            global_index = self.page * PAGE_SIZE + slot_index
            if global_index >= len(self.worlds):
                await interaction.response.send_message("World card not found.", ephemeral=True)
                return
            detail_view = MyWorldDetailView(
                self.worlds, global_index, self.viewer, return_page=self.page
            )
            await interaction.response.edit_message(
                embed=detail_view.build_embed(), view=detail_view
            )
        return callback

    async def _cycle_sort(self, interaction):
        idx         = SORT_CYCLE.index(self.sort)
        self.sort   = SORT_CYCLE[(idx + 1) % len(SORT_CYCLE)]
        self.worlds = _sort_worlds(self.all_worlds, self.sort)
        self.page   = 0
        self._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_roster_embed(
                self.worlds, self.page, self.total_pages(),
                interaction.user.display_name, viewer_discord_id=self.viewer_did,
            ),
            view=self,
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.", ephemeral=True, delete_after=5
            )
            return False
        return True

    async def _roster_prev(self, interaction):
        self.page = max(0, self.page - 1)
        self._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_roster_embed(
                self.worlds, self.page, self.total_pages(),
                interaction.user.display_name, viewer_discord_id=self.viewer_did,
            ),
            view=self,
        )

    async def _roster_next(self, interaction):
        self.page = min(self.total_pages() - 1, self.page + 1)
        self._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_roster_embed(
                self.worlds, self.page, self.total_pages(),
                interaction.user.display_name, viewer_discord_id=self.viewer_did,
            ),
            view=self,
        )

    async def _roster_jump(self, interaction):
        await interaction.response.send_modal(_WorldsJumpToPageModal(self))
