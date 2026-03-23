"""
Post Scorer — D3
Scores each pending draft in data/queue.json using Claude as a judge.
Updates posts with score, score_breakdown, and status.
Usage: python scripts/post_scorer.py
"""

import os
import uuid
from openai import OpenAI
from dotenv import load_dotenv
from scripts.post_queue import load_queue, save_queue
from scripts.cadence import get_todays_pillar
from scripts.trend_scanner import run as get_trends
from scripts.content_generator import generate

load_dotenv()

MODEL = "gpt-4o-mini"
MAX_REGENERATION_ATTEMPTS = 3
QUALITY_FLOOR = 7.5

DIMENSIONS = [
    {"key": "hook_strength",          "weight": 20, "description": "Passes Harry Dry's 3 tests: Can I visualize it? Can I falsify it? Can nobody else say this?"},
    {"key": "tone_compliance",        "weight": 20, "description": "Six Core Laws from voice playbook. Never List: no emdashes, no exclamation marks, no passive voice, no hedging."},
    {"key": "data_specificity",       "weight": 15, "description": "Cites specific numbers, companies, or outcomes. Abstract claims score low."},
    {"key": "pillar_alignment",       "weight": 15, "description": "Clear fit to today's assigned content pillar."},
    {"key": "funnel_stage_accuracy",  "weight": 10, "description": "Post format and CTA match the tagged funnel stage (TOFU/MOFU/BOFU)."},
    {"key": "cta_quality",            "weight": 10, "description": "CTA present and appropriate to funnel stage."},
    {"key": "x_algorithm_optimization", "weight": 10, "description": "Max 2 hashtags, no link in main body, reply-bait elements present."},
]


def build_scoring_prompt(post_text: str, pillar: str, funnel: str) -> str:
    from scripts.config_loader import get_config
    prompt = f"""You are a Twitter content quality judge evaluating posts for @{get_config()['handle']}.

Post to evaluate:
\"\"\"{post_text}\"\"\"

Assigned pillar: {pillar}
Assigned funnel stage: {funnel}

Score each dimension 0-10. Also flag if the post contains a Never List violation (emdash, exclamation mark, passive voice, or hedging phrase).

Respond in exactly this format (no extra text):
hook_strength: <0-10>
tone_compliance: <0-10>
data_specificity: <0-10>
pillar_alignment: <0-10>
funnel_stage_accuracy: <0-10>
cta_quality: <0-10>
x_algorithm_optimization: <0-10>
never_list_violation: <true|false>"""

    # Load performance calibration if available
    try:
        from scripts.performance_analyzer import load_calibration
        cal = load_calibration()
        if cal:
            prompt += f"\n\n## Performance Calibration (from {cal['post_count']} live posts)\n"
            prompt += f"Average engagement score: {cal['avg_engagement_score']}\n"
            if cal.get('blind_spots'):
                prompt += "Scoring blind spots (high predicted, low actual engagement):\n"
                for bs in cal['blind_spots'][:3]:
                    prompt += f"- Score {bs['predicted']}: \"{bs['text_preview']}\"\n"
            if cal.get('undervalued_signals'):
                prompt += "Undervalued patterns (lower predicted, high actual engagement):\n"
                for uv in cal['undervalued_signals'][:3]:
                    prompt += f"- Score {uv['predicted']}: \"{uv['text_preview']}\"\n"
    except Exception:
        pass

    return prompt


def parse_score_response(raw: str) -> tuple:
    """Parse Claude's scoring response into a scores dict and violation flag."""
    scores = {}
    violation = False
    for line in raw.strip().split("\n"):
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key == "never_list_violation":
            violation = value.lower() == "true"
        else:
            try:
                scores[key] = int(value)
            except ValueError:
                scores[key] = 0
    return scores, violation


def compute_composite_score(scores: dict, never_list_violation: bool = False) -> float:
    """Compute weighted composite score. Returns 0.0 if Never List is violated."""
    if never_list_violation:
        return 0.0
    total = sum(
        scores.get(d["key"], 0) * (d["weight"] / 100)
        for d in DIMENSIONS
    )
    return round(total, 2)


def score_post(post: dict) -> dict:
    """Score a single post. Returns updated post dict with score fields."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt = build_scoring_prompt(
        post_text=post["text"],
        pillar=post.get("pillar", ""),
        funnel=post.get("funnel", ""),
    )
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.choices[0].message.content
    scores, violation = parse_score_response(raw)
    composite = compute_composite_score(scores, never_list_violation=violation)

    post["score"] = composite
    post["score_breakdown"] = scores
    post["never_list_violation"] = violation

    if composite >= 8.0:
        post["status"] = "ready"
    elif composite >= QUALITY_FLOOR:
        post["status"] = "below_target"
    else:
        post["status"] = "failed_floor"

    return post


def regenerate_if_below_floor(post: dict) -> dict:
    """
    Score a post. If below QUALITY_FLOOR, regenerate and re-score.
    Tries up to MAX_REGENERATION_ATTEMPTS times.
    On exhaustion, surfaces best-scoring draft with a warning.
    """
    best = score_post(post)
    if best["score"] is not None and best["score"] >= QUALITY_FLOOR:
        return best

    today = get_todays_pillar()
    trend_context = get_trends(pillar=today["pillar"], funnel=today["funnel"])

    for attempt in range(2, MAX_REGENERATION_ATTEMPTS + 1):
        print(f"  Score {best['score']} below floor. Regenerating (attempt {attempt}/{MAX_REGENERATION_ATTEMPTS})...")
        new_drafts = generate(pillar=post["pillar"], funnel=post["funnel"], trend_context=trend_context)
        if not new_drafts:
            break
        candidate = {
            **post,
            "id": str(uuid.uuid4()),
            "text": new_drafts[0],
            "score": None,
            "score_breakdown": None,
            "status": "pending_score",
        }
        scored_candidate = score_post(candidate)
        if scored_candidate["score"] is not None and scored_candidate["score"] > (best["score"] or 0):
            best = scored_candidate
        if best["score"] is not None and best["score"] >= QUALITY_FLOOR:
            break

    if best["status"] == "failed_floor":
        best["status"] = "below_target"
        best["quality_warning"] = f"Best score after {MAX_REGENERATION_ATTEMPTS} attempts: {best['score']}/10. Review carefully."

    return best


if __name__ == "__main__":
    queue = load_queue()
    updated = []

    for post in queue:
        if post["status"] != "pending_score":
            updated.append(post)
            continue

        print(f"Scoring: {post['text'][:60]}...")
        scored = regenerate_if_below_floor(post)
        print(f"  Score: {scored['score']} | Status: {scored['status']}")
        updated.append(scored)

    save_queue(updated)
    print(f"\nScoring complete. Queue updated.")

    ready = [p for p in updated if p["status"] == "ready"]
    below = [p for p in updated if p["status"] == "below_target"]
    print(f"Ready (>=9.5): {len(ready)} | Below target (shown with warning): {len(below)}")
