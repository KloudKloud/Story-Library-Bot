from database import (
    get_user_id,
    add_user,
    add_character,
    get_characters_by_user,
    get_connection,
    get_characters_by_story as db_get_characters_by_story
)


def create_character(discord_id, username, story_id, name):
    """
    Create a character for a story.

    Prevents duplicate characters in the same story.
    """

    add_user(str(discord_id), username)

    user_id = get_user_id(str(discord_id))

    # --------------------------------
    # Prevent duplicates
    # --------------------------------

    existing = db_get_characters_by_story(story_id)

    for c in existing:

        # supports dict OR tuple depending on DB format
        char_name = c["name"] if isinstance(c, dict) else c[1]

        if char_name.lower() == name.lower():
            raise ValueError(
                "A character with this name already exists for that story."
            )

    # --------------------------------
    # Create character
    # --------------------------------

    character_id = add_character(
        user_id,
        story_id,
        name,
        None,
        None,
        None
    )
    return character_id


def get_user_characters(discord_id):

    uid = get_user_id(str(discord_id))
    if not uid:
        return []

    return get_characters_by_user(uid)

def update_character_details(
    character_id,
    name=None,
    gender=None,
    personality=None,
    image_url=None,
    quote=None,
    age=None,
    height=None,
    physical_features=None,
    relationships=None,
    lore=None,
    music_url=None,
    species=None,
    shiny_image_url=None,
):
    conn = get_connection()
    cursor = conn.cursor()

    updates = []
    values = []

    if name is not None:
        updates.append("name = ?")
        values.append(name.strip())

    if gender is not None:
        updates.append("gender = ?")
        values.append(gender)

    if personality is not None:
        updates.append("personality = ?")
        values.append(personality)

    if image_url is not None:
        updates.append("image_url = ?")
        values.append(image_url)

    if quote is not None:
        updates.append("quote = ?")
        values.append(quote)

    if age is not None:
        updates.append("age = ?")
        values.append(age)

    if height is not None:
        updates.append("height = ?")
        values.append(height)

    if physical_features is not None:
        updates.append("physical_features = ?")
        values.append(physical_features)

    if relationships is not None:
        updates.append("relationships = ?")
        values.append(relationships)

    if lore is not None:
        updates.append("lore = ?")
        values.append(lore)

    if music_url is not None:
        updates.append("music_url = ?")
        values.append(music_url)

    if species is not None:
        updates.append("species = ?")
        values.append(species)

    if shiny_image_url is not None:
        updates.append("shiny_image_url = ?")
        values.append(shiny_image_url)

    if not updates:
        conn.close()
        return

    values.append(character_id)

    cursor.execute(
        f"UPDATE characters SET {', '.join(updates)} WHERE id = ?",
        values
    )

    conn.commit()
    conn.close()

    # Name change requires flushing the global character cache
    if name is not None:
        try:
            from database import _all_characters_cache
            _all_characters_cache.invalidate()
        except Exception:
            pass

def get_characters_by_story(story_id):
    """
    Character logic layer.
    Future-safe place for sorting/filtering/etc.
    """
    return db_get_characters_by_story(story_id)

def delete_character(character_id):
    """
    Safely remove a character and all references to them:
    - Grants a respin token to every user who owned this card in their CTC collection
    - Removes from anyone's favorites
    - Removes from all fanart character tags
    - Removes from all ships (and deletes ship if now empty / only them)
    - Removes ship fanart links for affected ships
    - ctc_collection rows are cleaned by ON DELETE CASCADE
    Then deletes the character.
    """
    from database import get_card_collectors, grant_respin_token

    # 0. Find CTC collectors and grant them each a respin token BEFORE cascade deletes them
    collectors = get_card_collectors(character_id)
    for uid in collectors:
        grant_respin_token(uid)

    conn = get_connection()
    cursor = conn.cursor()

    # 1. Remove from favorites
    cursor.execute(
        "DELETE FROM favorite_characters WHERE character_id = ?",
        (character_id,)
    )

    # 2. Remove fanart character tags
    cursor.execute(
        "DELETE FROM fanart_characters WHERE character_id = ?",
        (character_id,)
    )

    # 3. Find ships containing this character
    cursor.execute(
        "SELECT DISTINCT ship_id FROM ship_characters WHERE character_id = ?",
        (character_id,)
    )
    ship_ids = [r["ship_id"] for r in cursor.fetchall()]

    if ship_ids:
        sp = ",".join("?" * len(ship_ids))
        # Remove fanart_ships links for those ships
        cursor.execute(f"DELETE FROM fanart_ships    WHERE ship_id IN ({sp})", ship_ids)
        # Remove ship_characters entries
        cursor.execute(f"DELETE FROM ship_characters WHERE ship_id IN ({sp})", ship_ids)
        # Delete the ships themselves
        cursor.execute(f"DELETE FROM ships           WHERE id      IN ({sp})", ship_ids)

    # 4. Delete the character
    cursor.execute(
        "DELETE FROM characters WHERE id = ?",
        (character_id,)
    )

    conn.commit()
    conn.close()
    from database import _all_characters_cache, _all_ships_cache
    _all_characters_cache.invalidate()
    _all_ships_cache.invalidate()