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


async def _global_world_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplete for /world search — searches all world cards globally."""
    from database import get_all_world_cards, get_world_cards_by_user
    import random as _random

    all_worlds = get_all_world_cards()

    if not current:
        # Smart defaults: up to 3 most-recent from this user, then 1 random from others
        uid         = get_user_id(str(interaction.user.id))
        user_worlds = get_world_cards_by_user(uid) if uid else []
        user_sorted = sorted(user_worlds, key=lambda w: w.get("id", 0), reverse=True)

        choices = []
        for w in user_sorted[:3]:
            story = w.get("story_title") or "Unknown Story"
            label = f"🌍 {w['name']} ✦ {story}"
            choices.append(app_commands.Choice(name=label[:100], value=str(w["id"])))

        own_ids    = {w["id"] for w in user_worlds}
        others     = [w for w in all_worlds if w["id"] not in own_ids]
        if others:
            pick  = _random.choice(others)
            label = f"🌍 {pick['name']} ✦ {pick.get('story_title', '?')} ({pick.get('author', '?')})"
            choices.append(app_commands.Choice(name=label[:100], value=str(pick["id"])))

        choices = choices[:4]
        choices.append(app_commands.Choice(
            name="✏️ Start typing to search all world cards…", value="__hint__"
        ))
        return choices

    name_matches  = []
    other_matches = []
    q = current.lower()
    for w in all_worlds:
        name   = w.get("name", "")
        story  = w.get("story_title") or ""
        author = w.get("author") or ""
        label  = f"🌍 {name} ✦ {story} ({author})"
        if q in name.lower():
            name_matches.append(app_commands.Choice(name=label[:100], value=str(w["id"])))
        elif q in story.lower() or q in author.lower():
            other_matches.append(app_commands.Choice(name=label[:100], value=str(w["id"])))

    results = (name_matches + other_matches)[:4]
    if len(name_matches) + len(other_matches) > 4:
        results.append(app_commands.Choice(
            name="✏️ Keep typing to narrow down results…", value="__hint__"
        ))
    return results


async def _myworld_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplete for /world myworld — user's own world cards with story label."""
    from database import get_world_cards_by_user
    uid    = get_user_id(str(interaction.user.id))
    worlds = get_world_cards_by_user(uid) if uid else []
    worlds_sorted = sorted(worlds, key=lambda w: w.get("id", 0), reverse=True)

    def make_label(w):
        story = w.get("story_title") or "Unknown Story"
        return f"🌍 {w['name']} ✦ {story}"

    if not current:
        choices = [
            app_commands.Choice(name=make_label(w)[:100], value=str(w["id"]))
            for w in worlds_sorted[:4]
        ]
        choices.append(app_commands.Choice(
            name="✏️ Start typing to search your world cards…", value="__hint__"
        ))
        return choices

    results = [
        app_commands.Choice(name=make_label(w)[:100], value=str(w["id"]))
        for w in worlds_sorted
        if current.lower() in make_label(w).lower()
    ]
    capped = results[:4]
    if len(results) > 4:
        capped.append(app_commands.Choice(
            name="✏️ Keep typing to narrow down results…", value="__hint__"
        ))
    return capped


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

    # ── /world myworld ────────────────────────────

    @group.command(name="myworld", description="Browse all your world cards, or jump straight to one")
    @app_commands.describe(world_card="Optional: jump straight to a world card")
    @app_commands.autocomplete(world_card=_myworld_autocomplete)
    async def world_myworld(
        interaction: discord.Interaction,
        world_card: str = None,
    ):
        from database import get_world_cards_by_user
        from features.world.views.my_worlds_roster_view import (
            MyWorldsRosterView, MyWorldDetailView, build_roster_embed,
        )

        add_user(str(interaction.user.id), interaction.user.name)
        uid    = get_user_id(str(interaction.user.id))
        worlds = get_world_cards_by_user(uid) if uid else []

        if not worlds:
            await interaction.response.send_message(
                "You don't have any world cards yet! Use `/world add` to create one~",
                ephemeral=True,
            )
            return

        worlds_sorted = sorted(worlds, key=lambda w: (w.get("name") or "").lower())

        # ── Optional: jump straight to a specific world card ──
        if world_card and world_card != "__hint__":
            try:
                world_id = int(world_card)
            except ValueError:
                await interaction.response.send_message(
                    "Please select a world card from autocomplete.", ephemeral=True
                )
                return

            world_index = next(
                (i for i, w in enumerate(worlds_sorted) if w["id"] == world_id), None
            )
            if world_index is None:
                await interaction.response.send_message(
                    "That world card wasn't found in your collection.", ephemeral=True
                )
                return

            detail_view = MyWorldDetailView(worlds_sorted, world_index, interaction.user, return_page=0)
            await interaction.response.send_message(
                embed=detail_view.build_embed(),
                view=detail_view,
            )
            return

        # ── Default: open roster page 1 ──────────────────────
        total_pages = max(1, (len(worlds_sorted) + 4) // 5)
        view = MyWorldsRosterView(worlds_sorted, interaction.user, start_page=0)
        await interaction.response.send_message(
            embed=build_roster_embed(
                worlds_sorted, 0, total_pages, interaction.user.display_name,
                viewer_discord_id=str(interaction.user.id),
            ),
            view=view,
        )

    # ── /world search ─────────────────────────────

    @group.command(name="search", description="Browse all world cards, or jump straight to one")
    @app_commands.describe(world_card="Optional: jump straight to a specific world card")
    @app_commands.autocomplete(world_card=_global_world_autocomplete)
    async def world_search(
        interaction: discord.Interaction,
        world_card: str = None,
    ):
        from database import get_all_world_cards, get_world_card_by_id
        from features.world.views.world_search_view import (
            WorldSearchRosterView, WorldSearchDetailView, PAGE_SIZE,
        )

        add_user(str(interaction.user.id), interaction.user.name)

        # ── No world card specified: open roster ──────────────────
        if not world_card or world_card == "__hint__":
            all_worlds = get_all_world_cards()
            if not all_worlds:
                await interaction.response.send_message(
                    "No world cards in the library yet.", ephemeral=True, delete_after=4
                )
                return
            view = WorldSearchRosterView(all_worlds, interaction.user)
            await interaction.response.send_message(embed=view.build_embed(), view=view)
            return

        # ── World card specified: open detail directly ─────────────
        try:
            world_id = int(world_card)
        except ValueError:
            await interaction.response.send_message(
                "Please select a world card from autocomplete.", ephemeral=True
            )
            return

        selected = get_world_card_by_id(world_id)
        if not selected:
            await interaction.response.send_message("World card not found.", ephemeral=True)
            return

        all_worlds = get_all_world_cards()
        roster     = WorldSearchRosterView(all_worlds, interaction.user)

        selected_index = next(
            (i for i, w in enumerate(roster._sorted) if w["id"] == world_id), 0
        )
        return_page = selected_index // PAGE_SIZE
        roster.page = return_page

        view = WorldSearchDetailView(
            worlds=roster._sorted,
            index=selected_index,
            viewer=interaction.user,
            roster=roster,
            return_page=return_page,
        )
        await interaction.response.send_message(embed=view.build_embed(), view=view)
