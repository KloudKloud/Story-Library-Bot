import discord
from discord import ui

from features.stories.views.confirm_delete_story_view import (
    ConfirmDeleteStoryView
)


class RemoveStorySelectView(ui.View):

    def __init__(self, stories, viewer=None):
        super().__init__(timeout=120)

        self.stories = stories
        self.viewer = viewer
        self.add_item(self.StorySelect(stories, viewer))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.viewer and interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    class StorySelect(ui.Select):

        def __init__(self, stories, viewer=None):

            options = [
                discord.SelectOption(
                    label=s[1][:100],   # title
                    value=str(s[0])     # story_id
                )
                for s in stories
            ]

            super().__init__(
                placeholder="Select story to remove...",
                options=options
            )

            self.stories = stories
            self.viewer = viewer

        async def callback(self, interaction):

            story_id = int(self.values[0])

            selected = next(
                (s for s in self.stories if s[0] == story_id),
                None
            )

            if not selected:
                await interaction.response.send_message(
                    "Story not found.",
                    ephemeral=True
                )
                return

            title = selected[1]

            view = ConfirmDeleteStoryView(
                story_id,
                title,
                viewer=self.viewer
            )

            await interaction.response.edit_message(
                content=(
                    f"⚠️ Are you sure you want to remove "
                    f"**{title}**?"
                ),
                view=view
            )