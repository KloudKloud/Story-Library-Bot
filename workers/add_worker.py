import asyncio
from datetime import datetime
from core.queues import add_queue

from ao3_parser import fetch_ao3_metadata
from wattpad_parser import fetch_wattpad_metadata, WattpadError
from database import (
    add_user,
    add_story,
    add_chapter,
    get_user_id,
    grant_story_credit
)
from pad_placeholder import get_placeholder_url
from ui.status_controller import StatusController

async def add_worker():

    while True:

        interaction, url, platform, cover = await add_queue.get()
        status_msg = None

        try:

            if platform == "wattpad":

                # ── WATTPAD PATH ──────────────────────────────────────────────

                status_msg = await interaction.followup.send(
                    "⏳ Processing started…\n"
                    "⬇️ Fetching from Wattpad…"
                )

                try:
                    data = await asyncio.to_thread(fetch_wattpad_metadata, url)
                except WattpadError as e:
                    await status_msg.edit(content=f"❌ {e.user_message}")
                    continue

                await status_msg.edit(
                    content=
                    "⏳ Processing started…\n"
                    "⬇️ Fetching from Wattpad…\n"
                    "📖 Counting words & parsing chapters…"
                )

                # If the user didn't upload a cover, use Wattpad's cover
                # (cover == None means "let the worker decide")
                if cover is None:
                    cover = data.get("cover_url") or get_placeholder_url()

                # Map Wattpad-specific keys to the shared keys the rest of
                # this worker expects
                data["summary"]        = data.get("description", "No summary available.")
                data["last_updated"]   = data.get("last_updated", "Unknown")
                # Represent the binary mature flag as a readable rating string
                data["rating"]         = "Mature" if data.get("mature") else None

            else:

                # ── AO3 PATH ─────────────────────────────────────────────────

                status_msg = await interaction.followup.send(
                    "⏳ Processing started…\n"
                    "⬇️ Downloading HTML export…"
                )

                data = await asyncio.to_thread(fetch_ao3_metadata, url)

                await status_msg.edit(
                    content=
                    "⏳ Processing started…\n"
                    "⬇️ Downloading HTML export…\n"
                    "📖 Parsing chapters…"
                )

            # ── SHARED: SAVE TO DATABASE ──────────────────────────────────────

            discord_id = str(interaction.user.id)
            add_user(discord_id, interaction.user.name)

            library_updated = datetime.utcnow().strftime("%Y-%m-%d")

            await status_msg.edit(
                content=
                "⏳ Processing started…\n"
                "⬇️ Downloading…\n"
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
                platform=platform or "ao3",
                tags=data.get("tags", []),
                rating=data.get("rating"),
                wattpad_reads=data.get("reads") if platform == "wattpad" else None,
                wattpad_votes=data.get("votes") if platform == "wattpad" else None,
                wattpad_comments=data.get("comments") if platform == "wattpad" else None,
            )

            if not story_id:
                await status_msg.edit(
                    content="⚠️ Story already exists."
                )
                continue

            for ch in data["chapters"]:
                add_chapter(
                    story_id,
                    ch["number"],
                    ch["title"],
                    None,
                    ch.get("summary"),
                    wattpad_comment_count=ch.get("comment_count") if platform == "wattpad" else None,
                )

            # ── FINAL STEP — grant story credit ───────────────────────────────
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
