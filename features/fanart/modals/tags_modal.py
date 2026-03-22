import asyncio
import discord
from discord import ui

from database import update_fanart_tags

from utils.tag_parser import normalize_tags

class FanartTagsModal(discord.ui.Modal):

    def __init__(self, editor_view):

        super().__init__(title="Vibe Tags")

        self.editor_view = editor_view

        self.tags = discord.ui.TextInput(
            label="Vibe Tags (comma separated)",
            placeholder="soft, rain, enemies-to-lovers, crying-in-the-car",
            max_length=300,
            default=editor_view.fanart.get("tags") or ""
        )

        self.add_item(self.tags)

    async def on_submit(self, interaction):

        clean_tags = normalize_tags(self.tags.value)

        update_fanart_tags(
            self.editor_view.fanart["id"],
            clean_tags
        )

        self.editor_view.reload_fanart()

        await interaction.response.send_message(
            "✨ Vibe tags updated!",
            ephemeral=True
        )

        msg = await interaction.original_response()
        await asyncio.sleep(3)
        await msg.delete()

        await self.editor_view.refresh()
        await self.editor_view.refresh_preview()