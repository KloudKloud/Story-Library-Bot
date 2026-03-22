import discord
from discord import app_commands, ui
import random
import asyncio
import datetime

from embeds.ctc_card_embed import build_ctc_card_embed, CTCCardView
from database import add_user

# ── Currency symbol used everywhere ───────────────
CRYSTAL = "💎"

# ─────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────

def _user_db_id(discord_id: int):
    from database import get_user_id
    return get_user_id(str(discord_id))


def _fmt_balance(bal: int) -> str:
    return f"{CRYSTAL} **{bal:,}** crystals"


def _gid_by_char(character_id: int):
    """Returns the DB user_id of the author of a character."""
    from database import get_connection
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("SELECT c.user_id FROM characters c WHERE c.id = ?", (character_id,))
    row = cur.fetchone()
    conn.close()
    return row["user_id"] if row else None


# ─────────────────────────────────────────────────
# Shared card-display embed (CTC flavour)
# ─────────────────────────────────────────────────

# ─────────────────────────────────────────────────
# Spin — card preview before claiming
# ─────────────────────────────────────────────────

class SpinCardPreviewView(CTCCardView):
    """
    Shows a full CTC card embed for one of the two rolled cards.
    Row 0: Behind the Scenes dropdown (from CTCCardView)
    Row 1: ✅ Claim [Name]  |  ↩️ Return
    """

    def __init__(
        self,
        card:         dict,
        viewer:       discord.Member,
        pick_view:    "SpinPickView",
        card_idx:     int,
    ):
        super().__init__(
            cards      = [card],
            viewer_uid = viewer.id,
            viewer     = viewer,
            timeout    = 300,
        )
        self.card      = card
        self.viewer    = viewer
        self.pick_view = pick_view
        self.card_idx  = card_idx
        self._message  = None   # set after send so on_timeout can edit it
        self._add_claim_buttons()

    def _add_claim_buttons(self):
        name = self.card.get("name", "this card")

        claim_btn = ui.Button(
            label  = f"✅ Claim {name}",
            style  = discord.ButtonStyle.success,
            row    = 1,
        )
        claim_btn.callback = self._claim
        self.add_item(claim_btn)

        ret_btn = ui.Button(
            label  = "↩️ Return",
            style  = discord.ButtonStyle.primary,
            row    = 1,
        )
        ret_btn.callback = self._return
        self.add_item(ret_btn)

    def _rebuild_shop_buttons(self):
        """Called by _full_refresh — re-adds claim/return after Behind the Scenes returns."""
        self.clear_items()
        self._refresh()
        self._add_claim_buttons()

    async def on_timeout(self):
        """If the preview times out, silently return to the browse embed."""
        if self._message:
            try:
                self.pick_view._rebuild_pick_buttons()
                await self._message.edit(
                    content=None,
                    embed=self.pick_view.browse_embed,
                    view=self.pick_view,
                )
            except Exception:
                pass

    async def _claim(self, interaction: discord.Interaction):
        if self.pick_view.chosen:
            await interaction.response.send_message("You already claimed a card!", ephemeral=True, delete_after=5)
            return

        self.pick_view.chosen = True
        self.pick_view.stop()
        self.stop()

        from database import (
            add_to_collection, grant_shiny, get_user_id,
            grant_author_passive, check_and_grant_milestones,
            get_character_by_id, add_credits, DUPLICATE_REFUND,
            user_owns_card,
        )

        card     = self.card
        uid      = get_user_id(str(interaction.user.id))
        via      = "free_roll" if self.pick_view.free else "roll"
        is_shiny = bool(card.get("is_shiny"))
        is_dupe  = bool(card.get("is_dupe"))
        is_fav   = bool(card.get("is_fav"))

        extra_lines = []

        if is_shiny:
            # Grant normal card first if they don't have it
            if not user_owns_card(uid, card["id"]):
                add_to_collection(uid, card["id"], via=via)
                extra_lines.append("📋 Normal card also added to your collection!")
            had_normal = grant_shiny(uid, card["id"], via=via)
            if had_normal:
                extra_lines.append("✨ **Your card was upgraded to SHINY!**")
            else:
                extra_lines.append("✨ **Shiny card added to your collection!**")
        elif is_dupe:
            add_credits(uid, DUPLICATE_REFUND, "dupe_refund")
            extra_lines.append(
                f"You already own **{card['name']}**. "
                f"Here's {CRYSTAL} **{DUPLICATE_REFUND}** as a consolation!"
            )
        else:
            add_to_collection(uid, card["id"], via=via)

        # Author passive & milestones
        if not is_dupe:
            full_char = get_character_by_id(card["id"])
            if full_char:
                author_uid_row = _gid_by_char(card["id"])
                if author_uid_row and author_uid_row != uid:
                    grant_author_passive(author_uid_row, card["id"], uid)
            new_milestones = check_and_grant_milestones(uid)
            if new_milestones:
                ms = new_milestones[-1]
                extra_lines.append(f"{CRYSTAL} **Milestone!** {ms} cards collected → **+500 crystals!**")

        if is_fav and not is_shiny:
            extra_lines.append(f"⭐ *{card['name']} is one of your favourites!*")

        congrats = (
            f"{'✨ Shiny claimed!' if is_shiny else '🎉 Congratulations!'} "
            f"**{card['name']}** has been added to your collection!"
        )
        if extra_lines:
            congrats += "\n" + "\n".join(f"-# {l}" for l in extra_lines)

        # Disable all buttons on the pick view browse embed
        self.pick_view._disable_all()

        # ── Replace the spin embed with the congratulations message ──────────
        if is_shiny:
            title = "✨ ★  SHINY CLAIMED  ★ ✨"
            desc  = (
                f"⋆｡‧˚ʚ ✨ ɞ˚‧｡⋆  **✦ SHINY CARD ✦**  ⋆｡‧˚ʚ ✨ ɞ˚‧｡⋆\n\n"
                + congrats
            )
            color = discord.Color.gold()
        else:
            title = "🎉 Card Claimed!"
            desc  = congrats
            color = discord.Color.green()

        # Pull the card image for a nice thumbnail
        card_image = card.get("image_url")
        congrats_embed = discord.Embed(title=title, description=desc, color=color)
        if card_image and card_image.startswith("http"):
            congrats_embed.set_thumbnail(url=card_image)

        await interaction.response.edit_message(content=None, embed=congrats_embed, view=None)

    async def _return(self, interaction: discord.Interaction):
        # Rebuild pick view browse embed and go back
        self.pick_view._rebuild_pick_buttons()
        await interaction.response.edit_message(
            content=None,
            embed=self.pick_view.browse_embed,
            view=self.pick_view,
        )


# ─────────────────────────────────────────────────
# Spin result view — browse two rolled cards
# ─────────────────────────────────────────────────

class SpinPickView(ui.View):
    """
    Shown after a roll — sparkly browse embed with two card buttons.
    Clicking a button opens SpinCardPreviewView (full card) instead of
    instantly claiming.

    roll_type: "free" | "respin" | "paid"
    """

    def __init__(
        self,
        cards:        list,
        roller_uid:   int,
        free:         bool,
        browse_embed: discord.Embed,
        roll_type:    str = "free",
        roller_db_id: int = None,
    ):
        super().__init__(timeout=300)
        self.cards         = cards
        self.roller_uid    = roller_uid
        self.free          = free
        self.browse_embed  = browse_embed
        self.roll_type     = roll_type   # "free" | "respin" | "paid"
        self.roller_db_id  = roller_db_id
        self.chosen        = False
        self._message      = None        # set after send so on_timeout can edit it
        self._rebuild_pick_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.roller_uid:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    def _rebuild_pick_buttons(self):
        self.clear_items()
        for i, card in enumerate(self.cards):
            if card.get("is_shiny"):
                emoji = "✨"
                style = discord.ButtonStyle.success
            elif card.get("is_fav"):
                emoji = "⭐"
                style = discord.ButtonStyle.primary
            else:
                emoji = "💎"
                style = discord.ButtonStyle.primary

            btn = ui.Button(
                label     = card.get("name", f"Card {i+1}"),
                style     = style,
                emoji     = emoji,
                row       = 0,
                custom_id = f"spin_pick_{i}",
            )
            btn.callback = self._make_preview_callback(i)
            self.add_item(btn)

    def _disable_all(self):
        """Disable all buttons — called after claim or timeout."""
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True

    async def on_timeout(self):
        """Time's up — disable the browse embed. No refund is issued."""
        if self.chosen:
            return   # already claimed, nothing to do

        self._disable_all()
        if self._message:
            try:
                await self._message.edit(view=self)
            except Exception:
                pass

    def _make_preview_callback(self, idx: int):
        async def callback(interaction: discord.Interaction):
            if self.chosen:
                await interaction.response.send_message(
                    "You already claimed a card!", ephemeral=True, delete_after=5
                )
                return

            card = self.cards[idx]

            # Hydrate full character details for the embed
            try:
                from database import get_character_by_id
                full = get_character_by_id(card["id"])
                if full:
                    full = dict(full)
                    # Preserve spin flags
                    for key in ("is_shiny", "is_dupe", "is_dupe_shiny", "is_fav",
                                "story_title", "author", "cover_url"):
                        if key in card:
                            full[key] = card[key]
                    card = full
            except Exception:
                pass

            preview_view = SpinCardPreviewView(
                card      = card,
                viewer    = interaction.user,
                pick_view = self,
                card_idx  = idx,
            )
            preview_view._message = interaction.message

            embed, _ = build_ctc_card_embed(
                card,
                interaction.user.id,
                viewer   = interaction.user,
                shiny    = bool(card.get("is_shiny")),
                index    = 1,
                total    = 1,
            )

            # Prefix the title to make context clear
            if card.get("is_shiny"):
                embed.title = f"✨ SHINY ROLL ✨  —  {embed.title}"
            else:
                embed.title = f"👀 Preview  —  {embed.title}"

            await interaction.response.edit_message(
                content=None, embed=embed, view=preview_view
            )
        return callback


# ─────────────────────────────────────────────────
# Shop — paginated browseable list
# ─────────────────────────────────────────────────

SHOP_PAGE_SIZE = 7
NUMBER_EMOJIS  = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣"]


class ShopCardView(CTCCardView):
    """
    Card detail opened when a user clicks a number in the shop list.
    Row 0: Behind the Scenes dropdown (inherited from CTCCardView)
    Row 1: Buy / Owned (disabled blue) + Back to Shop (green)
    """

    def __init__(self, char: dict, shop_view: "ShopView", viewer: discord.Member = None):
        super().__init__(
            cards      = [char],
            viewer_uid = shop_view.buyer_uid,
            viewer     = viewer,   # passed directly from the interaction
            timeout    = 300,
        )
        self.char      = char
        self.shop_view = shop_view
        self._add_shop_buttons()

    def _add_shop_buttons(self):
        """Append Buy/Owned and Return to row 1."""
        sv = self.shop_view

        if self.char["id"] in sv.owned_ids:
            owned_btn = ui.Button(
                label    = "✅ Owned",
                style    = discord.ButtonStyle.primary,   # blue
                disabled = True,
                row      = 1,
            )
            self.add_item(owned_btn)
        else:
            buy_btn = ui.Button(
                label = f"🛒 Buy  {CRYSTAL} 3,000",
                style = discord.ButtonStyle.success,
                row   = 1,
            )
            buy_btn.callback = self._buy
            self.add_item(buy_btn)

        return_btn = ui.Button(
            label = "🏪 Shop",
            style = discord.ButtonStyle.success,
            row   = 1,
        )
        return_btn.callback = self._return
        self.add_item(return_btn)

    def _rebuild_shop_buttons(self):
        self.clear_items()
        self._refresh()
        self._add_shop_buttons()

    async def _buy(self, interaction: discord.Interaction):
        sv = self.shop_view

        from database import perform_direct_buy, check_and_grant_milestones, grant_author_passive

        success, msg, new_bal = perform_direct_buy(sv.buyer_db_id, self.char["id"])
        if not success:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True, delete_after=5)
            return

        sv.balance = new_bal
        sv.owned_ids.add(self.char["id"])

        author_uid = _gid_by_char(self.char["id"])
        if author_uid and author_uid != sv.buyer_db_id:
            grant_author_passive(author_uid, self.char["id"], sv.buyer_db_id)

        new_milestones = check_and_grant_milestones(sv.buyer_db_id)
        bonus = ""
        if new_milestones:
            ms    = new_milestones[-1]
            bonus = f"\n{CRYSTAL} **Milestone!** {ms} cards → **+500 crystals!**"

        self._rebuild_shop_buttons()
        # Keep viewer live so dropdown still works after purchase
        self.viewer = interaction.user

        embed, _ = build_ctc_card_embed(
            self.char, sv.buyer_uid,
            viewer=interaction.user,
            obtained_via="direct_buy", index=1, total=1,
        )
        await interaction.response.edit_message(
            content=(
                f"🛒 **{self.char['name']}** added to your collection!{bonus}\n"
                f"Remaining balance: {_fmt_balance(new_bal)}"
            ),
            embed=embed,
            view=self,
        )

    async def _return(self, interaction: discord.Interaction):
        sv = self.shop_view
        sv._build_ui()
        await interaction.response.edit_message(
            content=None, embed=sv.build_embed(), view=sv
        )


class ShopView(ui.View):

    def __init__(self, chars: list, buyer_uid: int, buyer_db_id: int,
                 balance: int, owned_ids: set, guild: discord.Guild = None):
        super().__init__(timeout=300)
        self.chars       = chars
        self.buyer_uid   = buyer_uid
        self.buyer_db_id = buyer_db_id
        self.balance     = balance
        self.owned_ids   = owned_ids
        self.page        = 0
        self._guild      = guild    # stored so ShopCardView can resolve the Member
        self._build_ui()

    @property
    def total_pages(self):
        return max(1, (len(self.chars) + SHOP_PAGE_SIZE - 1) // SHOP_PAGE_SIZE)

    def _page_items(self):
        start = self.page * SHOP_PAGE_SIZE
        return self.chars[start:start + SHOP_PAGE_SIZE]

    def build_embed(self) -> discord.Embed:
        from database import DIRECT_BUY_COST
        items = self._page_items()
        embed = discord.Embed(
            title=f"🛒  CTC Shop  —  Page {self.page + 1} of {self.total_pages}",
            description=(
                f"{_fmt_balance(self.balance)}\n"
                f"-# Direct buy costs {CRYSTAL} **{DIRECT_BUY_COST:,}** per card\n"
                f"-# Cards you already own are marked ✅"
            ),
            color=discord.Color.blurple()
        )
        for i, c in enumerate(items, 1):
            owned  = c["id"] in self.owned_ids
            status = "✅" if owned else f"{CRYSTAL} {3000:,}"
            embed.add_field(
                name=f"{NUMBER_EMOJIS[i-1]}  {c['name']}",
                value=f"-# ✦ {c.get('story_title','?')}  ·  {status}",
                inline=False
            )
        embed.set_footer(text=f"Total characters in library: {len(self.chars)}")
        return embed

    def _build_ui(self):
        self.clear_items()
        items = self._page_items()

        # All gray; 1-5 on row 0, 6-7 on row 1
        for i, c in enumerate(items):
            btn = ui.Button(
                emoji=NUMBER_EMOJIS[i],
                style=discord.ButtonStyle.primary,
                row=0 if i < 5 else 1,
                custom_id=f"shop_pick_{i}"
            )
            btn.callback = self._make_open_callback(c)
            self.add_item(btn)

        # Nav on row 2
        prev = ui.Button(emoji="⬅️", style=discord.ButtonStyle.secondary,
                         row=2, disabled=self.page == 0)
        prev.callback = self._prev
        self.add_item(prev)

        nxt = ui.Button(emoji="➡️", style=discord.ButtonStyle.secondary,
                        row=2, disabled=self.page >= self.total_pages - 1)
        nxt.callback = self._next
        self.add_item(nxt)

    def _make_open_callback(self, char: dict):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.buyer_uid:
                await interaction.response.send_message("Not your shop!", ephemeral=True, delete_after=5)
                return

            # Look up this user's collection record for the card (if owned)
            obtained_via = None
            obtained_at  = None
            try:
                from database import get_connection, get_user_id
                uid = get_user_id(str(interaction.user.id))
                if uid:
                    _conn = get_connection()
                    _row  = _conn.execute(
                        "SELECT obtained_via, obtained_at FROM ctc_collection "
                        "WHERE user_id=? AND character_id=?",
                        (uid, char["id"])
                    ).fetchone()
                    _conn.close()
                    if _row:
                        obtained_via = _row["obtained_via"]
                        obtained_at  = _row["obtained_at"]
            except Exception:
                pass

            card_view = ShopCardView(char, self, viewer=interaction.user)
            embed, _  = build_ctc_card_embed(
                char, self.buyer_uid,
                viewer       = interaction.user,
                obtained_via = obtained_via,
                obtained_at  = obtained_at,
                index=1, total=1,
            )
            await interaction.response.edit_message(embed=embed, view=card_view)
        return callback

    async def _prev(self, interaction: discord.Interaction):
        if interaction.user.id != self.buyer_uid:
            await interaction.response.send_message("Not your shop!", ephemeral=True, delete_after=5)
            return
        self.page = max(0, self.page - 1)
        self._build_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        if interaction.user.id != self.buyer_uid:
            await interaction.response.send_message("Not your shop!", ephemeral=True, delete_after=5)
            return
        self.page = min(self.total_pages - 1, self.page + 1)
        self._build_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


# ─────────────────────────────────────────────────
# Trade flow
# ─────────────────────────────────────────────────

TRADE_FEE          = 100
TRADE_MIN_AGE_DAYS = 7


def _card_old_enough(obtained_at: str) -> bool:
    try:
        dt  = datetime.datetime.fromisoformat(obtained_at)
        age = datetime.datetime.utcnow() - dt
        return age.days >= TRADE_MIN_AGE_DAYS
    except Exception:
        return False


class TradeConfirmView(ui.View):

    def __init__(self, initiator: discord.Member, target: discord.Member,
                 offer_char: dict, request_char: dict,
                 init_db_id: int, target_db_id: int):
        super().__init__(timeout=120)
        self.initiator    = initiator
        self.target       = target
        self.offer_char   = offer_char
        self.request_char = request_char
        self.init_db_id   = init_db_id
        self.target_db_id = target_db_id
        self._message     = None   # set after send so on_timeout can edit

    async def on_timeout(self):
        from database import add_credits
        add_credits(self.init_db_id, TRADE_FEE, "refund:trade_timeout")
        if self._message:
            try:
                for item in self.children:
                    item.disabled = True
                await self._message.edit(
                    content=(
                        f"⏰ Trade offer expired — no response from {self.target.display_name}. "
                        f"{CRYSTAL} **{TRADE_FEE}** fee refunded to {self.initiator.mention}."
                    ),
                    view=self,
                )
            except Exception:
                pass

    @ui.button(label="✅ Accept Trade", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("This isn't your trade!", ephemeral=True, delete_after=5)
            return
        self.stop()

        from database import add_to_collection, get_connection, check_and_grant_milestones

        conn = get_connection()
        cur  = conn.cursor()
        cur.execute("DELETE FROM ctc_collection WHERE user_id=? AND character_id=?",
                    (self.init_db_id, self.offer_char["id"]))
        cur.execute("DELETE FROM ctc_collection WHERE user_id=? AND character_id=?",
                    (self.target_db_id, self.request_char["id"]))
        conn.commit()
        conn.close()

        add_to_collection(self.target_db_id, self.offer_char["id"],   via="trade")
        add_to_collection(self.init_db_id,   self.request_char["id"], via="trade")

        check_and_grant_milestones(self.init_db_id)
        check_and_grant_milestones(self.target_db_id)

        embed = discord.Embed(
            title="🤝 Trade Complete!",
            description=(
                f"✅ {self.initiator.mention} and {self.target.mention} swapped cards!\n\n"
                f"💎 {self.initiator.display_name} received **{self.request_char['name']}**\n"
                f"💎 {self.target.display_name} received **{self.offer_char['name']}**"
            ),
            color=discord.Color.green()
        )
        await interaction.response.edit_message(content=None, embed=embed, view=None)

    @ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("This isn't your trade!", ephemeral=True, delete_after=5)
            return
        self.stop()
        from database import add_credits
        add_credits(self.init_db_id, TRADE_FEE, "refund:trade_declined")
        await interaction.response.edit_message(
            content=(
                f"❌ {self.target.display_name} declined the trade. "
                f"{self.initiator.mention}'s {CRYSTAL} **{TRADE_FEE}** fee was refunded."
            ),
            embed=None, view=None
        )


# ─────────────────────────────────────────────────
# Shop autocomplete helpers
# ─────────────────────────────────────────────────

async def _shop_story_autocomplete(interaction: discord.Interaction, current: str):
    """
    If character is already filled → lock to only that character's story.
    Otherwise: user's story first, then random others. Max 4 + hint.
    """
    from database import get_all_stories_sorted, get_user_id, get_story_by_character
    import random as _r

    # Lock to character's story if character is already chosen
    char_val = interaction.namespace.__dict__.get("character")
    if char_val and char_val != "__hint__":
        try:
            char_id    = int(char_val)
            char_story = get_story_by_character(char_id)
            if char_story:
                title = char_story.get("title", "?")
                sid   = char_story.get("id")
                return [app_commands.Choice(name=title[:100], value=str(sid))]
        except Exception:
            pass

    all_stories = get_all_stories_sorted()
    uid = get_user_id(str(interaction.user.id))
    from database import get_stories_by_user as _gsbu
    try:
        user_story_ids = {s[0] for s in (_gsbu(uid) if uid else [])}
    except Exception:
        user_story_ids = set()

    mine   = [s for s in all_stories if s[9] in user_story_ids]
    others = [s for s in all_stories if s[9] not in user_story_ids]
    _r.shuffle(others)
    ordered = mine + others

    choices = []
    for s in ordered:
        title = s[0]
        sid   = s[9]
        if current.lower() in title.lower():
            choices.append(app_commands.Choice(name=title[:100], value=str(sid)))
        if len(choices) >= 4:
            break

    if len(choices) == 4 or (not current and len(ordered) > 4):
        choices.append(app_commands.Choice(
            name="✏️ Keep typing to narrow down…", value="__hint__"
        ))
    return choices


async def _shop_char_autocomplete(interaction: discord.Interaction, current: str):
    """
    If story param is filled → only chars from that story.
    Otherwise: user's chars first (up to 3), then random others. Max 4 + hint.
    """
    from database import get_all_characters, get_user_id, get_characters_by_story
    import random as _r

    story_val = interaction.namespace.__dict__.get("story")

    if story_val and story_val != "__hint__":
        try:
            story_id = int(story_val)
            chars    = [dict(c) for c in get_characters_by_story(story_id)]
        except Exception:
            chars = get_all_characters()
    else:
        chars = get_all_characters()

    uid = get_user_id(str(interaction.user.id))
    try:
        from database import get_characters_by_user as _gcu
        my_ids = {c["id"] for c in (_gcu(uid) if uid else [])}
    except Exception:
        my_ids = set()

    mine   = [c for c in chars if c.get("id") in my_ids]
    others = [c for c in chars if c.get("id") not in my_ids]
    _r.shuffle(others)
    ordered = mine[:3] + others

    choices = []
    for c in ordered:
        name  = c.get("name", "?")
        story = c.get("story_title", "?")
        label = f"{name}  —  {story}"
        if current.lower() in label.lower():
            choices.append(app_commands.Choice(name=label[:100], value=str(c["id"])))
        if len(choices) >= 4:
            break

    if len(choices) == 4 or (not current and len(ordered) > 4):
        choices.append(app_commands.Choice(
            name="✏️ Keep typing to narrow down…", value="__hint__"
        ))
    return choices


# ─────────────────────────────────────────────────
# All CTC slash commands
# ─────────────────────────────────────────────────

def register_ctc_commands(ctc_group: app_commands.Group, guild_id: int):

    # ── /ctc wallet ───────────────────────────────

    @ctc_group.command(name="wallet", description="View your CTC wallet, collection stats, and account info")
    async def ctc_wallet(interaction: discord.Interaction):
        from database import (
            get_balance, get_connection, get_user_id,
            get_respin_tokens, can_free_roll,
            get_collection_count, get_profile_by_discord_id,
            get_showcase_stats, get_reader_badge_count,
            ROLL_COST, DIRECT_BUY_COST, MILESTONE_INTERVAL, MILESTONE_BONUS,
            DAILY_AMOUNT, DAILY_COOLDOWN,
        )
        import random, datetime

        add_user(str(interaction.user.id), interaction.user.name)
        uid = get_user_id(str(interaction.user.id))
        if not uid:
            await interaction.response.send_message("No account found.", ephemeral=True, delete_after=5)
            return

        # ── Crystal data ──────────────────────────────────────────────────────
        bal = get_balance(uid)

        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT COALESCE(SUM(amount),0) AS total FROM credit_log WHERE user_id=? AND amount > 0 AND reason NOT LIKE 'refund:%'",
            (uid,)
        )
        lifetime = cur.fetchone()["total"]

        # Daily claim status
        cur.execute("SELECT last_claim FROM daily_claims WHERE user_id=?", (uid,))
        daily_row  = cur.fetchone()
        now        = datetime.datetime.utcnow()
        if daily_row:
            last      = datetime.datetime.fromisoformat(daily_row["last_claim"])
            diff      = now - last
            remaining = datetime.timedelta(hours=DAILY_COOLDOWN) - diff
            if diff.total_seconds() < DAILY_COOLDOWN * 3600:
                h, rem   = divmod(int(remaining.total_seconds()), 3600)
                m        = rem // 60
                daily_str = f"⏳ {h}h {m}m"
            else:
                daily_str = f"✅ Ready! (+{DAILY_AMOUNT} 💎)"
        else:
            daily_str = f"✅ Ready! (+{DAILY_AMOUNT} 💎)"
        conn.close()

        # ── Spin data ─────────────────────────────────────────────────────────
        respins                   = get_respin_tokens(uid)
        free_eligible, hours_left = can_free_roll(uid)
        spin_str = f"✅ Ready!" if free_eligible else f"⏳ {hours_left}h"

        # ── Collection data ───────────────────────────────────────────────────
        card_count = get_collection_count(uid)
        try:
            from database import get_all_characters
            total_chars = len(get_all_characters())
        except Exception:
            total_chars = 0

        # Shiny count
        try:
            conn2 = get_connection()
            shiny_row = conn2.execute(
                "SELECT COUNT(*) AS cnt FROM ctc_collection WHERE user_id=? AND is_shiny=1",
                (uid,)
            ).fetchone()
            conn2.close()
            shiny_count = shiny_row["cnt"] if shiny_row else 0
        except Exception:
            shiny_count = 0

        # Milestones hit
        milestones_hit = card_count // MILESTONE_INTERVAL
        next_milestone = ((card_count // MILESTONE_INTERVAL) + 1) * MILESTONE_INTERVAL
        cards_to_next  = next_milestone - card_count

        # ── Author / reader stats ─────────────────────────────────────────────
        stats        = get_showcase_stats(str(interaction.user.id))
        badge_count  = get_reader_badge_count(str(interaction.user.id))

        # ── Profile thumbnail ─────────────────────────────────────────────────
        profile   = get_profile_by_discord_id(str(interaction.user.id))
        banner_url = profile.get("image_url") if profile else None

        # ── Color — seeded from user ID, non-gold palette ─────────────────────
        # Use a LOCAL Random instance so the global random state (used for spin
        # shiny odds) is never contaminated by a deterministic seed.
        _wallet_palette = [
            (140, 158, 255), (100, 181, 246), (100, 220, 180), ( 60, 170, 240),
            (210, 100, 255), (255,  80, 200), (160, 120, 255), ( 70, 220, 150),
            (200, 150, 255), (150, 100, 255), (220, 100, 180), ( 80, 200, 230),
            ( 60, 200, 210), (244, 143, 177), (186, 104, 200), ( 90, 200, 100),
        ]
        _local_rng = random.Random(uid)
        r, g, b = _local_rng.choice(_wallet_palette)
        color   = discord.Color.from_rgb(r, g, b)

        # ── Build embed ───────────────────────────────────────────────────────
        div = "── ✦ ──────────────────── ✦ ──"

        embed = discord.Embed(
            title=f"💎  {interaction.user.display_name}'s Wallet",
            description=(
                f"*Your full CTC account overview — crystals, collection, and more.*\n"
                f"{div}"
            ),
            color=color,
        )

        if banner_url and banner_url.startswith("http"):
            embed.set_thumbnail(url=banner_url)

        # Section 1 — Crystals
        embed.add_field(name="💰 Balance",        value=f"**{bal:,}** crystals",      inline=True)
        embed.add_field(name="📈 Lifetime Earned", value=f"**{lifetime:,}** crystals", inline=True)
        embed.add_field(name="🎁 Daily Claim",     value=daily_str,                    inline=True)

        embed.add_field(name="\u200b", value=div, inline=False)

        # Section 2 — Spin info
        embed.add_field(name="🎲 Free Spin",    value=spin_str,                          inline=True)
        embed.add_field(name="🎟️ Respin Tokens", value=f"**{respins}** banked",          inline=True)
        embed.add_field(name="🛒 Direct Buy",   value=f"{CRYSTAL} **{DIRECT_BUY_COST:,}** per card", inline=True)

        embed.add_field(name="\u200b", value=div, inline=False)

        # Section 3 — Collection
        collection_pct = f"{int((card_count / total_chars) * 100)}%" if total_chars else "0%"
        embed.add_field(
            name="🃏 Cards Collected",
            value=f"**{card_count}** / {total_chars}  ·  {collection_pct}",
            inline=True,
        )
        embed.add_field(
            name="✨ Shiny Cards",
            value=f"**{shiny_count}** shiny" if shiny_count else "*None yet*",
            inline=True,
        )
        embed.add_field(
            name="🏆 Milestones",
            value=(
                f"**{milestones_hit}** hit  ·  {CRYSTAL} **{milestones_hit * MILESTONE_BONUS:,}** earned\n"
                f"-# Next milestone in **{cards_to_next}** card{'s' if cards_to_next != 1 else ''}"
            ),
            inline=True,
        )

        embed.add_field(name="\u200b", value=div, inline=False)

        # Section 4 — Author & reader stats
        embed.add_field(name="📚 Stories",        value=f"**{stats['stories']}**",   inline=True)
        embed.add_field(name="🧬 Characters",      value=f"**{stats['characters']}**", inline=True)
        embed.add_field(name="🏅 Reader Badges",   value=f"**{badge_count}**",        inline=True)

        embed.set_footer(
            text=(
                "💎 Earn crystals by: chatting · reading chapters · adding stories, characters & fanart · "
                "daily claims · collection milestones · author passives"
            )
        )

        await interaction.response.send_message(embed=embed)

    # ── /ctc daily ────────────────────────────────

    @ctc_group.command(name="daily", description="Claim your daily 50 crystals")
    async def ctc_daily(interaction: discord.Interaction):
        import datetime, random
        from database import (
            get_user_id, claim_daily, add_user, get_balance,
            can_free_roll, get_respin_tokens, get_collection_count,
            DAILY_AMOUNT, DAILY_COOLDOWN,
        )

        add_user(str(interaction.user.id), interaction.user.name)
        uid = get_user_id(str(interaction.user.id))

        success, msg, new_bal = claim_daily(uid)

        # Extra context regardless of success/fail
        bal              = get_balance(uid) if not success else new_bal
        free_eligible, free_hrs = can_free_roll(uid)
        respins          = get_respin_tokens(uid)
        card_count       = get_collection_count(uid)

        spin_str = "✅ Ready to spin!" if free_eligible else f"⏳ Free spin in **{free_hrs}h**"

        _palette = [
            (140, 158, 255), (100, 220, 180), (210, 100, 255),
            (80, 200, 230),  (255, 80, 200),  (100, 181, 246),
        ]
        # Use a LOCAL Random instance — never seed the global random (used by spin odds)
        _local_rng = random.Random(uid)
        r, g, b = _local_rng.choice(_palette)
        color   = discord.Color.green() if success else discord.Color.from_rgb(r, g, b)

        div = "── ✦ ──────────────────── ✦ ──"

        if success:
            title = f"🎁  Daily Claimed!"
            desc  = (
                f"✨ **+{DAILY_AMOUNT} crystals** added to your wallet!\n"
                f"-# Come back in **{DAILY_COOLDOWN}h** for your next claim.\n"
                f"{div}"
            )
        else:
            title = f"⏳  Already Claimed"
            desc  = f"{msg}\n{div}"

        embed = discord.Embed(title=title, description=desc, color=color)

        embed.add_field(name="💰 Balance",      value=f"**{bal:,}** crystals",          inline=True)
        embed.add_field(name="🎲 Free Spin",    value=spin_str,                          inline=True)
        embed.add_field(name="🎟️ Respin Tokens", value=f"**{respins}** banked",         inline=True)
        embed.add_field(name="\u200b",          value=div,                               inline=False)
        embed.add_field(name="🃏 Cards Owned",  value=f"**{card_count}** in collection", inline=True)

        tips = [
            "💡 Spin daily to grow your collection!",
            "💡 Shiny cards have a 2% base chance on every spin!",
            f"💡 Collect {10} cards to earn a milestone bonus!",
            "💡 Direct buy a card anytime for 💎 3,000 crystals.",
            "💡 Read chapters to earn bonus crystals!",
            "💡 Trade cards with other collectors after 7 days.",
            "💡 If you already own a card, you have a 20% shiny chance on it!",
            "💡 Just chatting earns you 💎 3 crystals every 90s — up to 200/day!",
        ]
        embed.set_footer(text=random.choice(tips))

        await interaction.response.send_message(embed=embed, ephemeral=True, delete_after=30)

    # ── /ctc collection ───────────────────────────

    async def _collection_char_autocomplete(
        interaction: discord.Interaction, current: str
    ):
        from database import get_user_id, get_collection
        uid = get_user_id(str(interaction.user.id))
        if not uid:
            return []
        cards = get_collection(uid)
        if not cards:
            return []

        names = sorted({c["name"] for c in cards if c.get("name")}, key=str.lower)
        if current:
            names = [n for n in names if current.lower() in n.lower()]

        choices = [
            app_commands.Choice(name=n, value=n)
            for n in names[:4]
        ]
        if len(names) > 4:
            choices.append(app_commands.Choice(
                name="✏️ Keep typing to narrow results...",
                value=current or names[0]
            ))
        return choices

    @ctc_group.command(name="collection", description="Browse your CTC card collection")
    @app_commands.describe(character="Jump straight to a character in your collection (optional)")
    @app_commands.autocomplete(character=_collection_char_autocomplete)
    async def ctc_collection(
        interaction: discord.Interaction,
        character: str = None,
    ):
        from database import get_user_id, get_collection, get_all_characters
        from features.ctc.ctc_collection_view import CollectionRosterView, CollectionDetailView, _sort_cards

        add_user(str(interaction.user.id), interaction.user.name)
        uid = get_user_id(str(interaction.user.id))
        if not uid:
            await interaction.response.send_message("No account found.", ephemeral=True, delete_after=5)
            return

        cards = get_collection(uid)
        if not cards:
            await interaction.response.send_message(
                "Your collection is empty! Use `/ctc spin` to get your first card~",
                ephemeral=True, delete_after=5
            )
            return

        total_chars = len(get_all_characters())
        sorted_cards = _sort_cards(cards, "alpha")

        roster = CollectionRosterView(
            cards             = cards,
            viewer            = interaction.user,
            owner_label       = interaction.user.display_name,
            viewer_discord_id = str(interaction.user.id),
            total_chars       = total_chars,
        )

        # Optional: jump straight to a character by name
        if character:
            needle = character.strip().lower()
            match_idx = next(
                (i for i, c in enumerate(sorted_cards)
                 if needle in (c.get("name") or "").lower()),
                None
            )
            if match_idx is not None:
                card = dict(sorted_cards[match_idx])
                try:
                    from database import get_character_by_id
                    full = get_character_by_id(card["id"])
                    if full:
                        full = dict(full)
                        for key in ("obtained_via", "obtained_at", "is_shiny",
                                    "shiny_at", "story_title", "cover_url"):
                            if key in card:
                                full[key] = card[key]
                        card = full
                except Exception:
                    pass

                return_page = match_idx // 5
                detail = CollectionDetailView(
                    cards       = sorted_cards,
                    index       = match_idx,
                    viewer      = interaction.user,
                    roster      = roster,
                    return_page = return_page,
                    total_chars = total_chars,
                )
                detail.cards[match_idx] = card
                await interaction.response.send_message(
                    embed=detail.build_embed(), view=detail
                )
                return
            else:
                await interaction.response.send_message(
                    f"❌ No card named **{character}** in your collection.",
                    ephemeral=True, delete_after=5
                )
                return

        await interaction.response.send_message(
            embed=roster.build_embed(), view=roster
        )

    # ── /ctc peek ─────────────────────────────────

    @ctc_group.command(name="peek", description="View another user's CTC card collection")
    @app_commands.describe(user="The user whose collection to view")
    async def ctc_peek(
        interaction: discord.Interaction,
        user: discord.Member,
    ):
        from database import get_user_id, get_collection, get_all_characters
        from features.ctc.ctc_collection_view import CollectionRosterView

        uid = get_user_id(str(user.id))
        if not uid:
            await interaction.response.send_message(
                f"**{user.display_name}** hasn't started their collection yet!",
                ephemeral=True, delete_after=5
            )
            return

        cards = get_collection(uid)
        if not cards:
            await interaction.response.send_message(
                f"**{user.display_name}** hasn't collected any cards yet!",
                ephemeral=True, delete_after=5
            )
            return

        total_chars = len(get_all_characters())

        roster = CollectionRosterView(
            cards             = cards,
            viewer            = interaction.user,
            owner_label       = user.display_name,
            viewer_discord_id = str(user.id),
            total_chars       = total_chars,
            show_progress     = False,   # progress bar only on own collection
        )

        await interaction.response.send_message(
            content=f"📖 **{user.display_name}**'s collection — {len(cards)} card{'s' if len(cards) != 1 else ''}",
            embed=roster.build_embed(), view=roster
        )

    # ── /ctc spin ─────────────────────────────────

    @ctc_group.command(name="spin", description="Roll for two character cards and keep one")
    async def ctc_spin(interaction: discord.Interaction):
        from database import (
            get_user_id, add_user, can_free_roll, use_free_roll,
            perform_paid_roll, get_all_favorites_for_user,
            get_rollable_characters, get_balance, ROLL_COST,
            get_respin_tokens, use_respin_token,
            user_owns_card, user_owns_shiny,
            SHINY_BASE_CHANCE, SHINY_OWNED_CHANCE,
        )

        add_user(str(interaction.user.id), interaction.user.name)
        uid = get_user_id(str(interaction.user.id))

        # ── Determine roll type ────────────────────────────────────────────────
        eligible, hours_left = can_free_roll(uid)
        respin_tokens        = get_respin_tokens(uid)

        if eligible:
            free      = True
            roll_type = "free"
            roll_label = "🎁 Free Weekly Roll"
        elif respin_tokens > 0:
            free      = True
            roll_type = "respin"
            roll_label = f"🎟️ Respin Token  ·  {respin_tokens - 1} remaining after this"
            use_respin_token(uid)
        else:
            free      = False
            roll_type = "paid"
            bal  = get_balance(uid)
            if bal < ROLL_COST:
                await interaction.response.send_message(
                    f"⏳ Your free roll refreshes in **{hours_left}h**.\n"
                    f"You have no respin tokens.\n"
                    f"A paid roll costs {CRYSTAL} **{ROLL_COST}** but you only have "
                    f"{CRYSTAL} **{bal:,}**.",
                    ephemeral=True, delete_after=5
                )
                return
            roll_label = f"🎲 Paid Roll  ·  {CRYSTAL} {ROLL_COST}"
            success, reason, _ = perform_paid_roll(uid)
            if not success:
                await interaction.response.send_message(f"❌ {reason}", ephemeral=True, delete_after=5)
                return

        # ── Favorites + full character pool ───────────────────────────────────
        favs    = get_all_favorites_for_user(uid)
        fav_ids = {f["character_id"] for f in favs}

        # Full pool = ALL characters (owned + unowned) so shiny logic can fire
        # on owned cards; get_rollable_characters gives us unowned only.
        from database import get_all_characters
        full_pool    = [dict(c) for c in get_all_characters()]
        unowned_pool = get_rollable_characters(uid)

        if not full_pool:
            await interaction.response.send_message(
                "There are no characters in the library yet!", ephemeral=True, delete_after=5
            )
            return

        if free:
            use_free_roll(uid)

        # ── Roll two cards, applying shiny + dupe logic per slot ──────────────
        def _roll_one_slot(already_picked_ids: set) -> dict:
            """
            Pick one card for a spin slot.
            - Draw from full pool (weighted: unowned cards 5× heavier than owned)
            - Determine shiny: 2% base; 20% if user already owns the normal card
            - If result is a dupe normal (no shiny): flag is_dupe for refund on claim
            """
            # Weighted pool: unowned weight 5, owned weight 1
            unowned_ids = {c["id"] for c in unowned_pool}
            weights = []
            pool    = []
            for c in full_pool:
                if c["id"] in already_picked_ids:
                    continue   # don't show same card twice in one roll
                pool.append(c)
                weights.append(5 if c["id"] in unowned_ids else 1)

            if not pool:
                return None

            card = random.choices(pool, weights=weights, k=1)[0].copy()

            owns_normal = user_owns_card(uid, card["id"])
            owns_shiny  = user_owns_shiny(uid, card["id"])

            # Shiny chance
            shiny_chance = SHINY_OWNED_CHANCE if owns_normal else SHINY_BASE_CHANCE
            is_shiny     = random.random() < shiny_chance

            # If shiny but already own shiny → downgrade to dupe shiny (still
            # handled, but even rarer to get full reward)
            if is_shiny and owns_shiny:
                # Already have shiny — give partial reward on claim, not a new card
                card["is_shiny"]      = True
                card["is_dupe"]       = True   # will refund on claim
                card["is_dupe_shiny"] = True
            elif is_shiny:
                card["is_shiny"] = True
                card["is_dupe"]  = False
            elif owns_normal:
                # Normal dupe — flag for reroll display + refund on claim
                card["is_shiny"] = False
                card["is_dupe"]  = True
            else:
                card["is_shiny"] = False
                card["is_dupe"]  = False

            card["is_fav"] = card["id"] in fav_ids
            return card

        picked   = []
        seen_ids = set()
        for _ in range(2):
            slot = _roll_one_slot(seen_ids)
            if slot:
                picked.append(slot)
                seen_ids.add(slot["id"])

        if not picked:
            await interaction.response.send_message(
                "🎉 You've collected every character! Nothing left to roll.",
                ephemeral=True, delete_after=5
            )
            return

        # ── Build the sparkly "choose one" browse embed ──────────────────────
        from database import get_card_owner_count, get_character_fav_count, get_fanart_by_character

        any_shiny = any(c.get("is_shiny") for c in picked)
        any_fav   = any(c.get("is_fav")   for c in picked)

        div      = "── ✦ ──────────────────── ✦ ──"

        if any_shiny:
            color = discord.Color.gold()
            title = f"✨  {roll_label}  ✨"
        elif any_fav:
            color = discord.Color.from_rgb(140, 158, 255)
            title = f"⭐  {roll_label}  ⭐"
        else:
            color = discord.Color.from_rgb(100, 181, 246)
            title = f"💎  {roll_label}  💎"

        desc_lines = [
            "Two cards rolled — preview each one before deciding!",
            "-# *Click a name below to view the full card. You can flip between them freely.*",
            div,
        ]
        if any_shiny:
            shiny_names = [c["name"] for c in picked if c.get("is_shiny")]
            desc_lines.append(
                f"✨ **SHINY ALERT!** "
                f"**{', '.join(shiny_names)}** "
                f"{'is' if len(shiny_names) == 1 else 'are'} shiny — this is extremely rare!"
            )
        if any_fav:
            fav_names = [c["name"] for c in picked if c.get("is_fav") and not c.get("is_shiny")]
            if fav_names:
                desc_lines.append(
                    f"⭐ **{', '.join(fav_names)}** "
                    f"{'is' if len(fav_names) == 1 else 'are'} in your favorites!"
                )

        browse_embed = discord.Embed(
            title       = title,
            description = "\n".join(desc_lines),
            color       = color,
        )

        for i, c in enumerate(picked):
            name    = c.get("name") or "?"
            story   = c.get("story_title") or "?"
            species = c.get("species") or ""
            gender  = c.get("gender") or ""
            char_id = c.get("id", 0)

            # Pull live stats
            collectors  = get_card_owner_count(char_id)
            fav_count   = get_character_fav_count(char_id)
            fanart_list = get_fanart_by_character(char_id)
            fanart_cnt  = len(fanart_list) if fanart_list else 0

            # Header tag line
            tags = "  ·  ".join(t for t in [gender, species] if t)

            # Status badge
            if c.get("is_shiny"):
                title_prefix = "✨ SHINY  ·  "
            elif c.get("is_dupe_shiny"):
                title_prefix = "✨ SHINY (dupe)  ·  "
            elif c.get("is_dupe"):
                title_prefix = "🔁 Duplicate  ·  "
            else:
                title_prefix = ""

            fav_tag = "  ⭐" if c.get("is_fav") else ""

            # Rarity feel — how many people own it
            if collectors == 0:
                rarity_str = "✦ Uncollected — be the first!"
            elif collectors == 1:
                rarity_str = "✦ Only **1** collector so far"
            elif collectors <= 5:
                rarity_str = f"✦ Rare — only **{collectors}** collectors"
            else:
                rarity_str = f"✦ **{collectors}** collectors"

            # Build value block
            value_lines = [
                f"📚 *{story}*" + (f"  ·  {tags}" if tags else ""),
                f"-# {rarity_str}",
                f"-# 💖 **{fav_count}** {'favorite' if fav_count == 1 else 'favorites'}  ·  "
                f"🎨 **{fanart_cnt}** fanart {'piece' if fanart_cnt == 1 else 'pieces'}",
            ]
            if c.get("is_dupe"):
                value_lines.append(f"-# 🔁 You already own this  ·  {CRYSTAL} **{DUPLICATE_REFUND}** refund on claim")
            elif c.get("is_shiny") and not c.get("is_dupe_shiny"):
                value_lines.append(f"-# ✨ *Claiming also grants the normal card!*")

            browse_embed.add_field(
                name   = f"{'✨' if c.get('is_shiny') else '💎'}  {title_prefix}{name}{fav_tag}",
                value  = "\n".join(value_lines),
                inline = True,
            )

        browse_embed.add_field(name="\u200b", value=div, inline=False)
        browse_embed.set_footer(text="⏰ This roll expires in 5 minutes  ·  Choose wisely!")

        view = SpinPickView(
            picked, interaction.user.id, free, browse_embed,
            roll_type=roll_type, roller_db_id=uid,
        )
        await interaction.response.send_message(embed=browse_embed, view=view)
        # Store message reference so on_timeout can edit it
        try:
            view._message = await interaction.original_response()
        except Exception:
            pass

    # ── /ctc shop ─────────────────────────────────

    @ctc_group.command(name="shop", description="Browse and buy character cards directly")
    async def ctc_shop(interaction: discord.Interaction):
        from database import (
            get_user_id, add_user, get_balance,
            get_all_characters, get_collection, get_character_by_id
        )
        from features.ctc.ctc_shop_view import ShopView as NewShopView, _hydrate

        add_user(str(interaction.user.id), interaction.user.name)
        uid = get_user_id(str(interaction.user.id))
        bal = get_balance(uid)

        all_chars  = get_all_characters()
        full_chars = _hydrate(all_chars)

        owned_cards = get_collection(uid)
        owned_ids   = {c["id"] for c in owned_cards}

        view = NewShopView(full_chars, interaction.user.id, uid, bal, owned_ids)
        await interaction.response.send_message(
            embed=view.build_embed(), view=view
        )

    # ── /ctc upgrade ──────────────────────────────

    async def _upgrade_char_autocomplete(
        interaction: discord.Interaction, current: str
    ):
        """Your owned non-shiny cards — 4 matches + hint."""
        from database import get_user_id, get_collection, user_owns_shiny
        uid = get_user_id(str(interaction.user.id))
        if not uid:
            return []
        cards = get_collection(uid)
        # Only cards the user doesn't already have shiny
        upgradeable = [
            c for c in cards
            if not user_owns_shiny(uid, c["id"])
            and (not current or current.lower() in (c.get("name") or "").lower())
        ]
        upgradeable.sort(key=lambda c: (c.get("name") or "").lower())
        choices = [
            app_commands.Choice(
                name=f"{c['name']}  ✦  {c.get('story_title', '?')}"[:100],
                value=c["name"],
            )
            for c in upgradeable[:4]
        ]
        choices.append(app_commands.Choice(
            name="✏️ Keep typing to search your upgradeable cards...",
            value=current or (upgradeable[0]["name"] if upgradeable else ""),
        ))
        return choices

    @ctc_group.command(name="upgrade", description="Upgrade a card you own to its ✨ shiny version")
    @app_commands.describe(character="Jump straight to a card to upgrade (optional)")
    @app_commands.autocomplete(character=_upgrade_char_autocomplete)
    async def ctc_upgrade(interaction: discord.Interaction, character: str = None):
        from database import (
            get_user_id, add_user, get_collection, user_owns_shiny,
        )
        from features.ctc.ctc_upgrade_view import UpgradeRosterView, UpgradeCardView, _sort_cards
        from features.ctc.ctc_shop_view import _hydrate_one

        add_user(str(interaction.user.id), interaction.user.name)
        uid = get_user_id(str(interaction.user.id))

        all_cards = get_collection(uid)

        # Filter to owned-but-not-shiny
        upgradeable = [c for c in all_cards if not user_owns_shiny(uid, c["id"])]

        if not upgradeable:
            await interaction.response.send_message(
                "✨ All your cards are already shiny — you're a legend!",
                ephemeral=True, delete_after=8
            )
            return

        sorted_cards = _sort_cards(upgradeable, "alpha")

        roster = UpgradeRosterView(
            cards             = upgradeable,
            viewer            = interaction.user,
            viewer_uid        = uid,
            viewer_discord_id = str(interaction.user.id),
        )

        # Optional: jump straight to a character
        if character:
            needle    = character.strip().lower()
            match_idx = next(
                (i for i, c in enumerate(sorted_cards)
                 if needle in (c.get("name") or "").lower()),
                None
            )
            if match_idx is not None:
                card = dict(sorted_cards[match_idx])
                try:
                    card = _hydrate_one(card)
                    src  = sorted_cards[match_idx]
                    for key in ("obtained_via", "obtained_at", "is_shiny", "shiny_at"):
                        if key in src:
                            card[key] = src[key]
                except Exception:
                    pass

                detail = UpgradeCardView(
                    cards       = sorted_cards,
                    index       = match_idx,
                    viewer      = interaction.user,
                    viewer_uid  = uid,
                    roster      = roster,
                    return_page = match_idx // 5,
                )
                detail.cards[match_idx] = card
                await interaction.response.send_message(
                    embed=detail.build_embed(), view=detail, ephemeral=True
                )
                try:
                    detail._message = await interaction.original_response()
                except Exception:
                    pass
                return
            else:
                await interaction.response.send_message(
                    f"❌ **{character}** isn't in your upgradeable cards.",
                    ephemeral=True, delete_after=6
                )
                return

        await interaction.response.send_message(
            embed=roster.build_embed(), view=roster, ephemeral=True
        )
        try:
            roster._message = await interaction.original_response()
        except Exception:
            pass

    # ── /ctc odds ─────────────────────────────────

    @ctc_group.command(name="odds", description="View roll odds and how the spin system works")
    async def ctc_odds(interaction: discord.Interaction):
        from database import (
            get_user_id, get_rollable_characters, get_all_characters,
            get_collection_count,
            ROLL_COST, DIRECT_BUY_COST, SHINY_UPGRADE_COST,
            SHINY_BASE_CHANCE, SHINY_OWNED_CHANCE, DUPLICATE_REFUND,
        )

        uid      = get_user_id(str(interaction.user.id))
        total    = len(get_all_characters())
        rollable = len(get_rollable_characters(uid)) if uid else total
        owned    = get_collection_count(uid) if uid else 0

        if total == 0:
            await interaction.response.send_message("No characters in the library yet!", ephemeral=True, delete_after=5)
            return

        div = "── ✦ ──────────────────── ✦ ──"

        embed = discord.Embed(
            title       = "🎲  CTC Spin — How It Works",
            description = (
                "Every spin draws **two cards** for you to preview in full before deciding.\n"
                "You can flip between both cards freely before claiming one.\n"
                f"{div}"
            ),
            color = discord.Color.from_rgb(100, 181, 246),
        )

        # Pool odds
        unowned_pct = round((rollable / total) * 100, 1) if total else 0
        embed.add_field(
            name  = "📊 Your Pool",
            value = (
                f"Library size: **{total}** characters\n"
                f"You own: **{owned}** · Unowned: **{rollable}**\n"
                f"-# Unowned cards are weighted **5×** heavier than owned ones,\n"
                f"-# so you're always more likely to roll something new."
            ),
            inline = False,
        )

        # Shiny odds
        embed.add_field(name="\u200b", value=div, inline=False)
        embed.add_field(
            name  = "✨ Shiny Odds",
            value = (
                f"**{int(SHINY_BASE_CHANCE * 100)}%** base chance on any spin\n"
                f"**{int(SHINY_OWNED_CHANCE * 100)}%** if you already own the normal card\n"
                f"-# Shinies have a gold embed and a special ✨ badge.\n"
                f"-# Claiming a shiny **also grants the normal card** if you don't have it!\n"
                f"-# Once you own both, a **🌟 Shiny toggle** appears on your collection card."
            ),
            inline = False,
        )

        # Duplicate handling
        embed.add_field(name="\u200b", value=div, inline=False)
        embed.add_field(
            name  = "🔁 Duplicate Normal Cards",
            value = (
                f"Rolling a card you already own (normal, no shiny) gives you a\n"
                f"{CRYSTAL} **{DUPLICATE_REFUND}** consolation refund on claim.\n"
                f"-# The card is not added again — you can't hold duplicates.\n"
                f"-# The **shiny chance is boosted** ({int(SHINY_OWNED_CHANCE * 100)}%) to compensate!"
            ),
            inline = False,
        )

        # Costs
        embed.add_field(name="\u200b", value=div, inline=False)
        embed.add_field(
            name  = f"{CRYSTAL} Costs",
            value = (
                f"🎁 **Free spin** — every **7 days**\n"
                f"🎟️ **Respin token** — earned via milestones & events\n"
                f"🎲 **Paid spin** — {CRYSTAL} **{ROLL_COST:,}** crystals\n"
                f"🛒 **Direct buy** — {CRYSTAL} **{DIRECT_BUY_COST:,}** crystals\n"
                f"✨ **Shiny upgrade** — {CRYSTAL} **{SHINY_UPGRADE_COST:,}** crystals\n"
                f"-# Upgrade any owned card to shiny via `/ctc upgrade`."
            ),
            inline = False,
        )

        embed.set_footer(text="⏰ Spin sessions expire after 5 minutes — make your pick before time runs out!")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        import asyncio
        await asyncio.sleep(120)
        try:
            await interaction.delete_original_response()
        except Exception:
            pass
        try:
            await interaction.followup.send("*Session timed out.*", ephemeral=True, wait=True)
        except Exception:
            pass

    # ── /ctc leaderboard ─────────────────────────

    @ctc_group.command(name="leaderboard", description="Top collectors, earners, and shinies")
    async def ctc_leaderboard(interaction: discord.Interaction):
        from database import get_connection

        LIBRARY_THUMB = (
            "https://images-wixmp-ed30a86b8c4ca887773594c2.wixmp.com/f/889ced1b-f394-4def-924c-4f920c92e0ac/"
            "dkvyphd-38e7fc4c-a349-4f24-bbbc-90d96dbb602b.png?token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9."
            "eyJzdWIiOiJ1cm46YXBwOjdlMGQxODg5ODIyNjQzNzNhNWYwZDQxNWVhMGQyNmUwIiwiaXNzIjoidXJuOmFwcDo3ZT"
            "BkMTg4OTgyMjY0MzczYTVmMGQ0MTVlYTBkMjZlMCIsIm9iaiI6W1t7InBhdGgiOiIvZi84ODljZWQxYi1mMzk0LTRk"
            "ZWYtOTI0Yy00ZjkyMGM5MmUwYWMvZGt2eXBoZC0zOGU3ZmM0Yy1hMzQ5LTRmMjQtYmJiYy05MGQ5NmRiYjYwMmIu"
            "cG5nIn1dXSwiYXVkIjpbInVybjpzZXJ2aWNlOmZpbGUuZG93bmxvYWQiXX0.CJlMPo-23sO7fwEZGNureydkCtLf5Ma8ZkDXzXOYocU"
        )

        TOP = 5
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        div = "── ✦ ──────────────────── ✦ ──"

        conn = get_connection()
        cur  = conn.cursor()

        # Top collectors (total cards)
        cur.execute("""
            SELECT u.username, COUNT(cc.character_id) AS n
            FROM ctc_collection cc JOIN users u ON cc.user_id = u.id
            GROUP BY cc.user_id ORDER BY n DESC LIMIT ?
        """, (TOP,))
        collectors = cur.fetchall()

        # Top shiny collectors
        cur.execute("""
            SELECT u.username, COUNT(cc.character_id) AS n
            FROM ctc_collection cc JOIN users u ON cc.user_id = u.id
            WHERE cc.is_shiny = 1
            GROUP BY cc.user_id ORDER BY n DESC LIMIT ?
        """, (TOP,))
        shiny_leaders = cur.fetchall()

        # Lifetime crystal earners (exclude refunds)
        cur.execute("""
            SELECT u.username,
                   COALESCE(SUM(CASE WHEN cl.amount > 0 THEN cl.amount ELSE 0 END), 0) AS n
            FROM credit_log cl JOIN users u ON cl.user_id = u.id
            WHERE cl.reason NOT LIKE 'refund:%'
            GROUP BY cl.user_id ORDER BY n DESC LIMIT ?
        """, (TOP,))
        earners = cur.fetchall()

        # Most gifted crystals (outgoing gifts)
        cur.execute("""
            SELECT u.username, COALESCE(SUM(ABS(cl.amount)), 0) AS n
            FROM credit_log cl JOIN users u ON cl.user_id = u.id
            WHERE cl.reason LIKE 'gift%' AND cl.amount < 0
            GROUP BY cl.user_id ORDER BY n DESC LIMIT ?
        """, (TOP,))
        gifters = cur.fetchall()

        # Most spins (roll + free_roll + respin token entries in ctc_collection)
        cur.execute("""
            SELECT u.username, COUNT(*) AS n
            FROM ctc_collection cc JOIN users u ON cc.user_id = u.id
            WHERE cc.obtained_via IN ('roll', 'free_roll', 'respin')
            GROUP BY cc.user_id ORDER BY n DESC LIMIT ?
        """, (TOP,))
        spinners = cur.fetchall()

        # Most obtained characters (characters with most collectors)
        cur.execute("""
            SELECT c.name, COUNT(cc.user_id) AS n
            FROM ctc_collection cc JOIN characters c ON cc.character_id = c.id
            GROUP BY cc.character_id ORDER BY n DESC LIMIT ?
        """, (TOP,))
        pop_chars = cur.fetchall()

        # Total characters in library for % calc
        cur.execute("SELECT COUNT(*) AS n FROM characters")
        total_chars = cur.fetchone()["n"] or 1

        conn.close()

        def _fmt(rows, suffix="", pct_of=None, name_key="username"):
            if not rows:
                return "-# *No data yet*"
            lines = []
            for i, r in enumerate(rows):
                val  = r["n"]
                name = r[name_key]
                extra = f" ({int(val/pct_of*100)}%)" if pct_of else ""
                lines.append(f"{medals[i]} **{name}** — {val:,}{suffix}{extra}")
            return "\n".join(lines)

        embed = discord.Embed(
            title       = "✦ ✦  CTC Leaderboard  ✦ ✦",
            description = (
                "*The finest collectors in the server — who will claim the top spot?*\n"
                f"{div}"
            ),
            color = discord.Color.gold(),
        )
        embed.set_thumbnail(url=LIBRARY_THUMB)

        embed.add_field(
            name  = "💎 Top Collectors",
            value = _fmt(collectors, " cards", pct_of=total_chars),
            inline = True,
        )
        embed.add_field(
            name  = "✨ Most Shinies",
            value = _fmt(shiny_leaders, " shiny"),
            inline = True,
        )
        embed.add_field(name="\u200b", value=div, inline=False)
        embed.add_field(
            name  = "📈 Lifetime Crystals Earned",
            value = _fmt(earners, " 💎"),
            inline = True,
        )
        embed.add_field(
            name  = "🎁 Most Generous (Gifts Sent)",
            value = _fmt(gifters, " 💎 gifted") if gifters and any(r["n"] > 0 for r in gifters) else "-# *No gifts yet — be the first!*",
            inline = True,
        )
        embed.add_field(name="\u200b", value=div, inline=False)
        embed.add_field(
            name  = "🎲 Most Spins",
            value = _fmt(spinners, " spins"),
            inline = True,
        )
        embed.add_field(
            name  = "🌟 Most Collected Characters",
            value = _fmt(pop_chars, " collectors", name_key="name"),
            inline = True,
        )
        embed.add_field(name="\u200b", value=div, inline=False)
        embed.set_footer(text="✦ Spin, collect, and gift your way to the top!  ✦  Top 5 in each category")
        await interaction.response.send_message(embed=embed)

    # ── /ctc trade ────────────────────────────────

    async def _trade_offer_autocomplete(
        interaction: discord.Interaction, current: str
    ):
        """Your collection — 4 matches + hint."""
        from database import get_user_id, get_collection
        uid = get_user_id(str(interaction.user.id))
        if not uid:
            return []
        cards = get_collection(uid)
        if not cards:
            return []
        matches = [
            c for c in cards
            if current.lower() in (c.get("name") or "").lower()
        ]
        matches.sort(key=lambda c: (c.get("name") or "").lower())
        choices = [
            app_commands.Choice(
                name=f"{c['name']}  ✦  {c.get('story_title', '?')}"[:100],
                value=c["name"],
            )
            for c in matches[:4]
        ]
        choices.append(app_commands.Choice(
            name="✏️ Keep typing to search your collection...",
            value=current or (matches[0]["name"] if matches else ""),
        ))
        return choices

    async def _trade_request_autocomplete(
        interaction: discord.Interaction, current: str
    ):
        """Every character in the DB — 4 random (or filtered) + hint."""
        import random as _r
        from database import get_all_characters
        all_chars = get_all_characters()
        if not all_chars:
            return []

        if current:
            pool = [
                c for c in all_chars
                if current.lower() in (c.get("name") or "").lower()
            ]
        else:
            pool = list(all_chars)
            _r.shuffle(pool)

        choices = []
        for c in pool[:4]:
            try:
                from database import get_story_by_character
                story = get_story_by_character(c["id"])
                story_title = story["title"] if story else "?"
            except Exception:
                story_title = c.get("story_title") or "?"
            choices.append(app_commands.Choice(
                name=f"{c['name']}  ✦  {story_title}"[:100],
                value=c["name"],
            ))
        choices.append(app_commands.Choice(
            name="✏️ Keep typing to search all characters...",
            value=current or (pool[0]["name"] if pool else ""),
        ))
        return choices

    @ctc_group.command(name="trade", description="Offer a card trade with another user")
    @app_commands.describe(
        user="User to trade with",
        offer="A card from YOUR collection to offer",
        request="A card you want in return (searches all characters)"
    )
    @app_commands.autocomplete(
        offer=_trade_offer_autocomplete,
        request=_trade_request_autocomplete,
    )
    async def ctc_trade(interaction: discord.Interaction,
                        user: discord.Member, offer: str, request: str):
        from database import get_user_id, add_user, get_collection, spend_credits, user_owns_card

        if user.id == interaction.user.id:
            await interaction.response.send_message("You can't trade with yourself!", ephemeral=True, delete_after=5)
            return

        add_user(str(interaction.user.id), interaction.user.name)
        init_uid   = get_user_id(str(interaction.user.id))
        target_uid = get_user_id(str(user.id))

        if not target_uid:
            await interaction.response.send_message(
                f"**{user.display_name}** hasn't started their collection yet!", ephemeral=True, delete_after=5
            )
            return

        my_cards    = get_collection(init_uid)
        their_cards = get_collection(target_uid)

        offer_card   = next((c for c in my_cards    if c["name"].lower() == offer.lower()),   None)
        request_card = next((c for c in their_cards if c["name"].lower() == request.lower()), None)

        if not offer_card:
            await interaction.response.send_message(
                f"You don't own a card called **{offer}**.", ephemeral=True, delete_after=5)
            return
        if not request_card:
            await interaction.response.send_message(
                f"**{user.display_name}** doesn't own a card called **{request}**.", ephemeral=True, delete_after=5)
            return

        if not _card_old_enough(offer_card.get("obtained_at", "")):
            await interaction.response.send_message(
                f"**{offer_card['name']}** was obtained less than 7 days ago and can't be traded yet.",
                ephemeral=True, delete_after=5)
            return

        ok, new_bal = spend_credits(
            init_uid, TRADE_FEE,
            f"trade_fee:{offer_card['id']}:{request_card['id']}"
        )
        if not ok:
            await interaction.response.send_message(
                f"You need {CRYSTAL} **{TRADE_FEE}** to initiate a trade "
                f"but only have {CRYSTAL} **{new_bal}**.",
                ephemeral=True, delete_after=5
            )
            return

        div = "── ✦ ──────────────────── ✦ ──"
        embed = discord.Embed(
            title="🤝  Trade Offer",
            description=(
                f"{interaction.user.mention} wants to trade with {user.mention}!\n"
                f"{div}"
            ),
            color=discord.Color.blurple()
        )
        embed.add_field(
            name="💎 Offering",
            value=(
                f"**{offer_card['name']}**\n"
                f"-# 📚 {offer_card.get('story_title','?')}"
            ),
            inline=True,
        )
        embed.add_field(name="⇄", value="\u200b", inline=True)
        embed.add_field(
            name="💎 Requesting",
            value=(
                f"**{request_card['name']}**\n"
                f"-# 📚 {request_card.get('story_title','?')}"
            ),
            inline=True,
        )
        embed.add_field(name="\u200b", value=div, inline=False)
        embed.add_field(
            name="💡 Info",
            value=(
                f"-# Trade fee of {CRYSTAL} **{TRADE_FEE}** paid by {interaction.user.display_name}.\n"
                f"-# Declining or timeout refunds the fee.\n"
                f"-# Offer expires in **2 minutes**."
            ),
            inline=False,
        )
        view = TradeConfirmView(
            interaction.user, user,
            offer_card, request_card,
            init_uid, target_uid
        )
        await interaction.response.send_message(content=user.mention, embed=embed, view=view)
        try:
            view._message = await interaction.original_response()
        except Exception:
            pass

    # ── /ctc gift ─────────────────────────────────

    @ctc_group.command(name="gift", description="Send crystals to another user (max 500/day)")
    @app_commands.describe(user="Who to send crystals to", amount="How many to send")
    async def ctc_gift(interaction: discord.Interaction,
                       user: discord.Member, amount: int):
        from database import get_user_id, add_user, spend_credits, add_credits, get_connection

        GIFT_DAILY_CAP = 500

        if user.id == interaction.user.id:
            await interaction.response.send_message("You can't gift yourself!", ephemeral=True, delete_after=5)
            return
        if amount <= 0:
            await interaction.response.send_message("Amount must be positive!", ephemeral=True, delete_after=5)
            return
        if amount > GIFT_DAILY_CAP:
            await interaction.response.send_message(
                f"You can only gift up to {CRYSTAL} **{GIFT_DAILY_CAP}** per day.", ephemeral=True, delete_after=5
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
                f"Not enough crystals! You have {CRYSTAL} **{new_bal}**.", ephemeral=True, delete_after=5
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

    # ── /ctc help ─────────────────────────────────

    @ctc_group.command(name="help", description="A full guide to the CTC system")
    async def ctc_help(interaction: discord.Interaction):
        from database import ROLL_COST, DIRECT_BUY_COST, SHINY_UPGRADE_COST

        div = "── ✦ ──────────────────── ✦ ──"

        embed = discord.Embed(
            title       = "✦ ✦  Character Trading Cards  ✦ ✦",
            description = (
                "*Collect, trade, and upgrade character cards from the library!*\n"
                "*Every card is unique — shiny versions are ultra rare.*\n"
                f"{div}"
            ),
            color = discord.Color.from_rgb(140, 158, 255),
        )

        # ── Getting cards ─────────────────────────────────────────────────────
        embed.add_field(
            name  = "🎲  Getting Cards",
            value = (
                f"`/ctc spin` — Roll two cards and preview both before choosing.\n"
                f"-# Free spin every **7 days** · {CRYSTAL} **{ROLL_COST}** for a paid spin\n"
                f"-# Unowned cards are **5× more likely** to appear\n"
                f"-# Expires in **5 minutes** — pick before time runs out!\n\n"
                f"`/ctc shop` — Browse and buy any card directly for {CRYSTAL} **{DIRECT_BUY_COST:,}**\n\n"
                f"`/ctc upgrade [character]` — Upgrade a card to ✨ shiny for {CRYSTAL} **{SHINY_UPGRADE_COST:,}**"
            ),
            inline = False,
        )
        embed.add_field(name="\u200b", value=div, inline=False)

        # ── Shiny system ──────────────────────────────────────────────────────
        embed.add_field(
            name  = "✨  Shiny Cards",
            value = (
                "Shinies have a **gold embed** and a special ✨ badge.\n"
                f"-# **2%** base chance per spin\n"
                f"-# **20%** if you already own the normal version\n"
                f"-# Claiming a shiny also **grants the normal card** if you don't have it\n"
                f"-# Own both? A **🌟 toggle** appears on your card to switch views\n"
                f"-# Can't get lucky? Buy shiny directly via `/ctc upgrade`"
            ),
            inline = False,
        )
        embed.add_field(name="\u200b", value=div, inline=False)

        # ── Collection ────────────────────────────────────────────────────────
        embed.add_field(
            name  = "🃏  Your Collection",
            value = (
                "`/ctc collection [character]` — Browse your cards. Sort by A-Z · Shiny First · Oldest · Newest.\n\n"
                "`/ctc peek @user` — View someone else's collection.\n\n"
                "`/ctc wallet` — Your crystals, spin status, collection stats, and account overview.\n\n"
                "`/ctc daily` — Claim **50 crystals** every 22 hours."
            ),
            inline = False,
        )
        embed.add_field(name="\u200b", value=div, inline=False)

        # ── Trading & gifting ─────────────────────────────────────────────────
        embed.add_field(
            name  = "🤝  Trading & Gifting",
            value = (
                f"`/ctc trade @user [offer] [request]` — Propose a card swap.\n"
                f"-# Costs {CRYSTAL} **{TRADE_FEE}** to initiate · refunded if declined or expired\n"
                f"-# Cards must be **7 days old** to trade · target has **2 min** to respond\n\n"
                f"`/ctc gift @user [amount]` — Send up to {CRYSTAL} **500** crystals per day."
            ),
            inline = False,
        )
        embed.add_field(name="\u200b", value=div, inline=False)

        # ── Earning crystals ──────────────────────────────────────────────────
        embed.add_field(
            name  = f"{CRYSTAL}  Earning Crystals",
            value = (
                f"**The best way to earn? Read!** Open `/library`, pick a story, and read chapters.\n"
                f"Every chapter earns you crystals — and supports the authors in this server! 📖\n\n"
                f"**+2** 💬 **Just chatting!** Every message earns a tiny drip *(90s cooldown · 1000/day cap)*\n"
                f"**+30** 📖 Reading a chapter for the first time *(they stack up fast!)*\n"
                f"**+50** 🎁 `/ctc daily` *(22h cooldown)*\n"
                f"**+40** ✍️ Adding a character · **+75** 🎨 Adding fanart · **+150** 📚 Adding a story\n"
                f"**+{DUPLICATE_REFUND}** 🔁 Rolling a duplicate card *(consolation refund)*\n"
                f"**+500** 🏆 Every **10 cards** collected *(milestone bonus)*\n"
                f"-# Authors earn a passive bonus when their character is collected!\n"
                f"-# Active chatters earn up to 💎 **200** crystals/day just from talking!"
            ),
            inline = False,
        )
        embed.add_field(name="\u200b", value=div, inline=False)

        # ── Info commands ─────────────────────────────────────────────────────
        embed.add_field(
            name  = "📊  Info & Stats",
            value = (
                "`/ctc odds` — Full breakdown of spin odds, shiny rates, duplicates, and costs.\n\n"
                "`/ctc leaderboard` — Top 5: most cards, most shinies, most crystals, "
                "most generous, most spins, most-collected characters.\n\n"
                "`/ctc help` — You're looking at it! 💎"
            ),
            inline = False,
        )

        embed.set_footer(text="✦ Chat · Read · Collect · Support your server's authors! ✦")
        await interaction.response.send_message(embed=embed, ephemeral=True)