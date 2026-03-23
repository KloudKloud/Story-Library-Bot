"""
ctc_shop_view.py  —  /ctc shop browse view.

Roster layout:
  Row 0: 1️⃣–5️⃣  index buttons
  Row 1: "Specific Search..." dropdown  (Character Name | Story Name | Full Shop)
  Row 2: ⬅️  sort (A–Z / Most Collected / Least Collected)  ➡️

Detail (ShopCardView — unchanged, lives in ctc_commands.py):
  Row 0: 📜 Lore  |  Buy 💎 3,500  |  ↩️ Return
"""

import discord
from discord import ui
import random

from database import (
    get_all_characters,
    get_characters_by_story,
    get_character_by_id,
    get_card_owner_count,
    get_all_stories_sorted,
)
from ui import TimeoutMixin

PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
CRYSTAL       = "💎"

SORT_CYCLE  = ["alpha", "most", "least"]
SORT_LABELS = {
    "alpha": "🔤 A–Z",
    "most":  "🃏 Most Collected",
    "least": "🃏 Least Collected",
}

# Sparkle palette
_SPARKS   = ["🛒", "💎", "✨", "🌸", "⭐", "🔮", "💫"]
_DIVIDERS = [
    "✦ · · ✦ · · ✦ · · ✦",
    "· ˖ ✦ ˖ · ˖ ✦ ˖ ·",
    "⋆ ˚ ✦ ˚ ⋆ · ⋆ ˚ ✦",
    "─ ✦ ─────────── ✦ ─",
]
_COLORS = [
    (100, 181, 246), (186, 104, 200), (121, 134, 203),
    (77, 182, 172),  (149, 117, 205), (255, 202, 40),
    (129, 199, 132), (240, 98, 146),
]


# ─────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────

def _fmt_balance(bal: int) -> str:
    return f"{CRYSTAL} **{bal:,}** crystals"


def _sort_chars(chars: list, sort: str) -> list:
    if sort == "most":
        return sorted(chars, key=lambda c: get_card_owner_count(c["id"]), reverse=True)
    if sort == "least":
        return sorted(chars, key=lambda c: get_card_owner_count(c["id"]))
    return sorted(chars, key=lambda c: (c.get("name") or "").lower())


def _hydrate_one(c: dict) -> dict:
    """Fetch full dict for a single minimal character dict, preserving cover_url."""
    from database import get_character_by_id, get_story_by_character
    full = get_character_by_id(c["id"])
    if not full:
        return c
    full["story_title"] = c.get("story_title") or full.get("story_title") or "?"
    full["author"]      = c.get("author")      or full.get("author")      or "?"
    # cover_url is not on the characters table — must look up via story
    cover = c.get("cover_url")
    if not cover:
        try:
            story = get_story_by_character(c["id"])
            if story:
                # get_story_by_character returns a sqlite3.Row — use bracket access
                cover = story["cover_url"]
        except Exception:
            pass
    full["cover_url"] = cover
    return full


def _hydrate(minimal_chars: list) -> list:
    """Fetch full dicts for a list of minimal character dicts."""
    return [_hydrate_one(c) for c in minimal_chars]


# ─────────────────────────────────────────────────
# Modals
# ─────────────────────────────────────────────────

class CharNameSearchModal(discord.ui.Modal):
    query = discord.ui.TextInput(
        label="Character name",
        placeholder="e.g. Inferno  (partial match OK)",
        max_length=100,
        required=True
    )

    def __init__(self, shop_view: "ShopView"):
        super().__init__(title="Search by Character Name")
        self.shop_view = shop_view

    async def on_submit(self, interaction: discord.Interaction):
        needle = self.query.value.strip().lower()
        all_chars = get_all_characters()
        matches = [c for c in all_chars if needle in c["name"].lower()]

        if not matches:
            await interaction.response.send_message(
                f"❌ No characters found matching **\"{self.query.value}\"**.",
                ephemeral=True, delete_after=5
            )
            return

        hydrated = _hydrate(matches)
        self.shop_view.set_chars(hydrated, mode="char_search")
        await interaction.response.edit_message(
            embed=self.shop_view.build_embed(), view=self.shop_view
        )


class StoryNameSearchModal(discord.ui.Modal):
    query = discord.ui.TextInput(
        label="Story title",
        placeholder="e.g. Between Two Worlds  (fuzzy match OK)",
        max_length=200,
        required=True
    )

    def __init__(self, shop_view: "ShopView"):
        super().__init__(title="Search by Story Name")
        self.shop_view = shop_view

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.query.value.strip()

        def _norm(s: str) -> str:
            return s.lower().replace("&", "and").replace(" ", "")

        needle = _norm(raw)
        all_stories = get_all_stories_sorted()

        match = None
        for s in all_stories:
            if _norm(s[0]) == needle:
                match = s
                break
        if not match:
            for s in all_stories:
                norm = _norm(s[0])
                if needle in norm or norm in needle:
                    match = s
                    break

        if not match:
            await interaction.response.send_message(
                f"❌ No story found matching **\"{raw}\"**.\n"
                f"-# Try a shorter part of the title, or swap `&` for `and`.",
                ephemeral=True, delete_after=6
            )
            return

        story_id   = match[9]
        story_chars = get_characters_by_story(story_id)
        if not story_chars:
            await interaction.response.send_message(
                f"No characters found for **{match[0]}**.",
                ephemeral=True, delete_after=5
            )
            return

        hydrated = _hydrate(story_chars)
        self.shop_view.set_chars(hydrated, mode="story_search")
        await interaction.response.edit_message(
            embed=self.shop_view.build_embed(), view=self.shop_view
        )


# ─────────────────────────────────────────────────
# Roster embed
# ─────────────────────────────────────────────────

def build_shop_embed(chars: list, page: int, total_pages: int,
                     sort: str, balance: int, owned_ids: set) -> discord.Embed:
    start   = page * PAGE_SIZE
    chunk   = chars[start:start + PAGE_SIZE]
    spark   = _SPARKS[page % len(_SPARKS)]
    divider = _DIVIDERS[page % len(_DIVIDERS)]

    _local_rng = random.Random(page + len(chars))
    r, g, b = _local_rng.choice(_COLORS)
    color   = discord.Color.from_rgb(r, g, b)

    entry_sep = "-# · · · · · · · · · ·"
    lines = [f"-# {divider}"]

    for i, c in enumerate(chunk):
        owned       = c["id"] in owned_ids
        collectors  = get_card_owner_count(c["id"])
        story       = c.get("story_title") or "?"
        status      = "✅ Owned" if owned else f"{CRYSTAL} 3,500"
        lines.append(
            f"{NUMBER_EMOJIS[i]}  **{c['name']}**\n"
            f"-# 📖 {story}  ·  🃏 {collectors} collected  ·  {status}"
        )
        if i < len(chunk) - 1:
            lines.append(entry_sep)

    lines.append(f"-# {divider}")

    embed = discord.Embed(
        title=f"{spark}  CTC Shop  {spark}",
        description="\n".join(lines),
        color=color
    )
    embed.set_footer(
        text=(
            f"{_fmt_balance(balance)}  ·  "
            f"Page {page+1} of {total_pages}  ·  {len(chars)} cards  ·  "
            f"{SORT_LABELS[sort]}"
        )
    )
    return embed


# ─────────────────────────────────────────────────
# Shop roster view
# ─────────────────────────────────────────────────

class ShopView(TimeoutMixin, ui.View):
    """
    mode:
      "full"         — full shop, dropdown shows Character Name + Story Name
      "char_search"  — filtered by name, dropdown shows Full Shop instead
      "story_search" — filtered by story, dropdown shows Full Shop instead
    """

    def __init__(self, all_chars: list, buyer_uid: int,
                 buyer_db_id: int, balance: int, owned_ids: set):
        super().__init__(timeout=300)
        self.all_chars    = all_chars          # master full list
        self.buyer_uid    = buyer_uid
        self.buyer_db_id  = buyer_db_id
        self.balance      = balance
        self.owned_ids    = owned_ids
        self.sort         = "alpha"
        self.page         = 0
        self.mode         = "full"
        self._sorted      = _sort_chars(all_chars, self.sort)
        self._build_ui()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.buyer_uid:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    # ── Public helpers ────────────────────────────

    def set_chars(self, chars: list, mode: str):
        self.mode    = mode
        self._sorted = _sort_chars(chars, self.sort)
        self.page    = 0
        self._build_ui()

    def total_pages(self):
        return max(1, (len(self._sorted) + PAGE_SIZE - 1) // PAGE_SIZE)

    def build_embed(self) -> discord.Embed:
        return build_shop_embed(
            self._sorted, self.page, self.total_pages(),
            self.sort, self.balance, self.owned_ids
        )

    # ── UI builder ────────────────────────────────

    def _build_ui(self):
        self.clear_items()
        start = self.page * PAGE_SIZE
        chunk = self._sorted[start:start + PAGE_SIZE]

        # Row 0: index buttons
        for i, c in enumerate(chunk):
            btn = ui.Button(
                emoji=NUMBER_EMOJIS[i],
                style=discord.ButtonStyle.primary,
                row=0
            )
            btn.callback = self._make_open(c)
            self.add_item(btn)

        # Row 1: Specific Search... dropdown
        search_options = []
        if self.mode == "full":
            search_options.append(discord.SelectOption(
                label="Character Name",
                emoji="🧬",
                value="search_char",
                description="Find cards by character name"
            ))
            search_options.append(discord.SelectOption(
                label="Story Name",
                emoji="📖",
                value="search_story",
                description="Browse cards from a specific story"
            ))
        else:
            search_options.append(discord.SelectOption(
                label="Full Shop",
                emoji="🛒",
                value="full_shop",
                description="Return to browsing all cards"
            ))

        search_select = ui.Select(
            placeholder="🔍 Specific Search...",
            options=search_options,
            row=1
        )
        search_select.callback = self._search
        self.add_item(search_select)

        # Row 2: ⬅️  sort  ➡️
        prev_btn = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary,
            row=2, disabled=(self.page == 0)
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        sort_btn = ui.Button(
            label=SORT_LABELS[self.sort],
            style=discord.ButtonStyle.primary,
            row=2
        )
        sort_btn.callback = self._cycle_sort
        self.add_item(sort_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=2, disabled=(self.page >= self.total_pages() - 1)
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

    # ── Callbacks ─────────────────────────────────

    def _make_open(self, char: dict):
        async def callback(interaction: discord.Interaction):
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

            from embeds.ctc_card_embed import build_ctc_card_embed
            from features.ctc.ctc_commands import ShopCardView
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

    async def _search(self, interaction: discord.Interaction):
        select = next((c for c in self.children if isinstance(c, ui.Select)), None)
        value  = select.values[0] if select and select.values else ""

        if value == "search_char":
            await interaction.response.send_modal(CharNameSearchModal(self))
        elif value == "search_story":
            await interaction.response.send_modal(StoryNameSearchModal(self))
        elif value == "full_shop":
            self.set_chars(self.all_chars, mode="full")
            await interaction.response.edit_message(
                embed=self.build_embed(), view=self
            )

    async def _prev(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self._build_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.page = min(self.total_pages() - 1, self.page + 1)
        self._build_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _cycle_sort(self, interaction: discord.Interaction):
        idx        = SORT_CYCLE.index(self.sort)
        self.sort  = SORT_CYCLE[(idx + 1) % len(SORT_CYCLE)]
        # Re-sort current filtered list (not all_chars, preserve filter)
        self._sorted = _sort_chars(self._sorted, self.sort)
        self.page  = 0
        self._build_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)