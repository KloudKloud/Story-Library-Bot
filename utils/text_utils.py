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


def fix_emoji_spacing(text: str) -> str:
    """
    Replace double spaces after an emoji with space + non-breaking space so
    Discord won't collapse them during embed rendering.  Safe to call on any
    text — leaves everything else untouched.
    """
    if not text:
        return text
    result = []
    i = 0
    while i < len(text):
        if text[i] == " " and i > 0 and _is_emoji_char(text[i - 1]):
            if i + 1 < len(text) and text[i + 1] == " ":
                result.append(" \u00A0")  # space + non-breaking space
                i += 2
                while i < len(text) and text[i] == " ":
                    i += 1
                continue
        result.append(text[i])
        i += 1
    return "".join(result)


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
                result.append(" \u00A0")  # space + non-breaking space — Discord won't collapse it
            else:
                result.append(" ")        # collapse everything else to one space
            i = j
        else:
            result.append(text[i])
            i += 1

    return "".join(result).strip()