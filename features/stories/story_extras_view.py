import discord
from discord import ui

from embeds.story_notes_embed import build_story_notes_embed
from database import get_story_by_id
from ui import TimeoutMixin


class StoryExtrasView(TimeoutMixin, ui.View):
    """
    Universal Extras / Story Notes view.

    Paths and their button sets (row 0):
      Character  → parent_story_view + char_hub_view   → "📖 Return to Story"  "🏠 Char Hub"
      Fanart     → parent_story_view + fanart_view      → "📖 Return to Story"  "🎨 Art Hub"
      Author     → author_view                          → "📖 Return to Story"  "✨ Author Page"
      Library    → library_view                         → "📖 Return to Story"
    """

    def __init__(
        self,
        story_id,
        parent_story_view=None,
        char_hub_view=None,
        fanart_view=None,
        author_view=None,
        library_view=None,
        viewer=None,
        stats_mode=False        # True = opened from /story stats; hides Return button
    ):

        super().__init__(timeout=300)

        self.story_id          = story_id
        self.parent_story_view = parent_story_view
        self.char_hub_view     = char_hub_view
        self.fanart_view       = fanart_view
        self.author_view       = author_view
        self.library_view      = library_view
        # Derive viewer from whichever parent is available
        if viewer:
            self.viewer = viewer
        elif char_hub_view and hasattr(char_hub_view, 'viewer'):
            self.viewer = char_hub_view.viewer
        elif fanart_view and hasattr(fanart_view, 'viewer'):
            self.viewer = fanart_view.viewer
        elif library_view and hasattr(library_view, 'user'):
            self.viewer = library_view.user
        elif author_view and hasattr(author_view, 'viewer'):
            self.viewer = author_view.viewer
        elif parent_story_view and hasattr(parent_story_view, 'viewer'):
            self.viewer = parent_story_view.viewer
        else:
            self.viewer = None
        self.stats_mode        = stats_mode

        # Decide which buttons to keep
        keep = set()

        if not stats_mode:
            keep.add("📖 Return to Story")

        if char_hub_view:
            keep.add("🏠 Char Hub")

        if fanart_view:
            keep.add("🎨 Art Hub")

        if author_view:
            keep.add("✨ Author Page")

        for item in list(self.children):
            if item.label not in keep:
                self.remove_item(item)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if self.viewer and interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    # ------------------------------------------------
    # EMBED
    # ------------------------------------------------

    def build_embed(self):
        story = get_story_by_id(self.story_id)
        return build_story_notes_embed(story, viewer=self.viewer)

    # ------------------------------------------------
    # 📖 RETURN TO STORY  (all paths)
    # ------------------------------------------------

    @ui.button(label="📖 Return to Story", style=discord.ButtonStyle.primary, row=0)
    async def return_story(self, interaction, button):

        # Library path
        if self.library_view:
            await interaction.response.edit_message(
                embed=self.library_view.generate_detail_embed(
                    self.library_view.current_item
                ),
                view=self.library_view
            )
            return

        # Character / Fanart paths  (have an explicit story card view)
        if self.parent_story_view:
            await interaction.response.edit_message(
                embed=self.parent_story_view.build_embed(),
                view=self.parent_story_view
            )
            return

        # Author path  (story card IS the showcase view)
        if self.author_view:
            await interaction.response.edit_message(
                embed=self.author_view.generate_story_showcase_embed(),
                view=self.author_view
            )
            return

        await interaction.response.send_message(
            "Couldn't find the story to return to.",
            ephemeral=True
        ,
                delete_after=4
            )

    # ------------------------------------------------
    # 🏠 CHAR HUB  (character path)
    # ------------------------------------------------

    @ui.button(label="🏠 Char Hub", style=discord.ButtonStyle.success, row=0)
    async def return_hub(self, interaction, button):

        from embeds.character_embeds import build_character_card

        hub = self.char_hub_view

        await interaction.response.edit_message(
            embed=build_character_card(
                hub.current_character(),
                viewer=interaction.user,
                index=hub.index + 1,
                total=len(hub.characters)
            ),
            view=hub
        )

    # ------------------------------------------------
    # 🎨 ART HUB  (fanart path)
    # ------------------------------------------------

    @ui.button(label="🎨 Art Hub", style=discord.ButtonStyle.success, row=0)
    async def return_fanart(self, interaction, button):

        await interaction.response.edit_message(
            embed=self.fanart_view.build_embed(),
            view=self.fanart_view
        )

    # ------------------------------------------------
    # ✨ AUTHOR PAGE  (author / showcase path)
    # ------------------------------------------------

    @ui.button(label="✨ Author Page", style=discord.ButtonStyle.success, row=0)
    async def return_author(self, interaction, button):

        # Return to the showcase bio page
        self.author_view.mode = "bio"
        self.author_view.refresh_ui()

        await interaction.response.edit_message(
            embed=self.author_view.generate_bio_embed(),
            view=self.author_view
        )

