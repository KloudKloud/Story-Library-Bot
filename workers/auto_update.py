import asyncio
from datetime import datetime

from ao3_parser import fetch_ao3_metadata
from database import (
    get_all_stories_sorted,
    delete_chapters_by_story,
    add_chapter,
    update_story_metadata
)

AUTO_UPDATE_BASE = 60 * 60 * 24
auto_update_delay = AUTO_UPDATE_BASE


async def auto_update_loop(bot, initial_delay=False):

    global auto_update_delay

    await bot.wait_until_ready()

    if initial_delay:
        print("🕒 Auto-update first run delayed 24 hours.")
        await asyncio.sleep(AUTO_UPDATE_BASE)

    while not bot.is_closed():

        print(f"🔄 Auto-update cycle started (delay={auto_update_delay//3600}h)")

        failures = 0
        successes = 0

        try:
            stories = get_all_stories_sorted("alphabetical")

            for story in stories:

                try:
                    (
                        title,
                        old_chapters,
                        old_updated,
                        old_words,
                        old_summary,
                        ao3_url,
                        username,
                        wattpad,
                        cover,
                        story_id
                    ) = story

                    print(f"Checking: {title}")

                    data = await asyncio.to_thread(
                        fetch_ao3_metadata,
                        ao3_url
                    )

                    successes += 1
                    changed = False

                    if data["chapter_count"] != old_chapters:
                        delete_chapters_by_story(story_id)

                        for ch in data["chapters"]:
                            add_chapter(story_id, ch["number"], ch["title"], None, ch.get("summary"))

                        changed = True
                        print(f"📚 Chapters updated: {title}")

                    if (
                        data["title"] != title
                        or data["word_count"] != old_words
                        or data["summary"] != old_summary
                        or data["chapter_count"] != old_chapters
                    ):
                        changed = True

                    if changed:
                        library_updated = datetime.utcnow().strftime("%Y-%m-%d")

                        update_story_metadata(
                            story_id,
                            data["title"],
                            data["chapter_count"],
                            data["last_updated"],
                            data["word_count"],
                            data["summary"],
                            library_updated
                        )

                        print(f"✔ Updated: {title}")

                    await asyncio.sleep(2)

                except Exception as e:
                    failures += 1
                    print(f"❌ Failed: {title} → {e}")

        except Exception as e:
            print(f"❌ Cycle error: {e}")
            failures += 1

        total = successes + failures

        if total > 0:
            failure_ratio = failures / total

            if failure_ratio > 0.6:
                auto_update_delay = min(auto_update_delay * 1.5, 60 * 60 * 36)
                print("⚠️ High failure rate — backing off.")

            elif failure_ratio > 0.3:
                auto_update_delay = min(auto_update_delay * 1.2, 60 * 60 * 24)
                print("⚠️ Some failures — slowing slightly.")

            else:
                auto_update_delay = max(
                    AUTO_UPDATE_BASE,
                    int(auto_update_delay * 0.8)
                )
                print("💚 AO3 healthy — reducing delay.")

        print(f"😴 Sleeping {auto_update_delay//3600} hours...\n")
        await asyncio.sleep(auto_update_delay)