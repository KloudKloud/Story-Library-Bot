import discord
from discord import ui

from database import get_story_by_id
from embeds.story_notes_embed import build_story_notes_embed


class FanartStoryNotesView(ui.View):

    def __init__(self, parent_story_view, parent_fanart_view, story_id):

        super().__init__(timeout=300)

        self.parent_story_view = parent_story_view
        self.parent_fanart_view = parent_fanart_view
        self.story_id = story_id
        self.viewer = parent_fanart_view.viewer

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    # =========================
    # BUILD EMBED
    # =========================

    def build_embed(self):

        story = get_story_by_id(self.story_id)

        if not story:
            return discord.Embed(
                title="Story not found.",
                color=discord.Color.red()
            )

        return build_story_notes_embed(story)

    # =========================
    # BUTTONS
    # =========================

    @ui.button(label="📖 Story", style=discord.ButtonStyle.success, row=0)
    async def back_story(self, interaction, button):

        await interaction.response.edit_message(
            embed=self.parent_story_view.build_embed(),
            view=self.parent_story_view
        )


    @ui.button(label="🎨 Return to Fanart", style=discord.ButtonStyle.primary, row=0)
    async def back_fanart(self, interaction, button):

        await interaction.response.edit_message(
            embed=self.parent_fanart_view.build_embed(),
            view=self.parent_fanart_view
        )