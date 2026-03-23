def _is_emoji_char(ch: str) -> bool:
    """Return True if ch looks like the trailing character of an emoji."""
    cp = ord(ch)
    return (
        0x1F000 <= cp <= 0x1FFFF   # faces, objects, symbols, etc.
        or 0x2600 <= cp <= 0x27BF  # misc symbols (☀️ ☁️ ♥️ …)
        or 0x2300 <= cp <= 0x23FF  # misc technical (⏰ ⌛ …)
        or 0xFE00 <= cp <= 0xFE0F  # variation selectors (often trail emoji)
        or ch == ">"               # end of Discord custom emoji <:name:id>
    )


def normalize_inline_text(text: str) -> str:

    if not text:
        return text

    # Normalize line endings to spaces
    text = text.replace("\n", " ").replace("\r", " ")

    # Collapse runs of spaces.
    # Rule: normally collapse any run to 1 space.
    #       Exception: allow exactly 2 spaces when the run is preceded by an
    #       emoji character, so users can write e.g. "Female 🌸  She/Her".
    result = []
    i = 0
    while i < len(text):
        if text[i] == " ":
            j = i
            while j < len(text) and text[j] == " ":
                j += 1
            run = j - i
            if run >= 2 and i > 0 and _is_emoji_char(text[i - 1]):
                result.append("  ")   # preserve double space after emoji
            else:
                result.append(" ")    # collapse everything else to one space
            i = j
        else:
            result.append(text[i])
            i += 1

    return "".join(result).strip()