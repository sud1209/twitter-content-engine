"""
Dashboard Server — D4
Flask app serving the approval dashboard and REST API at localhost:3000.
"""

import os
import threading
from flask import Flask, jsonify, request, send_from_directory
from scripts.post_queue import load_queue, save_queue, update_post_status

_posts_refresh_status = {"running": False, "done": False, "error": None}
_posts_refresh_lock = threading.Lock()
_regen_statuses = {}  # post_id -> {"status": "running"|"done"|"error", "error": None}


def _run_posts_pipeline():
    with _posts_refresh_lock:
        _posts_refresh_status.update({"running": True, "done": False, "error": None})
    try:
        import uuid
        from scripts.cadence import get_todays_pillar
        from scripts.trend_scanner import get_all_topics, rank_pillars, rank_topics, build_trend_context
        from scripts.content_generator import generate
        from scripts.post_scorer import score_all_posts
        from scripts.post_queue import add_post

        # Clear non-published posts before generating fresh batch
        queue = load_queue()
        queue = [p for p in queue if p["status"] == "published"]
        save_queue(queue)

        today = get_todays_pillar()
        pillar = today["pillar"]
        funnel = today["funnel"]

        # Fetch all topics once — reused for trend context and pillar ranking
        all_topics = get_all_topics()

        # Pick 3 trending non-primary pillars
        trending_pillars = rank_pillars(all_topics, exclude_pillar=pillar, n=3)

        all_posts = []

        # PRIMARY PILLAR: generate 8 candidates, keep top 5
        primary_topics = rank_topics(all_topics, pillar=pillar, n=7)
        if not primary_topics:
            primary_topics = all_topics[:7]
        primary_context = build_trend_context(primary_topics, pillar, funnel)
        primary_drafts = generate(pillar, funnel, primary_context, num_drafts=8)

        primary_candidates = []
        for draft in primary_drafts:
            post = {
                "id": str(uuid.uuid4()),
                "text": draft,
                "pillar": pillar,
                "funnel": funnel,
                "score": None,
                "score_breakdown": None,
                "status": "pending_score",
            }
            primary_candidates.append(post)

        primary_candidates = score_all_posts(primary_candidates)
        primary_candidates.sort(key=lambda p: p.get("score") or 0, reverse=True)
        all_posts.extend(primary_candidates[:5])

        # NON-PRIMARY PILLARS: generate 3 candidates each, keep top 1
        for np_pillar in trending_pillars:
            try:
                np_topics = rank_topics(all_topics, pillar=np_pillar, n=7)
                if not np_topics:
                    np_topics = all_topics[:7]
                np_context = build_trend_context(np_topics, np_pillar, funnel)
                np_drafts = generate(np_pillar, funnel, np_context, num_drafts=3)

                np_candidates = []
                for draft in np_drafts:
                    post = {
                        "id": str(uuid.uuid4()),
                        "text": draft,
                        "pillar": np_pillar,
                        "funnel": funnel,
                        "score": None,
                        "score_breakdown": None,
                        "status": "pending_score",
                    }
                    np_candidates.append(post)

                np_candidates = score_all_posts(np_candidates)
                np_candidates.sort(key=lambda p: p.get("score") or 0, reverse=True)
                all_posts.append(np_candidates[0])
            except Exception as e:
                print(f"Warning: failed to generate post for pillar '{np_pillar}': {e}")

        for post in all_posts:
            add_post(post)

        with _posts_refresh_lock:
            _posts_refresh_status.update({"running": False, "done": True})
    except Exception as e:
        with _posts_refresh_lock:
            _posts_refresh_status.update({"running": False, "done": True, "error": str(e)})

DASHBOARD_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard"))


def create_app() -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def index():
        return send_from_directory(DASHBOARD_DIR, "index.html")

    @app.route("/<path:filename>")
    def static_files(filename):
        return send_from_directory(DASHBOARD_DIR, filename)

    @app.route("/api/config", methods=["GET"])
    def get_config_endpoint():
        from scripts.config_loader import get_config
        cfg = get_config()
        return jsonify({
            "handle": cfg["handle"],
            "display_name": cfg["display_name"],
            "avatar_initial": cfg["avatar_initial"],
            "publish_time_utc": cfg["publish_time_utc"],
        })

    @app.route("/api/posts/today", methods=["GET"])
    def get_posts_today():
        queue = load_queue()
        # Show all non-skipped, non-published posts
        visible = [p for p in queue if p["status"] not in ("skipped", "published")]
        return jsonify(visible)

    @app.route("/api/posts/<post_id>/approve", methods=["POST"])
    def approve_post(post_id):
        update_post_status(post_id, "approved")
        return jsonify({"ok": True})

    @app.route("/api/posts/<post_id>/reject", methods=["POST"])
    def reject_post(post_id):
        update_post_status(post_id, "rejected")
        return jsonify({"ok": True})

    @app.route("/api/posts/<post_id>/unapprove", methods=["POST"])
    def unapprove_post(post_id):
        queue = load_queue()
        for post in queue:
            if post["id"] == post_id:
                post["status"] = "scored" if post.get("score") is not None else "pending"
                save_queue(queue)
                return jsonify({"ok": True})
        return jsonify({"error": "not found"}), 404

    @app.route("/api/posts/<post_id>/edit", methods=["POST"])
    def edit_post(post_id):
        data = request.get_json()
        new_text = data.get("text", "").strip()
        if not new_text:
            return jsonify({"error": "text is required"}), 400

        queue = load_queue()
        for post in queue:
            if post["id"] == post_id:
                post["text"] = new_text
                post["status"] = "pending_score"  # re-score after edit
                post["score"] = None
                post["score_breakdown"] = None
                save_queue(queue)
                _rescore_post(post_id)
                return jsonify({"ok": True})
        return jsonify({"error": "not found"}), 404

    @app.route("/api/posts/<post_id>/regen", methods=["POST"])
    def regen_post(post_id):
        _regen_statuses[post_id] = {"status": "running", "error": None}

        def _regen():
            import uuid
            import re as _re
            from scripts.trend_scanner import run as get_trends
            from scripts.content_generator import generate
            from scripts.post_scorer import regenerate_if_below_floor

            queue = load_queue()
            original = next((p for p in queue if p["id"] == post_id), None)
            if not original:
                _regen_statuses[post_id] = {"status": "error", "error": "Post not found"}
                return
            pillar = original.get("pillar", "")
            funnel = original.get("funnel", "")

            try:
                trend_context = get_trends(pillar=pillar, funnel=funnel)
                trend_context = _re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", trend_context)
                drafts = generate(pillar=pillar, funnel=funnel, trend_context=trend_context)
                if not drafts:
                    _regen_statuses[post_id] = {"status": "error", "error": "Generation returned no drafts"}
                    return
                new_post = {
                    "id": str(uuid.uuid4()),
                    "text": drafts[0],
                    "pillar": pillar,
                    "funnel": funnel,
                    "score": None,
                    "score_breakdown": None,
                    "status": "pending_score",
                }
                new_post = regenerate_if_below_floor(new_post)
            except Exception as e:
                _regen_statuses[post_id] = {"status": "error", "error": str(e)}
                return

            # Generation succeeded — replace in-place at same position
            queue = load_queue()
            for i, p in enumerate(queue):
                if p["id"] == post_id:
                    queue[i] = new_post
                    break
            else:
                queue.append(new_post)
            save_queue(queue)
            _regen_statuses[post_id] = {"status": "done", "error": None}

        threading.Thread(target=_regen, daemon=True).start()
        return jsonify({"ok": True})

    @app.route("/api/posts/<post_id>/regen/status", methods=["GET"])
    def regen_status(post_id):
        status = _regen_statuses.get(post_id, {"status": "unknown", "error": None})
        return jsonify(status)

    @app.route("/api/skip-today", methods=["POST"])
    def skip_today():
        queue = load_queue()
        for post in queue:
            if post["status"] not in ("published",):
                post["status"] = "skipped"
        save_queue(queue)
        return jsonify({"ok": True, "message": "Today's posting skipped."})

    @app.route("/api/performance", methods=["GET"])
    def get_performance():
        queue = load_queue()
        published = [p for p in queue if p["status"] == "published"]
        published.sort(key=lambda p: p.get("published_at", ""), reverse=True)
        return jsonify(published)

    @app.route("/api/posts/generate", methods=["POST"])
    def generate_posts():
        with _posts_refresh_lock:
            if _posts_refresh_status["running"]:
                return jsonify({"ok": False, "error": "Already running"}), 409
            _posts_refresh_status.update({"running": True, "done": False, "error": None})
        t = threading.Thread(target=_run_posts_pipeline, daemon=True)
        t.start()
        return jsonify({"ok": True, "started": True})

    @app.route("/api/posts/generate/status", methods=["GET"])
    def generate_posts_status():
        with _posts_refresh_lock:
            return jsonify(dict(_posts_refresh_status))

    @app.route("/api/playbooks/refresh", methods=["POST"])
    def start_playbook_refresh():
        from scripts.playbook_refresher import run_refresh, get_status, confirm_write, _refresh_status
        data = request.get_json(silent=True) or {}

        # If user is confirming a pending write
        if data.get("confirm"):
            confirm_write()
            return jsonify({"ok": True, "written": True})

        status = get_status()
        if status["running"]:
            return jsonify({"ok": False, "error": "Refresh already running"}), 409

        # Reset and start background job
        import threading
        thread = threading.Thread(target=run_refresh, kwargs={"client_x": None}, daemon=True)
        thread.start()
        return jsonify({"ok": True, "started": True})

    @app.route("/api/playbooks/refresh/status", methods=["GET"])
    def playbook_refresh_status():
        from scripts.playbook_refresher import get_status
        return jsonify(get_status())

    @app.route("/api/playbooks/last-updated", methods=["GET"])
    def playbook_last_updated():
        import glob as _glob
        import time
        playbook_dir = os.path.abspath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "docs", "playbooks"
        ))
        files = _glob.glob(os.path.join(playbook_dir, "*.md"))
        if not files:
            return jsonify({"timestamp": None})
        latest_mtime = max(os.path.getmtime(f) for f in files)
        return jsonify({"timestamp": latest_mtime})

    return app


def _rescore_post(post_id: str) -> None:
    """Re-score a single edited post."""
    import threading
    from scripts.post_scorer import regenerate_if_below_floor
    from scripts.post_queue import load_queue, save_queue

    def rescore():
        queue = load_queue()
        for i, post in enumerate(queue):
            if post["id"] == post_id and post["status"] == "pending_score":
                queue[i] = regenerate_if_below_floor(post)
                save_queue(queue)
                return

    thread = threading.Thread(target=rescore, daemon=True)
    thread.start()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from dotenv import load_dotenv
    load_dotenv()
    port = int(os.getenv("DASHBOARD_PORT", 3000))
    app = create_app()
    print(f"Dashboard running at http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
