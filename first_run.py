#!/usr/bin/env python3
"""
One-click setup wizard for the Twitter/X content engine.
Run this once after cloning. Never run again unless resetting.
"""

import os
import subprocess
import sys
import webbrowser
import threading
import time

REQUIRED_KEYS = [
    ("X_CONSUMER_KEY",        "X API Consumer Key"),
    ("X_CONSUMER_SECRET",     "X API Consumer Secret"),
    ("X_BEARER_TOKEN",        "X API Bearer Token"),
    ("X_ACCESS_TOKEN",        "X API Access Token"),
    ("X_ACCESS_TOKEN_SECRET", "X API Access Token Secret"),
    ("OPENAI_API_KEY",        "OpenAI API Key"),
]


def install_dependencies():
    print("\nInstalling dependencies...")
    subprocess.check_call(["uv", "sync"])
    print("Dependencies installed.")


def collect_api_keys() -> dict:
    """Serve a browser form to collect API keys."""
    from flask import Flask, request, jsonify, render_template_string

    app = Flask(__name__)
    keys_collected = {}
    done_event = threading.Event()

    form_html = """
    <!DOCTYPE html>
    <html>
    <head>
      <title>Content Engine Setup</title>
      <style>
        body { font-family: -apple-system, sans-serif; max-width: 560px; margin: 60px auto; padding: 0 20px; }
        h1 { font-size: 1.3rem; margin-bottom: 8px; }
        p { color: #555; margin-bottom: 24px; font-size: 0.9rem; }
        label { display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 4px; margin-top: 16px; }
        input { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 6px; font-size: 0.9rem; }
        button { margin-top: 24px; padding: 12px 24px; background: #000; color: #fff; border: none; border-radius: 6px; font-size: 1rem; cursor: pointer; width: 100%; }
        .success { color: #28a745; font-weight: 600; margin-top: 20px; text-align: center; }
      </style>
    </head>
    <body>
      <h1>Content Engine Setup</h1>
      <p>Enter your API keys below. These are saved locally to .env and never shared.</p>
      <form id="setup-form">
        {% for key, label in keys %}
        <label>{{ label }}</label>
        <input type="text" name="{{ key }}" placeholder="{{ key }}" required>
        {% endfor %}
        <button type="submit">Save and Start</button>
      </form>
      <div id="msg"></div>
      <script>
        document.getElementById('setup-form').onsubmit = async (e) => {
          e.preventDefault();
          const data = Object.fromEntries(new FormData(e.target));
          const res = await fetch('/save-keys', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data) });
          const json = await res.json();
          document.getElementById('msg').innerHTML = '<p class="success">Setup complete. You can close this window.</p>';
        };
      </script>
    </body>
    </html>
    """

    @app.route("/")
    def index():
        return render_template_string(form_html, keys=REQUIRED_KEYS)

    @app.route("/save-keys", methods=["POST"])
    def save_keys():
        data = request.get_json()
        keys_collected.update(data)
        done_event.set()
        return jsonify({"ok": True})

    def run_server():
        app.run(host="127.0.0.1", port=3001, debug=False)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    time.sleep(1)

    webbrowser.open("http://localhost:3001")
    print("Browser opened for API key entry. Waiting...")
    done_event.wait()
    return keys_collected


def write_env_file(keys: dict) -> None:
    lines = []
    for key, _ in REQUIRED_KEYS:
        lines.append(f"{key}={keys.get(key, '')}")
    lines += [
        "POST_TIME_UTC=15:30",
        "DASHBOARD_PORT=3000",
    ]
    with open(".env", "w") as f:
        f.write("\n".join(lines))
    print(".env file written.")


def register_mcp_for_claude_desktop() -> None:
    """Add OpenClaw as MCP server in Claude Desktop config if it exists."""
    import json
    import platform

    if platform.system() == "Darwin":
        config_path = os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")
    elif platform.system() == "Windows":
        config_path = os.path.expandvars(r"%APPDATA%\Claude\claude_desktop_config.json")
    else:
        print("MCP registration: unsupported OS, skipping.")
        return

    if not os.path.exists(config_path):
        print(f"Claude Desktop config not found at {config_path}. Skipping MCP registration.")
        return

    with open(config_path) as f:
        config = json.load(f)

    cwd = os.path.abspath(".")
    config.setdefault("mcpServers", {})["twitter-content-engine"] = {
        "command": "python",
        "args": [os.path.join(cwd, "scripts", "server.py")],
        "env": {"PYTHONPATH": cwd},
    }

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print("OpenClaw registered as MCP server in Claude Desktop.")


if __name__ == "__main__":
    print("=== Content Engine Setup ===\n")
    install_dependencies()
    keys = collect_api_keys()
    write_env_file(keys)
    register_mcp_for_claude_desktop()

    print("\nSetup complete.")
    print("To start the content engine, run:")
    print("  uv run python scripts/scheduler.py   (keeps running in background)")
    print("  uv run python scripts/server.py      (dashboard at http://localhost:3000)")
