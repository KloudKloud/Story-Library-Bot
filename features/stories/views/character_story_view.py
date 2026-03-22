import discord
from discord import ui
import random

from database import (
    get_story_by_character,
    get_discord_id_by_story,
    get_stories_by_discord_user,
)

from features.stories.views.showcase_view import ShowcaseView
from features.stories.views.story_extras_view import StoryExtrasView
from embeds.character_embeds import build_character_card
from features.stories.views.clone_library_view import build_story_embed


# =====================================================
# CHARACTER STORY VIEW (QTE STORY SNAPSHOT)
# =====================================================

class CharacterStoryView(ui.View):

    def __init__(self, character_view, character_id, viewer, from_mychar=False):

        super().__init__(timeout=300)

        self.character_view = character_view
        self.character_id = character_id
        self.viewer = viewer
        self.from_mychar = from_mychar

        self.story = get_story_by_character(character_id)

        # store story id safely
        self.story_id = self.story["id"] if self.story else None

        # Show correct back button — only one should appear
        if from_mychar:
            self.remove_item(self.back_to_character)
        else:
            self.remove_item(self.back_to_mychar)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    # =====================================================
    # EMBED BUILDER
    # =====================================================

    def build_embed(self):

        if not self.story:

            return discord.Embed(
                title="Story not found.",
                color=discord.Color.red()
            )

        return build_story_embed(
            self.story,
            self.viewer
        )

    # =====================================================
    # BUTTONS
    # =====================================================

    def rebuild_story_embed(self):
        return self.build_embed()


    # -----------------------------------------------------
    # EXTRAS
    # -----------------------------------------------------

    @ui.button(label="✨ Extras", style=discord.ButtonStyle.primary, row=0)
    async def extras(self, interaction, button):

        if not self.story_id:

            await interaction.response.send_message(
                "Extras not available.",
                ephemeral=True
            )
            return

        view = StoryExtrasView(
            parent_story_view=self,
            char_hub_view=self.character_view,
            story_id=self.story_id
        )

        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view
        )


    # -----------------------------------------------------
    # AUTHOR BIO
    # -----------------------------------------------------

    @ui.button(label="👤 Author", style=discord.ButtonStyle.primary, row=0)
    async def author_bio(self, interaction, button):

        if not self.story:
            await interaction.response.send_message(
                "Author not found.",
                ephemeral=True
            )
            return

        story_id = self.story["id"]

        discord_id = get_discord_id_by_story(story_id)

        if not discord_id:
            await interaction.response.send_message(
                "Author profile missing.",
                ephemeral=True
            )
            return

        target_user = interaction.guild.get_member(int(discord_id))

        if not target_user:

            try:
                target_user = await interaction.guild.fetch_member(
                    int(discord_id)
                )

            except:

                await interaction.response.send_message(
                    "Author not found in server.",
                    ephemeral=True
                )
                return

        stories = get_stories_by_discord_user(discord_id)

        view = ShowcaseView(
            stories,
            interaction.user,
            target_user,
            source="charview",
            from_story_view=True
        )

        view.character_view = self.character_view
        view.story_view = self

        await interaction.response.edit_message(
            embed=view.generate_bio_embed(),
            view=view
        )


    # -----------------------------------------------------
    # BACK TO CHARACTER HUB
    # -----------------------------------------------------

    @ui.button(label="⬅️ Back to Character", style=discord.ButtonStyle.success, row=0)
    async def back_to_character(self, interaction, button):

        # rebuild character fresh
        self.character_view.rebuild_character()

        await interaction.response.edit_message(
            embed=build_character_card(
                self.character_view.current_character(),
                viewer=self.viewer,
                index=self.character_view.index + 1,
                total=len(self.character_view.characters)
            ),
            view=self.character_view
        )

    # -----------------------------------------------------
    # BACK TO /mychars SLIDESHOW (if launched from there)
    # -----------------------------------------------------

    @ui.button(label="⬅️ Back to Chars", style=discord.ButtonStyle.success, row=0)
    async def back_to_mychar(self, interaction, button):
        # Rebuild current card in the slideshow
        self.character_view.rebuild_character()
        self.character_view.update_buttons()

        await interaction.response.edit_message(
            embed=self.character_view.build_embed(),
            view=self.character_view
        )