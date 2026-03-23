import discord
from discord import ui
import asyncio

from database import (
    get_chapters_full,
    update_chapter_extras,
    get_comment_count_for_chapter,
)
from ui.base_builder_view import BaseBuilderView


# ─────────────────────────────────────────────────
# Author's Note Modal
# ─────────────────────────────────────────────────

class ChapterSummaryModal(discord.ui.Modal, title="Edit Author's Note"):

    summary = discord.ui.TextInput(
        label="Author's note / chapter summary",
        style=discord.TextStyle.paragraph,
        placeholder="Set the mood, tease the chapter, leave a note for readers...",
        max_length=500,
        required=False
    )

    def __init__(self, builder):
        super().__init__()
        self.builder = builder
        ch = builder.current_chapter()
        self.summary.default = ch.get("chapter_summary") or ""

    async def on_submit(self, interaction):
        ch = self.builder.current_chapter()
        update_chapter_extras(ch["id"], summary=self.summary.value)
        self.builder.reload_chapters()
        bonus = await self.builder.check_completion_bonus()
        msg = "✨ Author's note saved!" + (f"\n{bonus}" if bonus else "")
        await interaction.response.send_message(msg, ephemeral=True, delete_after=4)
        await self.builder.refresh()


# ─────────────────────────────────────────────────
# Link Modal — title + URL, saves to slot 1 or 2
# ─────────────────────────────────────────────────

class ChapterLinkModal(discord.ui.Modal, title="Edit Chapter Link"):

    link_title = discord.ui.TextInput(
        label="Link title",
        placeholder="e.g. Wattpad",
        max_length=50,
        required=False
    )

    link_url = discord.ui.TextInput(
        label="Link URL",
        placeholder="https://...",
        max_length=500,
        required=False
    )

    def __init__(self, builder, slot: int, source_message=None):
        super().__init__()
        self.builder        = builder
        self.slot           = slot          # 1 = wattpad_url, 2 = ao3_url
        self.source_message = source_message

        ch = builder.current_chapter()
        if slot == 1:
            self.link_title.default = "Wattpad"
            self.link_url.default   = ch.get("chapter_wattpad_url") or ""
        else:
            self.link_title.default = "AO3"
            self.link_url.default   = ch.get("chapter_ao3_url") or ""

    async def on_submit(self, interaction):
        ch  = self.builder.current_chapter()
        url = self.link_url.value.strip() or None

        if self.slot == 1:
            update_chapter_extras(ch["id"], wattpad_url=url)
        else:
            update_chapter_extras(ch["id"], ao3_url=url)

        self.builder.reload_chapters()
        bonus = await self.builder.check_completion_bonus()
        self.builder._rebuild_ui()

        await self.builder._safe_edit(embed=self.builder.build_embed(), view=self.builder)

        msg = "✅ Link saved!" + (f"\n{bonus}" if bonus else "")
        await interaction.response.send_message(msg, ephemeral=True, delete_after=3)

        if self.source_message:
            try:
                await self.source_message.delete()
            except Exception:
                pass


# ─────────────────────────────────────────────────
# Links picker view — shown ephemerally on Link click
# ─────────────────────────────────────────────────

class ChapterLinksView(ui.View):

    def __init__(self, builder):
        super().__init__(timeout=120)
        self.builder = builder

    @ui.button(label="Edit Link 1", style=discord.ButtonStyle.primary)
    async def edit_link1(self, interaction, button):
        await interaction.response.send_modal(
            ChapterLinkModal(self.builder, 1, interaction.message)
        )

    @ui.button(label="Edit Link 2", style=discord.ButtonStyle.primary)
    async def edit_link2(self, interaction, button):
        await interaction.response.send_modal(
            ChapterLinkModal(self.builder, 2, interaction.message)
        )


# ─────────────────────────────────────────────────
# Progress bar — sparkly style
# ─────────────────────────────────────────────────

SPARKS = ["✦", "✧", "⋆"]

def build_sparkle_bar(done: int, total: int) -> str:
    """
    Returns a clean sparkle progress bar.
    Filled segments: ✦  Empty segments: ·
    A glowing ✨ caps the filled section when partially done.
    """
    length = total  # one segment per field
    if done == 0:
        return "· " * length
    if done >= total:
        return "✦ " * length + " ✨"
    bar = "✦ " * done + "✨ " + "· " * (total - done)
    return bar.rstrip()


# ─────────────────────────────────────────────────
# Chapter builder embed
# ─────────────────────────────────────────────────

def build_chapter_builder_embed(chapter, story_title, index, total, cover_url=None):
    num          = chapter.get("chapter_number", index)
    title        = chapter.get("chapter_title") or f"Chapter {num}"
    summary      = chapter.get("chapter_summary")
    image        = chapter.get("chapter_image_url")
    wattpad_url  = chapter.get("chapter_wattpad_url")
    ao3_url      = chapter.get("chapter_ao3_url")
    auto_ao3_url = chapter.get("chapter_url")
    comments     = get_comment_count_for_chapter(chapter["id"])

    embed = discord.Embed(
        title=f"🛠️  Chapter Builder  ·  Ch. {num}",
        color=discord.Color.dark_teal()
    )
    embed.description = f"-# 📚 {story_title}  ·  {index} of {total} chapters"

    # ── Sparkle progress bar ──────────────────────
    fields_set = [summary, image, wattpad_url or ao3_url]
    done       = sum(1 for f in fields_set if f)
    bar        = build_sparkle_bar(done, 3)

    embed.add_field(
        name="✨  Chapter Progress",
        value=(
            f"{bar}\n"
            f"-# {done}/3 fields complete"
            + (f"  ·  💬 {comments} comment{'s' if comments != 1 else ''}" if comments else "")
        ),
        inline=False
    )

    # ── Chapter title ─────────────────────────────
    embed.add_field(name="📖  Title", value=f"**{title}**", inline=False)

    # ── Author's note ─────────────────────────────
    embed.add_field(
        name="✏️  Summary" + ("  ✔" if summary else "  ✦"),
        value=(
                "\n\n".join(f"> {line}" for line in summary.splitlines() if line.strip())
                
              ) if summary else "-# *Not set — add a note or teaser for readers*",
        inline=False
    )

    # ── Links (inline pair) ───────────────────────
    link1_val = f"[Wattpad]({wattpad_url})" if wattpad_url else "-# *Not set*"
    embed.add_field(
        name="🔗  Link 1" + ("  ✔" if wattpad_url else "  ✦"),
        value=link1_val,
        inline=True
    )

    if ao3_url:
        link2_val = f"[AO3 (direct)]({ao3_url})  ✔"
    elif auto_ao3_url:
        link2_val = f"[AO3 (auto)]({auto_ao3_url})\n-# *Override with a direct link*"
    else:
        link2_val = "-# *Not set*"

    embed.add_field(
        name="🔗  Link 2" + ("  ✔" if ao3_url else ""),
        value=link2_val,
        inline=True
    )

    # ── Reference image ───────────────────────────
    embed.add_field(
        name="🖼️  Reference Image" + ("  ✔" if image else "  ✦"),
        value="-# *Click* ***🖼️ Image*** *below to upload one*"
              if not image else "-# *Image set — click* ***🖼️ Image*** *to replace*",
        inline=False
    )

    if image and image.startswith("http"):
        embed.set_image(url=image)

    if cover_url and cover_url.startswith("http"):
        embed.set_thumbnail(url=cover_url)

    embed.set_footer(text="Use the buttons below to edit each field")
    return embed


# ─────────────────────────────────────────────────
# Chapter builder view
# ─────────────────────────────────────────────────

class ChapterBuilderView(BaseBuilderView):

    def __init__(self, story_id, story_title, author, message=None, cover_url=None):
        super().__init__(author)
        self.story_id        = story_id
        self.story_title     = story_title
        self.cover_url       = cover_url
        self.index           = 0
        self.chapters        = get_chapters_full(story_id)
        self.builder_message = message
        self._rebuild_ui()

    def current_chapter(self):
        return self.chapters[self.index]

    def reload_chapters(self):
        self.chapters = get_chapters_full(self.story_id)

    def build_embed(self):
        return build_chapter_builder_embed(
            self.current_chapter(), self.story_title,
            index=self.index + 1,
            total=len(self.chapters),
            cover_url=self.cover_url
        )

    async def refresh(self):
        self._rebuild_ui()
        await self._safe_edit(embed=self.build_embed(), view=self)

    async def check_completion_bonus(self):
        from database import grant_chapter_build_bonus, get_user_id as _gid
        ch       = self.current_chapter()
        fresh    = get_chapters_full(self.story_id)
        ch_fresh = next((c for c in fresh if c["id"] == ch["id"]), ch)

        filled = sum(1 for f in [
            ch_fresh.get("chapter_summary"),
            ch_fresh.get("chapter_image_url"),
            ch_fresh.get("chapter_wattpad_url") or ch_fresh.get("chapter_ao3_url")
        ] if f)

        if filled < 3:
            return ""
        uid = _gid(str(self.user.id))
        if not uid:
            return ""
        granted, new_bal = grant_chapter_build_bonus(uid, ch["id"])
        if granted:
            return f"-# 💎 +10 crystals — chapter fully built!  ·  {new_bal:,} total"
        return ""

    def _rebuild_ui(self):
        self.clear_items()
        total = len(self.chapters)

        # ── Row 0: ⬅️  Ch. X/Y  ➡️ ──────────────────
        prev = ui.Button(emoji="⬅️", style=discord.ButtonStyle.secondary,
                         row=0, disabled=self.index == 0)
        prev.callback = self._prev
        self.add_item(prev)

        counter = ui.Button(
            label=f"Ch. {self.index + 1} / {total}",
            style=discord.ButtonStyle.success,
            disabled=True,
            row=0
        )
        self.add_item(counter)

        nxt = ui.Button(emoji="➡️", style=discord.ButtonStyle.secondary,
                        row=0, disabled=self.index >= total - 1)
        nxt.callback = self._next
        self.add_item(nxt)

        # ── Row 1: ✏️ Note  🔗 Link  🖼️ Image ─────────
        note_btn = ui.Button(label="✏️ Summary",
                              style=discord.ButtonStyle.primary, row=1)
        note_btn.callback = self._edit_note
        self.add_item(note_btn)

        link_btn = ui.Button(label="🔗 Link",
                              style=discord.ButtonStyle.primary, row=1)
        link_btn.callback = self._edit_links
        self.add_item(link_btn)

        img_btn = ui.Button(label="🖼️ Image",
                             style=discord.ButtonStyle.primary, row=1)
        img_btn.callback = self._edit_image
        self.add_item(img_btn)

    # ── Navigation ───────────────────────────────

    async def _prev(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Not your builder!", ephemeral=True)
            return
        self.index = max(0, self.index - 1)
        self.reload_chapters()
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Not your builder!", ephemeral=True)
            return
        self.index = min(len(self.chapters) - 1, self.index + 1)
        self.reload_chapters()
        self._rebuild_ui()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    # ── Edit callbacks ───────────────────────────

    async def _edit_note(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Not your builder!", ephemeral=True)
            return
        await interaction.response.send_modal(ChapterSummaryModal(self))

    async def _edit_links(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Not your builder!", ephemeral=True)
            return

        ch = self.current_chapter()
        link1 = ch.get("chapter_wattpad_url")
        link2 = ch.get("chapter_ao3_url")

        embed = discord.Embed(
            title="🔗  Chapter Links",
            description="Add or edit up to two links for this chapter.",
            color=discord.Color.dark_teal()
        )
        embed.add_field(name="Link 1", value=link1 or "Not set", inline=True)
        embed.add_field(name="Link 2", value=link2 or "Not set", inline=True)

        await interaction.response.send_message(
            embed=embed,
            view=ChapterLinksView(self),
            ephemeral=True,
            delete_after=10
        )

    async def _edit_image(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Not your builder!", ephemeral=True)
            return

        async def save_image(url):
            ch = self.current_chapter()
            update_chapter_extras(ch["id"], image_url=url)
            self.reload_chapters()
            bonus = await self.check_completion_bonus()
            if bonus:
                try:
                    await interaction.followup.send(bonus, ephemeral=True, delete_after=5)
                except Exception:
                    pass
            await self.refresh()

        await self.handle_image_upload(interaction, save_image)