"""
pvp/session_manager.py
Thread-safe session store for concurrent PVP games.
Sessions expire after SESSION_TTL seconds of inactivity.
"""

import secrets
import time
import threading
from pvp.engine import GameEngine

SESSION_TTL    = 7200  # 2 hours
CLEANUP_PERIOD = 300   # cleanup check every 5 minutes

_sessions: dict = {}
_lock = threading.Lock()


def create_session(p1_name: str | None = None, p2_name: str | None = None) -> str:
    """Create a new game session and return its ID."""
    sid = secrets.token_urlsafe(8)
    with _lock:
        _sessions[sid] = {
            "engine":      GameEngine(),
            "created_at":  time.time(),
            "last_active": time.time(),
            "p1_name":     p1_name,
            "p2_name":     p2_name,
        }
    return sid


def get_session(sid: str) -> dict | None:
    """Return session dict and bump last_active, or None if expired/missing."""
    with _lock:
        sess = _sessions.get(sid)
        if sess:
            sess["last_active"] = time.time()
        return sess


def active_count() -> int:
    with _lock:
        return len(_sessions)


def _cleanup_loop():
    while True:
        time.sleep(CLEANUP_PERIOD)
        now = time.time()
        with _lock:
            expired = [sid for sid, s in _sessions.items()
                       if now - s["last_active"] > SESSION_TTL]
            for sid in expired:
                del _sessions[sid]


# Start background cleanup thread
threading.Thread(target=_cleanup_loop, daemon=True).start()
