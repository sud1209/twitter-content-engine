"""
Post Scorer — D3
Batch-scores draft posts using Claude as judge. Max 5 API calls for any N posts.
Usage: python -m scripts.post_scorer
"""

import json
import os
import uuid

from dotenv import load_dotenv

from scripts.cadence import get_todays_pillar
from scripts.content_generator import generate
from scripts.llm_client import complete as llm_complete
from scripts.post_queue import load_queue, save_queue
from scripts.trend_scanner import run as get_trends

load_dotenv()

GEN_MODEL_KEY = "scoring"  # reads config["models"]["scoring"]
MAX_REGENERATION_ATTEMPTS = 2
QUALITY_FLOOR = 8.0
TARGET_THRESHOLD = 9.25

DIMENSIONS = [
    {"key": "hook_strength",           "weight": 25,
     "description": "Harry Dry 3 tests: Can I visualize it? Can I falsify it? Can nobody else say this? "
                    "All 3 must pass for 9+. Vague claims or clichés = 5/10 max."},
    {"key": "tone_compliance",         "weight": 20,
     "description": "Six Core Laws (Direct, Data-First, Casual Confidence, Outcome-First, Business Casual, Equal Status). "
                    "ZERO hashtags, ZERO emdashes, ZERO exclamation marks, ZERO hedging ('seems','could','might'). "
                    "Any hashtag = 0/10. Score 9+ only if flawless."},
    {"key": "x_algorithm_optimization","weight": 20,
     "description": "Reply=27x like, Repost=20x like. 9+ requires: ZERO hashtags + specific falsifiable claim "
                    "that makes someone want to publicly argue back. DM CTA alone = 7. "
                    "Bold contestable claim with data = 9+."},
    {"key": "data_specificity",        "weight": 15,
     "description": "Must cite real numbers, named people/products, or concrete outcomes. "
                    "Abstract claims = 6/10 max. Specific data = 9+/10."},
    {"key": "pillar_alignment",        "weight": 15,
     "description": "Reader should know the content pillar in the first sentence. "
                    "Vague or generic opener = 6/10 max. Score 9+ only if pillar is unmistakable immediately."},
    {"key": "cta_quality",             "weight": 5,
     "description": "TOFU only: awareness/follow/debate-bait CTAs score highest. "
                    "No hard sell, no newsletter push, no link drop. "
                    "Soft engagement (reply, follow) or a bold claim with no explicit CTA = 8+. "
                    "DM push = 5."},
]

SCORING_RUBRIC = """Score each post on 6 dimensions (0-10 integers). Use X Algorithm weights: Reply=27x like, Repost=20x like.

hook_strength (25%): Harry Dry 3 tests — visualizable, falsifiable, nobody else can say this. 9+ only if all 3 pass. Generic = 5 max.
tone_compliance (20%): Six Core Laws + ZERO hashtags/emdashes/exclamation marks/hedging. Any hashtag = 0. 9+ if flawless.
x_algorithm_optimization (20%): 9+ = ZERO hashtags + specific falsifiable claim someone argues back at. DM CTA alone = 7. Debate-bait + data = 9+.
data_specificity (15%): Named people/products, concrete numbers, falsifiable outcomes. Abstract claim = 6 max.
pillar_alignment (15%): Pillar clear in first sentence. Vague opener = 6 max. Score 9+ only if pillar is unmistakable.
cta_quality (5%): TOFU. No hard sell, no link drop. Bold claim or follow invite = 8+. DM push = 5.

CRITICAL: If post contains ANY hashtag (#), mark never_list_violation = true."""

REGEN_HARD_RULES = """HARD RULES (NON-NEGOTIABLE):
- ZERO hashtags. EVER.
- ZERO exclamation marks (!)
- ZERO em-dashes (—). Use periods or colons.
- No soft CTAs: "What's your...", "How are you...", "Thoughts?", "Let's discuss"
- No cheesy openers: "Imagine", "Let's dive in", "Let's explore"
- No banned words: streamline, transformative, unlock, ecosystem, landscape, game-changer
- TOFU only: awareness/follow/debate-bait CTAs. No DM asks, no links.

REFRAME WEAK HOOKS using one of:
- COMPETITIVE DISADVANTAGE: "If you're still [old way], your competitors are beating you [specific way]."
- TRUTH NOBODY ADMITS: "The real reason [authority] won't discuss [topic] is [specific truth]."
- TIMESTAMP OBSOLESCENCE: "Anyone still [old way] in 2026 is [consequence]. The ones who shifted to [new way] are [winning how]."
- INVERSE RISK: "People think [common belief] is risky. Real risk is [opposite]. [Data]."
"""


def _get_scoring_model() -> str:
    from scripts.config_loader import get_config
    return get_config()["models"]["scoring"]


def _build_shared_scoring_context() -> str:
    """Build rubric + optional benchmark patterns + optional calibration. Called once per batch."""
    ctx = SCORING_RUBRIC

    try:
        with open("data/benchmark_insights.json", encoding="utf-8") as f:
            insights = json.load(f)
        patterns = insights.get("patterns", {}).get("hook_patterns", [])[:3]
        if patterns:
            ctx += "\nBenchmark hook patterns (top performers):\n"
            ctx += "\n".join(f"- {p}" for p in patterns)
    except Exception:
        pass

    try:
        from scripts.performance_analyzer import load_calibration
        cal = load_calibration()
        if cal:
            ctx += f"\n\nCalibration ({cal['post_count']} live posts): avg engagement {cal['avg_engagement_score']}"
            if cal.get("blind_spots"):
                ctx += "\nOverrated patterns: " + "; ".join(
                    f"\"{b['text_preview']}\"" for b in cal["blind_spots"][:2]
                )
            if cal.get("undervalued_signals"):
                ctx += "\nUnderrated patterns: " + "; ".join(
                    f"\"{u['text_preview']}\"" for u in cal["undervalued_signals"][:2]
                )
    except Exception:
        pass

    return ctx


def compute_composite_score(scores: dict, never_list_violation: bool = False) -> float:
    """Compute weighted composite score with +0.5 calibration offset. Returns 0.0 on violation."""
    if never_list_violation:
        return 0.0
    total = sum(scores.get(d["key"], 0) * (d["weight"] / 100) for d in DIMENSIONS)
    total += 0.5  # calibration offset
    return round(total, 2)


def _strip_fences(raw: str) -> str:
    """Strip markdown code fences if present."""
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _weak_dims(score_breakdown: dict) -> str:
    """Return comma-separated dimension names scoring below 8."""
    if not score_breakdown:
        return "all"
    return (
        ", ".join(k for k, v in score_breakdown.items() if isinstance(v, (int, float)) and v < 8)
        or "none"
    )


def batch_score_posts(posts: list[dict]) -> list[dict]:
    """Score all posts in a single API call. Mutates and returns posts with score fields."""
    if not posts:
        return posts

    shared_context = _build_shared_scoring_context()
    posts_block = "\n\n".join(
        f'POST {i + 1}:\n"""{p["text"]}"""\nPillar: {p.get("pillar", "")}'
        for i, p in enumerate(posts)
    )

    prompt = f"""{shared_context}

Score each of the following {len(posts)} posts. Return a JSON array with one object per post in order.
Each object must have exactly these keys: hook_strength, tone_compliance, x_algorithm_optimization, data_specificity, pillar_alignment, cta_quality (all integers 0-10), and never_list_violation (boolean).

{posts_block}

Return ONLY a valid JSON array. No explanation, no markdown fences."""

    raw = llm_complete(
        model=_get_scoring_model(),
        system="You are a Twitter content quality judge. Respond only with valid JSON.",
        user=prompt,
        max_tokens=150 * len(posts),
    )

    results = json.loads(_strip_fences(raw))

    for post, score_obj in zip(posts, results):
        violation = bool(score_obj.pop("never_list_violation", False))
        composite = compute_composite_score(score_obj, never_list_violation=violation)
        post["score"] = composite
        post["score_breakdown"] = score_obj
        post["never_list_violation"] = violation
        post["status"] = "ready" if composite >= TARGET_THRESHOLD else "below_target"

    return posts


def batch_regenerate_posts(failing_posts: list[dict], trend_context: str) -> list[dict]:
    """Regenerate all failing posts in a single API call. Returns new post dicts."""
    if not failing_posts:
        return failing_posts

    posts_block = "\n\n".join(
        f'POST {i + 1} (weak dims: {_weak_dims(p.get("score_breakdown", {}))}, score: {p.get("score", "?")})\n"""{p["text"]}"""'
        for i, p in enumerate(failing_posts)
    )

    prompt = f"""You are a Twitter content coach. Revise each failing post to fix its weak dimensions.

{REGEN_HARD_RULES}

Trend context to leverage: {trend_context[:500]}

{posts_block}

Return a JSON array of {len(failing_posts)} revised post texts in order. Each element is just the post text string.
Return ONLY valid JSON array. No explanation, no markdown fences."""

    raw = llm_complete(
        model=_get_scoring_model(),
        system="You are a Twitter content coach. Respond only with valid JSON.",
        user=prompt,
        max_tokens=350 * len(failing_posts),
    )

    revised_texts = json.loads(_strip_fences(raw))

    return [
        {
            **post,
            "id": str(uuid.uuid4()),
            "text": new_text,
            "score": None,
            "score_breakdown": None,
            "status": "pending_score",
        }
        for post, new_text in zip(failing_posts, revised_texts)
    ]


def score_all_posts(posts: list[dict]) -> list[dict]:
    """
    Batch score → batch regen failing → batch rescore. Max 5 API calls total.
    All posts are returned; below-floor posts get status='below_target'.
    """
    if not posts:
        return posts

    print(f"  Batch scoring {len(posts)} posts...", flush=True)
    scored = batch_score_posts(posts)

    failing = [p for p in scored if (p.get("score") or 0) < TARGET_THRESHOLD]
    passing = [p for p in scored if (p.get("score") or 0) >= TARGET_THRESHOLD]

    print(f"  Scores: {[p['score'] for p in scored]} | Failing: {len(failing)}", flush=True)

    if not failing:
        return scored

    today = get_todays_pillar()
    trend_context = get_trends(pillar=today["pillar"], funnel=today["funnel"])

    for attempt in range(1, MAX_REGENERATION_ATTEMPTS + 1):
        print(
            f"  Batch regenerating {len(failing)} posts (attempt {attempt}/{MAX_REGENERATION_ATTEMPTS})...",
            flush=True,
        )
        revised = batch_regenerate_posts(failing, trend_context)
        rescored = batch_score_posts(revised)

        still_failing = []
        for original, candidate in zip(failing, rescored):
            if (candidate.get("score") or 0) >= TARGET_THRESHOLD:
                passing.append(candidate)
            elif (candidate.get("score") or 0) > (original.get("score") or 0):
                still_failing.append(candidate)
            else:
                still_failing.append(original)

        failing = still_failing
        if not failing:
            break

    for p in failing:
        p["status"] = "below_target"

    return passing + failing


def regenerate_if_below_floor(post: dict) -> dict:
    """Legacy single-post wrapper. Delegates to score_all_posts()."""
    results = score_all_posts([post])
    return results[0] if results else post


if __name__ == "__main__":
    queue = load_queue()
    pending = [p for p in queue if p["status"] == "pending_score"]
    unchanged = [p for p in queue if p["status"] != "pending_score"]

    if not pending:
        print("No posts pending scoring.")
    else:
        print(f"Scoring {len(pending)} posts in batch...")
        scored = score_all_posts(pending)
        save_queue(unchanged + scored)

        ready = [p for p in scored if p["status"] == "ready"]
        below = [p for p in scored if p["status"] == "below_target"]
        print(f"\nScoring complete.")
        print(f"Ready (>={TARGET_THRESHOLD}): {len(ready)} | Below target: {len(below)}")
        for p in scored:
            print(f"  [{p['status'].upper()}] {p['score']} — {p['text'][:60]}...")
