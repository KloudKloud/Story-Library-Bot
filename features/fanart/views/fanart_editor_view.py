import discord
from discord import ui
import asyncio

from embeds.fanart_embeds import build_fanart_editor_embed
from features.fanart.views.fanart_gallery_view import FanartGalleryView

from database import (
    get_fanart_characters,
    get_fanart_ships,
    get_fanart_by_id,
)

from ui.base_builder_view import BaseBuilderView
from ui import TimeoutMixin

PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
_SPARKS       = ["✨", "🌸", "⭐", "💎", "🌺", "🔮", "💫"]
_DIVIDER      = "✦ ˖ ⋆ ˚ · ✧ · ˚ ⋆ ˖ ✦ ˖ ⋆ ˚ · ✧ · ˚ ⋆ ˖ ✦"
_ENTRY_SEP    = "-# ˖ · · ⋆ · · ˖ · · ✦ · · ˖ · · ⋆ · · ˖"


# ─────────────────────────────────────────────────
# Fanart Roster helpers
# ─────────────────────────────────────────────────

def build_fanart_roster_embed(fanarts: list, page: int, total_pages: int,
                               viewer_name: str) -> discord.Embed:
    start        = page * PAGE_SIZE
    page_fanarts = fanarts[start:start + PAGE_SIZE]
    spark        = _SPARKS[page % len(_SPARKS)]
    embed = discord.Embed(
        title = f"{spark}  {viewer_name}'s Fanart Builder  {spark}",
        color = discord.Color.from_rgb(255, 182, 193),
    )
    lines = [f"-# {_DIVIDER}"]
    for i, f in enumerate(page_fanarts):
        title = f.get("title") or "Untitled"
        story = f.get("story_title") or "No story linked"
        lines.append(
            f"{NUMBER_EMOJIS[i]}  **{title}**\n"
            f"-# 📚 {story}"
        )
        if i < len(page_fanarts) - 1:
            lines.append(_ENTRY_SEP)
    lines.append(f"-# {_DIVIDER}")
    embed.description = "\n".join(lines)
    embed.set_footer(
        text=f"Page {page + 1} of {total_pages}  ·  "
             f"{len(fanarts)} piece{'s' if len(fanarts) != 1 else ''} total"
    )
    return embed


class _FanartBuildJumpModal(discord.ui.Modal, title="Jump to Page"):
    page_num = discord.ui.TextInput(
        label="Page number", placeholder="e.g. 2", max_length=4, required=True
    )

    def __init__(self, roster_view: "FanartBuildRosterView"):
        super().__init__()
        self.roster_view = roster_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            num = int(self.page_num.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Enter a valid page number.", ephemeral=True, delete_after=4)
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
            embed=build_fanart_roster_embed(
                self.roster_view.fanarts, self.roster_view.page,
                total, self.roster_view.viewer.display_name,
            ),
            view=self.roster_view,
        )


class FanartBuildRosterView(TimeoutMixin, ui.View):
    """5-per-page browse of all your fanart for the builder."""

    def __init__(self, fanarts: list, viewer: discord.Member, bot, start_page: int = 0):
        super().__init__(timeout=300)
        self.fanarts = fanarts
        self.viewer  = viewer
        self.bot     = bot
        self.page    = start_page
        self.builder_message = None
        self._rebuild_ui()

    def total_pages(self) -> int:
        return max(1, (len(self.fanarts) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _page_fanarts(self) -> list:
        start = self.page * PAGE_SIZE
        return self.fanarts[start:start + PAGE_SIZE]

    def build_embed(self) -> discord.Embed:
        return build_fanart_roster_embed(
            self.fanarts, self.page, self.total_pages(), self.viewer.display_name
        )

    def _rebuild_ui(self):
        self.clear_items()
        page_fanarts = self._page_fanarts()

        for i in range(len(page_fanarts)):
            btn = ui.Button(emoji=NUMBER_EMOJIS[i], style=discord.ButtonStyle.primary, row=0)
            btn.callback = self._make_open_cb(i)
            self.add_item(btn)

        prev_btn = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary, row=1,
            disabled=(self.page == 0),
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        jump_btn = ui.Button(
            label=f"Page {self.page + 1}/{self.total_pages()}",
            style=discord.ButtonStyle.success, row=1,
            disabled=(self.total_pages() == 1),
        )
        jump_btn.callback = self._jump
        self.add_item(jump_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary, row=1,
            disabled=(self.page >= self.total_pages() - 1),
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

    def _make_open_cb(self, slot_index: int):
        async def callback(interaction: discord.Interaction):
            global_index = self.page * PAGE_SIZE + slot_index
            if global_index >= len(self.fanarts):
                await interaction.response.send_message("Fanart not found.", ephemeral=True)
                return
            fanart_data = self.fanarts[global_index]
            view = FanartEditorView(
                fanart=fanart_data, user=self.viewer, bot=self.bot,
                fanarts=self.fanarts, index=global_index, return_page=self.page,
            )
            view.builder_message = self.builder_message
            await interaction.response.edit_message(embed=view.build_embed(), view=view)
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

    async def _jump(self, interaction: discord.Interaction):
        await interaction.response.send_modal(_FanartBuildJumpModal(self))


# ================= DESCRIPTION MODAL =================

class FanartDescriptionModal(discord.ui.Modal):

    def __init__(self, editor_view):

        super().__init__(title="Edit Fanart Description")

        self.editor_view = editor_view

        if hasattr(editor_view, '_modal_open'):
            editor_view._modal_open = True

        self.description = discord.ui.TextInput(
            label="Scene Description",
            style=discord.TextStyle.paragraph,
            placeholder="Describe the scene, mood, dialogue, etc...",
            max_length=2000,
            default=editor_view.fanart.get("description") or "",
        )

        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction):

        if hasattr(self.editor_view, '_modal_open'):
            self.editor_view._modal_open = False

        from database import update_fanart_description

        update_fanart_description(
            self.editor_view.fanart["id"],
            self.description.value
        )

        await self.editor_view.refresh()
        await self.editor_view.refresh_preview()

        await interaction.response.send_message(
            "✨ Description updated!",
            ephemeral=True,
            delete_after=3
        )


# ================= CHARACTER MODAL =================

class FanartCharacterModal(discord.ui.Modal):

    def __init__(self, editor_view):

        super().__init__(title="Tag Characters")

        self.editor_view = editor_view

        if hasattr(editor_view, '_modal_open'):
            editor_view._modal_open = True

        self.names_input = discord.ui.TextInput(
            label="Character names (comma separated)",
            style=discord.TextStyle.paragraph,
            placeholder="e.g. Aria, Marcus, Lune",
            required=False,
            max_length=500,
        )

        self.add_item(self.names_input)

    async def on_submit(self, interaction: discord.Interaction):

        if hasattr(self.editor_view, '_modal_open'):
            self.editor_view._modal_open = False

        from database import (
            get_character_id_by_name,
            clear_fanart_characters,
            add_fanart_character,
        )

        story_id  = self.editor_view.fanart.get("story_id")
        fanart_id = self.editor_view.fanart["id"]
        raw       = self.names_input.value.strip()

        # Clear existing tags on every submit (empty input = clear all)
        clear_fanart_characters(fanart_id)

        if not raw:
            await self.editor_view.refresh()
            await self.editor_view.refresh_preview()
            await interaction.response.send_message(
                "🧬 Characters cleared.",
                ephemeral=True,
                delete_after=3
            )
            return

        names   = [n.strip() for n in raw.split(",") if n.strip()]
        invalid = []

        for name in names:
            cid = get_character_id_by_name(story_id, name)
            if cid:
                add_fanart_character(fanart_id, cid)
            else:
                invalid.append(name)

        await self.editor_view.refresh()
        await self.editor_view.refresh_preview()

        if invalid:
            bad = ", ".join(f"**{n}**" for n in invalid)
            await interaction.response.send_message(
                f"⚠️ Couldn't find: {bad}\n"
                f"-# Names are case-sensitive. Double-check spelling with `/char mychars`, "
                f"or add missing characters with `/char add`.",
                ephemeral=True,
                delete_after=10
            )
        else:
            await interaction.response.send_message(
                f"🧬 Tagged **{len(names)}** character{'s' if len(names) != 1 else ''}!",
                ephemeral=True,
                delete_after=3
            )



# ================= SHIP MODAL =================

class FanartShipModal(discord.ui.Modal):

    def __init__(self, editor_view):

        super().__init__(title="Tag Ships")

        self.editor_view = editor_view

        if hasattr(editor_view, '_modal_open'):
            editor_view._modal_open = True

        self.names_input = discord.ui.TextInput(
            label="Ship names (comma separated)",
            style=discord.TextStyle.paragraph,
            placeholder="e.g. Aria x Marcus, Lune x Vael",
            required=False,
            max_length=500,
        )

        self.add_item(self.names_input)

    async def on_submit(self, interaction: discord.Interaction):

        if hasattr(self.editor_view, '_modal_open'):
            self.editor_view._modal_open = False

        from database import (
            get_ships_by_story,
            clear_fanart_ships,
            add_fanart_ship,
        )

        story_id  = self.editor_view.fanart.get("story_id")
        fanart_id = self.editor_view.fanart["id"]
        raw       = self.names_input.value.strip()

        clear_fanart_ships(fanart_id)

        if not raw:
            await self.editor_view.refresh()
            await self.editor_view.refresh_preview()
            await interaction.response.send_message(
                "💞 Ships cleared.",
                ephemeral=True,
                delete_after=3
            )
            return

        # Match typed names against existing story ships
        all_ships  = get_ships_by_story(story_id) if story_id else []
        ship_map   = {s["name"].lower(): s["id"] for s in all_ships}
        names      = [n.strip() for n in raw.split(",") if n.strip()]
        invalid    = []

        for name in names:
            sid = ship_map.get(name.lower())
            if sid:
                add_fanart_ship(fanart_id, sid)
            else:
                invalid.append(name)

        await self.editor_view.refresh()
        await self.editor_view.refresh_preview()

        if invalid:
            bad = ", ".join(f"**{n}**" for n in invalid)
            await interaction.response.send_message(
                f"⚠️ Couldn't find: {bad}\n"
                f"-# Ship names are case-insensitive but must exist. "
                f"Create ships with `/createship`, or view yours with `/myships`.",
                ephemeral=True,
                delete_after=10
            )
        else:
            await interaction.response.send_message(
                f"💞 Tagged **{len(names)}** ship{'s' if len(names) != 1 else ''}!",
                ephemeral=True,
                delete_after=3
            )

# ================= ORIGIN MODAL =================

class FanartOriginModal(discord.ui.Modal):

    def __init__(self, editor_view):

        super().__init__(title="Origin — How did this come to be?")

        self.editor_view = editor_view

        if hasattr(editor_view, '_modal_open'):
            editor_view._modal_open = True

        self.origin_input = discord.ui.TextInput(
            label="Origin",
            placeholder="e.g. Self-Made, Commissioned, Gifted...",
            max_length=100,
            required=False,
            default=editor_view.fanart.get("origin") or ""
        )

        self.add_item(self.origin_input)

    async def on_submit(self, interaction: discord.Interaction):

        if hasattr(self.editor_view, '_modal_open'):
            self.editor_view._modal_open = False

        from database import update_fanart_origin

        value = self.origin_input.value.strip() or None
        update_fanart_origin(self.editor_view.fanart["id"], value)
        self.editor_view.reload_fanart()
        await self.editor_view.refresh()
        await self.editor_view.refresh_preview()

        await interaction.response.send_message(
            f"💸 Origin set to **{value}**!" if value else "💸 Origin cleared.",
            ephemeral=True,
            delete_after=3
        )



# ================= STORY LINK MODAL =================

class FanartStoryLinkModal(discord.ui.Modal):

    story_name = discord.ui.TextInput(
        label="Story title",
        placeholder="e.g. Between Two Worlds  (fuzzy match, any caps ok)",
        max_length=200,
        required=True
    )

    def __init__(self, editor_view):
        super().__init__(title="Link a Story")
        self.editor_view = editor_view

    async def on_submit(self, interaction: discord.Interaction):
        from database import get_all_stories_sorted, update_fanart_story

        raw = self.story_name.value

        def _normalize(s: str) -> str:
            """Lowercase, strip spaces, replace & with and."""
            return s.lower().replace("&", "and").replace(" ", "")

        needle = _normalize(raw)
        stories = get_all_stories_sorted()

        # 1. Exact normalized match
        match = None
        for s in stories:
            if _normalize(s[0]) == needle:
                match = s
                break

        # 2. Partial normalized match (needle is substring of title or vice versa)
        if not match:
            for s in stories:
                norm_title = _normalize(s[0])
                if needle in norm_title or norm_title in needle:
                    match = s
                    break

        if not match:
            await interaction.response.send_message(
                f'❌ Couldn\'t find a story matching **"{raw}"**.\n'
                f"-# Check the spelling or try a shorter part of the title. "
                f"Titles are in the library — you can also swap `&` for `and`.",
                ephemeral=True,
                delete_after=6
            )
            return

        update_fanart_story(self.editor_view.fanart["id"], int(match[9]))
        self.editor_view.reload_fanart()
        await self.editor_view.refresh()
        await self.editor_view.refresh_preview()

        await interaction.response.send_message(
            f"📚 Linked to **{match[0]}**!",
            ephemeral=True,
            delete_after=4
        )


# ================= MAIN EDITOR VIEW =================

class FanartEditorView(BaseBuilderView):

    def __init__(self, fanart, user, bot, fanarts=None, index=0, return_page=0):

        super().__init__(user)

        self.builder_message = None
        self.fanart          = fanart
        self.bot             = bot
        self.preview_view    = None
        self.preview_message = None
        self._fanarts        = fanarts
        self._index          = index
        self._return_page    = return_page

        self.refresh_ui()

    # ================= SHIP SELECT =================

    class ShipTagSelect(ui.Select):

        def __init__(self, view_ref, ships):

            self.view_ref = view_ref

            options = [
                discord.SelectOption(
                    label=f"💞 {ship['name']}"[:100],
                    description="/".join(ship["characters"])[:100],
                    value=str(ship["id"])
                )
                for ship in ships
            ]

            super().__init__(
                placeholder="Select ships featured in this art...",
                min_values=0,
                max_values=min(len(options), 25),
                options=options
            )

        async def callback(self, interaction):

            from database import clear_fanart_ships, add_fanart_ship

            fanart_id = self.view_ref.fanart["id"]
            clear_fanart_ships(fanart_id)

            for sid in self.values:
                add_fanart_ship(fanart_id, int(sid))

            await self.view_ref.refresh()
            await self.view_ref.refresh_preview()

            await interaction.response.edit_message(content="💞 Ships updated!", view=None)
            await asyncio.sleep(3)
            try:
                await interaction.delete_original_response()
            except Exception:
                pass

    # ================= FUN OPTIONS DROPDOWN =================

    class FunOptionsSelect(ui.Select):

        def __init__(self, view_ref):

            self.view_ref = view_ref

            options = [
                discord.SelectOption(
                    label="Vibe Tags",
                    description="Moods & aesthetics — soft, dramatic, rain, etc.",
                    emoji="✨",
                    value="tags"
                ),
                discord.SelectOption(
                    label="Quote",
                    description="A lyric, line, or phrase that fits the vibe",
                    emoji="📖",
                    value="scene_ref"
                ),
                discord.SelectOption(
                    label="Artist Credit",
                    description="Name + link for the artist who made this",
                    emoji="🎨",
                    value="artist_credit"
                ),
                discord.SelectOption(
                    label="Canon / AU",
                    description="Is this a canon moment or alternate universe?",
                    emoji="🌀",
                    value="canon_au"
                ),
                discord.SelectOption(
                    label="The Vibe — Add a Song",
                    description="Link a Spotify/YouTube song for this piece",
                    emoji="🎵",
                    value="music"
                ),
                discord.SelectOption(
                    label="Origin",
                    description="Commissioned, Gift Art, or Gifted?",
                    emoji="💸",
                    value="origin"
                ),
                discord.SelectOption(
                    label="Add Ship",
                    description="Tag ships featured in this artwork",
                    emoji="💞",
                    value="ship"
                ),
                discord.SelectOption(
                    label="Remove Fanart",
                    description="Delete this fanart entry",
                    emoji="🗑️",
                    value="delete"
                ),
            ]

            super().__init__(
                placeholder="🎨 More Options...",
                options=options,
                min_values=1,
                max_values=1,
                row=1
            )

        async def callback(self, interaction):

            choice = self.values[0]

            if choice == "tags":
                self.view_ref._modal_open = True
                from features.fanart.modals.tags_modal import FanartTagsModal
                await interaction.response.send_modal(FanartTagsModal(self.view_ref))

            elif choice == "scene_ref":
                self.view_ref._modal_open = True
                from features.fanart.modals.scene_ref_modal import FanartSceneRefModal
                await interaction.response.send_modal(FanartSceneRefModal(self.view_ref))

            elif choice == "artist_credit":
                self.view_ref._modal_open = True
                from features.fanart.modals.artist_credit_modal import FanartArtistCreditModal
                await interaction.response.send_modal(FanartArtistCreditModal(self.view_ref))

            elif choice == "canon_au":
                from database import update_fanart_canon_au
                current = self.view_ref.fanart.get("canon_au") or "canon"
                toggled = "au" if current == "canon" else "canon"
                update_fanart_canon_au(self.view_ref.fanart["id"], toggled)
                self.view_ref.reload_fanart()
                await self.view_ref.refresh()
                await self.view_ref.refresh_preview()
                await interaction.response.send_message(
                    f"🌀 Marked as **{'Alternate Universe' if toggled == 'au' else 'Canon'}**!",
                    ephemeral=True,
                    delete_after=3
                )

            elif choice == "music":
                self.view_ref._modal_open = True
                from features.fanart.modals.music_modal import FanartMusicModal
                await interaction.response.send_modal(FanartMusicModal(self.view_ref))

            elif choice == "origin":
                self.view_ref._modal_open = True
                await interaction.response.send_modal(FanartOriginModal(self.view_ref))

            elif choice == "ship":
                if not self.view_ref.fanart.get("story_id"):
                    await interaction.response.send_message(
                        "Link a story first before tagging ships.",
                        ephemeral=True,
                        delete_after=4
                    )
                    return
                self.view_ref._modal_open = True
                await interaction.response.send_modal(FanartShipModal(self.view_ref))

            elif choice == "delete":
                from features.fanart.views.confirm_delete_view import ConfirmDeleteFanartView
                await interaction.response.send_message(
                    "⚠️ Are you sure you want to delete this fanart?",
                    view=ConfirmDeleteFanartView(self.view_ref),
                    ephemeral=True
                )

    # ================= EMBED =================

    def build_embed(self):
        chars = get_fanart_characters(self.fanart["id"])
        ships = get_fanart_ships(self.fanart["id"])
        return build_fanart_editor_embed(self.fanart, characters=chars, ships=ships)

    # ================= RELOAD =================

    def reload_fanart(self):
        updated = get_fanart_by_id(self.fanart["id"])
        if updated:
            self.fanart = updated

    async def refresh(self):
        self.reload_fanart()
        self.refresh_ui()
        await self._safe_edit(embed=self.build_embed(), view=self)

    # ================= UI =================

    def refresh_ui(self):
        self.reload_fanart()
        self.clear_items()

        # Row 0
        self.add_item(self.add_story)
        self.add_item(self.tag_characters)
        self.add_item(self.edit_vibe_tags)
        self.add_item(self.edit_description)
        self.add_item(self.preview)

        # Row 1 dropdown
        self.add_item(self.FunOptionsSelect(self))

        # Row 2 nav (browse mode only)
        if self._fanarts is not None:
            prev_btn = ui.Button(
                emoji="⬅️", style=discord.ButtonStyle.secondary, row=2,
                disabled=(self._index == 0),
            )
            prev_btn.callback = self._nav_prev
            self.add_item(prev_btn)

            ret_btn = ui.Button(label="↩️ Return", style=discord.ButtonStyle.success, row=2)
            ret_btn.callback = self._nav_return
            self.add_item(ret_btn)

            next_btn = ui.Button(
                emoji="➡️", style=discord.ButtonStyle.secondary, row=2,
                disabled=(self._index >= len(self._fanarts) - 1),
            )
            next_btn.callback = self._nav_next
            self.add_item(next_btn)

    # ================= ROW 2 NAV CALLBACKS =================

    async def _nav_prev(self, interaction: discord.Interaction):
        self._index -= 1
        fanart_data = self._fanarts[self._index]
        new_view = FanartEditorView(
            fanart=fanart_data, user=self.user, bot=self.bot,
            fanarts=self._fanarts, index=self._index, return_page=self._return_page,
        )
        new_view.builder_message = self.builder_message
        await interaction.response.edit_message(embed=new_view.build_embed(), view=new_view)

    async def _nav_next(self, interaction: discord.Interaction):
        self._index += 1
        fanart_data = self._fanarts[self._index]
        new_view = FanartEditorView(
            fanart=fanart_data, user=self.user, bot=self.bot,
            fanarts=self._fanarts, index=self._index, return_page=self._return_page,
        )
        new_view.builder_message = self.builder_message
        await interaction.response.edit_message(embed=new_view.build_embed(), view=new_view)

    async def _nav_return(self, interaction: discord.Interaction):
        roster = FanartBuildRosterView(
            self._fanarts, self.user, self.bot, start_page=self._return_page
        )
        roster.builder_message = self.builder_message
        await interaction.response.edit_message(embed=roster.build_embed(), view=roster)

    # ================= BUTTONS =================

    @ui.button(label="🧬 Add Chars", style=discord.ButtonStyle.primary)
    async def tag_characters(self, interaction, button):

        if not self.fanart.get("story_id"):
            await interaction.response.send_message(
                "Link a story first before tagging characters.",
                ephemeral=True,
                delete_after=4
            )
            return

        await interaction.response.send_modal(FanartCharacterModal(self))

    @ui.button(label="✨ Vibe Tags", style=discord.ButtonStyle.primary)
    async def edit_vibe_tags(self, interaction, button):
        self._modal_open = True
        from features.fanart.modals.tags_modal import FanartTagsModal
        await interaction.response.send_modal(FanartTagsModal(self))

    @ui.button(label="🎬 Description", style=discord.ButtonStyle.primary)
    async def edit_description(self, interaction, button):
        self._modal_open = True
        await interaction.response.send_modal(FanartDescriptionModal(self))

    @ui.button(label="📚 Story", style=discord.ButtonStyle.primary)
    async def add_story(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(FanartStoryLinkModal(self))

    @ui.button(label="👀 Preview", style=discord.ButtonStyle.success)
    async def preview(self, interaction, button):

        view = FanartGalleryView(
            [self.fanart],
            interaction.user,
            reduced=True,
            draft=True
        )

        view.parent_view      = self
        self.preview_view     = view
        self.preview_message  = interaction.message

        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view
        )

    # ================= PREVIEW REFRESH =================

    async def refresh_preview(self):

        if not self.preview_view or not self.preview_message:
            return

        if not isinstance(self.preview_view, FanartGalleryView):
            return

        # Push the freshly reloaded fanart into the preview view so it reflects
        # the latest artist credit, music, origin, and any other updated fields.
        self.preview_view.items[0] = self.fanart

        try:
            loading = discord.Embed(
                title="✨ Updating Preview...",
                description="Refreshing your fanart card ✨",
                color=discord.Color.dark_gray()
            )
            await self.preview_message.edit(embed=loading, view=self.preview_view)
            await asyncio.sleep(0.05)
            await self.preview_message.edit(
                embed=self.preview_view.build_embed(),
                view=self.preview_view
            )
        except Exception:
            pass