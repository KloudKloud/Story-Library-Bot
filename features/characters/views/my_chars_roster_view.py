import discord
from discord import ui

from embeds.character_embeds import build_character_card
from database import (
    get_character_by_id,
    get_story_by_character,
    get_discord_id_by_story,
    get_stories_by_discord_user,
    get_user_id,
    get_favorite_characters,
    add_favorite_character,
    remove_favorite_character,
    is_favorite_character,
    get_fanart_by_character,
    get_character_fav_count,
    get_card_owner_count,
)


PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"]

SORT_CYCLE  = ["alpha", "favs", "collected", "recent"]
SORT_LABELS = {
    "alpha":     "🔤 A–Z",
    "favs":      "💖 Most",
    "collected": "🃏 Most",
    "recent":    "🕐 Newest",
}

_PAGE_SPARKS = ["✨","🌸","⭐","💎","🌺","🔮","💫"]
_DIVIDERS    = [
    "✦ · · ✦ · · ✦ · · ✦",
    "· ˖ ✦ ˖ · ˖ ✦ ˖ ·",
    "⋆ ˚ ✦ ˚ ⋆ · ⋆ ˚ ✦",
]


def _sort_chars(chars: list, sort: str) -> list:
    from database import get_character_fav_count, get_card_owner_count
    if sort == "favs":
        return sorted(chars, key=lambda c: get_character_fav_count(c["id"]), reverse=True)
    if sort == "collected":
        return sorted(chars, key=lambda c: get_card_owner_count(c["id"]), reverse=True)
    if sort == "recent":
        return sorted(chars, key=lambda c: c["id"], reverse=True)
    return sorted(chars, key=lambda c: (c.get("name") or "").lower())


# ─────────────────────────────────────────────────
# Roster embed
# ─────────────────────────────────────────────────

def build_roster_embed(chars, page, total_pages, viewer_name, viewer_discord_id=None):
    from database import get_profile_by_discord_id

    start      = page * PAGE_SIZE
    page_chars = chars[start:start + PAGE_SIZE]
    spark      = _PAGE_SPARKS[page % len(_PAGE_SPARKS)]
    divider    = _DIVIDERS[page % len(_DIVIDERS)]

    embed = discord.Embed(
        title=f"{spark}  {viewer_name}'s Characters  {spark}",
        color=discord.Color.from_rgb(150, 255, 180)
    )

    entry_sep = "-# · · · · · · · · · ·"
    lines = [f"-# {divider}"]

    for i, c in enumerate(page_chars):
        global_num = start + i + 1
        story   = c.get("story_title") or "Unknown Story"
        gender  = c.get("gender") or ""
        species = c.get("species") or ""
        tags    = "  ·  ".join(t for t in [gender, species] if t)

        fav_count  = get_character_fav_count(c["id"])
        card_count = get_card_owner_count(c["id"])
        lines.append(
            f"{NUMBER_EMOJIS[i]}  **{c['name']}**"
            + (f"  ✦  *{tags}*" if tags else "")
            + f"\n-# 📚 {story}  ·  💖 {fav_count} favs  ·  🃏 {card_count} collected  ·  #{global_num}"
        )
        if i < len(page_chars) - 1:
            lines.append(entry_sep)

    lines.append(f"-# {divider}")
    embed.description = "\n".join(lines)

    if viewer_discord_id:
        try:
            profile = get_profile_by_discord_id(viewer_discord_id)
            img = profile.get("image_url") if profile else None
            if img and img.startswith("http"):
                embed.set_thumbnail(url=img)
        except Exception:
            pass

    embed.set_footer(
        text=f"Page {page + 1} of {total_pages}  ·  {len(chars)} character{'s' if len(chars) != 1 else ''} total"
    )
    return embed


# ─────────────────────────────────────────────────
# Jump-to-page modal
# ─────────────────────────────────────────────────

class _CharsJumpToPageModal(discord.ui.Modal, title="Jump to Page"):
    page_num = discord.ui.TextInput(
        label="Page number",
        placeholder="e.g. 3",
        max_length=4,
        required=True
    )

    def __init__(self, roster_view):
        super().__init__()
        self.roster_view = roster_view

    async def on_submit(self, interaction):
        try:
            num = int(self.page_num.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid page number.", ephemeral=True, delete_after=4
            )
            return
        total = self.roster_view.total_pages()
        if num < 1 or num > total:
            await interaction.response.send_message(
                f"❌ Page must be between 1 and {total}.", ephemeral=True, delete_after=4
            )
            return
        self.roster_view.page = num - 1
        self.roster_view._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_roster_embed(
                self.roster_view.chars,
                self.roster_view.page,
                total,
                interaction.user.display_name,
                viewer_discord_id=str(interaction.user.id)
            ),
            view=self.roster_view
        )


# ─────────────────────────────────────────────────
# Character detail view (single card with Return)
# ─────────────────────────────────────────────────

class MyCharDetailView(ui.View):

    def __init__(self, chars, char_index, viewer, return_page):
        super().__init__(timeout=300)
        self.chars       = chars
        self.char_index  = char_index
        self.viewer      = viewer
        self.return_page = return_page
        self._rebuild_ui()

    def current_char(self):
        return self.chars[self.char_index]

    def build_embed(self):
        uid = get_user_id(str(self.viewer.id))
        return build_character_card(
            self.current_char(),
            viewer=self.viewer,
            user_id=uid,
            index=self.char_index + 1,
            total=len(self.chars)
        )

    def _rebuild_ui(self):
        self.clear_items()
        char = self.current_char()

        prev = ui.Button(emoji="⬅️", style=discord.ButtonStyle.secondary,
                         row=0, disabled=self.char_index == 0)
        prev.callback = self._prev
        self.add_item(prev)

        uid   = get_user_id(str(self.viewer.id))
        faved = is_favorite_character(uid, char["id"]) if uid else False
        fav_btn = ui.Button(
            label="✦ Unstar" if faved else "✦ Favorite",
            style=discord.ButtonStyle.primary,
            row=0
        )
        fav_btn.callback = self._fav
        self.add_item(fav_btn)

        lore_btn = ui.Button(
            label="📜 Lore",
            style=discord.ButtonStyle.primary,
            row=0,
            disabled=not bool(char.get("lore"))
        )
        lore_btn.callback = self._lore
        self.add_item(lore_btn)

        back_btn = ui.Button(label="↩️ Return", style=discord.ButtonStyle.success, row=0)
        back_btn.callback = self._back
        self.add_item(back_btn)

        nxt = ui.Button(emoji="➡️", style=discord.ButtonStyle.secondary,
                        row=0, disabled=self.char_index >= len(self.chars) - 1)
        nxt.callback = self._next
        self.add_item(nxt)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.", ephemeral=True, delete_after=5
            )
            return False
        return True

    async def _fav(self, interaction):
        from features.characters.views.favorite_helpers import handle_fav_toggle
        char = self.current_char()
        async def _refresh(i):
            self._rebuild_ui()
            await i.response.edit_message(content=None, embed=self.build_embed(), view=self)
        await handle_fav_toggle(interaction, char, _refresh)

    async def _prev(self, interaction):
        self.char_index -= 1
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction):
        self.char_index += 1
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _lore(self, interaction):
        char = get_character_by_id(self.current_char()["id"])
        lore = char.get("lore") if char else None
        if not lore:
            await interaction.response.send_message("No lore written yet.", ephemeral=True)
            return
        embed = discord.Embed(
            title="📜 Character Lore",
            description=lore,
            color=discord.Color.dark_purple()
        )
        embed.set_footer(text="⚠️ Spoiler Content")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _back(self, interaction):
        total_pages = (len(self.chars) + PAGE_SIZE - 1) // PAGE_SIZE
        roster = MyCharsRosterView(self.chars, self.viewer, start_page=self.return_page)
        await interaction.response.edit_message(
            embed=build_roster_embed(
                self.chars, self.return_page, total_pages,
                interaction.user.display_name,
                viewer_discord_id=str(interaction.user.id)
            ),
            view=roster
        )


# ─────────────────────────────────────────────────
# Roster view
# ─────────────────────────────────────────────────

class MyCharsRosterView(ui.View):

    def __init__(self, chars, viewer, start_page=0):
        super().__init__(timeout=300)
        self.all_chars  = chars
        self.viewer     = viewer
        self.viewer_did = str(viewer.id)
        self.sort       = "alpha"
        self.chars      = _sort_chars(chars, self.sort)
        self.page       = start_page
        self._rebuild_ui()

    def total_pages(self):
        return max(1, (len(self.chars) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _page_chars(self):
        start = self.page * PAGE_SIZE
        return self.chars[start:start + PAGE_SIZE]

    def _rebuild_ui(self):
        self.clear_items()
        page_chars = self._page_chars()
        count      = len(page_chars)

        # Row 0: index buttons 1-5
        for i in range(min(count, PAGE_SIZE)):
            btn = ui.Button(
                emoji=NUMBER_EMOJIS[i],
                style=discord.ButtonStyle.primary,
                row=0
            )
            btn.callback = self._make_open_callback(i)
            self.add_item(btn)

        # Row 1: ⬅️  sort  Jump to...  ➡️
        prev_btn = ui.Button(
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=1,
            disabled=(self.page == 0)
        )
        prev_btn.callback = self._roster_prev
        self.add_item(prev_btn)

        sort_btn = ui.Button(
            label=SORT_LABELS[self.sort],
            style=discord.ButtonStyle.primary,
            row=1
        )
        sort_btn.callback = self._cycle_sort
        self.add_item(sort_btn)

        jump_btn = ui.Button(
            label="Jump to...",
            style=discord.ButtonStyle.success,
            row=1
        )
        jump_btn.callback = self._roster_jump
        self.add_item(jump_btn)

        next_btn = ui.Button(
            emoji="➡️",
            style=discord.ButtonStyle.secondary,
            row=1,
            disabled=(self.page >= self.total_pages() - 1)
        )
        next_btn.callback = self._roster_next
        self.add_item(next_btn)

    def _make_open_callback(self, slot_index):
        async def callback(interaction):
            global_index = self.page * PAGE_SIZE + slot_index
            if global_index >= len(self.chars):
                await interaction.response.send_message("Character not found.", ephemeral=True)
                return
            detail_view = MyCharDetailView(
                self.chars, global_index, self.viewer, return_page=self.page
            )
            await interaction.response.edit_message(
                embed=detail_view.build_embed(), view=detail_view
            )
        return callback

    async def _cycle_sort(self, interaction):
        idx        = SORT_CYCLE.index(self.sort)
        self.sort  = SORT_CYCLE[(idx + 1) % len(SORT_CYCLE)]
        self.chars = _sort_chars(self.all_chars, self.sort)
        self.page  = 0
        self._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_roster_embed(
                self.chars, self.page, self.total_pages(),
                interaction.user.display_name, viewer_discord_id=self.viewer_did
            ),
            view=self
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.", ephemeral=True, delete_after=5
            )
            return False
        return True

    async def _roster_prev(self, interaction):
        self.page = max(0, self.page - 1)
        self._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_roster_embed(
                self.chars, self.page, self.total_pages(),
                interaction.user.display_name, viewer_discord_id=self.viewer_did
            ),
            view=self
        )

    async def _roster_next(self, interaction):
        self.page = min(self.total_pages() - 1, self.page + 1)
        self._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_roster_embed(
                self.chars, self.page, self.total_pages(),
                interaction.user.display_name, viewer_discord_id=self.viewer_did
            ),
            view=self
        )

    async def _roster_jump(self, interaction):
        await interaction.response.send_modal(_CharsJumpToPageModal(self))