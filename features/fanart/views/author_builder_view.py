import discord
from discord import ui

from ui.base_builder_view import BaseBuilderView
from database import (
    get_profile_by_discord_id,
    update_profile
)

from features.author.modals.edit_bio_modal import EditBioModal
from features.author.modals.edit_pronouns_modal import EditPronounsModal
from features.author.modals.edit_fav_pokemon_modal import EditFavPokemonModal
from features.author.modals.edit_favorite_fics_modal import EditFavoriteFicsModal
from features.author.modals.edit_favorite_authors_modal import EditFavoriteAuthorsModal
from features.author.modals.edit_hobbies_modal import EditHobbiesModal
from features.author.modals.edit_fun_fact_modal import EditFunFactModal


class AuthorBuilderView(BaseBuilderView):

    def __init__(self, user):
        super().__init__(user)

        self.profile = get_profile_by_discord_id(user.id)
        self.add_item(self.FunDetailsDropdown(self))

    # ---------------------------
    # EMBED
    # ---------------------------
    def build_embed(self):

        embed = discord.Embed(
            title="✨ Author Profile Builder",
            description="Customize your author profile.",
            color=discord.Color.blurple()
        )

        profile = get_profile_by_discord_id(self.user.id)

        percent, filled, total = self.calculate_profile_completion(profile)

        progress_bar = self.build_progress_bar(percent)

        embed.add_field(
            name="✨ Profile Completion",
            value=f"{progress_bar}\n{percent}% ✦ {filled}/{total}",
            inline=False
        )

        bio_preview = self.preview_text(profile["bio"]) or "*No bio set.*"

        embed.add_field(
            name="📝 Bio",
            value=bio_preview,
            inline=False
        )

        embed.add_field(
            name="⚧️ Pronouns",
            value=profile["pronouns"] or "Not set",
            inline=True
        )

        embed.add_field(
            name="⭐ Favorite Pokémon",
            value=profile["favorite_pokemon"] or "Not set",
            inline=True
        )

        embed.add_field(
            name="🖌️ Upload Banner",
            value="Uploaded" if profile["image_url"] else "Not set",
            inline=True
        )
        

        fav_fics_check = "✓" if profile["favorite_fics"] else "•"
        fav_auth_check = "✓" if profile["favorite_authors"] else "•"
        hobbies_check = "✓" if profile["hobbies"] else "•"
        funfact_check = "✓" if profile["fun_fact"] else "•"

        embed.add_field(
            name="🧩 Fun Profile Details",
            value=(
                "Add extra personality to your profile.\n"
                "Use the dropdown below to edit:\n\n"
                f"{fav_fics_check} Favorite Fics\n"
                f"{fav_auth_check} Top Authors\n"
                f"{hobbies_check} Hobbies\n"
                f"{funfact_check} Fun Fact"
            ),
            inline=False
        )

        if profile["image_url"]:
            embed.set_thumbnail(url=profile["image_url"])

        embed.set_footer(
            text="Use the buttons below to edit your profile."
        )

        return embed
    
    def calculate_profile_completion(self, profile):

        fields = [
            profile.get("bio"),
            profile.get("pronouns"),
            profile.get("favorite_pokemon"),
            profile.get("image_url"),

            # future fields (safe if not present)
            profile.get("favorite_fics"),
            profile.get("favorite_authors"),
            profile.get("hobbies"),
            profile.get("fun_fact")
        ]

        filled = sum(1 for f in fields if f)
        total = len(fields)

        percent = int((filled / total) * 100)

        return percent, filled, total

    # ---------------------------
    # BUTTONS
    # ---------------------------

    class FunDetailsDropdown(discord.ui.Select):

        def __init__(self, builder_view):

            self.builder_view = builder_view

            options = [
                discord.SelectOption(
                    label="Favorite Fics",
                    emoji="📚",
                    description="Highlight stories you love"
                ),
                discord.SelectOption(
                    label="Top Authors",
                    emoji="✍️",
                    description="Authors who inspire you"
                ),
                discord.SelectOption(
                    label="Hobbies",
                    emoji="🎮",
                    description="Things you enjoy outside writing"
                ),
                discord.SelectOption(
                    label="Fun Fact",
                    emoji="✨",
                    description="Share something interesting"
                ),
            ]

            super().__init__(
                placeholder="🎭 Edit Fun Profile Details...",
                options=options,
                row=1
            )

        async def callback(self, interaction: discord.Interaction):

            choice = self.values[0]

            if choice == "Favorite Fics":
                self.builder_view._modal_open = True
                await interaction.response.send_modal(
                    EditFavoriteFicsModal(self.builder_view)
                )

            elif choice == "Top Authors":
                self.builder_view._modal_open = True
                await interaction.response.send_modal(
                    EditFavoriteAuthorsModal(self.builder_view)
                )

            elif choice == "Hobbies":
                self.builder_view._modal_open = True
                await interaction.response.send_modal(
                    EditHobbiesModal(self.builder_view)
                )

            elif choice == "Fun Fact":
                self.builder_view._modal_open = True
                await interaction.response.send_modal(
                    EditFunFactModal(self.builder_view)
                )

    @ui.button(label="📝 Bio", style=discord.ButtonStyle.primary, row=0)
    async def edit_bio(self, interaction: discord.Interaction, button: ui.Button):

        self._modal_open = True
        modal = EditBioModal(self)
        await interaction.response.send_modal(modal)


    @ui.button(label="⚧️ Pronouns", style=discord.ButtonStyle.primary, row=0)
    async def edit_pronouns(self, interaction: discord.Interaction, button: ui.Button):

        self._modal_open = True
        modal = EditPronounsModal(self)
        await interaction.response.send_modal(modal)


    @ui.button(label="⭐ Fav Pokémon", style=discord.ButtonStyle.primary, row=0)
    async def edit_pokemon(self, interaction: discord.Interaction, button: ui.Button):

        self._modal_open = True
        modal = EditFavPokemonModal(self)
        await interaction.response.send_modal(modal)


    @ui.button(label="🖌️ Banner", style=discord.ButtonStyle.primary, row=0)
    async def upload_image(self, interaction: discord.Interaction, button: ui.Button):

        async def save_callback(url):
            update_profile(self.user.id, image_url=url)

        await self.handle_image_upload(interaction, save_callback)

        await self.refresh()

    @ui.button(label="👀 Preview", style=discord.ButtonStyle.success, row=0)
    async def preview(self, interaction: discord.Interaction, button: ui.Button):

        from features.stories.views.showcase_view import ShowcaseView
        from database import get_stories_by_discord_user

        stories = get_stories_by_discord_user(self.user.id)

        view = ShowcaseView(
            stories,
            self.user,
            self.user,
            preview_mode=True
        )

        await interaction.response.edit_message(
            embed=view.generate_bio_embed(),
            view=view
        )