"""
Config Loader — reads config.json from project root.
All scripts import get_config() instead of hardcoding user-specific values.
"""

import json
import os

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"
)

_config: dict | None = None


def get_config() -> dict:
    global _config
    if _config is None:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            _config = json.load(f)
    return _config
