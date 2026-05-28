import discord
from discord import ui

from embeds.fanart_embeds import build_fanart_embed

from database import (
    get_fanart_characters,
    get_fanart_ships,
    get_story_by_id,
    get_discord_id_by_story,
    get_stories_by_discord_user
)
from embeds.character_embeds import build_character_card
from features.fanart.views.fanart_character_view import FanartCharacterView
from features.stories.views.showcase_view import ShowcaseView
from features.fanart.views.fanart_story_view import FanartStoryView
from ui import TimeoutMixin


# =====================================================
# REDUCED STORY VIEW
# =====================================================

def build_reduced_story_embed(story):

    (
        sid,
        user_id,
        title,
        chapter_count,
        word_count,
        summary,
        last_updated,
        ao3_url
    ) = story

    embed = discord.Embed(
        title=f"📖 {title}",
        color=discord.Color.dark_teal()
    )

    embed.add_field(
        name="📊 Story Info",
        value=(
            f"📚 Chapters: {chapter_count}\n"
            f"📝 Words: {word_count:,}\n"
            f"📅 Updated: {last_updated}"
        ),
        inline=False
    )

    embed.add_field(
        name="✨ Summary",
        value=summary or "No summary.",
        inline=False
    )

    embed.add_field(
        name="🔗 Link",
        value=f"[AO3]({ao3_url})",
        inline=False
    )

    embed.set_footer(text="Fanart → Story View")

    return embed


# =====================================================
# FANART GALLERY VIEW
# =====================================================

class FanartGalleryView(TimeoutMixin, ui.View):

    def __init__(self, fanart, user, reduced=False, draft=False, minimal=False, return_label=None):

        super().__init__(timeout=300)

        self.items = fanart
        self.index = 0

        self.viewer = user
        self.reduced = reduced
        self.draft = draft
        self.minimal = minimal
        self.return_label = return_label  # overrides the back button label in minimal mode

        self.parent_view = None

        self.build_ui()

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

    # =====================================================
    # CURRENT ITEM
    # =====================================================

    def current_item(self):
        return self.items[self.index]
    
    def update_navigation(self):

        total = len(self.items)

        self.left.disabled = (self.index == 0)
        self.right.disabled = (self.index >= total - 1)

    # =====================================================
    # EMBED
    # =====================================================

    def build_embed(self):

        item = self.current_item()
        fanart_id = item["id"]

        chars = get_fanart_characters(fanart_id)
        ships = get_fanart_ships(fanart_id)

        embed = build_fanart_embed(
            item,
            index=self.index + 1,
            total=len(self.items),
            characters=chars,
            ships=ships
        )

        if self.draft:
            embed.color = discord.Color.from_rgb(180, 120, 255)
            embed.title = f"🧪 PREVIEW • {embed.title}"
            embed.set_footer(
                text="🧪 Draft Preview Mode • Not live yet"
            )

        return embed

    # =====================================================
    # UI BUILDER
    # =====================================================

    def build_ui(self):

        self.clear_items()

        # ------------------------------------------------
# MINIMAL MODE (character fanart slideshow)
# ------------------------------------------------

        if self.minimal:

            # LEFT
            left = ui.Button(
                emoji="⬅️",
                style=discord.ButtonStyle.secondary,
                row=0
            )

            if self.index == 0:
                left.disabled = True

            async def left_cb(interaction):

                if self.index > 0:
                    self.index -= 1

                self.build_ui()

                await interaction.response.edit_message(
                    embed=self.build_embed(),
                    view=self
                )

            left.callback = left_cb
            self.add_item(left)

            # RETURN TO PARENT HUB
            back = ui.Button(
                label=self.return_label or "🧬 Return to Character",
                style=discord.ButtonStyle.primary,
                row=0,
                custom_id="fanart_return_character"
            )

            async def back_cb(interaction):

                if not self.parent_view:
                    await interaction.response.send_message(
                        "No parent view found.",
                        ephemeral=True
                    )
                    return

                view = self.parent_view

                # Library path: parent_view is a LibraryView — go back to story detail
                if hasattr(view, "current_item") and hasattr(view, "generate_detail_embed") and not hasattr(view, "current_character"):
                    view.mode = "story"
                    view.refresh_ui()
                    await interaction.response.edit_message(
                        embed=view.generate_detail_embed(view.current_item),
                        view=view
                    )
                    return

                # Character path: parent_view has current_character
                await interaction.response.edit_message(
                    embed=build_character_card(
                        view.current_character(),
                        index=view.index + 1,
                        total=len(view.characters)
                    ),
                    view=view
                )

            back.callback = back_cb
            self.add_item(back)

            # RIGHT
            right = ui.Button(
                emoji="➡️",
                style=discord.ButtonStyle.secondary,
                row=0,
                custom_id="fanart_right"
            )

            if self.index >= len(self.items) - 1:
                right.disabled = True

            async def right_cb(interaction):

                if self.index < len(self.items) - 1:
                    self.index += 1

                self.build_ui()

                await interaction.response.edit_message(
                    embed=self.build_embed(),
                    view=self
                )

            right.callback = right_cb
            self.add_item(right)

            return

        # ------------------------------------------------
    # PREVIEW MODE (used by fanart builder)
    # ------------------------------------------------

        if self.reduced:

            back = ui.Button(
                label="🛠️ Return to Editor",
                style=discord.ButtonStyle.primary,
                row=0
            )

            async def back_cb(interaction):

                await interaction.response.edit_message(
                    embed=self.parent_view.build_embed(),
                    view=self.parent_view
                )

            back.callback = back_cb

            self.add_item(back)

            return

        item = self.current_item()
        fanart_id = item["id"]

        chars = get_fanart_characters(fanart_id)
        story_id = item.get("story_id")

        # -----------------------
        # LEFT ARROW
        # -----------------------

        left = ui.Button(
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=0,
            custom_id = "fanart_left"
        )

        if self.index == 0:
            left.disabled = True

        async def left_cb(interaction):

            if self.index > 0:
                self.index -= 1

            self.build_ui()

            await interaction.response.edit_message(
                embed=self.build_embed(),
                view=self
            )

        left.callback = left_cb

        self.add_item(left)

        # -----------------------
        # VIEW CHARS
        # -----------------------

        chars_btn = ui.Button(
            label="🎭 Characters",
            style=discord.ButtonStyle.primary,
            row=0
        )

        if not chars:
            chars_btn.disabled = True

        async def chars_cb(interaction):

            view = FanartCharacterView(
                characters=chars,
                parent_view=self,
                viewer=self.viewer
            )

            await interaction.response.edit_message(
                embed=view.build_embed(),
                view=view
            )

        chars_btn.callback = chars_cb

        self.add_item(chars_btn)

        # -----------------------
        # VIEW STORY
        # -----------------------

        story_btn = ui.Button(
            label="📚 Story",
            style=discord.ButtonStyle.primary,
            row=0
        )

        if not story_id:
            story_btn.disabled = True

        async def story_cb(interaction: discord.Interaction):

            fanart = self.items[self.index]

            story_id = fanart["story_id"]

            if not story_id:

                await interaction.response.send_message(
                    "This fanart is not linked to a story.",
                    ephemeral=True
                )
                return

            from features.fanart.views.fanart_story_view import FanartStoryView

            view = FanartStoryView(
                story_id=story_id,
                user=interaction.user,
                parent_view=self
            )

            await interaction.response.edit_message(
                embed=view.build_embed(),
                view=view
            )

        story_btn.callback = story_cb

        self.add_item(story_btn)

        # -----------------------
        # VIEW AUTHOR
        # -----------------------

        author_btn = ui.Button(
            label="👤 Author",
            style=discord.ButtonStyle.primary,
            row=0
        )

        if not story_id:
            author_btn.disabled = True

        async def author_cb(interaction):

            discord_id = get_discord_id_by_story(story_id)

            if not discord_id:

                await interaction.response.send_message(
                    "Author not found.",
                    ephemeral=True
                )
                return

            target_user = interaction.guild.get_member(int(discord_id))

            if not target_user:
                target_user = await interaction.guild.fetch_member(int(discord_id))

            stories = get_stories_by_discord_user(discord_id)

            view = ShowcaseView(
                stories,
                interaction.user,
                target_user,
                source="fanart"
            )

            view.parent_view = self

            await interaction.response.edit_message(
                embed=view.generate_bio_embed(),
                view=view
            )

        author_btn.callback = author_cb

        self.add_item(author_btn)

        # -----------------------
        # RIGHT ARROW
        # -----------------------

        right = ui.Button(
            emoji="➡️",
            style=discord.ButtonStyle.secondary,
            row=0
        )

        if self.index >= len(self.items) - 1:
            right.disabled = True

        async def right_cb(interaction):

            if self.index < len(self.items) - 1:
                self.index += 1

            self.build_ui()

            await interaction.response.edit_message(
                embed=self.build_embed(),
                view=self
            )

        right.callback = right_cb

        self.add_item(right)

        # -----------------------
        # EXPLORE MORE FANART
        # -----------------------

        explore_options = []

        # Character exploration
        if chars:

            for c in chars[:3]:

                explore_options.append(
                    discord.SelectOption(
                        label=f"See more {c['name']} art",
                        emoji="🧬",
                        value=f"char:{c['name']}"
                    )
                )

            # show remaining count
            remaining = len(chars) - 3

            if remaining > 0:

                explore_options.append(
                    discord.SelectOption(
                        label=f"+{remaining} more characters...",
                        emoji="➕",
                        value="extra_chars",
                        description="Additional characters tagged in this artwork",
                        disabled=True
                    )
                )

        # Ship exploration
        ships = get_fanart_ships(fanart_id)

        for s in ships:

            explore_options.append(
                discord.SelectOption(
                    label=f"See more {s['name']} art",
                    emoji="💞",
                    value=f"ship:{s['name']}"
                )
            )

        # Story exploration
        if story_id:

            story_title = item.get("story_title") or "this story"

            explore_options.append(
                discord.SelectOption(
                    label=f"See more from {story_title}",
                    emoji="📚",
                    value=f"story:{story_id}"
                )
            )

            explore_options.append(
                discord.SelectOption(
                    label=f"Random art from {story_title}",
                    emoji="🎲",
                    value=f"story_random:{story_id}"
                )
            )

        # Always allow explore menu
        # Ensure dropdown always exists
        if not explore_options:

            explore_options.append(
                discord.SelectOption(
                    label="No related fanart available",
                    value="none",
                    emoji="🌙"
                )
            )

        explore = ui.Select(
            placeholder="✨ Explore More Fanart...",
            options=explore_options[:25],
            row=1
        )

        async def explore_cb(interaction):

            value = explore.values[0]

            if value == "none":
                await interaction.response.send_message(
                    "This artwork has no related fanart yet.",
                    ephemeral=True
                )
                return

            from database import search_fanart, get_fanart_by_story

            if value.startswith("char:"):

                char = value.split(":",1)[1]
                results = search_fanart(character=char)

            elif value.startswith("ship:"):

                ship = value.split(":",1)[1]
                results = search_fanart(ship=ship)

            elif value.startswith("story:"):

                sid = int(value.split(":",1)[1])
                results = get_fanart_by_story(sid)

            elif value.startswith("story_random:"):

                sid = int(value.split(":",1)[1])

                import random

                results = get_fanart_by_story(sid)

                if results:
                    random.shuffle(results)

            else:
                results = []

            if not results:

                await interaction.response.send_message(
                    "No fanart found.",
                    ephemeral=True
                )
                return

            new_view = FanartGalleryView(
                results,
                interaction.user
            )

            new_view.parent_view = self.parent_view

            await interaction.response.edit_message(
                embed=new_view.build_embed(),
                view=new_view
            )

        explore.callback = explore_cb
        self.add_item(explore)

        # -----------------------
        # BACK TO EDITOR
        # -----------------------

        if self.reduced and self.parent_view:

            back = ui.Button(
                label="⬅ Back to Editor",
                style=discord.ButtonStyle.secondary,
                row=2
            )

            async def back_cb(interaction):

                await interaction.response.edit_message(
                    embed=self.parent_view.build_embed(),
                    view=self.parent_view
                )

            back.callback = back_cb

            self.add_item(back)

        # ------------------------------------------------
        # BACK TO LIBRARY (when opened from library)
        # ------------------------------------------------

        if self.parent_view and not self.minimal and not self.reduced:

            back_btn = ui.Button(
                label="📚 Library",
                style=discord.ButtonStyle.success,
                row=2
            )

            async def back_cb(interaction):

                view = self.parent_view

                view.mode = "story"
                view.refresh_ui()

                await interaction.response.edit_message(
                    embed=view.generate_detail_embed(view.current_item),
                    view=view
                )

            back_btn.callback = back_cb

            self.add_item(back_btn)