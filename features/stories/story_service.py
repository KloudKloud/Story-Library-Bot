from database import (
    get_all_stories_sorted,
    get_user_id,
    get_story_progress,
    set_story_progress
)


# =====================================================
# STORY QUERIES
# =====================================================

def get_library_stories():
    return get_all_stories_sorted("alphabetical")


# =====================================================
# PROGRESS HELPERS
# =====================================================

def get_user_progress(discord_user_id, story_id):

    uid = get_user_id(str(discord_user_id))
    if not uid:
        return 0

    return get_story_progress(uid, story_id) or 0


def increment_progress(discord_user_id, story):

    uid = get_user_id(str(discord_user_id))
    if not uid:
        return

    current = get_story_progress(uid, story[-1]) or 0
    set_story_progress(uid, story[-1], min(current + 1, story[1]))


def mark_finished(discord_user_id, story):

    uid = get_user_id(str(discord_user_id))
    if not uid:
        return

    set_story_progress(uid, story[-1], story[1])


def reset_progress(discord_user_id, story):

    uid = get_user_id(str(discord_user_id))
    if not uid:
        return

    set_story_progress(uid, story[-1], 0)

def unpack_story(row):

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "author": row["author"],
        "ao3_url": row["ao3_url"],
        "chapter_count": row["chapter_count"],
        "last_updated": row["last_updated"],
        "word_count": row["word_count"],
        "summary": row["summary"],
        "library_updated": row["library_updated"],
        "cover_url": row["cover_url"],
        "wattpad_url": row["wattpad_url"],
        "playlist_url": row["playlist_url"],
        "roadmap": row["roadmap"],
        "story_notes": row["story_notes"],
        "extra_link_title": row["extra_link_title"],
        "extra_link_url": row["extra_link_url"],
        "appreciation": row["appreciation"],
    }