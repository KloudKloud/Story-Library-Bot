import discord
from discord import ui
from database import update_profile


class EditFavPokemonModal(ui.Modal, title="Favorite Pokémon"):

    pokemon = ui.TextInput(
        label="Favorite Pokémon",
        placeholder="Espeon, Pikachu, etc.",
        required=False
    )

    def __init__(self, builder_view):
        super().__init__()
        self.builder_view = builder_view

    async def on_submit(self, interaction: discord.Interaction):

        update_profile(
            interaction.user.id,
            favorite_pokemon=str(self.pokemon)
        )

        await self.builder_view.refresh()

        await interaction.response.defer()