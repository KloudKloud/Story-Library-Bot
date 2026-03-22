import asyncio
import discord
from discord import ui


class FanartArtistCreditModal(discord.ui.Modal):

    def __init__(self, editor_view):

        super().__init__(title="Artist Credit")

        self.editor_view = editor_view

        if hasattr(editor_view, '_modal_open'):
            editor_view._modal_open = True

        self.artist_name = discord.ui.TextInput(
            label="Artist name",
            placeholder="e.g. StardustPaws",
            max_length=100,
            required=False,
            default=editor_view.fanart.get("artist_name") or ""
        )

        self.artist_link = discord.ui.TextInput(
            label="Artist link (optional)",
            placeholder="e.g. https://twitter.com/StardustPaws",
            max_length=300,
            required=False,
            default=editor_view.fanart.get("artist_link") or ""
        )

        self.add_item(self.artist_name)
        self.add_item(self.artist_link)

    async def on_submit(self, interaction):

        if hasattr(self.editor_view, '_modal_open'):
            self.editor_view._modal_open = False

        from database import update_fanart_artist_credit

        update_fanart_artist_credit(
            self.editor_view.fanart["id"],
            self.artist_name.value.strip() or None,
            self.artist_link.value.strip() or None
        )

        self.editor_view.reload_fanart()

        await interaction.response.send_message(
            "🎨 Artist credit saved!",
            ephemeral=True,
            delete_after=3
        )

        await asyncio.sleep(0.1)

        await self.editor_view.refresh()
        await self.editor_view.refresh_preview()