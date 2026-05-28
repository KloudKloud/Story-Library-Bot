import discord
from discord import ui
from itertools import groupby
from ui import TimeoutMixin


STORIES_PER_PAGE = 6

SLOT_ICONS = ["💫", "⭐"]
EMPTY_SLOT = "○ *Empty slot*"


def build_favs_embed(grouped_stories, page, total_pages, sort_order, total_favs):
    """
    grouped_stories: list of {story_title, story_id, characters: [{name}]}
    Only stories that have at least one fav character are included.
    """

    if sort_order == "az":
        sorted_stories = sorted(grouped_stories, key=lambda s: s["story_title"].lower())
        sort_label = "A → Z"
    else:
        sorted_stories = sorted(grouped_stories, key=lambda s: s["story_title"].lower(), reverse=True)
        sort_label = "Z → A"

    start = page * STORIES_PER_PAGE
    chunk = sorted_stories[start : start + STORIES_PER_PAGE]

    embed = discord.Embed(
        title="✨ Your Favorite Characters ✨",
        description=(
            f"💖 *Your personal Pokédex of beloved characters!*\n"
            f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
            f"📖 Sorted **{sort_label}** • Use the button to toggle order"
        ),
        color=discord.Color.from_rgb(255, 182, 255)
    )

    if not chunk:
        embed.add_field(
            name="🌀 No favorites yet!",
            value="Use the ✦ Favorite button while browsing characters to add some.",
            inline=False
        )
    else:
        for entry in chunk:
            story_title = entry["story_title"]
            chars = entry["characters"]   # up to 2

            slot_lines = []
            for i in range(2):
                if i < len(chars):
                    icon = SLOT_ICONS[i]
                    slot_lines.append(f"{icon} **{chars[i]['name']}**")
                else:
                    slot_lines.append(EMPTY_SLOT)

            embed.add_field(
                name=f"📖 {story_title}",
                value="\n".join(slot_lines),
                inline=True   # two per row
            )

    total_chars = total_favs
    fav_word = "favorite" if total_chars == 1 else "favorites"

    embed.set_footer(
        text=(
            f"Page {page + 1} of {total_pages}  •  "
            f"💫 {total_chars} {fav_word} total  •  "
            f"Gotta fav 'em all~"
        )
    )

    return embed, sorted_stories


class ShowFavsView(TimeoutMixin, ui.View):

    def __init__(self, raw_favs, viewer, filter_story_id=None):
        super().__init__(timeout=300)

        self.viewer = viewer
        self.page = 0
        self.sort_order = "az"   # or "za"

        # Group by story
        story_map = {}
        for fav in raw_favs:
            sid = fav["story_id"]
            if sid not in story_map:
                story_map[sid] = {
                    "story_id":    sid,
                    "story_title": fav["story_title"],
                    "characters":  []
                }
            story_map[sid]["characters"].append({
                "name":         fav["character_name"],
                "character_id": fav["character_id"]
            })

        self.grouped = list(story_map.values())

        # Optional: filter to one story
        if filter_story_id:
            self.grouped = [g for g in self.grouped if g["story_id"] == filter_story_id]

        self.total_favs = len(raw_favs)
        self._update_pagination()
        self._refresh_buttons()

    def _update_pagination(self):
        n = len(self.grouped)
        self.total_pages = max(1, -(-n // STORIES_PER_PAGE))   # ceiling div

    def build_embed(self):
        embed, _ = build_favs_embed(
            self.grouped,
            self.page,
            self.total_pages,
            self.sort_order,
            self.total_favs
        )
        return embed

    def _refresh_buttons(self):
        self.left.disabled  = (self.page == 0)
        self.right.disabled = (self.page >= self.total_pages - 1)
        self.sort_btn.label = "🔤 A→Z" if self.sort_order == "za" else "🔤 Z→A"

    # ── Buttons ────────────────────────────────────

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.", ephemeral=True, delete_after=5
            )
            return False
        return True

    @ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary, row=0)
    async def left(self, interaction, button):
        if self.page > 0:
            self.page -= 1
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @ui.button(label="🔤 Z→A", style=discord.ButtonStyle.primary, row=0)
    async def sort_btn(self, interaction, button):
        self.sort_order = "za" if self.sort_order == "az" else "az"
        self.page = 0
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @ui.button(emoji="➡️", style=discord.ButtonStyle.secondary, row=0)
    async def right(self, interaction, button):
        if self.page < self.total_pages - 1:
            self.page += 1
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)