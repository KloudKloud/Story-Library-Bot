import discord
from discord import ui
import asyncio

from features.characters.service import delete_character


class ConfirmDeleteCharacterView(ui.View):

    def __init__(self, character_id, character_name, story_name):
        super().__init__(timeout=60)

        self.character_id = character_id
        self.character_name = character_name
        self.story_name = story_name

    # ---------------------------
    # CONFIRM
    # ---------------------------
    @ui.button(label="🗑 Yes, Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):

        from database import get_card_collectors, get_user_id
        collectors = get_card_collectors(self.character_id)

        delete_character(self.character_id)

        respin_note = ""
        if collectors:
            respin_note = (
                f"\n-# 💎 **{len(collectors)}** collector(s) had this card "
                f"and each received a free respin token."
            )

        await interaction.response.edit_message(
            content=(
                f"🗑 Removed **{self.character_name}** "
                f"from **{self.story_name}**."
                f"{respin_note}"
            ),
            embed=None,
            view=None
        )

        # Auto delete after 3 seconds
        await asyncio.sleep(3)

        try:
            await interaction.delete_original_response()
        except:
            pass

    # ---------------------------
    # CANCEL
    # ---------------------------
    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):

        await interaction.response.edit_message(
            content="Deletion cancelled.",
            embed=None,
            view=None
        )