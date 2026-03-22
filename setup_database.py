import sqlite3

# This will create the database file if it doesn't exist
conn = sqlite3.connect("library.db")
cursor = conn.cursor()

# Enable foreign key support
cursor.execute("PRAGMA foreign_keys = ON;")

# Create users table
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id TEXT UNIQUE NOT NULL,
    username TEXT NOT NULL
);
""")

# Create stories table
cursor.execute("""
CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    ao3_url TEXT UNIQUE NOT NULL,
    chapter_count INTEGER DEFAULT 0,
    last_updated TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
""")

# Create chapters table
cursor.execute("""
CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL,
    chapter_number INTEGER NOT NULL,
    chapter_title TEXT,
    FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE
);
""")

conn.commit()
conn.close()

print("Database and tables created successfully!")
