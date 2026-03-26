import discord
from discord import ui
import asyncio
import io

from database import get_character_by_id
from features.characters.service import update_character_details
from embeds.character_embeds import build_character_card, unpack_character
from ui.base_builder_view import BaseBuilderView
from ui import TimeoutMixin

STORAGE_CHANNEL_ID = 1478560442723864737

PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
_SPARKS       = ["✨", "🌸", "⭐", "💎", "🌺", "🔮", "💫"]
_DIVIDER      = "✦ ˖ ⋆ ˚ · ✧ · ˚ ⋆ ˖ ✦ ˖ ⋆ ˚ · ✧ · ˚ ⋆ ˖ ✦"
_ENTRY_SEP    = "-# ˖ · · ⋆ · · ˖ · · ✦ · · ˖ · · ⋆ · · ˖"

# Fields used for completion checking in the roster
_ALL_FIELDS    = ["gender", "personality", "image_url", "quote", "lore",
                  "age", "height", "physical_features", "relationships",
                  "species", "music_url"]
_DETAIL_FIELDS = ["gender", "quote", "age", "height", "physical_features",
                  "relationships", "species", "music_url"]


def _char_roster_stats(c: dict):
    """Returns (has_img, has_bio, has_lore, detail_filled, detail_total, is_complete)."""
    def filled(f):
        v = c.get(f)
        return bool(v and str(v).strip())

    has_img  = filled("image_url")
    has_bio  = filled("personality")
    has_lore = filled("lore")
    detail_filled = sum(1 for f in _DETAIL_FIELDS if filled(f))
    detail_total  = len(_DETAIL_FIELDS)
    total_filled  = sum(1 for f in _ALL_FIELDS if filled(f))
    is_complete   = total_filled == len(_ALL_FIELDS)
    return has_img, has_bio, has_lore, detail_filled, detail_total, is_complete


# ─────────────────────────────────────────────────
# Roster helpers
# ─────────────────────────────────────────────────

def build_char_roster_embed(chars: list, page: int, total_pages: int,
                             viewer_name: str,
                             banner_url: str = None) -> discord.Embed:
    start      = page * PAGE_SIZE
    page_chars = chars[start:start + PAGE_SIZE]
    spark      = _SPARKS[page % len(_SPARKS)]
    embed = discord.Embed(
        title       = f"✨  {viewer_name}'s Character Builder  ✨",
        description = "",
        color       = discord.Color.from_rgb(148, 87, 235),
    )
    if banner_url:
        embed.set_thumbnail(url=banner_url)

    lines = [f"-# {_DIVIDER}"]
    for i, c in enumerate(page_chars):
        has_img, has_bio, has_lore, det_fill, det_total, is_complete = _char_roster_stats(dict(c))
        story = c.get("story_title") or "Unknown Story"

        if is_complete:
            name_line = f"{NUMBER_EMOJIS[i]}  🌟 **{c['name']}** 🌟"
            status    = "⭐ **Fully Complete!**"
        else:
            name_line = f"{NUMBER_EMOJIS[i]}  **{c['name']}**"
            img_mark  = "✅" if has_img  else "❌"
            bio_mark  = "✅" if has_bio  else "❌"
            lore_mark = "✅" if has_lore else "❌"
            status    = f"🖼️ {img_mark}  📝 {bio_mark}  📖 {lore_mark}  ⚙️ {det_fill}/{det_total}"

        lines.append(
            f"{name_line}\n"
            f"-# 📚 {story}\n"
            f"-# {status}"
        )
        if i < len(page_chars) - 1:
            lines.append(_ENTRY_SEP)
    lines.append(f"-# {_DIVIDER}")
    embed.description = "\n".join(lines)
    embed.set_footer(
        text=f"Page {page + 1} of {total_pages}  ·  "
             f"{len(chars)} character{'s' if len(chars) != 1 else ''} total"
    )
    return embed


class _CharBuildJumpModal(discord.ui.Modal, title="Jump to Page"):
    page_num = discord.ui.TextInput(
        label="Page number", placeholder="e.g. 2", max_length=4, required=True
    )

    def __init__(self, roster_view: "CharBuildRosterView"):
        super().__init__()
        self.roster_view = roster_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            num = int(self.page_num.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid page number.", ephemeral=True, delete_after=4)
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
            embed=build_char_roster_embed(
                self.roster_view.chars, self.roster_view.page,
                total, self.roster_view.viewer.display_name,
                banner_url=self.roster_view.banner_url,
            ),
            view=self.roster_view,
        )


class CharBuildRosterView(TimeoutMixin, ui.View):
    """5-per-page browse of all your characters for the builder."""

    def __init__(self, chars: list, viewer: discord.Member,
                 start_page: int = 0, banner_url: str = None):
        super().__init__(timeout=300)
        self.chars      = chars
        self.viewer     = viewer
        self.page       = start_page
        self.banner_url = banner_url
        self.builder_message = None
        self._rebuild_ui()

    def total_pages(self) -> int:
        return max(1, (len(self.chars) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _page_chars(self) -> list:
        start = self.page * PAGE_SIZE
        return self.chars[start:start + PAGE_SIZE]

    def build_embed(self) -> discord.Embed:
        return build_char_roster_embed(
            self.chars, self.page, self.total_pages(), self.viewer.display_name,
            banner_url=self.banner_url,
        )

    def _rebuild_ui(self):
        self.clear_items()
        page_chars = self._page_chars()

        for i in range(len(page_chars)):
            btn = ui.Button(emoji=NUMBER_EMOJIS[i], style=discord.ButtonStyle.primary, row=0)
            btn.callback = self._make_open_cb(i)
            self.add_item(btn)

        prev_btn = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary, row=1,
            disabled=(self.page == 0),
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        jump_btn = ui.Button(
            label=f"Pg. {self.page + 1}/{self.total_pages()}",
            style=discord.ButtonStyle.success, row=1,
            disabled=(self.total_pages() == 1),
        )
        jump_btn.callback = self._jump
        self.add_item(jump_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary, row=1,
            disabled=(self.page >= self.total_pages() - 1),
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

    def _make_open_cb(self, slot_index: int):
        async def callback(interaction: discord.Interaction):
            global_index = self.page * PAGE_SIZE + slot_index
            if global_index >= len(self.chars):
                await interaction.response.send_message("Character not found.", ephemeral=True)
                return
            char_data = dict(self.chars[global_index])
            fresh = get_character_by_id(char_data["id"])
            if fresh:
                merged = dict(fresh)
                for k in ("story_title", "story_id"):
                    if not merged.get(k) and char_data.get(k):
                        merged[k] = char_data[k]
                char_data = merged
            view = CharacterBuildView(
                char_data, self.viewer,
                chars=self.chars, index=global_index, return_page=self.page,
            )
            view.builder_message = self.builder_message
            await interaction.response.edit_message(embed=view.build_embed(), view=view)
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
        await interaction.response.send_modal(_CharBuildJumpModal(self))


# =====================================================
# MODALS
# =====================================================

class SimpleTextModal(ui.Modal):

    def __init__(self, title, label, field_name, parent_view, default=None):
        super().__init__(title=title)

        self.field_name = field_name
        self.parent_view = parent_view
        if hasattr(parent_view, '_modal_open'):
            parent_view._modal_open = True

        self.input = ui.TextInput(
            label=label,
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000,
            default=default[:1000] if default else None,
        )

        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):

        if hasattr(self.parent_view, '_modal_open'):
            self.parent_view._modal_open = False

        from utils.text_utils import fix_emoji_spacing
        kwargs = {self.field_name: fix_emoji_spacing(self.input.value)}

        update_character_details(
            self.parent_view.character_id,
            **kwargs
        )

        # refresh character from DB
        self.parent_view.reload_character()

        try:
            await interaction.response.edit_message(
                embed=self.parent_view.build_embed(),
                view=self.parent_view
            )
        except discord.NotFound:
            # The builder message was dismissed (e.g. on mobile) while the
            # modal was open.  The field was saved — just let them know.
            await interaction.response.send_message(
                "✅ Saved! Your changes were recorded, but the builder window was "
                "closed while you were typing. Run `/char build` again to continue.",
                ephemeral=True
            )


class CharacterPreviewView(ui.View):

    def __init__(self, parent_view):
        super().__init__(timeout=1200)
        self.parent_view = parent_view
        self.viewer = parent_view.user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    @ui.button(label="⬅️ Back to Editor", style=discord.ButtonStyle.success)
    async def back_to_editor(self, interaction: discord.Interaction, button):

        # reload character to ensure latest data
        self.parent_view.reload_character()

        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )
# =====================================================
# CHARACTER BUILD HUB
# =====================================================

class CharacterBuildView(BaseBuilderView):

    def __init__(self, character, user, chars=None, index=0, return_page=0):

        super().__init__(user)

        self.waiting_for_image = False
        self.image_task = None
        self.character    = character
        self.character_id = character["id"]
        self._chars       = chars
        self._index       = index
        self._return_page = return_page

        self.misc_select = self.MiscSelect(self)
        self.misc_select.row = 1
        self.add_item(self.misc_select)

        if chars is not None:
            self._add_nav_buttons()

    BUILD_FIELDS = {
        "gender": 3,
        "personality": 4,
        "image_url": 5,
        "quote": 6,
        "lore": 7,
        "age": 8,
        "height": 9,
        "physical_features": 10,
        "relationships": 11,
        "species": 12,
        "music_url": 13,
    }

    # -------------------------------------------------
    # CORE
    # -------------------------------------------------

    def reload_character(self):
        fresh = get_character_by_id(self.character_id)
        if fresh:
            self.character = fresh

    def build_embed(self):

        char = unpack_character(self.character)

        filled, total, percent = self.get_completion_stats()

        embed = build_character_card(
            self.character,
            story_title=None,
            builder_mode=True
        )

        embed.title = f"🛠 {char['name']} • {percent}% Complete"

        DIV = "✦ ·  · ✧ · ────────── · ✧ ·  · ✦"

        # -------------------------------------------------
        # PROGRESS BAR
        # -------------------------------------------------

        bar = self.build_progress_bar(percent)

        embed.add_field(
            name="✨ Character Progress",
            value=(
                f"{bar}\n"
                f"**{filled}/{total} sections completed**"
            ),
            inline=False
        )

        # -------------------------------------------------
        # CORE CHARACTER WRITING
        # -------------------------------------------------

        embed.add_field(name="\u200b", value=DIV, inline=False)

        embed.add_field(
            name="📖 Bio / Personality",
            value=(
                "Core personality, behavior, and vibe.\n"
                f"**Current:** *{self.preview_text(char['personality'], 140) or 'Not written yet'}*"
            ),
            inline=False
        )

        embed.add_field(name="\u200b", value=DIV, inline=False)

        embed.add_field(
            name="📜 Lore",
            value=(
                "Backstory, history, secrets, world role.\n"
                f"**Current:** *{self.preview_text(char['lore'], 140) or 'Not written yet'}*"
            ),
            inline=False
        )

        embed.add_field(name="\u200b", value=DIV, inline=False)

        embed.add_field(
            name="🧬 Physical Features",
            value=(
                "Scars, size differences, fluffiness, build, colors, etc.\n"
                f"**Current:** *{self.preview_text(char['physical_features'], 140) or 'Not written yet'}*"
            ),
            inline=False
        )

        embed.add_field(name="\u200b", value=DIV, inline=False)

        embed.add_field(
            name="🎨 Image",
            value=(
                "**Current:** Set" if char['image_url'] else
                "🖼 *No character art yet? No worries! This bot is for fun, so find a picture online and paste it in `/char build`~*\n"
                "**Current:** *Not set*"
            ),
            inline=False
        )

        embed.add_field(name="\u200b", value=DIV, inline=False)

        # ── CTC Shiny Card Art ────────────────────────────────────────────────
        shiny_img = char.get("shiny_image_url")
        embed.add_field(
            name="💠 CTC Shiny Card Art" + ("  ✔" if shiny_img else "  ✦"),
            value=(
                "✔ You have set a CTC Shiny Card Image." if shiny_img else
                "The **CTC card game** lets readers collect character cards! "
                "2% of spins land a rare ✨ Shiny version! "
                "If you upload a special image here, it will display *instead* of "
                "your normal card art whenever someone views the shiny version of "
                f"**{char['name']}** in their collection.\n"
                "-# *Optional — your normal art is used by default.*"
            ),
            inline=False
        )

        # -------------------------------------------------
        # CHARACTER DETAILS
        # -------------------------------------------------

        embed.add_field(name="\u200b", value=DIV, inline=False)

        embed.add_field(
            name="⚙️ Character Details",
            value=(
                f"{'✔' if char['quote'] else '✦'} Quote\n"
                f"{'✔' if char['gender'] else '✦'} Gender\n"
                f"{'✔' if char['age'] else '✦'} Age\n"
                f"{'✔' if char['height'] else '✦'} Height\n"
                f"{'✔' if char.get('species') else '✦'} Species\n"
                f"{'✔' if char.get('music_url') else '✦'} Theme Song\n"
                f"{'✔' if char['relationships'] else '✦'} Relationships"
            ),
            inline=False
        )

        # -------------------------------------------------
        # FOOTER
        # -------------------------------------------------

        # Thumbnail: character art (small top-right preview)
        if char.get("image_url"):
            embed.set_thumbnail(url=char["image_url"])

        embed.set_footer(
            text="✨ Use the buttons below to build and customize your character"
        )

        return embed

    def get_completion_stats(self):

        char = unpack_character(self.character)

        filled = 0
        total = len(self.BUILD_FIELDS)

        for field in self.BUILD_FIELDS.keys():

            value = char.get(field)

            if value and str(value).strip():
                filled += 1

        percent = int((filled / total) * 100)

        return filled, total, percent

    # -------------------------------------------------
    # ROW 2 NAV (browse mode only)
    # -------------------------------------------------

    def _add_nav_buttons(self):
        prev_btn = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary, row=2,
            disabled=(self._index == 0),
        )
        prev_btn.callback = self._nav_prev
        self.add_item(prev_btn)

        ret_btn = ui.Button(label="↩️ Return", style=discord.ButtonStyle.success, row=2)
        ret_btn.callback = self._nav_return
        self.add_item(ret_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary, row=2,
            disabled=(self._index >= len(self._chars) - 1),
        )
        next_btn.callback = self._nav_next
        self.add_item(next_btn)

    async def _nav_prev(self, interaction: discord.Interaction):
        self._index -= 1
        char_data = dict(self._chars[self._index])
        fresh = get_character_by_id(char_data["id"])
        if fresh:
            merged = dict(fresh)
            for k in ("story_title", "story_id"):
                if not merged.get(k) and char_data.get(k):
                    merged[k] = char_data[k]
            char_data = merged
        new_view = CharacterBuildView(char_data, self.user, chars=self._chars, index=self._index, return_page=self._return_page)
        new_view.builder_message = self.builder_message
        await interaction.response.edit_message(embed=new_view.build_embed(), view=new_view)

    async def _nav_next(self, interaction: discord.Interaction):
        self._index += 1
        char_data = dict(self._chars[self._index])
        fresh = get_character_by_id(char_data["id"])
        if fresh:
            merged = dict(fresh)
            for k in ("story_title", "story_id"):
                if not merged.get(k) and char_data.get(k):
                    merged[k] = char_data[k]
            char_data = merged
        new_view = CharacterBuildView(char_data, self.user, chars=self._chars, index=self._index, return_page=self._return_page)
        new_view.builder_message = self.builder_message
        await interaction.response.edit_message(embed=new_view.build_embed(), view=new_view)

    async def _nav_return(self, interaction: discord.Interaction):
        roster = CharBuildRosterView(self._chars, self.user, start_page=self._return_page)
        roster.builder_message = self.builder_message
        await interaction.response.edit_message(embed=roster.build_embed(), view=roster)

    # -------------------------------------------------
    # BUTTONS (ROW 0)
    # -------------------------------------------------

    @ui.button(label="📝 Bio", style=discord.ButtonStyle.primary, row=0)
    async def add_bio(self, interaction: discord.Interaction, button: ui.Button):
        char = unpack_character(self.character)
        current = char["personality"]
        await interaction.response.send_modal(
            SimpleTextModal(
                "Edit Personality / Bio" if current else "Add Personality / Bio",
                "Personality / Bio",
                "personality",
                self,
                default=current,
            )
        )

    @ui.button(label="🎨 Image", style=discord.ButtonStyle.primary, row=0)
    async def add_image(self, interaction: discord.Interaction, button: ui.Button):

        async def save_image(url):

            update_character_details(
                self.character_id,
                image_url=url
            )

            self.reload_character()
            await self._safe_edit(embed=self.build_embed(), view=self)

        await self.handle_image_upload(
            interaction,
            save_image,
            pad_ratio=4/3,
            prompt_prefix=(
                "🖼 **It is highly encouraged that you add a picture for every character! This will directly effect the /ctc collections view!\n"
                "Don't have a reference for your character yet? No problem! This bot is for fun, so find one online temporarily and replace later if you'd like!**\n\n"
            )
        )


    @ui.button(label="📚 Lore", style=discord.ButtonStyle.primary, row=0)
    async def add_lore(self, interaction: discord.Interaction, button: ui.Button):
        char = unpack_character(self.character)
        current = char["lore"]
        await interaction.response.send_modal(
            SimpleTextModal(
                "Edit Lore" if current else "Add Lore",
                "Lore / Backstory",
                "lore",
                self,
                default=current,
            )
        )

    @ui.button(label="💬 Add Quote", style=discord.ButtonStyle.primary, row=0)
    async def add_quote(self, interaction: discord.Interaction, button: ui.Button):
        char = unpack_character(self.character)
        current = char["quote"]
        await interaction.response.send_modal(
            SimpleTextModal(
                "Edit Quote" if current else "Add Quote",
                "Character Quote",
                "quote",
                self,
                default=current,
            )
        )


    @ui.button(label="👁 Preview", style=discord.ButtonStyle.success, row=0)
    async def preview(self, interaction, button):

        preview_view = CharacterPreviewView(self)

        await interaction.response.edit_message(
            embed=build_character_card(self.character),
            view=preview_view
        )

    # -------------------------------------------------
    # DROPDOWN
    # -------------------------------------------------

    class MiscSelect(ui.Select):

        def __init__(self, view_ref):

            self.view_ref = view_ref

            options = [
                discord.SelectOption(label="🧬 Physical Features", value="physical_features"),
                discord.SelectOption(label="✨ Set Gender", value="gender"),
                discord.SelectOption(label="🎂 Add Age", value="age"),
                discord.SelectOption(label="📏 Add Height", value="height"),
                discord.SelectOption(label="🐾 Set Species", value="species"),
                discord.SelectOption(label="🎵 Add Theme Song", value="music_url"),
                discord.SelectOption(label="💞 Relationships", value="relationships"),
                discord.SelectOption(label="💠 CTC Shiny Card Art", value="shiny_image_url",
                                     description="Upload a special image for the shiny CTC card version"),
                discord.SelectOption(label="🗑 Remove Character", value="delete"),
            ]

            super().__init__(
                placeholder="⚙️ More Character Options...",
                options=options
            )

        async def callback(self, interaction: discord.Interaction):

            choice = self.values[0]

            if choice == "delete":

                from features.characters.views.confirm_delete_view import ConfirmDeleteCharacterView

                char = unpack_character(self.view_ref.character)
                character_name = char["name"]

                view = ConfirmDeleteCharacterView(
                    self.view_ref.character_id,
                    character_name,
                    None  # story name optional here
                )

                await interaction.response.send_message(
                    f"⚠️ Are you sure you want to remove **{character_name}**?",
                    view=view,
                    ephemeral=True
                )

                return

            if choice == "shiny_image_url":
                char = unpack_character(self.view_ref.character)

                async def save_shiny_image(url):
                    update_character_details(
                        self.view_ref.character_id,
                        shiny_image_url=url,
                    )
                    self.view_ref.reload_character()
                    await self.view_ref._safe_edit(
                        embed=self.view_ref.build_embed(),
                        view=self.view_ref,
                    )

                await self.view_ref.handle_image_upload(
                    interaction,
                    save_shiny_image,
                    pad_ratio=4/3,
                    prompt_prefix=(
                        "✨ **CTC Shiny Card Art**\n\n"
                        "Upload a special image to display when readers view the **shiny ✨ version** "
                        f"of **{char['name']}**'s CTC card.\n"
                        "This is optional — if you skip it, the normal card art will be used for shiny cards too.\n\n"
                        "*Tip: something that feels sparkly, golden, or alternate-palette works great!*\n\n"
                    ),
                    confirmation_message=(
                        f"💠 **Shiny card art saved for {char['name']}!**\n"
                        "Whenever someone spins or collects a ✨ shiny version of your character in the CTC game, "
                        "they'll see this special alt art instead of the normal card image. Congrats! 🎉"
                    ),
                )
                return

            char = unpack_character(self.view_ref.character)
            current_value = char.get(choice)

            # Friendly display labels
            labels = {
                "gender": "Gender",
                "age": "Age",
                "height": "Height",
                "physical_features": "Physical Features",
                "relationships": "Relationships",
                "species": "Species",
                "music_url": "Theme Song URL",
            }

            field_label = labels.get(choice, choice.replace("_", " ").title())

            await interaction.response.send_modal(
                SimpleTextModal(
                    f"Edit {field_label}" if current_value else f"Add {field_label}",
                    field_label,
                    choice,
                    self.view_ref,
                    default=str(current_value) if current_value else None,
                )
            )