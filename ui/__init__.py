import asyncio
import time
import discord

# Set to True before shutdown so interaction_check can notify users gracefully.
_shutting_down = False


class TimeoutMixin:
    """
    Mixin for public ui.View subclasses.
    On timeout, disables all interactive components and edits the message
    so users see a clear "session expired" state instead of a cryptic
    "This interaction failed" error.

    Automatically captures the message reference via interaction_check
    so child views swapped in via edit_message also work.

    Add this mixin BEFORE ui.View in the class definition:
        class MyView(TimeoutMixin, ui.View):
    """

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Capture message reference on every interaction
        if interaction.message:
            self.message = interaction.message
        # Notify users who tap a button during a restart
        if _shutting_down:
            await interaction.response.send_message(
                "✨ The bot is restarting — hang tight, I'll be back in just a moment!",
                ephemeral=True
            )
            return False
        # Delegate to the next class in MRO (the real interaction_check)
        sup = super()
        if hasattr(sup, "interaction_check"):
            return await sup.interaction_check(interaction)
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        msg = getattr(self, "message", None) or getattr(self, "_message", None)
        if not msg:
            return

        try:
            await msg.edit(view=self)
        except Exception:
            pass


class IdleTimeoutMixin:
    """
    Drop-in replacement for a fixed Discord.py timeout on browse/read views.
    Instead of timing out N seconds after creation, this times out after N
    seconds of *inactivity* — any button or select interaction resets the clock.

    Usage:
        class MyView(IdleTimeoutMixin, TimeoutMixin, ui.View):
            IDLE_TIMEOUT = 1200  # optional override; default 20 min

    The mixin manages its own asyncio task and calls the view's on_timeout()
    when the idle window expires.  Pass timeout=None to ui.View.__init__.
    """

    IDLE_TIMEOUT = 1200  # seconds of inactivity before timeout

    def _idle_init(self):
        """Call this at the end of __init__ to start the watcher."""
        self._last_activity = time.monotonic()
        self._idle_task = asyncio.ensure_future(self._idle_watcher())

    async def _idle_watcher(self):
        try:
            while True:
                await asyncio.sleep(15)
                if time.monotonic() - self._last_activity >= self.IDLE_TIMEOUT:
                    await self.on_timeout()
                    self.stop()
                    return
        except asyncio.CancelledError:
            pass

    def stop(self):
        task = getattr(self, "_idle_task", None)
        if task:
            task.cancel()
            self._idle_task = None
        super().stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        self._last_activity = time.monotonic()
        sup = super()
        if hasattr(sup, "interaction_check"):
            return await sup.interaction_check(interaction)
        return True
