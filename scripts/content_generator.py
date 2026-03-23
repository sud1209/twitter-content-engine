"""
Content Generator — D2
Reads D1 playbooks + trend context, calls Claude API, drafts 3-5 post variants.
Writes drafts to data/queue.json as pending posts.
Usage: python scripts/content_generator.py
"""

import os
import re
import uuid
from openai import OpenAI
from dotenv import load_dotenv
from scripts.cadence import get_todays_pillar
from scripts.trend_scanner import run as get_trends
from scripts.post_queue import add_post

load_dotenv()

from scripts.config_loader import get_config

MODEL = "gpt-4o-mini"
NUM_DRAFTS = 8  # Generate more candidates; pipeline keeps top 5


def load_playbooks() -> dict[str, str]:
    paths = get_config()["playbooks"]
    result = {}
    for key, path in paths.items():
        with open(path, encoding="utf-8") as f:
            result[key] = f.read()
    return result


def build_system_prompt(pillar: str, funnel: str) -> str:
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
- Funnel stage: {funnel}

Your job is to write {NUM_DRAFTS} distinct post variants for today's pillar. Each must:
1. Pass all Six Core Laws and the Never List from the Voice Guide
2. Use a specific hook (data point, bold claim, or vivid scenario — never vague)
3. Map clearly to the {pillar} pillar
4. Match the {funnel} funnel stage and its CTA pattern
5. Be under 280 characters unless it is a thread opener (then write the opener only)

## Hard rule: No AI fingerprints

Before finalising each post, scan for these and rewrite if found:
- Em-dashes (—): replace with a colon, period, or line break
- "Moreover," / "Furthermore," / "Additionally," as sentence starters
- "It's worth noting" / "It's important to note" / "Needless to say"
- "Transformative," "ecosystem," "landscape," "unlock," "streamline," "robust," "seamlessly," "cutting-edge," "best practices," "pain points," "moving forward," "delve into," "navigate [challenges]"
- "Not just X. Not just Y. But Z." triple construction
- "What do you think?" / "What are your thoughts?" question closers
- "(this is key)" / "(worth noting)" parenthetical asides
- "Context:" / "Problem:" / "Solution:" single-word label lines
- "Imagine a world where..." / "Let's dive in." / "Let's explore." openers
- "Simply put:" / "The truth is:" / "The reality is:" pivots

A post that sounds like it was written by a language model fails, even if the data is correct. Write like a sharp founder who runs a company, not like a content brief.

Format your response as a numbered list:
1. [post text]
2. [post text]
...{NUM_DRAFTS}. [post text]

Write only the post text. No labels, no commentary."""

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


def parse_drafts(raw: str) -> list[str]:
    """Extract numbered posts from Claude's response."""
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


def generate(pillar: str, funnel: str, trend_context: str) -> list[str]:
    """Call Claude API to generate draft posts. Returns list of post strings."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    system = build_system_prompt(pillar=pillar, funnel=funnel)
    user_message = f"Trending context for today:\n\n{trend_context}\n\nWrite the {NUM_DRAFTS} post variants now."

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
    )
    return parse_drafts(response.choices[0].message.content)


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

    print(f"\nDrafts written to data/queue.json")
