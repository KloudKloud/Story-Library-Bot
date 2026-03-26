from ui.base_builder_view import BaseBuilderView
from ui import TimeoutMixin
import discord
from discord import ui
from features.stories.story_service import unpack_story
from database import update_story_metadata
from database import get_story_by_id
from database import get_all_stories_sorted
from database import (
    get_characters_by_story,
    get_fanart_by_story,
    get_all_comments_for_story,
    get_global_comment_count_for_story,
    get_chapters_full,
)
from features.stories.views.library_view import LibraryView
from features.stories.views.story_notes_preview_view import StoryNotesPreviewView

PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
_SPARKS       = ["✨", "🌸", "⭐", "💎", "🌺", "🔮", "💫"]
_DIVIDER      = "✦ ˖ ⋆ ˚ · ✧ · ˚ ⋆ ˖ ✦ ˖ ⋆ ˚ · ✧ · ˚ ⋆ ˖ ✦"
_ENTRY_SEP    = "-# ˖ · · ⋆ · · ˖ · · ✦ · · ˖ · · ⋆ · · ˖"

# Fields checked for fic completion in the roster
# Main trio: cover, summary, playlist
# Detail fields: roadmap, story_notes, appreciation
_FIC_DETAIL_FIELDS = ["roadmap", "story_notes", "appreciation"]


def _fic_roster_stats(s):
    """Returns (has_cover, has_summary, has_playlist, det_fill, det_total, is_complete)."""
    def filled(key):
        try:
            v = s[key]
        except (IndexError, KeyError):
            return False
        return bool(v and str(v).strip())

    has_cover    = filled("cover_url")
    has_summary  = filled("summary")
    has_playlist = filled("playlist_url")
    det_fill     = sum(1 for f in _FIC_DETAIL_FIELDS if filled(f))
    det_total    = len(_FIC_DETAIL_FIELDS)
    is_complete  = has_cover and has_summary and has_playlist and det_fill == det_total
    return has_cover, has_summary, has_playlist, det_fill, det_total, is_complete


# ─────────────────────────────────────────────────
# Fic Roster helpers
# ─────────────────────────────────────────────────

def build_fic_roster_embed(stories: list, page: int, total_pages: int,
                            viewer_name: str) -> discord.Embed:
    start        = page * PAGE_SIZE
    page_stories = stories[start:start + PAGE_SIZE]
    embed = discord.Embed(
        title = f"{viewer_name}'s Fic Builder",
        color = discord.Color.blurple(),
    )
    lines = [f"-# {_DIVIDER}", ""]
    for i, s in enumerate(page_stories):
        title    = s[1] or "Untitled"
        chapters = s[2] or 0
        words    = s[4] or 0
        words_str = f"{words:,}" if words else "—"

        has_cover, has_summary, has_playlist, det_fill, det_total, is_complete = _fic_roster_stats(s)

        if is_complete:
            name_line = f"{NUMBER_EMOJIS[i]}  ✨ **{title}** ✨  **—  Done!**"
            status    = (
                f"-# 🖼️ ✅  📝 ✅  🎵 ✅  ⚙️ {det_fill}/{det_total}\n"
                f"-# ⭐ **Fully Complete**"
            )
        else:
            cov_mark  = "✅" if has_cover    else "❌"
            sum_mark  = "✅" if has_summary  else "❌"
            play_mark = "✅" if has_playlist else "❌"
            name_line = f"{NUMBER_EMOJIS[i]}  ⏳ **{title}**"
            status    = (
                f"-# 🖼️ {cov_mark}  📝 {sum_mark}  🎵 {play_mark}  ⚙️ {det_fill}/{det_total}\n"
                f"-# ⏳ **Not complete!**"
            )

        lines.append(
            f"{name_line}\n"
            f"-# 📖 {chapters} chapter{'s' if chapters != 1 else ''}  ·  ✏️ {words_str} words\n"
            f"{status}"
        )
        if i < len(page_stories) - 1:
            lines.append(f"\n{_ENTRY_SEP}\n")
    lines.append("")
    lines.append(f"-# {_DIVIDER}")
    embed.description = "\n".join(lines)
    embed.set_footer(
        text=f"Page {page + 1} of {total_pages}  ·  "
             f"{len(stories)} stor{'ies' if len(stories) != 1 else 'y'} total"
    )
    return embed


class _FicBuildJumpModal(discord.ui.Modal, title="Jump to Page"):
    page_num = discord.ui.TextInput(
        label="Page number", placeholder="e.g. 2", max_length=4, required=True
    )

    def __init__(self, roster_view: "FicBuildRosterView"):
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
            embed=build_fic_roster_embed(
                self.roster_view.stories, self.roster_view.page,
                total, self.roster_view.viewer.display_name,
            ),
            view=self.roster_view,
        )


class FicBuildRosterView(TimeoutMixin, ui.View):
    """5-per-page browse of all your stories for the builder."""

    def __init__(self, stories: list, viewer: discord.Member, start_page: int = 0):
        super().__init__(timeout=300)
        self.stories = stories
        self.viewer  = viewer
        self.page    = start_page
        self.builder_message = None
        self._rebuild_ui()

    def total_pages(self) -> int:
        return max(1, (len(self.stories) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _page_stories(self) -> list:
        start = self.page * PAGE_SIZE
        return self.stories[start:start + PAGE_SIZE]

    def build_embed(self) -> discord.Embed:
        return build_fic_roster_embed(
            self.stories, self.page, self.total_pages(), self.viewer.display_name
        )

    def _rebuild_ui(self):
        self.clear_items()
        page_stories = self._page_stories()

        for i in range(len(page_stories)):
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
            if global_index >= len(self.stories):
                await interaction.response.send_message("Story not found.", ephemeral=True)
                return
            story_row = self.stories[global_index]
            story_data = get_story_by_id(story_row[0])
            if not story_data:
                await interaction.response.send_message("Story could not be loaded.", ephemeral=True)
                return
            view = FicBuildView(
                story_data, self.viewer,
                stories=self.stories, index=global_index, return_page=self.page,
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
        await interaction.response.send_modal(_FicBuildJumpModal(self))

class StoryTextModal(ui.Modal):

    def __init__(self, title, label, field_name, parent_view, default=None):
        super().__init__(title=title)

        self.field_name = field_name
        self.parent_view = parent_view
        if hasattr(parent_view, '_modal_open'):
            parent_view._modal_open = True

        self.input = ui.TextInput(
            label=label,
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000,
            default=default or "",
        )

        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):

        if hasattr(self.parent_view, '_modal_open'):
            self.parent_view._modal_open = False

        if self.field_name in ("title", "summary") and not self.input.value.strip():
            label = "Title" if self.field_name == "title" else "Summary"
            await interaction.response.send_message(
                f"❌ {label} cannot be empty.", ephemeral=True, delete_after=5
            )
            return

        kwargs = {self.field_name: self.input.value}

        # Mark as manually customised so /fic refresh won't overwrite it
        if self.field_name == "title":
            kwargs["title_custom"] = 1
        elif self.field_name == "summary":
            kwargs["summary_custom"] = 1

        update_story_metadata(
            self.parent_view.story_id,
            **kwargs
        )

        self.parent_view.reload_story()

        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )


class TagsModal(ui.Modal):

    def __init__(self, parent_view, current_tags, platform: str = "ao3"):
        super().__init__(title="Edit Tags")
        self.parent_view = parent_view
        self.platform = platform

        if platform == "wattpad":
            label = "Insert AO3 link or Edit Tags"
            placeholder = "Paste an AO3 URL to auto-import tags, or type: romance, slow burn..."
        else:
            label = "Insert Wattpad link or Edit Tags"
            placeholder = "Paste a Wattpad URL to auto-import tags, or type: romance, slow burn..."

        self.tags_input = ui.TextInput(
            label=label,
            style=discord.TextStyle.paragraph,
            placeholder=placeholder,
            required=False,
            max_length=1000,
            default=", ".join(current_tags) if current_tags else "",
        )
        self.add_item(self.tags_input)

    async def on_submit(self, interaction: discord.Interaction):
        import asyncio
        from workers.update_worker import _clear_story_tags, _rebuild_story_tags
        from database import update_story_metadata

        raw = (self.tags_input.value or "").strip()

        is_ao3_url = "archiveofourown.org" in raw
        is_wp_url  = "wattpad.com" in raw

        if is_ao3_url or is_wp_url:
            await interaction.response.defer()
            try:
                if is_ao3_url:
                    from ao3_parser import fetch_ao3_tags_only
                    new_tags = await asyncio.to_thread(fetch_ao3_tags_only, raw)
                else:
                    from wattpad_parser import fetch_wattpad_tags_only
                    new_tags = await asyncio.to_thread(fetch_wattpad_tags_only, raw)
            except Exception as e:
                await interaction.followup.send(
                    f"❌ Couldn't fetch tags: {e}\n-# Your tags were not changed.",
                    ephemeral=True, delete_after=8
                )
                return
            _clear_story_tags(self.parent_view.story_id)
            _rebuild_story_tags(self.parent_view.story_id, new_tags)
            update_story_metadata(self.parent_view.story_id, tags_custom=1)
            self.parent_view.reload_story()
            await self.parent_view._safe_edit(
                embed=self.parent_view.build_embed(),
                view=self.parent_view,
            )
        else:
            new_tags = [t.strip() for t in raw.split(",") if t.strip()]
            _clear_story_tags(self.parent_view.story_id)
            if new_tags:
                _rebuild_story_tags(self.parent_view.story_id, new_tags)
            update_story_metadata(self.parent_view.story_id, tags_custom=1)
            self.parent_view.reload_story()
            await interaction.response.edit_message(
                embed=self.parent_view.build_embed(),
                view=self.parent_view,
            )


class FicBuildView(BaseBuilderView):

    def __init__(self, story, user, stories=None, index=0, return_page=0):

        super().__init__(user)

        self.story    = story
        self.story_id = story[0]
        self._stories     = stories
        self._index       = index
        self._return_page = return_page

        self.misc_select = self.MiscSelect(self)
        self.misc_select.row = 1
        self.add_item(self.misc_select)

        if stories is not None:
            self._add_nav_buttons()


    # (kept for reference — completion is computed in get_completion_stats)
    BUILD_FIELDS = [
        "cover_url",
        "summary",
        "playlist_url",
        "roadmap",
        "story_notes",
        "appreciation",
    ]

    class LibraryPreviewView(ui.View):

        def __init__(self, builder, story):
            super().__init__(timeout=300)

            self.builder = builder
            self.story = story
            self.viewer = builder.user

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id != self.viewer.id:
                await interaction.response.send_message(
                    "❌ This session belongs to someone else.",
                    ephemeral=True, delete_after=5
                )
                return False
            return True

        @ui.button(label="📚 Return", style=discord.ButtonStyle.success)
        async def back_to_editor(self, interaction, button):
            await interaction.response.edit_message(
                embed=self.builder.build_embed(),
                view=self.builder
            )

    class LinkModal(ui.Modal):

        def __init__(self, builder):
            super().__init__(title="Add Misc. Link")

            self.builder = builder

            self.title_input = ui.TextInput(
                label="Link Title",
                placeholder="Example: RoyalRoad",
                max_length=50
            )

            self.url_input = ui.TextInput(
                label="Link URL",
                placeholder="https://...",
                max_length=500
            )

            self.add_item(self.title_input)
            self.add_item(self.url_input)

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer()

            update_story_metadata(
                self.builder.story_id,
                extra_link_title=self.title_input.value,
                extra_link_url=self.url_input.value
            )

            self.builder.reload_story()
            await self.builder._safe_edit(embed=self.builder.build_embed(), view=self.builder)

    class AltLinkModal(ui.Modal):
        """Handles adding/replacing the platform mirror link (AO3 for Wattpad stories, vice versa)."""

        def __init__(self, builder, alt_platform: str):
            alt_name = "AO3" if alt_platform == "ao3" else "Wattpad"
            super().__init__(title=f"Link {alt_name} Mirror")
            self.builder      = builder
            self.alt_platform = alt_platform

            self.url_input = ui.TextInput(
                label=f"{alt_name} URL",
                placeholder="https://...",
                max_length=500,
            )
            self.add_item(self.url_input)

        async def on_submit(self, interaction: discord.Interaction):
            import asyncio
            from ao3_parser import fetch_ao3_metadata, normalize_ao3_url
            from wattpad_parser import fetch_wattpad_metadata, WattpadError, normalize_wattpad_url
            from database import update_story_metadata, fill_chapter_alt_urls, fill_chapter_summaries
            from workers.update_worker import _build_alt_maps

            raw_url = self.url_input.value.strip()
            alt_platform = self.alt_platform
            alt_name = "AO3" if alt_platform == "ao3" else "Wattpad"

            if alt_platform == "ao3" and "archiveofourown.org" not in raw_url:
                await interaction.response.send_message(
                    "❌ That doesn't look like an AO3 link. Please paste a URL from archiveofourown.org.",
                    ephemeral=True, delete_after=8
                )
                return
            if alt_platform == "wattpad" and "wattpad.com" not in raw_url:
                await interaction.response.send_message(
                    "❌ That doesn't look like a Wattpad link. Please paste a wattpad.com URL.",
                    ephemeral=True, delete_after=8
                )
                return

            await interaction.response.defer()

            try:
                if alt_platform == "ao3":
                    normalized = normalize_ao3_url(raw_url)
                    data = await asyncio.to_thread(fetch_ao3_metadata, normalized)
                    alt_stats = dict(
                        ao3_url       = normalized,
                        ao3_hits      = data.get("hits"),
                        ao3_kudos     = data.get("kudos"),
                        ao3_comments  = data.get("comments"),
                        ao3_bookmarks = data.get("bookmarks"),
                    )
                else:
                    normalized = normalize_wattpad_url(raw_url)
                    try:
                        data = await asyncio.to_thread(fetch_wattpad_metadata, normalized)
                    except WattpadError as e:
                        await interaction.followup.send(
                            f"❌ {e.user_message}\n-# Mirror link was not saved.",
                            ephemeral=True, delete_after=8
                        )
                        return
                    alt_stats = dict(
                        wattpad_url      = normalized,
                        wattpad_reads    = data.get("reads"),
                        wattpad_votes    = data.get("votes"),
                        wattpad_comments = data.get("comments"),
                    )

                alt_url_map, alt_summary_map = _build_alt_maps(data, alt_platform)
                update_story_metadata(self.builder.story_id, **alt_stats)
                fill_chapter_alt_urls(self.builder.story_id, alt_platform, alt_url_map)
                if alt_summary_map:
                    fill_chapter_summaries(self.builder.story_id, alt_summary_map)

            except Exception as e:
                await interaction.followup.send(
                    f"❌ Couldn't fetch {alt_name}:\n`{e}`\n-# Mirror link was not saved.",
                    ephemeral=True, delete_after=10
                )
                return

            self.builder.reload_story()
            await self.builder._safe_edit(embed=self.builder.build_embed(), view=self.builder)

            msg = f"✅ {alt_name} mirror linked! Stats and chapter data imported."
            if alt_platform == "ao3":
                msg += " Chapter summaries have been filled where empty."
            await interaction.followup.send(msg, ephemeral=True, delete_after=6)


    class StoryLinksView(ui.View):

        def __init__(self, builder, platform: str = "ao3"):
            super().__init__(timeout=300)
            self.builder  = builder
            self.platform = platform

            alt_label = "🔗 Link AO3 Mirror" if platform == "wattpad" else "🔗 Link Wattpad Mirror"
            alt_btn = ui.Button(label=alt_label, style=discord.ButtonStyle.primary, row=0)
            alt_btn.callback = self._link_mirror
            self.add_item(alt_btn)

            misc_btn = ui.Button(label="📎 Misc. Link", style=discord.ButtonStyle.primary, row=0)
            misc_btn.callback = self._edit_misc
            self.add_item(misc_btn)

            back_btn = ui.Button(label="↩ Return", style=discord.ButtonStyle.success, row=0)
            back_btn.callback = self._back
            self.add_item(back_btn)

        async def _link_mirror(self, interaction: discord.Interaction):
            alt_platform = "ao3" if self.platform == "wattpad" else "wattpad"
            await interaction.response.send_modal(
                FicBuildView.AltLinkModal(self.builder, alt_platform)
            )

        async def _edit_misc(self, interaction: discord.Interaction):
            await interaction.response.send_modal(
                FicBuildView.LinkModal(self.builder)
            )

        async def _back(self, interaction: discord.Interaction):
            self.builder.reload_story()
            await interaction.response.edit_message(
                embed=self.builder.build_embed(),
                view=self.builder
            )

    # ─────────────────────────────────────────────────
    # ROW 2 NAV (browse mode only)
    # ─────────────────────────────────────────────────

    def _add_nav_buttons(self):
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
            disabled=(self._index >= len(self._stories) - 1),
        )
        next_btn.callback = self._nav_next
        self.add_item(next_btn)

    async def _nav_prev(self, interaction: discord.Interaction):
        self._index -= 1
        story_data = get_story_by_id(self._stories[self._index][0])
        new_view = FicBuildView(story_data, self.user, stories=self._stories, index=self._index, return_page=self._return_page)
        new_view.builder_message = self.builder_message
        await interaction.response.edit_message(embed=new_view.build_embed(), view=new_view)

    async def _nav_next(self, interaction: discord.Interaction):
        self._index += 1
        story_data = get_story_by_id(self._stories[self._index][0])
        new_view = FicBuildView(story_data, self.user, stories=self._stories, index=self._index, return_page=self._return_page)
        new_view.builder_message = self.builder_message
        await interaction.response.edit_message(embed=new_view.build_embed(), view=new_view)

    async def _nav_return(self, interaction: discord.Interaction):
        roster = FicBuildRosterView(self._stories, self.user, start_page=self._return_page)
        roster.builder_message = self.builder_message
        await interaction.response.edit_message(embed=roster.build_embed(), view=roster)

    def reload_story(self):

        fresh = get_story_by_id(self.story_id)

        if fresh:
            self.story = fresh


    # =====================================================
    # EMBED
    # =====================================================

    def build_embed(self):
        from database import get_tags_by_story

        story = unpack_story(self.story)

        _platform   = self.story["platform"] or "ao3"
        _ao3_mirror = self.story["ao3_url"] if _platform == "wattpad" else None
        _wp_mirror  = self.story["wattpad_url"] if _platform == "ao3" else None
        _alt_label  = "AO3" if _platform == "wattpad" else "Wattpad"

        title        = story["title"]
        cover_url    = story.get("cover_url")
        summary      = story.get("summary")
        appreciation = story.get("appreciation")
        roadmap      = story.get("roadmap")
        inspirations = story.get("story_notes")
        playlist     = story.get("playlist_url")
        extra_link   = story.get("extra_link_url")
        current_tags = get_tags_by_story(self.story_id)
        mirror_set   = bool(_ao3_mirror or _wp_mirror)
        links_set    = bool(mirror_set or extra_link)

        filled, total, percent = self.get_completion_stats()
        bar = self.build_progress_bar(percent)

        embed = discord.Embed(
            title=f"📚 {title} • {percent}% Complete",
            color=discord.Color.blurple()
        )
        embed.description = f"**{filled}/{total} sections completed**\n{bar}"

        if cover_url:
            embed.set_thumbnail(url=cover_url)

        DIVIDER = "─── ✦ ───"

        def _cur(value, preview=None):
            if value:
                return f"-# Current: *{preview or 'Set'}*"
            return "-# Current: *Not set*"

        # ── Cover ────────────────────────────────────────────────────────────
        embed.add_field(
            name="🎨 Cover",
            value=(
                "Upload or change your story cover.\n"
                f"{_cur(cover_url)}\n{DIVIDER}"
            ),
            inline=False
        )

        # ── Summary ───────────────────────────────────────────────────────────
        embed.add_field(
            name="📝 Summary",
            value=(
                "The blurb readers see when they view your story.\n"
                f"{_cur(summary, self.preview_text(summary, 80) if summary else None)}\n{DIVIDER}"
            ),
            inline=False
        )

        # ── Tags ─────────────────────────────────────────────────────────────
        if current_tags:
            tags_preview = ", ".join(current_tags[:6])
            if len(current_tags) > 6:
                tags_preview += f" +{len(current_tags) - 6} more"
        else:
            tags_preview = None
        embed.add_field(
            name="🏷️ Tags",
            value=(
                f"Auto-filled from {_platform.upper()}, or paste a {_alt_label} link to swap them.\n"
                f"{_cur(current_tags, tags_preview)}\n{DIVIDER}"
            ),
            inline=False
        )

        # ── Story Playlist ─────────────────────────────────────────────────────
        embed.add_field(
            name="🎵 Story Playlist",
            value=(
                "Add music that represents the vibe of your story.\n"
                f"{_cur(playlist)}\n{DIVIDER}"
            ),
            inline=False
        )

        # ── Story Links ────────────────────────────────────────────────────────
        if _platform == "wattpad":
            links_desc = "Link an AO3 mirror or a misc. link (RoyalRoad, FFN, etc.)."
            _primary_name = "Wattpad"
            _mirror_name  = "AO3"
            _mirror_val   = _ao3_mirror
        else:
            links_desc = "Link a Wattpad mirror or a misc. link (RoyalRoad, FFN, etc.)."
            _primary_name = "AO3"
            _mirror_name  = "Wattpad"
            _mirror_val   = _wp_mirror

        _extra_title = story.get("extra_link_title")
        _links_parts = [
            f"**{_primary_name}** ✔",
            f"**{_mirror_name}** {'✔' if _mirror_val else '—'}",
            f"**{_extra_title}** ✔" if _extra_title else "**Misc.** —",
        ]
        links_preview = " | ".join(_links_parts)
        embed.add_field(
            name="🔗 Story Links",
            value=(
                f"{links_desc}\n"
                f"-# Current: *{links_preview}*\n{DIVIDER}"
            ),
            inline=False
        )

        # ── Condensed details ─────────────────────────────────────────────────
        def _mini(value, label):
            return f"{'⭐' if value else '•'} {label}"

        # Chapters built check (fast: count chapters with any content)
        chapters_built = sum(
            1 for ch in get_chapters_full(self.story_id)
            if ch.get("chapter_summary") or ch.get("chapter_image_url")
               or ch.get("chapter_link") or ch.get("chapter_wattpad_url")
               or ch.get("chapter_ao3_url")
        )

        embed.add_field(
            name="⚙️ More Details",
            value="\n".join([
                _mini(title,              "Title"),
                _mini(appreciation,       "Appreciation"),
                _mini(chapters_built > 0, "Build Chapters"),
                _mini(inspirations,       "Inspirations"),
                _mini(roadmap,            "Update Roadmap"),
            ]),
            inline=False
        )

        embed.set_footer(text="✨ Fic Builder • Configure how readers discover your story")
        return embed

    # =====================================================
    # COMPLETION
    # =====================================================

    def get_completion_stats(self):
        from database import get_tags_by_story

        story     = unpack_story(self.story)
        _platform = self.story["platform"] or "ao3"

        cover_url    = story.get("cover_url")
        summary      = story.get("summary")
        playlist     = story.get("playlist_url")
        appreciation = story.get("appreciation")
        roadmap      = story.get("roadmap")
        inspirations = story.get("story_notes")
        extra_link   = story.get("extra_link_url")
        tags         = get_tags_by_story(self.story_id)
        mirror       = self.story["ao3_url"] if _platform == "wattpad" else self.story["wattpad_url"]
        links_ok     = bool(mirror or extra_link)

        chapters_built = sum(
            1 for ch in get_chapters_full(self.story_id)
            if ch.get("chapter_summary") or ch.get("chapter_image_url")
               or ch.get("chapter_link") or ch.get("chapter_wattpad_url")
               or ch.get("chapter_ao3_url")
        )

        checks = [
            bool(cover_url),
            bool(summary),
            bool(tags),
            bool(playlist),
            bool(links_ok),
            bool(story.get("title")),   # title — condensed
            bool(appreciation),         # condensed
            bool(chapters_built),       # condensed
            bool(inspirations),         # condensed
            bool(roadmap),              # condensed
        ]

        total   = len(checks)
        filled  = sum(checks)
        percent = int((filled / total) * 100)
        return filled, total, percent


    # =====================================================
    # BUTTONS
    # =====================================================

    @ui.button(label="🎨 Cover", style=discord.ButtonStyle.primary, row=0)
    async def edit_cover(self, interaction: discord.Interaction, button: ui.Button):

        async def save_image(url):

            update_story_metadata(
                self.story_id,
                cover_url=url
            )

            # reload story from DB
            self.reload_story()

            await self._safe_edit(embed=self.build_embed(), view=self)

        await self.handle_image_upload(
            interaction,
            save_image
        )





    @ui.button(label="🔗 Links", style=discord.ButtonStyle.primary, row=0)
    async def story_links(self, interaction, button):
        from pad_placeholder import get_placeholder_url

        story = unpack_story(self.story)
        _platform = self.story["platform"] or "ao3"
        cover_url = story.get("cover_url")

        link1 = story.get("extra_link_title")

        if _platform == "wattpad":
            primary_name = "Wattpad"
            mirror_label = "AO3 Mirror"
            mirror_url   = self.story["ao3_url"]
            mirror_note  = (
                "Linking AO3 adds an **AO3 link** beside Wattpad on the Resume screen, "
                "auto-fills empty chapter summaries, and tracks AO3 stats separately.\n\n"
                "`/fic refresh` will update new chapters, hits, and kudos for AO3 automatically.\n"
                "-# These links display as clickable buttons on your library page!"
            )
        else:
            primary_name = "AO3"
            mirror_label = "Wattpad Mirror"
            mirror_url   = self.story["wattpad_url"]
            mirror_note  = (
                "Linking Wattpad adds a **Wattpad link** beside AO3 on the Resume screen "
                "and tracks Wattpad stats separately.\n\n"
                "`/fic refresh` will update new chapters, reads, and votes for Wattpad automatically.\n"
                "-# These links display as clickable buttons on your library page!"
            )

        embed = discord.Embed(
            title="🔗 Story Links",
            description="Manage where readers can find your story.",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=cover_url or get_placeholder_url())
        embed.add_field(
            name=f"✅ {primary_name}",
            value="Always included automatically.",
            inline=False
        )
        embed.add_field(
            name=f"🔗 {mirror_label}",
            value=f"**Set:** {mirror_url or 'Not linked yet'}\n\n{mirror_note}",
            inline=False
        )
        embed.add_field(
            name="📎 Misc. Link",
            value=f"**Set:** {link1 or 'Not set'}\nAdd a link to another platform (RoyalRoad, FFN, etc.).",
            inline=False
        )

        await interaction.response.edit_message(
            embed=embed,
            view=self.StoryLinksView(self, _platform)
        )


    @ui.button(label="💖 Appreciation", style=discord.ButtonStyle.primary, row=0)
    async def edit_appreciation(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.send_modal(
            StoryTextModal(
                "Reader Appreciation",
                "Message to readers",
                "appreciation",
                self
            )
        )


    @ui.button(label="👁 Preview", style=discord.ButtonStyle.success, row=0)
    async def preview(self, interaction, button):

        from embeds.story_notes_embed import build_story_notes_embed

        sid = self.story_id

        # Build the same stats dict the live Story Dex uses
        all_chapters   = get_chapters_full(sid)
        ch_count       = len(all_chapters)
        chapters_built = sum(
            1 for ch in all_chapters
            if ch.get("chapter_summary") or ch.get("chapter_image_url")
               or ch.get("chapter_link") or ch.get("chapter_wattpad_url")
               or ch.get("chapter_ao3_url")
        )
        all_comments       = get_all_comments_for_story(sid)
        commented_chapters = len({c["chapter_id"] for c in all_comments if "chapter_id" in c})
        global_c           = get_global_comment_count_for_story(sid)
        total_comments     = len(all_comments) + global_c

        stats = {
            "chars":                len(get_characters_by_story(sid)),
            "fanarts":              len(get_fanart_by_story(sid)),
            "comments":             total_comments,
            "chapters_built":       chapters_built,
            "ch_count":             ch_count,
            "commented_chapters":   commented_chapters,
            "global_comment_count": global_c,
        }

        embed = build_story_notes_embed(self.story, viewer=interaction.user, stats=stats)

        await interaction.response.edit_message(
            embed=embed,
            view=StoryNotesPreviewView(self)
        )


    # =====================================================
    # DROPDOWN
    # =====================================================

    class MiscSelect(ui.Select):

        def __init__(self, view_ref):

            self.view_ref = view_ref

            options = [

                discord.SelectOption(
                    label="🏷️ Add / Edit Tags",
                    description="Update the tags shown on your story.",
                    value="edit_tags"
                ),

                discord.SelectOption(
                    label="📝 Edit Summary",
                    description="Rewrite your story's summary.",
                    value="edit_summary"
                ),

                discord.SelectOption(
                    label="✏️ Edit Title",
                    description="Rename your story in the library.",
                    value="edit_title"
                ),

                discord.SelectOption(
                    label="📖 Build Chapters",
                    description="Add summaries, images, and links to each chapter.",
                    value="chapbuild"
                ),

                discord.SelectOption(
                    label="🎵 Book Playlist",
                    description="Add music that represents your story.",
                    value="playlist"
                ),

                discord.SelectOption(
                    label="💡 Inspirations",
                    description="Share what inspired this story — songs, fics, moments.",
                    value="inspirations"
                ),

                discord.SelectOption(
                    label="🗺 Update Roadmap",
                    description="Share your latest writing progress with readers.",
                    value="roadmap"
                ),

            ]

            super().__init__(
                placeholder="⚙️ Additional Story Features...",
                options=options
            )


        async def callback(self, interaction: discord.Interaction):

            choice = self.values[0]
            v = self.view_ref
            story = v.story

            if choice == "edit_title":
                await interaction.response.send_modal(
                    StoryTextModal(
                        "Edit Title", "Story Title", "title", v,
                        default=story["title"] if story["title"] else "",
                    )
                )

            elif choice == "edit_summary":
                await interaction.response.send_modal(
                    StoryTextModal(
                        "Edit Summary", "Summary", "summary", v,
                        default=story["summary"] if story["summary"] else "",
                    )
                )

            elif choice == "edit_tags":
                from database import get_tags_by_story
                current_tags = get_tags_by_story(v.story_id)
                _platform = v.story["platform"] or "ao3"
                await interaction.response.send_modal(TagsModal(v, current_tags, platform=_platform))

            elif choice == "chapbuild":
                from features.chapters.chapter_builder_view import ChapterBuilderView
                from database import get_chapters_full
                chapters = get_chapters_full(v.story_id)
                if not chapters:
                    await interaction.response.send_message(
                        "❌ No chapters found. Run `/fic refresh` to sync chapters first.",
                        ephemeral=True, delete_after=6
                    )
                    return
                chapter_view = ChapterBuilderView(
                    v.story_id, story["title"], interaction.user,
                    cover_url=story["cover_url"] if story["cover_url"] else None,
                    parent_view=v,
                )
                await interaction.response.edit_message(
                    embed=chapter_view.build_embed(), view=chapter_view
                )
                chapter_view.builder_message = await interaction.original_response()

            elif choice == "playlist":

                await interaction.response.send_modal(
                    StoryTextModal(
                        "Story Playlist",
                        "Spotify or YouTube Link",
                        "playlist_url",
                        self.view_ref
                    )
                )

            elif choice == "inspirations":

                await interaction.response.send_modal(
                    StoryTextModal(
                        "Story Inspirations",
                        "What inspired this story?",
                        "story_notes",
                        self.view_ref
                    )
                )

            elif choice == "roadmap":

                await interaction.response.send_modal(
                    StoryTextModal(
                        "Writing Roadmap",
                        "Progress Update",
                        "roadmap",
                        self.view_ref
                    )
                )