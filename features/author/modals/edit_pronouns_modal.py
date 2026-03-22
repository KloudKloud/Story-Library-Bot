import discord
from discord import ui
from database import update_profile


class EditPronounsModal(ui.Modal, title="Edit Pronouns"):

    pronouns = ui.TextInput(
        label="Pronouns",
        placeholder="she/her, they/them, etc.",
        required=False
    )

    def __init__(self, builder_view):
        super().__init__()
        self.builder_view = builder_view

    async def on_submit(self, interaction: discord.Interaction):

        update_profile(
            interaction.user.id,
            pronouns=str(self.pronouns)
        )

        await self.builder_view.refresh()

        await interaction.response.defer()