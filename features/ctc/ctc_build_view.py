import discord
from discord import ui

from ui import TimeoutMixin
from ui.base_builder_view import BaseBuilderView

PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

SORT_CYCLE  = ["alpha", "alpha_z", "char_first", "world_first"]
SORT_LABELS = {
    "alpha":       "A–Z",
    "alpha_z":     "Z–A",
    "char_first":  "👤",
    "world_first": "🌍",
}

_SPARKS    = ["✨", "🌸", "⭐", "💎", "🌺", "🔮", "💫"]
_DIVIDERS  = [
    "✦ ˖ ⋆ ˚ · ✧ · ˚ ⋆ ˖ ✦ ˖ ⋆ ˚ · ✧ · ˚ ⋆ ˖ ✦",
    "⋆ ˚ ✦ ˖ · ˖ ✧ ˖ · ˖ ✦ ˚ ⋆ ˚ ✦ ˖ · ˖ ✧ ˖ ✦",
    "· ˖ ✧ ˚ ✦ · ⋆ · ✦ ˚ ✧ ˖ · ˖ ✧ ˚ ✦ · ⋆ · ✦",
]
_ENTRY_SEP = "-# ˖ · · ⋆ · · ˖ · · ✦ · · ˖ · · ⋆ · · ˖"


# ─────────────────────────────────────────────────
# Sort helper
# ─────────────────────────────────────────────────

def _sort_cards(cards: list, sort: str) -> list:
    if sort == "alpha_z":
        return sorted(cards, key=lambda c: (c.get("name") or "").lower(), reverse=True)
    if sort == "char_first":
        return sorted(cards, key=lambda c: (
            0 if c.get("card_type", "char") == "char" else 1,
            (c.get("name") or "").lower()
        ))
    if sort == "world_first":
        return sorted(cards, key=lambda c: (
            0 if c.get("card_type") == "world" else 1,
            (c.get("name") or "").lower()
        ))
    return sorted(cards, key=lambda c: (c.get("name") or "").lower())


# ─────────────────────────────────────────────────
# Roster embed
# ─────────────────────────────────────────────────

def build_ctc_roster_embed(cards: list, page: int, total_pages: int,
                            viewer_name: str, viewer_discord_id: str = None,
                            sort: str = "alpha") -> discord.Embed:
    start      = page * PAGE_SIZE
    page_cards = cards[start:start + PAGE_SIZE]
    spark      = _SPARKS[page % len(_SPARKS)]
    divider    = _DIVIDERS[page % len(_DIVIDERS)]

    embed = discord.Embed(
        title = f"{spark}  {viewer_name}'s CTC Card Builder  {spark}",
        color = discord.Color.from_rgb(180, 140, 255),
    )

    if viewer_discord_id:
        try:
            from database import get_profile_by_discord_id
            profile = get_profile_by_discord_id(viewer_discord_id)
            img = profile.get("image_url") if profile else None
            if img and img.startswith("http"):
                embed.set_thumbnail(url=img)
        except Exception:
            pass

    lines = [f"-# {divider}"]
    for i, c in enumerate(page_cards):
        has_shiny = bool(c.get("shiny_image_url"))
        ctype     = c.get("card_type", "char")
        story     = c.get("story_title") or "Unknown Story"

        shiny_tag = "💠 ✅  Shiny set" if has_shiny else "💠 ❌  No shiny art"

        if ctype == "world":
            world_type = c.get("world_type") or "World Card"
            extra_tag  = f"  ·  🌍 {world_type}"
        else:
            is_mc = bool(c.get("is_main_character"))
            extra_tag = "  ·  ⭐ MC" if is_mc else ""

        lines.append(
            f"{NUMBER_EMOJIS[i]}  **{c['name']}**\n"
            f"-# 📚 {story}  ·  {shiny_tag}{extra_tag}"
        )
        if i < len(page_cards) - 1:
            lines.append(_ENTRY_SEP)

    lines.append(f"-# {divider}")
    embed.description = "\n".join(lines)
    embed.set_footer(
        text=f"Page {page + 1} of {total_pages}  ·  {len(cards)} card{'s' if len(cards) != 1 else ''} total  ·  {SORT_LABELS[sort]}"
    )
    return embed


# ─────────────────────────────────────────────────
# Jump-to-page modal
# ─────────────────────────────────────────────────

class _CTCJumpModal(discord.ui.Modal, title="Jump to Page"):
    page_num = discord.ui.TextInput(
        label="Page number", placeholder="e.g. 2", max_length=4, required=True
    )

    def __init__(self, roster_view: "CTCRosterView"):
        super().__init__()
        self.roster_view = roster_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            num = int(self.page_num.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ Enter a valid page number.", ephemeral=True, delete_after=4
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
            embed=build_ctc_roster_embed(
                self.roster_view.cards, self.roster_view.page,
                total, self.roster_view.viewer.display_name,
                viewer_discord_id=str(self.roster_view.viewer.id),
                sort=self.roster_view.sort,
            ),
            view=self.roster_view,
        )


# ─────────────────────────────────────────────────
# Detail / builder view for a single card (char or world)
# ─────────────────────────────────────────────────

class CTCBuildDetailView(BaseBuilderView):
    """
    Row 0: ← | ✨ Shiny (preview toggle) | Add/Edit Shiny Image | ↩️ Return | →
    """

    def __init__(self, cards: list, index: int, viewer: discord.Member,
                 return_page: int, uid: int):
        super().__init__(viewer)
        self.cards       = cards
        self.index       = index
        self.return_page = return_page
        self.uid         = uid
        self._shiny_view = False
        self._reload_current()
        self._rebuild_ui()

    # ── Core ────────────────────────────────────────

    def _reload_current(self):
        card  = self.cards[self.index]
        ctype = card.get("card_type", "char")
        if ctype == "world":
            from database import get_world_card_by_id
            fresh = get_world_card_by_id(card["id"])
            if fresh:
                merged = dict(fresh)
                for key in ("story_title", "story_id", "card_type"):
                    if not merged.get(key) and card.get(key):
                        merged[key] = card[key]
                merged["card_type"] = "world"
                self.cards[self.index] = merged
        else:
            from database import get_character_by_id
            fresh = get_character_by_id(card["id"])
            if fresh:
                merged = dict(fresh)
                for key in ("story_title", "story_id"):
                    if not merged.get(key) and card.get(key):
                        merged[key] = card[key]
                merged.setdefault("card_type", "char")
                self.cards[self.index] = merged

    def current_card(self) -> dict:
        return self.cards[self.index]

    # backward compat alias
    def current_char(self) -> dict:
        return self.current_card()

    def _has_shiny_img(self) -> bool:
        return bool(self.current_card().get("shiny_image_url"))

    # ── Embed ────────────────────────────────────────

    def build_embed(self) -> discord.Embed:
        card      = self.current_card()
        ctype     = card.get("card_type", "char")
        has_shiny = self._has_shiny_img()
        show_shiny = self._shiny_view and has_shiny

        if ctype == "world":
            from embeds.world_card_embed import build_world_card_embed
            embed = build_world_card_embed(
                card, self.user.id,
                shiny = show_shiny,
                index = self.index + 1,
                total = len(self.cards),
            )
        else:
            from embeds.ctc_card_embed import build_ctc_card_embed
            embed, _ = build_ctc_card_embed(
                card, self.user.id,
                viewer = self.user,
                shiny  = show_shiny,
                index  = self.index + 1,
                total  = len(self.cards),
            )

        mode_note    = "✨ Shiny preview" if show_shiny else "🖼️ Normal preview"
        shiny_status = "💠 ✅ Shiny art set" if has_shiny else "💠 ❌ No shiny art"
        quote        = card.get("quote")
        footer_parts = []
        if quote:
            footer_parts.append(f'"{quote[:120]}"')
        footer_parts.append(f"{mode_note}  ·  {shiny_status}  ·  CTC Builder")
        embed.set_footer(text="  ·  ".join(footer_parts))
        return embed

    # ── UI ───────────────────────────────────────────

    def _rebuild_ui(self):
        self.clear_items()
        has_shiny = self._has_shiny_img()

        prev_btn = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index == 0),
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        shiny_btn = ui.Button(
            label    = "✨ Shiny" if not self._shiny_view else "✦ Normal",
            emoji    = "🌟" if has_shiny else None,
            style    = discord.ButtonStyle.primary,
            row      = 0,
            disabled = not has_shiny,
        )
        shiny_btn.callback = self._toggle_shiny
        self.add_item(shiny_btn)

        shiny_img_btn = ui.Button(
            label = "Edit Shiny Image" if has_shiny else "Add Shiny Image",
            style = discord.ButtonStyle.primary,
            row   = 0,
        )
        shiny_img_btn.callback = self._set_shiny_image
        self.add_item(shiny_img_btn)

        ret_btn = ui.Button(label="↩️ Return", style=discord.ButtonStyle.success, row=0)
        ret_btn.callback = self._return
        self.add_item(ret_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index >= len(self.cards) - 1),
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

    # ── Button callbacks ─────────────────────────────

    async def _prev(self, interaction: discord.Interaction):
        self._shiny_view = False
        self.index -= 1
        self._reload_current()
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self._shiny_view = False
        self.index += 1
        self._reload_current()
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _toggle_shiny(self, interaction: discord.Interaction):
        self._shiny_view = not self._shiny_view
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _set_shiny_image(self, interaction: discord.Interaction):
        card      = self.current_card()
        card_name = card.get("name", "this card")
        ctype     = card.get("card_type", "char")

        if ctype == "world":
            from features.world.service import update_world_details

            async def save_shiny(url: str):
                update_world_details(card["id"], shiny_image_url=url)
                self._reload_current()
                self._rebuild_ui()
                await self._safe_edit(embed=self.build_embed(), view=self)

            await self.handle_image_upload(
                interaction, save_shiny,
                pad_ratio = 4 / 3,
                prompt_prefix = (
                    "✨ **CTC Shiny Card Art — World Card**\n\n"
                    "Upload a special image for the ✨ shiny version of "
                    f"**{card_name}**'s world card.\n\n"
                ),
                confirmation_message = f"💠 **Shiny card art saved for {card_name}!** 🎉",
            )
        else:
            from features.characters.service import update_character_details

            async def save_shiny(url: str):
                update_character_details(card["id"], shiny_image_url=url)
                self._reload_current()
                self._rebuild_ui()
                await self._safe_edit(embed=self.build_embed(), view=self)

            await self.handle_image_upload(
                interaction, save_shiny,
                pad_ratio = 4 / 3,
                prompt_prefix = (
                    "✨ **CTC Shiny Card Art**\n\n"
                    "Upload a special image to display when readers view the **shiny ✨ version** "
                    f"of **{card_name}**'s CTC card.\n"
                    "This is optional — if you skip it, the normal card art is used for shiny rolls too.\n\n"
                    "*Tip: something that feels sparkly, golden, or alternate-palette works great!*\n\n"
                ),
                confirmation_message = (
                    f"💠 **Shiny card art saved for {card_name}!**\n"
                    "Whenever someone spins or collects a ✨ shiny version of your character, "
                    "they'll see this special art instead of the normal card image. 🎉"
                ),
            )

    async def _return(self, interaction: discord.Interaction):
        roster = CTCRosterView(self.cards, self.user, self.uid, start_page=self.return_page)
        roster.builder_message = self.builder_message
        await roster.attach_message(self.builder_message)
        await interaction.response.edit_message(
            embed=build_ctc_roster_embed(
                roster.cards, self.return_page, roster.total_pages(),
                self.user.display_name,
                viewer_discord_id=str(self.user.id),
                sort=roster.sort,
            ),
            view=roster,
        )


# ─────────────────────────────────────────────────
# Roster browse view
# ─────────────────────────────────────────────────

class CTCRosterView(TimeoutMixin, ui.View):
    """5-per-page browse of all your chars + world cards showing shiny art status."""

    def __init__(self, cards: list, viewer: discord.Member, uid: int, start_page: int = 0):
        super().__init__(timeout=300)
        self.all_cards = cards
        self.viewer    = viewer
        self.uid       = uid
        self.sort      = "alpha"
        self.cards     = _sort_cards(cards, self.sort)
        self.page      = start_page
        self.builder_message = None
        self._rebuild_ui()

    def total_pages(self) -> int:
        return max(1, (len(self.cards) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _page_cards(self) -> list:
        start = self.page * PAGE_SIZE
        return self.cards[start:start + PAGE_SIZE]

    async def attach_message(self, message):
        self.builder_message = message

    def _rebuild_ui(self):
        self.clear_items()
        page_cards = self._page_cards()

        # Row 0: number buttons
        for i in range(len(page_cards)):
            btn = ui.Button(emoji=NUMBER_EMOJIS[i], style=discord.ButtonStyle.primary, row=0)
            btn.callback = self._make_open_cb(i)
            self.add_item(btn)

        # Row 1: ⬅️  Sort  Pg. #/##  ➡️
        prev_btn = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary,
            row=1, disabled=(self.page == 0),
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        sort_btn = ui.Button(
            label=SORT_LABELS[self.sort],
            style=discord.ButtonStyle.primary,
            row=1,
        )
        sort_btn.callback = self._cycle_sort
        self.add_item(sort_btn)

        jump_btn = ui.Button(
            label    = f"Pg. {self.page + 1}/{self.total_pages()}",
            style    = discord.ButtonStyle.success,
            row      = 1,
            disabled = (self.total_pages() == 1),
        )
        jump_btn.callback = self._jump
        self.add_item(jump_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=1, disabled=(self.page >= self.total_pages() - 1),
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

    def _make_open_cb(self, slot_index: int):
        async def callback(interaction: discord.Interaction):
            global_index = self.page * PAGE_SIZE + slot_index
            if global_index >= len(self.cards):
                await interaction.response.send_message("Card not found.", ephemeral=True)
                return
            detail = CTCBuildDetailView(
                self.cards, global_index, self.viewer,
                return_page=self.page, uid=self.uid
            )
            detail.builder_message = self.builder_message
            await detail.attach_message(self.builder_message)
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

    def _build_embed(self) -> discord.Embed:
        return build_ctc_roster_embed(
            self.cards, self.page, self.total_pages(),
            self.viewer.display_name,
            viewer_discord_id=str(self.viewer.id),
            sort=self.sort,
        )

    async def _prev(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.page = min(self.total_pages() - 1, self.page + 1)
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    async def _cycle_sort(self, interaction: discord.Interaction):
        idx        = SORT_CYCLE.index(self.sort)
        self.sort  = SORT_CYCLE[(idx + 1) % len(SORT_CYCLE)]
        self.cards = _sort_cards(self.all_cards, self.sort)
        self.page  = 0
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    async def _jump(self, interaction: discord.Interaction):
        await interaction.response.send_modal(_CTCJumpModal(self))
