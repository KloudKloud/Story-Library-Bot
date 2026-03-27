from database import (
    get_user_id,
    add_user,
    get_connection,
)


def create_world_card(discord_id: int, username: str, story_id: int, name: str) -> int:
    """
    Create a new world card for a story.
    Raises ValueError if a card with the same name already exists in that story.
    Returns the new world card's DB id.
    """
    add_user(str(discord_id), username)
    user_id = get_user_id(str(discord_id))

    conn   = get_connection()
    cursor = conn.cursor()

    # Prevent duplicates within the same story
    cursor.execute(
        "SELECT id FROM world_cards WHERE story_id = ? AND LOWER(name) = LOWER(?)",
        (story_id, name),
    )
    if cursor.fetchone():
        conn.close()
        raise ValueError("A world card with this name already exists for that story.")

    cursor.execute(
        "INSERT INTO world_cards (user_id, story_id, name) VALUES (?, ?, ?)",
        (user_id, story_id, name),
    )
    world_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return world_id


def delete_world_card_safe(world_id: int) -> None:
    """
    Safely delete a world card:
    1. Grant a respin token to every user who owns this card in world_ctc_collection
    2. Delete the world card (CASCADE removes world_ctc_collection + world_ctc_hunt rows)
    """
    from database import get_world_card_collectors, grant_respin_token, delete_world_card

    collectors = get_world_card_collectors(world_id)
    for uid in collectors:
        grant_respin_token(uid)

    delete_world_card(world_id)


def update_world_details(world_id: int, **kwargs) -> None:
    """
    Update any subset of world card fields.
    Accepted keys: world_type, description, lore, quote, image_url,
                   shiny_image_url, music_url
    """
    allowed = {
        "world_type", "description", "lore", "quote",
        "image_url", "shiny_image_url", "music_url",
    }
    updates = [(f"{k} = ?", v) for k, v in kwargs.items() if k in allowed and v is not None]
    if not updates:
        return

    cols, vals = zip(*updates)
    vals = list(vals) + [world_id]

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE world_cards SET {', '.join(cols)} WHERE id = ?",
        vals,
    )
    conn.commit()
    conn.close()
