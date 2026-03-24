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

BASE_URL = "https://www.wattpad.com/api/v3"

# Fields requested from the story endpoint — avoids pulling chapter text etc.
_STORY_FIELDS = ",".join([
    "id", "title", "description", "tags",
    "user", "mature", "completed",
    "numParts", "readCount", "voteCount", "commentCount",
    "cover", "coverOriginal",
    "mainCategory", "mainCategoryEnglish",
    "createDate", "modifyDate",
    "length",
])

# Fields requested per chapter from the parts endpoint
_PARTS_FIELDS = ",".join([
    "id", "title", "length",
    "readCount", "voteCount", "commentCount",
    "createDate", "modifyDate",
])


# =====================================================
# NORMALIZE URL + EXTRACT STORY ID
# =====================================================

def normalize_wattpad_url(url):
    """Return the canonical https://www.wattpad.com/story/{id} URL."""
    story_id = extract_story_id(url)
    if story_id:
        return f"https://www.wattpad.com/story/{story_id}"
    return url


def extract_story_id(url):
    """Extract the numeric story ID from a Wattpad story URL."""
    # Handles:
    #   https://www.wattpad.com/story/123456789-some-slug
    #   https://www.wattpad.com/story/123456789
    #   https://wattpad.com/story/123456789-slug
    match = re.search(r"/story/(\d+)", url)
    return match.group(1) if match else None


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
    """Fetch story-level metadata from the Wattpad API."""
    return _get(f"stories/{story_id}", params={"fields": _STORY_FIELDS})


# =====================================================
# CHAPTERS (PARTS)
# =====================================================

def _fetch_parts(story_id):
    """
    Fetch the chapter list for a story.
    Returns the raw list of part dicts from the API.
    """
    data = _get(
        f"stories/{story_id}/parts",
        params={"fields": f"parts({_PARTS_FIELDS})"},
    )
    # The API wraps the list under a "parts" key
    return data.get("parts", [])


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

    # -- Word count --
    # The story-level "length" field is not always populated by the API,
    # so we sum per-chapter lengths from the parts list as the reliable source.
    word_count = 0
    for part in parts_data:
        word_count += part.get("length", 0)

    # Fall back to story-level length if parts gave us nothing
    if word_count == 0:
        word_count = story_data.get("length", 0)

    # -- Chapters --
    chapters = []
    for i, part in enumerate(parts_data, start=1):
        chapters.append({
            "id":            part.get("id"),
            "number":        i,
            "title":         (part.get("title") or f"Chapter {i}").strip(),
            "word_count":    part.get("length", 0),
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
        "word_count":    word_count,
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
# MAIN ENTRY POINT
# =====================================================

def fetch_wattpad_metadata(url):
    """
    Parse a Wattpad story URL and return a metadata dict.

    Mirrors fetch_ao3_metadata() in ao3_parser.py.

    Raises Exception on invalid URL, 404, or API failure.
    """
    normalized = normalize_wattpad_url(url)
    story_id   = extract_story_id(url)

    if not story_id:
        raise WattpadError(
            "That doesn't look like a valid Wattpad story link. "
            "Make sure it follows the format: `https://www.wattpad.com/story/123456789-story-name`",
            technical=f"Could not extract story ID from URL: {url}",
        )

    story_data = _fetch_story(story_id)
    parts_data = _fetch_parts(story_id)

    return _parse_story(story_data, parts_data, normalized)
