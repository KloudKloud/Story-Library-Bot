from ui.base_builder_view import BaseBuilderView
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

        kwargs = {self.field_name: self.input.value}

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
            self.parent_view.reload_story()
            await interaction.response.edit_message(
                embed=self.parent_view.build_embed(),
                view=self.parent_view,
            )


class FicBuildView(BaseBuilderView):

    def __init__(self, story, user):

        super().__init__(user)

        self.story = story
        self.story_id = story[0]

        self.misc_select = self.MiscSelect(self)
        self.misc_select.row = 1
        self.add_item(self.misc_select)


    # Fields that count toward completion
    BUILD_FIELDS = [
        "cover_url",
        "playlist_url",
        "roadmap",
        "story_notes",
        "appreciation",
        "extra_link_url"
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

        @ui.button(label="⬅ Return", style=discord.ButtonStyle.success)
        async def back_to_notes(self, interaction, button):

            from embeds.story_notes_embed import build_story_notes_embed

            await interaction.response.edit_message(
                embed=build_story_notes_embed(self.builder.story),
                view=self.builder.StoryNotesPreviewView(self.builder)
            )

        @ui.button(label="🛠 Back to Editor", style=discord.ButtonStyle.primary)
        async def back_to_editor(self, interaction, button):

            await interaction.response.edit_message(
                embed=self.builder.build_embed(),
                view=self.builder
            )

    class LinkModal(ui.Modal):

        def __init__(self, builder, source_message):
            super().__init__(title="Add Story Link")

            self.builder = builder
            self.source_message = source_message

            if hasattr(builder, '_modal_open'):
                builder._modal_open = True

            self.title_input = ui.TextInput(
                label="Link Title",
                placeholder="Example: Wattpad",
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

            if hasattr(self.builder, '_modal_open'):
                self.builder._modal_open = False

            update_story_metadata(
                self.builder.story_id,
                extra_link_title=self.title_input.value,
                extra_link_url=self.url_input.value
            )

            # refresh story data
            self.builder.reload_story()

            # update the fic builder embed live
            await self.builder._safe_edit(embed=self.builder.build_embed(), view=self.builder)

            await interaction.response.send_message(
                "✅ Link saved!",
                ephemeral=True,
                delete_after=2
            )

            try:
                await self.source_message.delete()
            except:
                pass

    class AltLinkModal(ui.Modal):
        """Handles adding/replacing the platform mirror link (AO3 for Wattpad stories, vice versa)."""

        def __init__(self, builder, alt_platform: str, source_message=None):
            alt_name = "AO3" if alt_platform == "ao3" else "Wattpad"
            super().__init__(title=f"Link {alt_name} Mirror")
            self.builder        = builder
            self.alt_platform   = alt_platform
            self.source_message = source_message

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
                msg += " Empty chapter summaries have been filled."
            await interaction.followup.send(msg, ephemeral=True, delete_after=6)

            if self.source_message:
                try:
                    await self.source_message.delete()
                except Exception:
                    pass


    class StoryLinksView(ui.View):

        def __init__(self, builder, platform: str = "ao3"):
            super().__init__(timeout=300)
            self.builder  = builder
            self.platform = platform

            alt_label = "🔗 Link AO3 Mirror" if platform == "wattpad" else "🔗 Link Wattpad Mirror"
            alt_btn = ui.Button(label=alt_label, style=discord.ButtonStyle.success, row=0)
            alt_btn.callback = self._link_mirror
            self.add_item(alt_btn)

        async def _link_mirror(self, interaction: discord.Interaction):
            alt_platform = "ao3" if self.platform == "wattpad" else "wattpad"
            await interaction.response.send_modal(
                FicBuildView.AltLinkModal(self.builder, alt_platform, interaction.message)
            )

        @ui.button(label="Edit Link", style=discord.ButtonStyle.primary, row=0)
        async def edit_link1(self, interaction, button):
            await interaction.response.send_modal(
                FicBuildView.LinkModal(self.builder, interaction.message)
            )

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

        link1 = story.get("extra_link_title")

        if _platform == "wattpad":
            _primary_label = "Wattpad"
            _mirror_label  = "AO3 ✔" if _ao3_mirror else "AO3 mirror"
            _mirror_note   = "-# 💡 Linking AO3 will track its stats & fill empty chapter summaries."
        else:
            _primary_label = "AO3"
            _mirror_label  = "Wattpad ✔" if _wp_mirror else "Wattpad mirror"
            _mirror_note   = "-# 💡 Linking Wattpad will track its stats alongside AO3."

        links_display = f"{_primary_label} | {_mirror_label} | {link1 if link1 else 'filler link'}"

        playlist    = story.get("playlist_url")
        title       = story["title"]
        cover_url   = story["cover_url"]
        appreciation = story.get("appreciation")
        roadmap     = story.get("roadmap")
        inspirations = story.get("story_notes")
        summary     = story.get("summary")

        current_tags = get_tags_by_story(self.story_id)

        filled, total, percent = self.get_completion_stats()
        bar = self.build_progress_bar(percent)

        embed = discord.Embed(
            title=f"📚 {title} • {percent}% Complete",
            color=discord.Color.blurple()
        )

        embed.description = (
            f"**{filled}/{total} sections completed**\n"
            f"{bar}"
        )

        if cover_url:
            embed.set_thumbnail(url=cover_url)

        DIVIDER = "─── ✦ ───"

        # ── Cover ────────────────────────────────────────────────────────────
        embed.add_field(
            name="🎨 Cover",
            value=(
                "Upload or change your story cover.\n"
                f"**Current:** *{'Set' if cover_url else 'Not set yet'}*\n"
                f"{DIVIDER}"
            ),
            inline=False
        )

        # ── Tags ─────────────────────────────────────────────────────────────
        _alt_label = "AO3" if _platform == "wattpad" else "Wattpad"
        if current_tags:
            tags_preview = ", ".join(current_tags[:8])
            if len(current_tags) > 8:
                tags_preview += f" +{len(current_tags) - 8} more"
            tags_value = (
                f"Tags are auto-filled from {_primary_label}, but you can edit them freely!\n"
                f"-# 💡 Tip: Paste a {_alt_label} link in the dropdown to import its tags instantly!\n"
                f"**Current:** *{tags_preview}*"
            )
        else:
            tags_value = (
                f"Tags are auto-filled from {_primary_label}, but you can edit them freely!\n"
                f"-# 💡 Tip: Paste a {_alt_label} link in the dropdown to import its tags instantly!\n"
                "**Current:** *None set yet*"
            )

        embed.add_field(
            name="🏷️ Tags",
            value=tags_value + f"\n{DIVIDER}",
            inline=False
        )

        # ── Summary ───────────────────────────────────────────────────────────
        embed.add_field(
            name="📝 Summary",
            value=(
                "The blurb readers see when they view your story.\n"
                f"**Current:** *{self.preview_text(summary, 120) if summary else 'Not set yet'}*\n"
                f"{DIVIDER}"
            ),
            inline=False
        )

        # ── Story Links ───────────────────────────────────────────────────────
        embed.add_field(
            name="🔗 Story Links",
            value=(
                f"{_primary_label} is automatic. Add **one more link** (RoyalRoad, FFN, etc.).\n"
                f"{_mirror_note}\n"
                f"**Current:** *{links_display}*\n"
                f"{DIVIDER}"
            ),
            inline=False
        )

        # ── Playlist ──────────────────────────────────────────────────────────
        embed.add_field(
            name="🎵 Story Playlist",
            value=(
                "Add music that represents the vibe of your story.\n"
                f"**Current:** *{'Set' if playlist else 'Not set yet'}*\n"
                f"{DIVIDER}"
            ),
            inline=False
        )

        # ── Appreciation ──────────────────────────────────────────────────────
        embed.add_field(
            name="💖 Appreciation",
            value=(
                "Leave a message thanking readers or promoting your story.\n"
                f"**Current:** *{self.preview_text(appreciation, 120) if appreciation else f'Thank you so much for reading {title}...'}*\n"
                f"{DIVIDER}"
            ),
            inline=False
        )

        # ── Inspirations ──────────────────────────────────────────────────────
        embed.add_field(
            name="💡 Inspirations",
            value=(
                "Share what inspired this story — songs, other fics, moments, anything.\n"
                f"**Current:** *{self.preview_text(inspirations, 120) if inspirations else 'Not set yet'}*\n"
                f"{DIVIDER}"
            ),
            inline=False
        )

        # ── Roadmap ───────────────────────────────────────────────────────────
        embed.add_field(
            name="🗺 Update Roadmap",
            value=(
                "Share your latest writing progress with readers.\n"
                f"**Current:** *{'Update posted' if roadmap else 'No roadmap update yet'}*"
            ),
            inline=False
        )

        embed.set_footer(
            text="✨ Fic Builder • Configure how readers discover your story"
        )

        return embed


    # =====================================================
    # COMPLETION
    # =====================================================

    def get_completion_stats(self):

        story = unpack_story(self.story)

        filled = 0
        total = len(self.BUILD_FIELDS)

        for field in self.BUILD_FIELDS:

            value = story.get(field)

            if value and str(value).strip():
                filled += 1

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

        story = unpack_story(self.story)
        _platform = self.story["platform"] or "ao3"

        link1 = story.get("extra_link_title")

        if _platform == "wattpad":
            primary_name = "Wattpad"
            mirror_label = "AO3 Mirror"
            mirror_url   = self.story["ao3_url"]
            mirror_note  = (
                "**AO3 Links Will Also Track Chapters!**\n"
                "Adding an AO3 link will display an AO3 button beside Wattpad on Resume, "
                "and auto-fill empty chapter summaries from AO3."
            )
        else:
            primary_name = "AO3"
            mirror_label = "Wattpad Mirror"
            mirror_url   = self.story["wattpad_url"]
            mirror_note  = (
                "**Wattpad Links Will Also Track Chapters!**\n"
                "Adding a Wattpad link will display a Wattpad button beside AO3 on Resume, "
                "and track Wattpad reads, votes, and comments alongside AO3."
            )

        embed = discord.Embed(
            title="🔗 Story Links",
            description="Add or edit links where readers can find your story.",
            color=discord.Color.blurple()
        )
        embed.add_field(name=primary_name, value="Always included", inline=False)
        embed.add_field(
            name=f"🔗 {mirror_label}",
            value=(mirror_url or "Not set") + f"\n\n{mirror_note}",
            inline=False
        )
        embed.add_field(name="Optional Link", value=link1 or "Not set", inline=False)

        await interaction.response.send_message(
            embed=embed,
            view=self.StoryLinksView(self, _platform),
            ephemeral=True,
            delete_after=90
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