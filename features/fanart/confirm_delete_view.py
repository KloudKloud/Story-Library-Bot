import discord
from discord import ui
from ui import TimeoutMixin

class ConfirmDeleteFanartView(TimeoutMixin, ui.View):

    def __init__(self, editor_view):

        super().__init__(timeout=30)

        self.editor_view = editor_view
        self.viewer = editor_view.viewer

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    @ui.button(label="Delete Fanart", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):

        from database import delete_fanart

        delete_fanart(self.editor_view.fanart["id"])

        await interaction.response.edit_message(
            content="🗑 Fanart deleted.",
            view=None
        )

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):

        await interaction.response.edit_message(
            content="Deletion cancelled.",
            view=None
        )