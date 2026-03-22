import discord
from discord import ui
from ui import TimeoutMixin


class BaseListView(TimeoutMixin, ui.View):

    def __init__(self, items, user, per_page=7):
        super().__init__(timeout=300)

        self.items = items
        self.user = user
        self.page = 0
        self.per_page = per_page
        self.total_pages = max(1, ((len(items)-1)//per_page)+1)
        self.current_item = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.message:
            self.message = interaction.message
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    # ---------- REQUIRED OVERRIDES ----------
    def generate_list_embed(self):
        raise NotImplementedError

    def generate_detail_embed(self, item):
        raise NotImplementedError

    # ---------- OPTIONAL HOOKS ----------
    def refresh_items(self):
        """
        Optional override.
        Called automatically before renders.
        """
        pass

    def on_item_selected(self, item):
        """
        Optional override.
        Runs when dropdown selects something.
        """
        pass

    # ---------- CORE UI ----------
    def refresh_ui(self):
        self.clear_items()

        self.add_item(self.prev)
        self.add_item(self.next)
        self.add_item(self.ItemSelect(self))

        # ⭐ allow child views to inject buttons
        self.add_extra_items()

    # ---------- BUTTONS ----------
    @ui.button(label="⬅️", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction, button):

        # ⭐ return to browse mode
        self.mode = "browse"
        self.current_item = None

        # Update page and items FIRST so the dropdown is built with correct data
        if self.page > 0:
            self.page -= 1
        self.refresh_items()
        self.refresh_ui()

        await interaction.response.edit_message(
            embed=self.generate_list_embed(),
            view=self
        )

    @ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):

        # ⭐ return to browse mode
        self.mode = "browse"
        self.current_item = None

        # Update page and items FIRST so the dropdown is built with correct data
        if self.page < self.total_pages - 1:
            self.page += 1
        self.refresh_items()
        self.refresh_ui()

        await interaction.response.edit_message(
            embed=self.generate_list_embed(),
            view=self
        )

    def add_extra_items(self):
        """
        Optional override.
        Child views can add buttons here.
        """
        pass
    # ---------- SELECT ----------
    class ItemSelect(ui.Select):

        def __init__(self, view_ref):
            self.view_ref = view_ref

            start = view_ref.page * view_ref.per_page
            chunk = view_ref.items[start:start+view_ref.per_page]

            options = [
                discord.SelectOption(
                    label=str(i)[:100],
                    value=str(n)
                )
                for n, i in enumerate(chunk)
            ]

            super().__init__(
                placeholder="Select item...",
                options=options
            )

        async def callback(self, interaction):

            start = self.view_ref.page * self.view_ref.per_page
            item = self.view_ref.items[start + int(self.values[0])]

            self.view_ref.current_item = item
            self.view_ref.on_item_selected(item)

            await interaction.response.edit_message(
                embed=self.view_ref.generate_detail_embed(item),
                view=self.view_ref
            )