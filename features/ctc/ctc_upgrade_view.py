"""
ctc_upgrade_view.py
─────────────────────────────────────────────────────────────────────────────
Browse + detail views for /ctc upgrade.

ROSTER  — your owned cards that don't yet have a shiny version
  Row 0: 1️⃣–5️⃣ index buttons
  Row 1: ⬅️  Sort (A-Z · Z-A · Recent · Oldest)  ➡️

DETAIL  — full CTC card embed
  Row 0: 🎬 Behind the Scenes... dropdown
  Row 1: 🌟 Shiny Toggle  |  ✨ Buy Shiny 5,000 / ✅ Already Shiny (disabled)  |  ↩️ Return
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations
import random
import discord
from discord import ui

CRYSTAL = "💎"

PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

SORT_CYCLE  = ["alpha", "z_alpha", "recent", "oldest"]
SORT_LABELS = {
    "alpha":   "🔤 A–Z",
    "z_alpha": "🔡 Z–A",
    "recent":  "🕒 Recent",
    "oldest":  "🕐 Oldest",
}

_SPARKS   = ["✨", "🌸", "⭐", "💎", "🌺", "🔮", "💫"]
_DIVIDERS = [
    "✦ · · ✦ · · ✦ · · ✦",
    "· ˖ ✦ ˖ · ˖ ✦ ˖ ·",
    "⋆ ˚ ✦ ˚ ⋆ · ⋆ ˚ ✦",
    "─ ✦ ─────────── ✦ ─",
]
_COLORS = [
    (140, 158, 255), (100, 181, 246), (100, 220, 180), ( 60, 170, 240),
    (210, 100, 255), (255,  80, 200), (160, 120, 255), ( 70, 220, 150),
    (200, 150, 255), (150, 100, 255), (220, 100, 180), ( 80, 200, 230),
    ( 60, 200, 210), (244, 143, 177), (186, 104, 200), ( 90, 200, 100),
]


# ─────────────────────────────────────────────────────────────────────────────
# Sort helper
# ─────────────────────────────────────────────────────────────────────────────

def _sort_cards(cards: list[dict], sort: str) -> list[dict]:
    if sort == "z_alpha":
        return sorted(cards, key=lambda c: (c.get("name") or "").lower(), reverse=True)
    if sort == "recent":
        return sorted(cards, key=lambda c: c.get("obtained_at") or "", reverse=True)
    if sort == "oldest":
        return sorted(cards, key=lambda c: c.get("obtained_at") or "")
    return sorted(cards, key=lambda c: (c.get("name") or "").lower())


# ─────────────────────────────────────────────────────────────────────────────
# Roster embed
# ─────────────────────────────────────────────────────────────────────────────

def build_upgrade_roster_embed(
    cards: list[dict],
    page: int,
    total_pages: int,
    sort: str,
    viewer_discord_id: str | None = None,
) -> discord.Embed:
    from database import SHINY_UPGRADE_COST

    start      = page * PAGE_SIZE
    page_cards = cards[start:start + PAGE_SIZE]
    spark      = _SPARKS[page % len(_SPARKS)]
    divider    = _DIVIDERS[page % len(_DIVIDERS)]

    _local_rng = random.Random(page + len(cards))
    r, g, b = _local_rng.choice(_COLORS)
    color   = discord.Color.from_rgb(r, g, b)

    entry_sep = "-# · · · · · · · · · ·"
    lines     = [f"-# {divider}"]

    for i, c in enumerate(page_cards):
        global_num = start + i + 1
        name       = c.get("name") or "?"
        story      = c.get("story_title") or "?"
        char_id    = c.get("id", 0)

        # Live stats
        try:
            from database import get_card_owner_count, get_connection as _gc
            collectors = get_card_owner_count(char_id)
            _conn = _gc()
            shiny_cnt = _conn.execute(
                "SELECT COUNT(*) AS cnt FROM ctc_collection WHERE character_id=? AND is_shiny=1",
                (char_id,)
            ).fetchone()["cnt"]
            _conn.close()
        except Exception:
            collectors = 0
            shiny_cnt  = 0

        # Shiny status for this viewer
        shiny_check = "✨ Shiny owned" if c.get("is_shiny") else "○ No shiny yet"

        # Obtained timestamp
        obtained_at = c.get("obtained_at")
        obtained_str = ""
        if obtained_at:
            try:
                import datetime
                dt = datetime.datetime.fromisoformat(obtained_at).replace(
                    tzinfo=datetime.timezone.utc
                )
                ts = int(dt.timestamp())
                obtained_str = f"  ·  obtained <t:{ts}:d>"
            except Exception:
                pass

        lines.append(
            f"{NUMBER_EMOJIS[i]}  **{name}**\n"
            f"-# 📚 {story}{obtained_str}\n"
            f"-# 🃏 **{collectors}** collector{'s' if collectors != 1 else ''}  ·  "
            f"✨ **{shiny_cnt}** shiny  ·  {shiny_check}"
        )
        if i < len(page_cards) - 1:
            lines.append(entry_sep)

    lines.append(f"-# {divider}")

    embed = discord.Embed(
        title       = f"{spark}  Upgrade to Shiny  {spark}",
        description = "\n".join(lines),
        color       = color,
    )

    # Profile banner thumbnail
    if viewer_discord_id:
        try:
            from database import get_profile_by_discord_id
            profile = get_profile_by_discord_id(viewer_discord_id)
            img = profile.get("image_url") if profile else None
            if img and img.startswith("http"):
                embed.set_thumbnail(url=img)
        except Exception:
            pass

    embed.set_footer(
        text=(
            f"Page {page + 1} of {total_pages}  ·  "
            f"{len(cards)} upgradeable card{'s' if len(cards) != 1 else ''}  ·  "
            f"✨ {SHINY_UPGRADE_COST:,} 💎 each  ·  {SORT_LABELS[sort]}"
        )
    )
    return embed


# ─────────────────────────────────────────────────────────────────────────────
# Detail view — full CTC card with upgrade button
# ─────────────────────────────────────────────────────────────────────────────

class UpgradeCardView(ui.View):
    """
    Row 0: 🎬 Behind the Scenes... dropdown
    Row 1: 🌟 Shiny Toggle | ✨ Buy Shiny / ✅ Already Shiny | ↩️ Return
    """

    def __init__(
        self,
        cards:       list[dict],
        index:       int,
        viewer:      discord.Member,
        viewer_uid:  int,
        roster:      "UpgradeRosterView",
        return_page: int,
    ):
        super().__init__(timeout=180)
        self.cards        = cards
        self.index        = index
        self.viewer       = viewer
        self.viewer_uid   = viewer_uid   # DB user id
        self.roster       = roster
        self.return_page  = return_page
        self._shiny_view  = False
        self._message     = None   # set after send so on_timeout can edit
        self._refresh()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self._message:
            try:
                await self._message.edit(view=self)
            except Exception:
                pass
            try:
                await self._message.channel.send(
                    "*⏰ Upgrade session timed out.*", delete_after=5
                )
            except Exception:
                pass

    # ── helpers ──────────────────────────────────────────────────────────────

    def current(self) -> dict:
        return self.cards[self.index]

    def _owns_shiny(self) -> bool:
        try:
            from database import user_owns_shiny
            return user_owns_shiny(self.viewer_uid, self.current()["id"])
        except Exception:
            return False

    def build_embed(self) -> discord.Embed:
        from embeds.ctc_card_embed import build_ctc_card_embed
        card    = self.current()
        shiny   = self._shiny_view and self._owns_shiny()
        embed, _ = build_ctc_card_embed(
            card,
            self.viewer.id,
            viewer       = self.viewer,
            shiny        = shiny,
            obtained_via = card.get("obtained_via"),
            obtained_at  = card.get("obtained_at"),
            index        = self.index + 1,
            total        = len(self.cards),
        )
        return embed

    # ── CTCCardView compatibility so _BehindTheScenesSelect works ─────────────
    def _refresh(self):
        self._rebuild()

    def _build_embed(self) -> discord.Embed:
        return self.build_embed()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _rebuild(self):
        self.clear_items()
        from database import SHINY_UPGRADE_COST
        owns_shiny = self._owns_shiny()

        # Row 0: Behind the Scenes dropdown
        from embeds.ctc_card_embed import _BehindTheScenesSelect
        self.add_item(_BehindTheScenesSelect(
            char     = self.current(),
            viewer   = self.viewer,
            ctc_view = self,
            row      = 0,
        ))

        # Row 1: Shiny toggle
        shiny_btn = ui.Button(
            label    = "✦ Normal" if self._shiny_view else "✨ Shiny",
            emoji    = "🌟",
            style    = discord.ButtonStyle.primary,
            disabled = not owns_shiny,
            row      = 1,
        )
        shiny_btn.callback = self._toggle_shiny
        self.add_item(shiny_btn)

        # Row 1: Upgrade / Already Shiny button
        if owns_shiny:
            already_btn = ui.Button(
                label    = "✅ Already Shiny",
                style    = discord.ButtonStyle.primary,
                disabled = True,
                row      = 1,
            )
            self.add_item(already_btn)
        else:
            buy_btn = ui.Button(
                label = f"✨ Buy Shiny  💎 {SHINY_UPGRADE_COST:,}",
                style = discord.ButtonStyle.success,
                row   = 1,
            )
            buy_btn.callback = self._buy_shiny
            self.add_item(buy_btn)

        # Row 1: Return
        ret = ui.Button(label="↩️ Return", style=discord.ButtonStyle.success, row=1)
        ret.callback = self._return
        self.add_item(ret)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    async def _toggle_shiny(self, interaction: discord.Interaction):
        self._shiny_view = not self._shiny_view
        self._rebuild()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _buy_shiny(self, interaction: discord.Interaction):
        from database import upgrade_card_to_shiny, SHINY_UPGRADE_COST
        char = self.current()
        success, msg, new_bal = upgrade_card_to_shiny(self.viewer_uid, char["id"])

        if not success:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True, delete_after=8)
            return

        # Update card in list so shiny toggle activates immediately
        updated = {**char, "is_shiny": 1}
        self.cards[self.index] = updated
        self._shiny_view = True   # auto-flip to shiny view on purchase
        self._rebuild()

        embed = self.build_embed()
        embed.title = f"✨ SHINY UNLOCKED! ✨  —  {embed.title}"
        await interaction.response.edit_message(
            content=f"✨ **{char['name']}** is now shiny! {CRYSTAL} **{new_bal:,}** remaining.",
            embed=embed, view=self
        )

    async def _return(self, interaction: discord.Interaction):
        self.roster.page = self.return_page
        self.roster._rebuild_ui()
        await interaction.response.edit_message(
            content=None,
            embed=self.roster.build_embed(),
            view=self.roster,
        )

    # _rebuild_shop_buttons compat so _full_refresh works from dropdown returns
    def _rebuild_shop_buttons(self):
        self._rebuild()


# ─────────────────────────────────────────────────────────────────────────────
# Roster view
# ─────────────────────────────────────────────────────────────────────────────

class UpgradeRosterView(ui.View):

    def __init__(
        self,
        cards:             list[dict],   # already filtered: owned + not shiny
        viewer:            discord.Member,
        viewer_uid:        int,
        viewer_discord_id: str,
        start_page:        int = 0,
    ):
        super().__init__(timeout=180)
        self.all_cards         = cards
        self.viewer            = viewer
        self.viewer_uid        = viewer_uid
        self.viewer_discord_id = viewer_discord_id
        self.sort              = "alpha"
        self.cards             = _sort_cards(cards, self.sort)
        self.page              = start_page
        self._message          = None   # set after send so on_timeout can edit
        self._rebuild_ui()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self._message:
            try:
                await self._message.edit(view=self)
            except Exception:
                pass
            try:
                await self._message.channel.send(
                    "*⏰ Upgrade session timed out.*", delete_after=5
                )
            except Exception:
                pass

    def total_pages(self) -> int:
        return max(1, (len(self.cards) + PAGE_SIZE - 1) // PAGE_SIZE)

    def build_embed(self) -> discord.Embed:
        return build_upgrade_roster_embed(
            cards             = self.cards,
            page              = self.page,
            total_pages       = self.total_pages(),
            sort              = self.sort,
            viewer_discord_id = self.viewer_discord_id,
        )

    def _page_cards(self) -> list[dict]:
        start = self.page * PAGE_SIZE
        return self.cards[start:start + PAGE_SIZE]

    def _rebuild_ui(self):
        self.clear_items()
        page_cards = self._page_cards()

        # Row 0: index buttons
        for i in range(len(page_cards)):
            btn = ui.Button(
                emoji = NUMBER_EMOJIS[i],
                style = discord.ButtonStyle.primary,
                row   = 0,
            )
            btn.callback = self._make_open(i)
            self.add_item(btn)

        # Row 1: ⬅️  Sort  ➡️
        prev = ui.Button(
            emoji    = "⬅️",
            style    = discord.ButtonStyle.secondary,
            row      = 1,
            disabled = (self.page == 0),
        )
        prev.callback = self._prev
        self.add_item(prev)

        sort_btn = ui.Button(
            label = SORT_LABELS[self.sort],
            style = discord.ButtonStyle.primary,
            row   = 1,
        )
        sort_btn.callback = self._cycle_sort
        self.add_item(sort_btn)

        nxt = ui.Button(
            emoji    = "➡️",
            style    = discord.ButtonStyle.secondary,
            row      = 1,
            disabled = (self.page >= self.total_pages() - 1),
        )
        nxt.callback = self._next
        self.add_item(nxt)

    def _make_open(self, slot: int):
        async def callback(interaction: discord.Interaction):
            global_idx = self.page * PAGE_SIZE + slot
            if global_idx >= len(self.cards):
                await interaction.response.send_message("Card not found.", ephemeral=True)
                return

            card = dict(self.cards[global_idx])

            # Hydrate full character + story data
            try:
                from features.ctc.ctc_shop_view import _hydrate_one
                card = _hydrate_one(card)
                # Preserve collection fields
                src = self.cards[global_idx]
                for key in ("obtained_via", "obtained_at", "is_shiny", "shiny_at"):
                    if key in src:
                        card[key] = src[key]
            except Exception:
                pass

            detail = UpgradeCardView(
                cards       = self.cards,
                index       = global_idx,
                viewer      = self.viewer,
                viewer_uid  = self.viewer_uid,
                roster      = self,
                return_page = self.page,
            )
            # Swap hydrated card in
            detail.cards = list(self.cards)
            detail.cards[global_idx] = card
            # Pass message reference so detail's on_timeout can edit it
            detail._message = self._message

            await interaction.response.edit_message(
                embed=detail.build_embed(), view=detail
            )
        return callback

    async def _prev(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.page = min(self.total_pages() - 1, self.page + 1)
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _cycle_sort(self, interaction: discord.Interaction):
        idx        = SORT_CYCLE.index(self.sort)
        self.sort  = SORT_CYCLE[(idx + 1) % len(SORT_CYCLE)]
        self.cards = _sort_cards(self.all_cards, self.sort)
        self.page  = 0
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)