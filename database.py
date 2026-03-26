import sqlite3
import os
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "library.db")


# =====================================================
# CONNECTION
# =====================================================
def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")   # required for CASCADE deletes
    cursor = conn.cursor()
    return conn


def safe_add_column(cursor, table, column, col_type="TEXT"):
    """
    Adds a column only if it doesn't exist.
    Prevents sqlite errors during upgrades.
    """
    try:
        cursor.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
        )
    except sqlite3.OperationalError:
        pass

def character_to_dict(row):

    if row is None:
        return None

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "story_id": row["story_id"],
        "name": row["name"],
        "gender": row["gender"],
        "personality": row["personality"],
        "image_url": row["image_url"],
        "quote": row["quote"],
        "age": row["age"],
        "height": row["height"],
        "physical_features": row["physical_features"],
        "relationships": row["relationships"],
        "lore": row["lore"],
        "music_url": row["music_url"] if "music_url" in row.keys() else None,
        "species": row["species"] if "species" in row.keys() else None,
        "shiny_image_url": row["shiny_image_url"] if "shiny_image_url" in row.keys() else None,
        "is_main_character": int(row["is_main_character"]) if "is_main_character" in row.keys() and row["is_main_character"] else 0,
    }


# =====================================================
# TTL CACHE (for autocomplete hot paths)
# =====================================================
class _TTLCache:
    """Simple single-value cache with a time-to-live."""
    def __init__(self, ttl_seconds=30):
        self._ttl = ttl_seconds
        self._data = None
        self._expires = 0

    def get(self):
        if time.monotonic() < self._expires:
            return self._data
        return None

    def set(self, data):
        self._data = data
        self._expires = time.monotonic() + self._ttl

    def invalidate(self):
        self._expires = 0

_all_characters_cache = _TTLCache(ttl_seconds=30)
_all_ships_cache = _TTLCache(ttl_seconds=30)


# =====================================================
# INITIALIZE DATABASE
# =====================================================
def initialize_database():
    conn = get_connection()
    cursor = conn.cursor()

    # USERS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        discord_id TEXT UNIQUE,
        username TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ship_characters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ship_id INTEGER,
        character_id INTEGER,
        FOREIGN KEY (ship_id) REFERENCES ships(id) ON DELETE CASCADE,
        FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
    );
    """)

    # =====================================================
    # STORY BADGES (BOOK COMPLETION)
    # =====================================================

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS story_badges (
        user_id INTEGER,
        story_id INTEGER,
        earned_at TEXT,
        PRIMARY KEY (user_id, story_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS story_shiny_charms (
        user_id INTEGER,
        story_id INTEGER,
        earned_at TEXT,
        PRIMARY KEY (user_id, story_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE
    );
    """)

    # STORIES
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        author TEXT,
        ao3_url TEXT UNIQUE,
        chapter_count INTEGER,
        last_updated TEXT,
        word_count INTEGER,
        summary TEXT,
        library_updated TEXT,
        cover_url TEXT,
        wattpad_url TEXT,
        playlist_url TEXT,
        roadmap TEXT,
        story_notes TEXT,
        appreciation TEXT,
        extra_link_title TEXT,
        extra_link_url TEXT,
        extra_link2_title TEXT,
        extra_link2_url TEXT,
        rating TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # STORY TAGS (MASTER LIST)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    );
    """)

    # STORY ↔ TAG RELATIONSHIP
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS story_tags (
        story_id INTEGER,
        tag_id INTEGER,
        FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE,
        FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
        UNIQUE(story_id, tag_id)
    );
    """)

    # =====================================================
    # CHARACTERS (NEW)
    # =====================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS characters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        story_id INTEGER,
        name TEXT NOT NULL,
        gender TEXT,
        personality TEXT,
        image_url TEXT,
        quote TEXT,
        lore TEXT,
        age TEXT,
        height TEXT,
        physical_features TEXT,
        relationships TEXT,
        music_url TEXT,
        species TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE
    );
    """)

    # CHAPTERS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chapters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        story_id INTEGER,
        chapter_number INTEGER,
        chapter_title TEXT,
        chapter_url TEXT,
        chapter_summary TEXT,
        FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE
    );
    """)

    # READING PROGRESS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        story_id INTEGER,
        completed_chapters INTEGER DEFAULT 0,
        UNIQUE(user_id, story_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE
    );
    """)

# =====================================================
# PROFILES
# =====================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE,
        bio TEXT,
        pronouns TEXT,
        favorite_pokemon TEXT,
        image_url TEXT,
        favorite_fics TEXT,
        favorite_authors TEXT,
        hobbies TEXT,
        fun_fact TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

 
# =====================================================
# FANART SYSTEM
# =====================================================

# FANART POSTS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fanart (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        story_id INTEGER,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        image_url TEXT NOT NULL,
        created_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE
    );
    """)

    safe_add_column(cursor, "fanart", "tags")
    safe_add_column(cursor, "fanart", "inspiration")
    safe_add_column(cursor, "fanart", "scene_ref")
    safe_add_column(cursor, "fanart", "artist_name")
    safe_add_column(cursor, "fanart", "artist_link")
    safe_add_column(cursor, "fanart", "canon_au")
    safe_add_column(cursor, "fanart", "music_url")
    safe_add_column(cursor, "fanart", "origin")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fanart_likes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        fanart_id  INTEGER NOT NULL,
        created_at TEXT    NOT NULL DEFAULT (datetime('now')),
        UNIQUE(user_id, fanart_id),
        FOREIGN KEY (user_id)   REFERENCES users(id)   ON DELETE CASCADE,
        FOREIGN KEY (fanart_id) REFERENCES fanart(id)  ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fanart_comments (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        fanart_id  INTEGER NOT NULL,
        content    TEXT    NOT NULL,
        created_at TEXT    NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id)   REFERENCES users(id)   ON DELETE CASCADE,
        FOREIGN KEY (fanart_id) REFERENCES fanart(id)  ON DELETE CASCADE
    );
    """)

    # FANART ↔ CHARACTERS (many-to-many)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fanart_characters (
        fanart_id INTEGER,
        character_id INTEGER,
        FOREIGN KEY (fanart_id) REFERENCES fanart(id) ON DELETE CASCADE,
        FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
    );
    """)

    # =====================================================
    # FAVORITE CHARACTERS
    # =====================================================

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS favorite_characters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        story_id INTEGER,
        character_id INTEGER,
        created_at TEXT,
        UNIQUE(user_id, character_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE,
        FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE
    );
    """)

    # SHIPS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT NOT NULL,
        character1_id INTEGER,
        character2_id INTEGER,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # FANART ↔ SHIPS

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fanart_ships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fanart_id INTEGER,
        ship_id INTEGER,
        FOREIGN KEY (fanart_id) REFERENCES fanart(id) ON DELETE CASCADE,
        FOREIGN KEY (ship_id) REFERENCES ships(id) ON DELETE CASCADE
    );
    """)

    # Migration: add columns introduced after initial schema.
    # These are no-ops on a fresh DB (columns already in CREATE TABLE above)
    # but ensure existing DBs get upgraded safely.
    safe_add_column(cursor, "characters", "age")
    safe_add_column(cursor, "characters", "height")
    safe_add_column(cursor, "characters", "physical_features")
    safe_add_column(cursor, "characters", "relationships")
    safe_add_column(cursor, "characters", "lore")
    safe_add_column(cursor, "characters", "music_url")
    safe_add_column(cursor, "characters", "species")
    safe_add_column(cursor, "characters", "shiny_image_url")
    safe_add_column(cursor, "characters", "is_main_character", "INTEGER")
    safe_add_column(cursor, "users", "ctc_main_character_id", "INTEGER")
    safe_add_column(cursor, "users", "setmc_last_input", "TEXT")
    safe_add_column(cursor, "stories", "playlist_url")
    safe_add_column(cursor, "stories", "roadmap")
    safe_add_column(cursor, "stories", "story_notes")
    safe_add_column(cursor, "stories", "appreciation")
    safe_add_column(cursor, "stories", "extra_link_title")
    safe_add_column(cursor, "stories", "extra_link_url")
    safe_add_column(cursor, "stories", "extra_link2_title")
    safe_add_column(cursor, "stories", "extra_link2_url")
    safe_add_column(cursor, "profiles", "favorite_fics")
    safe_add_column(cursor, "profiles", "favorite_authors")
    safe_add_column(cursor, "profiles", "hobbies")
    safe_add_column(cursor, "profiles", "fun_fact")
    safe_add_column(cursor, "stories", "rating")
    safe_add_column(cursor, "fanart", "tags")
    safe_add_column(cursor, "fanart", "inspiration")
    # v3 migration: chapter summaries from AO3 HTML export
    safe_add_column(cursor, "chapters", "chapter_summary")
    safe_add_column(cursor, "chapters", "chapter_image_url")
    safe_add_column(cursor, "chapters", "chapter_link")
    safe_add_column(cursor, "chapters", "chapter_wattpad_url")
    safe_add_column(cursor, "chapters", "chapter_ao3_url")

    # =====================================================
    # COMMENTS
    # =====================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS comments (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        story_id    INTEGER NOT NULL,
        chapter_id  INTEGER,
        content     TEXT    NOT NULL,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id)    REFERENCES users(id)    ON DELETE CASCADE,
        FOREIGN KEY (story_id)   REFERENCES stories(id)  ON DELETE CASCADE,
        FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
    );
    """)

    # ── Announcement channels ────────────────────────────
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS announcement_channels (
        user_id INTEGER PRIMARY KEY,
        channel_id TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()

def create_reader_badges_table():

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reader_badges (
            user_id INTEGER NOT NULL,
            story_id INTEGER NOT NULL,
            earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, story_id)
        )
    """)

    conn.commit()
    conn.close()

def fanart_row_to_dict(row):

    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "image_url": row["image_url"],
        "created_at": row["created_at"],
        "story_title": row["story_title"] if "story_title" in row.keys() else None,
        "story_id": row["story_id"] if "story_id" in row.keys() else None,
        "author": row["author"] if "author" in row.keys() else None,
        "cover_url": row["cover_url"] if "cover_url" in row.keys() else None,
        "tags": row["tags"] if "tags" in row.keys() else None,
        "inspiration": row["inspiration"] if "inspiration" in row.keys() else None,
        "scene_ref": row["scene_ref"] if "scene_ref" in row.keys() else None,
        "artist_name": row["artist_name"] if "artist_name" in row.keys() else None,
        "artist_link": row["artist_link"] if "artist_link" in row.keys() else None,
        "canon_au": row["canon_au"] if "canon_au" in row.keys() else None,
        "music_url": row["music_url"] if "music_url" in row.keys() else None,
        "origin": row["origin"] if "origin" in row.keys() else None,
        "user_id": row["user_id"] if "user_id" in row.keys() else None,
        "discord_id": row["discord_id"] if "discord_id" in row.keys() else None,
    }
# =====================================================
# USERS
# =====================================================
    
def add_user(discord_id, username):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT OR IGNORE INTO users (discord_id, username)
    VALUES (?, ?)
    """, (discord_id, username))

    # Also ensure a blank profile row exists so profile queries never crash
    cursor.execute(
        "SELECT id FROM users WHERE discord_id = ?", (str(discord_id),)
    )
    row = cursor.fetchone()
    if row:
        cursor.execute("""
        INSERT OR IGNORE INTO profiles (user_id)
        VALUES (?)
        """, (row[0],))

    conn.commit()
    conn.close()


def get_or_create_user(discord_id, username):
    """Ensures a user (and blank profile) exists, then returns their DB id."""
    add_user(str(discord_id), username)
    return get_user_id(str(discord_id))


def get_discord_id_by_user_id(user_id: int):
    """Return the discord_id string for a given internal user_id, or None."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT discord_id FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row["discord_id"] if row else None


# ── Announcement channels ─────────────────────────────

def set_announcement_channel(user_id: int, channel_id: str):
    """Set (or update) a user's announcement channel."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO announcement_channels (user_id, channel_id)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET channel_id = excluded.channel_id
    """, (user_id, channel_id))
    conn.commit()
    conn.close()


def get_announcement_channel(user_id: int):
    """Return the channel_id string for a user, or None."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT channel_id FROM announcement_channels WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row["channel_id"] if row else None


def remove_announcement_channel(user_id: int):
    """Remove a user's announcement channel."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM announcement_channels WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()
    conn.close()


def get_user_id(discord_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM users WHERE discord_id = ?",
        (discord_id,)
    )

    result = cursor.fetchone()
    conn.close()

    return result[0] if result else None


# =====================================================
# STORIES
# =====================================================
def add_story(
    discord_id,
    title,
    author,
    primary_url,
    chapter_count,
    last_updated,
    word_count,
    summary,
    library_updated,
    cover,
    platform='ao3',
    rating=None,
    tags=None,
    wattpad_reads=None,
    wattpad_votes=None,
    wattpad_comments=None,
    ao3_hits=None,
    ao3_kudos=None,
    ao3_comments=None,
    ao3_bookmarks=None,
):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        user_id = get_user_id(discord_id)

        ao3_url_val     = primary_url if platform == "ao3"     else None
        wattpad_url_val = primary_url if platform == "wattpad" else None
        url_col         = "wattpad_url" if platform == "wattpad" else "ao3_url"

        # Prevent duplicate entries (check the correct URL column)
        cursor.execute(
            f"SELECT id FROM stories WHERE {url_col} = ?",
            (primary_url,)
        )

        existing = cursor.fetchone()

        if existing:
            conn.close()
            return None

        cursor.execute("""
        INSERT INTO stories (
            user_id,
            title,
            author,
            ao3_url,
            wattpad_url,
            platform,
            chapter_count,
            last_updated,
            word_count,
            summary,
            library_updated,
            cover_url,
            rating,
            wattpad_reads,
            wattpad_votes,
            wattpad_comments,
            ao3_hits,
            ao3_kudos,
            ao3_comments,
            ao3_bookmarks
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            title,
            author,
            ao3_url_val,
            wattpad_url_val,
            platform,
            chapter_count,
            last_updated,
            word_count,
            summary,
            library_updated,
            cover,
            rating,
            wattpad_reads,
            wattpad_votes,
            wattpad_comments,
            ao3_hits,
            ao3_kudos,
            ao3_comments,
            ao3_bookmarks,
        ))

        story_id = cursor.lastrowid

        # ---------- TAGS ----------
        if tags:
            add_story_tags(cursor, story_id, tags)

        conn.commit()
        conn.close()

        return story_id

    except Exception as e:
        conn.rollback()
        conn.close()
        raise e


def get_story_by_url(url, platform='ao3'):
    conn = get_connection()
    cursor = conn.cursor()

    col = "wattpad_url" if platform == "wattpad" else "ao3_url"

    cursor.execute(f"""
    SELECT id, user_id, title, chapter_count,
           word_count, summary, last_updated
    FROM stories
    WHERE {col} = ?
    """, (url,))

    result = cursor.fetchone()
    conn.close()
    return result


def update_story_metadata(story_id, **kwargs):

    conn = get_connection()
    cursor = conn.cursor()

    fields = []
    values = []

    for key, value in kwargs.items():
        fields.append(f"{key} = ?")
        values.append(value)

    values.append(story_id)

    query = f"""
    UPDATE stories
    SET {", ".join(fields)}
    WHERE id = ?
    """

    cursor.execute(query, values)

    conn.commit()
    conn.close()


def delete_story(story_id):
    """
    Fully purge a story and all associated data:
    progress, badges, fanart links, character favorites/ships, then the story itself.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Wipe all reading progress for this story (no FK cascade to stories table)
    cursor.execute("DELETE FROM progress WHERE story_id = ?", (story_id,))

    # 2. Wipe all story badges for this story
    cursor.execute("DELETE FROM story_badges WHERE story_id = ?", (story_id,))

    # 3. Unlink fanart (keep artwork, just remove story association)
    cursor.execute(
        "UPDATE fanart SET story_id = NULL WHERE story_id = ?",
        (story_id,)
    )

    # 4. Collect character IDs belonging to this story
    cursor.execute("SELECT id FROM characters WHERE story_id = ?", (story_id,))
    char_ids = [r["id"] for r in cursor.fetchall()]

    if char_ids:
        placeholders = ",".join("?" * len(char_ids))

        # 4a. Remove from anyone's favorites
        cursor.execute(
            f"DELETE FROM favorite_characters WHERE character_id IN ({placeholders})",
            char_ids
        )

        # 4b. Remove fanart character tags
        cursor.execute(
            f"DELETE FROM fanart_characters WHERE character_id IN ({placeholders})",
            char_ids
        )

        # 4c. Find and purge ships that include these characters
        cursor.execute(
            f"SELECT DISTINCT ship_id FROM ship_characters WHERE character_id IN ({placeholders})",
            char_ids
        )
        ship_ids = [r["ship_id"] for r in cursor.fetchall()]

        if ship_ids:
            sp = ",".join("?" * len(ship_ids))
            cursor.execute(f"DELETE FROM fanart_ships    WHERE ship_id IN ({sp})", ship_ids)
            cursor.execute(f"DELETE FROM ship_characters WHERE ship_id IN ({sp})", ship_ids)
            cursor.execute(f"DELETE FROM ships           WHERE id      IN ({sp})", ship_ids)

    # 5. Delete story — CASCADE handles story_tags, chapters, characters FK fields
    cursor.execute("DELETE FROM stories WHERE id = ?", (story_id,))

    conn.commit()
    conn.close()


# =====================================================
# CHAPTERS
# =====================================================
def add_chapter(story_id, chapter_number, chapter_title, chapter_url=None, chapter_summary=None, wattpad_comment_count=None):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO chapters (
        story_id,
        chapter_number,
        chapter_title,
        chapter_url,
        chapter_summary,
        wattpad_comment_count
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (story_id, chapter_number, chapter_title, chapter_url, chapter_summary, wattpad_comment_count))

    conn.commit()
    conn.close()


def delete_chapters_by_story(story_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM chapters WHERE story_id = ?", (story_id,))
    conn.commit()
    conn.close()


def get_chapters_by_story(story_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT chapter_number, chapter_title, chapter_url
    FROM chapters
    WHERE story_id = ?
    ORDER BY chapter_number ASC
    """, (story_id,))

    rows = cursor.fetchall()
    conn.close()
    return rows


def get_chapter_id_by_number(story_id: int, chapter_number: int):
    """Returns the DB id of a specific chapter, or None if not found."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM chapters
        WHERE story_id = ? AND chapter_number = ?
    """, (story_id, chapter_number))
    row = cursor.fetchone()
    conn.close()
    return row["id"] if row else None

def grant_chapter_build_bonus(author_user_id: int, chapter_id: int):
    """
    Awards 10 crystals to an author the first time a chapter reaches 3/3 fields.
    Uses credit_log to ensure it only fires once per chapter.
    Returns (granted: bool, new_balance: int).
    """
    AMOUNT = 10
    reason = f"chapter_build_complete:{chapter_id}"
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM credit_log WHERE user_id = ? AND reason = ?",
        (author_user_id, reason)
    )
    if cursor.fetchone():
        conn.close()
        return False, get_balance(author_user_id)
    conn.close()
    new_balance = add_credits(author_user_id, AMOUNT, reason)
    return True, new_balance


def get_chapters_full(story_id: int):
    """Returns all chapter rows with every column including image/link/summary."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, chapter_number, chapter_title, chapter_url,
               chapter_summary, chapter_image_url, chapter_link,
               chapter_wattpad_url, chapter_ao3_url
        FROM chapters
        WHERE story_id = ?
        ORDER BY chapter_number ASC
    """, (story_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_chapter_extras(chapter_id: int, summary: str = None,
                          image_url: str = None, wattpad_url: str = None,
                          ao3_url: str = None):
    """Author-facing update for summary, image, Wattpad link, and AO3 link."""
    conn = get_connection()
    cursor = conn.cursor()
    if summary is not None:
        cursor.execute("UPDATE chapters SET chapter_summary = ? WHERE id = ?",
                       (summary or None, chapter_id))
    if image_url is not None:
        cursor.execute("UPDATE chapters SET chapter_image_url = ? WHERE id = ?",
                       (image_url or None, chapter_id))
    if wattpad_url is not None:
        cursor.execute("UPDATE chapters SET chapter_wattpad_url = ? WHERE id = ?",
                       (wattpad_url or None, chapter_id))
    if ao3_url is not None:
        cursor.execute("UPDATE chapters SET chapter_ao3_url = ? WHERE id = ?",
                       (ao3_url or None, chapter_id))
    conn.commit()
    conn.close()


def fill_chapter_alt_urls(story_id: int, alt_platform: str, chapter_url_map: dict):
    """
    Store the alt-platform chapter URL for each chapter by number.
    alt_platform "ao3"     → writes chapter_ao3_url
    alt_platform "wattpad" → writes chapter_wattpad_url
    Only writes rows where the target column is currently NULL (preserves manual overrides).
    """
    if not chapter_url_map:
        return
    col = "chapter_ao3_url" if alt_platform == "ao3" else "chapter_wattpad_url"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executemany(
        f"UPDATE chapters SET {col} = ? WHERE story_id = ? AND chapter_number = ? AND {col} IS NULL",
        [(url, story_id, num) for num, url in chapter_url_map.items()]
    )
    conn.commit()
    conn.close()


def fill_chapter_summaries(story_id: int, chapter_summary_map: dict):
    """
    Set chapter_summary for each chapter by number, but ONLY if currently NULL.
    Preserves any summaries the author has already filled in.
    chapter_summary_map: {chapter_number: summary_text}
    """
    if not chapter_summary_map:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executemany(
        "UPDATE chapters SET chapter_summary = ? WHERE story_id = ? AND chapter_number = ? AND chapter_summary IS NULL",
        [(summary, story_id, num) for num, summary in chapter_summary_map.items() if summary]
    )
    conn.commit()
    conn.close()


# ── Comments ──────────────────────────────────────

def add_comment(user_id: int, story_id: int, chapter_id: int, content: str):
    """Inserts a comment and returns its new id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO comments (user_id, story_id, chapter_id, content)
        VALUES (?, ?, ?, ?)
    """, (user_id, story_id, chapter_id, content))
    conn.commit()
    cid = cursor.lastrowid
    conn.close()
    return cid


def get_comments_for_chapter(chapter_id: int):
    """Returns all comments for a chapter, oldest first."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.content, c.created_at, u.username, u.discord_id
        FROM comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.chapter_id = ?
        ORDER BY c.created_at ASC
    """, (chapter_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_comment_count_for_chapter(chapter_id: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM comments WHERE chapter_id = ?", (chapter_id,)
    )
    count = cursor.fetchone()["cnt"]
    conn.close()
    return count


def user_has_commented(user_id: int, chapter_id: int) -> bool:
    """True if the user has already left a comment on this chapter."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM comments WHERE user_id = ? AND chapter_id = ?
    """, (user_id, chapter_id))
    result = cursor.fetchone() is not None
    conn.close()
    return result


def get_all_comments_for_story(story_id: int):
    """Returns all comments across all chapters of a story, newest first."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.content, c.created_at,
               u.username, u.discord_id,
               ch.chapter_number, ch.chapter_title
        FROM comments c
        JOIN users u    ON c.user_id    = u.id
        JOIN chapters ch ON c.chapter_id = ch.id
        WHERE c.story_id = ?
        ORDER BY c.created_at DESC
    """, (story_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# =====================================================
# CHARACTERS
# =====================================================

def get_characters_by_user(user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        c.id,
        c.user_id,
        c.story_id,
        c.name,
        c.gender,
        c.personality,
        c.image_url,
        c.quote,
        c.age,
        c.height,
        c.physical_features,
        c.relationships,
        c.lore,
        c.music_url,
        c.species,
        c.shiny_image_url,
        COALESCE(c.is_main_character, 0) AS is_main_character,
        s.title AS story_title,
        u.username AS author
    FROM characters c
    JOIN stories s ON c.story_id = s.id
    JOIN users u ON s.user_id = u.id
    WHERE c.user_id = ?
    ORDER BY c.name COLLATE NOCASE
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(r) for r in rows]

def get_character_id_by_name(story_id, name):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id
    FROM characters
    WHERE story_id = ?
      AND name = ?
    LIMIT 1
    """, (story_id, name))

    row = cursor.fetchone()
    conn.close()

    return row[0] if row else None

# =====================================================
# PROGRESS SYSTEM
# =====================================================
def set_story_progress(user_id, story_id, completed):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO progress (user_id, story_id, completed_chapters)
    VALUES (?, ?, ?)
    ON CONFLICT(user_id, story_id)
    DO UPDATE SET completed_chapters = excluded.completed_chapters
    """, (user_id, story_id, completed))

    conn.commit()
    conn.close()


def get_story_progress(user_id, story_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT completed_chapters
    FROM progress
    WHERE user_id = ? AND story_id = ?
    """, (user_id, story_id))

    result = cursor.fetchone()
    conn.close()

    return result[0] if result else 0

def get_story_by_id(story_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM stories WHERE id = ?",
        (story_id,)
    )

    result = cursor.fetchone()
    conn.close()

    return result

def get_stories_by_user(user_id):
    """
    Returns all stories owned by a specific user.
    Used by /update command.
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            title,
            chapter_count,
            last_updated,
            word_count,
            summary,
            COALESCE(is_dummy, 0) AS is_dummy
        FROM stories
        WHERE user_id = ?
        ORDER BY COALESCE(is_dummy, 0) ASC, title COLLATE NOCASE
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()

    return rows


# =====================================================
# LIBRARY QUERIES
# =====================================================
def get_all_stories_sorted(sort_type="alphabetical"):

    conn = get_connection()
    cursor = conn.cursor()

    if sort_type == "newest":
        order_clause = "ORDER BY stories.library_updated DESC"
    elif sort_type == "words":
        order_clause = "ORDER BY stories.word_count DESC"
    else:
        order_clause = "ORDER BY stories.title COLLATE NOCASE ASC"

    cursor.execute(f"""
    SELECT
        stories.title,
        stories.chapter_count,
        stories.library_updated,
        stories.word_count,
        stories.summary,
        stories.ao3_url,
        stories.author,
        stories.wattpad_url,
        stories.cover_url,
        stories.id,
        stories.extra_link_title,
        stories.extra_link_url,
        stories.extra_link2_title,
        stories.extra_link2_url,
        stories.playlist_url,
        stories.rating,
        stories.platform,
        stories.wattpad_reads,
        stories.wattpad_votes,
        stories.wattpad_comments,
        stories.ao3_hits,
        stories.ao3_kudos,
        stories.ao3_comments,
        stories.ao3_bookmarks
    FROM stories
    JOIN users ON stories.user_id = users.id
    WHERE (stories.is_dummy = 0 OR stories.is_dummy IS NULL)
    {order_clause}
    """)

    rows = cursor.fetchall()
    conn.close()

    return rows


def add_global_comment(user_id: int, story_id: int, content: str) -> int:
    """Inserts a global (non-chapter) comment. Returns new id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO comments (user_id, story_id, chapter_id, content)
        VALUES (?, ?, NULL, ?)
    """, (user_id, story_id, content))
    conn.commit()
    cid = cursor.lastrowid
    conn.close()
    return cid


def get_global_comments_for_story(story_id: int):
    """Returns only global (chapter_id IS NULL) comments, newest first."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.content, c.created_at, u.username, u.discord_id
        FROM comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.story_id = ? AND c.chapter_id IS NULL
        ORDER BY c.created_at DESC
    """, (story_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_comments_unified(story_id: int):
    """
    Returns ALL comments (global + chapter-specific) newest first.
    Each row: id, content, created_at, username, discord_id,
              chapter_number (None if global), chapter_title (None if global).
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.content, c.created_at,
               u.username, u.discord_id,
               ch.chapter_number, ch.chapter_title
        FROM comments c
        JOIN users u ON c.user_id = u.id
        LEFT JOIN chapters ch ON c.chapter_id = ch.id
        WHERE c.story_id = ?
        ORDER BY c.created_at DESC
    """, (story_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_global_comment_count_for_story(story_id: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM comments WHERE story_id = ? AND chapter_id IS NULL",
        (story_id,)
    )
    count = cursor.fetchone()["cnt"]
    conn.close()
    return count


# =====================================================
# FANART COMMENTS
# =====================================================

def add_fanart_comment(user_id: int, fanart_id: int, content: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO fanart_comments (user_id, fanart_id, content) VALUES (?, ?, ?)",
        (user_id, fanart_id, content)
    )
    conn.commit()
    cid = cursor.lastrowid
    conn.close()
    return cid


def get_fanart_comments(fanart_id: int) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT fc.id, fc.content, fc.created_at, u.username, u.discord_id
        FROM fanart_comments fc
        JOIN users u ON fc.user_id = u.id
        WHERE fc.fanart_id = ?
        ORDER BY fc.created_at DESC
    """, (fanart_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_fanart_comment_count(fanart_id: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM fanart_comments WHERE fanart_id = ?",
        (fanart_id,)
    )
    count = cursor.fetchone()["cnt"]
    conn.close()
    return count


# =====================================================
# FANART LIKES
# =====================================================

def toggle_fanart_like(user_id: int, fanart_id: int) -> bool:
    """
    Toggles a like for user on fanart_id.
    Returns True if now liked, False if now unliked.
    """
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM fanart_likes WHERE user_id = ? AND fanart_id = ?",
        (user_id, fanart_id)
    )
    exists = cursor.fetchone() is not None
    if exists:
        cursor.execute(
            "DELETE FROM fanart_likes WHERE user_id = ? AND fanart_id = ?",
            (user_id, fanart_id)
        )
        conn.commit()
        conn.close()
        return False
    else:
        cursor.execute(
            "INSERT INTO fanart_likes (user_id, fanart_id) VALUES (?, ?)",
            (user_id, fanart_id)
        )
        conn.commit()
        conn.close()
        return True


def user_has_liked_fanart(user_id: int, fanart_id: int) -> bool:
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM fanart_likes WHERE user_id = ? AND fanart_id = ?",
        (user_id, fanart_id)
    )
    result = cursor.fetchone() is not None
    conn.close()
    return result


def get_fanart_like_count(fanart_id: int) -> int:
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM fanart_likes WHERE fanart_id = ?",
        (fanart_id,)
    )
    count = cursor.fetchone()["cnt"]
    conn.close()
    return count


def get_liked_fanart_by_user(discord_id: str) -> list:
    """Returns all fanart pieces liked by a user, most recently liked first."""
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            f.id, f.title, f.description, f.image_url, f.created_at,
            s.title  AS story_title,
            s.id     AS story_id,
            f.user_id,
            uploader.discord_id,
            uploader.username,
            s.author,
            s.cover_url,
            f.tags, f.inspiration, f.scene_ref,
            f.artist_name, f.artist_link, f.canon_au,
            f.music_url, f.origin,
            fl.created_at AS liked_at
        FROM fanart_likes fl
        JOIN fanart f          ON fl.fanart_id  = f.id
        JOIN users liker       ON fl.user_id    = liker.id
        LEFT JOIN users uploader ON f.user_id   = uploader.id
        LEFT JOIN stories s    ON f.story_id    = s.id
        WHERE liker.discord_id = ?
        ORDER BY fl.created_at DESC
    """, (str(discord_id),))
    rows = cursor.fetchall()
    conn.close()
    return [fanart_row_to_dict(r) for r in rows]


# =====================================================
# CHARACTERS
# =====================================================

def add_character(user_id, story_id, name, gender, personality, image_url=None):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO characters (
        user_id,
        story_id,
        name,
        gender,
        personality,
        image_url
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        story_id,
        name,
        gender,
        personality,
        image_url
    ))

    conn.commit()
    character_id = cursor.lastrowid
    conn.close()
    _all_characters_cache.invalidate()
    return character_id

def get_story_id_by_title(title):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id
        FROM stories
        WHERE title = ?
    """, (title,))

    result = cursor.fetchone()
    conn.close()

    return result[0] if result else None

def get_characters_by_story_and_user(story_id, discord_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.id, c.name
        FROM characters c
        JOIN users u ON c.user_id = u.id
        WHERE c.story_id = ?
          AND u.discord_id = ?
        ORDER BY c.name COLLATE NOCASE
    """, (story_id, str(discord_id)))

    rows = cursor.fetchall()
    conn.close()
    return rows

def get_stories_by_discord_user(discord_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            s.title,
            s.chapter_count,
            s.library_updated,
            s.word_count,
            s.summary,
            s.ao3_url,
            s.author,
            s.wattpad_url,
            s.cover_url,
            s.id,
            s.extra_link_title,
            s.extra_link_url,
            s.extra_link2_title,
            s.extra_link2_url
        FROM stories s
        JOIN users u ON s.user_id = u.id
        WHERE u.discord_id = ?
          AND (s.is_dummy = 0 OR s.is_dummy IS NULL)
        ORDER BY s.title COLLATE NOCASE
    """, (str(discord_id),))

    rows = cursor.fetchall()
    conn.close()

    stories = []

    for r in rows:
        stories.append({
            "title": r[0],
            "chapters": r[1],
            "updated": r[2],
            "words": r[3],
            "summary": r[4],
            "ao3": r[5],
            "author": r[6],
            "wattpad": r[7],
            "cover": r[8],
            "id": r[9],
            "extra_link_title": r[10],
            "extra_link_url": r[11],
            "extra_link2_title": r[12],
            "extra_link2_url": r[13]
        })

    return stories

def get_characters_by_discord_user(discord_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT c.*
        FROM characters c
        JOIN stories s ON c.story_id = s.id
        JOIN users u ON s.user_id = u.id
        WHERE u.discord_id = ?
        ORDER BY RANDOM()
    """, (str(discord_id),))

    rows = cursor.fetchall()
    conn.close()

    return [character_to_dict(r) for r in rows]

def get_showcase_stats(discord_id):

    conn = get_connection()
    cursor = conn.cursor()

    # total stories + words
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(s.word_count), 0)
        FROM stories s
        JOIN users u ON s.user_id = u.id
        WHERE u.discord_id = ?
    """, (str(discord_id),))

    story_count, total_words = cursor.fetchone()

    # total characters
    cursor.execute("""
        SELECT COUNT(*)
        FROM characters c
        JOIN stories s ON c.story_id = s.id
        JOIN users u ON s.user_id = u.id
        WHERE u.discord_id = ?
    """, (str(discord_id),))

    char_count = cursor.fetchone()[0]

    conn.close()

    return {
        "stories": story_count or 0,
        "characters": char_count or 0,
        "words": total_words or 0
    }

def update_profile(
    discord_id,
    bio=None,
    pronouns=None,
    favorite_pokemon=None,
    image_url=None,
    favorite_fics=None,
    favorite_authors=None,
    hobbies=None,
    fun_fact=None
):

    conn = get_connection()
    cursor = conn.cursor()

    user_id = get_user_id(str(discord_id))
    if not user_id:
        conn.close()
        return

    # Get current profile first
    current = get_profile_by_discord_id(discord_id)

    bio = bio if bio is not None else current["bio"]
    pronouns = pronouns if pronouns is not None else current["pronouns"]
    favorite_pokemon = (
        favorite_pokemon if favorite_pokemon is not None else current["favorite_pokemon"]
    )
    image_url = image_url if image_url is not None else current["image_url"]

    favorite_fics = favorite_fics if favorite_fics is not None else current["favorite_fics"]
    favorite_authors = favorite_authors if favorite_authors is not None else current["favorite_authors"]
    hobbies = hobbies if hobbies is not None else current["hobbies"]
    fun_fact = fun_fact if fun_fact is not None else current["fun_fact"]

    cursor.execute("""
    INSERT INTO profiles (
        user_id,
        bio,
        pronouns,
        favorite_pokemon,
        image_url,
        favorite_fics,
        favorite_authors,
        hobbies,
        fun_fact
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(user_id)
    DO UPDATE SET
        bio = excluded.bio,
        pronouns = excluded.pronouns,
        favorite_pokemon = excluded.favorite_pokemon,
        image_url = excluded.image_url,
        favorite_fics = excluded.favorite_fics,
        favorite_authors = excluded.favorite_authors,
        hobbies = excluded.hobbies,
        fun_fact = excluded.fun_fact
    """, (
        user_id,
        bio,
        pronouns,
        favorite_pokemon,
        image_url,
        favorite_fics,
        favorite_authors,
        hobbies,
        fun_fact
    ))

    conn.commit()
    conn.close()

def get_profile_by_discord_id(discord_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        p.bio,
        p.pronouns,
        p.favorite_pokemon,
        p.image_url,
        p.favorite_fics,
        p.favorite_authors,
        p.hobbies,
        p.fun_fact
    FROM profiles p
    JOIN users u ON p.user_id = u.id
    WHERE u.discord_id = ?
    """, (str(discord_id),))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            "bio": None,
            "pronouns": None,
            "favorite_pokemon": None,
            "image_url": None,
            "favorite_fics": None,
            "favorite_authors": None,
            "hobbies": None,
            "fun_fact": None
        }

    return {
        "bio": row[0],
        "pronouns": row[1],
        "favorite_pokemon": row[2],
        "image_url": row[3],
        "favorite_fics": row[4],
        "favorite_authors": row[5],
        "hobbies": row[6],
        "fun_fact": row[7]
    }

def get_all_showcase_authors():

    conn = get_connection()
    cursor = conn.cursor()

    # Include ALL registered users, not just those with stories
    cursor.execute("""
    SELECT DISTINCT discord_id
    FROM users
    WHERE discord_id IS NOT NULL
    """)

    rows = cursor.fetchall()
    conn.close()

    return [int(r[0]) for r in rows]

def get_all_characters_random():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT *
    FROM characters
    ORDER BY RANDOM()
    """)

    rows = cursor.fetchall()
    conn.close()

    return [character_to_dict(r) for r in rows]

def add_dummy_story(user_id: int, display_name: str) -> int:
    """Create a private DNE story for a user. Returns the new story_id."""
    conn   = get_connection()
    cursor = conn.cursor()
    title  = f"{display_name}'s Private Collection"
    cursor.execute("""
        INSERT INTO stories (user_id, title, author, chapter_count, word_count,
                             library_updated, is_dummy)
        VALUES (?, ?, ?, 0, 0, datetime('now'), 1)
    """, (user_id, title, display_name))
    story_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return story_id


def get_dummy_story(user_id: int):
    """Return the DNE story row for a user, or None."""
    conn = get_connection()
    row  = conn.execute(
        "SELECT * FROM stories WHERE user_id = ? AND is_dummy = 1 LIMIT 1",
        (user_id,)
    ).fetchone()
    conn.close()
    return row


def swap_character_story(character_id: int, new_story_id: int):
    """Move a character to a different story."""
    conn = get_connection()
    conn.execute(
        "UPDATE characters SET story_id = ? WHERE id = ?",
        (new_story_id, character_id)
    )
    conn.commit()
    conn.close()


def get_story_by_character(character_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT s.*
    FROM stories s
    JOIN characters c ON c.story_id = s.id
    WHERE c.id = ?
    """, (character_id,))

    row = cursor.fetchone()
    conn.close()

    return row

def get_all_characters():
    cached = _all_characters_cache.get()
    if cached is not None:
        return cached

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            c.id,
            c.name,
            s.title,
            s.author,
            COALESCE(s.is_dummy, 0) AS is_dummy
        FROM characters c
        LEFT JOIN stories s ON c.story_id = s.id
        ORDER BY c.name COLLATE NOCASE
    """)

    rows = cursor.fetchall()
    conn.close()

    characters = []

    for r in rows:
        characters.append({
            "id": r["id"],
            "name": r["name"],
            "story_title": r["title"],
            "author": r["author"],
            "is_dummy": bool(r["is_dummy"]),
        })

    _all_characters_cache.set(characters)
    return characters

def get_character_by_id(character_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM characters
        WHERE id = ?
    """, (character_id,))

    row = cursor.fetchone()
    conn.close()

    return character_to_dict(row)


def get_characters_by_ids(character_ids):
    """Fetch multiple characters in a single query instead of one-by-one."""
    if not character_ids:
        return []
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" * len(character_ids))
    cursor.execute(f"SELECT * FROM characters WHERE id IN ({placeholders})",
                   list(character_ids))
    rows = cursor.fetchall()
    conn.close()
    # Return in the same order as the input IDs
    by_id = {r["id"]: character_to_dict(r) for r in rows}
    return [by_id[cid] for cid in character_ids if cid in by_id]


def get_discord_id_by_story(story_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.discord_id
        FROM stories s
        JOIN users u ON s.user_id = u.id
        WHERE s.id = ?
    """, (story_id,))

    result = cursor.fetchone()
    conn.close()

    return result[0] if result else None

def fanart_title_exists_for_user(user_id, title):
    """Return True if this user already has a fanart piece with this title."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM fanart WHERE user_id = ? AND LOWER(title) = LOWER(?) LIMIT 1",
        (user_id, title)
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def add_fanart(user_id, title, description, image_url, created_at, story_id=None):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO fanart (
        user_id,
        story_id,
        title,
        description,
        image_url,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        story_id,  # None becomes NULL in SQLite
        title,
        description,
        image_url,
        created_at
    ))

    conn.commit()

    fanart_id = cursor.lastrowid

    conn.close()
    return fanart_id

def get_fanart_by_discord_user(discord_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            f.id,
            f.title,
            f.description,
            f.image_url,
            f.created_at,
            s.title AS story_title,
            f.story_id,
            f.user_id,
            u.discord_id,
            u.username AS author,
            s.cover_url,
            f.tags,
            f.inspiration,
            f.scene_ref,
            f.artist_name,
            f.artist_link,
            f.canon_au,
            f.music_url,
            f.origin
        FROM fanart f
        JOIN users u ON f.user_id = u.id
        LEFT JOIN stories s ON f.story_id = s.id
        WHERE u.discord_id = ?
        ORDER BY f.id DESC
    """, (str(discord_id),))

    rows = cursor.fetchall()
    conn.close()

    return [fanart_row_to_dict(r) for r in rows]

def get_fanart_by_story(story_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        f.id,
        f.title,
        f.description,
        f.image_url,
        f.created_at,
        s.title AS story_title,
        s.id AS story_id,
        s.author,
        s.cover_url,
        f.tags,
        f.inspiration,
        f.scene_ref,
        f.artist_name,
        f.artist_link,
        f.canon_au,
        f.music_url,
        f.origin
    FROM fanart f
    JOIN stories s ON f.story_id = s.id
    WHERE s.id = ?
    ORDER BY f.id DESC
    """, (story_id,))

    rows = cursor.fetchall()
    conn.close()

    return [fanart_row_to_dict(r) for r in rows]

def get_fanart_by_character(character_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        f.id,
        f.title,
        f.description,
        f.image_url,
        f.created_at,
        s.title AS story_title,
        f.story_id,
        u.username,
        s.cover_url,
        f.tags,
        f.inspiration,
        f.scene_ref,
        f.artist_name,
        f.artist_link,
        f.canon_au,
        f.music_url,
        f.origin
    FROM fanart f
    JOIN fanart_characters fc ON f.id = fc.fanart_id
    LEFT JOIN stories s ON f.story_id = s.id
    LEFT JOIN users u ON f.user_id = u.id
    WHERE fc.character_id = ?
    ORDER BY f.id DESC
    """, (character_id,))

    rows = cursor.fetchall()
    conn.close()

    return [fanart_row_to_dict(r) for r in rows]

def get_fanart_characters(fanart_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT c.id, c.name
    FROM fanart_characters fc
    JOIN characters c ON fc.character_id = c.id
    WHERE fc.fanart_id = ?
    ORDER BY c.name COLLATE NOCASE
    """, (fanart_id,))

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r["id"],
            "name": r["name"]
        }
        for r in rows
    ]

def get_fanart_ships(fanart_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT s.id, s.name
    FROM fanart_ships fs
    JOIN ships s ON fs.ship_id = s.id
    WHERE fs.fanart_id = ?
    """, (fanart_id,))

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r["id"],
            "name": r["name"]
        }
        for r in rows
    ]

def clear_fanart_characters(fanart_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    DELETE FROM fanart_characters
    WHERE fanart_id = ?
    """, (fanart_id,))

    conn.commit()
    conn.close()

def add_fanart_character(fanart_id, character_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO fanart_characters (
        fanart_id,
        character_id
    )
    VALUES (?, ?)
    """, (fanart_id, character_id))

    conn.commit()
    conn.close()


def update_fanart_description(fanart_id, description):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE fanart
    SET description = ?
    WHERE id = ?
    """, (description, fanart_id))

    conn.commit()
    conn.close()

def delete_fanart(fanart_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    DELETE FROM fanart
    WHERE id = ?
    """, (fanart_id,))

    conn.commit()
    conn.close()

def create_ship(user_id, ship_name, character_ids):

    conn = get_connection()
    cursor = conn.cursor()

    # Sort character IDs for consistent duplicate detection
    char_ids_sorted = sorted(character_ids)

    # Check if any existing ship has the exact same set of characters
    cursor.execute("""
    SELECT s.id, s.name
    FROM ships s
    JOIN ship_characters sc ON sc.ship_id = s.id
    GROUP BY s.id
    HAVING COUNT(sc.character_id) = ?
    """, (len(char_ids_sorted),))

    candidate_ships = cursor.fetchall()

    for candidate in candidate_ships:
        sid = candidate["id"]
        cursor.execute("""
        SELECT character_id FROM ship_characters WHERE ship_id = ?
        ORDER BY character_id
        """, (sid,))
        existing_chars = sorted([r["character_id"] for r in cursor.fetchall()])
        if existing_chars == char_ids_sorted:
            conn.close()
            return None  # Duplicate pairing

    cursor.execute("""
    INSERT INTO ships (user_id, name)
    VALUES (?, ?)
    """, (user_id, ship_name))

    ship_id = cursor.lastrowid

    for cid in char_ids_sorted:
        cursor.execute("""
        INSERT INTO ship_characters (ship_id, character_id)
        VALUES (?, ?)
        """, (ship_id, cid))

    conn.commit()
    conn.close()
    _all_ships_cache.invalidate()

    return ship_id


def get_ship_by_id(ship_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, user_id FROM ships WHERE id = ?", (ship_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    cursor.execute("""
    SELECT c.name, c.id
    FROM ship_characters sc
    JOIN characters c ON sc.character_id = c.id
    WHERE sc.ship_id = ?
    ORDER BY c.name COLLATE NOCASE
    """, (ship_id,))

    chars = cursor.fetchall()
    conn.close()

    return {
        "id": row["id"],
        "name": row["name"],
        "user_id": row["user_id"],
        "characters": [{"id": c["id"], "name": c["name"]} for c in chars]
    }


def rename_ship(ship_id, new_name):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE ships SET name = ? WHERE id = ?", (new_name, ship_id))
    conn.commit()
    conn.close()


def delete_ship(ship_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM ships WHERE id = ?", (ship_id,))
    conn.commit()
    conn.close()
    _all_ships_cache.invalidate()


def get_ships_by_user(user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT s.id, s.name
    FROM ships s
    WHERE s.user_id = ?
    ORDER BY s.name COLLATE NOCASE
    """, (user_id,))

    ships = cursor.fetchall()
    result = []

    for r in ships:
        sid = r["id"]
        ship_name = r["name"]

        cursor.execute("""
        SELECT c.name
        FROM ship_characters sc
        JOIN characters c ON sc.character_id = c.id
        WHERE sc.ship_id = ?
        ORDER BY c.name COLLATE NOCASE
        """, (sid,))

        chars = [row["name"] for row in cursor.fetchall()]
        result.append({"id": sid, "name": ship_name, "characters": chars})

    conn.close()
    return result

def clear_fanart_ships(fanart_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    DELETE FROM fanart_ships
    WHERE fanart_id = ?
    """, (fanart_id,))

    conn.commit()
    conn.close()

def add_fanart_ship(fanart_id, ship_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO fanart_ships (fanart_id, ship_id)
    VALUES (?, ?)
    """, (fanart_id, ship_id))

    conn.commit()
    conn.close()

def get_fanart_by_id(fanart_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            f.id,
            f.title,
            f.description,
            f.image_url,
            f.created_at,
            s.title AS story_title,
            f.story_id,
            u.username,
            s.cover_url,
            f.tags,
            f.inspiration,
            f.scene_ref,
            f.artist_name,
            f.artist_link,
            f.canon_au,
            f.music_url,
            f.origin
        FROM fanart f
        LEFT JOIN stories s ON f.story_id = s.id
        LEFT JOIN users u ON s.user_id = u.id
        WHERE f.id = ?
    """, (fanart_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return fanart_row_to_dict(row)

def get_library_reader_score(discord_id):

    conn = get_connection()
    cursor = conn.cursor()

    user_id = get_user_id(str(discord_id))

    cursor.execute("SELECT SUM(chapter_count) FROM stories")
    total_chapters = cursor.fetchone()[0] or 0

    cursor.execute("""
        SELECT SUM(completed_chapters)
        FROM progress
        WHERE user_id = ?
    """, (user_id,))

    read_chapters = cursor.fetchone()[0] or 0

    conn.close()

    if total_chapters == 0:
        percent = 0
    else:
        percent = int((read_chapters / total_chapters) * 100)

    return percent, read_chapters, total_chapters

def get_characters_by_story(story_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT *
    FROM characters
    WHERE story_id = ?
    ORDER BY id ASC
    """, (story_id,))

    rows = cursor.fetchall()
    conn.close()

    return [character_to_dict(r) for r in rows]

def update_fanart_tags(fanart_id, tags):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE fanart
    SET tags = ?
    WHERE id = ?
    """, (tags, fanart_id))

    conn.commit()
    conn.close()

def update_fanart_inspiration(fanart_id, inspiration):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE fanart
    SET inspiration = ?
    WHERE id = ?
    """, (inspiration, fanart_id))

    conn.commit()
    conn.close()



def update_fanart_scene_ref(fanart_id, scene_ref):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE fanart
    SET scene_ref = ?
    WHERE id = ?
    """, (scene_ref, fanart_id))

    conn.commit()
    conn.close()


def update_fanart_artist_credit(fanart_id, artist_name, artist_link):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE fanart
    SET artist_name = ?, artist_link = ?
    WHERE id = ?
    """, (artist_name or None, artist_link or None, fanart_id))

    conn.commit()
    conn.close()


def update_fanart_music_url(fanart_id, music_url):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE fanart SET music_url = ? WHERE id = ?", (music_url, fanart_id))
    conn.commit()
    conn.close()


def update_fanart_origin(fanart_id, origin):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE fanart SET origin = ? WHERE id = ?", (origin, fanart_id))
    conn.commit()
    conn.close()


def update_fanart_canon_au(fanart_id, canon_au):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE fanart
    SET canon_au = ?
    WHERE id = ?
    """, (canon_au, fanart_id))

    conn.commit()
    conn.close()

def get_fanart_by_tag(tag):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM fanart
        WHERE tags LIKE ?
        ORDER BY id DESC
    """, (f"%{tag.lower()}%",))

    rows = cursor.fetchall()
    conn.close()

    return [fanart_row_to_dict(r) for r in rows]

def search_fanart(tag=None, character=None, ship=None, story=None, name=None):

    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT DISTINCT
        f.id,
        f.title,
        f.description,
        f.image_url,
        f.created_at,
        s.title AS story_title,
        f.story_id,
        f.user_id,
        u.discord_id,
        u.username,
        s.cover_url,
        s.author,
        f.tags,
        f.inspiration,
        f.scene_ref,
        f.artist_name,
        f.artist_link,
        f.canon_au,
        f.music_url,
        f.origin
    FROM fanart f
    LEFT JOIN stories s ON f.story_id = s.id
    LEFT JOIN users u ON f.user_id = u.id
    LEFT JOIN fanart_characters fc ON f.id = fc.fanart_id
    LEFT JOIN characters c ON fc.character_id = c.id
    LEFT JOIN fanart_ships fs ON f.id = fs.fanart_id
    LEFT JOIN ships sh ON fs.ship_id = sh.id
    WHERE 1=1
    """

    params = []

    # -------------------------------------------------
    # TAG FILTER
    # -------------------------------------------------

    if tag:
        query += " AND LOWER(f.tags) LIKE ?"
        params.append(f"%{tag.lower()}%")

    # -------------------------------------------------
    # CHARACTER FILTER
    # -------------------------------------------------

    if character:
        query += " AND LOWER(c.name) LIKE ?"
        params.append(f"%{character.lower()}%")

    # -------------------------------------------------
    # SHIP FILTER
    # -------------------------------------------------

    if ship:
        query += " AND LOWER(sh.name) LIKE ?"
        params.append(f"%{ship.lower()}%")

    # -------------------------------------------------
    # STORY FILTER
    # -------------------------------------------------

    if story:
        query += " AND LOWER(s.title) LIKE ?"
        params.append(f"%{story.lower()}%")

    # -------------------------------------------------
# TITLE FILTER
# -------------------------------------------------

    if name:
        query += " AND LOWER(f.title) LIKE ?"
        params.append(f"%{name.lower()}%")

    query += " ORDER BY f.created_at DESC"

    cursor.execute(query, params)

    rows = cursor.fetchall()
    conn.close()

    return [fanart_row_to_dict(r) for r in rows]

def update_fanart_story(fanart_id, story_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE fanart
    SET story_id = ?
    WHERE id = ?
    """, (story_id, fanart_id))

    conn.commit()
    conn.close()

def get_all_fanart_tags():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT tags FROM fanart
    WHERE tags IS NOT NULL
    """)

    rows = cursor.fetchall()
    conn.close()

    tags = set()

    for r in rows:

        tag_string = r[0]

        for tag in tag_string.split(","):
            tag = tag.strip()

            if tag:
                tags.add(tag)

    return sorted(tags)

def get_random_fanart():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        f.id,
        f.title,
        f.description,
        f.image_url,
        f.created_at,
        s.title AS story_title,
        f.story_id,
        f.user_id,
        u.username,
        u.discord_id,
        s.cover_url,
        f.tags,
        f.inspiration,
        f.scene_ref,
        f.artist_name,
        f.artist_link,
        f.canon_au,
        f.music_url,
        f.origin
    FROM fanart f
    LEFT JOIN stories s ON f.story_id = s.id
    LEFT JOIN users u ON f.user_id = u.id
    ORDER BY RANDOM()
    """)

    rows = cursor.fetchall()
    conn.close()

    return [fanart_row_to_dict(r) for r in rows]

def get_fanart_character_names(fanart_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT c.name
    FROM fanart_characters fc
    JOIN characters c ON fc.character_id = c.id
    WHERE fc.fanart_id = ?
    """, (fanart_id,))

    rows = cursor.fetchall()
    conn.close()

    return [r[0] for r in rows]

def get_ships_by_story(story_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT DISTINCT s.id, s.name
    FROM ships s
    JOIN ship_characters sc ON sc.ship_id = s.id
    JOIN characters c ON sc.character_id = c.id
    WHERE c.story_id = ?
    ORDER BY s.name COLLATE NOCASE
    """, (story_id,))

    ships = cursor.fetchall()

    result = []

    for r in ships:

        sid = r["id"]
        ship_name = r["name"]

        cursor.execute("""
        SELECT c.name
        FROM ship_characters sc
        JOIN characters c ON sc.character_id = c.id
        WHERE sc.ship_id = ?
        """, (sid,))

        chars = [row["name"] for row in cursor.fetchall()]

        result.append({
            "id": sid,
            "name": ship_name,
            "characters": chars
        })

    conn.close()
    return result

def add_story_tags(cursor, story_id, tags):

    for tag in tags:

        tag = tag.strip().lower()

        if not tag:
            continue

        # Create tag if it doesn't exist
        cursor.execute("""
        INSERT OR IGNORE INTO tags (name)
        VALUES (?)
        """, (tag,))

        # Get tag ID
        cursor.execute("""
        SELECT id FROM tags
        WHERE name = ?
        """, (tag,))

        row = cursor.fetchone()

        if not row:
            continue

        tag_id = row[0]

        # Link story ↔ tag
        cursor.execute("""
        INSERT OR IGNORE INTO story_tags (story_id, tag_id)
        VALUES (?, ?)
        """, (story_id, tag_id))

def get_story_tags(story_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT t.name
    FROM story_tags st
    JOIN tags t ON st.tag_id = t.id
    WHERE st.story_id = ?
    ORDER BY t.name COLLATE NOCASE
    """, (story_id,))

    rows = cursor.fetchall()
    conn.close()

    return [r[0] for r in rows]

def get_stories_by_tag(tag):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT DISTINCT s.*
    FROM stories s
    JOIN story_tags st ON s.id = st.story_id
    JOIN tags t ON st.tag_id = t.id
    WHERE LOWER(t.name) = LOWER(?)
    ORDER BY s.title COLLATE NOCASE
    """, (tag,))

    rows = cursor.fetchall()
    conn.close()

    return rows

def get_top_tags(limit=4):
    """Return the most-used tags across all stories, ordered by story count descending."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT t.name, COUNT(st.story_id) AS story_count
    FROM tags t
    JOIN story_tags st ON t.id = st.tag_id
    GROUP BY t.id
    ORDER BY story_count DESC, t.name COLLATE NOCASE
    LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    return [r[0] for r in rows]

def get_all_story_tags():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT name
    FROM tags
    ORDER BY name COLLATE NOCASE
    """)

    rows = cursor.fetchall()
    conn.close()

    return [r[0] for r in rows]

def get_stories_by_tags(tags):

    conn = get_connection()
    cursor = conn.cursor()

    placeholders = ",".join("?" for _ in tags)

    query = f"""
    SELECT DISTINCT
        s.title,
        s.chapter_count,
        s.library_updated,
        s.word_count,
        s.summary,
        s.ao3_url,
        s.author,
        s.wattpad_url,
        s.cover_url,
        s.id,
        s.extra_link_title,
        s.extra_link_url,
        s.extra_link2_title,
        s.extra_link2_url,
        s.playlist_url,
        s.rating
    FROM stories s
    JOIN story_tags st ON s.id = st.story_id
    JOIN tags t ON st.tag_id = t.id
    WHERE LOWER(t.name) IN ({placeholders})
    GROUP BY s.id
    HAVING COUNT(DISTINCT t.name) = ?
    ORDER BY s.title COLLATE NOCASE
    """

    params = [tag.lower() for tag in tags]
    params.append(len(tags))

    cursor.execute(query, params)

    rows = cursor.fetchall()
    conn.close()

    return rows

def get_tags_by_story(story_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT t.name
    FROM tags t
    JOIN story_tags st ON st.tag_id = t.id
    WHERE st.story_id = ?
    ORDER BY t.name COLLATE NOCASE
    """, (story_id,))

    rows = cursor.fetchall()
    conn.close()

    return [r[0] for r in rows]

def get_all_ships():
    cached = _all_ships_cache.get()
    if cached is not None:
        return cached

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT s.id, s.name
    FROM ships s
    ORDER BY s.name COLLATE NOCASE
    """)

    ships = cursor.fetchall()

    result = []

    for r in ships:

        ship_id = r["id"]
        ship_name = r["name"]

        cursor.execute("""
        SELECT c.name
        FROM ship_characters sc
        JOIN characters c ON sc.character_id = c.id
        WHERE sc.ship_id = ?
        ORDER BY c.name COLLATE NOCASE
        """, (ship_id,))

        chars = [row["name"] for row in cursor.fetchall()]

        result.append({
            "id": ship_id,
            "name": ship_name,
            "characters": chars
        })

    conn.close()

    _all_ships_cache.set(result)
    return result

def get_all_fanart_titles():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        f.id,
        f.title,
        u.discord_id
    FROM fanart f
    LEFT JOIN users u ON f.user_id = u.id
    ORDER BY f.title COLLATE NOCASE
    """)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r["id"],
            "title": r["title"],
            "discord_id": r["discord_id"]
        }
        for r in rows
    ]
    
def get_favorite_characters(user_id, story_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT fc.character_id, c.name
    FROM favorite_characters fc
    JOIN characters c ON c.id = fc.character_id
    WHERE fc.user_id = ?
    AND fc.story_id = ?
    """, (user_id, story_id))

    rows = cursor.fetchall()
    conn.close()

    return [{"id": r["character_id"], "name": r["name"]} for r in rows]

def add_favorite_character(user_id, story_id, character_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO favorite_characters (
        user_id,
        story_id,
        character_id,
        created_at
    )
    VALUES (?, ?, ?, datetime('now'))
    """, (user_id, story_id, character_id))

    conn.commit()
    conn.close()


def remove_favorite_character(user_id, character_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    DELETE FROM favorite_characters
    WHERE user_id = ?
    AND character_id = ?
    """, (user_id, character_id))

    conn.commit()
    conn.close()

def get_character_fav_count(character_id: int) -> int:
    """Returns how many users have favorited a given character."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM favorite_characters WHERE character_id = ?",
        (character_id,)
    )
    count = cursor.fetchone()["cnt"]
    conn.close()
    return count


def is_favorite_character(user_id, character_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 1
    FROM favorite_characters
    WHERE user_id = ?
    AND character_id = ?
    """, (user_id, character_id))

    result = cursor.fetchone()
    conn.close()

    return result is not None

def update_story_badge(user_id, story_id):

    progress = get_story_progress(user_id, story_id) or 0
    chapters = get_chapters_by_story(story_id)

    total = len(chapters)

    # One-shots have no chapter rows — fall back to chapter_count on the story
    if total == 0:
        story = get_story_by_id(story_id)
        total = story["chapter_count"] if story else 0

    if total == 0:
        return

    threshold = max(1, int(total * 0.8))
    if progress >= threshold:
        add_story_badge(user_id, story_id)
    else:
        remove_story_badge(user_id, story_id)

def add_story_badge(user_id, story_id):

    conn = get_connection()
    conn.execute(
        """
        INSERT OR IGNORE INTO story_badges (user_id, story_id, earned_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        """,
        (user_id, story_id)
    )
    conn.commit()
    conn.close()

def remove_story_badge(user_id, story_id):

    conn = get_connection()
    conn.execute(
        "DELETE FROM story_badges WHERE user_id=? AND story_id=?",
        (user_id, story_id)
    )
    conn.commit()
    conn.close()

def has_story_badge(user_id, story_id):

    conn = get_connection()

    row = conn.execute(
        "SELECT 1 FROM story_badges WHERE user_id=? AND story_id=?",
        (user_id, story_id)
    ).fetchone()

    conn.close()

    return bool(row)

def count_user_badges(user_id):

    conn = get_connection()

    row = conn.execute(
        "SELECT COUNT(*) FROM story_badges WHERE user_id=?",
        (user_id,)
    ).fetchone()

    conn.close()

    return row[0]

def get_reader_badge_count(discord_id):

    uid = get_user_id(str(discord_id))

    if not uid:
        return 0

    conn = get_connection()

    row = conn.execute(
        "SELECT COUNT(*) FROM story_badges WHERE user_id=?",
        (uid,)
    ).fetchone()

    conn.close()

    return row[0]

# =====================================================
# SHINY CHARMS
# =====================================================

def has_shiny_charm(user_id, story_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM story_shiny_charms WHERE user_id=? AND story_id=?",
        (user_id, story_id)
    ).fetchone()
    conn.close()
    return bool(row)


def add_shiny_charm(user_id, story_id):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO story_shiny_charms (user_id, story_id, earned_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
        (user_id, story_id)
    )
    conn.commit()
    conn.close()


def remove_shiny_charm(user_id, story_id):
    conn = get_connection()
    conn.execute(
        "DELETE FROM story_shiny_charms WHERE user_id=? AND story_id=?",
        (user_id, story_id)
    )
    conn.commit()
    conn.close()


def get_user_library_score(user_id):
    """Returns fraction (0.0–1.0) of total library chapters this user has read."""
    conn = get_connection()
    total_row = conn.execute("SELECT SUM(chapter_count) FROM stories WHERE chapter_count > 0").fetchone()
    total = total_row[0] or 0
    if total == 0:
        conn.close()
        return 0.0
    read_row = conn.execute(
        "SELECT SUM(completed_chapters) FROM progress WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    read = read_row[0] or 0
    conn.close()
    return min(read / total, 1.0)


def update_shiny_charm(user_id, story_id, discord_id):
    """
    Award or remove the shiny charm based on 100% completion + author rules.

    Returns one of:
        'earned'              — charm newly awarded (reader or qualifying author)
        'author_no_charm'     — author at 100% but library score < 80%
        'author_earned_charm' — author earned charm via ≥80% library score
        None                  — no change
    """
    progress = get_story_progress(user_id, story_id) or 0
    chapters = get_chapters_by_story(story_id)
    total = len(chapters)
    if total == 0:
        story = get_story_by_id(story_id)
        total = story["chapter_count"] if story else 0
    if total == 0:
        return None

    had_charm = has_shiny_charm(user_id, story_id)

    if progress >= total:
        story_owner = get_discord_id_by_story(story_id)
        is_author = (str(story_owner) == str(discord_id))

        if is_author:
            score = get_user_library_score(user_id)
            if score >= 0.80:
                add_shiny_charm(user_id, story_id)
                if not had_charm:
                    return 'author_earned_charm'
            else:
                remove_shiny_charm(user_id, story_id)
                if not had_charm:
                    return 'author_no_charm'
        else:
            add_shiny_charm(user_id, story_id)
            if not had_charm:
                return 'earned'
    else:
        remove_shiny_charm(user_id, story_id)

    return None


def has_shiny_charm_for_character(user_id, character_id):
    """Check if the user has a shiny charm for the story that owns this character."""
    conn = get_connection()
    row = conn.execute("""
        SELECT 1 FROM story_shiny_charms sc
        JOIN characters c ON c.story_id = sc.story_id
        WHERE sc.user_id = ? AND c.id = ?
    """, (user_id, character_id)).fetchone()
    conn.close()
    return bool(row)


def get_mc_count_for_story(story_id: int) -> int:
    conn = get_connection()
    row  = conn.execute(
        "SELECT COUNT(*) AS cnt FROM characters WHERE story_id = ? AND is_main_character = 1",
        (story_id,)
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def set_character_mc(character_id: int, is_main: bool):
    conn = get_connection()
    conn.execute(
        "UPDATE characters SET is_main_character = ? WHERE id = ?",
        (1 if is_main else 0, character_id),
    )
    conn.commit()
    conn.close()


def get_mc_characters_for_user(user_id: int) -> list:
    """Returns all characters marked as main for the given DB user_id."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT c.id, c.name, s.id AS story_id, s.title AS story_title
        FROM characters c
        JOIN stories s ON c.story_id = s.id
        WHERE s.user_id = ? AND c.is_main_character = 1
        ORDER BY s.title, c.name
    """, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_setmc_last_input(user_id: int) -> list:
    """Returns the last names the user typed into /char setmc (up to 4)."""
    import json
    conn = get_connection()
    row  = conn.execute(
        "SELECT setmc_last_input FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if not row or not row["setmc_last_input"]:
        return []
    try:
        return json.loads(row["setmc_last_input"])
    except Exception:
        return []


def save_setmc_last_input(user_id: int, names: list):
    """Persists the names the user typed into /char setmc."""
    import json
    conn = get_connection()
    conn.execute(
        "UPDATE users SET setmc_last_input = ? WHERE id = ?",
        (json.dumps(names[:4]), user_id),
    )
    conn.commit()
    conn.close()


def get_ctc_main_character(user_id: int):
    """Returns the character dict set as the user's CTC main character, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT ctc_main_character_id FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if not row or not row["ctc_main_character_id"]:
        return None
    return get_character_by_id(row["ctc_main_character_id"])


def set_ctc_main_character(user_id: int, character_id: int | None):
    """Sets (or clears) the user's CTC main character."""
    conn = get_connection()
    conn.execute(
        "UPDATE users SET ctc_main_character_id = ? WHERE id = ?",
        (character_id, user_id),
    )
    conn.commit()
    conn.close()


def get_author_metal_count(discord_id):

    conn = get_connection()
    cur = conn.cursor()

    uid = get_user_id(str(discord_id))

    cur.execute("""
        SELECT id, chapter_count
        FROM stories
        WHERE user_id = ?
    """, (uid,))

    stories = cur.fetchall()

    metal_count = 0

    for row in stories:

        story_id = row["id"]
        chapter_count = row["chapter_count"]

        # total readers
        cur.execute("""
            SELECT COUNT(DISTINCT user_id)
            FROM progress
            WHERE story_id = ?
        """, (story_id,))

        total_readers = cur.fetchone()[0]

        if total_readers == 0:
            continue

        # finished readers
        cur.execute("""
            SELECT COUNT(DISTINCT user_id)
            FROM progress
            WHERE story_id = ?
            AND completed_chapters >= ?
        """, (story_id, chapter_count))

        finished = cur.fetchone()[0]

        completion_rate = finished / total_readers

        if completion_rate >= 0.8:
            metal_count += 1

    conn.close()

    return metal_count

# =====================================================
# STORY RIBBONS (80% READERS)
# =====================================================

def get_story_ribbon_count(story_id):

    conn = get_connection()
    cursor = conn.cursor()

    # get chapter count
    cursor.execute("""
        SELECT chapter_count
        FROM stories
        WHERE id = ?
    """, (story_id,))

    row = cursor.fetchone()

    if not row:
        conn.close()
        return 0

    chapter_count = row["chapter_count"]

    # calculate 80% threshold
    threshold = int(chapter_count * 0.8)

    cursor.execute("""
        SELECT COUNT(DISTINCT user_id)
        FROM progress
        WHERE story_id = ?
        AND completed_chapters >= ?
    """, (story_id, threshold))

    ribbons = cursor.fetchone()[0]

    conn.close()

    return ribbons

# =====================================================
# TOP FAVORITE CHARACTERS
# =====================================================

def get_top_story_characters(story_id, limit=2):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            c.id,
            c.name,
            COUNT(fc.character_id) AS votes
        FROM characters c
        LEFT JOIN favorite_characters fc
            ON fc.character_id = c.id
        WHERE c.story_id = ?
        GROUP BY c.id
        ORDER BY votes DESC, c.id ASC
        LIMIT ?
    """, (story_id, limit))

    rows = cursor.fetchall()

    # total voters (for percentage math)
    cursor.execute("""
        SELECT COUNT(DISTINCT user_id)
        FROM favorite_characters
        WHERE story_id = ?
    """, (story_id,))

    total_votes = cursor.fetchone()[0] or 1

    conn.close()

    results = []

    for r in rows:

        percent = int((r["votes"] / total_votes) * 100)

        results.append({
            "id": r["id"],
            "name": r["name"],
            "votes": r["votes"],
            "percent": percent
        })

    return results

# =====================================================
# GET FANART OWNED BY USER (with ownership check)
# =====================================================
def get_fanart_by_id_owned(fanart_id, discord_id):
    """Returns fanart only if the given discord_id owns it."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT f.id, f.title, f.tags, f.story_id, u.discord_id
        FROM fanart f
        JOIN users u ON f.user_id = u.id
        WHERE f.id = ? AND u.discord_id = ?
    """, (fanart_id, str(discord_id)))

    row = cursor.fetchone()
    conn.close()
    return row


def delete_fanart_full(fanart_id):
    """Delete fanart and all related tags, characters, ships."""
    conn = get_connection()
    cursor = conn.cursor()
    # CASCADE handles fanart_characters and fanart_ships via FK
    cursor.execute("DELETE FROM fanart WHERE id = ?", (fanart_id,))
    conn.commit()
    conn.close()


# =====================================================
# GET ALL FAVORITES FOR A USER (with story context)
# =====================================================
def get_all_favorites_for_user(user_id):
    """
    Returns list of dicts: {character_id, character_name, story_id, story_title}
    Only stories that have at least one favorite are included.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            fc.character_id,
            c.name AS character_name,
            s.id   AS story_id,
            s.title AS story_title
        FROM favorite_characters fc
        JOIN characters c ON fc.character_id = c.id
        JOIN stories    s ON fc.story_id     = s.id
        WHERE fc.user_id = ?
        ORDER BY s.title COLLATE NOCASE, c.name COLLATE NOCASE
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "character_id":   r["character_id"],
            "character_name": r["character_name"],
            "story_id":       r["story_id"],
            "story_title":    r["story_title"]
        }
        for r in rows
    ]


def get_user_fanart_for_autocomplete(discord_id):
    """Returns minimal fanart info for the autocomplete of /removefanart."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT f.id, f.title, f.tags, s.title AS story_title
        FROM fanart f
        JOIN users u ON f.user_id = u.id
        LEFT JOIN stories s ON f.story_id = s.id
        WHERE u.discord_id = ?
        ORDER BY f.title COLLATE NOCASE
    """, (str(discord_id),))

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id":          r["id"],
            "title":       r["title"],
            "tags":        r["tags"],
            "story_title": r["story_title"]
        }
        for r in rows
    ]

# =====================================================
# ✨ ECONOMY & CTC SYSTEM
# =====================================================

def initialize_economy():
    """
    Creates all economy/CTC tables. Safe to call on every bot start —
    uses CREATE TABLE IF NOT EXISTS and safe_add_column throughout.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # -------------------------------------------------
    # WALLETS — one row per user, current balance
    # -------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS wallets (
        user_id     INTEGER PRIMARY KEY,
        balance     INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # -------------------------------------------------
    # CREDIT LEDGER — every earn/spend event logged
    # Used for debugging and future audit trails
    # -------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS credit_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        amount      INTEGER NOT NULL,
        reason      TEXT    NOT NULL,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # -------------------------------------------------
    # DAILY CLAIM — tracks last claim timestamp
    # -------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_claims (
        user_id     INTEGER PRIMARY KEY,
        last_claim  TEXT    NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # -------------------------------------------------
    # CHAPTER CREDITS — one row per (user, chapter)
    # Insert-only. Prevents re-earning on same chapter.
    # -------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chapter_credits_earned (
        user_id     INTEGER NOT NULL,
        chapter_id  INTEGER NOT NULL,
        earned_at   TEXT    NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (user_id, chapter_id),
        FOREIGN KEY (user_id)    REFERENCES users(id)    ON DELETE CASCADE,
        FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chapter_milestones (
        user_id     INTEGER NOT NULL,
        milestone   INTEGER NOT NULL,
        granted_at  TEXT    NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (user_id, milestone),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # -------------------------------------------------
    # ONE-TIME CREDIT FLAGS on existing tables
    # Tracked separately to avoid mutating those tables
    # -------------------------------------------------

    # Characters: credit granted once ever per character
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS character_credit_log (
        character_id INTEGER PRIMARY KEY,
        granted_at   TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
    );
    """)

    # Fanart: credit granted once ever per fanart entry
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fanart_credit_log (
        fanart_id  INTEGER PRIMARY KEY,
        granted_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (fanart_id) REFERENCES fanart(id) ON DELETE CASCADE
    );
    """)

    # Stories: credit granted once ever per story (on first /fic add)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS story_credit_log (
        story_id   INTEGER PRIMARY KEY,
        granted_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE
    );
    """)

    # -------------------------------------------------
    # FREE ROLLS — one row per user, tracks last roll
    # -------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS free_rolls (
        user_id     INTEGER PRIMARY KEY,
        last_roll   TEXT    NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # -------------------------------------------------
    # CTC COLLECTION — characters a user owns
    # -------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ctc_collection (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL,
        character_id INTEGER NOT NULL,
        obtained_at  TEXT    NOT NULL DEFAULT (datetime('now')),
        obtained_via TEXT    NOT NULL DEFAULT 'roll',
        is_shiny     INTEGER NOT NULL DEFAULT 0,
        shiny_at     TEXT,
        UNIQUE(user_id, character_id),
        FOREIGN KEY (user_id)      REFERENCES users(id)       ON DELETE CASCADE,
        FOREIGN KEY (character_id) REFERENCES characters(id)  ON DELETE CASCADE
    );
    """)

    # -------------------------------------------------
    # MILESTONE TRACKER — which milestones a user has claimed
    # Prevents re-granting the 10/20/30... card bonuses
    # -------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ctc_milestones (
        user_id     INTEGER NOT NULL,
        milestone   INTEGER NOT NULL,
        granted_at  TEXT    NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (user_id, milestone),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # -------------------------------------------------
    # RESPIN TOKENS — banked free spins from deleted cards
    # -------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS respin_tokens (
        user_id     INTEGER NOT NULL,
        tokens      INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # -------------------------------------------------
    # CTC HUNT — active shiny hunt target per user
    # -------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ctc_hunt (
        user_id      INTEGER PRIMARY KEY,
        character_id INTEGER NOT NULL,
        hunt_chain   INTEGER NOT NULL DEFAULT 0,
        set_at       TEXT    NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id)      REFERENCES users(id)       ON DELETE CASCADE,
        FOREIGN KEY (character_id) REFERENCES characters(id)  ON DELETE CASCADE
    );
    """)

    # Migrate existing ctc_hunt rows to include hunt_chain if missing
    safe_add_column(cursor, "daily_claims", "streak", "INTEGER NOT NULL DEFAULT 0")
    safe_add_column(cursor, "ctc_hunt", "hunt_chain", "INTEGER NOT NULL DEFAULT 0")

    # Migrate existing ctc_collection rows — cards received via trade are locked from further trading
    safe_add_column(cursor, "ctc_collection", "trade_locked", "INTEGER NOT NULL DEFAULT 0")

    # DNE (private story) support — stories created via /fic private
    safe_add_column(cursor, "stories", "is_dummy", "INTEGER NOT NULL DEFAULT 0")
    safe_add_column(cursor, "stories", "platform")           # 'ao3' or 'wattpad'; NULL = legacy ao3
    safe_add_column(cursor, "stories", "wattpad_reads",    "INTEGER")
    safe_add_column(cursor, "stories", "wattpad_votes",    "INTEGER")
    safe_add_column(cursor, "stories", "wattpad_comments", "INTEGER")
    safe_add_column(cursor, "chapters", "wattpad_comment_count", "INTEGER")
    safe_add_column(cursor, "stories", "ao3_hits",      "INTEGER")
    safe_add_column(cursor, "stories", "ao3_kudos",     "INTEGER")
    safe_add_column(cursor, "stories", "ao3_comments",  "INTEGER")
    safe_add_column(cursor, "stories", "ao3_bookmarks", "INTEGER")

    # -------------------------------------------------
    # BOT SETTINGS — generic key/value config store
    # -------------------------------------------------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bot_settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    # Seed the CTC unlock time once (INSERT OR IGNORE means it won't reset on restart)
    import time as _time
    cursor.execute("""
        INSERT OR IGNORE INTO bot_settings (key, value)
        VALUES ('ctc_unlock_time', ?)
    """, (str(_time.time() + 12 * 3600),))

    conn.commit()
    conn.close()


# =====================================================
# BOT SETTINGS HELPERS
# =====================================================

def get_setting(key: str) -> str | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else None


# =====================================================
# WALLET HELPERS
# =====================================================

def _ensure_wallet(cursor, user_id):
    """Creates a wallet row if one doesn't exist yet."""
    cursor.execute("""
        INSERT OR IGNORE INTO wallets (user_id, balance)
        VALUES (?, 0)
    """, (user_id,))


def get_balance(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    _ensure_wallet(cursor, user_id)
    conn.commit()
    cursor.execute("SELECT balance FROM wallets WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row["balance"] if row else 0


def add_credits(user_id, amount, reason):
    """
    Add (or subtract) credits and write a ledger entry.
    Returns the new balance. Never lets balance go below 0.
    """
    conn = get_connection()
    cursor = conn.cursor()
    _ensure_wallet(cursor, user_id)
    cursor.execute("""
        UPDATE wallets
        SET balance = MAX(0, balance + ?)
        WHERE user_id = ?
    """, (amount, user_id))
    cursor.execute("""
        INSERT INTO credit_log (user_id, amount, reason)
        VALUES (?, ?, ?)
    """, (user_id, amount, reason))
    conn.commit()
    cursor.execute("SELECT balance FROM wallets WHERE user_id = ?", (user_id,))
    new_balance = cursor.fetchone()["balance"]
    conn.close()
    return new_balance


def spend_credits(user_id, amount, reason):
    """
    Deduct credits. Returns (success: bool, new_balance: int).
    Fails cleanly if the user can't afford it.
    """
    conn = get_connection()
    cursor = conn.cursor()
    _ensure_wallet(cursor, user_id)
    cursor.execute("SELECT balance FROM wallets WHERE user_id = ?", (user_id,))
    balance = cursor.fetchone()["balance"]
    if balance < amount:
        conn.close()
        return False, balance
    cursor.execute("""
        UPDATE wallets SET balance = balance - ? WHERE user_id = ?
    """, (amount, user_id))
    cursor.execute("""
        INSERT INTO credit_log (user_id, amount, reason)
        VALUES (?, ?, ?)
    """, (user_id, -amount, reason))
    conn.commit()
    cursor.execute("SELECT balance FROM wallets WHERE user_id = ?", (user_id,))
    new_balance = cursor.fetchone()["balance"]
    conn.close()
    return True, new_balance


# =====================================================
# DAILY CLAIM
# =====================================================

DAILY_COOLDOWN = 24  # hours

# Streak reward table — gems earned per consecutive day
DAILY_STREAK_REWARDS = {1: 150, 2: 300, 3: 500, 4: 600, 5: 750, 6: 900}
DAILY_STREAK_MAX_REWARD = 1200  # cap at day 7+

# Keep for backwards compat (wallet display uses this symbol)
DAILY_AMOUNT = DAILY_STREAK_REWARDS[1]


def _daily_reward_for_streak(streak: int) -> int:
    return DAILY_STREAK_REWARDS.get(streak, DAILY_STREAK_MAX_REWARD)


def claim_daily(user_id):
    """
    Attempts a daily claim.
    Returns a dict:
      success          bool   — whether the claim went through
      new_balance      int    — gem balance after claim (0 if on cooldown)
      streak           int    — current streak (after claim, or existing if on cooldown)
      reward           int    — gems awarded this claim (0 if on cooldown)
      chain_broken     bool   — True if streak was reset because 48h window was missed
      cooldown_seconds float  — seconds remaining until next claim (0 if claimable)
      chain_break_seconds float|None  — seconds until chain breaks from NOW
                                        (None if chain already broken or not applicable)
    """
    import datetime
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.datetime.utcnow()
    cursor.execute(
        "SELECT last_claim, COALESCE(streak, 0) AS streak FROM daily_claims WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()

    if row:
        last           = datetime.datetime.fromisoformat(row["last_claim"])
        current_streak = int(row["streak"])
        diff_secs      = (now - last).total_seconds()
        cooldown_secs  = DAILY_COOLDOWN * 3600
        chain_window   = 48 * 3600  # must claim within 48h of last claim

        if diff_secs < cooldown_secs:
            # Still on cooldown
            remaining_secs   = cooldown_secs - diff_secs
            chain_break_secs = chain_window - diff_secs   # always > 0 here
            conn.close()
            return {
                "success":             False,
                "new_balance":         0,
                "streak":              current_streak,
                "reward":              0,
                "chain_broken":        False,
                "cooldown_seconds":    remaining_secs,
                "chain_break_seconds": chain_break_secs,
            }

        # Claimable — did they miss the chain window?
        if diff_secs >= chain_window:
            new_streak   = 1
            chain_broken = True
        else:
            new_streak   = current_streak + 1
            chain_broken = False
    else:
        new_streak   = 1
        chain_broken = False

    reward = _daily_reward_for_streak(new_streak)

    cursor.execute("""
        INSERT INTO daily_claims (user_id, last_claim, streak)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            last_claim = excluded.last_claim,
            streak     = excluded.streak
    """, (user_id, now.isoformat(), new_streak))
    conn.commit()
    conn.close()

    new_balance = add_credits(user_id, reward, "daily_claim")
    return {
        "success":             True,
        "new_balance":         new_balance,
        "streak":              new_streak,
        "reward":              reward,
        "chain_broken":        chain_broken,
        "cooldown_seconds":    0.0,
        "chain_break_seconds": None,
    }


# =====================================================
# ONE-TIME CREDIT GRANTS (anti-abuse)
# =====================================================

def grant_character_credit(user_id, character_id):
    """
    Awards credits for adding a character — once ever per character_id.
    Returns (granted: bool, new_balance: int).
    """
    AMOUNT = 75
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM character_credit_log WHERE character_id = ?", (character_id,)
    )
    if cursor.fetchone():
        conn.close()
        return False, get_balance(user_id)
    cursor.execute(
        "INSERT INTO character_credit_log (character_id) VALUES (?)", (character_id,)
    )
    conn.commit()
    conn.close()
    new_balance = add_credits(user_id, AMOUNT, f"character_add:{character_id}")
    return True, new_balance


def grant_fanart_credit(user_id, fanart_id):
    """
    Awards credits for adding fanart — once ever per fanart_id.
    Returns (granted: bool, new_balance: int).
    """
    AMOUNT = 200
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM fanart_credit_log WHERE fanart_id = ?", (fanart_id,)
    )
    if cursor.fetchone():
        conn.close()
        return False, get_balance(user_id)
    cursor.execute(
        "INSERT INTO fanart_credit_log (fanart_id) VALUES (?)", (fanart_id,)
    )
    conn.commit()
    conn.close()
    new_balance = add_credits(user_id, AMOUNT, f"fanart_add:{fanart_id}")
    return True, new_balance


def grant_story_credit(user_id, story_id):
    """
    Awards credits for first /fic add — once ever per story_id.
    Returns (granted: bool, new_balance: int).
    """
    AMOUNT = 150
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM story_credit_log WHERE story_id = ?", (story_id,)
    )
    if cursor.fetchone():
        conn.close()
        return False, get_balance(user_id)
    cursor.execute(
        "INSERT INTO story_credit_log (story_id) VALUES (?)", (story_id,)
    )
    conn.commit()
    conn.close()
    new_balance = add_credits(user_id, AMOUNT, f"story_add:{story_id}")
    return True, new_balance


def grant_chapter_read_credit(user_id, chapter_id):
    """
    Awards credits for completing a chapter — once ever per (user, chapter).
    Returns (granted: bool, new_balance: int).
    """
    AMOUNT = 50
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM chapter_credits_earned
        WHERE user_id = ? AND chapter_id = ?
    """, (user_id, chapter_id))
    if cursor.fetchone():
        conn.close()
        return False, get_balance(user_id)
    cursor.execute("""
        INSERT INTO chapter_credits_earned (user_id, chapter_id)
        VALUES (?, ?)
    """, (user_id, chapter_id))
    conn.commit()
    conn.close()
    new_balance = add_credits(user_id, AMOUNT, f"chapter_read:{chapter_id}")
    check_and_grant_chapter_milestones(user_id)
    return True, new_balance


def revoke_chapter_read_credit(user_id, chapter_id):
    """
    Reverses a chapter read credit: removes the earned record and deducts 50 gems.
    Always deducts regardless of whether the record existed (balance can go negative).
    Returns (revoked: bool, new_balance: int).
    """
    AMOUNT = 50
    conn = get_connection()
    rows_deleted = conn.execute(
        "DELETE FROM chapter_credits_earned WHERE user_id = ? AND chapter_id = ?",
        (user_id, chapter_id)
    ).rowcount
    conn.commit()
    conn.close()
    new_balance = add_credits(user_id, -AMOUNT, f"chapter_unread:{chapter_id}")
    return rows_deleted > 0, new_balance


def get_chapter_read_count(user_id: int) -> int:
    """Returns how many unique chapters this user has read (received credit for)."""
    conn  = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM chapter_credits_earned WHERE user_id = ?",
        (user_id,)
    ).fetchone()["cnt"]
    conn.close()
    return count


def check_and_grant_chapter_milestones(user_id: int) -> list:
    """
    Awards CHAPTER_MILESTONE_BONUS for every CHAPTER_MILESTONE_INTERVAL unique chapters read.
    Returns list of newly-hit milestones (integers).
    """
    chapters_read = get_chapter_read_count(user_id)
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT milestone FROM chapter_milestones WHERE user_id = ?", (user_id,)
    )
    already = {r["milestone"] for r in cursor.fetchall()}
    conn.close()

    newly_granted = []
    for i in range(1, (chapters_read // CHAPTER_MILESTONE_INTERVAL) + 1):
        milestone = i * CHAPTER_MILESTONE_INTERVAL
        if milestone not in already:
            conn2 = get_connection()
            conn2.execute(
                "INSERT INTO chapter_milestones (user_id, milestone) VALUES (?, ?)",
                (user_id, milestone)
            )
            conn2.commit()
            conn2.close()
            add_credits(user_id, CHAPTER_MILESTONE_BONUS, f"chapter_milestone:{milestone}")
            newly_granted.append(milestone)
    return newly_granted


def grant_author_passive(author_user_id, character_id, collector_user_id):
    """
    Awards the author 50 credits every time someone collects their character.
    No dedup — repeat collections (e.g. shiny hunting) all benefit the author.
    Returns (granted: bool, new_balance: int).
    """
    AMOUNT = 50
    reason = f"author_passive:{character_id}:collector:{collector_user_id}"
    new_balance = add_credits(author_user_id, AMOUNT, reason)
    return True, new_balance


# =====================================================
# COLLECTION MILESTONES
# =====================================================

MILESTONE_INTERVAL = 7    # every 7 cards
MILESTONE_BONUS    = 1000 # credits per card milestone

CHAPTER_MILESTONE_INTERVAL = 10    # every 10 unique chapters read
CHAPTER_MILESTONE_BONUS    = 300   # credits per chapter milestone


def check_and_grant_milestones(user_id):
    """
    Checks how many cards the user owns and grants any unclaimed
    10/20/30... milestones. Returns list of newly granted milestones.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM ctc_collection WHERE user_id = ?", (user_id,)
    )
    total = cursor.fetchone()["cnt"]
    newly_granted = []
    for n in range(MILESTONE_INTERVAL, total + 1, MILESTONE_INTERVAL):
        cursor.execute("""
            SELECT 1 FROM ctc_milestones WHERE user_id = ? AND milestone = ?
        """, (user_id, n))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO ctc_milestones (user_id, milestone) VALUES (?, ?)
            """, (user_id, n))
            newly_granted.append(n)
    conn.commit()
    conn.close()
    for milestone in newly_granted:
        add_credits(user_id, MILESTONE_BONUS, f"milestone:{milestone}")
    return newly_granted


# =====================================================
# RESPIN TOKENS (granted when a collected card is deleted)
# =====================================================

def grant_respin_token(user_id: int):
    """Give a user one banked free respin."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO respin_tokens (user_id, tokens)
        VALUES (?, 1)
        ON CONFLICT(user_id) DO UPDATE SET tokens = tokens + 1
    """, (user_id,))
    conn.commit()
    conn.close()


def get_respin_tokens(user_id: int) -> int:
    """Returns how many banked respins this user has."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT tokens FROM respin_tokens WHERE user_id = ?", (user_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row["tokens"] if row else 0


def use_respin_token(user_id: int) -> bool:
    """
    Consumes one respin token. Returns True if successful, False if none left.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT tokens FROM respin_tokens WHERE user_id = ?", (user_id,)
    )
    row = cursor.fetchone()
    if not row or row["tokens"] < 1:
        conn.close()
        return False
    cursor.execute(
        "UPDATE respin_tokens SET tokens = tokens - 1 WHERE user_id = ?", (user_id,)
    )
    conn.commit()
    conn.close()
    return True


# =====================================================
# CTC HUNT HELPERS
# =====================================================

def set_hunt(user_id: int, character_id: int):
    """Set (or replace) the user's active shiny hunt target. Always resets chain to 0."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO ctc_hunt (user_id, character_id, hunt_chain)
        VALUES (?, ?, 0)
        ON CONFLICT(user_id) DO UPDATE SET
            character_id = excluded.character_id,
            hunt_chain   = 0,
            set_at       = datetime('now')
    """, (user_id, character_id))
    conn.commit()
    conn.close()


def get_hunt(user_id: int) -> dict | None:
    """Return the hunted character dict (id, name, image_url, shiny_image_url, hunt_chain) or None."""
    conn = get_connection()
    row = conn.execute("""
        SELECT ch.id, ch.name, ch.image_url, ch.shiny_image_url, h.hunt_chain
        FROM ctc_hunt h
        JOIN characters ch ON ch.id = h.character_id
        WHERE h.user_id = ?
    """, (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def clear_hunt(user_id: int):
    """Remove the user's active hunt target (chain lost)."""
    conn = get_connection()
    conn.execute("DELETE FROM ctc_hunt WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def increment_hunt_chain(user_id: int):
    """Increment the hunt chain counter by 1 (called when hunted card is claimed)."""
    conn = get_connection()
    conn.execute("""
        UPDATE ctc_hunt SET hunt_chain = hunt_chain + 1 WHERE user_id = ?
    """, (user_id,))
    conn.commit()
    conn.close()


# Chain shiny rates for the hunted card specifically.
# Normal spin: [0-4, 5-9, 10-14, 15+]
HUNT_CHAIN_RATES_NORMAL  = [1/400, 1/200, 1/100, 1/25]
# Premium spin: [0-4, 5-9, 10-14, 15+]
HUNT_CHAIN_RATES_PREMIUM = [1/100, 1/50,  1/15,  1/5]
# Thresholds that mark each tier (chain must be >= value to use that tier)
HUNT_CHAIN_THRESHOLDS = [0, 5, 10, 15]

def hunt_chain_shiny_rate(chain: int, premium: bool = False) -> float:
    """Return the chain-boosted shiny rate for the hunted card."""
    rates = HUNT_CHAIN_RATES_PREMIUM if premium else HUNT_CHAIN_RATES_NORMAL
    tier = 0
    for i, threshold in enumerate(HUNT_CHAIN_THRESHOLDS):
        if chain >= threshold:
            tier = i
    return rates[tier]


def hunt_chain_tier(chain: int) -> int:
    """Return the current tier index (0-4)."""
    tier = 0
    for i, threshold in enumerate(HUNT_CHAIN_THRESHOLDS):
        if chain >= threshold:
            tier = i
    return tier


def get_card_collectors(character_id: int) -> list:
    """
    Returns a list of DB user_ids who own a given character card.
    Call this BEFORE deleting the character.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id FROM ctc_collection WHERE character_id = ?", (character_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


# =====================================================
# FREE WEEKLY ROLL
# =====================================================

FREE_ROLL_COOLDOWN = 7  # days


def can_free_roll(user_id):
    """
    Returns (eligible: bool, hours_remaining: int).
    """
    import datetime
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT last_roll FROM free_rolls WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return True, 0
    last = datetime.datetime.fromisoformat(row["last_roll"])
    diff = datetime.datetime.utcnow() - last
    cooldown = datetime.timedelta(days=FREE_ROLL_COOLDOWN)
    if diff >= cooldown:
        return True, 0
    remaining = int((cooldown - diff).total_seconds() / 3600)
    return False, remaining


def use_free_roll(user_id):
    """Stamps the free roll timestamp. Call after confirming eligibility."""
    import datetime
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT INTO free_rolls (user_id, last_roll)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET last_roll = excluded.last_roll
    """, (user_id, now))
    conn.commit()
    conn.close()


# =====================================================
# CTC COLLECTION
# =====================================================

ROLL_COST        = 300
DIRECT_BUY_COST  = 25000


def get_rollable_characters(user_id):
    """
    Returns ALL characters — every card is eligible for any roll regardless
    of ownership. Owned cards still have boosted shiny odds on roll.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.name, c.image_url, c.story_id,
               COALESCE(c.is_main_character, 0) AS is_main_character,
               s.title AS story_title, u.discord_id AS author_discord_id
        FROM characters c
        LEFT JOIN stories s  ON c.story_id = s.id
        LEFT JOIN users   u  ON c.user_id  = u.id
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_to_collection(user_id, character_id, via="roll"):
    """
    Adds a character to the user's collection.
    Returns (success: bool, already_owned: bool).
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM ctc_collection WHERE user_id = ? AND character_id = ?
    """, (user_id, character_id))
    if cursor.fetchone():
        conn.close()
        return False, True   # already owned
    cursor.execute("""
        INSERT INTO ctc_collection (user_id, character_id, obtained_via)
        VALUES (?, ?, ?)
    """, (user_id, character_id, via))
    conn.commit()
    conn.close()
    return True, False


def get_collection_count(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM ctc_collection WHERE user_id = ?", (user_id,)
    )
    count = cursor.fetchone()["cnt"]
    conn.close()
    return count


def get_shiny_count(user_id):
    """Returns how many shiny cards a user owns."""
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM ctc_collection WHERE user_id = ? AND is_shiny = 1",
        (user_id,)
    ).fetchone()["cnt"]
    conn.close()
    return count


def get_card_owner_count(character_id):
    """Returns how many users own a given character card."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM ctc_collection WHERE character_id = ?
    """, (character_id,))
    count = cursor.fetchone()["cnt"]
    conn.close()
    return count


def user_owns_card(user_id, character_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM ctc_collection WHERE user_id = ? AND character_id = ?
    """, (user_id, character_id))
    owns = cursor.fetchone() is not None
    conn.close()
    return owns


def do_roll(user_id):
    """
    Picks 2 random characters from the rollable pool.
    Returns list of 2 character dicts, or fewer if pool is small.
    """
    import random
    pool = get_rollable_characters(user_id)
    if not pool:
        return []
    return random.sample(pool, min(2, len(pool)))


def perform_paid_roll(user_id):
    """
    Deducts ROLL_COST and returns the 2 rolled characters.
    Returns (success: bool, reason: str, cards: list).
    """
    ok, balance = spend_credits(user_id, ROLL_COST, "ctc_roll")
    if not ok:
        return False, f"Not enough credits! You need **{ROLL_COST}** but have **{balance}**.", []
    cards = do_roll(user_id)
    if not cards:
        # Refund — no cards available
        add_credits(user_id, ROLL_COST, "ctc_roll_refund:empty_pool")
        return False, "You've collected every character! Nothing left to roll.", []
    return True, "ok", cards


def perform_direct_buy(user_id, character_id):
    """
    Deducts DIRECT_BUY_COST and adds the character directly.
    Returns (success: bool, message: str, new_balance: int).
    """
    if user_owns_card(user_id, character_id):
        return False, "You already own this card!", get_balance(user_id)
    ok, balance = spend_credits(user_id, DIRECT_BUY_COST, f"ctc_direct_buy:{character_id}")
    if not ok:
        return False, f"Not enough credits! You need **{DIRECT_BUY_COST}** but have **{balance}**.", balance
    add_to_collection(user_id, character_id, via="direct_buy")
    return True, "ok", balance


# =====================================================
# SHINY SYSTEM
# =====================================================

SHINY_UPGRADE_COST         = 125000  # crystals to manually upgrade a normal card to shiny
SHINY_BASE_CHANCE          = 1/400   # 0.25 % base shiny roll
PREMIUM_ROLL_COST          = 1000    # cost of a premium spin
SHINY_BASE_CHANCE_PREMIUM  = 0.01    # 1 % on premium spin
DUPLICATE_REFUND     = 20     # crystals back when a duplicate normal card is rolled
SHINY_DUPE_REFUND    = 4000   # crystals back when a shiny is rolled that you already own
SHINY_CHARM_MULTIPLIER = 2.0  # shiny rate multiplier for characters from a 100%-completed story


def _migrate_shiny_columns():
    """
    Safe migration: adds is_shiny / shiny_at to ctc_collection if they don't
    exist yet. Call once at startup (bot.py or core/startup.py).
    """
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("PRAGMA table_info(ctc_collection)")
    cols = {row["name"] for row in cur.fetchall()}
    if "is_shiny" not in cols:
        cur.execute("ALTER TABLE ctc_collection ADD COLUMN is_shiny INTEGER NOT NULL DEFAULT 0")
    if "shiny_at" not in cols:
        cur.execute("ALTER TABLE ctc_collection ADD COLUMN shiny_at TEXT")
    conn.commit()
    conn.close()


def user_owns_shiny(user_id: int, character_id: int) -> bool:
    """Returns True if the user has the shiny version of this card."""
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(
        "SELECT is_shiny FROM ctc_collection WHERE user_id=? AND character_id=?",
        (user_id, character_id)
    )
    row = cur.fetchone()
    conn.close()
    return bool(row and row["is_shiny"])


def upgrade_card_to_shiny(user_id: int, character_id: int):
    """
    Marks an existing normal card as shiny (in-place upgrade).
    Returns (success: bool, message: str, new_balance: int).
    """
    if not user_owns_card(user_id, character_id):
        return False, "You don't own this card yet!", get_balance(user_id)
    if user_owns_shiny(user_id, character_id):
        return False, "Your card is already shiny! ✨", get_balance(user_id)

    ok, balance = spend_credits(user_id, SHINY_UPGRADE_COST, f"shiny_upgrade:{character_id}")
    if not ok:
        return False, (
            f"You need {SHINY_UPGRADE_COST:,} crystals but only have {balance:,}."
        ), balance

    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE ctc_collection SET is_shiny=1, shiny_at=datetime('now') "
        "WHERE user_id=? AND character_id=?",
        (user_id, character_id)
    )
    conn.commit()
    conn.close()
    return True, "ok", balance


def grant_shiny(user_id: int, character_id: int, via: str = "roll"):
    """
    Upgrades (or inserts) a card as shiny.  If the user already owns the
    normal card this replaces it in-place.  If they don't own it at all,
    inserts it as shiny from the start.
    Returns (already_had_normal: bool).
    """
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(
        "SELECT id, is_shiny FROM ctc_collection WHERE user_id=? AND character_id=?",
        (user_id, character_id)
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE ctc_collection SET is_shiny=1, shiny_at=datetime('now'), obtained_via=? "
            "WHERE user_id=? AND character_id=?",
            (via, user_id, character_id)
        )
        conn.commit()
        conn.close()
        return True   # had normal, now upgraded
    else:
        cur.execute(
            "INSERT INTO ctc_collection (user_id, character_id, obtained_via, is_shiny, shiny_at) "
            "VALUES (?, ?, ?, 1, datetime('now'))",
            (user_id, character_id, via)
        )
        conn.commit()
        conn.close()
        return False  # fresh shiny insert


def get_collection(user_id):
    """Returns all character cards in a user's collection, newest first."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.name, c.image_url, c.story_id,
               s.title AS story_title,
               s.author,
               s.cover_url,
               cc.obtained_at, cc.obtained_via,
               cc.is_shiny, cc.shiny_at,
               cc.trade_locked
        FROM ctc_collection cc
        JOIN characters c ON cc.character_id = c.id
        LEFT JOIN stories s ON c.story_id = s.id
        WHERE cc.user_id = ?
        ORDER BY cc.obtained_at DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_card_trade_locked(user_id: int, character_id: int):
    """Mark a card as trade-locked. Called after a trade completes for the received card."""
    conn = get_connection()
    conn.execute(
        "UPDATE ctc_collection SET trade_locked = 1 WHERE user_id = ? AND character_id = ?",
        (user_id, character_id)
    )
    conn.commit()
    conn.close()


# =====================================================
# ACTIVITY GEMS  —  earn crystals by chatting
# =====================================================
#
# Design:
#   • Each message has a ACTIVITY_COOLDOWN_SECONDS cooldown per user.
#     This prevents spam-farming — only the first message in any window
#     counts toward the reward.
#   • Each qualifying message grants ACTIVITY_REWARD crystals.
#   • A user can earn at most ACTIVITY_DAILY_CAP crystals this way per day.
#     (resets at UTC midnight)
#
# Each qualifying message grants a random amount between ACTIVITY_REWARD_MIN
# and ACTIVITY_REWARD_MAX crystals (inclusive). No daily cap.
#
ACTIVITY_REWARD_MIN       = 25   # minimum crystals per qualifying message
ACTIVITY_REWARD_MAX       = 35   # maximum crystals per qualifying message
ACTIVITY_COOLDOWN_MIN     = 45   # minimum seconds between rewards
ACTIVITY_COOLDOWN_MAX     = 75   # maximum seconds between rewards (randomised per grant)


def ensure_activity_table():
    """Create the activity_gem_log table if it doesn't exist yet."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_gem_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            granted_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()


def try_grant_activity_gem(user_id: int) -> tuple[bool, int]:
    """
    Called on every user message.  Grants a random ACTIVITY_REWARD_MIN–MAX
    crystals if at least ACTIVITY_COOLDOWN_SECONDS have passed since the
    last grant.  No daily cap.

    Returns (granted: bool, new_balance: int).
    """
    import datetime as _dt
    import random as _random

    conn = get_connection()
    try:
        now = _dt.datetime.utcnow()

        # ── Cooldown check ────────────────────────────────────────────────────
        last_row = conn.execute(
            "SELECT granted_at FROM activity_gem_log WHERE user_id = ? "
            "ORDER BY granted_at DESC LIMIT 1",
            (user_id,)
        ).fetchone()

        if last_row:
            last_dt = _dt.datetime.fromisoformat(last_row["granted_at"])
            cooldown = _random.randint(ACTIVITY_COOLDOWN_MIN, ACTIVITY_COOLDOWN_MAX)
            if (now - last_dt).total_seconds() < cooldown:
                conn.close()
                return False, 0

        # ── Grant ─────────────────────────────────────────────────────────────
        conn.execute(
            "INSERT INTO activity_gem_log (user_id) VALUES (?)", (user_id,)
        )
        conn.commit()
    finally:
        conn.close()

    reward = _random.randint(ACTIVITY_REWARD_MIN, ACTIVITY_REWARD_MAX)
    new_balance = add_credits(user_id, reward, "activity_chat")
    return True, new_balance