import discord
from discord import ui
from database import update_profile


class EditFavoriteAuthorsModal(ui.Modal, title="Top Authors"):

    favorite_authors = ui.TextInput(
        label="Favorite Authors",
        style=discord.TextStyle.paragraph,
        placeholder="Who inspires your writing?",
        required=False,
        max_length=500
    )

    def __init__(self, builder_view):
        super().__init__()
        self.builder_view = builder_view

    async def on_submit(self, interaction: discord.Interaction):

        update_profile(
            interaction.user.id,
            favorite_authors=str(self.favorite_authors)
        )

        await self.builder_view.refresh()
        await interaction.response.defer()