import discord
from discord import ui
import asyncio
from datetime import datetime

from ao3_parser import fetch_ao3_metadata
from database import (
    get_story_by_id,
    delete_chapters_by_story,
    add_chapter,
    update_story_metadata
)

class UpdateSelectView(ui.View):

    def __init__(self, stories, requester):
        super().__init__(timeout=120)
        self.stories = stories
        self.requester = requester
        self.viewer = requester

        options = [
            discord.SelectOption(
                label=s[1][:100],   # title
                value=str(s[0])     # story_id
            )
            for s in stories
        ]

        self.add_item(self.StorySelect(options, self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.viewer.id:
            await interaction.response.send_message(
                "❌ This session belongs to someone else.",
                ephemeral=True, delete_after=5
            )
            return False
        return True

    class StorySelect(ui.Select):
        def __init__(self, options, parent_view):
            self.parent_view = parent_view
            super().__init__(
                placeholder="Select story to update...",
                options=options
            )

        async def callback(self, interaction: discord.Interaction):

            story_id = int(self.values[0])

            # IMPORTANT: defer so Discord shows "thinking"
            await interaction.response.defer()

            status_msg = await interaction.followup.send(
                "⏳ **Starting update...**\n"
                "⬇️ Downloading EPUB..."
            )

            try:
                # ---------------- GET STORY DATA ----------------
                story = get_story_by_id(story_id)

                if not story:
                    await status_msg.edit(content="❌ Story not found.")
                    return

                ao3_url = story["ao3_url"]
                old_chapters = story["chapter_count"] or 0
                old_words    = story["word_count"] or 0
                title        = story["title"]
                sid          = story["id"]

                # ---------------- FETCH NEW DATA ----------------
                data = await asyncio.to_thread(
                    fetch_ao3_metadata,
                    ao3_url
                )

                await status_msg.edit(
                    content="📖 Checking chapters..."
                )

                # ---------------- UPDATE CHAPTERS ----------------
                if data["chapter_count"] != old_chapters:

                    delete_chapters_by_story(sid)

                    for n, c in data["chapters"]:
                        add_chapter(sid, n, c)

                await status_msg.edit(
                    content="💾 Saving updates..."
                )

                # ---------------- UPDATE STORY (kwargs) ----------------
                library_updated = datetime.utcnow().strftime("%Y-%m-%d")

                update_story_metadata(
                    sid,
                    title=data["title"],
                    chapter_count=data["chapter_count"],
                    last_updated=data["last_updated"],
                    word_count=data["word_count"],
                    summary=data["summary"],
                    library_updated=library_updated,
                    rating=data.get("rating")
                )

                await status_msg.edit(
                    content=(
                        f"✅ **{data['title']} refreshed!**\n"
                        f"📚 Chapters: {old_chapters} → {data['chapter_count']}\n"
                        f"📝 Words: {old_words:,} → {data['word_count']:,}"
                    )
                )

            except Exception as e:
                await status_msg.edit(
                    content=f"❌ Update failed:\n`{e}`"
                )
