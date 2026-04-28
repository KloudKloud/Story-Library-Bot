"""
favorite_helpers.py

Generic ReplaceFavoriteView and ConfirmFavoriteRemoval that work with
any character detail view — just pass a refresh_callback that rebuilds
and re-renders the parent embed+view.
"""

import discord
from discord import ui
from database import (
    remove_favorite_character,
    add_favorite_character,
    get_favorite_characters,
    is_favorite_character,
    get_story_by_character,
    get_user_id,
)


# ─────────────────────────────────────────────────
# Replace favorite (at-limit popup)
# ─────────────────────────────────────────────────

class GenericReplaceFavoriteView(ui.View):
    """
    Shown when the user already has 2 favorites for a story.
    refresh_callback(interaction) must edit the message back to the parent card.
    """

    def __init__(self, favorites, new_character, user_id, story_title, refresh_callback, viewer=None):
        super().__init__(timeout=30)
        self.new_character    = new_character
        self.user_id          = user_id
        self.refresh_callback = refresh_callback
        self.viewer           = viewer

        options = [
            discord.SelectOption(
                label=f"{fav['name']} → Replace with {new_character['name']}"[:100],
                value=str(fav["id"])
            )
            for fav in favorites
        ]

        self.select = ui.Select(
            placeholder="Choose a character to replace...",
            options=options
        )
        self.select.callback = self._replace
        self.add_item(self.select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.viewer and interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    async def _replace(self, interaction: discord.Interaction):
        old_id = int(self.select.values[0])
        remove_favorite_character(self.user_id, old_id)
        add_favorite_character(
            self.user_id,
            self.new_character["story_id"],
            self.new_character["id"]
        )
        await self.refresh_callback(interaction)

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await self.refresh_callback(interaction)


# ─────────────────────────────────────────────────
# Confirm removal popup
# ─────────────────────────────────────────────────

class GenericConfirmFavoriteRemoval(ui.View):
    """
    Shown when the user clicks Unstar to confirm they want to remove.
    refresh_callback(interaction) must edit the message back to the parent card.
    """

    def __init__(self, character, user_id, refresh_callback, viewer=None):
        super().__init__(timeout=30)
        self.character        = character
        self.user_id          = user_id
        self.refresh_callback = refresh_callback
        self.viewer           = viewer

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.viewer and interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    @ui.button(label="Yes, Remove", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        remove_favorite_character(self.user_id, self.character["id"])
        await self.refresh_callback(interaction)

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await self.refresh_callback(interaction)


# ─────────────────────────────────────────────────
# Shared fav toggle logic
# ─────────────────────────────────────────────────

async def handle_fav_toggle(interaction: discord.Interaction, char: dict, refresh_callback):
    """
    Full favorite toggle with limit enforcement.

    char            — character dict with at least id, story_id, name
    refresh_callback(interaction) — async callable that edits the message
                                    back to the calling view's embed+view
    """
    uid = get_user_id(str(interaction.user.id))
    if not uid:
        await interaction.response.send_message("No profile found.", ephemeral=True)
        return

    char_id  = char["id"]
    story_id = char.get("story_id")

    # ── Already a favorite → confirm removal ─────────────────────
    if is_favorite_character(uid, char_id):
        story     = get_story_by_character(char_id)
        story_title = story["title"] if story else "this story"

        view = GenericConfirmFavoriteRemoval(
            character=char,
            user_id=uid,
            refresh_callback=refresh_callback,
            viewer=interaction.user
        )
        await interaction.response.edit_message(
            content=f"💔 Remove **{char['name']}** from your favorites?",
            embed=None,
            view=view
        )
        return

    # ── Under the limit → add directly ───────────────────────────
    favorites = get_favorite_characters(uid, story_id) if story_id else []

    if len(favorites) < 2:
        add_favorite_character(uid, story_id, char_id)
        await refresh_callback(interaction)
        return

    # ── At limit → show replace picker ───────────────────────────
    story       = get_story_by_character(char_id)
    story_title = story["title"] if story else "this story"

    view = GenericReplaceFavoriteView(
        favorites=favorites,
        new_character=char,
        user_id=uid,
        story_title=story_title,
        refresh_callback=refresh_callback,
        viewer=interaction.user
    )
    await interaction.response.edit_message(
        content=(
            f"You already have **two favorite characters** from **{story_title}**.\n"
            f"Select one to replace with **{char['name']}**."
        ),
        embed=None,
        view=view
    )