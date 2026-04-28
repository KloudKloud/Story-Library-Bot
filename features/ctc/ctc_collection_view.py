"""
ctc_collection_view.py
─────────────────────────────────────────────────────────────────────────────
Roster + detail views for /ctc collection and /ctc profile.

ROSTER LAYOUT
─────────────────────────────────────────────────────────────────────────────
  ✨  [Owner]'s Collection  ✨          [profile banner thumbnail]
  ── ✦ ─────────────────── ✦ ──
  1️⃣  Character Name  ✦  Species · Gender
      -# 📚 Story · 🃏 N collected · #1
  · · · · · · ·
  2️⃣  …
  ── ✦ ─────────────────── ✦ ──

  [Collection progress bar + milestone info]

  Row 0: 1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣
  Row 1: ⬅️  Sort  Pg. #/##  ➡️

DETAIL LAYOUT
─────────────────────────────────────────────────────────────────────────────
  Full CTC card embed (identical to shop card)

  Row 0: ⬅️  ✨ Shiny (disabled blue / lit up if owned)  ↩️ Return  ➡️
  Row 1: 🎬 Behind the Scenes... dropdown  (character cards only)
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import random
import discord
from discord import ui
from ui import TimeoutMixin


PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

SORT_CYCLE  = ["alpha", "alpha_z", "shiny_first", "char_first", "world_first", "author_first"]
SORT_LABELS = {
    "alpha":        "🔤 A–Z",
    "alpha_z":      "🔤 Z–A",
    "shiny_first":  "✨",
    "char_first":   "👤",
    "world_first":  "🌍",
    "author_first": "✍️",
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
    if sort == "alpha_z":
        return sorted(cards, key=lambda c: (c.get("name") or "").lower(), reverse=True)
    if sort == "shiny_first":
        return sorted(cards, key=lambda c: (not bool(c.get("is_shiny", 0)),
                                             (c.get("name") or "").lower()))
    if sort == "char_first":
        return sorted(cards, key=lambda c: (
            0 if c.get("card_type", "char") == "char" else 1,
            (c.get("name") or "").lower()
        ))
    if sort == "world_first":
        return sorted(cards, key=lambda c: (
            0 if c.get("card_type") == "world" else 1,
            (c.get("name") or "").lower()
        ))
    if sort == "author_first":
        return sorted(cards, key=lambda c: (
            0 if c.get("card_type") == "author" else 1,
            (c.get("name") or "").lower()
        ))
    # alpha (default)
    return sorted(cards, key=lambda c: (c.get("name") or "").lower())


# ─────────────────────────────────────────────────────────────────────────────
# Roster embed
# ─────────────────────────────────────────────────────────────────────────────

def build_collection_roster_embed(
    cards: list[dict],
    page: int,
    total_pages: int,
    owner_label: str,
    sort: str,
    viewer_discord_id: str | None = None,
    owned_count: int = 0,
    total_cards: int = 0,
    show_progress: bool = True,
) -> discord.Embed:
    from database import get_card_owner_count, get_world_card_owner_count

    start      = page * PAGE_SIZE
    page_cards = cards[start:start + PAGE_SIZE]
    spark      = _SPARKS[page % len(_SPARKS)]
    divider    = _DIVIDERS[page % len(_DIVIDERS)]

    _local_rng = random.Random(page + len(cards))
    r, g, b = _local_rng.choice(_COLORS)
    color   = discord.Color.from_rgb(r, g, b)

    entry_sep = "-# · · · · · · · · · ·"
    lines = [f"-# {divider}"]

    for i, c in enumerate(page_cards):
        global_num  = start + i + 1
        name        = c.get("name") or "Unknown"
        is_shiny    = bool(c.get("is_shiny", 0))
        ctype       = c.get("card_type", "char")

        if ctype == "author":
            pronouns   = c.get("pronouns") or ""
            tags_str   = f"✍️ *Author Card*" + (f"  ·  *{pronouns}*" if pronouns else "")
            collectors = 0
            try:
                from database import get_author_card_owner_count
                collectors = get_author_card_owner_count(c["id"])
            except Exception:
                pass
            story_count = c.get("story_count") or 0
            source_str  = f"✍️ {story_count} {'story' if story_count == 1 else 'stories'}"
            snippet_raw = c.get("bio") or ""
        elif ctype == "world":
            world_type = c.get("world_type") or "World Card"
            tags_str   = f"🌍 *{world_type}*"
            collectors = get_world_card_owner_count(c["id"])
            source_str = f"📚 {c.get('story_title') or '?'}"
            snippet_raw = c.get("lore") or c.get("description") or ""
        else:
            species    = c.get("species") or ""
            gender     = c.get("gender") or ""
            tags       = "  ·  ".join(t for t in [gender, species] if t)
            tags_str   = f"*{tags}*" if tags else ""
            collectors = get_card_owner_count(c["id"])
            source_str = f"📚 {c.get('story_title') or '?'}"
            snippet_raw = c.get("personality") or c.get("lore") or ""

        shiny_tag = "  ✨ **SHINY**" if is_shiny else ""

        # Obtained timestamp — localized via Discord dynamic timestamp
        obtained_str = ""
        obtained_at  = c.get("obtained_at")
        if obtained_at:
            try:
                import datetime
                dt = datetime.datetime.fromisoformat(obtained_at).replace(
                    tzinfo=datetime.timezone.utc
                )
                obtained_str = f"  ·  <t:{int(dt.timestamp())}:d>"
            except Exception:
                pass

        # Short lore/bio snippet
        snippet_line = ""
        if snippet_raw:
            snippet = snippet_raw.replace("\n", " ").strip()
            if len(snippet) > 85:
                snippet = snippet[:82] + "…"
            snippet_line = f"\n-# *{snippet}*"

        lines.append(
            f"{NUMBER_EMOJIS[i]}  **{name}**"
            + (f"  ✦  {tags_str}" if tags_str else "")
            + shiny_tag
            + f"\n-# {source_str}  ·  🃏 {collectors} collected{obtained_str}"
            + snippet_line
        )
        if i < len(page_cards) - 1:
            lines.append(entry_sep)

    lines.append(f"-# {divider}")

    embed = discord.Embed(
        title=f"{spark}  {owner_label}'s Collection  {spark}",
        description="\n".join(lines),
        color=color,
    )

    # Thumbnail — profile banner
    if viewer_discord_id:
        try:
            from database import get_profile_by_discord_id
            profile = get_profile_by_discord_id(viewer_discord_id)
            img = profile.get("image_url") if profile else None
            if img and img.startswith("http"):
                embed.set_thumbnail(url=img)
        except Exception:
            pass

    # Collection progress bar — only shown on your own collection, not peek
    if show_progress and total_cards > 0:
        try:
            from database import MILESTONE_INTERVAL, MILESTONE_BONUS
        except Exception:
            MILESTONE_INTERVAL, MILESTONE_BONUS = 10, 500

        embed.add_field(
            name="\u200b",
            value="✦ ══════════════════════════ ✦",
            inline=False,
        )

        pct     = min(owned_count / total_cards, 1.0)
        steps   = 10
        filled  = int(pct * steps)
        if filled >= steps:
            bar = "✦ " * steps + "✨"
        elif filled == 0:
            bar = "· " * steps
        else:
            bar = "✦ " * filled + "✨ " + "· " * (steps - filled)
        bar      = bar.strip()
        pct_str  = f"{int(pct * 100)}%"
        next_ms  = ((owned_count // MILESTONE_INTERVAL) + 1) * MILESTONE_INTERVAL
        to_next  = next_ms - owned_count

        shiny_count  = sum(1 for c in cards if c.get("is_shiny"))
        world_count  = sum(1 for c in cards if c.get("card_type") == "world")
        author_count = sum(1 for c in cards if c.get("card_type") == "author")
        char_count   = owned_count - world_count - author_count

        embed.add_field(
            name="✨  𝐂𝐎𝐋𝐋𝐄𝐂𝐓𝐈𝐎𝐍 𝐏𝐑𝐎𝐆𝐑𝐄𝐒𝐒",
            value=(
                f"{bar}  **{pct_str}**\n"
                f"-# {owned_count} / {total_cards} cards  ·  "
                f"✨ {shiny_count} shiny  ·  "
                f"👤 {char_count}  ·  🌍 {world_count}  ·  ✍️ {author_count}  ·  "
                f"💎 +{MILESTONE_BONUS} in **{to_next}** more "
                f"card{'s' if to_next != 1 else ''}"
            ),
            inline=False,
        )

    embed.set_footer(
        text=f"Page {page + 1} of {total_pages}  ·  "
             f"{len(cards)} card{'s' if len(cards) != 1 else ''}  ·  {SORT_LABELS[sort]}"
    )
    return embed


# ─────────────────────────────────────────────────────────────────────────────
# Jump modal
# ─────────────────────────────────────────────────────────────────────────────

class _CollectionJumpModal(discord.ui.Modal, title="Jump to Page"):
    page_num = discord.ui.TextInput(
        label="Page number", placeholder="e.g. 3", max_length=4, required=True
    )

    def __init__(self, roster: "CollectionRosterView"):
        super().__init__()
        self.roster = roster

    async def on_submit(self, interaction: discord.Interaction):
        try:
            p = int(self.page_num.value.strip()) - 1
            p = max(0, min(p, self.roster.total_pages() - 1))
        except ValueError:
            await interaction.response.send_message(
                "❌ Enter a valid page number.", ephemeral=True, delete_after=3
            )
            return
        self.roster.page = p
        self.roster._rebuild_ui()
        await interaction.response.edit_message(
            embed=self.roster.build_embed(), view=self.roster
        )


# ─────────────────────────────────────────────────────────────────────────────
# Detail view — full CTC card with shiny toggle + Behind the Scenes
# ─────────────────────────────────────────────────────────────────────────────

class CollectionDetailView(TimeoutMixin, ui.View):
    """
    Shows a single CTC card from the collection.

    Row 0: ⬅️  ✨ Shiny Toggle  ↩️ Return  ➡️
    Row 1: 🎬 Behind the Scenes... dropdown  (character cards only)
    """

    def __init__(
        self,
        cards:       list[dict],
        index:       int,
        viewer:      discord.Member,
        roster:      "CollectionRosterView",
        return_page: int,
        total_cards: int = 0,
    ):
        super().__init__(timeout=300)
        self.cards        = cards
        self.index        = index
        self.viewer       = viewer
        self.roster       = roster
        self.return_page  = return_page
        self.total_cards  = total_cards
        self._shiny_view  = bool(self.cards[index].get("is_shiny", 0))
        self._rebuild_ui()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    # ── helpers ──────────────────────────────────────────────────────────────

    def current(self) -> dict:
        return self.cards[self.index]

    def _has_shiny(self) -> bool:
        return bool(self.current().get("is_shiny", 0))

    def _full_card(self) -> dict:
        """Return a fully hydrated card dict for the current index."""
        minimal = self.current()
        ctype   = minimal.get("card_type", "char")
        if ctype == "author":
            return minimal  # already fully hydrated from get_full_collection
        if ctype == "world":
            from database import get_world_card_by_id
            full = get_world_card_by_id(minimal["id"])
        else:
            from database import get_character_by_id
            full = get_character_by_id(minimal["id"])
        if full:
            full = dict(full)
            for key in ("obtained_via", "obtained_at", "is_shiny",
                        "shiny_at", "story_title", "cover_url", "author", "card_type"):
                if key in minimal:
                    full[key] = minimal[key]
            return full
        return minimal

    def build_embed(self) -> discord.Embed:
        card  = self._full_card()
        ctype = card.get("card_type", "char")
        shiny = self._shiny_view and bool(card.get("is_shiny", 0))

        if ctype == "author":
            from embeds.author_card_embed import build_author_card_embed
            return build_author_card_embed(
                card, self.viewer.id,
                index = self.index + 1,
                total = len(self.cards),
            )
        if ctype == "world":
            from embeds.world_card_embed import build_world_card_embed
            return build_world_card_embed(
                card, self.viewer.id,
                shiny = shiny,
                index = self.index + 1,
                total = len(self.cards),
            )
        from database import get_user_id
        _uid = get_user_id(str(self.viewer.id))
        from embeds.ctc_card_embed import build_ctc_card_embed
        embed, _ = build_ctc_card_embed(
            card,
            _uid,
            viewer       = self.viewer,
            shiny        = shiny,
            obtained_via = card.get("obtained_via"),
            obtained_at  = card.get("obtained_at"),
            index        = self.index + 1,
            total        = len(self.cards),
        )
        return embed

    # ── UI builder ────────────────────────────────────────────────────────────

    def _rebuild_ui(self):
        self.clear_items()
        has_shiny = self._has_shiny()
        ctype     = self.current().get("card_type", "char")

        # ── Row 0 ─────────────────────────────────────────────────────────────
        prev = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index == 0)
        )
        prev.callback = self._prev
        self.add_item(prev)

        shiny_btn = ui.Button(
            label="✨ Shiny" if not self._shiny_view else "✦ Normal",
            emoji="🌟" if has_shiny else None,
            style=discord.ButtonStyle.primary,
            disabled=not has_shiny,
            row=0,
        )
        shiny_btn.callback = self._toggle_shiny
        self.add_item(shiny_btn)

        ret = ui.Button(label="↩️ Return", style=discord.ButtonStyle.success, row=0)
        ret.callback = self._return
        self.add_item(ret)

        nxt = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index >= len(self.cards) - 1)
        )
        nxt.callback = self._next
        self.add_item(nxt)

        # ── Row 1: Behind the Scenes dropdown (character cards only) ──────────
        if ctype == "char":
            from embeds.ctc_card_embed import _BehindTheScenesSelect
            self.add_item(
                _BehindTheScenesSelect(
                    char=self.current(),
                    viewer=self.viewer,
                    ctc_view=self,
                    row=1,
                )
            )

    # ── Callbacks ─────────────────────────────────────────────────────────────

    async def _prev(self, interaction: discord.Interaction):
        self.index      -= 1
        self._shiny_view = bool(self.current().get("is_shiny", 0))
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.index      += 1
        self._shiny_view = bool(self.current().get("is_shiny", 0))
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _toggle_shiny(self, interaction: discord.Interaction):
        self._shiny_view = not self._shiny_view
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _return(self, interaction: discord.Interaction):
        self.roster.page = self.return_page
        self.roster._rebuild_ui()
        await interaction.response.edit_message(
            embed=self.roster.build_embed(), view=self.roster
        )

    # ── CTCCardView compatibility (for _BehindTheScenesSelect / _full_refresh) ─

    def _refresh(self):
        self._rebuild_ui()

    def _build_embed(self) -> discord.Embed:
        return self.build_embed()

    @property
    def viewer_uid(self) -> int:
        return self.viewer.id

    @property
    def cards_list(self) -> list[dict]:
        return self.cards


# ─────────────────────────────────────────────────────────────────────────────
# Roster view
# ─────────────────────────────────────────────────────────────────────────────

class CollectionRosterView(TimeoutMixin, ui.View):

    def __init__(
        self,
        cards:             list[dict],
        viewer:            discord.Member,
        owner_label:       str,
        viewer_discord_id: str,
        total_cards:       int = 0,
        start_page:        int = 0,
        show_progress:     bool = True,
    ):
        super().__init__(timeout=300)
        self.all_cards         = cards
        self.viewer            = viewer
        self.owner_label       = owner_label
        self.viewer_discord_id = viewer_discord_id
        self.total_cards       = total_cards
        self.show_progress     = show_progress
        self.sort              = "alpha"
        self.cards             = _sort_cards(cards, self.sort)
        self.page              = start_page
        self._rebuild_ui()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    def total_pages(self) -> int:
        return max(1, (len(self.cards) + PAGE_SIZE - 1) // PAGE_SIZE)

    def build_embed(self) -> discord.Embed:
        return build_collection_roster_embed(
            cards             = self.cards,
            page              = self.page,
            total_pages       = self.total_pages(),
            owner_label       = self.owner_label,
            sort              = self.sort,
            viewer_discord_id = self.viewer_discord_id,
            owned_count       = len(self.cards),
            total_cards       = self.total_cards,
            show_progress     = self.show_progress,
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
                emoji=NUMBER_EMOJIS[i],
                style=discord.ButtonStyle.primary,
                row=0,
            )
            btn.callback = self._make_open(i)
            self.add_item(btn)

        # Row 1: ⬅️  Sort  Pg. #/##  ➡️
        prev = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary,
            row=1, disabled=(self.page == 0)
        )
        prev.callback = self._prev
        self.add_item(prev)

        sort_btn = ui.Button(
            label=SORT_LABELS[self.sort],
            style=discord.ButtonStyle.primary,
            row=1,
        )
        sort_btn.callback = self._cycle_sort
        self.add_item(sort_btn)

        jump_btn = ui.Button(
            label    = f"Pg. {self.page + 1}/{self.total_pages()}",
            style    = discord.ButtonStyle.success,
            row      = 1,
            disabled = (self.total_pages() == 1),
        )
        jump_btn.callback = self._jump
        self.add_item(jump_btn)

        nxt = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=1, disabled=(self.page >= self.total_pages() - 1)
        )
        nxt.callback = self._next
        self.add_item(nxt)

    def _make_open(self, slot: int):
        async def callback(interaction: discord.Interaction):
            global_idx = self.page * PAGE_SIZE + slot
            if global_idx >= len(self.cards):
                await interaction.response.send_message("Card not found.", ephemeral=True)
                return

            detail = CollectionDetailView(
                cards       = self.cards,
                index       = global_idx,
                viewer      = self.viewer,
                roster      = self,
                return_page = self.page,
                total_cards = self.total_cards,
            )

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

    async def _jump(self, interaction: discord.Interaction):
        await interaction.response.send_modal(_CollectionJumpModal(self))
