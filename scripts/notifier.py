"""
Notifier — sends system notifications.
Cross-platform: Mac (plyer) and Windows (plyer).
"""

from scripts.config_loader import get_config


def notify(title: str, message: str) -> None:
    """Send a system notification. Falls back to print if plyer unavailable."""
    try:
        from plyer import notification
        notification.notify(title=title, message=message, timeout=15)
    except Exception:
        # Fallback for environments where plyer doesn't work
        print(f"[NOTIFICATION] {title}: {message}")


def notify_posts_ready(count: int) -> None:
    notify(
        title="@{get_config()['handle']} — Posts Ready",
        message=f"{count} post{'s' if count != 1 else ''} ready for review at localhost:3000",
    )


def notify_posts_published(count: int) -> None:
    notify(
        title="@{get_config()['handle']} — Posts Published",
        message=f"{count} post{'s' if count != 1 else ''} published to X.",
    )


def notify_no_approved_posts() -> None:
    notify(
        title="@{get_config()['handle']} — No Posts Queued",
        message="No approved posts to publish today. Nothing was sent.",
    )


def notify_spike(topic: str, suggested_pillar: str, headline_count: int) -> None:
    """Alert Nik that a topic is spiking in the RSS feeds."""
    notify(
        title="@{get_config()['handle']} — Trending Now",
        message=(
            f"{headline_count} headlines on '{topic}' in the last 2 hours. "
            f"Suggested angle: {suggested_pillar}. Check dashboard."
        ),
    )
