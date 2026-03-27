import discord
from discord import ui

from ui import TimeoutMixin
from ui.base_builder_view import BaseBuilderView

PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


# ─────────────────────────────────────────────────
# Roster embed
# ─────────────────────────────────────────────────

_SPARKS    = ["✨", "🌸", "⭐", "💎", "🌺", "🔮", "💫"]
_DIVIDERS  = [
    "✦ ˖ ⋆ ˚ · ✧ · ˚ ⋆ ˖ ✦ ˖ ⋆ ˚ · ✧ · ˚ ⋆ ˖ ✦",
    "⋆ ˚ ✦ ˖ · ˖ ✧ ˖ · ˖ ✦ ˚ ⋆ ˚ ✦ ˖ · ˖ ✧ ˖ ✦",
    "· ˖ ✧ ˚ ✦ · ⋆ · ✦ ˚ ✧ ˖ · ˖ ✧ ˚ ✦ · ⋆ · ✦",
]
_ENTRY_SEP = "-# ˖ · · ⋆ · · ˖ · · ✦ · · ˖ · · ⋆ · · ˖"


def build_ctc_roster_embed(chars: list, page: int, total_pages: int,
                            viewer_name: str, viewer_discord_id: str = None) -> discord.Embed:
    start      = page * PAGE_SIZE
    page_chars = chars[start:start + PAGE_SIZE]
    spark      = _SPARKS[page % len(_SPARKS)]
    divider    = _DIVIDERS[page % len(_DIVIDERS)]

    embed = discord.Embed(
        title = f"{spark}  {viewer_name}'s CTC Card Builder  {spark}",
        color = discord.Color.from_rgb(180, 140, 255),
    )

    # User profile image as thumbnail
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
    for i, c in enumerate(page_chars):
        has_shiny = bool(c.get("shiny_image_url"))
        is_mc     = bool(c.get("is_main_character"))
        story     = c.get("story_title") or "Unknown Story"

        shiny_tag = "💠 ✅  Shiny set" if has_shiny else "💠 ❌  No shiny art"
        mc_tag    = "  ·  ⭐ MC" if is_mc     else ""

        lines.append(
            f"{NUMBER_EMOJIS[i]}  **{c['name']}**\n"
            f"-# 📚 {story}  ·  {shiny_tag}{mc_tag}"
        )
        if i < len(page_chars) - 1:
            lines.append(_ENTRY_SEP)

    lines.append(f"-# {divider}")
    embed.description = "\n".join(lines)
    embed.set_footer(
        text=f"Page {page + 1} of {total_pages}  ·  {len(chars)} character{'s' if len(chars) != 1 else ''} total"
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
                self.roster_view.chars, self.roster_view.page,
                total, self.roster_view.viewer.display_name,
                viewer_discord_id=str(self.roster_view.viewer.id),
            ),
            view=self.roster_view,
        )


# ─────────────────────────────────────────────────
# Detail / builder view for a single character
# ─────────────────────────────────────────────────

class CTCBuildDetailView(BaseBuilderView):
    """
    Row 0: ← | ✨ Shiny (preview toggle) | Add/Edit Shiny Image | ↩️ Return | →
    """

    def __init__(self, chars: list, index: int, viewer: discord.Member,
                 return_page: int, uid: int):
        super().__init__(viewer)
        self.chars       = chars
        self.index       = index
        self.return_page = return_page
        self.uid         = uid
        self._shiny_view = False
        self._reload_current()
        self._rebuild_ui()

    # ── Core ────────────────────────────────────────

    def _reload_current(self):
        from database import get_character_by_id
        fresh = get_character_by_id(self.chars[self.index]["id"])
        if fresh:
            existing = self.chars[self.index]
            merged = dict(fresh)
            # get_character_by_id has no story JOIN — preserve story fields from the original
            for key in ("story_title", "story_id"):
                if not merged.get(key) and existing.get(key):
                    merged[key] = existing[key]
            self.chars[self.index] = merged

    def current_char(self) -> dict:
        return self.chars[self.index]

    def _has_shiny_img(self) -> bool:
        return bool(self.current_char().get("shiny_image_url"))

    # ── Embed ────────────────────────────────────────

    def build_embed(self) -> discord.Embed:
        from embeds.ctc_card_embed import build_ctc_card_embed
        char      = self.current_char()
        has_shiny = self._has_shiny_img()
        show_shiny = self._shiny_view and has_shiny

        embed, _ = build_ctc_card_embed(
            char,
            self.user.id,
            viewer = self.user,
            shiny  = show_shiny,
            index  = self.index + 1,
            total  = len(self.chars),
        )

        # Append builder status note to footer (include quote if set)
        mode_note    = "✨ Shiny preview" if show_shiny else "🖼️ Normal preview"
        shiny_status = "💠 ✅ Shiny art set" if has_shiny else "💠 ❌ No shiny art"
        quote        = char.get("quote")
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

        # Row 0: ← | ✨ Shiny | Add/Edit Shiny Image | Make Stats | →
        prev_btn = ui.Button(
            emoji    = "⬅️",
            style    = discord.ButtonStyle.secondary,
            row      = 0,
            disabled = (self.index == 0),
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
            emoji    = "➡️",
            style    = discord.ButtonStyle.secondary,
            row      = 0,
            disabled = (self.index >= len(self.chars) - 1),
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
        from features.characters.service import update_character_details
        char      = self.current_char()
        char_name = char.get("name", "this character")

        async def save_shiny(url: str):
            update_character_details(char["id"], shiny_image_url=url)
            self._reload_current()
            self._rebuild_ui()
            await self._safe_edit(embed=self.build_embed(), view=self)

        await self.handle_image_upload(
            interaction,
            save_shiny,
            pad_ratio = 4 / 3,
            prompt_prefix = (
                "✨ **CTC Shiny Card Art**\n\n"
                "Upload a special image to display when readers view the **shiny ✨ version** "
                f"of **{char_name}**'s CTC card.\n"
                "This is optional — if you skip it, the normal card art is used for shiny rolls too.\n\n"
                "*Tip: something that feels sparkly, golden, or alternate-palette works great!*\n\n"
            ),
            confirmation_message = (
                f"💠 **Shiny card art saved for {char_name}!**\n"
                "Whenever someone spins or collects a ✨ shiny version of your character, "
                "they'll see this special art instead of the normal card image. 🎉"
            ),
        )

    async def _return(self, interaction: discord.Interaction):
        total_pages = max(1, (len(self.chars) + PAGE_SIZE - 1) // PAGE_SIZE)
        roster = CTCRosterView(self.chars, self.user, self.uid, start_page=self.return_page)
        roster.builder_message = self.builder_message
        await roster.attach_message(self.builder_message)
        await interaction.response.edit_message(
            embed=build_ctc_roster_embed(
                self.chars, self.return_page, total_pages, self.user.display_name,
                viewer_discord_id=str(self.user.id),
            ),
            view=roster,
        )


# ─────────────────────────────────────────────────
# Roster browse view
# ─────────────────────────────────────────────────

class CTCRosterView(TimeoutMixin, ui.View):
    """5-per-page browse of all your characters showing shiny art status."""

    def __init__(self, chars: list, viewer: discord.Member, uid: int, start_page: int = 0):
        super().__init__(timeout=300)
        self.chars   = chars
        self.viewer  = viewer
        self.uid     = uid
        self.page    = start_page
        self.builder_message = None
        self._rebuild_ui()

    def total_pages(self) -> int:
        return max(1, (len(self.chars) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _page_chars(self) -> list:
        start = self.page * PAGE_SIZE
        return self.chars[start:start + PAGE_SIZE]

    async def attach_message(self, message):
        self.builder_message = message

    def _rebuild_ui(self):
        self.clear_items()
        page_chars = self._page_chars()

        # Row 0: number buttons (up to 5)
        for i in range(len(page_chars)):
            btn = ui.Button(emoji=NUMBER_EMOJIS[i], style=discord.ButtonStyle.primary, row=0)
            btn.callback = self._make_open_cb(i)
            self.add_item(btn)

        # Row 1: ← Jump to... →
        prev_btn = ui.Button(
            emoji    = "⬅️",
            style    = discord.ButtonStyle.secondary,
            row      = 1,
            disabled = (self.page == 0),
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        jump_btn = ui.Button(
            label    = "Jump to...",
            style    = discord.ButtonStyle.success,
            row      = 1,
            disabled = (self.total_pages() == 1),
        )
        jump_btn.callback = self._jump
        self.add_item(jump_btn)

        next_btn = ui.Button(
            emoji    = "➡️",
            style    = discord.ButtonStyle.secondary,
            row      = 1,
            disabled = (self.page >= self.total_pages() - 1),
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

    def _make_open_cb(self, slot_index: int):
        async def callback(interaction: discord.Interaction):
            global_index = self.page * PAGE_SIZE + slot_index
            if global_index >= len(self.chars):
                await interaction.response.send_message("Character not found.", ephemeral=True)
                return
            detail = CTCBuildDetailView(
                self.chars, global_index, self.viewer,
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

    async def _prev(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_ctc_roster_embed(
                self.chars, self.page, self.total_pages(), self.viewer.display_name,
                viewer_discord_id=str(self.viewer.id),
            ),
            view=self,
        )

    async def _next(self, interaction: discord.Interaction):
        self.page = min(self.total_pages() - 1, self.page + 1)
        self._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_ctc_roster_embed(
                self.chars, self.page, self.total_pages(), self.viewer.display_name,
                viewer_discord_id=str(self.viewer.id),
            ),
            view=self,
        )

    async def _jump(self, interaction: discord.Interaction):
        await interaction.response.send_modal(_CTCJumpModal(self))
