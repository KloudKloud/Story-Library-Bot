import asyncio
import discord
from discord import ui


class FanartSceneRefModal(discord.ui.Modal):

    def __init__(self, editor_view):

        super().__init__(title="Add an Excerpt")

        self.editor_view = editor_view

        if hasattr(editor_view, '_modal_open'):
            editor_view._modal_open = True

        self.scene_ref = discord.ui.TextInput(
            label="Paste a quote from this moment",
            style=discord.TextStyle.paragraph,
            placeholder='e.g. "She reached for his hand, and the world went quiet."',
            max_length=300,
            required=False,
            default=editor_view.fanart.get("scene_ref") or ""
        )

        self.add_item(self.scene_ref)

    async def on_submit(self, interaction):

        if hasattr(self.editor_view, '_modal_open'):
            self.editor_view._modal_open = False

        from database import update_fanart_scene_ref

        update_fanart_scene_ref(
            self.editor_view.fanart["id"],
            self.scene_ref.value
        )

        self.editor_view.reload_fanart()

        await interaction.response.send_message(
            "✨ Excerpt saved!",
            ephemeral=True,
            delete_after=3
        )

        await asyncio.sleep(0.1)

        await self.editor_view.refresh()
        await self.editor_view.refresh_preview()