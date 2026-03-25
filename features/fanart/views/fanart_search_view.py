"""
fanart_search_view.py  —  /fanart search roster + detail views.

Roster:
  Row 0: 1️⃣–5️⃣ index buttons (blue)
  Row 1: ⬅️  sort (blue, cycles newest/liked/active)  Jump to...  ➡️

Detail:
  Row 0: ⬅️  👍  💬  ↩️ Return  ➡️
  Row 1: "Explore More Fanart..." dropdown
"""

import discord
from discord import ui
import datetime

from embeds.fanart_embeds import build_fanart_embed
from database import (
    get_fanart_characters,
    get_fanart_ships,
    get_fanart_like_count,
    get_fanart_comment_count,
    get_user_id,
    user_has_liked_fanart,
    toggle_fanart_like,
    add_fanart_comment,
    get_character_by_id,
    get_characters_by_ids,
)
from ui import TimeoutMixin

PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

SORT_CYCLE  = ["newest", "liked", "comments"]
SORT_LABELS = {
    "newest":   "🕐 Most Recent",
    "liked":    "👍 Top Likes",
    "comments": "💬 Top Comments",
}


# ─────────────────────────────────────────────────
# Sort helper
# ─────────────────────────────────────────────────

def _sort_fanarts(fanarts: list, sort: str) -> list:
    if sort == "liked":
        return sorted(fanarts, key=lambda f: get_fanart_like_count(f["id"]), reverse=True)
    if sort == "comments":
        return sorted(fanarts, key=lambda f: get_fanart_comment_count(f["id"]), reverse=True)
    def _dt(f):
        try:
            return datetime.datetime.fromisoformat(f.get("created_at") or "")
        except Exception:
            return datetime.datetime.min
    return sorted(fanarts, key=_dt, reverse=True)


# ─────────────────────────────────────────────────
# Roster embed
# ─────────────────────────────────────────────────

# Story-fanart-style sparkle palette & dividers
_SEARCH_COLORS = [
    (255, 182, 193), (255, 218, 185), (179, 255, 179), (153, 229, 255),
    (204, 153, 255), (255, 179, 255), (255, 204, 153), (153, 255, 229),
    (255,  92,  92), (255, 160,  50), ( 80, 220, 100), ( 50, 200, 255),
    (130,  80, 255), (255,  80, 200), (255, 215,   0), (100, 149, 237),
]
_SEARCH_SPARKS    = ["🎨", "🌸", "⭐", "💎", "🌺", "✨", "🔍", "🖼️"]
_SEARCH_DIVIDERS  = [
    "✦ · · ✦ · · ✦ · · ✦",
    "· ˖ ✦ ˖ · ˖ ✦ ˖ ·",
    "⋆ ˚ ✦ ˚ ⋆ · ⋆ ˚ ✦",
    "─ ✦ ─────────── ✦ ─",
]

def build_search_roster_embed(fanarts, page, total_pages, tags, sort, guild=None):
    import random

    start = page * PAGE_SIZE
    chunk = fanarts[start:start + PAGE_SIZE]

    _local_rng = random.Random(page + len(fanarts))
    r, g, b  = _local_rng.choice(_SEARCH_COLORS)
    color    = discord.Color.from_rgb(r, g, b)
    spark    = _SEARCH_SPARKS[page % len(_SEARCH_SPARKS)]
    divider  = _SEARCH_DIVIDERS[page % len(_SEARCH_DIVIDERS)]

    tag_str = "  ✦  ".join(f"`{t}`" for t in tags) if tags else "all fanart"

    entry_sep = "-# · · · · · · · · · ·"
    lines = [f"-# {divider}"]

    embed = discord.Embed(
        title=f"{spark}  Fanart Search  {spark}",
        color=color
    )

    for i, f in enumerate(chunk):
        global_num = page * PAGE_SIZE + i + 1
        title      = f.get("title", "Untitled")
        author     = f.get("display_name") or f.get("username") or "Unknown"
        likes      = get_fanart_like_count(f["id"])
        comments   = get_fanart_comment_count(f["id"])
        chars      = get_fanart_characters(f["id"])
        char_text  = "  ✦  ".join(c["name"] for c in chars[:3]) if chars else "no characters"
        lines.append(
            f"{NUMBER_EMOJIS[i]}  **{title}**\n"
            f"-# 🎨 by {author}  ·  👍 {likes}  ·  💬 {comments}  ·  🧬 {char_text}  ·  #{global_num}"
        )
        if i < len(chunk) - 1:
            lines.append(entry_sep)

    lines.append(f"-# {divider}")
    embed.description = "\n".join(lines)
    embed.set_footer(
        text=f"Page {page+1} of {total_pages}  ·  {len(fanarts)} result{'s' if len(fanarts) != 1 else ''}  ·  {SORT_LABELS[sort]}"
    )
    return embed


# ─────────────────────────────────────────────────
# Comment modal
# ─────────────────────────────────────────────────

class SearchFanartCommentModal(discord.ui.Modal, title="Leave a Comment"):

    content = discord.ui.TextInput(
        label="Your comment",
        style=discord.TextStyle.paragraph,
        placeholder="Share your thoughts on this piece...",
        max_length=1000,
        required=True
    )

    def __init__(self, detail_view: "SearchFanartDetailView"):
        super().__init__()
        self.detail_view = detail_view

    async def on_submit(self, interaction: discord.Interaction):
        uid = get_user_id(str(interaction.user.id))
        if not uid:
            await interaction.response.send_message(
                "No account found.", ephemeral=True, delete_after=4
            )
            return
        add_fanart_comment(uid, self.detail_view.current()["id"], self.content.value)
        self.detail_view._rebuild_ui()
        await interaction.response.send_message(
            "💬 Comment posted!", ephemeral=True, delete_after=3
        )
        if self.detail_view._message:
            try:
                await self.detail_view._message.edit(
                    embed=self.detail_view.build_embed(),
                    view=self.detail_view
                )
            except Exception:
                pass


# ─────────────────────────────────────────────────
# Jump modal
# ─────────────────────────────────────────────────

class SearchJumpModal(discord.ui.Modal, title="Jump to Page"):

    page_num = discord.ui.TextInput(
        label="Page number", placeholder="e.g. 3", max_length=4, required=True
    )

    def __init__(self, roster: "FanartSearchRosterView"):
        super().__init__()
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
# Roster view
# ─────────────────────────────────────────────────

class FanartSearchRosterView(TimeoutMixin, ui.View):

    def __init__(self, fanarts: list, viewer: discord.Member,
                 tags: list, guild=None):
        super().__init__(timeout=300)
        self.all_fanarts = fanarts
        self.viewer      = viewer
        self.tags        = tags
        self.guild       = guild
        self.sort        = "newest"
        self.page        = 0
        self._sorted     = _sort_fanarts(fanarts, self.sort)
        self._rebuild_ui()

    def total_pages(self):
        return max(1, (len(self._sorted) + PAGE_SIZE - 1) // PAGE_SIZE)

    def build_embed(self):
        return build_search_roster_embed(
            self._sorted, self.page, self.total_pages(),
            self.tags, self.sort, self.guild
        )

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
            style=discord.ButtonStyle.primary,  # always blue
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
            detail = SearchFanartDetailView(
                fanarts=self._sorted,
                index=global_index,
                viewer=self.viewer,
                roster=self,
                return_page=self.page
            )
            await interaction.response.edit_message(
                embed=detail.build_embed(), view=detail
            )
            detail._message = interaction.message
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
        idx          = SORT_CYCLE.index(self.sort)
        self.sort    = SORT_CYCLE[(idx + 1) % len(SORT_CYCLE)]
        self._sorted = _sort_fanarts(self.all_fanarts, self.sort)
        self.page    = 0
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _jump(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SearchJumpModal(self))


# ─────────────────────────────────────────────────
# Detail view
# Row 0: ⬅️  👍  💬  ↩️ Return  ➡️
# Row 1: "Explore More Fanart..." dropdown
# ─────────────────────────────────────────────────

class SearchFanartDetailView(TimeoutMixin, ui.View):

    def __init__(self, fanarts: list, index: int,
                 viewer: discord.Member,
                 roster: FanartSearchRosterView,
                 return_page: int):
        super().__init__(timeout=300)
        self.fanarts     = fanarts
        self.index       = index
        self.viewer      = viewer
        self.roster      = roster
        self.return_page = return_page
        self._message    = None
        self._rebuild_ui()

    def current(self):
        return self.fanarts[self.index]

    def build_embed(self) -> discord.Embed:
        f     = self.current()
        chars = get_fanart_characters(f["id"])
        ships = get_fanart_ships(f["id"])
        likes = get_fanart_like_count(f["id"])
        embed = build_fanart_embed(
            f, index=self.index + 1, total=len(self.fanarts),
            characters=chars, ships=ships
        )
        existing = embed.footer.text or ""
        embed.set_footer(text=f"{existing}  ·  👍 {likes}" if existing else f"👍 {likes}")
        return embed

    def _rebuild_ui(self):
        self.clear_items()
        f        = self.current()
        total    = len(self.fanarts)
        uid      = get_user_id(str(self.viewer.id))
        liked    = user_has_liked_fanart(uid, f["id"]) if uid else False
        chars    = get_fanart_characters(f["id"])
        ships    = get_fanart_ships(f["id"])
        story_id = f.get("story_id")

        # ── Row 0 ─────────────────────────────────────────────────
        prev_btn = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index == 0)
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        like_btn = ui.Button(
            emoji="👍",
            style=discord.ButtonStyle.success if liked else discord.ButtonStyle.secondary,
            row=0
        )
        like_btn.callback = self._like
        self.add_item(like_btn)

        comment_btn = ui.Button(
            emoji="💬", style=discord.ButtonStyle.primary, row=0
        )
        comment_btn.callback = self._comment
        self.add_item(comment_btn)

        return_btn = ui.Button(
            label="↩️ Return", style=discord.ButtonStyle.success, row=0
        )
        return_btn.callback = self._return_to_roster
        self.add_item(return_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index >= total - 1)
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

        # ── Row 1: Explore More Fanart... dropdown ─────────────────
        options = []

        # ── View Comments (always first) ──────────────────────────
        n_comments = get_fanart_comment_count(f["id"])
        options.append(discord.SelectOption(
            label=f"View Comments ({n_comments})",
            emoji="💬",
            value="view_comments"
        ))

        # ── Characters: ONE combined option ───────────────────────
        if chars:
            names = [c["name"] for c in chars]
            if len(names) <= 3:
                char_label = ", ".join(names)
            else:
                char_label = ", ".join(names[:3]) + " and more"
            # Store all char IDs pipe-separated
            char_ids = "|".join(str(c["id"]) for c in chars)
            options.append(discord.SelectOption(
                label=f"View {char_label} character cards"[:100],
                emoji="🧬",
                value=f"chars:{char_ids}"
            ))

        # ── Story ──────────────────────────────────────────────────
        if story_id:
            story_title = f.get("story_title") or "linked story"
            options.append(discord.SelectOption(
                label=f"View {story_title}"[:100],
                emoji="📖",
                value=f"story:{story_id}"
            ))

        # ── Author ─────────────────────────────────────────────────
        if story_id:
            author_name = f.get("author") or f.get("username")
            if not author_name:
                try:
                    from database import get_story_by_id as _gsbi
                    _s = _gsbi(story_id)
                    if _s:
                        author_name = _s["author"]
                except Exception:
                    pass
            author_name = author_name or "Unknown Author"
            options.append(discord.SelectOption(
                label=f"✍️ View {author_name}"[:100],
                emoji="✍️",
                value=f"author:{story_id}"
            ))

        # ── Ships: see more fanart per ship ──────────────────────────
        for s in ships[:3]:
            options.append(discord.SelectOption(
                label=f"See more {s['name']} fanart"[:100],
                emoji="💞",
                value=f"more_ship:{s['name']}"
            ))

        # ── See more fanart by character(s) ───────────────────────
        for c in chars[:3]:
            options.append(discord.SelectOption(
                label=f"See more {c['name']} fanart"[:100],
                emoji="🖼️",
                value=f"more_char:{c['name']}"
            ))

        # ── See more fanart from story ─────────────────────────────
        if story_id:
            story_title = f.get("story_title") or "this story"
            options.append(discord.SelectOption(
                label=f"See more from {story_title}"[:100],
                emoji="📚",
                value=f"more_story:{story_id}"
            ))

        explore = ui.Select(
            placeholder="✨ Explore More Fanart...",
            options=options[:25],
            row=1
        )
        explore.callback = self._explore
        self.add_item(explore)

    # ── Row 0 callbacks ───────────────────────────────────────────

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
        self._message = interaction.message
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.index = min(len(self.fanarts) - 1, self.index + 1)
        self._rebuild_ui()
        self._message = interaction.message
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _like(self, interaction: discord.Interaction):
        uid = get_user_id(str(interaction.user.id))
        if not uid:
            await interaction.response.send_message("❌ Profile not found.", ephemeral=True)
            return
        f = self.current()
        was_liked = user_has_liked_fanart(uid, f["id"])
        toggle_fanart_like(uid, f["id"])
        self._rebuild_ui()
        self._message = interaction.message
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        msg = await interaction.followup.send(
            f"💔 Removed **{f.get('title', 'this piece')}** from liked!" if was_liked
            else f"👍 Added **{f.get('title', 'this piece')}** to your likes!",
            ephemeral=True, wait=True
        )
        import asyncio
        await asyncio.sleep(2)
        try:
            await msg.delete()
        except Exception:
            pass

    async def _comment(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SearchFanartCommentModal(self))

    async def _return_to_roster(self, interaction: discord.Interaction):
        self.roster.page = self.return_page
        self.roster._rebuild_ui()
        await interaction.response.edit_message(
            embed=self.roster.build_embed(), view=self.roster
        )

    # ── Dropdown callback ─────────────────────────────────────────

    async def _explore(self, interaction: discord.Interaction):
        select = next((c for c in self.children if isinstance(c, ui.Select)), None)
        value  = select.values[0] if select and select.values else ""

        # ── View Comments ────────────────────────────────────────
        if value == "view_comments":
            from features.fanart.views.my_fanart_view import FanartCommentsView
            n = get_fanart_comment_count(self.current()["id"])
            if n == 0:
                await interaction.response.send_message(
                    "✦ No comments on this piece yet. Be the first!",
                    ephemeral=True, delete_after=3
                )
                return
            cv = FanartCommentsView(self.current(), self, guild=interaction.guild)
            self._message = interaction.message
            await interaction.response.edit_message(
                embed=await cv.build_embed(), view=cv
            )
            return

        # ── View character card slideshow ─────────────────────────
        if value.startswith("chars:"):
            char_ids = [int(x) for x in value.split(":")[1].split("|") if x]
            characters = get_characters_by_ids(char_ids)
            if not characters:
                await interaction.response.send_message(
                    "Characters not found.", ephemeral=True, delete_after=3
                )
                return
            view = SearchCharSlideView(
                characters=characters,
                viewer=self.viewer,
                back_detail=self
            )
            await interaction.response.edit_message(
                embed=view.build_embed(), view=view
            )
            return

        # ── View story (library-style embed) ──────────────────────
        if value.startswith("story:"):
            story_id = int(value.split(":")[1])
            view = SearchStoryView(
                story_id=story_id,
                viewer=interaction.user,
                back_detail=self
            )
            embed = view.build_story_embed()
            if not embed:
                await interaction.response.send_message(
                    "Story not found.", ephemeral=True, delete_after=3
                )
                return
            await interaction.response.edit_message(embed=embed, view=view)
            return

        # ── View author ───────────────────────────────────────────
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
            view = SearchAuthorView(
                stories=stories,
                viewer=interaction.user,
                target_user=target,
                back_detail=self
            )
            await interaction.response.edit_message(
                embed=view.generate_bio_embed(), view=view
            )
            return

        # ── See more fanart by character ──────────────────────────
        if value.startswith("more_char:"):
            char_name = value.split(":", 1)[1]
            from database import search_fanart
            results = search_fanart(character=char_name)
            if not results:
                await interaction.response.send_message(
                    f"No fanart found featuring {char_name}.",
                    ephemeral=True, delete_after=3
                )
                return
            new_view = SearchFanartDetailView(
                fanarts=results,
                index=0,
                viewer=self.viewer,
                roster=self.roster,
                return_page=self.return_page
            )
            await interaction.response.edit_message(
                embed=new_view.build_embed(), view=new_view
            )
            new_view._message = interaction.message
            return

        # ── See more fanart by ship ───────────────────────────────
        if value.startswith("more_ship:"):
            ship_name = value.split(":", 1)[1]
            from database import search_fanart
            results = search_fanart(ship=ship_name)
            if not results:
                await interaction.response.send_message(
                    f"No fanart found featuring {ship_name}.",
                    ephemeral=True, delete_after=3
                )
                return
            new_view = SearchFanartDetailView(
                fanarts=results,
                index=0,
                viewer=self.viewer,
                roster=self.roster,
                return_page=self.return_page
            )
            await interaction.response.edit_message(
                embed=new_view.build_embed(), view=new_view
            )
            new_view._message = interaction.message
            return

        # ── See more fanart from story ─────────────────────────────
        if value.startswith("more_story:"):
            story_id = int(value.split(":")[1])
            from database import get_fanart_by_story
            results = get_fanart_by_story(story_id)
            if not results:
                await interaction.response.send_message(
                    "No fanart found for that story.",
                    ephemeral=True, delete_after=3
                )
                return
            new_view = SearchFanartDetailView(
                fanarts=results,
                index=0,
                viewer=self.viewer,
                roster=self.roster,
                return_page=self.return_page
            )
            await interaction.response.edit_message(
                embed=new_view.build_embed(), view=new_view
            )
            new_view._message = interaction.message
            return


# ─────────────────────────────────────────────────
# Story view (library-style)
# Row 0: Extras  ↩️ Return
# ─────────────────────────────────────────────────

class SearchStoryView(TimeoutMixin, ui.View):

    def __init__(self, story_id: int, viewer: discord.Member,
                 back_detail: SearchFanartDetailView):
        super().__init__(timeout=300)
        self.story_id    = story_id
        self.viewer      = viewer
        self.back_detail = back_detail

        from database import get_story_by_id as _gsbi
        _row = _gsbi(story_id)
        _is_dummy = bool(_row and _row["is_dummy"]) if _row else False

        if not _is_dummy:
            extras_btn = ui.Button(
                label="✨ Extras", style=discord.ButtonStyle.primary, row=0
            )
            extras_btn.callback = self._extras
            self.add_item(extras_btn)

        return_btn = ui.Button(
            label="↩️ Return", style=discord.ButtonStyle.success, row=0
        )
        return_btn.callback = self._return
        self.add_item(return_btn)

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

    def build_story_embed(self):
        """
        Full library-style embed using direct column-name access on the
        SQLite row — avoids the index-mapping issues with story_to_dict.
        """
        from features.stories.views.library_view import build_progress_bar, clean_summary
        from database import (
            get_story_by_id, get_story_progress, get_user_id,
            has_story_badge, get_tags_by_story
        )

        row = get_story_by_id(self.story_id)
        if not row:
            return None

        if row["is_dummy"]:
            return discord.Embed(
                title="📦 Character Storage",
                description=(
                    "This character doesn't belong to a particular story!\n\n"
                    "They're stored in their author's private Character Storage — "
                    "a personal space for characters that haven't been assigned to a story yet."
                ),
                color=discord.Color.blurple()
            )

        # Access columns by name — works with SELECT * rows
        story_id   = row["id"]
        title      = row["title"]      or "Untitled"
        author     = row["author"]     or "?"
        ao3        = row["ao3_url"]    or ""
        ch         = int(row["chapter_count"] or 1)
        upd        = row["last_updated"]      or ""
        lib_upd    = row["library_updated"]   or ""
        words      = int(row["word_count"]    or 0)
        summary    = row["summary"]    or ""
        cover      = row["cover_url"]  or ""
        music      = row["playlist_url"] or ""
        rating     = row["rating"]     or ""
        e1t        = row["extra_link_title"]  or ""
        e1u        = row["extra_link_url"]    or ""
        e2t        = row["extra_link2_title"] or ""
        e2u        = row["extra_link2_url"]   or ""

        uid      = get_user_id(str(self.viewer.id))
        progress = int(get_story_progress(uid, story_id) or 0)
        percent  = int((progress / ch) * 100) if ch else 0
        bar      = ("✨ " + build_progress_bar(percent) + " ✨") if percent == 100 else build_progress_bar(percent)
        badge    = "🏅 " if has_story_badge(uid, story_id) else ""
        color    = discord.Color.gold() if has_story_badge(uid, story_id) else discord.Color.dark_teal()

        embed = discord.Embed(
            title=f"{badge}📖 {title} • ✨ {percent}% Complete",
            description=bar,
            color=color
        )

        if cover.startswith("http"):
            embed.set_thumbnail(url=cover)

        # Summary
        summary_text = clean_summary(summary) or "No summary available."
        embed.add_field(
            name="✨ Summary",
            value="\n".join(f"> {line}" for line in summary_text.split("\n")),
            inline=False
        )

        # Tags
        tags = sorted(get_tags_by_story(story_id))
        if tags:
            MAX_TAGS   = 30
            visible    = tags[:MAX_TAGS]
            tag_string = " ".join(f"`{t.title()}`" for t in visible)
            if len(tags) > MAX_TAGS:
                tag_string += " • ..."
            embed.add_field(name=f"🏷️ Tags ({len(visible)}/{len(tags)})", value=f"> {tag_string}", inline=False)

        # Rating
        if rating:
            embed.add_field(name="🔞 Rating", value=f"`{rating}`", inline=False)

        # Story Info + Progress (inline pair)
        badge_line = "\n> 🏅 Badge Earned" if has_story_badge(uid, story_id) else ""
        embed.add_field(
            name="🌸 Story Info",
            value=f"**Author** • {author}\n**Chapters** • {ch}\n**Words** • {words:,}",
            inline=True
        )
        embed.add_field(
            name="📖 Your Progress",
            value=f"**Progress** • {progress}/{ch}\n**Completion** • {percent}%{badge_line}",
            inline=True
        )

        # Links
        link_list = [f"[AO3]({ao3})"] if ao3 else []
        if e1t and e1u:
            link_list.append(f"[{e1t}]({e1u})")
        if e2t and e2u:
            link_list.append(f"[{e2t}]({e2u})")
        if link_list:
            embed.add_field(name="🔗 Read", value=" ✦ ".join(link_list), inline=False)

        # Music playlist (from /fic build)
        if music.startswith("http"):
            embed.add_field(name="🎵 Music Playlist", value=f"[Listen While Reading]({music})", inline=True)

        # Cover as full-width image
        if cover.startswith("http"):
            embed.set_image(url=cover)

        embed.set_footer(text=f"Last Updated • {lib_upd or upd}")
        return embed


    async def _extras(self, interaction: discord.Interaction):
        from features.stories.views.story_extras_view import StoryExtrasView
        from embeds.story_notes_embed import build_story_notes_embed
        from database import get_story_by_id

        story = get_story_by_id(self.story_id)
        extras = StoryExtrasView(story_id=self.story_id, viewer=interaction.user, stats_mode=True)

        # Replace "Return to Story" with going back to this library-style view
        return_btn = ui.Button(
            label="↩️ Return", style=discord.ButtonStyle.success, row=0
        )
        async def _back(i):
            await i.response.edit_message(embed=self.build_story_embed(), view=self)
        return_btn.callback = _back
        extras.add_item(return_btn)

        await interaction.response.edit_message(
            embed=build_story_notes_embed(story, viewer=interaction.user),
            view=extras
        )

    async def _return(self, interaction: discord.Interaction):
        self.back_detail._rebuild_ui()
        await interaction.response.edit_message(
            embed=self.back_detail.build_embed(),
            view=self.back_detail
        )


# ─────────────────────────────────────────────────
# Character slideshow from Explore
# Row 0: ⬅️  ✦ Favorite  📜 Lore  ➡️
# Row 1: "Return to fanart search..." dropdown
# ─────────────────────────────────────────────────

class SearchCharSlideView(TimeoutMixin, ui.View):

    def __init__(self, characters: list, viewer: discord.Member,
                 back_detail: SearchFanartDetailView):
        super().__init__(timeout=300)
        self.characters  = characters
        self.viewer      = viewer
        self.back_detail = back_detail
        self.index       = 0
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

    def current(self):
        return self.characters[self.index]

    def build_embed(self):
        from embeds.character_embeds import build_character_card
        return build_character_card(
            self.current(),
            viewer=self.viewer,
            index=self.index + 1,
            total=len(self.characters)
        )

    def _rebuild_ui(self):
        self.clear_items()
        char  = self.current()
        total = len(self.characters)
        from database import is_favorite_character

        prev_btn = ui.Button(
            emoji="⬅️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index == 0)
        )
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

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
            label="📜 Lore", style=discord.ButtonStyle.primary,
            row=0, disabled=not bool(char.get("lore"))
        )
        lore_btn.callback = self._lore
        self.add_item(lore_btn)

        next_btn = ui.Button(
            emoji="➡️", style=discord.ButtonStyle.secondary,
            row=0, disabled=(self.index >= total - 1)
        )
        next_btn.callback = self._next
        self.add_item(next_btn)

        return_select = ui.Select(
            placeholder="↩️ Return to fanart search...",
            options=[discord.SelectOption(
                label="Return to fanart search",
                emoji="🔍",
                value="__return__"
            )],
            row=1
        )
        return_select.callback = self._return
        self.add_item(return_select)

    async def _prev(self, interaction: discord.Interaction):
        self.index = max(0, self.index - 1)
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.index = min(len(self.characters) - 1, self.index + 1)
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _fav(self, interaction: discord.Interaction):
        from features.characters.views.favorite_helpers import handle_fav_toggle
        char = self.current()
        async def _refresh(i):
            self._rebuild_ui()
            await i.response.edit_message(content=None, embed=self.build_embed(), view=self)
        await handle_fav_toggle(interaction, char, _refresh)

    async def _lore(self, interaction: discord.Interaction):
        from embeds.character_embeds import build_lore_embed
        char = self.current()
        lore = char.get("lore")
        if not lore:
            await interaction.response.send_message("No lore written yet.", ephemeral=True, delete_after=5)
            return
        await interaction.response.send_message(embed=build_lore_embed(char["name"], lore), ephemeral=True)

    async def _return(self, interaction: discord.Interaction):
        self.back_detail._rebuild_ui()
        await interaction.response.edit_message(
            embed=self.back_detail.build_embed(),
            view=self.back_detail
        )


# ─────────────────────────────────────────────────
# Author view from Explore — bio + Return
# ─────────────────────────────────────────────────

class SearchAuthorView(TimeoutMixin, ui.View):

    def __init__(self, stories: list, viewer: discord.Member,
                 target_user: discord.Member,
                 back_detail: SearchFanartDetailView):
        super().__init__(timeout=300)
        self.stories     = stories
        self.viewer      = viewer
        self.target_user = target_user
        self.back_detail = back_detail

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

        return_btn = ui.Button(
            label="↩️ Return", style=discord.ButtonStyle.success, row=0
        )
        return_btn.callback = self._return
        self.add_item(return_btn)

    def generate_bio_embed(self):
        from features.stories.views.showcase_view import ShowcaseView
        temp = ShowcaseView(
            self.stories, self.viewer, self.target_user, source="fanart"
        )
        return temp.generate_bio_embed()

    async def _return(self, interaction: discord.Interaction):
        self.back_detail._rebuild_ui()
        await interaction.response.edit_message(
            embed=self.back_detail.build_embed(),
            view=self.back_detail
        )