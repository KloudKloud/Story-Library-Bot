import discord
from discord import ui
from ui import TimeoutMixin


class FanartStoryTestView(TimeoutMixin, ui.View):

    def __init__(self, parent_view):
        super().__init__(timeout=300)
        self.parent_view = parent_view
        self.viewer = parent_view.viewer

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

    def build_embed(self):

        embed = discord.Embed(
            title="Hi",
            description="Fanart → Story path is working.",
            color=discord.Color.blurple()
        )

        return embed

    @ui.button(label="🎬 See Extras", style=discord.ButtonStyle.success)
    async def extras(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.send_message(
            "Extras will exist later.",
            ephemeral=True
        )

    @ui.button(label="🎨 Return to Fanart", style=discord.ButtonStyle.primary)
    async def back(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )