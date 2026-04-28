"""
pvp/server.py
Multi-session PVP web server.

  python pvp/server.py

Then open http://localhost:5051 in your browser, or use /pvp challenge on Discord.
Set PVP_PUBLIC_URL and PVP_PORT in your .env for production.
"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, jsonify, request, send_from_directory, render_template, redirect
from pvp.session_manager import create_session, get_session, active_count
from pvp.cards import ALL_CARDS

app = Flask(__name__,
            template_folder="templates",
            static_folder="static")

IMAGES_DIR = os.path.join(os.path.dirname(__file__), "..", "images")


# ── Static assets ──────────────────────────────────────────────────────────────

@app.route("/images/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGES_DIR, filename)


# ── Pages ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Root: create a fresh local session and redirect into it."""
    sid = create_session()
    return redirect(f"/game/{sid}")


@app.route("/game/<sid>")
def game_page(sid):
    sess = get_session(sid)
    if not sess:
        return render_template("expired.html"), 404
    return render_template(
        "game.html",
        session_id=sid,
        p1_name=sess.get("p1_name") or "",
        p2_name=sess.get("p2_name") or "",
    )


# ── Internal management API ────────────────────────────────────────────────────

@app.route("/api/create_session", methods=["POST"])
def api_create_session():
    """Called by the Discord bot to spin up a new session."""
    data   = request.json or {}
    p1     = (data.get("p1_name") or "").strip() or None
    p2     = (data.get("p2_name") or "").strip() or None
    sid    = create_session(p1_name=p1, p2_name=p2)
    public = os.getenv("PVP_PUBLIC_URL", "http://localhost:5051")
    return jsonify({
        "session_id":      sid,
        "url":             f"{public}/game/{sid}",
        "active_sessions": active_count(),
    })


@app.route("/api/status")
def api_status():
    return jsonify({"status": "ok", "active_sessions": active_count()})


# ── Per-session API helpers ────────────────────────────────────────────────────

def _sess_or_err(sid):
    sess = get_session(sid)
    if not sess:
        return None, (jsonify({"error": "Session not found or expired."}), 404)
    return sess, None


# ── Per-session routes ─────────────────────────────────────────────────────────

@app.route("/api/<sid>/state")
def api_state(sid):
    sess, err = _sess_or_err(sid)
    if err: return err
    return jsonify(sess["engine"].get_state())


@app.route("/api/<sid>/cards")
def api_cards(sid):
    return jsonify(list(ALL_CARDS.values()))


@app.route("/api/<sid>/new_game", methods=["POST"])
def api_new_game(sid):
    sess, err = _sess_or_err(sid)
    if err: return err
    data = request.json or {}
    p1_name     = (data.get("p1_name") or sess.get("p1_name") or "Player 1").strip() or "Player 1"
    p1_affinity = data.get("p1_affinity", "fire")
    p2_name     = (data.get("p2_name") or sess.get("p2_name") or "Player 2").strip() or "Player 2"
    p2_affinity = data.get("p2_affinity", "ice")
    valid = {"fire", "ice", "lightning"}
    if p1_affinity not in valid: p1_affinity = "fire"
    if p2_affinity not in valid: p2_affinity = "ice"
    state = sess["engine"].new_game(p1_name, p1_affinity, p2_name, p2_affinity)
    return jsonify(state)


@app.route("/api/<sid>/action", methods=["POST"])
def api_action(sid):
    sess, err = _sess_or_err(sid)
    if err: return err
    engine = sess["engine"]
    data   = request.json or {}
    action = data.get("action", "")
    player = int(data.get("player", 0))

    if   action == "select_character":
        result = engine.select_character(player, int(data.get("char_index", 0)))
    elif action == "play_card":
        result = engine.play_card(player, data.get("card_id", ""))
    elif action == "draw_card":
        result = engine.draw_card(player)
    elif action == "discard_card":
        result = engine.discard_card(player, data.get("card_id", ""))
    elif action == "end_turn":
        result = engine.end_turn(player)
    else:
        result = {"error": f"Unknown action: {action}"}

    return jsonify(result)


if __name__ == "__main__":
    port = int(os.getenv("PVP_PORT", 5051))
    print("=" * 60)
    print("  SapheroBot PVP — Multi-Session Game Server")
    print(f"  Local:  http://localhost:{port}")
    print(f"  Public: {os.getenv('PVP_PUBLIC_URL', '(set PVP_PUBLIC_URL in .env)')}")
    print("  Ctrl+C to stop")
    print("=" * 60)
    app.run(host="0.0.0.0", debug=False, port=port, use_reloader=False)
