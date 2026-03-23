import discord
from discord import ui

def _pad_to_ratio(file_bytes: bytes, target_ratio: float) -> bytes:
    """
    Widens the canvas so width/height >= target_ratio, keeping the image
    centred. Small images are upscaled first so the final canvas is at
    least MIN_WIDTH pixels wide — this ensures Discord renders the embed
    image at full width instead of leaving it squished.
    Returns original bytes on any failure.
    """
    try:
        from PIL import Image
        import io as _io

        MIN_WIDTH = 520  # Discord embeds display images at ~400px; 520 gives headroom

        src = Image.open(_io.BytesIO(file_bytes)).convert("RGBA")
        ow, oh = src.size

        # Upscale tiny images so the final result is wide enough for Discord
        canvas_w = max(int(oh * target_ratio), ow)
        if canvas_w < MIN_WIDTH:
            scale = MIN_WIDTH / canvas_w
            src = src.resize((int(ow * scale), int(oh * scale)), Image.LANCZOS)
            ow, oh = src.size

        if ow / oh >= target_ratio:
            # Already wide enough — re-encode as PNG and return
            out = _io.BytesIO()
            src.save(out, format="PNG", optimize=True)
            return out.getvalue()

        canvas_w = int(oh * target_ratio)
        canvas   = Image.new("RGBA", (canvas_w, oh), (0, 0, 0, 0))
        canvas.paste(src, ((canvas_w - ow) // 2, 0), src)

        out = _io.BytesIO()
        canvas.save(out, format="PNG", optimize=True)
        return out.getvalue()

    except Exception:
        return file_bytes  # fall back gracefully

import asyncio
import io
import time
import discord

STORAGE_CHANNEL_ID = 1478560442723864737


class BaseBuilderView(ui.View):

    IDLE_TIMEOUT = 1200  # 20 minutes of inactivity before closing

    def __init__(self, user, timeout=None):
        super().__init__(timeout=None)  # We manage our own idle timeout

        self.user = user
        self.builder_message = None
        self._modal_open = False   # set True before send_modal, False on submit
        self._last_activity = time.monotonic()
        self._timeout_task = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        self._last_activity = time.monotonic()
        return True

    def stop(self):
        if self._timeout_task:
            self._timeout_task.cancel()
            self._timeout_task = None
        super().stop()

    # --------------------------------
    # Register message reference
    # --------------------------------
    async def attach_message(self, message):
        self.builder_message = message
        if self._timeout_task:
            self._timeout_task.cancel()
        self._timeout_task = asyncio.create_task(self._idle_watcher())

    # --------------------------------
    # Idle watcher — pauses while a modal is open
    # --------------------------------
    async def _idle_watcher(self):
        try:
            while True:
                await asyncio.sleep(15)
                if self._modal_open:
                    # Modal is open: keep resetting the idle clock
                    self._last_activity = time.monotonic()
                    continue
                if time.monotonic() - self._last_activity >= self.IDLE_TIMEOUT:
                    await self.on_timeout()
                    super().stop()
                    return
        except asyncio.CancelledError:
            pass

    # --------------------------------
    # Session timeout
    # --------------------------------
    async def on_timeout(self):
        if not self.builder_message:
            return

        self.disable_all_buttons()

        try:
            await self._safe_edit(
                content="🌙 Session closed — use the command again to reopen.",
                embed=None,
                view=None
            )
        except Exception:
            return

        await asyncio.sleep(30)

        try:
            await self.builder_message.delete()
        except Exception:
            pass

    # --------------------------------
    # Safe edit — falls back to channel fetch if the webhook token expired
    # --------------------------------
    async def _safe_edit(self, **kwargs):
        """
        Edit builder_message.  If the interaction webhook token has expired
        (error 50027), fetch the message fresh via the channel and edit that
        instead, then update self.builder_message to the live object.
        """
        if not self.builder_message:
            return
        try:
            await self.builder_message.edit(**kwargs)
        except discord.HTTPException as e:
            if e.code == 50027:
                try:
                    fresh = await self.builder_message.channel.fetch_message(
                        self.builder_message.id
                    )
                    await fresh.edit(**kwargs)
                    self.builder_message = fresh
                except Exception:
                    pass
            else:
                raise

    # --------------------------------
    # Safe message refresh
    # --------------------------------
    async def refresh(self):
        if self.builder_message:
            await self._safe_edit(embed=self.build_embed(), view=self)

    # --------------------------------
    # Progress Bar
    # --------------------------------
    def build_progress_bar(self, percent, length=10):

        filled = int((percent / 100) * length)
        empty = length - filled

        return "✦" * filled + " ·" * empty

    # --------------------------------
    # Preview helper
    # --------------------------------
    def preview_text(self, text, length=120):

        if not text:
            return None

        if len(text) <= length:
            return text

        return text[:length].rstrip() + "..."

    # --------------------------------
    # Disable / Enable buttons
    # --------------------------------
    def disable_all_buttons(self):

        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True

    def enable_all_buttons(self):

        for item in self.children:
            item.disabled = False

    async def handle_image_upload(
        self,
        interaction: discord.Interaction,
        save_callback,
        pad_ratio: float | None = None,
        prompt_prefix: str = "",
        confirmation_message: str = "✨ Image successfully added!"
    ):
        """
        Generic image uploader used by all builders.

        save_callback(image_url)
        prompt_prefix: optional text prepended before the upload instructions.
        """

        class CancelUploadView(discord.ui.View):

            def __init__(self):
                super().__init__(timeout=300)
                self.cancelled = False

            @discord.ui.button(label="❌ Cancel Upload", style=discord.ButtonStyle.danger)
            async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.cancelled = True
                await interaction.response.edit_message(
                    content="❌ Image upload cancelled.",
                    delete_after=3,
                    view=None
                )

        cancel_view = CancelUploadView()

        await interaction.response.send_message(
            prompt_prefix +
            "📸 Upload ONE image in this channel within 5 minutes.\n"
            "Supported formats: PNG, JPG, JPEG, WEBP, GIF.",
            view=cancel_view,
            ephemeral=True
        )

        upload_prompt = await interaction.original_response()

        def check(msg: discord.Message):
            return (
                msg.author.id == interaction.user.id
                and msg.channel.id == interaction.channel.id
                and msg.attachments
            )

        try:
            msg = await interaction.client.wait_for(
                "message",
                timeout=300,
                check=check
            )

            if cancel_view.cancelled:
                return

        except asyncio.TimeoutError:
            await interaction.followup.send(
                "⏰ Image upload timed out.",
                ephemeral=True
            )
            return

        attachment = msg.attachments[0]

        allowed_types = [
            "image/png",
            "image/jpeg",
            "image/webp",
            "image/gif"
        ]

        content_type = (attachment.content_type or "").split(";")[0].strip()
        if content_type not in allowed_types:
            await interaction.followup.send(
                "❌ Only image files are allowed (PNG, JPG, WEBP, GIF).",
                ephemeral=True
            )
            return

        try:
            file_bytes = await attachment.read()
        except Exception as e:
            print(f"❌ Failed to download image: {e}")
            await interaction.followup.send(
                "❌ Failed to download image.",
                ephemeral=True
            )
            return

        storage_channel = interaction.guild.get_channel(STORAGE_CHANNEL_ID)
        if not storage_channel:
            try:
                storage_channel = await interaction.client.fetch_channel(STORAGE_CHANNEL_ID)
            except Exception as e:
                print(f"❌ Could not fetch storage channel {STORAGE_CHANNEL_ID}: {e}")
                await interaction.followup.send(
                    "❌ Storage channel not found.",
                    ephemeral=True
                )
                return

        # Optional: pad image to target aspect ratio before storing
        if pad_ratio is not None:
            file_bytes = _pad_to_ratio(file_bytes, pad_ratio)

        try:
            ext      = attachment.filename.rsplit(".", 1)[-1].lower()
            filename = attachment.filename if pad_ratio is None else f"{attachment.filename.rsplit('.', 1)[0]}_padded.png"

            # Guard against oversized files (Discord limit ~25 MB boosted, 8 MB otherwise)
            size_mb = len(file_bytes) / (1024 * 1024)
            if size_mb > 25:
                print(f"❌ Padded image too large to upload: {size_mb:.1f} MB")
                await interaction.followup.send(
                    "❌ Image is too large after processing. Try a smaller image.",
                    ephemeral=True
                )
                return

            file = discord.File(
                io.BytesIO(file_bytes),
                filename=filename
            )

            storage_msg = await storage_channel.send(file=file)

        except Exception as e:
            print(f"❌ Failed to store image in channel {STORAGE_CHANNEL_ID}: {e}")
            await interaction.followup.send(
                "❌ Failed to store image.",
                ephemeral=True
            )
            return

        permanent_url = storage_msg.attachments[0].url

        # Save result using callback
        await save_callback(permanent_url)

        try:
            await msg.delete()
        except:
            pass

        confirmation = await interaction.followup.send(
            confirmation_message,
            ephemeral=True
        )

        await asyncio.sleep(3)

        try:
            await confirmation.delete()
        except:
            pass

        try:
            await upload_prompt.delete()
        except:
            pass