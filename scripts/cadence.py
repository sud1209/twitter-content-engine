"""
Cadence — returns today's content pillar and funnel stage based on UTC weekday.
Monday=0, Sunday=6. Schedule loaded from config.json.

Special values:
  pillar "flex"  -> resolved to the lowest-engagement pillar this week
  funnel "BOFU"  -> falls back to TOFU when newsletter_url is not set in config
"""

from datetime import datetime
from scripts.config_loader import get_config


def get_todays_pillar() -> dict:
    """Return today's resolved pillar, funnel stage, and day name based on UTC."""
    today = datetime.utcnow()
    weekday = str(today.weekday())
    cfg = get_config()
    entry = cfg["cadence"][weekday]

    pillar = entry["pillar"]
    funnel = entry["funnel"]

    # Resolve flex pillar to lowest-engagement pillar
    if pillar == "flex":
        from scripts.performance_analyzer import get_lowest_engagement_pillar
        pillar = get_lowest_engagement_pillar(cfg.get("pillars", [pillar]))

    # BOFU dormancy — fall back to TOFU until newsletter_url is set
    if funnel == "BOFU" and not cfg.get("newsletter_url"):
        funnel = "TOFU"

    return {
        "pillar": pillar,
        "funnel": funnel,
        "day": today.strftime("%A"),
    }
