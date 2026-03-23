"""
Cadence — returns today's content pillar and funnel stage based on UTC weekday.
Monday=0, Sunday=6. Schedule loaded from config.json.
"""

from datetime import datetime
from scripts.config_loader import get_config


def get_todays_pillar() -> dict:
    """Return today's pillar, funnel stage, and day name based on UTC."""
    today = datetime.utcnow()
    weekday = str(today.weekday())
    cadence = get_config()["cadence"]
    entry = cadence[weekday]
    return {
        "pillar": entry["pillar"],
        "funnel": entry["funnel"],
        "day": today.strftime("%A"),
    }
