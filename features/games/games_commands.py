import discord
from discord import app_commands, ui
import random
import asyncio
import os

from database import (
    get_user_id, add_user, get_balance, add_credits, spend_credits,
    get_connection, get_collection_count, get_shiny_count,
)
from ui import TimeoutMixin

# ─────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────

WAGER_CHOICES = [200, 500, 1000, 5000]
MAX_FILE_BYTES = 8 * 1024 * 1024  # 8 MB — Discord free-tier limit

EEVEELUTIONS = ["Umbreon", "Glaceon", "Espeon", "Sylveon", "Vaporeon", "Leafeon", "Flareon", "Jolteon"]
WILD_CHANCE  = 0.10

_IMG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "images")

def _img(name: str) -> str:
    return os.path.join(_IMG_DIR, f"{name.lower()}.gif")

def _safe_file(name: str) -> discord.File | None:
    """Return a discord.File only if the gif exists and is under 8 MB."""
    path = _img(name)
    if not os.path.exists(path):
        return None
    if os.path.getsize(path) > MAX_FILE_BYTES:
        return None
    return discord.File(path, filename=f"{name.lower()}.gif")

EEVEE_COLOR  = discord.Color.gold()
RIOLU_COLOR  = discord.Color.gold()
NORMAL_COLOR = discord.Color.from_rgb(120, 75, 210)   # vibrant purple for pick screen
WIN_COLOR    = discord.Color.from_rgb(30, 144, 255)    # bright dodger blue
LOSS_COLOR   = discord.Color.from_rgb(220, 20, 60)     # bright crimson red

WIN_BORDER  = "🎊  🎉  ✨  🎊  🎉  ✨  🎊  🎉  ✨  🎊"
LOSS_BORDER = "💀  ☠️   💀  ☠️   💀  ☠️   💀  ☠️   💀"
_LINE_SEP   = "── ✦ ──────────────────── ✦ ──"

# ─────────────────────────────────────────────────
# Splash text
# ─────────────────────────────────────────────────

PICK_SPLASHES = [
    '"I\'m either gonna catch \'em all or... well... nothing."',
    '"Even Professor Oak doesn\'t know what\'s about to happen."',
    '"A Pokémon trainer never quits. A Pokémon gambler probably should."',
    '"No Repel can protect you from this."',
    '"Arceus has no favorites. Your wallet might."',
    '"Some days you\'re the Magikarp. Some days you\'re the Gyarados."',
    '"Team Rocket would call this a calculated risk."',
    '"This is definitely not in the Pokédex."',
    '"Ash never checked his wallet either."',
    '"Even Gary Oak is sweating right now."',
    '"The real treasure was the crystals we lost along the way."',
    '"I used to have more money. Then I found this command."',
]

WIN_SPLASHES = [
    "Arceus smiles upon you today.",
    "Even Lance couldn't have predicted this.",
    "The Elite Four has nothing on you.",
    "You magnificent Trainer.",
    "Your Pokédex just gained a new entry: **Luck**.",
    "Team Rocket blasted off. Your balance didn't.",
    "Professor Oak is *moderately* impressed.",
    "A shiny outcome. How rare.",
    "You're basically the Champion at this point.",
    "Not even Mewtwo saw that coming.",
]

LOSS_SPLASHES = [
    "...You blacked out.",
    "A wild LOSS appeared! It was super effective.",
    "Your rival would not have made this bet.",
    "Team Rocket is laughing somewhere.",
    "This is why Ash kept losing gym badges.",
    "Even Magikarp is judging you right now.",
    "The Pokédex has no data on this kind of pain.",
    "Professor Oak is deeply disappointed.",
    "You have been defeated. Please heal at the Pokémon Center.",
    "Your mom called. She said to come home.",
]

# ─────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────

def _get_roulette_stats(user_id: int) -> dict:
    """Returns spins, wins, and losses for a user from the credit_log."""
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM credit_log WHERE user_id = ? AND reason = 'game:roulette_wager'",
        (user_id,)
    )
    spins = cursor.fetchone()["cnt"]
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM credit_log WHERE user_id = ? AND reason = 'game:roulette_win'",
        (user_id,)
    )
    wins = cursor.fetchone()["cnt"]
    conn.close()
    return {"spins": spins, "wins": wins, "losses": max(0, spins - wins)}


def _gambler_rank(wins: int) -> str:
    if wins == 0:   return "🌱 First Time?"
    if wins <= 3:   return "🎲 Lucky Rookie"
    if wins <= 10:  return "🃏 Seasoned Trainer"
    if wins <= 25:  return "🎰 High Roller"
    if wins <= 50:  return "💀 Reckless"
    return "👑 Arceus's Chosen"


# ─────────────────────────────────────────────────
# Embed builders
# ─────────────────────────────────────────────────

def _pick_embed(
    wager: int,
    balance: int,
    player_name: str,
    choice_a: str,
    choice_b: str,
    wildcard: str | None,
    stats: dict,
    cards: int,
    shinies: int,
) -> discord.Embed:

    splash = random.choice(PICK_SPLASHES)
    rank   = _gambler_rank(stats["wins"])

    if wildcard == "Eevee":
        color = EEVEE_COLOR
        title = "🎰  Eevee's Roulette  ·  ⚠️ Wild Card!"
        wild_info = (
            "\n\n**⚠️ Eevee Wild Card Rules:**\n"
            "> 🟢 Win → earnings **×1.5**\n"
            "> 🔴 Lose → lose **double** your wager"
        )
    elif wildcard == "Riolu":
        color = RIOLU_COLOR
        title = "🎰  Riolu's Roulette  ·  ⚠️ Wild Card!"
        wild_info = (
            "\n\n**⚠️ Riolu Wild Card Rules:**\n"
            "> 🟢 Win → **triple** your wager\n"
            "> 🎲 Odds → only **30%** chance to win"
        )
    else:
        color     = NORMAL_COLOR
        title     = "🎰  Arceus's Roulette"
        wild_info = ""

    win_rate = f"{round(stats['wins'] / stats['spins'] * 100)}%" if stats["spins"] > 0 else "—"

    embed = discord.Embed(
        title=title,
        description=f"-# {splash}{wild_info}",
        color=color,
    )

    # ── Player info row ───────────────────────────
    embed.add_field(name="👤  Player",      value=player_name,       inline=True)
    embed.add_field(name="🏅  Rank",        value=rank,              inline=True)
    embed.add_field(name="👜  Balance",     value=f"{balance:,} 💎", inline=True)

    # ── Wager row ─────────────────────────────────
    embed.add_field(name="💰  Wager",       value=f"{wager:,} 💎",   inline=True)
    embed.add_field(name="📈  Win Rate",    value=win_rate,          inline=True)
    embed.add_field(name="\u200b",          value="\u200b",          inline=True)

    # ── Stats row ─────────────────────────────────
    embed.add_field(name="🎲  Spins",       value=str(stats["spins"]),   inline=True)
    embed.add_field(name="🏆  Wins",        value=str(stats["wins"]),    inline=True)
    embed.add_field(name="💀  Losses",      value=str(stats["losses"]),  inline=True)

    # ── Card collection row ───────────────────────
    embed.add_field(name="🃏  Cards",       value=str(cards),            inline=True)
    embed.add_field(name="✨  Shinies",     value=str(shinies),          inline=True)
    embed.add_field(name="\u200b",          value="\u200b",              inline=True)

    # ── Choice ────────────────────────────────────
    embed.add_field(
        name="🃏  Pick Your Champion",
        value=f"**{choice_a}**  ✦  **{choice_b}**",
        inline=False,
    )
    embed.set_footer(text="Times out in 3 minutes · Arceus is watching.")
    return embed


def _spinning_embed(picked: str) -> discord.Embed:
    return discord.Embed(
        title="🌀  The Wheel is Spinning...",
        description=f"You picked **{picked}**. Arceus consults the cosmos...",
        color=NORMAL_COLOR,
    )


def _result_embed(
    result_mon: str,
    player_name: str,
    player_choice: str,
    won: bool,
    new_balance: int,
    wager: int,
    wildcard: str | None,
    chickened: bool = False,
    timeout: bool = False,
) -> discord.Embed:

    if chickened:
        color   = discord.Color.greyple()
        title   = "🐔  Roulette  ·  Chickened Out"
        outcome = f"*{player_name} was too scared to continue...*"
        splash  = ""
    elif timeout:
        color   = discord.Color.dark_gray()
        title   = "⏰  Roulette  ·  Timed Out"
        outcome = f"The wheel never spun. **{wager:,} 💎** lost to the void."
        splash  = ""
    elif won:
        color  = WIN_COLOR
        title  = "🎰  Roulette  ·  You Won! 🎉"
        splash = random.choice(WIN_SPLASHES)
        if wildcard == "Riolu":
            profit  = wager * 3
            outcome = f"Arceus has chosen **{result_mon}**. You won **triple** your wager!\n**+{profit:,} 💎**  _(wagered {wager:,} → received {wager + profit:,})_"
        elif wildcard == "Eevee":
            profit  = int(wager * 1.5)
            outcome = f"Arceus has chosen **{result_mon}**. You won **×1.5** your wager!\n**+{profit:,} 💎**  _(wagered {wager:,} → received {wager + profit:,})_"
        else:
            outcome = f"Arceus has chosen **{result_mon}**. You **won**!\n**+{wager:,} 💎**  _(wagered {wager:,} → received {wager * 2:,})_"
        border = WIN_BORDER
    else:
        color  = LOSS_COLOR
        title  = "🎰  Roulette  ·  You Lost"
        splash = random.choice(LOSS_SPLASHES)
        if wildcard == "Eevee":
            outcome = (
                f"Arceus has chosen **{result_mon}**. You lost...\n"
                f"☠️  The Eevee curse activates — you lose **double** your wager.\n"
                f"**Total lost: {wager * 2:,} 💎**"
            )
        else:
            outcome = f"Arceus has chosen **{result_mon}**. You lost..."
        border = LOSS_BORDER

    if chickened or timeout:
        desc = outcome
        if splash:
            desc += f"\n-# {splash}"
    else:
        desc = (
            f"{border}\n"
            f"{_LINE_SEP}\n"
            f"{outcome}\n\n"
            f"*{splash}*\n\n"
            f"{_LINE_SEP}"
        )

    embed = discord.Embed(title=title, description=desc, color=color)

    embed.add_field(name="👤  Player",      value=player_name,          inline=True)
    embed.add_field(name="💰  Wagered",     value=f"{wager:,} 💎",      inline=True)
    embed.add_field(name="👜  New Balance", value=f"{new_balance:,} 💎", inline=True)

    if not chickened and not timeout:
        embed.add_field(name="🎯  Your Pick", value=player_choice, inline=True)
        embed.add_field(name="🌀  Landed On", value=result_mon,    inline=True)

    embed.set_footer(text="Thanks for playing Arceus's Roulette!")
    return embed


# ─────────────────────────────────────────────────
# Roulette View
# ─────────────────────────────────────────────────

class RouletteView(TimeoutMixin, ui.View):

    TIMEOUT_SECONDS = 180

    def __init__(
        self,
        user_id: int,
        discord_user: discord.Member | discord.User,
        wager: int,
        choice_a: str,
        choice_b: str,
        wildcard: str | None,
    ):
        super().__init__(timeout=self.TIMEOUT_SECONDS)
        self.db_user_id   = user_id
        self.discord_user = discord_user
        self.wager        = wager
        self.choice_a     = choice_a
        self.choice_b     = choice_b
        self.wildcard     = wildcard
        self.message: discord.Message | None = None
        self._done = False

        btn_a = ui.Button(label=choice_a, emoji="✅", style=discord.ButtonStyle.success, row=0)
        btn_a.callback = self._make_pick_callback(choice_a)
        self.add_item(btn_a)

        btn_b = ui.Button(label=choice_b, emoji="💎", style=discord.ButtonStyle.primary, row=0)
        btn_b.callback = self._make_pick_callback(choice_b)
        self.add_item(btn_b)

        if wildcard:
            chicken_btn = ui.Button(label="🐔 Chicken", style=discord.ButtonStyle.danger, row=0)
            chicken_btn.callback = self._chicken
            self.add_item(chicken_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.discord_user.id:
            await interaction.response.send_message(
                "❌ This isn't your roulette session.", ephemeral=True, delete_after=5
            )
            return False
        return True

    def _make_pick_callback(self, picked: str):
        async def _callback(interaction: discord.Interaction):
            if self._done:
                return
            self._done = True
            self.stop()
            await self._resolve(interaction, picked)
        return _callback

    async def _chicken(self, interaction: discord.Interaction):
        if self._done:
            return
        self._done = True
        self.stop()

        # Remove buttons immediately, show brief transition
        await interaction.response.edit_message(
            embed=discord.Embed(title="🐔  Chickening out...", color=discord.Color.greyple()),
            view=None,
            attachments=[],
        )

        new_bal      = get_balance(self.db_user_id)
        display_name = getattr(self.discord_user, "display_name", None) or self.discord_user.name

        embed = _result_embed(
            result_mon="—",
            player_name=display_name,
            player_choice="—",
            won=False,
            new_balance=new_bal,
            wager=self.wager,
            wildcard=self.wildcard,
            chickened=True,
        )

        files = []
        if self.wildcard:
            f = _safe_file(self.wildcard)
            if f:
                files.append(f)
                embed.set_thumbnail(url=f"attachment://{self.wildcard.lower()}.gif")
        else:
            df = _safe_file("default")
            if df:
                files.append(df)
                embed.set_thumbnail(url="attachment://default.gif")

        # Delete the transition message, send result fresh (guarantees file upload works)
        try:
            await self.message.delete()
        except Exception:
            pass
        await interaction.followup.send(embed=embed, files=files)

    async def _resolve(self, interaction: discord.Interaction, picked: str):
        # Step 1 — immediate visual feedback: remove buttons, show spinning state
        await interaction.response.edit_message(
            embed=_spinning_embed(picked),
            view=None,
            attachments=[],
        )

        await asyncio.sleep(1.5)

        # Step 2 — spin the wheel
        other = self.choice_b if picked == self.choice_a else self.choice_a

        if self.wildcard == "Riolu":
            # Riolu: 30% pure chance — wheel result follows the outcome so they're consistent
            won        = random.random() < 0.30
            result_mon = picked if won else other
        else:
            # Normal / Eevee: wheel is a true 50/50, win if it matches the pick
            result_mon = random.choice([self.choice_a, self.choice_b])
            won        = (result_mon == picked)

        # Step 3 — calculate payout
        if won:
            if self.wildcard == "Eevee":
                profit = int(self.wager * 1.5)
            elif self.wildcard == "Riolu":
                profit = self.wager * 3
            else:
                profit = self.wager
            new_bal = add_credits(self.db_user_id, profit, "game:roulette_win")
        else:
            if self.wildcard == "Eevee":
                new_bal = add_credits(self.db_user_id, -self.wager, "game:roulette_eevee_double_loss")
            else:
                new_bal = get_balance(self.db_user_id)

        display_name = getattr(self.discord_user, "display_name", None) or self.discord_user.name

        embed = _result_embed(
            result_mon=result_mon,
            player_name=display_name,
            player_choice=picked,
            won=won,
            new_balance=new_bal,
            wager=self.wager,
            wildcard=self.wildcard,
        )

        # Step 4 — build file attachments
        files = []

        mon_file = _safe_file(result_mon)
        if mon_file:
            files.append(mon_file)
            embed.set_image(url=f"attachment://{result_mon.lower()}.gif")

        if self.wildcard:
            wc_file = _safe_file(self.wildcard)
            if wc_file:
                files.append(wc_file)
                embed.set_thumbnail(url=f"attachment://{self.wildcard.lower()}.gif")
        else:
            df = _safe_file("default")
            if df:
                files.append(df)
                embed.set_thumbnail(url="attachment://default.gif")

        # Delete the spinning message, send result fresh so files upload correctly
        try:
            await self.message.delete()
        except Exception:
            pass
        await interaction.followup.send(embed=embed, files=files)

    async def on_timeout(self):
        if self._done:
            return
        self._done = True

        new_bal      = get_balance(self.db_user_id)
        display_name = getattr(self.discord_user, "display_name", None) or self.discord_user.name

        embed = _result_embed(
            result_mon="—",
            player_name=display_name,
            player_choice="—",
            won=False,
            new_balance=new_bal,
            wager=self.wager,
            wildcard=self.wildcard,
            timeout=True,
        )
        if self.message:
            try:
                await self.message.edit(embed=embed, view=None)
            except Exception:
                pass


# ─────────────────────────────────────────────────
# Command registration
# ─────────────────────────────────────────────────

def register_game_commands(gam_group: app_commands.Group, guild_id: int):
    pass


def _legacy_rou(gam_group: app_commands.Group):
    @gam_group.command(name="rou", description="Spin Arceus's roulette — pick your wager and bet on an Eeveelution!")
    @app_commands.describe(wager="How much to bet")
    @app_commands.choices(wager=[
        app_commands.Choice(name="200 💎",   value=200),
        app_commands.Choice(name="500 💎",   value=500),
        app_commands.Choice(name="1,000 💎", value=1000),
        app_commands.Choice(name="5,000 💎", value=5000),
    ])
    async def gam_rou(interaction: discord.Interaction, wager: app_commands.Choice[int]):
        add_user(str(interaction.user.id), interaction.user.name)
        uid = get_user_id(str(interaction.user.id))

        actual_wager = wager.value
        success, balance = spend_credits(uid, actual_wager, "game:roulette_wager")
        if not success:
            await interaction.response.send_message(
                f"❌ You don't have enough crystals. Balance: **{balance:,} 💎**",
                ephemeral=True, delete_after=8
            )
            return

        choice_a, choice_b = random.sample(EEVEELUTIONS, 2)

        wildcard: str | None = None
        if random.random() < WILD_CHANCE:
            wildcard = random.choice(["Eevee", "Riolu"])

        player_name = getattr(interaction.user, "display_name", None) or interaction.user.name
        stats       = _get_roulette_stats(uid)
        cards       = get_collection_count(uid)
        shinies     = get_shiny_count(uid)

        embed = _pick_embed(
            wager=actual_wager,
            balance=balance,
            player_name=player_name,
            choice_a=choice_a,
            choice_b=choice_b,
            wildcard=wildcard,
            stats=stats,
            cards=cards,
            shinies=shinies,
        )
        view = RouletteView(
            user_id=uid,
            discord_user=interaction.user,
            wager=actual_wager,
            choice_a=choice_a,
            choice_b=choice_b,
            wildcard=wildcard,
        )

        files = []
        if wildcard:
            f = _safe_file(wildcard)
            if f:
                files.append(f)
                embed.set_thumbnail(url=f"attachment://{wildcard.lower()}.gif")
        else:
            df = _safe_file("default")
            if df:
                files.append(df)
                embed.set_thumbnail(url="attachment://default.gif")

        await interaction.response.send_message(embed=embed, view=view, files=files)
        view.message = await interaction.original_response()
