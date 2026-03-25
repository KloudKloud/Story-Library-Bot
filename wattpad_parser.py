import re
import requests
import time
import random

from urllib.parse import urlparse


# =====================================================
# CUSTOM EXCEPTION
# =====================================================

class WattpadError(Exception):
    """
    Raised for any Wattpad parse/API failure.

    Attributes:
        user_message  — safe, friendly string to show directly in Discord
        technical     — internal detail for logging (not shown to users)
    """
    def __init__(self, user_message, technical=None):
        super().__init__(technical or user_message)
        self.user_message = user_message
        self.technical    = technical or user_message


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.wattpad.com/",
}

# Used as fallback only when the text fetch fails for a part
_CHARS_PER_WORD = 6.0

BASE_URL = "https://www.wattpad.com/api/v3"

# All fields fetched in a single story request.
# Parts are embedded via the "parts" field — there is no separate /parts endpoint.
_STORY_FIELDS = ",".join([
    "id", "title", "description", "tags",
    "user", "mature", "completed",
    "numParts", "readCount", "voteCount", "commentCount",
    "cover", "coverOriginal",
    "mainCategory", "mainCategoryEnglish",
    "createDate", "modifyDate",
    "length",
    "parts",
])


# =====================================================
# NORMALIZE URL + EXTRACT STORY ID
# =====================================================

def normalize_wattpad_url(url):
    """
    Return the canonical https://www.wattpad.com/story/{id} URL.
    For chapter URLs the story ID is not yet known at this point, so we
    return a best-effort normalized form; fetch_wattpad_metadata resolves it.
    """
    story_id, _ = extract_story_id(url)
    if story_id:
        return f"https://www.wattpad.com/story/{story_id}"
    return url


def extract_story_id(url):
    """
    Extract the numeric story ID from a Wattpad URL.

    Handles:
      https://www.wattpad.com/story/123456789-some-slug  → story ID directly
      https://www.wattpad.com/story/123456789
      https://www.wattpad.com/1517596161-chapter-slug    → part ID (needs resolution)

    Returns (story_id_or_part_id, is_part_id).
    """
    # Story page URL — ID is the story ID directly
    match = re.search(r"/story/(\d+)", url)
    if match:
        return match.group(1), False

    # Chapter/part URL — leading number is a part ID, not a story ID
    # e.g. https://www.wattpad.com/1517596161-some-chapter-name
    match = re.search(r"wattpad\.com/(\d+)(?:-|$)", url)
    if match:
        return match.group(1), True

    return None, False


def _resolve_story_id_from_part(part_id, chapter_url):
    """
    Given a Wattpad chapter URL, return the parent story ID by scraping
    the chapter page HTML.  The story ID appears repeatedly as /story/{id}
    in the page source.  This is more reliable than the parts API, which
    does not expose a usable lookup endpoint.
    """
    from collections import Counter

    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        resp = session.get(chapter_url, timeout=(10, 20), allow_redirects=True)
        if resp.status_code == 200:
            matches = re.findall(r"/story/(\d+)", resp.text)
            if matches:
                story_id = Counter(matches).most_common(1)[0][0]
                return str(story_id)
    except requests.exceptions.RequestException:
        pass

    raise WattpadError(
        "That Wattpad link looks like a chapter page, but we couldn't find the story it belongs to. "
        "Try linking to the story's main page instead.",
        technical=f"Could not resolve story ID from chapter URL: {chapter_url}",
    )


# =====================================================
# LOW-LEVEL API HELPERS
# =====================================================

def _get(endpoint, params=None, retries=3):
    """
    GET a Wattpad API endpoint and return parsed JSON.
    Retries on transient failures with a short back-off.
    Raises on permanent failure.
    """
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    session = requests.Session()
    session.headers.update(HEADERS)

    last_exc = None

    for attempt in range(retries):
        try:
            time.sleep(random.uniform(0.5, 1.5))
            response = session.get(url, params=params, timeout=(10, 30))

            if response.status_code == 200:
                return response.json()

            if response.status_code == 404:
                raise WattpadError(
                    "That Wattpad story couldn't be found. "
                    "Double-check the link — the story may have been deleted or set to private.",
                    technical=f"Wattpad 404: {url}",
                )

            if response.status_code == 400:
                # Wattpad uses 400 with error_code 1017 specifically for "story not found"
                try:
                    err_code = response.json().get("error_code")
                except Exception:
                    err_code = None
                if err_code == 1017:
                    raise WattpadError(
                        "That Wattpad story couldn't be found. "
                        "Double-check the link — the story may have been deleted or set to private.",
                        technical=f"Wattpad 400/1017 (NotFound): {url}",
                    )
                # Other 400s are unexpected API errors — don't retry, raise with detail
                raise WattpadError(
                    "Wattpad returned an unexpected error. Please try again in a moment.",
                    technical=f"Wattpad 400: {url} — {response.text[:300]}",
                )

            if response.status_code == 403:
                raise WattpadError(
                    "Wattpad is refusing access to that story. "
                    "It may be private, password-protected, or restricted to logged-in users.",
                    technical=f"Wattpad 403: {url}",
                )

            # 429 / 5xx — back off and retry
            wait = 3 + attempt * 3
            time.sleep(wait)

        except WattpadError:
            raise  # don't swallow intentional errors

        except requests.exceptions.RequestException as exc:
            last_exc = exc
            time.sleep(3 + attempt * 3)

    raise WattpadError(
        "Wattpad didn't respond in time. Their API can be a little unstable — "
        "please try again in a moment, or add your story with an AO3 link using `/fic add` instead.",
        technical=f"Wattpad API timed out after {retries} attempts: {url}",
    ) from last_exc


# =====================================================
# STORY METADATA
# =====================================================

def _fetch_story(story_id):
    """
    Fetch story metadata + chapter list in a single API call.
    Parts are embedded via the 'parts' field — there is no separate /parts endpoint.
    """
    return _get(f"stories/{story_id}", params={"fields": _STORY_FIELDS})


# =====================================================
# CHAPTER COMMENTS  (optional / separate call)
# =====================================================

def fetch_chapter_comments(part_id, limit=20, offset=0):
    """
    Fetch comments for a single chapter (part).

    This is intentionally kept as a standalone function and is NOT
    called during the main parse — use it on-demand (e.g. /fic export-comments).

    Returns a list of comment dicts:
        {
            "id":        int,
            "user":      str,   # username
            "body":      str,   # comment text
            "created":   str,   # ISO datetime string
            "likes":     int,
        }
    """
    data = _get(
        f"parts/{part_id}/comments",
        params={
            "limit":  limit,
            "offset": offset,
            "fields": "comments(id,user,body,created,likes)",
        },
    )

    raw_comments = data.get("comments", [])
    results = []

    for c in raw_comments:
        results.append({
            "id":      c.get("id"),
            "user":    c.get("user", {}).get("name", "Unknown"),
            "body":    c.get("body", ""),
            "created": c.get("created", ""),
            "likes":   c.get("likes", 0),
        })

    return results


# =====================================================
# DATE HELPER
# =====================================================

def _parse_date(raw):
    """
    Normalise a Wattpad datetime string to a plain YYYY-MM-DD date.
    Returns the raw string unchanged if it cannot be parsed.
    """
    if not raw:
        return "Unknown"
    # Wattpad returns ISO 8601: "2023-05-15T10:30:00Z"
    match = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    return match.group(1) if match else raw


# =====================================================
# WORD COUNT (real fetch per chapter)
# =====================================================

def _count_words_in_part(part_id):
    """
    Fetch the HTML text of a single chapter and count words by stripping
    tags and splitting on whitespace.

    Falls back to None on any network/parse failure so the caller can use
    the character-count estimate instead.
    """
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": HEADERS["User-Agent"],
            "Accept-Encoding": "gzip, deflate",
        })
        resp = session.get(
            f"https://www.wattpad.com/apiv2/storytext?id={part_id}",
            timeout=(5, 15),
        )
        if resp.status_code == 200:
            plain = re.sub(r"<[^>]+>", " ", resp.text)
            return len(plain.split())
    except Exception:
        pass
    return None


# =====================================================
# PARSE INTO CLEAN DICT
# =====================================================

def _parse_story(story_data, parts_data, normalized_url):
    """Combine story + parts API responses into a clean result dict."""

    # -- Basic fields --
    title       = story_data.get("title", "Unknown Title").strip()
    description = story_data.get("description", "No description available.").strip()
    mature      = bool(story_data.get("mature", False))
    completed   = bool(story_data.get("completed", False))
    reads       = story_data.get("readCount", 0)
    votes       = story_data.get("voteCount", 0)
    comments    = story_data.get("commentCount", 0)
    story_id    = str(story_data.get("id", ""))

    # -- Author --
    user_obj = story_data.get("user") or {}
    author   = user_obj.get("name", "Unknown Author")

    # -- Cover image — prefer full-size original --
    cover_url = (
        story_data.get("coverOriginal")
        or story_data.get("cover")
        or ""
    )

    # -- Category --
    # "mainCategory" may be localised; "mainCategoryEnglish" is the safe fallback
    category = (
        story_data.get("mainCategoryEnglish")
        or story_data.get("mainCategory")
        or ""
    )

    # -- Tags --
    tags = story_data.get("tags") or []

    # -- Dates --
    last_updated = _parse_date(story_data.get("modifyDate"))
    published    = _parse_date(story_data.get("createDate"))

    # -- Chapters + word count --
    # Fetch real word counts from chapter text. Falls back to char-count
    # estimate (_CHARS_PER_WORD) for any chapter whose text fetch fails.
    chapters = []
    total_word_count = 0

    for i, part in enumerate(parts_data, start=1):
        part_id = part.get("id")
        char_len = part.get("length", 0)

        real_words = _count_words_in_part(part_id) if part_id else None
        part_words = real_words if real_words is not None else round(char_len / _CHARS_PER_WORD)
        total_word_count += part_words

        chapters.append({
            "id":            part_id,
            "number":        i,
            "title":         (part.get("title") or f"Chapter {i}").strip(),
            "word_count":    part_words,
            "comment_count": part.get("commentCount", 0),
            "reads":         part.get("readCount", 0),
            "votes":         part.get("voteCount", 0),
            "published":     _parse_date(part.get("createDate")),
            "last_updated":  _parse_date(part.get("modifyDate")),
        })

    chapter_count = len(chapters) or story_data.get("numParts", 0)

    return {
        "title":         title,
        "author":        author,
        "description":   description,
        "tags":          tags,
        "category":      category,
        "mature":        mature,
        "completed":     completed,
        "word_count":    total_word_count,
        "chapter_count": chapter_count,
        "reads":         reads,
        "votes":         votes,
        "comments":      comments,
        "cover_url":     cover_url,
        "last_updated":  last_updated,
        "published":     published,
        "story_id":      story_id,
        "normalized_url": normalized_url,
        # list of dicts: see chapter schema above
        # comment text is NOT included here — call fetch_chapter_comments(part_id) separately
        "chapters":      chapters,
    }


# =====================================================
# TAGS-ONLY FETCH  (used by /fic build smart tag modal)
# =====================================================

def fetch_wattpad_tags_only(url):
    """
    Fetch tags from a Wattpad story URL.
    Returns a list of tag strings.
    Raises WattpadError if the URL is invalid or no tags are found.
    """
    raw_id, is_part = extract_story_id(url)
    if not raw_id:
        raise WattpadError(
            "That doesn't look like a valid Wattpad link.",
            technical=f"Could not extract any ID from URL: {url}",
        )
    if is_part:
        story_id = _resolve_story_id_from_part(raw_id, url)
    else:
        story_id = raw_id

    data = _get(f"stories/{story_id}", params={"fields": "tags"})
    tags = data.get("tags", [])
    if not tags:
        raise WattpadError("No tags found for this Wattpad story.")
    return tags


# =====================================================
# MAIN ENTRY POINT
# =====================================================

def fetch_wattpad_metadata(url):
    """
    Parse a Wattpad story URL and return a metadata dict.

    Accepts both story page URLs and chapter/part URLs — chapter URLs
    resolve to their parent story automatically via a single extra API call.

    Mirrors fetch_ao3_metadata() in ao3_parser.py.
    Raises WattpadError on invalid URL, 404, or API failure.
    """
    raw_id, is_part = extract_story_id(url)

    if not raw_id:
        raise WattpadError(
            "That doesn't look like a valid Wattpad link. "
            "Please paste the link to your story's main page or any chapter.",
            technical=f"Could not extract any ID from URL: {url}",
        )

    # Chapter URL — resolve part ID → story ID by scraping the chapter page
    if is_part:
        story_id = _resolve_story_id_from_part(raw_id, url)
    else:
        story_id = raw_id

    normalized = f"https://www.wattpad.com/story/{story_id}"

    story_data = _fetch_story(story_id)
    parts_data = story_data.get("parts") or []

    return _parse_story(story_data, parts_data, normalized)
