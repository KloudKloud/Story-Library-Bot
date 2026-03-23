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
