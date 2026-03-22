def normalize_inline_text(text: str):

    if not text:
        return text

    # Replace newlines and multiple spaces
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")

    # Collapse multiple spaces
    text = " ".join(text.split())

    return text