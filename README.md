# twitter-content-engine

A config-driven, AI-assisted Twitter/X content engine. Generates, scores, and queues posts for manual approval before publishing. Built for a single user — fully adaptable to any handle, pillar set, or posting cadence via `config.json`.

**Stack:** Python 3.10+, `uv`, Anthropic Claude Haiku (generation + scoring), OpenAI GPT-4o-mini (playbook refresh), Tweepy, Flask, APScheduler.

---

## Features

### Pillar/cadence system
Daily content pillar is assigned by weekday. Sunday is "flex" — the engine auto-selects the lowest-engagement pillar at runtime. A BOFU (bottom-of-funnel) newsletter CTA funnel is built in but dormant until `newsletter_url` is set in `config.json`; it activates automatically when the URL is filled in.

### Multi-pillar pipeline
Each morning run produces 8 draft posts: 5 from today's scheduled pillar + 3 from three trending non-primary pillars detected by the trend scanner.

### Batch AI scoring
Posts are scored across 6 dimensions using a TOFU rubric before they reach the approval queue. Scoring is batched to a maximum of 5 API calls regardless of post count.

| Dimension | Weight |
|---|---|
| Hook strength | 25% |
| Tone compliance | 20% |
| X algorithm optimization | 20% |
| Data specificity | 15% |
| Pillar alignment | 15% |
| CTA quality | 5% |

### Hard-rule validation
`validate_post()` runs before scoring and rejects posts that contain hashtags, em-dashes, or weak CTAs — no LLM call is wasted on posts that fail the rules.

### Playbook distillation
A one-time cache compresses ~4,500-token playbook files to ~1,000 tokens. Subsequent generation runs use the cache, cutting prompt cost significantly.

### Provider-agnostic LLM routing
`llm_client.py` routes requests to Anthropic or OpenAI based on the model name prefix. Swap models without touching any other file.

### Flask approval dashboard
Runs on `localhost:3000`. Review, approve, reject, edit, or regenerate posts before they are published. Nothing publishes without explicit approval.

### APScheduler jobs
Four jobs registered at startup via `schedule_jobs()`:

| Job | Default time (UTC) |
|---|---|
| Morning pipeline (generation + queue) | 07:00 |
| Performance analysis | 09:00 |
| Publish approved posts | 15:30 (configurable) |
| Spike check / trend scan | Every 2 hours |

### Benchmark analyzer
Standalone utility that fetches recent posts from competitor accounts, scores them against the same rubric, and writes structured insights to `data/benchmark_insights.json`. Run manually; requires `X_BEARER_TOKEN`.

---

## Quick start

### Option A — setup wizard (recommended)

```bash
git clone <repo-url>
cd twitter-content-engine
pip install uv          # or: curl -Lsf https://astral.sh/uv/install.sh | sh
uv run python first_run.py
```

`first_run.py` installs dependencies, opens a browser form to collect API keys, writes `.env`, and registers the MCP server entry.

### Option B — manual setup

```bash
git clone <repo-url>
cd twitter-content-engine
pip install uv
cp .env.example .env    # fill in API keys
uv sync
```

### Start the engine

```bash
# Terminal 1 — background scheduler (pipeline, publish, spike check)
uv run python scripts/scheduler.py

# Terminal 2 — approval dashboard
uv run python -m scripts.server
```

Dashboard: [http://localhost:3000](http://localhost:3000)

---

## Environment variables

Copy `.env.example` to `.env` and fill in the values below.

```
X_CONSUMER_KEY=
X_CONSUMER_SECRET=
X_BEARER_TOKEN=
X_ACCESS_TOKEN=
X_ACCESS_TOKEN_SECRET=
ANTHROPIC_API_KEY=       # generation + scoring (Claude Haiku)
OPENAI_API_KEY=          # playbook refresher only
POST_TIME_UTC=15:30
DASHBOARD_PORT=3000
```

---

## Key commands

| Command | Purpose |
|---|---|
| `uv run pytest tests/ -v` | Run test suite |
| `uv run python first_run.py` | Setup wizard |
| `uv run python -m scripts.server` | Dashboard only (no scheduler) |
| `uv run python scripts/scheduler.py` | Full scheduled engine |
| `uv run python -m scripts.content_generator` | Manual generation run |
| `uv run python -m scripts.benchmark_analyzer` | Analyze competitor accounts (needs `X_BEARER_TOKEN`) |
| `uv run python -c "from scripts.content_generator import distill_playbooks; distill_playbooks()"` | Rebuild playbook cache |

---

## Weekly cadence (default)

| Day | Pillar | Funnel |
|---|---|---|
| Monday | AI Innovations | TOFU |
| Tuesday | Sports & Cricket | MOFU |
| Wednesday | eSports & Dota 2 | TOFU |
| Thursday | Literature | MOFU |
| Friday | Gaming & Experimental Cooking | TOFU |
| Saturday | AI Innovations | MOFU |
| Sunday | flex (lowest-engagement pillar) | TOFU |

Cadence is defined in `config.json → "cadence"` and resolved by `scripts/cadence.py`. To change it, edit `config.json` — no code changes required.

### Funnel definitions

- **TOFU** (Top of Funnel): broad, discovery-oriented. Hook-first, no CTA.
- **MOFU** (Middle of Funnel): depth and expertise signal. Soft engagement CTA.
- **BOFU** (Bottom of Funnel): newsletter/Substack CTA. Dormant until `newsletter_url` is set in `config.json`.

---

## Project structure

```
twitter-content-engine/
├── config.json                  # All user config — pillars, cadence, handle, publish time
├── .env                         # API keys (not committed)
├── .env.example                 # Template
├── first_run.py                 # Setup wizard
├── scripts/
│   ├── config_loader.py         # get_config() singleton
│   ├── cadence.py               # get_todays_pillar() — flex + BOFU logic
│   ├── content_generator.py     # Prompt builder + LLM caller, playbook distillation
│   ├── post_scorer.py           # Batch 6-dimension TOFU scorer
│   ├── llm_client.py            # Provider-agnostic LLM router (Anthropic / OpenAI)
│   ├── post_queue.py            # Queue management
│   ├── server.py                # Flask dashboard + API endpoints
│   ├── scheduler.py             # APScheduler — always use schedule_jobs()
│   ├── trend_scanner.py         # RSS + X feed scanner
│   ├── performance_analyzer.py  # analyze_performance() + get_lowest_engagement_pillar()
│   ├── playbook_refresher.py    # LLM-powered playbook update
│   ├── benchmark_analyzer.py    # Competitor post analysis
│   ├── x_publisher.py           # Tweepy publisher
│   ├── velocity_monitor.py      # T+30 / T+60 traction alerts
│   ├── notifier.py              # Desktop notifications (plyer)
│   ├── archive_analyzer.py      # Personal tweet archive analysis
│   └── spike_detector.py        # Trend spike detection
├── docs/
│   └── playbooks/
│       ├── voice-playbook.md    # Tone laws, signature patterns, per-pillar voice notes
│       ├── twitter-playbook.md  # Format mix, hook rules, per-pillar hook formulas
│       └── x-posts-strategy.md # Pillar table, funnel definitions, repurposing system
├── data/
│   └── benchmark_insights.json  # Written by benchmark_analyzer
└── tests/
```

---

## Configuration

All user-specific values live in `config.json`. Key sections:

- **`handle`** — your X/Twitter handle (without `@`)
- **`pillars`** — list of content pillars with descriptions
- **`cadence`** — weekday-to-pillar mapping (`0` = Monday, `6` = Sunday)
- **`publish_time_utc`** — daily publish time in `HH:MM` format
- **`newsletter_url`** — leave empty to keep BOFU dormant; fill in to activate

`scripts/config_loader.py` exposes a `get_config()` module-level singleton. Import this wherever config access is needed — do not read `config.json` directly.

---

## Architecture notes

**Deferred import in `cadence.py`**: `get_lowest_engagement_pillar` is imported inside the `if pillar == "flex":` block rather than at module top. This avoids a potential circular import and keeps the non-flex code path fast.

**BOFU dormancy**: The newsletter URL check lives in `cadence.py`, not in `content_generator.py`. Cadence is the single source of truth for pillar + funnel. The generator consumes whatever `get_todays_pillar()` returns.

**Scheduler discipline**: Always call `schedule_jobs()` at startup. Never add bare `scheduler.add_job()` calls at module level.

---

## Tests

```bash
uv run pytest tests/ -v
```

80 tests pass. Two test files have known pre-existing failures inherited from the source repo (`test_playbook_refresher.py`, `test_content_generator.py`) — these are deferred and should not be addressed unless explicitly planned.

---

## What is not done yet

**Competitive benchmark live data** — playbook files contain the analytical framework, but live data sections are unpopulated. Trigger a refresh once X API credentials are set:

```bash
curl -X POST http://localhost:3000/api/playbooks/refresh
```

**Personal tweet archive** — `scripts/archive_analyzer.py` is ready. Place a Twitter data export in `data/` to activate it. Until then, flex-Sunday defaults to the first configured pillar.

**Newsletter / BOFU posts** — Set `newsletter_url` in `config.json` when a newsletter is launched. BOFU posts activate automatically on the next cadence resolution.

---

## Adapting for your own account

1. Edit `config.json`: set `handle`, `display_name`, `profile_url`, `pillars`, `cadence`, and `publish_time_utc`.
2. Update playbook files in `docs/playbooks/` to match your voice and content strategy.
3. Rebuild the playbook cache:
   ```bash
   uv run python -c "from scripts.content_generator import distill_playbooks; distill_playbooks()"
   ```
4. Run the benchmark analyzer to populate competitor insights for your niche.

No code changes are required for a basic re-configuration.

---

## PII / public push checklist

`config.json` contains your handle, display name, and profile URL. Before pushing to a public repository:

- Add `config.json` to `.gitignore`
- Commit `config.example.json` with placeholder values (`YOUR_HANDLE`, `Your Name`, `https://x.com/YOUR_HANDLE`) instead
- Verify playbook files do not contain personal identifiers

---

## License

MIT
