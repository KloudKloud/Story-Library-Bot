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


class TagsModal(ui.Modal, title="Edit Tags"):

    tags_input = ui.TextInput(
        label="Tags (comma-separated)",
        style=discord.TextStyle.paragraph,
        placeholder="romance, slow burn, enemies to lovers...",
        required=False,
        max_length=1000,
    )

    def __init__(self, parent_view, current_tags):
        super().__init__()
        self.parent_view = parent_view
        self.tags_input.default = ", ".join(current_tags) if current_tags else ""

    async def on_submit(self, interaction: discord.Interaction):
        from database import get_tags_by_story
        from workers.update_worker import _clear_story_tags, _rebuild_story_tags

        raw = self.tags_input.value or ""
        new_tags = [t.strip().lower() for t in raw.split(",") if t.strip()]

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

        def __init__(self, builder, slot, source_message):
            super().__init__(title="Add Story Link")

            self.builder = builder
            self.slot = slot
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

            if self.slot == 1:
                update_story_metadata(
                    self.builder.story_id,
                    extra_link_title=self.title_input.value,
                    extra_link_url=self.url_input.value
                )
            else:
                update_story_metadata(
                    self.builder.story_id,
                    extra_link2_title=self.title_input.value,
                    extra_link2_url=self.url_input.value
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

    class StoryLinksView(ui.View):

        def __init__(self, builder):
            super().__init__(timeout=300)
            self.builder = builder


        @ui.button(label="Edit Link 1", style=discord.ButtonStyle.primary)
        async def edit_link1(self, interaction, button):

            await interaction.response.send_modal(
                FicBuildView.LinkModal(self.builder, 1, interaction.message)
            )


        @ui.button(label="Edit Link 2", style=discord.ButtonStyle.primary)
        async def edit_link2(self, interaction, button):

            await interaction.response.send_modal(
                FicBuildView.LinkModal(self.builder, 2, interaction.message)
            )    

    def reload_story(self):

        fresh = get_story_by_id(self.story_id)

        if fresh:
            self.story = fresh


    # =====================================================
    # EMBED
    # =====================================================

    def build_embed(self):

        story = unpack_story(self.story)

        link1 = story.get("extra_link_title")
        link2 = story.get("extra_link2_title")

        links_display = []

        links_display.append("AO3")

        if link1:
            links_display.append(link1)
        else:
            links_display.append("Not set")

        if link2:
            links_display.append(link2)
        else:
            links_display.append("Not set")

        
        playlist = story.get("playlist_url")

        title = story["title"]
        cover_url = story["cover_url"]
        appreciation = story.get("appreciation")

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

        # Thumbnail (cover)
        if cover_url:
            embed.set_thumbnail(url=cover_url)

        # ------------------------------------------------
        # BUILDER SECTIONS
        # ------------------------------------------------

        embed.add_field(
            name="🎨 Cover",
            value=(
                "Upload or change your story cover.\n"
                f"**Current:** *{'Set' if cover_url else 'Not set yet'}*"
            ),
            inline=False
        )

        embed.add_field(
            name="🎵 Story Playlist",
            value=(
                "Add music that represents the vibe of your story.\n"
                f"**Current:** *{'Set' if playlist else 'Not set yet'}*"
            ),
            inline=False
        )

        embed.add_field(
            name="🔗 Story Links",
            value=(
                "Share your story across platforms.\n"
                "AO3 is automatic. Add up to **two more links**.\n"
                f"**Current:** *{' | '.join(links_display)}*"
            ),
            inline=False
        )

        embed.add_field(
            name="💖 Appreciation",
            value=(
                "Leave a message thanking readers or promoting your story.\n"
                f"**Current:** *{self.preview_text(appreciation, 120) if appreciation else 'Thank you so much for reading {title}...'}*"
            ),
            inline=False
        )

        roadmap = story.get("roadmap")

        inspirations = story.get("story_notes")

        embed.add_field(
            name="💡 Inspirations",
            value=(
                "Share what inspired this story — songs, other fics, moments, anything.\n"
                f"**Current:** *{self.preview_text(inspirations, 120) if inspirations else 'Not set yet'}*"
            ),
            inline=False
        )

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

        link1 = story.get("extra_link_title")
        link2 = story.get("extra_link2_title")

        embed = discord.Embed(
            title="🔗 Story Links",
            description="Add or edit links where readers can find your story.",
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="AO3",
            value="Always included",
            inline=False
        )

        embed.add_field(
            name="Optional Link #1",
            value=link1 or "Not set",
            inline=True
        )

        embed.add_field(
            name="Optional Link #2",
            value=link2 or "Not set",
            inline=True
        )

        await interaction.response.send_message(
            embed=embed,
            view=self.StoryLinksView(self),
            ephemeral=True,
            delete_after=60
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
                    label="✏️ Edit Title",
                    description="Rename your story in the library.",
                    value="edit_title"
                ),

                discord.SelectOption(
                    label="📝 Edit Summary",
                    description="Rewrite your story's summary.",
                    value="edit_summary"
                ),

                discord.SelectOption(
                    label="🏷️ Add / Edit Tags",
                    description="Update the tags shown on your story.",
                    value="edit_tags"
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
                await interaction.response.send_modal(TagsModal(v, current_tags))

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