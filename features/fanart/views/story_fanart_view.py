import discord
from discord import ui

from database import (
    get_fanart_characters,
    get_fanart_ships,
    get_discord_id_by_story,
    get_stories_by_discord_user,
)
from embeds.fanart_embeds import build_fanart_embed
from features.stories.views.showcase_view import ShowcaseView

import random as _random
from ui import TimeoutMixin

FANART_COLORS = [
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
    (255, 215,   0), (192, 192, 192), (255, 127,  80), (100, 149, 237), (144, 238, 144),
]

def _random_color():
    r, g, b = _random.choice(FANART_COLORS)
    return discord.Color.from_rgb(r, g, b)


PAGE_SIZE     = 5
NUMBER_EMOJIS = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"]

_SPARKS   = ["🎨","🌸","⭐","💎","🌺"]
_DIVIDERS = [
    "✦ · · ✦ · · ✦ · · ✦",
    "· ˖ ✦ ˖ · ˖ ✦ ˖ ·",
    "⋆ ˚ ✦ ˚ ⋆ · ⋆ ˚ ✦",
]


# ─────────────────────────────────────────────────
# Roster embed
# ─────────────────────────────────────────────────

def build_story_fanart_list_embed(fanarts: list, page: int,
                                   total_pages: int, story_title: str) -> discord.Embed:
    start      = page * PAGE_SIZE
    page_items = fanarts[start:start + PAGE_SIZE]
    spark      = _SPARKS[page % len(_SPARKS)]
    divider    = _DIVIDERS[page % len(_DIVIDERS)]

    embed = discord.Embed(
        title=f"{spark}  {story_title} — Fanart  {spark}",
        color=_random_color()
    )

    entry_sep = "-# · · · · · · · · · ·"
    lines = [f"-# {divider}"]

    for i, f in enumerate(page_items):
        global_num = start + i + 1
        artist     = f.get("artist_name") or "Unknown Artist"
        lines.append(
            f"{NUMBER_EMOJIS[i]}  **{f['title']}**\n"
            f"-# 🎨 {artist}  ·  #{global_num}"
        )
        if i < len(page_items) - 1:
            lines.append(entry_sep)

    lines.append(f"-# {divider}")
    embed.description = "\n".join(lines)
    embed.set_footer(
        text=f"Page {page + 1} of {total_pages}  ·  {len(fanarts)} piece{'s' if len(fanarts) != 1 else ''}"
    )
    return embed


# ─────────────────────────────────────────────────
# Jump-to-page modal
# ─────────────────────────────────────────────────

class _FanartJumpModal(discord.ui.Modal, title="Jump to Page"):
    page_num = discord.ui.TextInput(
        label="Page number", placeholder="e.g. 2", max_length=4, required=True
    )

    def __init__(self, roster_view: "StoryFanartRosterView"):
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
            embed=build_story_fanart_list_embed(
                self.roster_view.fanarts,
                self.roster_view.page,
                total,
                self.roster_view.story_title
            ),
            view=self.roster_view
        )


# ─────────────────────────────────────────────────
# Fanart detail view
# ─────────────────────────────────────────────────

class StoryFanartDetailView(TimeoutMixin, ui.View):
    """
    Row 0: ⬅️ | 👍 | 💬 | ↩️ Return | ➡️
    Row 1: Explore More Fanart... dropdown  (includes See <author>'s profile)
    """

    def __init__(self, fanarts: list, index: int,
                 viewer: discord.Member, roster: "StoryFanartRosterView",
                 return_page: int):
        super().__init__(timeout=300)
        self.fanarts     = fanarts
        self.index       = index
        self.viewer      = viewer
        self.roster      = roster
        self.return_page = return_page
        self._rebuild_ui()

    def current(self):
        return self.fanarts[self.index]

    def build_embed(self) -> discord.Embed:
        from database import get_fanart_like_count
        f = self.current()
        chars = get_fanart_characters(f["id"])
        ships = get_fanart_ships(f["id"])
        likes = get_fanart_like_count(f["id"])
        embed = build_fanart_embed(
            f,
            index=self.index + 1,
            total=len(self.fanarts),
            characters=chars,
            ships=ships
        )
        # Append like count to footer
        existing_footer = embed.footer.text or ""
        embed.set_footer(text=f"{existing_footer}  ·  👍 {likes}" if existing_footer else f"👍 {likes}")
        return embed

    def _rebuild_ui(self):
        self.clear_items()
        f       = self.current()
        total   = len(self.fanarts)
        chars   = get_fanart_characters(f["id"])
        ships   = get_fanart_ships(f["id"])
        story_id = f.get("story_id")

        from database import get_user_id, user_has_liked_fanart
        uid     = get_user_id(str(self.viewer.id))
        liked   = user_has_liked_fanart(uid, f["id"]) if uid else False

        # ── Row 0 ──────────────────────────────────
        prev_btn = ui.Button(emoji="⬅️", style=discord.ButtonStyle.secondary,
                             row=0, disabled=(self.index == 0))
        prev_btn.callback = self._prev
        self.add_item(prev_btn)

        like_btn = ui.Button(
            emoji="👍",
            style=discord.ButtonStyle.success if liked else discord.ButtonStyle.secondary,
            row=0
        )
        like_btn.callback = self._like
        self.add_item(like_btn)

        comment_btn = ui.Button(emoji="💬", style=discord.ButtonStyle.primary, row=0)
        comment_btn.callback = self._comment
        self.add_item(comment_btn)

        return_btn = ui.Button(label="↩️ Return", style=discord.ButtonStyle.success, row=0)
        return_btn.callback = self._return
        self.add_item(return_btn)

        next_btn = ui.Button(emoji="➡️", style=discord.ButtonStyle.secondary,
                             row=0, disabled=(self.index >= total - 1))
        next_btn.callback = self._next
        self.add_item(next_btn)

        # ── Row 1: Explore More Fanart... dropdown ─────────────────
        options = []

        # View Comments (always first)
        from database import get_fanart_comment_count
        n_comments = get_fanart_comment_count(f["id"])
        options.append(discord.SelectOption(
            label=f"View Comments ({n_comments})",
            emoji="💬",
            value="view_comments"
        ))

        # Characters: ONE combined option
        if chars:
            names = [c["name"] for c in chars]
            char_label = ", ".join(names[:3]) + (" and more" if len(names) > 3 else "")
            char_ids   = "|".join(str(c["id"]) for c in chars)
            options.append(discord.SelectOption(
                label=f"View {char_label} character cards"[:100],
                emoji="🧬",
                value=f"chars:{char_ids}"
            ))

        # Story
        if story_id:
            story_title = f.get("story_title") or "linked story"
            options.append(discord.SelectOption(
                label=f"View {story_title}"[:100],
                emoji="📖",
                value=f"story:{story_id}"
            ))

        # Author
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

        # See more fanart by character
        # ── Ships: see more fanart per ship ──────────────────────────
        for s in ships[:3]:
            options.append(discord.SelectOption(
                label=f"See more {s['name']} fanart"[:100],
                emoji="💞",
                value=f"more_ship:{s['name']}"
            ))


        for c in chars[:3]:
            options.append(discord.SelectOption(
                label=f"See more {c['name']} fanart"[:100],
                emoji="🖼️",
                value=f"more_char:{c['name']}"
            ))

        # See more from story
        if story_id:
            story_title = f.get("story_title") or "this story"
            options.append(discord.SelectOption(
                label=f"See more from {story_title}"[:100],
                emoji="📚",
                value=f"more_story:{story_id}"
            ))

        if not options:
            options.append(discord.SelectOption(
                label="No related fanart available", value="none", emoji="🌙"
            ))

        explore = ui.Select(
            placeholder="✨ Explore More Fanart...",
            options=options[:25],
            row=1
        )
        explore.callback = self._explore
        self.add_item(explore)

    # ── Callbacks ────────────────────────────────

    async def _prev(self, interaction: discord.Interaction):
        self.index = max(0, self.index - 1)
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.index = min(len(self.fanarts) - 1, self.index + 1)
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _like(self, interaction: discord.Interaction):
        from database import get_user_id, toggle_fanart_like, user_has_liked_fanart
        import asyncio
        uid = get_user_id(str(interaction.user.id))
        if not uid:
            await interaction.response.send_message("❌ Profile not found.", ephemeral=True)
            return
        f = self.current()
        was_liked = user_has_liked_fanart(uid, f["id"])
        toggle_fanart_like(uid, f["id"])
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        msg = await interaction.followup.send(
            f"💔 Removed **{f.get('title', 'this piece')}** from liked!" if was_liked
            else f"👍 Added **{f.get('title', 'this piece')}** to your likes!",
            ephemeral=True, wait=True
        )
        await asyncio.sleep(2)
        try:
            await msg.delete()
        except Exception:
            pass

    async def _comment(self, interaction: discord.Interaction):
        from features.fanart.views.fanart_search_view import SearchFanartCommentModal
        await interaction.response.send_modal(SearchFanartCommentModal(self))

    async def _return(self, interaction: discord.Interaction):
        self.roster.page = self.return_page
        self.roster._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_story_fanart_list_embed(
                self.roster.fanarts,
                self.return_page,
                self.roster.total_pages(),
                self.roster.story_title
            ),
            view=self.roster
        )

    async def _explore(self, interaction: discord.Interaction):
        select = next((c for c in self.children if isinstance(c, ui.Select)), None)
        value  = select.values[0] if select and select.values else ""

        if value == "none":
            await interaction.response.send_message(
                "No related fanart found.", ephemeral=True, delete_after=3
            )
            return

        # View Comments
        if value == "view_comments":
            from features.fanart.views.my_fanart_view import FanartCommentsView
            from database import get_fanart_comment_count
            n = get_fanart_comment_count(self.current()["id"])
            if n == 0:
                await interaction.response.send_message(
                    "✦ No comments on this piece yet. Be the first!",
                    ephemeral=True, delete_after=3
                )
                return
            cv = FanartCommentsView(self.current(), self, guild=interaction.guild)
            await interaction.response.edit_message(
                embed=await cv.build_embed(), view=cv
            )
            return

        # View character cards slideshow
        if value.startswith("chars:"):
            from database import get_characters_by_ids
            char_ids   = [int(x) for x in value.split(":")[1].split("|") if x]
            characters = get_characters_by_ids(char_ids)
            if not characters:
                await interaction.response.send_message(
                    "Characters not found.", ephemeral=True, delete_after=3
                )
                return
            from features.fanart.views.fanart_search_view import SearchCharSlideView
            view = SearchCharSlideView(characters=characters, viewer=self.viewer, back_detail=self)
            await interaction.response.edit_message(embed=view.build_embed(), view=view)
            return

        # View story (library-style)
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

        # View author
        if value.startswith("author:"):
            story_id = int(value.split(":")[1])
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

        # See more fanart by character
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
            from features.fanart.views.fanart_search_view import SearchFanartDetailView, FanartSearchRosterView
            dummy_roster = FanartSearchRosterView(results, self.viewer, [], guild=interaction.guild)
            new_view = SearchFanartDetailView(
                fanarts=results, index=0, viewer=self.viewer,
                roster=dummy_roster, return_page=0
            )
            await interaction.response.edit_message(embed=new_view.build_embed(), view=new_view)
            new_view._message = interaction.message
            return

        # ── See more fanart by ship ───────────────────────────────────
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
            from features.fanart.views.fanart_search_view import SearchFanartDetailView, FanartSearchRosterView
            dummy_roster = FanartSearchRosterView(results, self.viewer, [], guild=interaction.guild)
            new_view = SearchFanartDetailView(
                fanarts=results, index=0, viewer=self.viewer,
                roster=dummy_roster, return_page=0
            )
            await interaction.response.edit_message(embed=new_view.build_embed(), view=new_view)
            new_view._message = interaction.message
            return

        # See more fanart from story
        if value.startswith("more_story:"):
            story_id = int(value.split(":")[1])
            from database import get_fanart_by_story
            results = get_fanart_by_story(story_id)
            if not results:
                await interaction.response.send_message(
                    "No fanart found for that story.", ephemeral=True, delete_after=3
                )
                return
            from features.fanart.views.fanart_search_view import SearchFanartDetailView, FanartSearchRosterView
            dummy_roster = FanartSearchRosterView(results, self.viewer, [], guild=interaction.guild)
            new_view = SearchFanartDetailView(
                fanarts=results, index=0, viewer=self.viewer,
                roster=dummy_roster, return_page=0
            )
            await interaction.response.edit_message(embed=new_view.build_embed(), view=new_view)
            new_view._message = interaction.message
            return

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.", ephemeral=True, delete_after=5
            )
            return False
        return True


# ─────────────────────────────────────────────────
# Roster list view
# ─────────────────────────────────────────────────

class StoryFanartRosterView(TimeoutMixin, ui.View):
    """
    Row 0: 1-5 number buttons
    Row 1: ⬅️  Jump to... (blue)  ➡️   — hidden when only 1 page
    """

    def __init__(self, fanarts: list, viewer: discord.Member,
                 story_title: str, start_page: int = 0):
        super().__init__(timeout=300)
        self.fanarts     = fanarts
        self.viewer      = viewer
        self.story_title = story_title
        self.page        = start_page
        self._rebuild_ui()

    def total_pages(self) -> int:
        return max(1, (len(self.fanarts) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _page_fanarts(self) -> list:
        start = self.page * PAGE_SIZE
        return self.fanarts[start:start + PAGE_SIZE]

    def _rebuild_ui(self):
        self.clear_items()
        page_items = self._page_fanarts()
        count      = len(page_items)

        # Row 0: number buttons
        for i in range(count):
            btn = ui.Button(
                emoji=NUMBER_EMOJIS[i],
                style=discord.ButtonStyle.primary,
                row=0
            )
            btn.callback = self._make_open_cb(i)
            self.add_item(btn)

        # Row 1: ◀ Jump to... ▶  (only if >1 page)
        if self.total_pages() > 1:
            prev_btn = ui.Button(
                emoji="⬅️", style=discord.ButtonStyle.secondary,
                row=1, disabled=(self.page == 0)
            )
            prev_btn.callback = self._prev
            self.add_item(prev_btn)

            jump_btn = ui.Button(
                label="Jump to...", style=discord.ButtonStyle.primary, row=1
            )
            jump_btn.callback = self._jump
            self.add_item(jump_btn)

            next_btn = ui.Button(
                emoji="➡️", style=discord.ButtonStyle.secondary,
                row=1, disabled=(self.page >= self.total_pages() - 1)
            )
            next_btn.callback = self._next
            self.add_item(next_btn)

    def _make_open_cb(self, slot_index: int):
        async def callback(interaction: discord.Interaction):
            global_index = self.page * PAGE_SIZE + slot_index
            if global_index >= len(self.fanarts):
                await interaction.response.send_message("Fanart not found.", ephemeral=True)
                return
            detail = StoryFanartDetailView(
                self.fanarts, global_index,
                interaction.user, roster=self, return_page=self.page
            )
            await interaction.response.edit_message(embed=detail.build_embed(), view=detail)
        return callback

    async def _prev(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_story_fanart_list_embed(
                self.fanarts, self.page, self.total_pages(), self.story_title
            ),
            view=self
        )

    async def _next(self, interaction: discord.Interaction):
        self.page = min(self.total_pages() - 1, self.page + 1)
        self._rebuild_ui()
        await interaction.response.edit_message(
            embed=build_story_fanart_list_embed(
                self.fanarts, self.page, self.total_pages(), self.story_title
            ),
            view=self
        )

    async def _jump(self, interaction: discord.Interaction):
        await interaction.response.send_modal(_FanartJumpModal(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.", ephemeral=True, delete_after=5
            )
            return False
        return True