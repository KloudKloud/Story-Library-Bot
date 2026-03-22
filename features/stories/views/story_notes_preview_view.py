import discord
from discord import ui

from embeds.story_notes_embed import build_story_notes_embed
from features.stories.views.library_view import LibraryView
from database import get_all_stories_sorted
from ui import TimeoutMixin

class LibraryPreviewView(TimeoutMixin, ui.View):

    def __init__(self, builder):
        super().__init__(timeout=300)
        self.builder = builder
        self.viewer = builder.user

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

    @ui.button(label="⬅ Back to Notes", style=discord.ButtonStyle.primary)
    async def back_to_notes(self, interaction, button):

        from embeds.story_notes_embed import build_story_notes_embed

        await interaction.response.edit_message(
            embed=build_story_notes_embed(self.builder.story),
            view=StoryNotesPreviewView(self.builder)
        )

    @ui.button(label="🛠 Back to Editor", style=discord.ButtonStyle.success)
    async def back_to_editor(self, interaction, button):

        await interaction.response.edit_message(
            embed=self.builder.build_embed(),
            view=self.builder
        )

class StoryNotesPreviewView(TimeoutMixin, ui.View):

    def __init__(self, builder):
        super().__init__(timeout=300)
        self.builder = builder
        self.viewer = builder.user

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


    @ui.button(label="⬅️ Back to Builder", style=discord.ButtonStyle.primary)
    async def back_to_builder(self, interaction, button):

        await interaction.response.edit_message(
            embed=self.builder.build_embed(),
            view=self.builder
        )


    @ui.button(label="📚 Preview Library", style=discord.ButtonStyle.success)
    async def preview_library(self, interaction, button):

        stories = get_all_stories_sorted("alphabetical")

        story = None
        for s in stories:
            if s[9] == self.builder.story_id:
                story = s
                break

        if not story:
            await interaction.response.send_message(
                "Story not found.",
                ephemeral=True
            )
            return

        # Use LibraryView ONLY to generate the embed
        temp_view = LibraryView(
            stories,
            "Saphero's Library",
            interaction.user
        )

        embed = temp_view.generate_detail_embed(story)

        await interaction.response.edit_message(
            embed=embed,
            view=LibraryPreviewView(self.builder)
        )