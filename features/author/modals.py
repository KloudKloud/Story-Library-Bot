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


class EditFunFactModal(ui.Modal, title="Fun Fact"):

    fun_fact = ui.TextInput(
        label="Fun Fact",
        style=discord.TextStyle.paragraph,
        placeholder="Share something interesting about yourself!",
        required=False,
        max_length=300
    )

    def __init__(self, builder_view):
        super().__init__()
        self.builder_view = builder_view

    async def on_submit(self, interaction: discord.Interaction):

        update_profile(
            interaction.user.id,
            fun_fact=str(self.fun_fact)
        )

        await self.builder_view.refresh()
        await interaction.response.defer()


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
