import re
import requests
import time
import random

from bs4 import BeautifulSoup
from urllib.parse import urlparse


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://archiveofourown.org/",
    "Connection": "keep-alive",
}

AO3_RATINGS = {
    "general audiences",
    "teen and up audiences",
    "mature",
    "explicit",
    "not rated"
}


# =====================================================
# NORMALIZE URL
# =====================================================

def normalize_ao3_url(url):

    parsed = urlparse(url)
    parts = parsed.path.split("/")

    if "works" in parts:
        work_index = parts.index("works")

        if len(parts) > work_index + 1:
            work_id = parts[work_index + 1]
            return f"https://archiveofourown.org/works/{work_id}"

    return url


# =====================================================
# EXTRACT WORK ID
# =====================================================

def extract_work_id(url):

    match = re.search(r"/works/(\d+)", url)
    return match.group(1) if match else None


# =====================================================
# DOWNLOAD HTML
# — Same /downloads/ endpoint AO3 uses for its exports.
# — Single file, no ZIP extraction needed.
# — Contains AO3's official stats block with the real
#   word count and chapter count — no self-counting.
# =====================================================

def download_html(work_id):

    session = requests.Session()
    session.headers.update(HEADERS)

    html_url = (
        f"https://archiveofourown.org/downloads/"
        f"{work_id}/work.html?nocache={int(time.time())}"
    )

    response = None

    for attempt in range(5):

        try:
            time.sleep(random.uniform(1, 4))

            headers = HEADERS.copy()
            headers["Cache-Control"] = "no-cache"
            headers["Pragma"] = "no-cache"

            response = session.get(
                html_url,
                headers=headers,
                timeout=(10, 120),
                allow_redirects=True
            )

            if response.status_code == 200:
                # Sanity-check: AO3 HTML exports always contain this string
                if b"archiveofourown.org" in response.content[:2000]:
                    break
                # Got 200 but looks like a Cloudflare challenge page — retry
                response = None

        except requests.exceptions.RequestException:
            response = None

        time.sleep(4 + attempt * 2)

    if not response or response.status_code != 200:
        raise Exception("AO3 blocked or timed out while downloading HTML export.")

    return response.content.decode("utf-8", errors="replace")


# =====================================================
# PARSE METADATA FROM AO3 HTML EXPORT
# =====================================================

def parse_ao3_html(html_text, normalized_url):

    soup = BeautifulSoup(html_text, "html.parser")

    # ------------------------------------------------
    # TITLE
    # ------------------------------------------------
    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"

    # ------------------------------------------------
    # AUTHOR
    # ------------------------------------------------
    author_tag = soup.find("a", rel="author")
    author = author_tag.get_text(strip=True) if author_tag else "Unknown Author"

    # ------------------------------------------------
    # SUMMARY (work-level)
    # ------------------------------------------------
    summary = "No summary available."
    summary_p = soup.find("p", string="Summary")
    if summary_p:
        bq = summary_p.find_next_sibling("blockquote")
        if bq:
            # Join paragraphs with double newline so Discord shows
            # visible spacing between them, matching AO3's layout.
            paragraphs = [p.get_text(strip=True) for p in bq.find_all("p") if p.get_text(strip=True)]
            summary = "\n\n".join(paragraphs) if paragraphs else bq.get_text("\n", strip=True)

    # ------------------------------------------------
    # STATS — trust AO3's numbers, never self-count
    # ------------------------------------------------
    word_count = 0
    chapter_count = 0
    last_updated = "Unknown"
    rating = "Not Rated"
    # hits / kudos / comments / bookmarks are fetched separately
    # from the live work page in fetch_ao3_metadata()

    for dt in soup.find_all("dt"):

        label = dt.get_text(strip=True).rstrip(":")
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue

        dd_text = dd.get_text()

        if label == "Stats":
            words_match = re.search(r"Words:\s*([\d,]+)", dd_text)
            if words_match:
                word_count = int(words_match.group(1).replace(",", ""))

            ch_match = re.search(r"Chapters:\s*(\d+)", dd_text)
            if ch_match:
                chapter_count = int(ch_match.group(1))

            # prefer Updated date; fall back to Published
            upd_match = re.search(r"Updated:\s*([\d-]+)", dd_text)
            if upd_match:
                last_updated = upd_match.group(1)
            else:
                pub_match = re.search(r"Published:\s*([\d-]+)", dd_text)
                if pub_match:
                    last_updated = pub_match.group(1)

        elif label == "Rating":
            rating_text = dd.get_text(strip=True)
            if rating_text.lower() in AO3_RATINGS:
                rating = rating_text

    # ------------------------------------------------
    # TAGS
    # ------------------------------------------------
    tags = []
    seen = set()

    for dt in soup.find_all("dt"):
        label = dt.get_text(strip=True).rstrip(":")
        if label in ("Additional Tags", "Relationships", "Characters", "Fandoms"):
            dd = dt.find_next_sibling("dd")
            if dd:
                for a in dd.find_all("a"):
                    tag = a.get_text(strip=True)
                    if tag and tag not in seen:
                        seen.add(tag)
                        tags.append(tag)

    # ------------------------------------------------
    # CHAPTERS — names and summaries
    # h2.heading = "Chapter N: Title"
    # followed optionally by <p>Chapter Summary</p>
    # and a <blockquote> with the summary text.
    # ------------------------------------------------
    chapters = []

    for heading in soup.find_all("h2", class_="heading"):
        raw_title = heading.get_text(strip=True)

        num_match = re.match(r"Chapter\s+(\d+)[:\s]*(.*)", raw_title)
        if num_match:
            ch_num = int(num_match.group(1))
            ch_name = num_match.group(2).strip() or f"Chapter {ch_num}"
        else:
            ch_num = len(chapters) + 1
            ch_name = raw_title

        # Chapter-level summary
        chapter_summary = None
        parent = heading.parent
        summary_label = parent.find("p", string="Chapter Summary")
        if summary_label:
            bq = summary_label.find_next_sibling("blockquote")
            if bq:
                chapter_summary = bq.get_text("\n", strip=True)

        chapters.append({
            "number": ch_num,
            "title": ch_name,
            "summary": chapter_summary,
        })

    # If AO3 stats chapter count > headings found, trust headings
    # (partial exports, ongoing fics, etc.)
    if len(chapters) > 0:
        chapter_count = max(chapter_count, len(chapters))

    return {
        "title": title,
        "author": author,
        "summary": summary,
        "word_count": word_count,
        "chapter_count": chapter_count,
        "last_updated": last_updated,
        "normalized_url": normalized_url,
        "rating": rating,
        "tags": tags,
        # hits / kudos / comments / bookmarks injected by fetch_ao3_metadata()
        # list of dicts: {"number": 1, "title": "Sylva Skies", "summary": "..."}
        "chapters": chapters,
    }


# =====================================================
# LIVE STATS  (hits / kudos / comments / bookmarks)
# — The HTML export doesn't include engagement stats,
#   so we fetch them from the live work page instead.
# =====================================================

def _fetch_live_stats(work_id):
    """
    Scrape hits, kudos, comments, bookmarks from the live AO3 work page.
    Returns a dict with those four keys (0 if not found).
    Silently returns all-zeros on any error so a network blip
    doesn't break the whole add/refresh flow.
    """
    stats = {"hits": 0, "kudos": 0, "comments": 0, "bookmarks": 0}
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        resp = session.get(
            f"https://archiveofourown.org/works/{work_id}?view_adult=true",
            timeout=(10, 30),
        )
        if resp.status_code != 200:
            return stats
        soup = BeautifulSoup(resp.content, "html.parser")
        dl = soup.find("dl", class_="stats")
        if not dl:
            return stats
        for dt in dl.find_all("dt"):
            label = dt.get_text(strip=True).rstrip(":")
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            raw = dd.get_text(strip=True).replace(",", "")
            if not raw.isdigit():
                continue
            v = int(raw)
            if label == "Hits":       stats["hits"]      = v
            elif label == "Kudos":    stats["kudos"]     = v
            elif label == "Comments": stats["comments"]  = v
            elif label == "Bookmarks":stats["bookmarks"] = v
    except Exception:
        pass
    return stats


# =====================================================
# MAIN ENTRY POINT (called by add_worker and future
# updatefic worker)
# =====================================================

def fetch_ao3_metadata(url):

    normalized = normalize_ao3_url(url)
    work_id = extract_work_id(normalized)

    if not work_id:
        raise Exception("Invalid AO3 URL — could not extract work ID.")

    html_text = download_html(work_id)
    data = parse_ao3_html(html_text, normalized)

    live = _fetch_live_stats(work_id)
    data["hits"]      = live["hits"]
    data["kudos"]     = live["kudos"]
    data["comments"]  = live["comments"]
    data["bookmarks"] = live["bookmarks"]

    return data
