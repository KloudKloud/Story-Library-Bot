import discord
from discord import ui
import random

from embeds.character_embeds import build_character_card

from database import (
    get_character_by_id,
    get_story_by_character,
    get_discord_id_by_story,
    get_stories_by_discord_user,
    get_all_characters,
    get_user_id,
    get_favorite_characters,
    add_favorite_character,
    remove_favorite_character,
    is_favorite_character
)
from database import get_characters_by_story
from database import get_fanart_by_character
from features.fanart.views.fanart_gallery_view import FanartGalleryView

from features.stories.views.showcase_view import ShowcaseView
from features.stories.views.character_story_view import CharacterStoryView
from ui import TimeoutMixin


# =====================================================
# QUICK VIEW (QTE STYLE)
# =====================================================

# =====================================================
# FAVORITE REMOVE CONFIRMATION
# =====================================================

class ReplaceFavoriteView(TimeoutMixin, ui.View):

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

        options = []

        for fav in favorites:
            options.append(
                discord.SelectOption(
                    label=f"{fav['name']} → Replace with {new_character['name']}",
                    value=str(fav["id"])
                )
            )

        self.select = ui.Select(
            placeholder="Choose a character to replace...",
            options=options
        )

        self.select.callback = self.replace_callback

        self.add_item(self.select)

    # ------------------------------------------------
    # REPLACE FAVORITE
    # ------------------------------------------------

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

    # ------------------------------------------------
    # CANCEL BUTTON
    # ------------------------------------------------

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.edit_message(
            content=None,
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )

class ConfirmFavoriteRemoval(TimeoutMixin, ui.View):

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

    # ---------------------------------
    # YES REMOVE
    # ---------------------------------

    @ui.button(label="Yes, Remove", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):

        remove_favorite_character(
            self.user_id,
            self.character["id"]
        )

        self.parent_view.rebuild_character()
        self.parent_view.update_buttons()

        await interaction.response.edit_message(
            content=None,
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )

    # ---------------------------------
    # CANCEL
    # ---------------------------------

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.edit_message(
            content=None,
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )

class CharacterQuickView(TimeoutMixin, ui.View):

    def __init__(self, characters, index, viewer):

        super().__init__(timeout=300)

        self.characters = characters
        self.index = index
        self.viewer = viewer

        # store IDs safely (dict access now)
        self.character_id = self.current_character()["id"]

        # dropdown created once
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

    # =====================================================
    # CORE STATE
    # =====================================================

    def current_character(self):
        return self.characters[self.index]

    def rebuild_character(self):
        """
        ⭐ ALWAYS rebuild fresh from DB.
        Future-proof for favorites / updates.
        """
        fresh = get_character_by_id(self.character_id)
        if fresh:
            self.characters[self.index] = fresh

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

        # -----------------------------
        # Lore button
        # -----------------------------
        lore = char.get("lore")
        self.view_lore.disabled = not lore

        # -----------------------------
        # Favorite button state
        # -----------------------------
        try:

            user_id = get_user_id(str(self.viewer.id))

            if user_id and is_favorite_character(user_id, char["id"]):

                self.mark_favorite.label = "✦ Unstar"
                self.mark_favorite.style = discord.ButtonStyle.primary

            else:

                self.mark_favorite.label = "✦ Favorite"
                self.mark_favorite.style = discord.ButtonStyle.primary

        except:
            pass

    # =====================================================
    # BUTTONS (ROW 0)
    # ORDER: Favorite → Lore → Author Bio → Story
    # =====================================================

    @ui.button(label="✦ Favorite", style=discord.ButtonStyle.primary, row=0)
    async def mark_favorite(self, interaction, button):

        char = self.current_character()

        character_id = char["id"]
        story_id = char["story_id"]

        user_id = get_user_id(str(interaction.user.id))

        if not user_id:
            await interaction.response.send_message(
                "User not registered.",
                ephemeral=True
            )
            return

        message_text = None

        # ---------------------------------
        # Already favorite → remove
        # ---------------------------------

        if is_favorite_character(user_id, character_id):

            story = get_story_by_character(character_id)
            story_title = story["title"] if story else "this story"

            confirm_view = ConfirmFavoriteRemoval(
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

        else:

            favorites = get_favorite_characters(user_id, story_id)

            if len(favorites) >= 2:

                story = get_story_by_character(character_id)
                story_title = story["title"] if story else "this story"

                view = ReplaceFavoriteView(
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

            message_text = "💫 Character added to your favorites!"

        # ---------------------------------
        # Refresh card so star appears
        # ---------------------------------

        self.rebuild_character()
        self.update_buttons()

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )

        # ---------------------------------
        # Send feedback message
        # ---------------------------------

        if message_text:
            await interaction.followup.send(
                message_text,
                ephemeral=True,
                delete_after=3
            )


    # -----------------------------------------------------
    # LORE BUTTON (NEW LOCATION)
    # -----------------------------------------------------

    @ui.button(label="📜 Lore", style=discord.ButtonStyle.primary, row=0)
    async def view_lore(self, interaction, button):
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


    # -----------------------------------------------------
    # AUTHOR BIO
    # -----------------------------------------------------

    @ui.button(label="👤 Author", style=discord.ButtonStyle.primary, row=0)
    async def author_bio(self, interaction, button):

        story = get_story_by_character(self.character_id)

        if not story:
            await interaction.response.send_message(
                "Author not found.",
                ephemeral=True
            )
            return

        story_id = story["id"]

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
            from_story_view=False
        )

        view.parent_view = self

        await interaction.response.edit_message(
            embed=view.generate_bio_embed(),
            view=view
        )


    # -----------------------------------------------------
    # STORY BUTTON (RENAMED)
    # -----------------------------------------------------

    @ui.button(label="📖 Story", style=discord.ButtonStyle.primary, row=0)
    async def view_story(self, interaction, button):

        view = CharacterStoryView(self, self.character_id, interaction.user)

        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view
        )

    # =====================================================
    # DROPDOWN (ROW 1)
    # =====================================================

    class ExploreSelect(ui.Select):

        def __init__(self, view_ref):

            self.view_ref = view_ref

            character = view_ref.current_character()
            char_name = character["name"]

            story = get_story_by_character(view_ref.character_id)

            if story:
                author_name = story["author"]
            else:
                author_name = "Author"

            options = [

                discord.SelectOption(
                    label=f"🧬 All {author_name}'s Character Cards",
                    value="all_author_chars"
                ),

                discord.SelectOption(
                    label=f"🎨 {char_name} ♢ Fanart Gallery",
                    value="fanart_gallery"
                )
            ]

            super().__init__(
                placeholder="✨ Explore Character...",
                options=options
            )

        async def callback(self, interaction):

            choice = self.values[0]

            character = self.view_ref.current_character()

            # ------------------------------------------------
            # ALL AUTHOR CHARACTERS
            # ------------------------------------------------

            if choice == "all_author_chars":

                story = get_story_by_character(self.view_ref.character_id)

                if not story:
                    await interaction.response.send_message(
                        "Story not found.",
                        ephemeral=True
                    )
                    return

                story_id = story["id"]

                chars = get_characters_by_story(story_id)

                if not chars:
                    await interaction.response.send_message(
                        "No characters found.",
                        ephemeral=True
                    )
                    return

                # -------------------------------------
                # Start with currently viewed character
                # -------------------------------------

                current_id = self.view_ref.character_id

                current_char = None
                other_chars = []

                for c in chars:
                    if c["id"] == current_id:
                        current_char = c
                    else:
                        other_chars.append(c)

                # Randomize the rest
                random.shuffle(other_chars)

                # Final ordered list
                ordered_chars = [current_char] + other_chars

                gallery = AuthorCharacterGalleryView(
                    ordered_chars,
                    0,
                    self.view_ref
                )

                user_id = get_user_id(str(interaction.user.id))

                await interaction.response.edit_message(
                    embed=build_character_card(
                        ordered_chars[0],
                        viewer=interaction.user,
                        user_id=user_id,
                        index=1,
                        total=len(ordered_chars)
                    ),
                    view=gallery
                )


            # ------------------------------------------------
            # FANART GALLERY (placeholder for now)
            # ------------------------------------------------

            if choice == "fanart_gallery":

                char_id = character["id"]

                fanart = get_fanart_by_character(char_id)

                if not fanart:

                    await interaction.response.send_message(
                        f"No fanart tagged with **{character['name']}** yet.",
                        ephemeral=True
                    )
                    return

                # Randomize order
                random.shuffle(fanart)

                view = FanartGalleryView(
                    fanart,
                    interaction.user,
                    minimal=True
                )

                view.parent_view = self.view_ref

                await interaction.response.edit_message(
                    embed=view.build_embed(),
                    view=view
                )

class AuthorCharacterGalleryView(TimeoutMixin, ui.View):

    def __init__(self, characters, index, parent_view):

        super().__init__(timeout=300)

        self.characters = characters
        self.index = index
        self.parent_view = parent_view
        self.viewer = parent_view.viewer

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

    def current(self):
        return self.characters[self.index]

    def update_buttons(self):

        # navigation
        self.left.disabled = self.index == 0
        self.right.disabled = self.index == len(self.characters) - 1

        char = self.current()

        lore = char.get("lore")
        self.lore.disabled = not lore


    # ------------------------------------------------
    # LEFT
    # ------------------------------------------------

    @ui.button(label="⬅️", style=discord.ButtonStyle.secondary, row=0)
    async def left(self, interaction, button):

        self.index -= 1
        self.update_buttons()

        char = self.current()

        user_id = get_user_id(str(interaction.user.id))

        await interaction.response.edit_message(
            embed=build_character_card(
                char,
                viewer=interaction.user,
                user_id=user_id,
                index=self.index + 1,
                total=len(self.characters)
            ),
            view=self
        )


    # ------------------------------------------------
    # LORE
    # ------------------------------------------------

    @ui.button(label="📜 Lore", style=discord.ButtonStyle.primary, row=0)
    async def lore(self, interaction, button):
        from embeds.character_embeds import build_lore_embed
        char = self.current()
        lore = char.get("lore")
        if not lore:
            await interaction.response.send_message("No lore written yet.", ephemeral=True)
            return
        await interaction.response.send_message(embed=build_lore_embed(char["name"], lore), ephemeral=True)


    # ------------------------------------------------
    # RETURN TO HUB
    # ------------------------------------------------

    @ui.button(label="🏠 Return to Hub", style=discord.ButtonStyle.success, row=0)
    async def return_hub(self, interaction, button):

        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )


    # ------------------------------------------------
    # RIGHT
    # ------------------------------------------------

    @ui.button(label="➡️", style=discord.ButtonStyle.secondary, row=0)
    async def right(self, interaction, button):

        self.index += 1
        self.update_buttons()

        char = self.current()

        user_id = get_user_id(str(interaction.user.id))

        await interaction.response.edit_message(
            embed=build_character_card(
                char,
                viewer=interaction.user,
                user_id=user_id,
                index=self.index + 1,
                total=len(self.characters)
            ),
            view=self
        )