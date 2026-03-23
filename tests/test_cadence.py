def test_monday_returns_ai_innovations(monkeypatch):
    monkeypatch.setattr("scripts.cadence.get_config", lambda: {
        "cadence": {"0": {"pillar": "AI Innovations", "funnel": "TOFU"}},
        "pillars": ["AI Innovations", "Sports & Cricket", "eSports & Dota 2",
                    "Literature", "Gaming & Experimental Cooking"],
        "newsletter_url": "",
    })
    monkeypatch.setattr("scripts.cadence.datetime",
        type("FakeDT", (), {"utcnow": staticmethod(
            lambda: __import__("datetime").datetime(2026, 3, 23))})())
    from scripts.cadence import get_todays_pillar
    result = get_todays_pillar()
    assert result["pillar"] == "AI Innovations"
    assert result["funnel"] == "TOFU"
    assert result["day"] == "Monday"


def test_tuesday_returns_sports_cricket(monkeypatch):
    monkeypatch.setattr("scripts.cadence.get_config", lambda: {
        "cadence": {"1": {"pillar": "Sports & Cricket", "funnel": "MOFU"}},
        "pillars": ["AI Innovations", "Sports & Cricket", "eSports & Dota 2",
                    "Literature", "Gaming & Experimental Cooking"],
        "newsletter_url": "",
    })
    monkeypatch.setattr("scripts.cadence.datetime",
        type("FakeDT", (), {"utcnow": staticmethod(
            lambda: __import__("datetime").datetime(2026, 3, 24))})())
    from scripts.cadence import get_todays_pillar
    result = get_todays_pillar()
    assert result["pillar"] == "Sports & Cricket"
    assert result["funnel"] == "MOFU"
    assert result["day"] == "Tuesday"


def test_wednesday_returns_esports_dota2(monkeypatch):
    monkeypatch.setattr("scripts.cadence.get_config", lambda: {
        "cadence": {"2": {"pillar": "eSports & Dota 2", "funnel": "TOFU"}},
        "pillars": ["AI Innovations", "Sports & Cricket", "eSports & Dota 2",
                    "Literature", "Gaming & Experimental Cooking"],
        "newsletter_url": "",
    })
    monkeypatch.setattr("scripts.cadence.datetime",
        type("FakeDT", (), {"utcnow": staticmethod(
            lambda: __import__("datetime").datetime(2026, 3, 25))})())
    from scripts.cadence import get_todays_pillar
    result = get_todays_pillar()
    assert result["pillar"] == "eSports & Dota 2"
    assert result["funnel"] == "TOFU"
    assert result["day"] == "Wednesday"


def test_thursday_returns_literature(monkeypatch):
    monkeypatch.setattr("scripts.cadence.get_config", lambda: {
        "cadence": {"3": {"pillar": "Literature", "funnel": "MOFU"}},
        "pillars": ["AI Innovations", "Sports & Cricket", "eSports & Dota 2",
                    "Literature", "Gaming & Experimental Cooking"],
        "newsletter_url": "",
    })
    monkeypatch.setattr("scripts.cadence.datetime",
        type("FakeDT", (), {"utcnow": staticmethod(
            lambda: __import__("datetime").datetime(2026, 3, 26))})())
    from scripts.cadence import get_todays_pillar
    result = get_todays_pillar()
    assert result["pillar"] == "Literature"
    assert result["funnel"] == "MOFU"
    assert result["day"] == "Thursday"


def test_friday_returns_gaming_experimental_cooking(monkeypatch):
    monkeypatch.setattr("scripts.cadence.get_config", lambda: {
        "cadence": {"4": {"pillar": "Gaming & Experimental Cooking", "funnel": "TOFU"}},
        "pillars": ["AI Innovations", "Sports & Cricket", "eSports & Dota 2",
                    "Literature", "Gaming & Experimental Cooking"],
        "newsletter_url": "",
    })
    monkeypatch.setattr("scripts.cadence.datetime",
        type("FakeDT", (), {"utcnow": staticmethod(
            lambda: __import__("datetime").datetime(2026, 3, 27))})())
    from scripts.cadence import get_todays_pillar
    result = get_todays_pillar()
    assert result["pillar"] == "Gaming & Experimental Cooking"
    assert result["funnel"] == "TOFU"
    assert result["day"] == "Friday"


def test_saturday_returns_ai_innovations_mofu(monkeypatch):
    monkeypatch.setattr("scripts.cadence.get_config", lambda: {
        "cadence": {"5": {"pillar": "AI Innovations", "funnel": "MOFU"}},
        "pillars": ["AI Innovations", "Sports & Cricket", "eSports & Dota 2",
                    "Literature", "Gaming & Experimental Cooking"],
        "newsletter_url": "",
    })
    monkeypatch.setattr("scripts.cadence.datetime",
        type("FakeDT", (), {"utcnow": staticmethod(
            lambda: __import__("datetime").datetime(2026, 3, 28))})())
    from scripts.cadence import get_todays_pillar
    result = get_todays_pillar()
    assert result["pillar"] == "AI Innovations"
    assert result["funnel"] == "MOFU"
    assert result["day"] == "Saturday"


def test_sunday_returns_ai_innovations_flex(monkeypatch):
    # Sunday is flex in final config; test with direct pillar for now
    # (flex resolution logic is added in Task 5)
    monkeypatch.setattr("scripts.cadence.get_config", lambda: {
        "cadence": {"6": {"pillar": "AI Innovations", "funnel": "TOFU"}},
        "pillars": ["AI Innovations", "Sports & Cricket", "eSports & Dota 2",
                    "Literature", "Gaming & Experimental Cooking"],
        "newsletter_url": "",
    })
    monkeypatch.setattr("scripts.cadence.datetime",
        type("FakeDT", (), {"utcnow": staticmethod(
            lambda: __import__("datetime").datetime(2026, 3, 22))})())
    from scripts.cadence import get_todays_pillar
    result = get_todays_pillar()
    assert result["pillar"] == "AI Innovations"
    assert result["funnel"] == "TOFU"
    assert result["day"] == "Sunday"


# --- flex pillar resolution ---

def test_flex_pillar_resolves_to_lowest_engagement(monkeypatch):
    """When cadence entry is 'flex', get_todays_pillar resolves to lowest-engagement pillar."""
    # Import performance_analyzer first so it's in sys.modules before patching
    import scripts.performance_analyzer  # noqa: F401
    monkeypatch.setattr(
        "scripts.performance_analyzer.get_lowest_engagement_pillar",
        lambda pillars: "Literature",
    )
    monkeypatch.setattr(
        "scripts.cadence.get_config",
        lambda: {
            "cadence": {"6": {"pillar": "flex", "funnel": "TOFU"}},
            "pillars": ["AI Innovations", "Literature"],
            "newsletter_url": "",
        },
    )
    monkeypatch.setattr(
        "scripts.cadence.datetime",
        type("FakeDT", (), {"utcnow": staticmethod(lambda: __import__("datetime").datetime(2026, 3, 22))})(),
    )
    from scripts.cadence import get_todays_pillar
    result = get_todays_pillar()
    assert result["pillar"] == "Literature"
    assert result["funnel"] == "TOFU"


def test_non_flex_pillar_unchanged(monkeypatch):
    """Non-flex pillars are returned as-is."""
    monkeypatch.setattr(
        "scripts.cadence.get_config",
        lambda: {
            "cadence": {"0": {"pillar": "AI Innovations", "funnel": "TOFU"}},
            "pillars": ["AI Innovations", "Literature"],
            "newsletter_url": "",
        },
    )
    monkeypatch.setattr(
        "scripts.cadence.datetime",
        type("FakeDT", (), {"utcnow": staticmethod(lambda: __import__("datetime").datetime(2026, 3, 23))})(),
    )
    from scripts.cadence import get_todays_pillar
    result = get_todays_pillar()
    assert result["pillar"] == "AI Innovations"


# --- BOFU dormancy ---

def test_bofu_falls_back_to_tofu_when_newsletter_url_empty(monkeypatch):
    """BOFU funnel falls back to TOFU when newsletter_url is not set."""
    monkeypatch.setattr(
        "scripts.cadence.get_config",
        lambda: {
            "cadence": {"4": {"pillar": "Literature", "funnel": "BOFU"}},
            "pillars": ["AI Innovations", "Literature"],
            "newsletter_url": "",
        },
    )
    monkeypatch.setattr(
        "scripts.cadence.datetime",
        type("FakeDT", (), {"utcnow": staticmethod(lambda: __import__("datetime").datetime(2026, 3, 20))})(),
    )
    from scripts.cadence import get_todays_pillar
    result = get_todays_pillar()
    assert result["funnel"] == "TOFU"


def test_bofu_active_when_newsletter_url_set(monkeypatch):
    """BOFU funnel is preserved when newsletter_url is set."""
    monkeypatch.setattr(
        "scripts.cadence.get_config",
        lambda: {
            "cadence": {"4": {"pillar": "Literature", "funnel": "BOFU"}},
            "pillars": ["AI Innovations", "Literature"],
            "newsletter_url": "https://sud.substack.com",
        },
    )
    monkeypatch.setattr(
        "scripts.cadence.datetime",
        type("FakeDT", (), {"utcnow": staticmethod(lambda: __import__("datetime").datetime(2026, 3, 20))})(),
    )
    from scripts.cadence import get_todays_pillar
    result = get_todays_pillar()
    assert result["funnel"] == "BOFU"
