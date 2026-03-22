import discord
from discord import ui

from database import get_story_by_id
from features.stories.views.clone_library_view import build_story_embed


class FanartStoryView(ui.View):

    def __init__(self, story_id, user, parent_view):

        super().__init__(timeout=300)

        self.story_id = story_id
        self.user = user
        self.parent_view = parent_view

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    # ------------------------------
    # EMBED
    # ------------------------------

    def build_embed(self):

        story_row = get_story_by_id(self.story_id)

        if not story_row:

            return discord.Embed(
                title="Story not found",
                color=discord.Color.red()
            )

        return build_story_embed(
            story_row,
            self.user
        )

    # ------------------------------
    # BUTTONS
    # ------------------------------

    @ui.button(label="🎬 See Extras", style=discord.ButtonStyle.success)
    async def extras(self, interaction: discord.Interaction, button: ui.Button):

        from features.stories.views.story_extras_view import StoryExtrasView

        view = StoryExtrasView(
            story_id=self.story_id,
            parent_story_view=self,
            fanart_view=self.parent_view
        )

        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view
        )

    @ui.button(label="🎨 Return to Fanart", style=discord.ButtonStyle.primary)
    async def back(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )