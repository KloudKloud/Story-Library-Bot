"""
features/pvp/pvp_commands.py
Discord /pvp command group — challenge a player, check server status.

Requires the PVP server (pvp/server.py) to be running separately.
Set PVP_INTERNAL_URL and PVP_PUBLIC_URL in your .env.
"""

import os
import aiohttp
import discord
from discord import app_commands

PVP_INTERNAL_URL = os.getenv("PVP_INTERNAL_URL", "http://localhost:5051")

# Element colour to use on embeds (purple = no single element wins)
EMBED_COLOR = 0x7c3aed

EL_BLURB = (
    "🔥 **Fire** — heavy damage & burn\n"
    "❄️ **Ice** — shields, freeze & control\n"
    "⚡ **Lightning** — draw power & stuns"
)


def register_pvp_commands(group: app_commands.Group, guild_id: int):

    # ── /pvp challenge ────────────────────────────────────────────────────────
    @group.command(
        name="challenge",
        description="Challenge another player to an Elemental PVP card battle!",
    )
    @app_commands.describe(opponent="The player you want to duel")
    async def pvp_challenge(interaction: discord.Interaction, opponent: discord.Member):
        if opponent.bot:
            await interaction.response.send_message(
                "You can't challenge a bot to a card duel!", ephemeral=True
            )
            return
        if opponent.id == interaction.user.id:
            await interaction.response.send_message(
                "You can't challenge yourself!", ephemeral=True
            )
            return

        await interaction.response.defer()

        p1 = interaction.user.display_name
        p2 = opponent.display_name

        # Ask the PVP server to create a session
        try:
            async with aiohttp.ClientSession() as http:
                async with http.post(
                    f"{PVP_INTERNAL_URL}/api/create_session",
                    json={"p1_name": p1, "p2_name": p2},
                    timeout=aiohttp.ClientTimeout(total=6),
                ) as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"Server returned HTTP {resp.status}")
                    data = await resp.json()
        except Exception as exc:
            embed = discord.Embed(
                title="⚠️  PVP Server Offline",
                description=(
                    "The PVP battle server isn't running right now.\n\n"
                    "A server admin needs to start it:\n"
                    "```\npython pvp/server.py\n```"
                ),
                color=0x992222,
            )
            await interaction.followup.send(embed=embed)
            return

        game_url   = data["url"]
        session_id = data["session_id"]

        # ── Build the fancy embed ─────────────────────────────────────────────
        embed = discord.Embed(
            title="⚔️  Elemental PVP — Battle Invitation",
            description=(
                f"{interaction.user.mention} has challenged {opponent.mention} "
                f"to an **Elemental card battle!**\n\n"
                f"Both players open the link below. Take turns on the same screen "
                f"and pass after each turn — or share your screen for a remote duel."
            ),
            color=EMBED_COLOR,
        )

        embed.add_field(name="⚔️  Challenger",  value=interaction.user.mention, inline=True)
        embed.add_field(name="🛡️  Defender",    value=opponent.mention,         inline=True)
        embed.add_field(name="\u200b",           value="\u200b",                 inline=True)

        embed.add_field(
            name="🎮  How to Play",
            value=(
                "1. Click **Open Battle** below\n"
                "2. Choose your elemental affinity (70 % pull)\n"
                "3. Pick your character card\n"
                "4. Battle! Pass the screen after each turn."
            ),
            inline=False,
        )

        embed.add_field(name="⚡  Elements", value=EL_BLURB, inline=False)

        embed.set_footer(
            text=f"Session expires after 2 h of inactivity  •  ID: {session_id}"
        )

        # URL button — Discord renders this as a proper link button
        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label="  Open Battle",
            url=game_url,
            style=discord.ButtonStyle.link,
            emoji="⚔️",
        ))

        await interaction.followup.send(
            content=f"⚔️  **{p1}** vs **{p2}** — may the best spellcaster win!",
            embed=embed,
            view=view,
        )

    # ── /pvp status ───────────────────────────────────────────────────────────
    @group.command(
        name="status",
        description="Check whether the PVP battle server is online.",
    )
    async def pvp_status(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            async with aiohttp.ClientSession() as http:
                async with http.get(
                    f"{PVP_INTERNAL_URL}/api/status",
                    timeout=aiohttp.ClientTimeout(total=4),
                ) as resp:
                    data = await resp.json()
            embed = discord.Embed(
                title="✅  PVP Server Online",
                description=(
                    f"**{data['active_sessions']}** active battle session(s) running.\n\n"
                    f"Use `/pvp challenge @player` to start a new battle."
                ),
                color=0x2ecc71,
            )
        except Exception:
            embed = discord.Embed(
                title="❌  PVP Server Offline",
                description=(
                    "The PVP server is not responding.\n\n"
                    "Start it with:\n```\npython pvp/server.py\n```"
                ),
                color=0xe74c3c,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)
