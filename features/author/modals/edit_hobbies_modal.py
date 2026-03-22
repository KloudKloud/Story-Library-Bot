import discord
from discord import ui
from database import update_profile


class EditHobbiesModal(ui.Modal, title="Hobbies"):

    hobbies = ui.TextInput(
        label="Hobbies",
        style=discord.TextStyle.paragraph,
        placeholder="Use short phrases separated by commas (example: music, writing, coding)",
        required=False,
        max_length=500
    )

    def __init__(self, builder_view):
        super().__init__()
        self.builder_view = builder_view

    async def on_submit(self, interaction: discord.Interaction):

        update_profile(
            interaction.user.id,
            hobbies=str(self.hobbies)
        )

        await self.builder_view.refresh()
        await interaction.response.defer()