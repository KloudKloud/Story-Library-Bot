def normalize_tags(tag_string: str) -> str:
    """
    Clean and normalize comma-separated tags.

    Example:
    "sketch, romance , sketch , ICON, digital art"
    -> "sketch,romance,icon,digital_art"
    """

    if not tag_string:
        return ""

    tags = tag_string.split(",")

    cleaned = []
    seen = set()

    for tag in tags:

        tag = tag.strip().lower()

        if not tag:
            continue

        # convert spaces inside tag to underscores
        tag = tag.replace(" ", "_")

        if tag in seen:
            continue

        seen.add(tag)
        cleaned.append(tag)

    return ",".join(cleaned)

def split_tags(tag_string):

    if not tag_string:
        return []

    return [
        tag.strip()
        for tag in tag_string.split(",")
        if tag.strip()
    ]