import discord
from discord import ui
from ui import TimeoutMixin

PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

_PAGE_SPARKS = ["📚", "🌸", "⭐", "💎", "🌺"]
_DIVIDERS    = [
    "✦ · · ✦ · · ✦ · · ✦",
    "· ˖ ✦ ˖ · ˖ ✦ ˖ ·",
    "⋆ ˚ ✦ ˚ ⋆ · ⋆ ˚ ✦",
]


def build_my_fics_embed(stories: list, page: int, total_pages: int,
                         viewer_name: str,
                         viewer_discord_id: str = None) -> discord.Embed:
    """Build the roster embed for the caller's story list."""
    from database import get_profile_by_discord_id

    start        = page * PAGE_SIZE
    page_stories = stories[start:start + PAGE_SIZE]
    spark        = _PAGE_SPARKS[page % len(_PAGE_SPARKS)]
    divider      = _DIVIDERS[page % len(_DIVIDERS)]

    embed = discord.Embed(
        title=f"{spark}  {viewer_name}'s Stories  {spark}",
        color=discord.Color.from_rgb(105, 185, 255)
    )

    entry_sep = "-# · · · · · · · · · ·"
    lines = [f"-# {divider}"]

    for i, s in enumerate(page_stories):
        # s is a sqlite3.Row / tuple: (id, title, chapter_count, last_updated, word_count, summary)
        title      = s[1]
        chapters   = s[2] or 0
        words      = s[4] or 0
        global_num = start + i + 1

        lines.append(
            f"{NUMBER_EMOJIS[i]}  **{title}**\n"
            f"-# 📖 {chapters} chapters  ·  {words:,} words  ·  #{global_num}"
        )
        if i < len(page_stories) - 1:
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
        text=f"Page {page + 1} of {total_pages}  ·  {len(stories)} "
             f"stor{'ies' if len(stories) != 1 else 'y'} total"
    )
    return embed


# ─────────────────────────────────────────────────────────────
# Story detail view — opened when user clicks a number button
# ─────────────────────────────────────────────────────────────

class MyFicDetailView(TimeoutMixin, ui.View):
    """
    Custom story detail page for /fic myfics.
    Row 0: Extras | Chapters | Cast (N) | Fanart (N) | Return  ← Return is green, rest blue
    Clicking Return sends the user back to the MyFicsView roster at the correct page.
    """

    def __init__(self, story_data: dict, viewer: discord.Member,
                 roster: "MyFicsView", return_page: int):
        super().__init__(timeout=300)
        self.story_data  = story_data   # full dict from get_story_by_id / all_stories_sorted
        self.viewer      = viewer
        self.roster      = roster
        self.return_page = return_page
        self._rebuild_ui()

    def _rebuild_ui(self):
        self.clear_items()

        from database import get_characters_by_story, get_fanart_by_story
        story_id     = self.story_data["id"]
        char_count   = len(get_characters_by_story(story_id))
        fanart_count = len(get_fanart_by_story(story_id))

        # ── Row 0 ──────────────────────────────────────
        extras_btn = ui.Button(
            label="✨ Extras",
            style=discord.ButtonStyle.primary,
            row=0
        )
        extras_btn.callback = self._extras
        self.add_item(extras_btn)

        chapters_btn = ui.Button(
            label="📖 Chapters",
            style=discord.ButtonStyle.primary,
            row=0
        )
        chapters_btn.callback = self._chapters
        self.add_item(chapters_btn)

        cast_btn = ui.Button(
            label=f"🧬 Cast ({char_count})",
            style=discord.ButtonStyle.primary,
            row=0,
            disabled=(char_count == 0)
        )
        cast_btn.callback = self._cast
        self.add_item(cast_btn)

        fanart_btn = ui.Button(
            label=f"🎨 Fanart ({fanart_count})",
            style=discord.ButtonStyle.primary,
            row=0,
            disabled=(fanart_count == 0)
        )
        fanart_btn.callback = self._fanart
        self.add_item(fanart_btn)

        return_btn = ui.Button(
            label="↩️ Return",
            style=discord.ButtonStyle.success,
            row=0
        )
        return_btn.callback = self._return
        self.add_item(return_btn)

    # ── Compatibility interface ───────────────────────
    # Child views (StoryExtrasView, FanartGalleryView) call back on their
    # parent using LibraryView's interface.  We expose just enough so those
    # return paths work without modifying any child view.

    @property
    def current_item(self):
        """Satisfies FanartGalleryView's back_cb library-path check."""
        return self.story_data

    def generate_detail_embed(self, _item=None):
        """Called by StoryExtrasView and FanartGalleryView when returning to the story."""
        return self.build_embed()

    def refresh_ui(self):
        """No-op shim — FanartGalleryView calls this before generate_detail_embed."""
        pass

    # ── End compatibility interface ───────────────────

    def build_embed(self) -> discord.Embed:
        """Reuse the library detail embed so the page looks identical."""
        from features.stories.views.library_view import LibraryView, story_to_dict
        from database import (
            get_user_id, get_story_progress, has_story_badge,
            get_tags_by_story, get_all_stories_sorted
        )
        from features.stories.views.library_view import build_progress_bar, clean_summary

        s    = self.story_data
        uid  = get_user_id(str(self.viewer.id))
        prog = get_story_progress(uid, s["id"]) or 0
        ch   = s.get("chapter_count") or s.get("chapters") or 0
        pct  = int((prog / ch) * 100) if ch else 0

        bar   = ("✨ " + build_progress_bar(pct) + " ✨") if pct == 100 else build_progress_bar(pct)
        badge = "🏅 " if has_story_badge(uid, s["id"]) else ""
        color = discord.Color.gold() if has_story_badge(uid, s["id"]) else discord.Color.dark_teal()

        title  = s.get("title", "Unknown")
        author = s.get("author", "Unknown")
        words  = s.get("word_count") or s.get("words") or 0
        summ   = s.get("summary", "")
        ao3    = s.get("ao3_url") or s.get("ao3", "")
        cover  = s.get("cover_url") or s.get("cover")
        music  = s.get("music_url")
        upd    = s.get("library_updated") or s.get("updated", "")

        embed = discord.Embed(
            title=f"{badge}📖 {title} • ✨ {pct}% Complete",
            description=bar,
            color=color
        )

        if cover:
            embed.set_thumbnail(url=cover)

        summary_text = clean_summary(summ) or "No summary available."
        embed.add_field(
            name="✨ Summary",
            value="\n".join(f"> {line}" for line in summary_text.split("\n")),
            inline=False
        )

        tags = sorted(get_tags_by_story(s["id"]))
        if tags:
            MAX_TAGS = 30
            visible  = tags[:MAX_TAGS]
            tag_str  = " ".join(f"`{t.title()}`" for t in visible)
            if len(tags) > MAX_TAGS:
                tag_str += " • ..."
            embed.add_field(
                name=f"🏷️ Tags ({len(visible)}/{len(tags)})",
                value=f"> {tag_str}",
                inline=False
            )

        rating = s.get("rating")
        if rating:
            embed.add_field(name="🔞 Rating", value=f"`{rating}`", inline=False)

        embed.add_field(
            name="🌸 Story Info",
            value=f"**Author** • {author}\n**Chapters** • {ch}\n**Words** • {words:,}",
            inline=True
        )

        badge_line = "\n> 🏅 Badge Earned" if has_story_badge(uid, s["id"]) else ""
        embed.add_field(
            name="📖 Your Progress",
            value=f"**Progress** • {prog}/{ch}\n**Completion** • {pct}%{badge_line}",
            inline=True
        )

        link_parts = [f"[AO3]({ao3})"] if ao3 else []
        e1t = s.get("extra_link_title")
        e1u = s.get("extra_link_url")
        e2t = s.get("extra_link2_title")
        e2u = s.get("extra_link2_url")
        if e1t and e1u:
            link_parts.append(f"[{e1t}]({e1u})")
        if e2t and e2u:
            link_parts.append(f"[{e2t}]({e2u})")
        if link_parts:
            embed.add_field(name="🔗 Read", value=" ✦ ".join(link_parts), inline=False)

        if music:
            embed.add_field(
                name="🎵 Music Playlist",
                value=f"[Listen While Reading]({music})",
                inline=True
            )

        if cover:
            embed.set_image(url=cover)

        embed.set_footer(text=f"Last Updated • {upd}")
        return embed

    # ── Button callbacks ──────────────────────────────

    async def _extras(self, interaction: discord.Interaction):
        from features.stories.views.story_extras_view import StoryExtrasView
        view = StoryExtrasView(
            story_id=self.story_data["id"],
            library_view=self,          # "Return to Story" in StoryExtrasView goes back here
            viewer=self.viewer
        )
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    async def _chapters(self, interaction: discord.Interaction):
        from features.chapters.chapter_view import ChapterScrollView
        from database import get_chapters_full, get_user_id, get_story_progress

        story_id = self.story_data["id"]
        chapters = get_chapters_full(story_id)

        if not chapters:
            await interaction.response.send_message(
                "No chapters found for this story yet.", ephemeral=True
            )
            return

        uid   = get_user_id(str(interaction.user.id))
        prog  = get_story_progress(uid, story_id) or 0
        start = max(0, min(prog, len(chapters) - 1))

        title     = self.story_data.get("title", "")
        cover_url = self.story_data.get("cover_url") or self.story_data.get("cover")

        view = ChapterScrollView(
            story_id, title, chapters,
            interaction.user, parent_view=self, start_index=start,
            cover_url=cover_url,
            hide_comment=True,
            story_btn_label="↩️ Return"
        )
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    async def _cast(self, interaction: discord.Interaction):
        from features.characters.views.characters_view import StoryCharactersView
        from database import get_characters_by_story

        story_id = self.story_data["id"]
        chars    = get_characters_by_story(story_id)

        if not chars:
            await interaction.response.send_message(
                "No characters for this story yet.", ephemeral=True
            )
            return

        # return_mode="myfics" → hits the else branch in StoryCharactersView.return_btn,
        # which calls parent_view.build_embed() — that's our MyFicDetailView.build_embed()
        view = StoryCharactersView(
            chars, self,
            story_title=self.story_data.get("title", ""),
            viewer=self.viewer,
            return_mode="myfics"
        )
        view.return_btn.label = "↩️ Return"
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    async def _fanart(self, interaction: discord.Interaction):
        from database import get_fanart_by_story
        from features.fanart.views.fanart_gallery_view import FanartGalleryView

        fanart = get_fanart_by_story(self.story_data["id"])
        if not fanart:
            await interaction.response.send_message(
                "No fanart tagged for this story yet.", ephemeral=True
            )
            return

        view = FanartGalleryView(
            fanart, interaction.user,
            minimal=True,
            return_label="📖 Return to Story"
        )
        view.parent_view = self
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    async def _return(self, interaction: discord.Interaction):
        """Go back to the MyFicsView roster at the correct page."""
        self.roster.page = self.return_page
        self.roster._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_my_fics_embed(
                self.roster.stories,
                self.return_page,
                self.roster.total_pages(),
                interaction.user.display_name,
                viewer_discord_id=self.roster.viewer_did
            ),
            view=self.roster
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.", ephemeral=True, delete_after=5
            )
            return False
        return True


# ─────────────────────────────────────────────────────────────
# Roster list view
# ─────────────────────────────────────────────────────────────

class MyFicsView(TimeoutMixin, ui.View):
    """
    Row 0 — up to 5 number buttons (one per story on the page).
             Clicking a number opens MyFicDetailView for that story.
    Row 1 — Prev / Next page navigation, hidden when only 1 page.
    """

    def __init__(self, stories: list, viewer: discord.Member, start_page: int = 0):
        super().__init__(timeout=300)
        self.stories    = stories
        self.viewer     = viewer
        self.viewer_did = str(viewer.id)
        self.page       = start_page
        self._rebuild_ui()

    def total_pages(self) -> int:
        return max(1, (len(self.stories) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _page_stories(self) -> list:
        start = self.page * PAGE_SIZE
        return self.stories[start:start + PAGE_SIZE]

    def _rebuild_ui(self):
        self.clear_items()
        page_stories = self._page_stories()
        count = len(page_stories)

        # ── Row 0: number buttons ────────────────────
        for i in range(count):
            btn = ui.Button(
                emoji=NUMBER_EMOJIS[i],
                style=discord.ButtonStyle.primary,
                row=0
            )
            btn.callback = self._make_open_callback(i)
            self.add_item(btn)

        # ── Row 1: page nav (hidden if only 1 page) ──
        if self.total_pages() > 1:
            prev_btn = ui.Button(
                label="◀ Prev",
                style=discord.ButtonStyle.primary,
                row=1,
                disabled=(self.page == 0)
            )
            prev_btn.callback = self._prev
            self.add_item(prev_btn)

            next_btn = ui.Button(
                label="Next ▶",
                style=discord.ButtonStyle.primary,
                row=1,
                disabled=(self.page >= self.total_pages() - 1)
            )
            next_btn.callback = self._next
            self.add_item(next_btn)

    def _make_open_callback(self, slot_index: int):
        """Open the story detail page for the clicked number."""
        async def callback(interaction: discord.Interaction):
            from database import get_story_by_id

            global_index = self.page * PAGE_SIZE + slot_index
            if global_index >= len(self.stories):
                await interaction.response.send_message(
                    "Story not found.", ephemeral=True
                )
                return

            row      = self.stories[global_index]
            story_id = row[0]

            # get_story_by_id returns a full Row/dict with all fields
            story_data = get_story_by_id(story_id)
            if not story_data:
                await interaction.response.send_message(
                    "❌ Story could not be loaded.", ephemeral=True
                )
                return

            detail_view = MyFicDetailView(
                story_data=dict(story_data),
                viewer=interaction.user,
                roster=self,
                return_page=self.page
            )
            await interaction.response.edit_message(
                embed=detail_view.build_embed(),
                view=detail_view
            )

        return callback

    async def _prev(self, interaction: discord.Interaction):
        self.page -= 1
        self._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_my_fics_embed(
                self.stories, self.page, self.total_pages(),
                interaction.user.display_name,
                viewer_discord_id=self.viewer_did
            ),
            view=self
        )

    async def _next(self, interaction: discord.Interaction):
        self.page += 1
        self._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_my_fics_embed(
                self.stories, self.page, self.total_pages(),
                interaction.user.display_name,
                viewer_discord_id=self.viewer_did
            ),
            view=self
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.", ephemeral=True, delete_after=5
            )
            return False
        return True