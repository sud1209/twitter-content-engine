"""
Content Generator — D2
Reads playbooks (distilled if available) + trend context, calls LLM, drafts post variants.
Usage: python -m scripts.content_generator
"""

import json
import os
import re
import uuid

from dotenv import load_dotenv

from scripts.cadence import get_todays_pillar
from scripts.config_loader import get_config
from scripts.llm_client import complete as llm_complete
from scripts.post_queue import add_post
from scripts.trend_scanner import run as get_trends

load_dotenv()

NUM_DRAFTS = 8  # default; pipeline passes explicit num_drafts per pillar
_DISTILLED_PATH = "data/playbook_distilled.json"


# ── Playbook loading ──────────────────────────────────────────────────────────

def load_playbooks() -> dict[str, str]:
    """Load playbooks. Uses distilled version (~1k tokens) if available, else full (~4.5k tokens)."""
    try:
        with open(_DISTILLED_PATH, encoding="utf-8") as f:
            distilled = json.load(f)
        if distilled.get("voice") and distilled.get("twitter") and distilled.get("strategy"):
            return distilled
    except Exception:
        pass

    paths = get_config()["playbooks"]
    result = {}
    for key, path in paths.items():
        with open(path, encoding="utf-8") as f:
            result[key] = f.read()
    return result


def distill_playbooks() -> None:
    """
    Compress full playbooks to ~1k token distilled version. One-time cost via Haiku.
    Caches result to data/playbook_distilled.json.
    Call manually: uv run python -c "from scripts.content_generator import distill_playbooks; distill_playbooks()"
    """
    cfg = get_config()
    paths = cfg["playbooks"]
    full = {}
    for key, path in paths.items():
        with open(path, encoding="utf-8") as f:
            full[key] = f.read()

    prompt = """Distill these three playbooks into compact rules for an AI content generator.
Output a JSON object with keys "voice", "twitter", "strategy".
Each value must be under 350 words. Include only:
- Core laws / rules (one line each)
- Never list (banned words/phrases)
- Hook formulas (one line each)
- CTA rule
- Pillar definitions (one line each)
No examples, no tables, no explanations. Just the rules.

VOICE PLAYBOOK:
""" + full["voice"][:3000] + """

TWITTER PLAYBOOK:
""" + full["twitter"][:3000] + """

STRATEGY PLAYBOOK:
""" + full["strategy"][:3000] + """

Return ONLY valid JSON. No markdown fences."""

    model = cfg["models"]["generation"]
    raw = llm_complete(model=model, system="You are a concise technical writer.", user=prompt, max_tokens=1200)

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    distilled = json.loads(raw.strip())
    os.makedirs("data", exist_ok=True)
    with open(_DISTILLED_PATH, "w", encoding="utf-8") as f:
        json.dump(distilled, f, indent=2)
    print(f"Playbooks distilled and cached to {_DISTILLED_PATH}")


# ── Benchmark insights ────────────────────────────────────────────────────────

def _load_benchmark_insights() -> dict | None:
    """Load benchmark_insights.json. Returns None if absent or malformed."""
    try:
        with open("data/benchmark_insights.json", encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("top_posts") or not data.get("patterns"):
            return None
        return data
    except FileNotFoundError:
        return None
    except Exception:
        return None


# ── Post validation ───────────────────────────────────────────────────────────

_WEAK_CTA_PHRASES = [
    "what do you think", "what are your thoughts", "share your thoughts",
    "share your strategies", "share your insights", "share your feedback",
    "let me know your", "comments below", "in the comments", "drop a comment",
    "let's discuss", "let's explore", "reach out to", "feel free to",
    "get in touch", "book a", "schedule a",
]

_SOFT_QUESTION_ENDINGS = [
    "what's your ", "how are you ", "what are you ",
    "how do you ", "are your", "what does your ",
]


def validate_post(text: str) -> tuple[bool, str]:
    """
    Check post against hard rules. Returns (is_valid, reason_if_invalid).
    Reason is "" when valid.
    """
    # Hashtags (regular and fullwidth)
    if "#" in text or "\uff03" in text:
        return False, "contains_hashtags"

    # Em-dashes
    if "\u2014" in text:
        return False, "contains_emdash"

    # Soft question in final 80 chars
    last_80 = text.lower()[-80:]
    for phrase in _SOFT_QUESTION_ENDINGS:
        if phrase in last_80:
            return False, "soft_qa_cta"

    # Weak CTA phrases anywhere
    text_lower = text.lower()
    for phrase in _WEAK_CTA_PHRASES:
        if phrase in text_lower:
            return False, f"weak_cta:{phrase}"

    return True, ""


# ── Prompt building ───────────────────────────────────────────────────────────

def build_system_prompt(pillar: str, funnel: str, num_drafts: int = NUM_DRAFTS) -> str:
    playbooks = load_playbooks()
    cfg = get_config()

    prompt = f"""You are the content engine for @{cfg['handle']}, a {cfg['bio']}.

## Voice Guide
{playbooks['voice']}

## Twitter Rules
{playbooks['twitter']}

## Content Strategy
{playbooks['strategy']}

## Today's Assignment
- Content pillar: {pillar}
- Funnel stage: {funnel} (TOFU -- discovery-oriented, no hard CTAs, no link drops)

Your job is to write {num_drafts} distinct post variants for today's pillar. Each must:

1. **HOOK** -- Pass Harry Dry's 3 tests: Can I visualize it? Can I falsify it? Can nobody else say this?
   STRONG: Specific, debatable, falsifiable claim in the first sentence.
   WEAK: "AI is changing everything." / "This matters." / Vague observations.

2. **DATA** -- Cite real numbers, named people/products, or concrete outcomes.
   STRONG: "GPT-4o's context window is 128k tokens -- 32x the average attention span of a Twitter thread."
   WEAK: "AI models are getting better every month."

3. **ADVERSARIAL FRAME** -- Every post must open with ONE of these frames:
   - COMPETITIVE DISADVANTAGE: "If you're still [old way], your peers are already [beating you how]."
   - TRUTH NOBODY ADMITS: "The real reason [authority] won't discuss [topic] is [specific truth]."
   - TIMESTAMP OBSOLESCENCE: "Anyone still [old way] in 2026 is [consequence]. The ones who shifted are [winning how]."
   - INVERSE RISK: "People think [belief] is risky. Real risk is [opposite]. [Data]."

4. **TONE** -- Direct, casual confidence. ZERO emdashes, ZERO exclamation marks, ZERO hashtags, ZERO hedging.
   Kill these words: "seems", "appears", "could", "might", "arguably", "transformative", "ecosystem", "landscape", "unlock", "streamline"

5. **CTA (TOFU)** -- Awareness or follow invite only. No DMs, no links, no newsletter pushes.
   STRONG: Bold claim, follow invite, or debate-bait statement.
   WEAK: "DM me", "Check the link", "Sign up", "What do you think?"

6. **LENGTH** -- Any length is fine. Longer posts score well when they add data, contrast, or step-by-step logic. Do not pad with filler.

## CRITICAL: No AI fingerprints
FORBIDDEN: emdashes (--), exclamation marks (!), hashtags (#), "Let's dive in", "It's worth noting",
"Not just X, not just Y, but Z", parenthetical asides like "(this is key)", "Simply put:", "The truth is:"

Format your response as a numbered list:
1. [post text]
2. [post text]
...{num_drafts}. [post text]

Write only the post text. No labels, no commentary."""

    # Performance calibration (graceful)
    try:
        from scripts.performance_analyzer import load_calibration
        cal = load_calibration()
        if cal:
            prompt += f"\n\n## Performance Calibration (from {cal['post_count']} live posts)\n"
            prompt += f"Average engagement score: {cal['avg_engagement_score']}\n"
            if cal.get("blind_spots"):
                prompt += "Scoring blind spots (high predicted, low actual engagement):\n"
                for bs in cal["blind_spots"][:3]:
                    prompt += f"- Score {bs['predicted']}: \"{bs['text_preview']}\"\n"
            if cal.get("undervalued_signals"):
                prompt += "Undervalued patterns (lower predicted, high actual engagement):\n"
                for uv in cal["undervalued_signals"][:3]:
                    prompt += f"- Score {uv['predicted']}: \"{uv['text_preview']}\"\n"
    except Exception:
        pass

    # Benchmark injection (graceful)
    try:
        insights = _load_benchmark_insights()
        if insights:
            cfg = get_config()
            accounts = cfg.get("benchmark_accounts", [])
            patterns = insights.get("patterns", {})
            top_posts = insights.get("top_posts", [])[:3]

            prompt += f"\n\n## Benchmark Calibration (from {', '.join('@' + a for a in accounts)})\n"

            for label, key in [
                ("Hook patterns", "hook_patterns"),
                ("CTA patterns that drive replies", "cta_patterns"),
                ("Engagement drivers", "engagement_drivers"),
            ]:
                items = patterns.get(key, [])[:3]
                if items:
                    prompt += f"{label}:\n" + "\n".join(f"- {p}" for p in items) + "\n"

            if patterns.get("reply_triggers"):
                prompt += "What drove REPLIES specifically (27x signal):\n"
                for p in patterns["reply_triggers"][:3]:
                    prompt += f"- {p}\n"

            if top_posts:
                prompt += "\nTop benchmark posts by X Algorithm score (27x replies + 20x retweets + 1x likes):\n"
                for post in top_posts:
                    score_note = (
                        f"[{post.get('replies', 0)} replies, {post.get('retweets', 0)} retweets, "
                        f"{post.get('likes', 0)} likes -- score {post.get('score', '?')}]"
                    )
                    prompt += f'- [{post["account"]}] {score_note}\n  "{post["text"][:120]}"\n'
    except Exception:
        pass

    return prompt


# ── Draft parsing ─────────────────────────────────────────────────────────────

def parse_drafts(raw: str) -> list[str]:
    """Extract numbered posts from LLM response."""
    lines = raw.strip().split("\n")
    drafts = []
    current = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                drafts.append(" ".join(current).strip())
                current = []
            continue
        if re.match(r"^\d+\.\s", stripped):
            if current:
                drafts.append(" ".join(current).strip())
            current = [re.sub(r"^\d+\.\s*", "", stripped)]
        else:
            current.append(stripped)

    if current:
        drafts.append(" ".join(current).strip())

    return [d for d in drafts if d]


# ── Generation ────────────────────────────────────────────────────────────────

def generate(pillar: str, funnel: str, trend_context: str, num_drafts: int = NUM_DRAFTS) -> list[str]:
    """Generate draft posts via LLM. Filters invalid posts before returning."""
    cfg = get_config()
    model = cfg["models"]["generation"]
    system = build_system_prompt(pillar=pillar, funnel=funnel, num_drafts=num_drafts)
    user_message = (
        f"Trending context for today:\n{trend_context}\n\n"
        f"Write all {num_drafts} posts now."
    )

    raw = llm_complete(model=model, system=system, user=user_message, max_tokens=2000)
    drafts = parse_drafts(raw)
    print(f"[GENERATE] {len(drafts)} raw drafts. Validating...", flush=True)

    valid = []
    for i, draft in enumerate(drafts, 1):
        is_valid, reason = validate_post(draft)
        if is_valid:
            valid.append(draft)
        else:
            print(f"  [DRAFT {i}] REJECTED -- {reason}: {draft[:60]}", flush=True)

    print(f"[GENERATE] {len(valid)}/{len(drafts)} passed validation.", flush=True)
    return valid


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    today = get_todays_pillar()
    print(f"Generating posts for: {today['pillar']} ({today['funnel']})")

    trend_context = get_trends(pillar=today["pillar"], funnel=today["funnel"])
    print(f"\nTrend context:\n{trend_context}\n")

    drafts = generate(pillar=today["pillar"], funnel=today["funnel"], trend_context=trend_context)
    print(f"Generated {len(drafts)} drafts")

    for draft in drafts:
        post = {
            "id": str(uuid.uuid4()),
            "text": draft,
            "pillar": today["pillar"],
            "funnel": today["funnel"],
            "score": None,
            "score_breakdown": None,
            "status": "pending_score",
        }
        add_post(post)
        print(f"  Added: {draft[:80]}...")

    print("\nDrafts written to data/queue.json")
