import discord
from discord import ui
from database import update_profile


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