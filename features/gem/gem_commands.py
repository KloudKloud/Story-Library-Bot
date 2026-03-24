import datetime
import random

import discord
from discord import app_commands

from database import add_user
from ui import TimeoutMixin

CRYSTAL = "💎"

_WALLET_PALETTE = [
    (140, 158, 255), (100, 181, 246), (100, 220, 180), ( 60, 170, 240),
    (210, 100, 255), (255,  80, 200), (160, 120, 255), ( 70, 220, 150),
    (200, 150, 255), (150, 100, 255), (220, 100, 180), ( 80, 200, 230),
    ( 60, 200, 210), (244, 143, 177), (186, 104, 200), ( 90, 200, 100),
]


def register_gem_commands(gem_group: app_commands.Group, guild_id: int):

    # ── /gem daily ────────────────────────────────────────────────────────────

    @gem_group.command(name="daily", description="Claim your daily crystals")
    async def gem_daily(interaction: discord.Interaction):
        import random as _r
        from database import (
            get_user_id, claim_daily, get_balance,
            can_free_roll, get_respin_tokens, get_collection_count,
            DAILY_AMOUNT, DAILY_COOLDOWN, DIRECT_BUY_COST,
        )

        add_user(str(interaction.user.id), interaction.user.name)
        uid = get_user_id(str(interaction.user.id))

        success, msg, new_bal = claim_daily(uid)

        bal                      = get_balance(uid) if not success else new_bal
        free_eligible, free_hrs  = can_free_roll(uid)
        respins                  = get_respin_tokens(uid)
        card_count               = get_collection_count(uid)

        spin_str = "✅ Ready to spin!" if free_eligible else f"⏳ Free spin in **{free_hrs}h**"

        _local_rng = _r.Random(uid)
        r, g, b = _local_rng.choice(_WALLET_PALETTE)
        color   = discord.Color.green() if success else discord.Color.from_rgb(r, g, b)

        div = "── ✦ ──────────────────── ✦ ──"

        if success:
            title = "🎁  Daily Claimed!"
            desc  = (
                f"✨ **+{DAILY_AMOUNT} crystals** added to your wallet!\n"
                f"-# Come back in **{DAILY_COOLDOWN}h** for your next claim.\n"
                f"{div}"
            )
        else:
            title = "⏳  Already Claimed"
            desc  = f"{msg}\n{div}"

        embed = discord.Embed(title=title, description=desc, color=color)
        embed.add_field(name="💰 Balance",       value=f"**{bal:,}** crystals",          inline=True)
        embed.add_field(name="🎲 Free Spin",     value=spin_str,                          inline=True)
        embed.add_field(name="🎟️ Respin Tokens", value=f"**{respins}** banked",           inline=True)
        embed.add_field(name="\u200b",           value=div,                               inline=False)
        embed.add_field(name="🃏 Cards Owned",   value=f"**{card_count}** in collection", inline=True)

        tips = [
            "💡 Spin daily to grow your CTC collection!",
            f"💡 Collect {7} cards to earn a +1,000 💎 milestone bonus!",
            f"💡 Read 10 chapters for a +2,000 💎 chapter milestone!",
            f"💡 Direct buy a card anytime for 💎 {DIRECT_BUY_COST:,} crystals.",
            "💡 Read chapters to earn +250 💎 each!",
            "💡 Chatting earns you 💎 30–40 crystals every ~2 min!",
            "💡 Adding fanart earns +200 💎!",
            "💡 Authors earn +75 💎 every time their character is collected!",
        ]
        embed.set_footer(text=_r.choice(tips))

        await interaction.response.send_message(embed=embed, ephemeral=True, delete_after=30)

    # ── /gem gift ─────────────────────────────────────────────────────────────

    @gem_group.command(name="gift", description="Send crystals to another user (max 500/day)")
    @app_commands.describe(user="Who to send crystals to", amount="How many crystals to send")
    async def gem_gift(interaction: discord.Interaction,
                       user: discord.Member, amount: int):
        from database import get_user_id, spend_credits, add_credits, get_connection

        GIFT_DAILY_CAP = 500

        if user.id == interaction.user.id:
            await interaction.response.send_message("You can't gift yourself!", ephemeral=True, delete_after=5)
            return
        if amount <= 0:
            await interaction.response.send_message("Amount must be positive!", ephemeral=True, delete_after=5)
            return
        if amount > GIFT_DAILY_CAP:
            await interaction.response.send_message(
                f"You can only gift up to {CRYSTAL} **{GIFT_DAILY_CAP}** per day.",
                ephemeral=True, delete_after=5
            )
            return

        add_user(str(interaction.user.id), interaction.user.name)
        add_user(str(user.id), user.name)
        sender_uid = get_user_id(str(interaction.user.id))
        recip_uid  = get_user_id(str(user.id))

        conn  = get_connection()
        cur   = conn.cursor()
        today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        cur.execute("""
            SELECT COALESCE(SUM(ABS(amount)), 0) AS sent_today
            FROM credit_log
            WHERE user_id = ?
              AND reason LIKE 'gift_sent:%'
              AND created_at >= ?
        """, (sender_uid, today))
        sent_today = cur.fetchone()["sent_today"]
        conn.close()

        if sent_today + amount > GIFT_DAILY_CAP:
            remaining = GIFT_DAILY_CAP - sent_today
            await interaction.response.send_message(
                f"You've already gifted {CRYSTAL} **{sent_today}** today. "
                f"You can send {CRYSTAL} **{remaining}** more.",
                ephemeral=True, delete_after=5
            )
            return

        ok, new_bal = spend_credits(sender_uid, amount, f"gift_sent:{recip_uid}")
        if not ok:
            await interaction.response.send_message(
                f"Not enough crystals! You have {CRYSTAL} **{new_bal}**.",
                ephemeral=True, delete_after=5
            )
            return

        add_credits(recip_uid, amount, f"gift_received:{sender_uid}")

        embed = discord.Embed(
            title=f"{CRYSTAL} Crystal Gift!",
            description=(
                f"{interaction.user.mention} sent {CRYSTAL} **{amount:,}** crystals "
                f"to {user.mention}!"
            ),
            color=discord.Color.green()
        )
        embed.set_footer(
            text=f"{interaction.user.display_name}'s remaining balance: {new_bal:,} crystals"
        )
        await interaction.response.send_message(embed=embed)

    # ── /gem rou ──────────────────────────────────────────────────────────────

    @gem_group.command(name="rou", description="Spin Arceus's roulette — pick your wager and bet on an Eeveelution!")
    @app_commands.describe(wager="How much to bet")
    @app_commands.choices(wager=[
        app_commands.Choice(name="200 💎",   value=200),
        app_commands.Choice(name="500 💎",   value=500),
        app_commands.Choice(name="1,000 💎", value=1000),
        app_commands.Choice(name="5,000 💎", value=5000),
    ])
    async def gem_rou(interaction: discord.Interaction, wager: app_commands.Choice[int]):
        from database import get_user_id, spend_credits, get_collection_count, get_shiny_count
        from features.games.games_commands import (
            RouletteView, _pick_embed, _get_roulette_stats,
            EEVEELUTIONS, WILD_CHANCE, _safe_file,
        )

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

    # ── /gem wallet ───────────────────────────────────────────────────────────

    @gem_group.command(name="wallet", description="Your full gem wallet — balance, earnings, chapter progress, and collection stats")
    async def gem_wallet(interaction: discord.Interaction):
        from database import (
            get_balance, get_connection, get_user_id,
            get_collection_count,
            get_showcase_stats, get_reader_badge_count,
            get_chapter_read_count,
            MILESTONE_INTERVAL, MILESTONE_BONUS,
            CHAPTER_MILESTONE_INTERVAL, CHAPTER_MILESTONE_BONUS,
            DAILY_AMOUNT, DAILY_COOLDOWN,
        )

        add_user(str(interaction.user.id), interaction.user.name)
        uid = get_user_id(str(interaction.user.id))
        if not uid:
            await interaction.response.send_message("No account found.", ephemeral=True, delete_after=5)
            return

        # ── Crystal balances ──────────────────────────────────────────────────
        bal = get_balance(uid)

        conn = get_connection()
        cur  = conn.cursor()

        cur.execute(
            "SELECT COALESCE(SUM(amount),0) AS total FROM credit_log "
            "WHERE user_id=? AND amount > 0 AND reason NOT LIKE 'refund:%'",
            (uid,)
        )
        lifetime = cur.fetchone()["total"]

        cur.execute(
            "SELECT COALESCE(SUM(amount),0) AS total FROM credit_log "
            "WHERE user_id=? AND reason = 'activity_chat'",
            (uid,)
        )
        chat_earned = cur.fetchone()["total"]

        cur.execute(
            "SELECT COALESCE(SUM(amount),0) AS total FROM credit_log "
            "WHERE user_id=? AND reason LIKE 'chapter_read:%'",
            (uid,)
        )
        chapter_earned = cur.fetchone()["total"]

        # Daily claim status
        cur.execute("SELECT last_claim FROM daily_claims WHERE user_id=?", (uid,))
        daily_row = cur.fetchone()
        now = datetime.datetime.utcnow()
        if daily_row:
            last      = datetime.datetime.fromisoformat(daily_row["last_claim"])
            diff      = now - last
            remaining = datetime.timedelta(hours=DAILY_COOLDOWN) - diff
            if diff.total_seconds() < DAILY_COOLDOWN * 3600:
                h, rem    = divmod(int(remaining.total_seconds()), 3600)
                m         = rem // 60
                daily_str = f"⏳ {h}h {m}m"
            else:
                daily_str = f"✅ Ready! (+{DAILY_AMOUNT} {CRYSTAL})"
        else:
            daily_str = f"✅ Ready! (+{DAILY_AMOUNT} {CRYSTAL})"

        conn.close()

        # ── Collection ────────────────────────────────────────────────────────
        card_count = get_collection_count(uid)
        try:
            from database import get_all_characters
            total_chars = len(get_all_characters())
        except Exception:
            total_chars = 0

        try:
            conn2     = get_connection()
            shiny_row = conn2.execute(
                "SELECT COUNT(*) AS cnt FROM ctc_collection WHERE user_id=? AND is_shiny=1",
                (uid,)
            ).fetchone()
            conn2.close()
            shiny_count = shiny_row["cnt"] if shiny_row else 0
        except Exception:
            shiny_count = 0

        card_milestones_hit = card_count // MILESTONE_INTERVAL
        cards_to_next_ms    = ((card_count // MILESTONE_INTERVAL) + 1) * MILESTONE_INTERVAL - card_count

        # ── Chapter milestones ────────────────────────────────────────────────
        chapters_read         = get_chapter_read_count(uid)
        chapter_ms_hit        = chapters_read // CHAPTER_MILESTONE_INTERVAL
        chapters_to_next_ms   = ((chapters_read // CHAPTER_MILESTONE_INTERVAL) + 1) * CHAPTER_MILESTONE_INTERVAL - chapters_read

        # ── Author / reader stats ─────────────────────────────────────────────
        stats       = get_showcase_stats(str(interaction.user.id))
        badge_count = get_reader_badge_count(str(interaction.user.id))

        # ── Active hunt ───────────────────────────────────────────────────────
        from database import (
            get_hunt as _get_hunt_w,
            hunt_chain_shiny_rate as _hcr_w,
            hunt_chain_tier as _hct_w,
            HUNT_CHAIN_THRESHOLDS as _hcthresh_w,
        )
        hunt_info = _get_hunt_w(uid)

        # ── Color ─────────────────────────────────────────────────────────────
        _local_rng = random.Random(uid)
        r, g, b    = _local_rng.choice(_WALLET_PALETTE)
        color      = discord.Color.from_rgb(r, g, b)

        sep = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

        embed = discord.Embed(
            title=f"{CRYSTAL}  {interaction.user.display_name}'s Gem Wallet",
            description=(
                f"*Your full economy overview — crystals, milestones, collection, and more.*\n"
                f"-# {CRYSTAL} Gems are the server's universal currency — more ways to spend them coming soon!\n"
                f"{sep}"
            ),
            color=color,
        )
        # Section 1 — Balance & Daily
        embed.add_field(name="💰 Balance",         value=f"**{bal:,}** {CRYSTAL}",       inline=True)
        embed.add_field(name="📈 Lifetime Earned",  value=f"**{lifetime:,}** {CRYSTAL}",  inline=True)
        embed.add_field(name="🎁 Daily Claim",      value=daily_str,                       inline=True)

        # Section 2 — Earning Breakdown
        embed.add_field(name=sep, value=(
            f"💬 **Chat passive** — **{chat_earned:,}** {CRYSTAL} earned so far\n"
            f"📖 **Chapter reads** — **{chapter_earned:,}** {CRYSTAL} earned so far\n"
            f"-# +250 {CRYSTAL} per chapter · +2,000 {CRYSTAL} every 10 chapters read"
        ), inline=False)

        # Section 3 — Chapter Milestones
        embed.add_field(
            name="📖 Chapters Read",
            value=(
                f"**{chapters_read}** read  ·  **{chapter_ms_hit}** milestone{'s' if chapter_ms_hit != 1 else ''} hit\n"
                f"-# Next +{CHAPTER_MILESTONE_BONUS:,} {CRYSTAL} in **{chapters_to_next_ms}** more chapter{'s' if chapters_to_next_ms != 1 else ''}"
            ),
            inline=True,
        )
        embed.add_field(
            name="🃏 Cards Collected",
            value=(
                f"**{card_count}** / {total_chars}  ·  **{card_milestones_hit}** milestone{'s' if card_milestones_hit != 1 else ''} hit\n"
                f"-# Next +{MILESTONE_BONUS:,} {CRYSTAL} in **{cards_to_next_ms}** more card{'s' if cards_to_next_ms != 1 else ''}"
            ),
            inline=True,
        )
        embed.add_field(
            name="✨ Shiny Cards",
            value=f"**{shiny_count}** shiny" if shiny_count else "*None yet*",
            inline=True,
        )

        # Section 4 — Active Hunt
        if hunt_info:
            _chain    = hunt_info["hunt_chain"]
            _tier     = _hct_w(_chain)
            _rate_n   = _hcr_w(_chain, premium=False)
            _rate_p   = _hcr_w(_chain, premium=True)
            _next_t   = next((t for t in _hcthresh_w if t > _chain), None)
            _next_str = f"next tier at **{_next_t}** claims" if _next_t else "**MAX CHAIN!**"
            _rate_n_str = f"{_rate_n * 100:.2f}".rstrip("0").rstrip(".") + "%"
            _rate_p_str = f"{_rate_p * 100:.2f}".rstrip("0").rstrip(".") + "%"

            try:
                conn3     = get_connection()
                sh        = conn3.execute(
                    "SELECT is_shiny FROM ctc_collection WHERE user_id=? AND character_id=?",
                    (uid, hunt_info["id"])
                ).fetchone()
                conn3.close()
                hunt_status = "✨ You own the shiny!" if (sh and sh["is_shiny"]) else "Hunting for shiny..."
            except Exception:
                hunt_status = "Hunting for shiny..."

            embed.add_field(
                name  = f"{sep}\n🎯 Active Shiny Hunt",
                value = (
                    f"**{hunt_info['name']}**  ·  {hunt_status}\n"
                    f"-# Chain: **{_chain}**  ·  Tier **{_tier + 1}**/5  ·  {_next_str}\n"
                    f"-# Shiny chance: **{_rate_n_str}** normal  ·  **{_rate_p_str}** premium  ·  2× spawn boost"
                ),
                inline = False,
            )

        # Section 5 — Library & Author stats
        embed.add_field(name=f"{sep}\n📚 Stories Added",   value=f"**{stats['stories']}**",   inline=True)
        embed.add_field(name="🧬 Characters Added", value=f"**{stats['characters']}**", inline=True)
        embed.add_field(name="🏅 Reader Badges",   value=f"**{badge_count}**",         inline=True)

        embed.set_footer(text=(
            "💎 Earn gems by: chatting · reading chapters · adding to the library · "
            "daily claims · card & chapter milestones · author passives"
        ))

        await interaction.response.send_message(embed=embed)
