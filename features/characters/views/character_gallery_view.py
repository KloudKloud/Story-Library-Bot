import discord
from discord import ui

from embeds.character_embeds import build_character_card
from database import get_story_by_character


class CharacterGalleryView(ui.View):

    def __init__(self, characters):

        super().__init__(timeout=300)

        self.characters = characters
        self.index = 0

        self.update_buttons()

    def current(self):
        return self.characters[self.index]

    def update_buttons(self):
        self.prev.disabled = (self.index == 0)
        self.next.disabled = (
            self.index >= len(self.characters)-1
        )

    # ---------- NAV ----------
    @ui.button(label="⬅️", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction, button):

        if self.index > 0:
            self.index -= 1

        self.update_buttons()

        await interaction.response.edit_message(
            embed=build_character_card(
                self.current(),
                index=self.index+1,
                total=len(self.characters)
            ),
            view=self
        )

    @ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):

        if self.index < len(self.characters)-1:
            self.index += 1

        self.update_buttons()

        await interaction.response.edit_message(
            embed=build_character_card(
                self.current(),
                index=self.index+1,
                total=len(self.characters)
            ),
            view=self
        )

    # ---------- STORY BUTTON ----------
    @ui.button(label="📖 Check out Story", style=discord.ButtonStyle.primary)
    async def story(self, interaction, button):

        char = self.current()
        character_id = char[0]

        story = get_story_by_character(character_id)

        if not story:
            await interaction.response.send_message(
                "Story not found.",
                ephemeral=True
            )
            return

        title = story[2]
        ao3 = story[4] if len(story) > 4 else None

        if ao3:
            await interaction.response.send_message(
                f"📚 **{title}**\n{ao3}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"📚 **{title}**",
                ephemeral=True
            )