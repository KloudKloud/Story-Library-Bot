"""
char_search_view.py  —  /char search roster + detail views.

Roster:
  Row 0: 1️⃣–5️⃣ index buttons (blue)
  Row 1: ⬅️  sort (blue)  Jump to...  ➡️

Detail:
  Row 0: ⬅️  ✦ Favorite  📜 Lore  ↩️ Return  ➡️
"""

import discord
from discord import ui
from ui import TimeoutMixin

from embeds.character_embeds import build_character_card
from database import (
    get_character_by_id,
    get_characters_by_story,
    get_user_id,
    is_favorite_character,
    add_favorite_character,
    remove_favorite_character,
    get_character_fav_count,
    get_card_owner_count,
)

PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

SORT_CYCLE  = ["alpha", "favs", "collected", "recent"]
SORT_LABELS = {
    "alpha":     "🔤 A–Z",
    "favs":      "💖 Most",
    "collected": "🃏 Most",
    "recent":    "🕐 Newest",
}

# Sparkle palette matching other roster views
_SPARKS    = ["🧬", "🌸", "⭐", "💎", "🌺", "✨", "🔮", "💫"]
_DIVIDERS  = [
    "✦ · · ✦ · · ✦ · · ✦",
    "· ˖ ✦ ˖ · ˖ ✦ ˖ ·",
    "⋆ ˚ ✦ ˚ ⋆ · ⋆ ˚ ✦",
    "─ ✦ ─────────── ✦ ─",
]
_COLORS = [
    (150, 255, 180), (186, 104, 200), (121, 134, 203), (100, 181, 246),
    (255, 183, 197), (130, 210, 255), (77, 182, 172),  (149, 117, 205),
]


# ─────────────────────────────────────────────────
# Sort helper
# ─────────────────────────────────────────────────

def _sort_chars(chars: list, sort: str) -> list:
    if sort == "favs":
        return sorted(chars, key=lambda c: get_character_fav_count(c["id"]), reverse=True)
    if sort == "collected":
        return sorted(chars, key=lambda c: get_card_owner_count(c["id"]), reverse=True)
    if sort == "recent":
        return sorted(chars, key=lambda c: c["id"], reverse=True)
    # alpha — A-Z by name
    return sorted(chars, key=lambda c: c.get("name", "").lower())


# ─────────────────────────────────────────────────
# Jump modal
# ─────────────────────────────────────────────────

class CharSearchJumpModal(discord.ui.Modal):

    page_num = discord.ui.TextInput(
        label="Page number", placeholder="e.g. 3", max_length=4, required=True
    )

    def __init__(self, roster: "CharSearchRosterView"):
        super().__init__(title="Jump to Page")
        self.roster = roster

    async def on_submit(self, interaction: discord.Interaction):
        try:
            p = int(self.page_num.value) - 1
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


# ─────────────────────────────────────────────────
# Roster embed
# ─────────────────────────────────────────────────

def build_char_search_embed(chars: list, page: int, total_pages: int, sort: str) -> discord.Embed:
    import random
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
        name        = c.get("name", "?")
        story       = c.get("story_title") or "?"
        author      = c.get("author") or "?"
        fav_count   = get_character_fav_count(c["id"])
        card_count  = get_card_owner_count(c["id"])
        lines.append(
            f"{NUMBER_EMOJIS[i]}  **{name}**\n"
            f"-# 📖 {story}  ·  ✍️ {author}  ·  💖 {fav_count} favs  ·  🃏 {card_count} collected"
        )
        if i < len(chunk) - 1:
            lines.append(entry_sep)

    lines.append(f"-# {divider}")

    embed = discord.Embed(
        title=f"{spark}  Character Search  {spark}",
        description="\n".join(lines),
        color=color
    )
    embed.set_footer(
        text=f"Page {page+1} of {total_pages}  ·  {len(chars)} character{'s' if len(chars) != 1 else ''}  ·  {SORT_LABELS[sort]}"
    )
    return embed


# ─────────────────────────────────────────────────
# Roster view
# ─────────────────────────────────────────────────

class CharSearchRosterView(TimeoutMixin, ui.View):

    def __init__(self, chars: list, viewer: discord.Member):
        super().__init__(timeout=300)
        self.all_chars = chars
        self.viewer    = viewer
        self.sort      = "alpha"
        self.page      = 0
        self._sorted   = _sort_chars(chars, self.sort)
        self._rebuild_ui()

    def total_pages(self):
        return max(1, (len(self._sorted) + PAGE_SIZE - 1) // PAGE_SIZE)

    def build_embed(self):
        return build_char_search_embed(self._sorted, self.page, self.total_pages(), self.sort)

    def _page_items(self):
        start = self.page * PAGE_SIZE
        return self._sorted[start:start + PAGE_SIZE]

    def _rebuild_ui(self):
        self.clear_items()
        chunk = self._page_items()

        # Row 0: blue index buttons
        for i, _ in enumerate(chunk):
            btn = ui.Button(
                emoji=NUMBER_EMOJIS[i],
                style=discord.ButtonStyle.primary,
                row=0
            )
            btn.callback = self._make_open(self.page * PAGE_SIZE + i)
            self.add_item(btn)

        # Row 1: ⬅️  sort (blue)  Jump to...  ➡️
        prev_btn = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary,
            row=1, disabled=(self.page == 0)
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        sort_btn = ui.Button(
            label=SORT_LABELS[self.sort],
            style=discord.ButtonStyle.primary,
            row=1
        )
        sort_btn.callback = self._cycle_sort
        self.add_item(sort_btn)

        jump_btn = ui.Button(
            label="Jump to...", style=discord.ButtonStyle.success, row=1
        )
        jump_btn.callback = self._jump
        self.add_item(jump_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=1, disabled=(self.page >= self.total_pages() - 1)
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

    def _make_open(self, global_index: int):
        async def callback(interaction: discord.Interaction):
            if global_index >= len(self._sorted):
                await interaction.response.send_message("Not found.", ephemeral=True)
                return
            detail = CharSearchDetailView(
                chars=self._sorted,   # full sorted list — arrows navigate all characters
                index=global_index,
                viewer=self.viewer,
                roster=self,
                return_page=self.page
            )
            await interaction.response.edit_message(
                embed=detail.build_embed(), view=detail
            )
        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.", ephemeral=True, delete_after=5
            )
            return False
        return True

    async def _prev(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.page = min(self.total_pages() - 1, self.page + 1)
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _cycle_sort(self, interaction: discord.Interaction):
        idx         = SORT_CYCLE.index(self.sort)
        self.sort   = SORT_CYCLE[(idx + 1) % len(SORT_CYCLE)]
        self._sorted = _sort_chars(self.all_chars, self.sort)
        self.page   = 0
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _jump(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CharSearchJumpModal(self))


# ─────────────────────────────────────────────────
# Detail view
# Row 0: ⬅️  ✦ Favorite  📜 Lore  ↩️ Return  ➡️
# ─────────────────────────────────────────────────

class CharSearchDetailView(TimeoutMixin, ui.View):

    def __init__(self, chars: list, index: int,
                 viewer: discord.Member,
                 roster: CharSearchRosterView = None,
                 return_page: int = 0):
        super().__init__(timeout=300)
        self.chars       = chars
        self.index       = index
        self.viewer      = viewer
        self.roster      = roster
        self.return_page = return_page
        self._rebuild_ui()

    def current(self):
        return self.chars[self.index]

    def _hydrated(self) -> dict:
        """Return full character dict for the current entry, hydrating if needed."""
        c = self.current()
        if c.get("personality") is not None or c.get("image_url") is not None:
            return c  # already full
        full = get_character_by_id(c["id"])
        if full:
            # carry over roster-only keys
            full["story_title"] = c.get("story_title")
            full["author"]      = c.get("author")
            return full
        return c

    def build_embed(self) -> discord.Embed:
        return build_character_card(
            self._hydrated(),
            viewer=self.viewer,
            index=self.index + 1,
            total=len(self.chars)
        )

    def _rebuild_ui(self):
        self.clear_items()
        char  = self._hydrated()
        total = len(self.chars)
        uid   = get_user_id(str(self.viewer.id))
        faved = is_favorite_character(uid, char["id"]) if uid else False

        prev_btn = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index == 0)
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        fav_btn = ui.Button(
            label="✦ Unstar" if faved else "✦ Favorite",
            style=discord.ButtonStyle.primary,
            row=0
        )
        fav_btn.callback = self._fav
        self.add_item(fav_btn)

        lore_btn = ui.Button(
            label="📜 Lore", style=discord.ButtonStyle.primary,
            row=0, disabled=not bool(char.get("lore"))
        )
        lore_btn.callback = self._lore
        self.add_item(lore_btn)

        if self.roster:
            return_btn = ui.Button(
                label="↩️ Return", style=discord.ButtonStyle.success, row=0
            )
            return_btn.callback = self._return
            self.add_item(return_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index >= total - 1)
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

        # ── Row 1: More [char name] dropdown ──────────────────────
        char_name   = char.get("name", "this character")
        story_id    = char.get("story_id")
        author_name = char.get("author") or "the author"

        options = []
        if story_id:
            story_title = char.get("story_title") or "linked story"
            options.append(discord.SelectOption(
                label=f"See {char_name}'s story"[:100],
                emoji="📖",
                value=f"story:{story_id}"
            ))
            options.append(discord.SelectOption(
                label=f"See {author_name}'s profile"[:100],
                emoji="✍️",
                value=f"author:{story_id}"
            ))

        if options:
            more_select = ui.Select(
                placeholder=f"✨ More {char_name}...",
                options=options,
                row=1
            )
            more_select.callback = self._more
            self.add_item(more_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.", ephemeral=True, delete_after=5
            )
            return False
        return True

    async def _prev(self, interaction: discord.Interaction):
        self.index = max(0, self.index - 1)
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.index = min(len(self.chars) - 1, self.index + 1)
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _fav(self, interaction: discord.Interaction):
        from features.characters.views.favorite_helpers import handle_fav_toggle
        char = self._hydrated()
        async def _refresh(i):
            self._rebuild_ui()
            await i.response.edit_message(content=None, embed=self.build_embed(), view=self)
        await handle_fav_toggle(interaction, char, _refresh)

    async def _lore(self, interaction: discord.Interaction):
        from embeds.character_embeds import build_lore_embed
        char = self._hydrated()
        lore = char.get("lore")
        if not lore:
            await interaction.response.send_message("No lore written yet.", ephemeral=True, delete_after=5)
            return
        await interaction.response.send_message(embed=build_lore_embed(char["name"], lore), ephemeral=True)

    async def _more(self, interaction: discord.Interaction):
        select = next((c for c in self.children if isinstance(c, ui.Select)), None)
        value  = select.values[0] if select and select.values else ""

        if value.startswith("story:"):
            story_id = int(value.split(":")[1])
            from features.fanart.views.fanart_search_view import SearchStoryView
            view = SearchStoryView(story_id=story_id, viewer=interaction.user, back_detail=self)
            embed = view.build_story_embed()
            if not embed:
                await interaction.response.send_message(
                    "Story not found.", ephemeral=True, delete_after=3
                )
                return
            await interaction.response.edit_message(embed=embed, view=view)
            return

        if value.startswith("author:"):
            story_id = int(value.split(":")[1])
            from database import get_discord_id_by_story, get_stories_by_discord_user
            discord_id = get_discord_id_by_story(story_id)
            if not discord_id:
                await interaction.response.send_message(
                    "Author not found.", ephemeral=True, delete_after=3
                )
                return
            target = interaction.guild.get_member(int(discord_id))
            if not target:
                try:
                    target = await interaction.guild.fetch_member(int(discord_id))
                except Exception:
                    pass
            if not target:
                await interaction.response.send_message(
                    "Couldn't find that author in this server.", ephemeral=True, delete_after=3
                )
                return
            stories = get_stories_by_discord_user(discord_id)
            from features.fanart.views.fanart_search_view import SearchAuthorView
            view = SearchAuthorView(
                stories=stories, viewer=interaction.user,
                target_user=target, back_detail=self
            )
            await interaction.response.edit_message(embed=view.generate_bio_embed(), view=view)
            return

    async def _return(self, interaction: discord.Interaction):
        self.roster.page = self.return_page
        self.roster._rebuild_ui()
        await interaction.response.edit_message(
            embed=self.roster.build_embed(), view=self.roster
        )