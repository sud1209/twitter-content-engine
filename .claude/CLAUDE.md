# twitter-content-engine — Claude Code Context

## What this repo is

A config-driven, AI-assisted Twitter/X content engine. Built as a portfolio project demonstrating a full content automation system.

**Stack:** Python 3.10+, `uv` (package manager), Claude Haiku (via `anthropic` SDK, for generation + scoring), OpenAI (for `playbook_refresher.py`), Tweepy, Flask (dashboard on localhost:3000), APScheduler, feedparser, plyer.

---

## PII — must scrub before public GitHub push

| Current value | Replace with |
|---|---|
| `"YOUR_HANDLE"` (in `config.json`) | your X handle |
| `"Sud"` (in `config.json`) | `"Your Name"` |
| Profile URL in `config.json` | `"https://x.com/YOUR_HANDLE"` |

> **Recommendation:** add `config.json` to `.gitignore` and commit a `config.example.json` instead. The playbook files (`docs/playbooks/*-sud.md`) contain no PII — they can stay public.

---

## Architecture overview

### Config-driven everything
All user-specific values live in `config.json`. Nothing is hardcoded in scripts.
`scripts/config_loader.py` exposes `get_config()` — a module-level singleton. Import this wherever config is needed.

### Pillar / cadence system
- `config.json → "cadence"` maps weekday number (0=Mon … 6=Sun) to `{pillar, funnel}`
- `scripts/cadence.py → get_todays_pillar()` is the single source of truth
- **Sunday is "flex"**: resolves at runtime to the lowest-engagement pillar via `get_lowest_engagement_pillar()` from `performance_analyzer.py`
- **BOFU dormancy**: if a cadence entry says `funnel: "BOFU"` but `config.json → newsletter_url` is empty, `cadence.py` silently falls back to `"TOFU"`. Activates automatically when the URL is filled in.

### Funnel definitions
- **TOFU** (Top of Funnel): broad, discovery-oriented. Hook-first, no CTA.
- **MOFU** (Middle of Funnel): depth/expertise signal. Soft engagement CTA.
- **BOFU** (Bottom of Funnel): newsletter/Substack CTA. Dormant until `newsletter_url` is set.

### Weekly cadence (as of setup)

| Day | Pillar | Funnel |
|-----|--------|--------|
| Mon | AI Innovations | TOFU |
| Tue | Sports & Cricket | MOFU |
| Wed | eSports & Dota 2 | TOFU |
| Thu | Literature | MOFU |
| Fri | Gaming & Experimental Cooking | TOFU |
| Sat | AI Innovations | MOFU |
| Sun | flex (lowest engagement pillar) | TOFU |

### Scheduler
`scripts/scheduler.py → schedule_jobs()` reads `publish_time_utc` from config and registers 4 APScheduler jobs:
1. Morning pipeline (content generation + queue)
2. Performance analysis
3. Publish (X post via Tweepy)
4. Spike check (trend scanner)

Always call `schedule_jobs()` at startup — never add bare module-level `scheduler.add_job()` calls.

### Playbook refresher
`POST /api/refresh-playbooks` (or `scripts/playbook_refresher.py` directly) fetches benchmark posts + user's own recent posts, synthesises a trend update via LLM, and appends it to the three playbook files. This is also how the competitive benchmark doc gets its live data section populated on first run.

### Dashboard
Flask server on port 3000 (configurable via `DASHBOARD_PORT` env var). MCP server key: `"twitter-content-engine"`. Run `python scripts/server.py` or let the scheduler start it.

---

## Key files

| File | Purpose |
|------|---------|
| `config.json` | All user config — pillars, cadence, playbook paths, handle, publish time |
| `scripts/config_loader.py` | `get_config()` singleton |
| `scripts/cadence.py` | `get_todays_pillar()` — flex + BOFU logic lives here |
| `scripts/llm_client.py` | Provider-agnostic `complete()` — routes to Anthropic or OpenAI by model name prefix |
| `scripts/content_generator.py` | Builds prompt from cadence + playbooks, calls Claude via llm_client; distills playbook cache; validates posts |
| `scripts/performance_analyzer.py` | `analyze_performance()` + `get_lowest_engagement_pillar()` |
| `scripts/scheduler.py` | APScheduler — always use `schedule_jobs()` |
| `scripts/post_queue.py` | Queue management (replaces deleted `queue.py`) |
| `scripts/playbook_refresher.py` | LLM-powered playbook update via benchmark + own posts |
| `scripts/x_publisher.py` | Tweepy publisher |
| `scripts/trend_scanner.py` | RSS + X feed scanner |
| `scripts/velocity_monitor.py` | T+30 / T+60 traction alerts |
| `scripts/benchmark_analyzer.py` | Standalone benchmark fetch + LLM insight extraction. Run manually to populate `data/benchmark_insights.json` |
| `scripts/notifier.py` | Desktop notifications via plyer |
| `scripts/server.py` | Flask dashboard + API endpoints |
| `first_run.py` | Setup wizard — runs `uv sync`, validates `.env`, writes MCP config |
| `docs/playbooks/voice-playbook-sud.md` | Tone laws, signature patterns, per-pillar voice notes |
| `docs/playbooks/twitter-playbook-sud.md` | Format mix, hook rules, per-pillar hook formulas |
| `docs/playbooks/x-posts-strategy-sud.md` | Pillar table, funnel definitions, repurposing system |
| `docs/competitive-benchmark-sud.md` | Framework for @karpathy, @paraschopra, @sidin — live data populated by playbook_refresher on first run |

---

## Environment variables (`.env`)

```
X_CONSUMER_KEY=
X_CONSUMER_SECRET=
X_BEARER_TOKEN=
X_ACCESS_TOKEN=
X_ACCESS_TOKEN_SECRET=
ANTHROPIC_API_KEY=       # generation + scoring both use Claude (via llm_client.py)
OPENAI_API_KEY=          # still used by playbook_refresher.py
POST_TIME_UTC=15:30
DASHBOARD_PORT=3000
```

Copy `.env.example` → `.env` and fill in values before running.

---

## Tests

Run with: `uv run pytest tests/ -v`

**Known pre-existing failures (do NOT fix — inherited from source repo):**
- `tests/test_playbook_refresher.py` — 8 tests fail because they patch `scripts.playbook_refresher.PLAYBOOK_PATHS` (a constant that doesn't exist; the module uses a `_playbook_paths()` function instead). Fixing requires rewriting either the tests or the module interface — deferred.
Everything else passes (119 tests as of scoring/model overhaul). Do not attempt to fix the above unless explicitly asked.

---

## What's not done yet

1. **Competitive benchmark live data** — `docs/competitive-benchmark-sud.md` has the analytical framework but all `[PENDING FIRST RUN]` sections need to be filled. Trigger via `POST /api/refresh-playbooks` once X API credentials are in `.env`.

2. **Personal archive** — Sud has no tweet archive yet. `scripts/archive_analyzer.py` will work once a Twitter data export is placed in `data/`. Until then, `load_calibration()` returns `None` and flex-Sunday defaults to the first pillar.

3. **Newsletter/Substack** — `newsletter_url` in `config.json` is empty. BOFU funnel is dormant. Fill in the URL when a newsletter is launched to activate BOFU posts automatically.

4. **PII scrub + public GitHub push** — see PII section above.

---

## Design decisions worth knowing

- **Deferred import in `cadence.py`**: `from scripts.performance_analyzer import get_lowest_engagement_pillar` is imported inside the `if pillar == "flex":` block, not at module top. This avoids a potential circular import and keeps the default path (non-flex days) fast.
- **BOFU dormancy in `cadence.py`**: The newsletter check lives here (not in `content_generator.py`) because cadence is the single source of truth for pillar+funnel. The generator just consumes whatever `get_todays_pillar()` returns.
- **`uv` not `pip`**: All dependency management uses `uv`. Run `uv sync` to install, `uv run pytest` to test, `uv run python` to execute scripts. Do not use `pip install`.
- **Model-agnostic via `llm_client.py`**: `scripts/llm_client.py` provides a single `complete(model, system, user)` function that routes to Anthropic (`claude-*`) or OpenAI (everything else) based on the model name prefix. Model names live in `config.json["models"]`. Default models are `claude-haiku-4-5-20251001` for both generation and scoring.

---

## Competitive benchmarks

- `@karpathy` — AI Innovations benchmark (practitioner takes, high signal)
- `@paraschopra` — tech/product/AI (Indian English, opinionated, precise)
- `@sidin` — cricket + literature + culture (Indian English, dry wit)

Space: Indian English-language Twitter. Audience rewards dry wit, specificity, and insider knowledge. Earnest motivational content does not land. Cricket content peaks during live matches.
