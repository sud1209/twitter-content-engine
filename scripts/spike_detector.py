"""
Spike Detector — Feature 4: Trend Spike Alerts
Monitors RSS headline volume and fires alerts when a keyword appears
threshold or more times within a rolling window.

Log structure:
  {
    "headlines": [{"title": str, "timestamp": ISO str, "source": str}],
    "alerts": {"keyword": ISO timestamp str}
  }
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional

SPIKE_LOG_PATH = "data/spike_log.json"

# Pillar mapping: (list of trigger words) -> pillar name
PILLAR_MAP = [
    (["mortgage", "lending", "loan"], "Non-QM Lending Optimization"),
    (["real estate", "housing", "property"], "AI for Real Estate"),
    (["ai", "automation", "agent"], "CEO/Founder AI Productivity"),
]
DEFAULT_PILLAR = "Industry Crossovers"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_log() -> dict:
    """Load spike log from disk; return empty structure if missing or corrupt."""
    path = SPIKE_LOG_PATH  # read at call-time so monkeypatch works
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "headlines" not in data:
                data["headlines"] = []
            if "alerts" not in data:
                data["alerts"] = {}
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"headlines": [], "alerts": {}}


def _save_log(data: dict) -> None:
    """Persist spike log to disk."""
    path = SPIKE_LOG_PATH
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _suggest_pillar(keyword: str) -> str:
    """Map a keyword to its nearest content pillar."""
    kw_lower = keyword.lower()
    for triggers, pillar in PILLAR_MAP:
        for trigger in triggers:
            if trigger in kw_lower:
                return pillar
    return DEFAULT_PILLAR


def _significant_words(text: str) -> list[str]:
    """Return words longer than 4 characters from text (lower-cased)."""
    return [w.strip(".,!?\"'():;").lower() for w in text.split() if len(w.strip(".,!?\"'():;")) > 4]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def record_headlines(topics: list[dict]) -> None:
    """
    Append topics to the rolling headline log, then prune entries older than
    7 days.  Reads/writes SPIKE_LOG_PATH.
    """
    log = _load_log()
    now = datetime.utcnow().isoformat()

    for topic in topics:
        log["headlines"].append({
            "title": topic.get("title", ""),
            "timestamp": now,
            "source": topic.get("source", ""),
        })

    # Prune entries older than 7 days
    cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
    log["headlines"] = [h for h in log["headlines"] if h.get("timestamp", "") >= cutoff]

    _save_log(log)


def detect_spike(topics: list[dict], window_hours: int = 2, threshold: int = 3) -> list[dict]:
    """
    Detect keyword spikes in *topics*.

    A headline "matches" a keyword cluster if any word in the keyword that has
    >4 characters appears in the headline title (case-insensitive).

    Groups are formed from the significant words found across all topic titles.
    Returns a list of dicts with: keyword, count, headlines, suggested_pillar.
    Only groups where count >= threshold are returned.
    """
    if not topics:
        return []

    # Build a vocabulary of candidate keywords from the titles
    # Each unique significant word becomes a candidate keyword
    candidate_words: set[str] = set()
    for topic in topics:
        candidate_words.update(_significant_words(topic.get("title", "")))

    clusters: dict[str, dict] = {}
    for word in candidate_words:
        matching_headlines = []
        for topic in topics:
            title_lower = topic.get("title", "").lower()
            if word in title_lower:
                matching_headlines.append(topic.get("title", ""))
        if len(matching_headlines) >= threshold:
            # Use the longest existing cluster key that subsumes this word,
            # or create a new one.  Simple approach: one entry per word.
            clusters[word] = {
                "keyword": word,
                "count": len(matching_headlines),
                "headlines": matching_headlines,
                "suggested_pillar": _suggest_pillar(word),
            }

    return list(clusters.values())


def get_cooldown_active(keyword: str, cooldown_hours: int = 6) -> bool:
    """
    Return True if an alert for *keyword* was fired within the last
    *cooldown_hours* hours.
    """
    log = _load_log()
    alerts = log.get("alerts", {})
    last_alerted_str = alerts.get(keyword)
    if not last_alerted_str:
        return False
    last_alerted = datetime.fromisoformat(last_alerted_str)
    return datetime.utcnow() - last_alerted < timedelta(hours=cooldown_hours)


def mark_alerted(keyword: str) -> None:
    """Record that an alert for *keyword* was just fired."""
    log = _load_log()
    log["alerts"][keyword] = datetime.utcnow().isoformat()
    _save_log(log)
