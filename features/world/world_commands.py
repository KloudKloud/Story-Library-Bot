import discord
from discord import app_commands

from database import add_user, get_user_id


# ─────────────────────────────────────────────────
# Autocomplete helpers
# ─────────────────────────────────────────────────

async def _story_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplete for the user's own stories, including the null/Character Storage story."""
    from database import get_user_id, get_stories_by_user
    uid = get_user_id(str(interaction.user.id))
    if not uid:
        return []
    stories = get_stories_by_user(uid) or []

    real_results = []
    storage_result = None

    for s in stories:
        sid      = s[0]
        title    = s[1]
        is_dummy = bool(s[6])

        if is_dummy:
            _keywords = "character storage private collection"
            if not current or current.lower() in _keywords:
                storage_result = app_commands.Choice(name="📦 Character Storage", value=str(sid))
        else:
            if current.lower() in title.lower():
                real_results.append(app_commands.Choice(name=title[:100], value=str(sid)))

    capped = real_results[:24]
    if storage_result:
        capped.append(storage_result)
    return capped


async def _world_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplete for the user's world cards."""
    from database import get_world_cards_by_user
    uid    = get_user_id(str(interaction.user.id))
    worlds = get_world_cards_by_user(uid) if uid else []
    choices = []
    for w in worlds:
        name = w["name"] if isinstance(w, dict) else w[2]
        wid  = w["id"]   if isinstance(w, dict) else w[0]
        if current.lower() in name.lower():
            choices.append(app_commands.Choice(name=name[:100], value=str(wid)))
        if len(choices) >= 25:
            break
    return choices


# ─────────────────────────────────────────────────
# Command registration
# ─────────────────────────────────────────────────

def register_world_commands(group: app_commands.Group, guild_id: int):

    # ── /world add ────────────────────────────────

    @group.command(name="add", description="Create a new world card for one of your stories")
    @app_commands.describe(
        story = "Choose the story this world card belongs to",
        name  = "Name of the world card (location, artifact, organization, etc.)",
    )
    @app_commands.autocomplete(story=_story_autocomplete)
    async def world_add(
        interaction: discord.Interaction,
        story: str,
        name:  str,
    ):
        from features.world.service import create_world_card
        from database import get_world_cards_by_user, get_story_by_id

        await interaction.response.defer(ephemeral=True)
        add_user(str(interaction.user.id), interaction.user.name)

        try:
            story_id = int(story)
        except ValueError:
            await interaction.followup.send(
                "❌ Please select a story from the dropdown.", ephemeral=True
            )
            return

        story_row = get_story_by_id(story_id)
        if not story_row:
            await interaction.followup.send("❌ Story not found.", ephemeral=True)
            return

        uid = get_user_id(str(interaction.user.id))
        if str(story_row["user_id"]) != str(uid):
            await interaction.followup.send(
                "❌ You can only add world cards to your own stories.", ephemeral=True
            )
            return

        name = name.strip()
        if not name:
            await interaction.followup.send("❌ Please enter a name.", ephemeral=True)
            return

        try:
            world_id = create_world_card(interaction.user.id, interaction.user.name, story_id, name)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
            return

        # Open the builder directly for the new card
        from features.world.views.world_build_view import WorldBuildView, WorldBuildRosterView, PAGE_SIZE
        from database import get_world_cards_by_user as _get_worlds

        all_worlds = _get_worlds(uid)
        if not all_worlds:
            await interaction.followup.send(
                f"✅ **{name}** created! Use `/world build` to open the builder.",
                ephemeral=True
            )
            return

        world_index = next((i for i, w in enumerate(all_worlds) if w["id"] == world_id), 0)
        return_page = world_index // PAGE_SIZE

        view = WorldBuildView(all_worlds, world_index, interaction.user, return_page=return_page)
        msg = await interaction.followup.send(
            f"🌍 **{name}** created! Opening builder...",
            embed=view.build_embed(),
            view=view,
            ephemeral=True,
        )
        view.builder_message = msg
        await view.attach_message(msg)

    # ── /world build ──────────────────────────────

    @group.command(name="build", description="Open the world card builder")
    @app_commands.describe(world="Choose a world card to edit (leave blank to browse all)")
    @app_commands.autocomplete(world=_world_autocomplete)
    async def world_build(
        interaction: discord.Interaction,
        world: str = None,
    ):
        from features.world.views.world_build_view import (
            WorldBuildView, WorldBuildRosterView,
            build_world_roster_embed, PAGE_SIZE,
        )
        from database import get_world_cards_by_user, get_world_card_by_id

        await interaction.response.defer(ephemeral=True)
        add_user(str(interaction.user.id), interaction.user.name)

        uid        = get_user_id(str(interaction.user.id))
        all_worlds = get_world_cards_by_user(uid) if uid else []

        if not all_worlds:
            await interaction.followup.send(
                "❌ You haven't created any world cards yet! Use `/world add` to get started.",
                ephemeral=True
            )
            return

        if world is None:
            total_pages = max(1, (len(all_worlds) + PAGE_SIZE - 1) // PAGE_SIZE)
            roster = WorldBuildRosterView(all_worlds, interaction.user)
            msg = await interaction.followup.send(
                embed=build_world_roster_embed(
                    all_worlds, 0, total_pages, interaction.user.display_name,
                    viewer_discord_id=str(interaction.user.id),
                ),
                view=roster,
                ephemeral=True,
            )
            roster.builder_message = msg
            return

        try:
            world_id = int(world)
        except ValueError:
            await interaction.followup.send(
                "❌ Please select a world card from autocomplete.", ephemeral=True
            )
            return

        world_data = get_world_card_by_id(world_id)
        if not world_data:
            await interaction.followup.send("❌ World card not found.", ephemeral=True)
            return

        if str(world_data["user_id"]) != str(uid):
            await interaction.followup.send(
                "❌ You do not own that world card.", ephemeral=True
            )
            return

        world_index = next((i for i, w in enumerate(all_worlds) if w["id"] == world_id), 0)
        return_page = world_index // PAGE_SIZE

        # Merge story fields from all_worlds
        merged = dict(world_data)
        match  = next((w for w in all_worlds if w["id"] == world_id), None)
        if match:
            for key in ("story_title", "story_id", "author", "cover_url"):
                merged.setdefault(key, match.get(key))
        all_worlds[world_index] = merged

        view = WorldBuildView(all_worlds, world_index, interaction.user, return_page=return_page)
        msg = await interaction.followup.send(
            embed=view.build_embed(), view=view, ephemeral=True
        )
        view.builder_message = msg
        await view.attach_message(msg)

    # ── /world delete ─────────────────────────────

    @group.command(name="delete", description="Delete one of your world cards — cleans up all collectors' copies")
    @app_commands.describe(world="Choose the world card to delete")
    @app_commands.autocomplete(world=_world_autocomplete)
    async def world_delete(
        interaction: discord.Interaction,
        world: str,
    ):
        from database import get_world_card_by_id, get_world_card_collectors

        await interaction.response.defer(ephemeral=True)
        add_user(str(interaction.user.id), interaction.user.name)

        try:
            world_id = int(world)
        except ValueError:
            await interaction.followup.send(
                "❌ Please select a world card from autocomplete.", ephemeral=True
            )
            return

        uid       = get_user_id(str(interaction.user.id))
        world_row = get_world_card_by_id(world_id)

        if not world_row:
            await interaction.followup.send("❌ World card not found.", ephemeral=True)
            return

        if str(world_row["user_id"]) != str(uid):
            await interaction.followup.send(
                "❌ You can only delete your own world cards.", ephemeral=True
            )
            return

        collector_count = len(get_world_card_collectors(world_id))
        world_name      = world_row["name"]
        story_name      = world_row.get("story_title") or "Unknown Story"

        # Confirmation view
        class _ConfirmDeleteView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.confirmed = False

            @discord.ui.button(label="🗑️ Yes, delete it", style=discord.ButtonStyle.danger)
            async def confirm(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                self.confirmed = True
                self.stop()
                from features.world.service import delete_world_card_safe
                delete_world_card_safe(world_id)
                refund_note = (
                    f"\n-# 🎟️ **{collector_count}** collector{'s' if collector_count != 1 else ''} "
                    "received a respin token."
                ) if collector_count > 0 else ""
                await btn_interaction.response.edit_message(
                    content=(
                        f"🗑️ **{world_name}** has been deleted from the library.{refund_note}"
                    ),
                    view=None,
                )

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, btn_interaction: discord.Interaction, button: discord.ui.Button):
                self.stop()
                await btn_interaction.response.edit_message(
                    content="❌ Deletion cancelled.", view=None
                )

        collector_note = (
            f"\n-# ⚠️ **{collector_count}** collector{'s' if collector_count != 1 else ''} "
            "own this card — they'll each receive a respin token."
        ) if collector_count > 0 else ""

        confirm_view = _ConfirmDeleteView()
        await interaction.followup.send(
            f"⚠️ Are you sure you want to delete **{world_name}** *(from {story_name})*?"
            f"{collector_note}\n\n**This cannot be undone.**",
            view=confirm_view,
            ephemeral=True,
        )
