import discord
from discord import ui
import asyncio
import random as _random

from ui.base_list_view import BaseListView
from embeds.character_embeds import build_character_card
from embeds.character_embeds import (
    build_character_list_embed,
    build_character_detail_embed
)
from database import (
    get_user_id,
    get_character_by_id,
    get_characters_by_ids,
    get_story_by_character,
    is_favorite_character,
    get_favorite_characters,
    add_favorite_character,
    remove_favorite_character,
    get_character_fav_count,
    get_card_owner_count,
)
from ui import TimeoutMixin


class CharactersView(BaseListView):

    def __init__(self, characters, user):
        super().__init__(characters, user, per_page=7)

    def generate_list_embed(self):
        return build_character_list_embed(self.items)

    def generate_detail_embed(self, item):
        return build_character_card(item, viewer=self.user)


# =====================================================
# SHARED FAVORITE LOGIC  (reusable mixin helpers)
# =====================================================

class FavoriteMixin:
    """
    Drop this into any character view that needs ✦ Favorite / ✦ Unstar logic.
    Requires: self.viewer, self.current_character(), self.build_embed(), self.update_buttons()
    """

    def _get_uid(self):
        return get_user_id(str(self.viewer.id)) if self.viewer else None

    def _is_fav(self, char):
        uid = self._get_uid()
        return uid and is_favorite_character(uid, char["id"])

    def _sync_fav_button(self, button, char):
        uid = self._get_uid()
        if uid and is_favorite_character(uid, char["id"]):
            button.label = "✦ Unstar"
            button.style = discord.ButtonStyle.primary
        else:
            button.label = "✦ Favorite"
            button.style = discord.ButtonStyle.primary

    async def _handle_mark_fav(self, interaction, char, parent_view):
        """
        Full mark-fav / remove-fav flow. parent_view = the view to refresh after.
        """
        uid = get_user_id(str(interaction.user.id))

        if not uid:
            await interaction.response.send_message(
                "User not registered.",
                ephemeral=True,
                delete_after=4
            )
            return

        character_id = char["id"]
        story_id = char["story_id"]

        # ---- Already favorite → confirm removal (edit the original message in-place) ----
        if is_favorite_character(uid, character_id):
            story = get_story_by_character(character_id)
            story_title = story["title"] if story else "this story"

            confirm_view = _ConfirmFavRemoval(
                parent_view=parent_view,
                character=char,
                story_title=story_title,
                user_id=uid,
                viewer=interaction.user
            )

            # Build a lightweight confirmation embed — no new message, just swap the current one
            confirm_embed = discord.Embed(
                title=f"💫 Remove Favorite?",
                description=(
                    f"Remove **{char['name']}** from your favorites?\n"
                    f"*({story_title})*"
                ),
                color=discord.Color.orange()
            )
            confirm_embed.set_footer(text="This prompt expires in 10 seconds.")

            await interaction.response.edit_message(
                embed=confirm_embed,
                view=confirm_view
            )
            confirm_view._interaction = interaction
            return

        # ---- Check slots ----
        favorites = get_favorite_characters(uid, story_id)

        if len(favorites) >= 2:
            story = get_story_by_character(character_id)
            story_title = story["title"] if story else "this story"

            # build full char dicts for replace view
            fav_chars = get_characters_by_ids([fid["id"] for fid in favorites])

            replace_view = _ReplaceFavorite(
                parent_view=parent_view,
                fav_chars=fav_chars,
                new_character=char,
                user_id=uid,
                viewer=interaction.user
            )

            # Swap in-place — no new ephemeral, same architecture as removal flow
            replace_embed = discord.Embed(
                title="💫 Swap Favorite?",
                description=(
                    f"You already have **2 favorites** from **{story_title}**.\n"
                    f"Pick one below to replace with **{char['name']}**."
                ),
                color=discord.Color.blurple()
            )
            replace_embed.set_footer(text="This prompt expires in 10 seconds.")

            await interaction.response.edit_message(
                embed=replace_embed,
                view=replace_view
            )
            replace_view._interaction = interaction
            return

        # ---- Add favorite ----
        add_favorite_character(uid, story_id, character_id)

        parent_view.rebuild_character()
        parent_view.update_buttons()

        await interaction.response.edit_message(
            embed=parent_view.build_embed(),
            view=parent_view
        )

        msg = await interaction.followup.send(
            f"💫 **{char['name']}** added to your favorites!",
            ephemeral=True
        )
        await asyncio.sleep(3)
        try:
            await msg.delete()
        except Exception:
            pass


# =====================================================
# INTERNAL CONFIRMATION VIEWS
# =====================================================

class _ConfirmFavRemoval(ui.View):

    def __init__(self, parent_view, character, story_title, user_id, viewer):
        super().__init__(timeout=10)
        self.parent_view  = parent_view
        self.character    = character
        self.story_title  = story_title
        self.user_id      = user_id
        self.viewer       = viewer
        self._interaction = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.viewer and interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    async def on_timeout(self):
        """Restore original character card if no action taken."""
        if self._interaction:
            try:
                self.parent_view.rebuild_character()
                self.parent_view.update_buttons()
                await self._interaction.edit_original_response(
                    embed=self.parent_view.build_embed(),
                    view=self.parent_view
                )
            except Exception:
                pass

    @ui.button(label="Yes, Remove", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        self._interaction = interaction
        self.stop()

        remove_favorite_character(self.user_id, self.character["id"])
        self.parent_view.rebuild_character()
        self.parent_view.update_buttons()

        # Restore the character card in the original message — no new message
        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        self._interaction = interaction
        self.stop()

        # Just restore the character card — no new message, no ephemeral
        self.parent_view.rebuild_character()
        self.parent_view.update_buttons()

        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )


class _ReplaceFavorite(ui.View):

    def __init__(self, parent_view, fav_chars, new_character, user_id, viewer):
        super().__init__(timeout=10)
        self.parent_view   = parent_view
        self.fav_chars     = fav_chars
        self.new_character = new_character
        self.user_id       = user_id
        self.viewer        = viewer
        self._interaction  = None

        options = [
            discord.SelectOption(
                label=f"{c['name']} → Replace with {new_character['name']}",
                value=str(c["id"])
            )
            for c in fav_chars
        ]

        sel = ui.Select(placeholder="Choose who to replace...", options=options)
        sel.callback = self._replace_cb
        self.add_item(sel)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.viewer and interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    async def on_timeout(self):
        """Restore the character card if no action taken."""
        if self._interaction:
            try:
                self.parent_view.rebuild_character()
                self.parent_view.update_buttons()
                await self._interaction.edit_original_response(
                    embed=self.parent_view.build_embed(),
                    view=self.parent_view
                )
            except Exception:
                pass

    async def _replace_cb(self, interaction):
        self._interaction = interaction
        self.stop()

        old_id = int(interaction.data["values"][0])
        remove_favorite_character(self.user_id, old_id)
        add_favorite_character(
            self.user_id,
            self.new_character["story_id"],
            self.new_character["id"]
        )
        self.parent_view.rebuild_character()
        self.parent_view.update_buttons()

        # Restore the original character card — no new message
        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(self, interaction, button):
        self._interaction = interaction
        self.stop()

        self.parent_view.rebuild_character()
        self.parent_view.update_buttons()

        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )


# =====================================================
# StoryCharactersView  — library path + author path
#
# Row 0: ⬅️ | ✦ Favorite | 📜 Lore | Return btn | ➡️
# =====================================================

# ─────────────────────────────────────────────────────────────
# Story Cast Roster — 7-per-page list opened by /story cast
# ─────────────────────────────────────────────────────────────

CAST_PAGE_SIZE   = 7
CAST_COLORS = [
    # Pastels
    (255, 182, 193), (255, 218, 185), (255, 255, 153), (179, 255, 179), (153, 229, 255),
    (204, 153, 255), (255, 179, 255), (255, 204, 153), (153, 255, 229), (179, 204, 255),
    # Vivids
    (255,  92,  92), (255, 160,  50), (255, 230,  50), ( 80, 220, 100), ( 50, 200, 255),
    (130,  80, 255), (255,  80, 200), ( 80, 255, 200), (255, 120, 180), (100, 200, 255),
    # Jewel tones
    (220,  20,  60), (255, 140,   0), (218, 165,  32), ( 34, 139,  34), ( 30, 144, 255),
    (138,  43, 226), (199,  21, 133), ( 72, 209, 204), (255,  69,   0), ( 60, 179, 113),
    # Muted/sophisticated
    (188, 143, 143), (210, 180, 140), (189, 183, 107), (143, 188, 143), (135, 206, 235),
    (147, 112, 219), (216, 112, 147), (102, 205, 170), (240, 128, 128), (176, 196, 222),
    # Neons (softened)
    (255, 111, 145), (255, 200,  87), (167, 255,  89), ( 89, 255, 232), (140, 120, 255),
    (255,  89, 172), ( 89, 220, 255), (255, 175,  89), (172, 255,  89), (220,  89, 255),
    # Extra luxe
    (180, 130, 255), (192, 192, 192), (255, 127,  80), (100, 149, 237), (144, 238, 144),
]

def _random_color():
    r, g, b = _random.choice(CAST_COLORS)
    return discord.Color.from_rgb(r, g, b)


CAST_NUM_EMOJIS  = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣"]
_CAST_SPARKS     = ["🧬","🌸","⭐","💎","🌺","🔮","💫"]
_CAST_DIVIDERS   = [
    "✦ · · ✦ · · ✦ · · ✦",
    "· ˖ ✦ ˖ · ˖ ✦ ˖ ·",
    "⋆ ˚ ✦ ˚ ⋆ · ⋆ ˚ ✦",
]


def build_cast_roster_embed(chars: list, page: int, total_pages: int,
                             story_title: str,
                             author_image_url: str = None) -> discord.Embed:
    start      = page * CAST_PAGE_SIZE
    page_chars = chars[start:start + CAST_PAGE_SIZE]
    spark      = _CAST_SPARKS[page % len(_CAST_SPARKS)]
    divider    = _CAST_DIVIDERS[page % len(_CAST_DIVIDERS)]

    embed = discord.Embed(
        title=f"{spark}  {story_title} — Cast  {spark}",
        color=_random_color()
    )

    if author_image_url:
        embed.set_thumbnail(url=author_image_url)

    entry_sep = "-# · · · · · · · · · ·"
    lines = [f"-# {divider}"]

    for i, c in enumerate(page_chars):
        global_num = start + i + 1
        gender     = c.get("gender") or ""
        species    = c.get("species") or ""
        tags       = "  ·  ".join(t for t in [gender, species] if t)
        fav_count  = get_character_fav_count(c["id"])
        card_count = get_card_owner_count(c["id"])

        lines.append(
            f"{CAST_NUM_EMOJIS[i]}  **{c['name']}**"
            + (f"  ✦  *{tags}*" if tags else "")
            + f"\n-# 💖 {fav_count} favs  ·  🃏 {card_count} collected  ·  #{global_num}"
        )
        if i < len(page_chars) - 1:
            lines.append(entry_sep)

    lines.append(f"-# {divider}")
    embed.description = "\n".join(lines)
    embed.set_footer(
        text=f"Page {page + 1} of {total_pages}  ·  {len(chars)} character{'s' if len(chars) != 1 else ''}"
    )
    return embed


class _JumpToPageModal(discord.ui.Modal, title="Jump to Page"):
    page_num = discord.ui.TextInput(
        label="Page number",
        placeholder="e.g. 3",
        max_length=4,
        required=True
    )

    def __init__(self, roster_view: "StoryCastRosterView"):
        super().__init__()
        self.roster_view = roster_view

    async def on_submit(self, interaction: discord.Interaction):
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
            embed=build_cast_roster_embed(
                self.roster_view.chars,
                self.roster_view.page,
                total,
                self.roster_view.story_title,
                self.roster_view.author_image_url
            ),
            view=self.roster_view
        )


class StoryCastRosterView(TimeoutMixin, ui.View):
    """
    Paginated character roster for /story cast (default, no char specified).
    Row 0 : number buttons 1-5
    Row 1 : number buttons 6-7  (only if page has 6-7 chars)
    Row 2 : 📄 Jump to Specific Page  (modal)
    """

    def __init__(self, chars: list, viewer: discord.Member, story_title: str,
                 start_page: int = 0, author_image_url: str = None):
        super().__init__(timeout=300)
        self.chars            = chars
        self.viewer           = viewer
        self.story_title      = story_title
        self.page             = start_page
        self.author_image_url = author_image_url
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
        return max(1, (len(self.chars) + CAST_PAGE_SIZE - 1) // CAST_PAGE_SIZE)

    def _page_chars(self) -> list:
        start = self.page * CAST_PAGE_SIZE
        return self.chars[start:start + CAST_PAGE_SIZE]

    def _rebuild_ui(self):
        self.clear_items()
        page_chars = self._page_chars()
        count = len(page_chars)

        # Row 0 : buttons 1-5
        for i in range(min(count, 5)):
            btn = ui.Button(emoji=CAST_NUM_EMOJIS[i],
                            style=discord.ButtonStyle.primary, row=0)
            btn.callback = self._make_open_cb(i)
            self.add_item(btn)

        # Row 1 : buttons 6-7
        for i in range(5, min(count, CAST_PAGE_SIZE)):
            btn = ui.Button(emoji=CAST_NUM_EMOJIS[i],
                            style=discord.ButtonStyle.primary, row=1)
            btn.callback = self._make_open_cb(i)
            self.add_item(btn)

        # Row 2 : ◀ Jump to... ▶  (page navigation)
        prev_btn = ui.Button(
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=2,
            disabled=(self.page == 0)
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        jump_btn = ui.Button(
            label="Jump to...",
            style=discord.ButtonStyle.success,
            row=2,
            disabled=(self.total_pages() == 1)
        )
        jump_btn.callback = self._jump
        self.add_item(jump_btn)

        next_btn = ui.Button(
            emoji="➡️",
            style=discord.ButtonStyle.secondary,
            row=2,
            disabled=(self.page >= self.total_pages() - 1)
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

    def _make_open_cb(self, slot_index: int):
        async def callback(interaction: discord.Interaction):
            global_index = self.page * CAST_PAGE_SIZE + slot_index
            if global_index >= len(self.chars):
                await interaction.response.send_message("Character not found.", ephemeral=True)
                return
            view = StoryCharactersView(
                self.chars,
                parent_view=self,
                story_title=self.story_title,
                viewer=self.viewer,
                return_mode="cast_roster",
                start_index=global_index
            )
            await interaction.response.edit_message(
                embed=view.build_embed(), view=view
            )
        return callback

    async def _prev(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_cast_roster_embed(self.chars, self.page, self.total_pages(), self.story_title, self.author_image_url),
            view=self
        )

    async def _next(self, interaction: discord.Interaction):
        self.page = min(self.total_pages() - 1, self.page + 1)
        self._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_cast_roster_embed(self.chars, self.page, self.total_pages(), self.story_title, self.author_image_url),
            view=self
        )

    async def _jump(self, interaction: discord.Interaction):
        await interaction.response.send_modal(_JumpToPageModal(self))


class StoryCharactersView(TimeoutMixin, FavoriteMixin, ui.View):

    def __init__(
        self,
        characters,
        parent_view,
        story_title=None,
        return_mode="story",   # "story" = library, "bio" = author, "cast_roster" = StoryCastRosterView, "myfics" = MyFicDetailView
        viewer=None,
        show_return: bool = True,
        start_index: int = 0
    ):
        ui.View.__init__(self, timeout=300)

        self.viewer      = viewer
        self.characters  = characters
        self.parent_view = parent_view
        self.story_title = story_title
        self.return_mode = return_mode
        self.show_return = show_return
        self.index       = start_index

        # Set return button label by path
        if return_mode == "story":
            self.return_btn.label = "Return 📖"
        elif return_mode == "bio":
            self.return_btn.label = "Return 🖊️"
        elif return_mode in ("cast_roster", "myfics"):
            self.return_btn.label = "↩️ Return"
        else:
            self.return_btn.label = "↩️ Return"

        self.update_buttons()
        self._build_ui()

    # ── Core helpers ────────────────────────────────

    def current_character(self):
        return self.characters[self.index]

    def rebuild_character(self):
        fresh = get_character_by_id(self.current_character()["id"])
        if fresh:
            self.characters[self.index] = fresh

    def build_embed(self):
        return build_character_card(
            self.current_character(),
            viewer=self.viewer,
            story_title=self.story_title,
            index=self.index + 1,
            total=len(self.characters)
        )

    def update_buttons(self):
        char = self.current_character()

        # Navigation arrows
        self.left.disabled  = self.index == 0
        self.right.disabled = self.index >= len(self.characters) - 1

        # Lore
        self.lore_btn.disabled = not bool(char.get("lore"))

        # Favorite button style
        self._sync_fav_button(self.fav_btn, char)

    def _build_ui(self):
        self.clear_items()
        if self.show_return:
            for btn in (self.left, self.fav_btn, self.lore_btn, self.return_btn, self.right):
                btn.row = 0
                self.add_item(btn)
        else:
            for btn in (self.left, self.fav_btn, self.lore_btn, self.right):
                btn.row = 0
                self.add_item(btn)

    # ── Buttons ─────────────────────────────────────

    @ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary, row=0)
    async def left(self, interaction, button):
        if self.index > 0:
            self.index -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @ui.button(label="✦ Favorite", style=discord.ButtonStyle.primary, row=0)
    async def fav_btn(self, interaction, button):
        await self._handle_mark_fav(interaction, self.current_character(), self)

    @ui.button(label="📜 Lore", style=discord.ButtonStyle.primary, row=0)
    async def lore_btn(self, interaction, button):
        from embeds.character_embeds import build_lore_embed
        char = self.current_character()
        lore = char.get("lore")
        if not lore:
            await interaction.response.send_message("No lore written yet.", ephemeral=True, delete_after=4)
            return
        await interaction.response.send_message(embed=build_lore_embed(char["name"], lore), ephemeral=True)

    @ui.button(label="Return 📖", style=discord.ButtonStyle.success, row=0)
    async def return_btn(self, interaction, button):
        if self.return_mode == "story":
            self.parent_view.mode = "story"
            self.parent_view.refresh_ui()
            await interaction.response.edit_message(
                embed=self.parent_view.generate_detail_embed(
                    self.parent_view.current_item
                ),
                view=self.parent_view
            )
        elif self.return_mode == "bio":
            self.parent_view.mode = "bio"
            self.parent_view.refresh_ui()
            await interaction.response.edit_message(
                embed=self.parent_view.generate_bio_embed(),
                view=self.parent_view
            )
        elif self.return_mode == "cast_roster":
            # Work out which page this character is on
            roster = self.parent_view
            return_page = self.index // CAST_PAGE_SIZE
            roster.page = return_page
            roster._rebuild_ui()
            await interaction.response.edit_message(
                embed=build_cast_roster_embed(
                    roster.chars, return_page, roster.total_pages(), roster.story_title
                ),
                view=roster
            )
        else:
            # "myfics" or any custom mode — parent exposes build_embed()
            await interaction.response.edit_message(
                embed=self.parent_view.build_embed(),
                view=self.parent_view
            )

    @ui.button(emoji="➡️", style=discord.ButtonStyle.secondary, row=0)
    async def right(self, interaction, button):
        if self.index < len(self.characters) - 1:
            self.index += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)