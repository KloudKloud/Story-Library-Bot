import discord
from discord import ui
from database import update_profile


class EditBioModal(ui.Modal, title="Edit Author Bio"):

    bio = ui.TextInput(
        label="Author Bio",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=False
    )

    def __init__(self, builder_view):
        super().__init__()
        self.builder_view = builder_view

    async def on_submit(self, interaction: discord.Interaction):

        update_profile(
            interaction.user.id,
            bio=str(self.bio)
        )

        await self.builder_view.refresh()

        await interaction.response.defer()