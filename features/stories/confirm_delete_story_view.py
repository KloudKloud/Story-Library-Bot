import discord
from discord import ui

from database import delete_story


class ConfirmDeleteStoryView(ui.View):

    def __init__(self, story_id, story_title, viewer=None):
        super().__init__(timeout=60)

        self.story_id = story_id
        self.story_title = story_title
        self.viewer = viewer

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.viewer and interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    @ui.button(label="✔️ Yes, Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button):

        delete_story(self.story_id)

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content=f"🗑️ **{self.story_title}** removed from the library.",
            view=self
        )

    @ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button):

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content="Removal cancelled.",
            view=self
        )