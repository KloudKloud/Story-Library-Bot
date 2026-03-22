import discord
from discord import ui
from database import update_profile


class EditFavoriteFicsModal(ui.Modal, title="Favorite Fics"):

    favorite_fics = ui.TextInput(
        label="Favorite Fics",
        style=discord.TextStyle.paragraph,
        placeholder="List stories you love reading.",
        required=False,
        max_length=500
    )

    def __init__(self, builder_view):
        super().__init__()
        self.builder_view = builder_view

    async def on_submit(self, interaction: discord.Interaction):

        update_profile(
            interaction.user.id,
            favorite_fics=str(self.favorite_fics)
        )

        await self.builder_view.refresh()
        await interaction.response.defer()