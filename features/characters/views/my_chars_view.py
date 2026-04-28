import discord
from discord import ui
import random

from embeds.character_embeds import build_character_card

from database import (
    get_character_by_id,
    get_story_by_character,
    get_discord_id_by_story,
    get_stories_by_discord_user,
    get_user_id,
    get_favorite_characters,
    add_favorite_character,
    remove_favorite_character,
    is_favorite_character,
    get_characters_by_story,
    get_fanart_by_character,
)

from features.fanart.views.fanart_gallery_view import FanartGalleryView
from features.stories.views.showcase_view import ShowcaseView
from features.stories.views.character_story_view import CharacterStoryView
from ui import TimeoutMixin


# =====================================================
# FAVORITE HELPERS (mirrors character_quick_view)
# =====================================================

class MyCharsReplaceFavoriteView(TimeoutMixin, ui.View):

    def __init__(self, parent_view, favorites, new_character, user_id, story_title):
        super().__init__(timeout=30)

        self.parent_view = parent_view
        self.favorites = favorites
        self.new_character = new_character
        self.user_id = user_id
        self.story_title = story_title
        self.viewer = parent_view.viewer

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

        options = [
            discord.SelectOption(
                label=f"{fav['name']} → Replace with {new_character['name']}",
                value=str(fav["id"])
            )
            for fav in favorites
        ]

        self.select = ui.Select(
            placeholder="Choose a character to replace...",
            options=options
        )
        self.select.callback = self.replace_callback
        self.add_item(self.select)

    async def replace_callback(self, interaction: discord.Interaction):
        old_character_id = int(self.select.values[0])
        remove_favorite_character(self.user_id, old_character_id)
        add_favorite_character(
            self.user_id,
            self.new_character["story_id"],
            self.new_character["id"]
        )
        self.parent_view.rebuild_character()
        self.parent_view.update_buttons()
        await interaction.response.edit_message(
            content=None,
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(
            content=None,
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )


class MyCharsConfirmFavoriteRemoval(TimeoutMixin, ui.View):

    def __init__(self, parent_view, character, story_title, user_id):
        super().__init__(timeout=30)
        self.parent_view = parent_view
        self.character = character
        self.story_title = story_title
        self.user_id = user_id
        self.viewer = parent_view.viewer

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

    @ui.button(label="Yes, Remove", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        remove_favorite_character(self.user_id, self.character["id"])
        self.parent_view.rebuild_character()
        self.parent_view.update_buttons()
        await interaction.response.edit_message(
            content=None,
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(
            content=None,
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )


# =====================================================
# MY CHARS VIEW — /mychars slideshow
# =====================================================

class MyCharsView(TimeoutMixin, ui.View):
    """
    Slideshow of the calling user's own characters.

    Row 0: ⬅  |  ✦ Favorite  |  📜 Lore  |  ➡
    Row 1: Explore dropdown  (Author Bio, Book Page, Fanart Gallery)
    """

    def __init__(self, characters: list, start_index: int, viewer: discord.Member):
        super().__init__(timeout=300)

        # Normalise to plain dicts so .get() always works regardless of
        # whether the caller passed sqlite3.Row objects or real dicts
        self.characters = [dict(c) for c in characters]
        self.index = start_index
        self.viewer = viewer

        # keep id for DB refreshes
        self.character_id = self.current_character()["id"]

        # Build the explore dropdown and attach it
        self.explore_select = self.ExploreSelect(self)
        self.explore_select.row = 1
        self.add_item(self.explore_select)

        self.update_buttons()

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

    # --------------------------------------------------
    # STATE HELPERS
    # --------------------------------------------------

    def current_character(self):
        return self.characters[self.index]

    def rebuild_character(self):
        """Refresh current character from DB."""
        fresh = get_character_by_id(self.character_id)
        if fresh:
            # Normalise to plain dict just in case
            self.characters[self.index] = dict(fresh) if not isinstance(fresh, dict) else fresh

    def build_embed(self):
        user_id = get_user_id(str(self.viewer.id))
        return build_character_card(
            self.current_character(),
            viewer=self.viewer,
            user_id=user_id,
            index=self.index + 1,
            total=len(self.characters)
        )

    def update_buttons(self):
        char = self.current_character()
        self.character_id = char["id"]

        # Arrows — smart enable/disable
        self.left_arrow.disabled  = (self.index == 0)
        self.right_arrow.disabled = (self.index == len(self.characters) - 1)

        # Lore — only enable if lore exists
        lore = char.get("lore")
        self.view_lore.disabled = not lore

        # Favorite button state
        try:
            user_id = get_user_id(str(self.viewer.id))
            if user_id and is_favorite_character(user_id, char["id"]):
                self.mark_favorite.label = "✦ Unstar"
                self.mark_favorite.style = discord.ButtonStyle.primary
            else:
                self.mark_favorite.label = "✦ Favorite"
                self.mark_favorite.style = discord.ButtonStyle.primary
        except Exception:
            pass

        # Rebuild the dropdown so its labels match the new character
        self.remove_item(self.explore_select)
        self.explore_select = self.ExploreSelect(self)
        self.explore_select.row = 1
        self.add_item(self.explore_select)

    # --------------------------------------------------
    # ROW 0 BUTTONS
    # Order: ⬅  |  ✦ Favorite  |  Lore  |  ➡
    # --------------------------------------------------

    @ui.button(label="⬅️", style=discord.ButtonStyle.secondary, row=0)
    async def left_arrow(self, interaction: discord.Interaction, button: ui.Button):
        self.index -= 1
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )

    @ui.button(label="✦ Favorite", style=discord.ButtonStyle.primary, row=0)
    async def mark_favorite(self, interaction: discord.Interaction, button: ui.Button):
        char = self.current_character()
        character_id = char["id"]
        story_id = char["story_id"]
        user_id = get_user_id(str(interaction.user.id))

        if not user_id:
            await interaction.response.send_message("User not registered.", ephemeral=True)
            return

        if is_favorite_character(user_id, character_id):
            story = get_story_by_character(character_id)
            story_title = story["title"] if story else "this story"
            confirm_view = MyCharsConfirmFavoriteRemoval(
                parent_view=self,
                character=char,
                story_title=story_title,
                user_id=user_id
            )
            await interaction.response.edit_message(
                content=f"💔 Remove **{char['name']}** from your favorites?",
                embed=None,
                view=confirm_view
            )
            return

        favorites = get_favorite_characters(user_id, story_id)

        if len(favorites) >= 2:
            story = get_story_by_character(character_id)
            story_title = story["title"] if story else "this story"
            view = MyCharsReplaceFavoriteView(
                parent_view=self,
                favorites=favorites,
                new_character=char,
                user_id=user_id,
                story_title=story_title
            )
            await interaction.response.edit_message(
                content=(
                    f"You already have **two favorite characters** from **{story_title}**.\n"
                    f"Select one to replace with **{char['name']}**."
                ),
                embed=None,
                view=view
            )
            return

        add_favorite_character(user_id, story_id, character_id)
        self.rebuild_character()
        self.update_buttons()

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )
        await interaction.followup.send("💫 Character added to your favorites!", ephemeral=True, delete_after=3)

    @ui.button(label="📜 Lore", style=discord.ButtonStyle.primary, row=0)
    async def view_lore(self, interaction: discord.Interaction, button: ui.Button):
        from embeds.character_embeds import build_lore_embed
        character = get_character_by_id(self.character_id)
        if not character:
            await interaction.response.send_message("Character not found.", ephemeral=True)
            return
        lore = character.get("lore")
        if not lore:
            await interaction.response.send_message("✨ This character has no lore written yet.", ephemeral=True)
            return
        await interaction.response.send_message(embed=build_lore_embed(character["name"], lore), ephemeral=True)

    @ui.button(label="➡️", style=discord.ButtonStyle.secondary, row=0)
    async def right_arrow(self, interaction: discord.Interaction, button: ui.Button):
        self.index += 1
        self.update_buttons()
        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )

    # --------------------------------------------------
    # ROW 1 — Explore Dropdown
    # Options: Author Bio, Book Page, Fanart Gallery
    # --------------------------------------------------

    class ExploreSelect(ui.Select):

        def __init__(self, view_ref: "MyCharsView"):
            self.view_ref = view_ref

            char = view_ref.current_character()
            char_name = char["name"]

            story = get_story_by_character(view_ref.character_id)
            story_title = story["title"] if story else "Story"
            author_name = story["author"] if story else "Author"

            options = [
                discord.SelectOption(
                    label=f"👤 See {author_name}'s Bio",
                    value="author_bio"
                ),
                discord.SelectOption(
                    label=f"📖 View {story_title}'s Page",
                    value="book_page"
                ),
                discord.SelectOption(
                    label=f"🎨 {char_name} ♢ Fanart Gallery",
                    value="fanart_gallery"
                ),
            ]

            super().__init__(
                placeholder="✨ Explore Character...",
                options=options
            )

        async def callback(self, interaction: discord.Interaction):
            choice = self.values[0]
            vr = self.view_ref
            character = vr.current_character()

            # ---- AUTHOR BIO ----
            if choice == "author_bio":
                story = get_story_by_character(vr.character_id)
                if not story:
                    await interaction.response.send_message("Author not found.", ephemeral=True)
                    return

                discord_id = get_discord_id_by_story(story["id"])
                if not discord_id:
                    await interaction.response.send_message("Author profile missing.", ephemeral=True)
                    return

                target_user = interaction.guild.get_member(int(discord_id))
                if not target_user:
                    try:
                        target_user = await interaction.guild.fetch_member(int(discord_id))
                    except Exception:
                        await interaction.response.send_message("Author not found in server.", ephemeral=True)
                        return

                stories = get_stories_by_discord_user(discord_id)
                showcase = ShowcaseView(
                    stories,
                    interaction.user,
                    target_user,
                    source="charview",
                    from_story_view=False
                )
                showcase.parent_view = vr
                await interaction.response.edit_message(
                    embed=showcase.generate_bio_embed(),
                    view=showcase
                )

            # ---- BOOK PAGE ----
            elif choice == "book_page":
                story_view = CharacterStoryView(vr, vr.character_id, interaction.user, from_mychar=True)
                await interaction.response.edit_message(
                    embed=story_view.build_embed(),
                    view=story_view
                )

            # ---- FANART GALLERY ----
            elif choice == "fanart_gallery":
                char_id = character["id"]
                fanart = get_fanart_by_character(char_id)

                if not fanart:
                    await interaction.response.send_message(
                        f"No fanart tagged with **{character['name']}** yet.",
                        ephemeral=True
                    )
                    return

                random.shuffle(fanart)
                gallery_view = FanartGalleryView(fanart, interaction.user, minimal=True)
                gallery_view.parent_view = vr

                await interaction.response.edit_message(
                    embed=gallery_view.build_embed(),
                    view=gallery_view
                )