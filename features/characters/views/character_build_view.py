import discord
from discord import ui
import asyncio
import io

from database import get_character_by_id
from features.characters.service import update_character_details   # adjust import if needed
from embeds.character_embeds import build_character_card
from embeds.character_embeds import build_character_card, unpack_character
from ui.base_builder_view import BaseBuilderView

STORAGE_CHANNEL_ID = 1478560442723864737  # <-- replace with your real channel ID


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

        kwargs = {self.field_name: self.input.value}

        update_character_details(
            self.parent_view.character_id,
            **kwargs
        )

        # refresh character from DB
        self.parent_view.reload_character()

        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )


class CharacterPreviewView(ui.View):

    def __init__(self, parent_view):
        super().__init__(timeout=300)
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

    def __init__(self, character, user):

        super().__init__(user)

        self.waiting_for_image = False
        self.image_task = None
        self.character = character
        self.character_id = character["id"]

        self.misc_select = self.MiscSelect(self)
        self.misc_select.row = 1
        self.add_item(self.misc_select)

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

        embed.add_field(
            name="📖 Bio / Personality",
            value=(
                "Core personality, behavior, and vibe.\n"
                f"**Current:** *{self.preview_text(char['personality'], 140) or 'Not written yet'}*"
            ),
            inline=False
        )

        embed.add_field(
            name="📜 Lore",
            value=(
                "Backstory, history, secrets, world role.\n"
                f"**Current:** *{self.preview_text(char['lore'], 140) or 'Not written yet'}*"
            ),
            inline=False
        )

        embed.add_field(
            name="🧬 Physical Features",
            value=(
                "Scars, size differences, fluffiness, build, colors, etc.\n"
                f"**Current:** *{self.preview_text(char['physical_features'], 140) or 'Not written yet'}*"
            ),
            inline=False
        )

        embed.add_field(
            name="🎨 Image",
            value=(
                "**Current:** Set" if char['image_url'] else
                "🖼 *No character art yet? No worries! This bot is for fun, so find a picture online and paste it in `/char build`~*\n"
                "**Current:** *Not set*"
            ),
            inline=False
        )

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