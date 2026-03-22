"""
admin_commands.py
─────────────────────────────────────────────────────────────────────────────
Admin-only slash commands grouped under /admin.

Current commands
────────────────
  /admin givegems <user> <amount>     Give gems to a user
  /admin takegems <user> <amount>     Take gems from a user
  /admin delstory <story>             Force-delete any story  (autocomplete)
  /admin delchar  <character>         Force-delete any character (autocomplete)
  /admin delart   <fanart>            Force-delete any fanart piece (autocomplete)

Access control
──────────────
  Every command checks that the invoking member has the Discord
  "Administrator" permission.  Non-admins receive a private 3-second
  ephemeral error and the command does nothing.
─────────────────────────────────────────────────────────────────────────────
"""

import discord
from discord import app_commands

CRYSTAL = "💎"
HINT    = "__hint__"


def _is_admin(interaction: discord.Interaction) -> bool:
    member = interaction.user
    if isinstance(member, discord.Member):
        return member.guild_permissions.administrator
    return False


async def _deny(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Missing the **Administrator** role! Only admins can run this command!",
        ephemeral=True,
        delete_after=3,
    )


# ── Autocomplete helpers ───────────────────────────────────────────────────

async def _story_autocomplete(interaction: discord.Interaction, current: str):
    from database import get_all_stories_sorted
    stories = get_all_stories_sorted()
    choices = []
    for s in stories:
        title = s[0]
        sid   = s[9]
        if current.lower() in title.lower():
            choices.append(app_commands.Choice(name=title[:100], value=str(sid)))
        if len(choices) >= 4:
            break
    if len(choices) == 4 or (not current and len(stories) > 4):
        choices.append(app_commands.Choice(name="✏️ Keep typing to narrow down…", value=HINT))
    return choices


async def _char_autocomplete(interaction: discord.Interaction, current: str):
    from database import get_all_characters
    chars = get_all_characters()
    choices = []
    for c in chars:
        label = f"{c['name']}  —  {c.get('story_title', '?')}"
        if current.lower() in label.lower():
            choices.append(app_commands.Choice(name=label[:100], value=str(c["id"])))
        if len(choices) >= 4:
            break
    if len(choices) == 4 or (not current and len(chars) > 4):
        choices.append(app_commands.Choice(name="✏️ Keep typing to narrow down…", value=HINT))
    return choices


async def _fanart_autocomplete(interaction: discord.Interaction, current: str):
    from database import get_all_fanart_titles
    fanarts = get_all_fanart_titles()
    choices = []
    for f in fanarts:
        title = f.get("title") or f"Fanart #{f['id']}"
        if current.lower() in title.lower():
            choices.append(app_commands.Choice(name=title[:100], value=str(f["id"])))
        if len(choices) >= 4:
            break
    if len(choices) == 4 or (not current and len(fanarts) > 4):
        choices.append(app_commands.Choice(name="✏️ Keep typing to narrow down…", value=HINT))
    return choices


# ── Command registration ───────────────────────────────────────────────────

def register_admin_commands(admin_group: app_commands.Group, guild_id: int):

    # ── /admin givegems ───────────────────────────────────────────────────────

    @admin_group.command(name="givegems", description="[Admin] Give gems to a user")
    @app_commands.describe(
        user="The user to receive the gems",
        amount="How many gems to give (must be positive)",
    )
    async def admin_give_gems(
        interaction: discord.Interaction,
        user: discord.Member,
        amount: int,
    ):
        if not _is_admin(interaction):
            await _deny(interaction)
            return
        if amount <= 0:
            await interaction.response.send_message("Amount must be a positive number!", ephemeral=True, delete_after=3)
            return
        if user.bot:
            await interaction.response.send_message("You can't give gems to a bot!", ephemeral=True, delete_after=3)
            return

        from database import add_user, get_user_id, add_credits
        add_user(str(user.id), user.name)
        uid = get_user_id(str(user.id))
        if not uid:
            await interaction.response.send_message(f"Could not find or create an account for {user.display_name}.", ephemeral=True, delete_after=5)
            return

        new_balance = add_credits(uid, amount, f"admin_give:{interaction.user.id}")
        embed = discord.Embed(
            description=(
                f"✨ {interaction.user.mention} has given "
                f"{CRYSTAL} **{amount:,}** gems to {user.mention}!\n"
                f"-# {user.display_name}'s new balance: **{new_balance:,}** gems"
            ),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)

    # ── /admin takegems ───────────────────────────────────────────────────────

    @admin_group.command(name="takegems", description="[Admin] Take gems from a user")
    @app_commands.describe(
        user="The user to take gems from",
        amount="How many gems to take (must be positive)",
    )
    async def admin_take_gems(
        interaction: discord.Interaction,
        user: discord.Member,
        amount: int,
    ):
        if not _is_admin(interaction):
            await _deny(interaction)
            return
        if amount <= 0:
            await interaction.response.send_message("Amount must be a positive number!", ephemeral=True, delete_after=3)
            return
        if user.bot:
            await interaction.response.send_message("You can't take gems from a bot!", ephemeral=True, delete_after=3)
            return

        from database import add_user, get_user_id, spend_credits
        add_user(str(user.id), user.name)
        uid = get_user_id(str(user.id))
        if not uid:
            await interaction.response.send_message(f"Could not find an account for {user.display_name}.", ephemeral=True, delete_after=5)
            return

        success, new_balance = spend_credits(uid, amount, f"admin_take:{interaction.user.id}")
        if not success:
            current = new_balance
            if current > 0:
                from database import add_credits as _add
                _add(uid, -current, f"admin_take:{interaction.user.id}")
                new_balance = 0
                note = f"-# {user.display_name} only had **{current:,}** gems — balance set to **0**."
            else:
                note = f"-# {user.display_name} already had **0** gems."
        else:
            note = f"-# {user.display_name}'s new balance: **{new_balance:,}** gems"

        embed = discord.Embed(
            description=(
                f"🔻 {interaction.user.mention} has taken "
                f"{CRYSTAL} **{amount:,}** gems from {user.mention}!\n"
                f"{note}"
            ),
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed)

    # ── /admin delstory ───────────────────────────────────────────────────────

    @admin_group.command(name="delstory", description="[Admin] Force-delete a story from the library")
    @app_commands.describe(story="The story to delete")
    @app_commands.autocomplete(story=_story_autocomplete)
    async def admin_del_story(interaction: discord.Interaction, story: str):
        if not _is_admin(interaction):
            await _deny(interaction)
            return
        if story == HINT:
            await interaction.response.send_message("Keep typing to find the story!", ephemeral=True, delete_after=3)
            return

        from database import get_story_by_id, delete_story
        try:
            story_id = int(story)
        except ValueError:
            await interaction.response.send_message("❌ Invalid selection — please pick from the autocomplete list.", ephemeral=True, delete_after=5)
            return

        record = get_story_by_id(story_id)
        if not record:
            await interaction.response.send_message(f"❌ Story not found.", ephemeral=True, delete_after=5)
            return

        title = record["title"] if "title" in record.keys() else f"Story #{story_id}"

        class ConfirmDeleteStory(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30)

            @discord.ui.button(label="🗑 Yes, delete it", style=discord.ButtonStyle.danger)
            async def confirm(self, inter: discord.Interaction, _):
                if inter.user.id != interaction.user.id:
                    await inter.response.send_message("Not your confirmation!", ephemeral=True, delete_after=3)
                    return
                self.stop()
                delete_story(story_id)
                embed = discord.Embed(
                    description=(
                        f"🗑️ {inter.user.mention} **force-deleted** the story **{title}** "
                        f"from the library.\n"
                        f"-# All associated chapters, progress, and badges have been wiped."
                    ),
                    color=discord.Color.dark_red(),
                )
                await inter.response.edit_message(content=None, embed=embed, view=None)

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, inter: discord.Interaction, _):
                if inter.user.id != interaction.user.id:
                    await inter.response.send_message("Not your confirmation!", ephemeral=True, delete_after=3)
                    return
                self.stop()
                await inter.response.edit_message(content="❌ Deletion cancelled.", embed=None, view=None)

        embed = discord.Embed(
            title="⚠️ Confirm Story Deletion",
            description=(
                f"You are about to **permanently delete** the story:\n\n"
                f"📚 **{title}**\n\n"
                f"This will remove all chapters, reading progress, and badges associated with it. "
                f"**This cannot be undone.**"
            ),
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, view=ConfirmDeleteStory(), ephemeral=True)

    # ── /admin delchar ────────────────────────────────────────────────────────

    @admin_group.command(name="delchar", description="[Admin] Force-delete a character")
    @app_commands.describe(character="The character to delete")
    @app_commands.autocomplete(character=_char_autocomplete)
    async def admin_del_char(interaction: discord.Interaction, character: str):
        if not _is_admin(interaction):
            await _deny(interaction)
            return
        if character == HINT:
            await interaction.response.send_message("Keep typing to find the character!", ephemeral=True, delete_after=3)
            return

        from database import get_character_by_id
        from features.characters.service import delete_character
        try:
            character_id = int(character)
        except ValueError:
            await interaction.response.send_message("❌ Invalid selection — please pick from the autocomplete list.", ephemeral=True, delete_after=5)
            return

        char = get_character_by_id(character_id)
        if not char:
            await interaction.response.send_message("❌ Character not found.", ephemeral=True, delete_after=5)
            return

        name        = char.get("name", f"Character #{character_id}")
        story_title = char.get("story_title", "Unknown Story")

        class ConfirmDeleteChar(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30)

            @discord.ui.button(label="🗑 Yes, delete them", style=discord.ButtonStyle.danger)
            async def confirm(self, inter: discord.Interaction, _):
                if inter.user.id != interaction.user.id:
                    await inter.response.send_message("Not your confirmation!", ephemeral=True, delete_after=3)
                    return
                self.stop()
                delete_character(character_id)
                embed = discord.Embed(
                    description=(
                        f"🗑️ {inter.user.mention} **force-deleted** the character **{name}** "
                        f"from *{story_title}*.\n"
                        f"-# All collectors received a respin token as compensation."
                    ),
                    color=discord.Color.dark_red(),
                )
                await inter.response.edit_message(content=None, embed=embed, view=None)

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, inter: discord.Interaction, _):
                if inter.user.id != interaction.user.id:
                    await inter.response.send_message("Not your confirmation!", ephemeral=True, delete_after=3)
                    return
                self.stop()
                await inter.response.edit_message(content="❌ Deletion cancelled.", embed=None, view=None)

        embed = discord.Embed(
            title="⚠️ Confirm Character Deletion",
            description=(
                f"You are about to **permanently delete** the character:\n\n"
                f"🧬 **{name}** from *{story_title}*\n\n"
                f"All CTC collectors will receive a respin token. Favorites, fanart tags, and ships will be cleaned up. "
                f"**This cannot be undone.**"
            ),
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, view=ConfirmDeleteChar(), ephemeral=True)

    # ── /admin delart ─────────────────────────────────────────────────────────

    @admin_group.command(name="delart", description="[Admin] Force-delete a fanart piece")
    @app_commands.describe(fanart="The fanart piece to delete")
    @app_commands.autocomplete(fanart=_fanart_autocomplete)
    async def admin_del_art(interaction: discord.Interaction, fanart: str):
        if not _is_admin(interaction):
            await _deny(interaction)
            return
        if fanart == HINT:
            await interaction.response.send_message("Keep typing to find the fanart!", ephemeral=True, delete_after=3)
            return

        from database import get_fanart_by_id, delete_fanart_full
        try:
            fanart_id = int(fanart)
        except ValueError:
            await interaction.response.send_message("❌ Invalid selection — please pick from the autocomplete list.", ephemeral=True, delete_after=5)
            return

        record = get_fanart_by_id(fanart_id)
        if not record:
            await interaction.response.send_message("❌ Fanart not found.", ephemeral=True, delete_after=5)
            return

        art_title   = record["title"] if "title" in record.keys() else f"Fanart #{fanart_id}"
        artist      = record["username"] if "username" in record.keys() else "Unknown"
        story_title = record["story_title"] if "story_title" in record.keys() else "Unknown"

        class ConfirmDeleteArt(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30)

            @discord.ui.button(label="🗑 Yes, delete it", style=discord.ButtonStyle.danger)
            async def confirm(self, inter: discord.Interaction, _):
                if inter.user.id != interaction.user.id:
                    await inter.response.send_message("Not your confirmation!", ephemeral=True, delete_after=3)
                    return
                self.stop()
                delete_fanart_full(fanart_id)
                embed = discord.Embed(
                    description=(
                        f"🗑️ {inter.user.mention} **force-deleted** the fanart **{art_title}** "
                        f"by *{artist}* for *{story_title}*.\n"
                        f"-# All tags, character links, and comments have been removed."
                    ),
                    color=discord.Color.dark_red(),
                )
                await inter.response.edit_message(content=None, embed=embed, view=None)

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, inter: discord.Interaction, _):
                if inter.user.id != interaction.user.id:
                    await inter.response.send_message("Not your confirmation!", ephemeral=True, delete_after=3)
                    return
                self.stop()
                await inter.response.edit_message(content="❌ Deletion cancelled.", embed=None, view=None)

        embed = discord.Embed(
            title="⚠️ Confirm Fanart Deletion",
            description=(
                f"You are about to **permanently delete** the fanart piece:\n\n"
                f"🎨 **{art_title}** by *{artist}* for *{story_title}*\n\n"
                f"All associated tags, character links, and comments will be removed. "
                f"**This cannot be undone.**"
            ),
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, view=ConfirmDeleteArt(), ephemeral=True)