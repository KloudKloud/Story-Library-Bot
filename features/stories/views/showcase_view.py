import discord
from discord import ui
import random

from database import (
    get_story_progress,
    get_user_id,
    get_characters_by_story,
    get_characters_by_discord_user,
    get_showcase_stats,
    get_profile_by_discord_id,
    get_all_showcase_authors,
    get_stories_by_discord_user,
    get_library_reader_score,
    get_reader_badge_count,
    get_author_metal_count
)

from embeds.character_embeds import build_character_card
from utils.text_utils import normalize_inline_text
from ui.base_list_view import BaseListView
from features.characters.views.characters_view import StoryCharactersView
from features.stories.views.clone_library_view import build_story_embed

SHOWCASE_COLORS = [
    discord.Color.blurple(),
    discord.Color.dark_teal(),
    discord.Color.purple(),
    discord.Color.magenta(),
    discord.Color.from_rgb(120, 170, 255),   # soft cobalt
    discord.Color.from_rgb(200, 120, 255),   # violet
    discord.Color.from_rgb(255, 140, 180),   # petal pink
    discord.Color.from_rgb(100, 220, 200),   # seafoam
    discord.Color.from_rgb(255, 180, 80),    # warm amber
    discord.Color.from_rgb(90, 160, 255),    # azure
    discord.Color.from_rgb(230, 90, 170),    # raspberry
    discord.Color.from_rgb(130, 220, 140),   # mint
    discord.Color.from_rgb(180, 130, 255),   # soft grape
    discord.Color.from_rgb(255, 110, 100),   # salmon
    discord.Color.from_rgb(60, 200, 220),    # teal cyan
    discord.Color.from_rgb(255, 210, 100),   # sunflower
    discord.Color.from_rgb(160, 100, 230),   # amethyst
    discord.Color.from_rgb(80, 190, 160),    # jade
]

def build_progress_bar(percent, length=10):
    filled = int((percent / 100) * length)
    empty = length - filled
    return "▰" * filled + "▱" * empty

def character_to_dict(row):

    if isinstance(row, dict):
        return row

    return {
        "id": row["id"],
        "name": row["name"],
        "species": row["species"],
        "description": row.get("description"),
        "image_url": row.get("image_url"),
        "story_id": row.get("story_id")
    }


class ShowcaseView(BaseListView):

    def __init__(
        self,
        stories,
        viewer,
        target_user,
        source="showcase",
        current_character=None,
        from_story_view=False,
        preview_mode=False
    ):


        self.reduced = (source == "fanart")
        self.viewer = viewer
        self.target_user = target_user
        self.source = source
        self.current_character = current_character
        self.from_story_view = from_story_view
        self.preview_mode = preview_mode

        authors = get_all_showcase_authors()
        random.shuffle(authors)

        target_id = target_user.id
        authors = [a for a in authors if a != target_id]

        self.author_order = [target_id] + authors
        self.author_index = 0

        # ⭐ Base class first
        super().__init__(stories, viewer, per_page=5)

        # ---------- SMART BACK LABEL ----------
        if self.source == "charview":
            self.add_item(self.back_to_character)
            
        elif self.source == "library":
            self.back_to_story.label = "⬅️ Back to Story"

        # ⭐ NOW override mode
        self.mode = "bio"

        self.refresh_ui()

    def generate_current_embed(self):

        if self.mode == "bio":
            return self.generate_bio_embed()

        if self.mode == "browse":
            return self.generate_list_embed()

        if self.mode == "story":
            return self.generate_story_embed()

        return self.generate_list_embed()

    def refresh_ui(self):

        if self.preview_mode:

            self.clear_items()
            self.add_item(self.back_to_editor)
            return

        self.clear_items()

        # ================= BIO =================
        if self.mode == "bio":

            if self.reduced:
                self.add_item(self.back_to_fanart)

            elif self.source == "library":
                self.add_item(self.back_to_story)

            elif self.source == "charview":

                if self.from_story_view:
                    self.add_item(self.back_to_story_from_char_story)
                    self.add_item(self.back_to_character_short)
                else:
                    self.add_item(self.view_story_from_bio)
                    self.add_item(self.back_to_character)

            else:
                self.add_item(self.prev_author)
                self.browse_stories.disabled = len(self.items) == 0
                self.add_item(self.browse_stories)
                self.character_cards.disabled = len(self.items) == 0
                self.add_item(self.character_cards)
                self.add_item(self.next_author)

        # ================= STORIES (NEW GALLERY MODE) =================
        elif self.mode == "stories":

            self.prev.row = 0
            self.story_note.row = 0
            self.back_to_bio.row = 0
            self.next.row = 0

            self.add_item(self.prev)
            self.add_item(self.story_note)
            self.add_item(self.back_to_bio)
            self.add_item(self.next)

            # smart disable
            self.prev.disabled = (self.index == 0)
            self.next.disabled = (
                self.index >= len(self.items) - 1
            )

        # ---------- AUTHOR ARROWS ----------
        self.prev_author.disabled = (self.author_index == 0)
        self.next_author.disabled = (
            self.author_index >= len(self.author_order) - 1
        )    

    def generate_list_embed(self):

        # ---------- SUPPORT MEMBER OR DB PROFILE ----------
        if hasattr(self.target_user, "id"):
            # discord.Member
            discord_id = self.target_user.id
            display_name = self.target_user.display_name
        else:
            # database profile dict
            discord_id = self.target_user["discord_id"]
            display_name = self.target_user["username"]

        stats = get_showcase_stats(discord_id)

        embed = discord.Embed(
            title=f"✨ {display_name}'s Showcase",
            color=discord.Color.gold()
        )    

        start = self.page * self.per_page
        chunk = self.items[start:start+self.per_page]

        uid = get_user_id(str(self.viewer.id))

        for i, s in enumerate(chunk, start=1):

            title = s["title"]
            ch = s["chapters"]
            upd = s["updated"]
            words = s["words"] or 0
            summ = s["summary"]
            ao3 = s["ao3"]
            author = s["author"]
            watt = s["wattpad"]
            cover = s["cover"]
            sid = s["id"]

            progress = get_story_progress(uid, sid) or 0
            percent = int((progress/ch)*100) if ch else 0

            preview = (summ[:100]+"...") if summ else "No summary."

            embed.add_field(
                name=f"{i}. 📘 {title} • {percent}%",
                value=(
                    f"📖 {ch} chapters • 📝 {words:,} words\n"
                    f"*{preview}*"
                ),
                inline=False
            )

        embed.set_footer(text="Showcase View")
        return embed
    
    def generate_bio_embed(self):

        stats = get_showcase_stats(self.target_user.id)
        profile = get_profile_by_discord_id(self.target_user.id)

        # Normalize fields to prevent vertical waterfall text
        profile["pronouns"] = normalize_inline_text(profile.get("pronouns"))
        profile["favorite_pokemon"] = normalize_inline_text(profile.get("favorite_pokemon"))
        profile["favorite_fics"] = normalize_inline_text(profile.get("favorite_fics"))
        profile["favorite_authors"] = normalize_inline_text(profile.get("favorite_authors"))
        profile["hobbies"] = normalize_inline_text(profile.get("hobbies"))
        profile["fun_fact"] = normalize_inline_text(profile.get("fun_fact"))
        profile["bio"] = normalize_inline_text(profile.get("bio"))

        reader_score, read, total = get_library_reader_score(self.target_user.id)

        badges = get_reader_badge_count(self.target_user.id)
        metals = get_author_metal_count(self.target_user.id)

        embed = discord.Embed(
            title=f"✨ {self.target_user.display_name}'s Author Profile",
            color=discord.Color.blurple()
        )

        # --------------------------------
        # WRITER STATS
        # --------------------------------

        embed.add_field(
            name="✦ Writer Stats",
            value=(
                f"✦ Stories: {stats['stories']}\n"
                f"✦ Characters: {stats['characters']}\n"
                f"✦ Words Written: {stats['words']:,}\n"
                f"✦ Badges • {badges}\n"
                f"✦ Ribbons • {metals}"
            ),
            inline=False
        )

        # --------------------------------
        # BIO
        # --------------------------------

        bio = profile["bio"] or "This author hasn't written a bio yet."

        embed.add_field(
            name="🪪 Bio",
            value=f"> {bio}",
            inline=False
        )

        # --------------------------------
        # INFO ROW
        # --------------------------------

        embed.add_field(
            name="⚧️ Pronouns",
            value=profile["pronouns"] or "Not set",
            inline=True
        )

        embed.add_field(
            name="🧬 Favorite Pokémon",
            value=profile["favorite_pokemon"] or "Not set",
            inline=True
        )

        embed.add_field(
            name="📘 Favorite Fic",
            value=profile["favorite_fics"] or "None",
            inline=True
        )

        # --------------------------------
        # SECOND ROW
        # --------------------------------

        embed.add_field(
            name="📜 Top Authors",
            value=profile["favorite_authors"] or "None",
            inline=True
        )

        embed.add_field(
            name="🌸 Hobbies",
            value=profile["hobbies"] or "None",
            inline=True
        )

        embed.add_field(
            name="📖 User Score",
            value=f"{reader_score}% ({read}/{total} chapters)",
            inline=True
        )

        # --------------------------------
        # FUN FACT
        # --------------------------------

        # --------------------------------
        # IMAGE
        # --------------------------------

        if profile["image_url"]:
            embed.set_thumbnail(url=profile["image_url"])

        fun_fact = profile["fun_fact"] or "No fun fact set yet!"
        embed.set_footer(text=f"✨ {fun_fact}  ·  Author Showcase")

        return embed  
    
    def generate_detail_embed(self, story):

        title = story["title"]
        ch = story["chapters"]
        upd = story["updated"]
        words = story["words"]
        summ = story["summary"]
        ao3 = story["ao3"]
        author = story["author"]
        watt = story["wattpad"]
        cover = story["cover"]
        sid = story["id"]

        uid = get_user_id(str(self.viewer.id))
        progress = get_story_progress(uid, sid) or 0
        percent = int((progress / ch) * 100) if ch else 0

        embed = discord.Embed(
            title=f"📖 {title}",
            color=discord.Color.dark_gold()
        )

        embed.add_field(
            name="📊 Story Info",
            value=(
                f"👤 **Author:** {author}\n"
                f"📚 **Chapters:** {ch}\n"
                f"📝 **Words:** {words:,}\n"
                f"✨ **Viewer Progress:** {percent}%"
            ),
            inline=False
        )

        embed.add_field(
            name="✨ Summary",
            value=summ or "No summary.",
            inline=False
        )

        links = f"[AO3]({ao3})"
        if watt:
            links += f" | [Wattpad]({watt})"

        embed.add_field(
            name="🔗 Links",
            value=links,
            inline=False
        )

        if cover:
            embed.set_image(url=cover)

        embed.set_footer(text="Showcase Story View")

        return embed
    
    def generate_story_showcase_embed(self):

        story = self.items[self.index]

        # Convert showcase story dict → row-like structure
        story_row = {
            "id": story["id"],
            "title": story["title"],
            "chapter_count": story["chapters"],
            "library_updated": story["updated"],
            "word_count": story["words"],
            "summary": story["summary"],
            "ao3_url": story["ao3"],
            "author": story["author"],
            "cover_url": story["cover"],
            "wattpad_url": story["wattpad"],
            "extra_link_title": None,
            "extra_link_url": None,
            "extra_link2_title": None,
            "extra_link2_url": None,
            "playlist_url": None,
            "rating": None
        }

        return build_story_embed(
            story_row,
            self.viewer
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.", ephemeral=True, delete_after=5
            )
            return False
        return True

    @ui.button(label="📚 Browse Stories", style=discord.ButtonStyle.primary)
    async def browse_stories(self, interaction, button):

        self.mode = "stories"
        self.index = 0
        self.refresh_ui()

        await interaction.response.edit_message(
            embed=self.generate_story_showcase_embed(),
            view=self
        )

    @ui.button(
    label="📖 View Story",
    style=discord.ButtonStyle.primary
    )
    async def view_story_from_bio(self, interaction, button):

        # open story snapshot from character quick view
        from features.stories.views.character_story_view import CharacterStoryView
        from features.characters.views.my_chars_view import MyCharsView

        from_mychar = isinstance(self.parent_view, MyCharsView)

        view = CharacterStoryView(
            self.parent_view,
            self.parent_view.character_id,
            interaction.user,
            from_mychar=from_mychar
        )

        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view
        )

    @ui.button(
        label="🏠 Char Hub",
        style=discord.ButtonStyle.success
    )
    async def back_to_character_short(self, interaction, button):

        self.character_view.rebuild_character()

        await interaction.response.edit_message(
            embed=build_character_card(
                self.character_view.current_character(),
                viewer=self.viewer,
                index=self.character_view.index + 1,
                total=len(self.character_view.characters)
            ),
            view=self.character_view
        )

    @ui.button(label="⬅ Back to Editor", style=discord.ButtonStyle.success)
    async def back_to_editor(self, interaction, button):

        from features.fanart.views.author_builder_view import AuthorBuilderView

        view = AuthorBuilderView(self.viewer)

        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view
        )

        await view.attach_message(await interaction.original_response())

    @ui.button(
        label="📖 View Story",
        style=discord.ButtonStyle.primary
    )
    async def back_to_story_from_char_story(self, interaction, button):

        await interaction.response.edit_message(
            embed=self.story_view.rebuild_story_embed(),
            view=self.story_view
        )

    @ui.button(
        label="⬅️ Return",
        style=discord.ButtonStyle.primary
    )
    async def back_to_fanart(self, interaction, button):

        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )

    @ui.button(label="🧬 All Characters", style=discord.ButtonStyle.primary)
    async def all_characters(self, interaction, button):

        chars = get_characters_by_discord_user(self.target_user.id)

        if not chars:
            await interaction.response.send_message(
                "No characters found.",
                ephemeral=True
            )
            return

        view = StoryCharactersView(
            chars,
            self,
            story_title=None,
            return_mode="bio",
            viewer=self.viewer
        )

        await interaction.response.edit_message(
            embed=build_character_card(
                chars[0],
                viewer=self.viewer,
                index=1,
                total=len(chars)
            ),
            view=view
        )

    @ui.button(label="⬅️", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction, button):

        if self.index > 0:
            self.index -= 1

        self.refresh_ui()

        await interaction.response.edit_message(
            embed=self.generate_story_showcase_embed(),
            view=self
        )


    @ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):

        if self.index < len(self.items) - 1:
            self.index += 1

        self.refresh_ui()

        await interaction.response.edit_message(
            embed=self.generate_story_showcase_embed(),
            view=self
        )


    @ui.button(label="🎬 Extras", style=discord.ButtonStyle.primary)
    async def story_note(self, interaction, button):

        from features.stories.views.story_extras_view import StoryExtrasView

        story = self.items[self.index]

        view = StoryExtrasView(
            story_id=story["id"],
            author_view=self,
            viewer=self.viewer
        )

        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view
        )

    @ui.button(label="⬅️ Return", style=discord.ButtonStyle.success)
    async def back_to_character(self, interaction, button):

        # rebuild character fresh
        self.parent_view.rebuild_character()

        await interaction.response.edit_message(
            embed=build_character_card(
                self.parent_view.current_character(),
                viewer=self.viewer,
                index=self.parent_view.index + 1,
                total=len(self.parent_view.characters)
            ),
            view=self.parent_view
        )

    @ui.button(label="🎨 Fanart Gallery", style=discord.ButtonStyle.primary)
    async def fanart_gallery(self, interaction, button):

        await interaction.response.send_message(
            "🚧 Fanart Gallery coming soon!",
            ephemeral=True
        )

    @ui.button(
        label="⬅️ Back to Story",
        style=discord.ButtonStyle.primary
    )
    async def back_to_story(self, interaction, button):

        # return to previous library view
        await interaction.response.edit_message(
            embed=self.parent_view.generate_detail_embed(
                self.parent_view.current_item
            ),
            view=self.parent_view
        )

    @ui.button(label="⬅️ Back to Bio", style=discord.ButtonStyle.success)
    async def back_to_bio(self, interaction, button):

        self.mode = "bio"
        self.refresh_ui()

        await interaction.response.edit_message(
            embed=self.generate_bio_embed(),
            view=self
        )

    @ui.button(label="🧬 Characters", style=discord.ButtonStyle.primary)
    async def character_cards(self, interaction, button):

        chars = get_characters_by_discord_user(self.target_user.id)

        if not chars:
            await interaction.response.send_message(
                "No characters found.",
                ephemeral=True
            )
            return

        view = StoryCharactersView(
            chars,
            self,
            story_title=None,
            return_mode="bio",
            viewer=self.viewer
        )

        await interaction.response.edit_message(
            embed=build_character_card(
                chars[0],
                viewer=self.viewer,
                index=1,
                total=len(chars)
            ),
            view=view
        )

    @ui.button(label="🧬 Characters", style=discord.ButtonStyle.primary)
    async def characters(self, interaction, button):

        if not self.current_item:
            return

        story_id = self.current_item["id"]
        chars = get_characters_by_story(story_id)

        if not chars:
            await interaction.response.send_message(
                "No characters for this story.",
                ephemeral=True
            )
            return

        view = StoryCharactersView(
            chars,
            self,
            story_title=self.current_item["title"],
            viewer=self.viewer
        )

        await interaction.response.edit_message(
            embed=build_character_card(
                chars[0],
                viewer=self.viewer,
                index=1,
                total=len(chars),
                story_title=self.current_item["title"]
            ),
            view=view
        )

    @ui.button(label="⬅️ Back to Showcase", style=discord.ButtonStyle.secondary)
    async def back(self, interaction, button):

        self.mode = "browse"
        self.current_item = None
        self.refresh_ui()

        await interaction.response.edit_message(
            embed=self.generate_list_embed(),
            view=self
        )

    @ui.button(label="⬅️", style=discord.ButtonStyle.secondary)
    async def prev_author(self, interaction, button):

        if self.author_index > 0:
            self.author_index -= 1

        await self.load_current_author(interaction)


    @ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next_author(self, interaction, button):

        if self.author_index < len(self.author_order) - 1:
            self.author_index += 1

        await self.load_current_author(interaction) 

    async def load_current_author(self, interaction: discord.Interaction):
        """Switch the showcase to the author at the current author_index."""

        target_discord_id = self.author_order[self.author_index]

        # Try to get the member from the guild
        member = interaction.guild.get_member(target_discord_id)

        if member is None:
            try:
                member = await interaction.guild.fetch_member(target_discord_id)
            except Exception:
                member = None

        if member is None:
            # Fall back to a lightweight dict so generate_bio_embed still works
            profile = get_profile_by_discord_id(target_discord_id)
            username = profile.get("username", "Unknown Author") if profile else "Unknown Author"

            class _FakeMember:
                def __init__(self, discord_id, name):
                    self.id = discord_id
                    self.display_name = name
                    self.avatar = None

            member = _FakeMember(target_discord_id, username)

        # Update view state
        self.target_user = member
        self.items = get_stories_by_discord_user(str(target_discord_id))
        self.index = 0
        self.mode = "bio"

        self.refresh_ui()

        await interaction.response.edit_message(
            embed=self.generate_bio_embed(),
            view=self
        )