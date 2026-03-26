import discord
from discord import ui
from bs4 import BeautifulSoup

from database import (
    get_chapters_full,
    get_story_by_id,
    update_chapter_extras,
    get_comment_count_for_chapter,
)
from ui.base_builder_view import BaseBuilderView


def _format_blockquote(text: str) -> str:
    from bs4 import BeautifulSoup
    cleaned = BeautifulSoup(text, "html.parser").get_text("\n", strip=True)
    lines = cleaned.split("\n")
    return "\n".join(f"> {line}" if line.strip() else "> \u200b" for line in lines)


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
# Go-to-chapter Modal
# ─────────────────────────────────────────────────

class GoToChapterModal(discord.ui.Modal, title="Go to Chapter"):

    def __init__(self, builder):
        super().__init__()
        self.builder = builder
        total = len(builder.chapters)
        self.add_item(discord.ui.TextInput(
            label=f"Chapter number (1–{total})",
            placeholder=f"Enter a number between 1 and {total}",
            max_length=5,
            required=True,
        ))

    async def on_submit(self, interaction):
        raw = self.children[0].value.strip()
        total = len(self.builder.chapters)
        try:
            n = int(raw)
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid number.", ephemeral=True, delete_after=4
            )
            return
        if n < 1 or n > total:
            await interaction.response.send_message(
                f"❌ Chapter must be between 1 and {total}.", ephemeral=True, delete_after=4
            )
            return
        self.builder.index = n - 1
        self.builder.reload_chapters()
        self.builder._rebuild_ui()
        await interaction.response.edit_message(
            embed=self.builder.build_embed(), view=self.builder
        )


# ─────────────────────────────────────────────────
# Progress bar — sparkly style
# ─────────────────────────────────────────────────

def build_sparkle_bar(done: int, total: int) -> str:
    if done == 0:
        return "· " * total
    if done >= total:
        return "✦ " * total + " ✨"
    return ("✦ " * done + "✨ " + "· " * (total - done)).rstrip()


# ─────────────────────────────────────────────────
# Chapter builder embed
# ─────────────────────────────────────────────────

def build_chapter_builder_embed(chapter, story_title, index, total, cover_url=None, has_ao3=False):
    num     = chapter.get("chapter_number", index)
    title   = chapter.get("chapter_title") or f"Chapter {num}"
    summary = chapter.get("chapter_summary")
    image   = chapter.get("chapter_image_url")
    comments = get_comment_count_for_chapter(chapter["id"])

    embed = discord.Embed(
        title=f"🛠️  Chapter Builder  ·  Ch. {num}",
        color=discord.Color.dark_teal()
    )
    embed.description = f"-# 📚 {story_title}  ·  {index} of {total} chapters"

    # Progress bar — 2 fields: summary + image
    # AO3 stories auto-count summary as done
    summary_done = bool(summary) or has_ao3
    image_done   = bool(image)
    done = sum([summary_done, image_done])
    bar  = build_sparkle_bar(done, 2)

    embed.add_field(
        name="✨  Chapter Progress",
        value=(
            f"{bar}\n"
            f"-# {done}/2 fields complete"
            + (f"  ·  💬 {comments} comment{'s' if comments != 1 else ''}" if comments else "")
        ),
        inline=False
    )

    # ── Chapter title ─────────────────────────────
    embed.add_field(name="📖  Title", value=f"**{title}**", inline=False)

    # ── Author's note ─────────────────────────────
    embed.add_field(
        name="✏️  Summary" + ("  ✔" if summary else ("  ✔" if has_ao3 else "  ✦")),
        value=(
            _format_blockquote(summary)
        ) if summary else (
            "-# *Auto-filled from AO3 — add a personal note to override*"
            if has_ao3 else
            "-# *Not set — add a note or teaser for readers*"
        ),
        inline=False
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

    def __init__(self, story_id, story_title, author, message=None, cover_url=None, parent_view=None):
        super().__init__(author)
        self.story_id        = story_id
        self.story_title     = story_title
        self.cover_url       = cover_url
        self.index           = 0
        self.chapters        = get_chapters_full(story_id)
        self.builder_message = message
        self.parent_view     = parent_view

        # Determine AO3 availability (main platform or mirror)
        story = get_story_by_id(story_id)
        if story:
            _platform = story["platform"] or "ao3"
            self.has_ao3 = (_platform == "ao3") or bool(story["ao3_url"])
        else:
            self.has_ao3 = False

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
            cover_url=self.cover_url,
            has_ao3=self.has_ao3,
        )

    async def refresh(self):
        self._rebuild_ui()
        await self._safe_edit(embed=self.build_embed(), view=self)

    async def check_completion_bonus(self):
        from database import grant_chapter_build_bonus, get_user_id as _gid
        ch       = self.current_chapter()
        fresh    = get_chapters_full(self.story_id)
        ch_fresh = next((c for c in fresh if c["id"] == ch["id"]), ch)

        summary_done = bool(ch_fresh.get("chapter_summary")) or self.has_ao3
        image_done   = bool(ch_fresh.get("chapter_image_url"))

        if not (summary_done and image_done):
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

        # ── Row 0: ⬅️  Ch. X/Y (clickable)  ➡️ ──────
        prev = ui.Button(emoji="⬅️", style=discord.ButtonStyle.secondary,
                         row=0, disabled=self.index == 0)
        prev.callback = self._prev
        self.add_item(prev)

        counter = ui.Button(
            label=f"Ch. {self.index + 1} / {total}",
            style=discord.ButtonStyle.success,
            row=0
        )
        counter.callback = self._go_to_chapter
        self.add_item(counter)

        nxt = ui.Button(emoji="➡️", style=discord.ButtonStyle.secondary,
                        row=0, disabled=self.index >= total - 1)
        nxt.callback = self._next
        self.add_item(nxt)

        # ── Row 1: ✏️ Summary  🖼️ Image  ↩ Return ───
        note_btn = ui.Button(label="✏️ Summary",
                              style=discord.ButtonStyle.primary, row=1)
        note_btn.callback = self._edit_note
        self.add_item(note_btn)

        img_btn = ui.Button(label="🖼️ Image",
                             style=discord.ButtonStyle.primary, row=1)
        img_btn.callback = self._edit_image
        self.add_item(img_btn)

        if self.parent_view is not None:
            back_btn = ui.Button(label="↩ Return",
                                 style=discord.ButtonStyle.success, row=1)
            back_btn.callback = self._back_to_parent
            self.add_item(back_btn)

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

    async def _go_to_chapter(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Not your builder!", ephemeral=True)
            return
        await interaction.response.send_modal(GoToChapterModal(self))

    # ── Edit callbacks ───────────────────────────

    async def _edit_note(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Not your builder!", ephemeral=True)
            return
        await interaction.response.send_modal(ChapterSummaryModal(self))

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

    async def _back_to_parent(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Not your builder!", ephemeral=True)
            return
        self.parent_view.reload_story()
        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view,
        )
