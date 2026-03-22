import asyncio
import discord


class FanartMusicModal(discord.ui.Modal):

    def __init__(self, editor_view):

        super().__init__(title="The Vibe — Add a Song")

        self.editor_view = editor_view

        if hasattr(editor_view, '_modal_open'):
            editor_view._modal_open = True

        self.music_url = discord.ui.TextInput(
            label="Spotify / YouTube / SoundCloud link",
            placeholder="https://open.spotify.com/track/...",
            max_length=500,
            required=False,
            default=editor_view.fanart.get("music_url") or ""
        )

        self.add_item(self.music_url)

    async def on_submit(self, interaction):

        if hasattr(self.editor_view, '_modal_open'):
            self.editor_view._modal_open = False

        from database import update_fanart_music_url

        update_fanart_music_url(
            self.editor_view.fanart["id"],
            self.music_url.value.strip() or None
        )

        self.editor_view.reload_fanart()

        await interaction.response.send_message(
            "🎵 Song saved!",
            ephemeral=True,
            delete_after=3
        )

        await asyncio.sleep(0.1)

        await self.editor_view.refresh()
        await self.editor_view.refresh_preview()