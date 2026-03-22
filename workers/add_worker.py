import asyncio
from datetime import datetime
from core.queues import add_queue

from ao3_parser import fetch_ao3_metadata
from database import (
    add_user,
    add_story,
    add_chapter,
    get_user_id,
    grant_story_credit
)
from ui.status_controller import StatusController

async def add_worker():

    while True:

        interaction, url, wattpad, cover = await add_queue.get()
        status_msg = None

        try:
            # STEP 1
            status_msg = await interaction.followup.send(
                "⏳ Processing started…\n"
                "⬇️ Downloading HTML export…"
            )

            # STEP 2
            data = await asyncio.to_thread(fetch_ao3_metadata, url)

            await status_msg.edit(
                content=
                "⏳ Processing started…\n"
                "⬇️ Downloading HTML export…\n"
                "📖 Parsing chapters…"
            )

            # STEP 3
            discord_id = str(interaction.user.id)
            add_user(discord_id, interaction.user.name)

            library_updated = datetime.utcnow().strftime("%Y-%m-%d")

            await status_msg.edit(
                content=
                "⏳ Processing started…\n"
                "⬇️ Downloading EPUB…\n"
                "📖 Parsing chapters…\n"
                "💾 Saving to library…"
            )

            story_id = add_story(
                discord_id,
                data["title"],
                data["author"],
                data["normalized_url"],
                data["chapter_count"],
                data["last_updated"],
                data["word_count"],
                data["summary"],
                library_updated,
                cover,
                wattpad,
                tags=data.get("tags", []),
                rating=data["rating"]
            )

            if not story_id:
                await status_msg.edit(
                    content="⚠️ Story already exists."
                )
                continue

            for ch in data["chapters"]:
                add_chapter(story_id, ch["number"], ch["title"], None, ch.get("summary"))

            # FINAL STEP — grant story credit
            credit_msg = ""
            uid = get_user_id(str(interaction.user.id))
            if uid and story_id:
                granted, new_balance = grant_story_credit(uid, story_id)
                if granted:
                    credit_msg = f"\n-# 💎 +150 crystals earned  ·  {new_balance:,} total"

            await status_msg.edit(
                content=
                "✅ Added successfully!\n"
                f"📚 **{data['title']}**\n"
                f"Chapters: {data['chapter_count']} | "
                f"Words: {data['word_count']:,}"
                f"{credit_msg}"
            )

        except Exception as e:
            if status_msg:
                await status_msg.edit(
                    content=f"❌ Error:\n`{e}`"
                )

        finally:
            add_queue.task_done()