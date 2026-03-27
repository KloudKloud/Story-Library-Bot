import discord
from discord import ui

from ui import TimeoutMixin
from ui.base_builder_view import BaseBuilderView

PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

_SPARKS   = ["✨", "🌸", "⭐", "💎", "🌺", "🔮", "💫"]
_DIVIDERS = [
    "✦ ˖ ⋆ ˚ · ✧ · ˚ ⋆ ˖ ✦ ˖ ⋆ ˚ · ✧ · ˚ ⋆ ˖ ✦",
    "⋆ ˚ ✦ ˖ · ˖ ✧ ˖ · ˖ ✦ ˚ ⋆ ˚ ✦ ˖ · ˖ ✧ ˖ ✦",
    "· ˖ ✧ ˚ ✦ · ⋆ · ✦ ˚ ✧ ˖ · ˖ ✧ ˚ ✦ · ⋆ · ✦",
]
_ENTRY_SEP = "-# ˖ · · ⋆ · · ˖ · · ✦ · · ˖ · · ⋆ · · ˖"

_DETAIL_FIELDS = ("image_url", "description", "lore", "world_type", "quote", "music_url")

# 7 fields tracked in the builder progress bar
_PROGRESS_FIELDS = ("image_url", "shiny_image_url", "description", "lore", "world_type", "quote", "music_url")

_DIV = "✦ ·  · ✧ · ────────── · ✧ ·  · ✦"


def _world_roster_stats(world: dict) -> tuple[int, int]:
    """Returns (complete_count, total_count) for required detail fields."""
    required = ("image_url", "description", "lore", "world_type")
    done = sum(1 for f in required if world.get(f))
    return done, len(required)


# ─────────────────────────────────────────────────
# Roster embed
# ─────────────────────────────────────────────────

def build_world_roster_embed(
    worlds: list,
    page: int,
    total_pages: int,
    viewer_name: str,
    viewer_discord_id: str = None,
) -> discord.Embed:
    start       = page * PAGE_SIZE
    page_worlds = worlds[start : start + PAGE_SIZE]
    spark       = _SPARKS[page % len(_SPARKS)]
    divider     = _DIVIDERS[page % len(_DIVIDERS)]

    embed = discord.Embed(
        title = f"{spark}  {viewer_name}'s World Builder  {spark}",
        color = discord.Color.from_rgb(100, 200, 230),
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

    lines = [f"-# {divider}", ""]
    for i, w in enumerate(page_worlds):
        done, total = _world_roster_stats(w)
        story       = w.get("story_title") or "Unknown Story"
        world_type  = w.get("world_type") or "Unknown"
        has_shiny   = bool(w.get("shiny_image_url"))
        is_complete = (done == total)

        shiny_tag = "💠 ✅  Shiny set" if has_shiny else "💠 ❌  No shiny art"

        if is_complete:
            lines.append(
                f"{NUMBER_EMOJIS[i]}  ✨ **{w['name']}** ✨  **—  Done!**  ({shiny_tag})\n"
                f"-# 📚 {story}  ·  🏷️ {world_type}\n"
                f"-# ⭐ **Fully Complete**"
            )
        else:
            img_tag  = "🖼️ ✅" if w.get("image_url")    else "🖼️ ❌"
            desc_tag = "📝 ✅" if w.get("description")   else "📝 ❌"
            lore_tag = "📖 ✅" if w.get("lore")          else "📖 ❌"
            type_tag = "🏷️ ✅" if w.get("world_type")   else "🏷️ ❌"

            lines.append(
                f"{NUMBER_EMOJIS[i]}  ⏳ **{w['name']}**\n"
                f"-# 📚 {story}  ·  {img_tag}  {desc_tag}  {lore_tag}  {type_tag}  ⚙️ {done}/{total}\n"
                f"-# ⏳ **Not complete!**"
            )

        if i < len(page_worlds) - 1:
            lines.append(f"\n{_ENTRY_SEP}\n")

    lines.append("")
    lines.append(f"-# {divider}")
    embed.description = "\n".join(lines)
    embed.set_footer(
        text=f"Page {page + 1} of {total_pages}  ·  {len(worlds)} card{'s' if len(worlds) != 1 else ''} total"
    )
    return embed


# ─────────────────────────────────────────────────
# Jump-to-page modal
# ─────────────────────────────────────────────────

class _WorldJumpModal(discord.ui.Modal, title="Jump to Page"):
    page_num = discord.ui.TextInput(
        label="Page number", placeholder="e.g. 2", max_length=4, required=True
    )

    def __init__(self, roster_view: "WorldBuildRosterView"):
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
            embed=build_world_roster_embed(
                self.roster_view.worlds, self.roster_view.page,
                total, self.roster_view.viewer.display_name,
                viewer_discord_id=str(self.roster_view.viewer.id),
            ),
            view=self.roster_view,
        )


# ─────────────────────────────────────────────────
# Modals for text fields
# ─────────────────────────────────────────────────

class _WorldTextModal(discord.ui.Modal):
    def __init__(self, title: str, label: str, field_key: str,
                 placeholder: str, detail_view: "WorldBuildView",
                 current: str = "", max_length: int = 1000):
        super().__init__(title=title)
        self.field_key   = field_key
        self.detail_view = detail_view
        self.text_input  = discord.ui.TextInput(
            label      = label,
            placeholder= placeholder,
            default    = current[:4000] if current else "",
            style      = discord.TextStyle.paragraph,
            required   = False,
            max_length = max_length,
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        from features.world.service import update_world_details
        self.detail_view._modal_open = False
        value = self.text_input.value.strip() or None
        update_world_details(self.detail_view.current_world()["id"], **{self.field_key: value})
        self.detail_view._reload_current()
        self.detail_view._rebuild_ui()
        await interaction.response.edit_message(embed=self.detail_view.build_embed(), view=self.detail_view)


class _WorldTypeModal(discord.ui.Modal, title="Set World Card Type"):
    type_input = discord.ui.TextInput(
        label      = "World Type",
        placeholder= "e.g. Location · Organization · Artifact · Concept · Realm · Phenomenon",
        max_length = 40,
        required   = False,
    )

    def __init__(self, detail_view: "WorldBuildView"):
        super().__init__()
        self.detail_view = detail_view
        current = detail_view.current_world().get("world_type") or ""
        self.type_input.default = current

    async def on_submit(self, interaction: discord.Interaction):
        from features.world.service import update_world_details
        self.detail_view._modal_open = False
        value = self.type_input.value.strip() or None
        update_world_details(self.detail_view.current_world()["id"], world_type=value)
        self.detail_view._reload_current()
        self.detail_view._rebuild_ui()
        await interaction.response.edit_message(embed=self.detail_view.build_embed(), view=self.detail_view)


# ─────────────────────────────────────────────────
# Preview view — shows the actual card embed
# ─────────────────────────────────────────────────

class _WorldPreviewView(ui.View):
    """Replaces the builder with the actual card embed. Has a Back button + optional Shiny toggle."""

    def __init__(self, build_view: "WorldBuildView", shiny: bool = False):
        super().__init__(timeout=300)
        self.build_view = build_view
        self.shiny      = shiny
        self._rebuild_ui()

    def _rebuild_ui(self):
        self.clear_items()

        back_btn = ui.Button(label="⬅️ Back to Editor", style=discord.ButtonStyle.success, row=0)
        back_btn.callback = self._back
        self.add_item(back_btn)

        if self.build_view._has_shiny_img():
            toggle_btn = ui.Button(
                label = "🖼️ Normal" if self.shiny else "✨ Shiny",
                style = discord.ButtonStyle.primary,
                row   = 0,
            )
            toggle_btn.callback = self._toggle_shiny
            self.add_item(toggle_btn)

    def build_preview_embed(self) -> discord.Embed:
        from embeds.world_card_embed import build_world_card_embed
        self.build_view._reload_current()
        world = self.build_view.current_world()
        return build_world_card_embed(
            world,
            self.build_view.user.id,
            shiny = self.shiny,
            index = self.build_view.index + 1,
            total = len(self.build_view.worlds),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.build_view.user.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.", ephemeral=True, delete_after=5
            )
            return False
        return True

    async def _back(self, interaction: discord.Interaction):
        self.build_view._reload_current()
        self.build_view._rebuild_ui()
        await interaction.response.edit_message(
            embed=self.build_view.build_embed(),
            view=self.build_view,
        )

    async def _toggle_shiny(self, interaction: discord.Interaction):
        self.shiny = not self.shiny
        self._rebuild_ui()
        await interaction.response.edit_message(
            embed=self.build_preview_embed(),
            view=self,
        )


# ─────────────────────────────────────────────────
# Detail / builder view for a single world card
# ─────────────────────────────────────────────────

class WorldBuildView(BaseBuilderView):
    """
    Row 0: 📝 Description | 🖼️ Image | 💠 Shiny Image | 🏷️ Type | 👁️ Preview
    Row 1: More World Options... (Select dropdown)
    Row 2: ← | ↩️ Return | →
    """

    def __init__(self, worlds: list, index: int, viewer: discord.Member,
                 return_page: int):
        super().__init__(viewer)
        self.worlds      = worlds
        self.index       = index
        self.return_page = return_page
        self._reload_current()
        self._rebuild_ui()

    # ── Core ────────────────────────────────────────

    def _reload_current(self):
        from database import get_world_card_by_id
        fresh = get_world_card_by_id(self.worlds[self.index]["id"])
        if fresh:
            existing = self.worlds[self.index]
            merged   = dict(fresh)
            for key in ("story_title", "story_id", "author", "cover_url"):
                if not merged.get(key) and existing.get(key):
                    merged[key] = existing[key]
            self.worlds[self.index] = merged

    def current_world(self) -> dict:
        return self.worlds[self.index]

    def _has_shiny_img(self) -> bool:
        return bool(self.current_world().get("shiny_image_url"))

    # ── Embed (informational dashboard) ─────────────

    def build_embed(self) -> discord.Embed:
        world   = self.current_world()
        name    = world.get("name") or "Unknown"
        story   = world.get("story_title") or "Unknown Story"

        filled  = sum(1 for f in _PROGRESS_FIELDS if world.get(f))
        total   = len(_PROGRESS_FIELDS)
        percent = int((filled / total) * 100)
        bar     = self.build_progress_bar(percent)

        embed = discord.Embed(
            title = f"🌍 {name} • {percent}% Complete",
            color = discord.Color.from_rgb(100, 200, 230),
        )

        # ── Progress bar ──────────────────────────────
        embed.add_field(
            name  = "✨ World Card Progress",
            value = f"{bar}\n**{filled}/{total} sections completed**",
            inline=False,
        )

        embed.add_field(name="\u200b", value=_DIV, inline=False)

        # ── Image ─────────────────────────────────────
        embed.add_field(
            name  = "🖼️ Image",
            value = (
                "**Current:** ✅ Set" if world.get("image_url") else
                "Upload art or an illustration for this world card.\n**Current:** ❌ *Not set*"
            ),
            inline=False,
        )

        embed.add_field(name="\u200b", value=_DIV, inline=False)

        # ── Description ───────────────────────────────
        desc_preview = world.get("description") or ""
        embed.add_field(
            name  = "📝 Description",
            value = (
                f"About this world element.\n**Current:** *{desc_preview[:140]}*"
                if desc_preview else
                "About this world element.\n**Current:** *Not written yet*"
            ),
            inline=False,
        )

        embed.add_field(name="\u200b", value=_DIV, inline=False)

        # ── Lore ──────────────────────────────────────
        lore_preview = world.get("lore") or ""
        embed.add_field(
            name  = "📖 Lore",
            value = (
                f"History, mythology, and backstory.\n**Current:** *{lore_preview[:140]}*"
                if lore_preview else
                "History, mythology, and backstory.\n**Current:** *Not written yet*"
            ),
            inline=False,
        )

        embed.add_field(name="\u200b", value=_DIV, inline=False)

        # ── Shiny art ─────────────────────────────────
        shiny_img = world.get("shiny_image_url")
        embed.add_field(
            name  = "💠 Shiny Card Art" + ("  ✔" if shiny_img else "  ✦"),
            value = (
                "✔ Shiny art is set." if shiny_img else
                "Upload a special shiny version of this card's art.\n"
                "-# *Optional — regular art is used by default.*"
            ),
            inline=False,
        )

        embed.add_field(name="\u200b", value=_DIV, inline=False)

        # ── Card details ──────────────────────────────
        embed.add_field(
            name  = "⚙️ Card Details",
            value = (
                f"{'✔' if world.get('world_type') else '✦'} Type\n"
                f"{'✔' if world.get('quote')      else '✦'} Quote\n"
                f"{'✔' if world.get('music_url')  else '✦'} Theme Song"
            ),
            inline=False,
        )

        # Thumbnail: card image if set
        if world.get("image_url"):
            embed.set_thumbnail(url=world["image_url"])

        embed.set_footer(text="✨ Use the buttons below to build and customize your world card")
        return embed

    # ── UI ───────────────────────────────────────────

    def _rebuild_ui(self):
        self.clear_items()

        # ── Row 0: main action buttons ─────────────────
        desc_btn = ui.Button(
            label = "📝 Description",
            style = discord.ButtonStyle.primary,
            row   = 0,
        )
        desc_btn.callback = self._set_description
        self.add_item(desc_btn)

        img_btn = ui.Button(
            label = "🖼️ Image",
            style = discord.ButtonStyle.primary,
            row   = 0,
        )
        img_btn.callback = self._set_image
        self.add_item(img_btn)

        shiny_img_btn = ui.Button(
            label = "💠 Shiny Image",
            style = discord.ButtonStyle.primary,
            row   = 0,
        )
        shiny_img_btn.callback = self._set_shiny_image
        self.add_item(shiny_img_btn)

        type_btn = ui.Button(
            label = "🏷️ Type",
            style = discord.ButtonStyle.primary,
            row   = 0,
        )
        type_btn.callback = self._set_type
        self.add_item(type_btn)

        preview_btn = ui.Button(
            label = "👁️ Preview",
            style = discord.ButtonStyle.success,
            row   = 0,
        )
        preview_btn.callback = self._show_preview
        self.add_item(preview_btn)

        # ── Row 1: More options dropdown ───────────────
        more_select = ui.Select(
            placeholder = "More World Options...",
            row         = 1,
            options     = [
                discord.SelectOption(
                    label       = "Make Stats",
                    value       = "stats",
                    description = "Coming soon!",
                    emoji       = "📊",
                ),
                discord.SelectOption(
                    label       = "Add Quote",
                    value       = "quote",
                    description = "Add a memorable quote for this world card",
                    emoji       = "💬",
                ),
                discord.SelectOption(
                    label       = "Lore",
                    value       = "lore",
                    description = "Write the lore / history for this world element",
                    emoji       = "📖",
                ),
                discord.SelectOption(
                    label       = "Add Theme Song",
                    value       = "theme",
                    description = "Link a theme song for this world card",
                    emoji       = "🎵",
                ),
            ],
        )
        more_select.callback = self._more_options
        self.add_item(more_select)

        # ── Row 2: navigation + return ─────────────────
        prev_btn = ui.Button(
            emoji    = "⬅️",
            style    = discord.ButtonStyle.secondary,
            row      = 2,
            disabled = (self.index == 0),
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        ret_btn = ui.Button(label="↩️ Return", style=discord.ButtonStyle.success, row=2)
        ret_btn.callback = self._return
        self.add_item(ret_btn)

        next_btn = ui.Button(
            emoji    = "➡️",
            style    = discord.ButtonStyle.secondary,
            row      = 2,
            disabled = (self.index >= len(self.worlds) - 1),
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

    # ── Button callbacks ─────────────────────────────

    async def _prev(self, interaction: discord.Interaction):
        self.index -= 1
        self._reload_current()
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.index += 1
        self._reload_current()
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _show_preview(self, interaction: discord.Interaction):
        preview = _WorldPreviewView(self, shiny=False)
        await interaction.response.edit_message(
            embed=preview.build_preview_embed(),
            view=preview,
        )

    async def _set_description(self, interaction: discord.Interaction):
        world   = self.current_world()
        current = world.get("description") or ""
        modal   = _WorldTextModal(
            title       = "Set Description",
            label       = "About this world element",
            field_key   = "description",
            placeholder = "Describe this location, artifact, concept, etc.",
            detail_view = self,
            current     = current,
            max_length  = 1000,
        )
        self._modal_open = True
        await interaction.response.send_modal(modal)

    async def _set_type(self, interaction: discord.Interaction):
        modal = _WorldTypeModal(self)
        self._modal_open = True
        await interaction.response.send_modal(modal)

    async def _set_image(self, interaction: discord.Interaction):
        from features.world.service import update_world_details
        world      = self.current_world()
        world_name = world.get("name", "this world card")

        async def save_image(url: str):
            update_world_details(world["id"], image_url=url)
            self._reload_current()
            self._rebuild_ui()
            await self._safe_edit(embed=self.build_embed(), view=self)

        await self.handle_image_upload(
            interaction,
            save_image,
            pad_ratio     = 4 / 3,
            prompt_prefix = (
                f"🖼️ **World Card Image — {world_name}**\n\n"
                "Upload the art or illustration for this world card.\n"
                "This will appear as the main card image.\n\n"
            ),
            confirmation_message = (
                f"🌍 **Card image saved for {world_name}!** 🎉"
            ),
        )

    async def _set_shiny_image(self, interaction: discord.Interaction):
        from features.world.service import update_world_details
        world      = self.current_world()
        world_name = world.get("name", "this world card")

        async def save_shiny(url: str):
            update_world_details(world["id"], shiny_image_url=url)
            self._reload_current()
            self._rebuild_ui()
            await self._safe_edit(embed=self.build_embed(), view=self)

        await self.handle_image_upload(
            interaction,
            save_shiny,
            pad_ratio     = 4 / 3,
            prompt_prefix = (
                "✨ **World Card Shiny Art**\n\n"
                f"Upload a special shiny version of **{world_name}**'s card art.\n"
                "This appears when someone collects the ✨ shiny version.\n\n"
            ),
            confirmation_message = (
                f"💠 **Shiny card art saved for {world_name}!** 🎉"
            ),
        )

    async def _more_options(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]

        if value == "stats":
            await interaction.response.send_message(
                "📊 **Make Stats** is coming soon! Check back in a future update.",
                ephemeral=True, delete_after=6,
            )
            return

        if value == "quote":
            world   = self.current_world()
            current = world.get("quote") or ""
            modal   = _WorldTextModal(
                title       = "Add Quote",
                label       = "A memorable quote",
                field_key   = "quote",
                placeholder = "\"Enter a quote associated with this world element...\"",
                detail_view = self,
                current     = current,
                max_length  = 200,
            )
            self._modal_open = True
            await interaction.response.send_modal(modal)
            return

        if value == "lore":
            world   = self.current_world()
            current = world.get("lore") or ""
            modal   = _WorldTextModal(
                title       = "Add Lore",
                label       = "History & lore",
                field_key   = "lore",
                placeholder = "Write the history, mythology, or backstory for this world element...",
                detail_view = self,
                current     = current,
                max_length  = 1000,
            )
            self._modal_open = True
            await interaction.response.send_modal(modal)
            return

        if value == "theme":
            world   = self.current_world()
            current = world.get("music_url") or ""
            modal   = _WorldTextModal(
                title       = "Add Theme Song",
                label       = "Theme song URL",
                field_key   = "music_url",
                placeholder = "Paste a YouTube, Spotify, or SoundCloud URL...",
                detail_view = self,
                current     = current,
                max_length  = 500,
            )
            self._modal_open = True
            await interaction.response.send_modal(modal)
            return

    async def _return(self, interaction: discord.Interaction):
        total_pages = max(1, (len(self.worlds) + PAGE_SIZE - 1) // PAGE_SIZE)
        roster = WorldBuildRosterView(self.worlds, self.user, start_page=self.return_page)
        roster.builder_message = self.builder_message
        await roster.attach_message(self.builder_message)
        await interaction.response.edit_message(
            embed=build_world_roster_embed(
                self.worlds, self.return_page, total_pages, self.user.display_name,
                viewer_discord_id=str(self.user.id),
            ),
            view=roster,
        )


# ─────────────────────────────────────────────────
# Roster browse view
# ─────────────────────────────────────────────────

class WorldBuildRosterView(TimeoutMixin, ui.View):
    """Paginated list of world cards with completion indicators."""

    def __init__(self, worlds: list, viewer: discord.Member, start_page: int = 0):
        super().__init__(timeout=300)
        self.worlds  = worlds
        self.viewer  = viewer
        self.page    = start_page
        self.builder_message = None
        self._rebuild_ui()

    def total_pages(self) -> int:
        return max(1, (len(self.worlds) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _page_worlds(self) -> list:
        start = self.page * PAGE_SIZE
        return self.worlds[start : start + PAGE_SIZE]

    async def attach_message(self, message):
        self.builder_message = message

    def _rebuild_ui(self):
        self.clear_items()
        page_worlds = self._page_worlds()

        # Row 0: number buttons
        for i in range(len(page_worlds)):
            btn = ui.Button(emoji=NUMBER_EMOJIS[i], style=discord.ButtonStyle.primary, row=0)
            btn.callback = self._make_open_cb(i)
            self.add_item(btn)

        # Row 1: ← Page X/Y →
        prev_btn = ui.Button(
            emoji    = "⬅️",
            style    = discord.ButtonStyle.secondary,
            row      = 1,
            disabled = (self.page == 0),
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        jump_btn = ui.Button(
            label    = f"Page {self.page + 1}/{self.total_pages()}",
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
            if global_index >= len(self.worlds):
                await interaction.response.send_message("World card not found.", ephemeral=True)
                return
            detail = WorldBuildView(
                self.worlds, global_index, self.viewer,
                return_page=self.page,
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
            embed=build_world_roster_embed(
                self.worlds, self.page, self.total_pages(), self.viewer.display_name,
                viewer_discord_id=str(self.viewer.id),
            ),
            view=self,
        )

    async def _next(self, interaction: discord.Interaction):
        self.page = min(self.total_pages() - 1, self.page + 1)
        self._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_world_roster_embed(
                self.worlds, self.page, self.total_pages(), self.viewer.display_name,
                viewer_discord_id=str(self.viewer.id),
            ),
            view=self,
        )

    async def _jump(self, interaction: discord.Interaction):
        await interaction.response.send_modal(_WorldJumpModal(self))
