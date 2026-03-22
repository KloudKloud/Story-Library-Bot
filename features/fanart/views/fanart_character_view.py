import discord
from discord import ui

from embeds.character_embeds import build_character_card
from database import (
    get_character_by_id,
    get_user_id,
    is_favorite_character,
    get_favorite_characters,
    add_favorite_character,
    remove_favorite_character,
    get_story_by_character
)
from features.characters.views.characters_view import FavoriteMixin


class FanartCharacterView(FavoriteMixin, ui.View):
    """
    /fanartview → Characters

    Row 0: ⬅️ | ✦ Favorite | 📜 Lore | Return 🎨 | ➡️
    """

    def __init__(self, characters, parent_view, viewer=None):

        ui.View.__init__(self, timeout=300)

        self.characters  = characters
        self.parent_view = parent_view
        self.viewer      = viewer
        self.index       = 0

        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.viewer and interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    # =========================
    # CURRENT CHARACTER
    # =========================

    def current_character(self):
        char_id = self.characters[self.index]["id"]
        fresh = get_character_by_id(char_id)
        if fresh:
            self.characters[self.index] = fresh
        return self.characters[self.index]

    def rebuild_character(self):
        self.current_character()  # already refreshes in place

    # =========================
    # BUILD EMBED
    # =========================

    def build_embed(self):
        char = self.current_character()
        self.update_buttons()
        return build_character_card(
            char,
            viewer=self.viewer,
            index=self.index + 1,
            total=len(self.characters)
        )

    # =========================
    # BUTTON STATE
    # =========================

    def update_buttons(self):
        char = self.characters[self.index]  # use cached, not re-fetch

        self.left.disabled  = self.index == 0
        self.right.disabled = self.index >= len(self.characters) - 1

        lore = char.get("lore")
        self.lore.disabled = not bool(lore)

        self._sync_fav_button(self.fav_btn, char)

    # =========================
    # BUTTONS
    # =========================

    @ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary, row=0)
    async def left(self, interaction, button):
        if self.index > 0:
            self.index -= 1
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @ui.button(label="✦ Favorite", style=discord.ButtonStyle.primary, row=0)
    async def fav_btn(self, interaction, button):
        await self._handle_mark_fav(interaction, self.current_character(), self)

    @ui.button(label="📜 Lore", style=discord.ButtonStyle.primary, row=0)
    async def lore(self, interaction, button):
        char = self.current_character()
        lore = char.get("lore")

        if not lore:
            await interaction.response.send_message(
                "No lore written yet.",
                ephemeral=True,
                delete_after=4
            )
            return

        embed = discord.Embed(
            title=f"📜 {char['name']} — Lore",
            description=lore,
            color=discord.Color.dark_purple()
        )
        embed.set_footer(text="⚠️ May contain spoilers")
        await interaction.response.send_message(embed=embed, ephemeral=True, delete_after=30)

    @ui.button(label="Return 🎨", style=discord.ButtonStyle.success, row=0)
    async def back(self, interaction, button):
        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )

    @ui.button(emoji="➡️", style=discord.ButtonStyle.secondary, row=0)
    async def right(self, interaction, button):
        if self.index < len(self.characters) - 1:
            self.index += 1
        await interaction.response.edit_message(embed=self.build_embed(), view=self)