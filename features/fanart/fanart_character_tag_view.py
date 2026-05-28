import discord
from discord import ui

from database import (
    get_characters_by_user,
    clear_fanart_characters,
    add_fanart_character,
    get_user_id
)
from ui import TimeoutMixin


class FanartCharacterTagView(TimeoutMixin, ui.View):

    def __init__(self, editor_view):

        super().__init__(timeout=300)

        self.editor_view = editor_view

        user_id = get_user_id(
            str(editor_view.viewer.id)
        )

        self.characters = get_characters_by_user(user_id)
        self.viewer = editor_view.viewer

        self.select = self.CharacterSelect(self)
        self.add_item(self.select)

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

    @ui.button(label="✔️ Save Tags", style=discord.ButtonStyle.success)
    async def save(self, interaction, button):

        fanart_id = self.editor_view.fanart[0]

        clear_fanart_characters(fanart_id)

        for value in self.select.values:
            add_fanart_character(
                fanart_id,
                int(value)
            )

        await interaction.response.edit_message(
            embed=self.editor_view.build_editor_embed(),
            view=self.editor_view
        )

    @ui.button(label="⬅️ Back", style=discord.ButtonStyle.secondary)
    async def back(self, interaction, button):

        await interaction.response.edit_message(
            embed=self.editor_view.build_editor_embed(),
            view=self.editor_view
        )

    class CharacterSelect(ui.Select):

        def __init__(self, view_ref):

            self.view_ref = view_ref

            options = [
                discord.SelectOption(
                    label=row["name"][:100],
                    value=str(row["id"])
                )
                for row in view_ref.characters
            ]

            super().__init__(
                placeholder="🧬 Select characters...",
                options=options[:25],
                min_values=0,
                max_values=min(25, len(options))
            )