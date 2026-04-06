# Operations Guide

Day-to-day reference for running the twitter-content-engine in production.

---

## Daily workflow

1. The morning pipeline fires automatically at 07:00 UTC. It generates 8 post drafts: 5 for the primary pillar of the day (from `cadence`) and 3 for the highest-trending non-primary pillars (scored via RSS keyword matching).
2. Each draft is scored and ranked. The queue is written to `data/queue.json`.
3. A desktop notification fires via `plyer` when posts are ready for review.
4. Open the dashboard at `localhost:3000`. Review, edit, approve, or reject drafts.
5. At least 1 approved post must exist in the queue before the publish time.
6. The publish job fires at 15:30 UTC (configurable via `publish_time_utc` in `config.json` or `POST_TIME_UTC` in `.env`). It posts the first approved item to X and sends a desktop notification.

---

## Starting the engine

```bash
# Full engine — scheduler runs in background, dashboard runs in foreground
uv run python scripts/scheduler.py &
uv run python -m scripts.server

# Dashboard only — no scheduled jobs
uv run python -m scripts.server
```

Always run from the project root. The server uses relative paths to locate `config.json`, playbooks, and data files. Running from a different directory will cause file-not-found errors.

Always use `uv run python -m scripts.server`, not `python scripts/server.py`. The `-m` flag sets the module resolution path correctly for relative imports within the `scripts/` package.

---

## Manual operations

| Task | Command |
|---|---|
| Generate posts now | `POST /api/posts/generate` via dashboard or curl |
| Refresh playbooks | `POST /api/playbooks/refresh` (two-step: start then confirm) |
| Run benchmark analysis | `uv run python -m scripts.benchmark_analyzer` |
| Distill playbook cache | `uv run python -c "from scripts.content_generator import distill_playbooks; distill_playbooks()"` |
| Run tests | `uv run pytest tests/ -v` |

---

## Monitoring

- Dashboard at `localhost:3000` — shows today's queue, post status, and pipeline state.
- `GET /api/performance` — history of published posts with engagement data.
- `GET /api/posts/generate/status` — pipeline health check; shows whether a generation run is in progress or completed.
- Spike alerts: `velocity_monitor.py` checks post traction at T+30 and T+60 minutes after publish. A desktop notification fires via `plyer` if a post is gaining unusual traction. The trend scanner also runs on a 2-hour interval with per-keyword cooldown to avoid alert spam.

---

## Troubleshooting

### No posts generated
- Verify `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY` depending on `config.json["models"]`) is set in `.env`.
- Verify the scheduler is running: the morning pipeline job must be registered by `schedule_jobs()` at startup. Bare `scheduler.add_job()` calls outside `schedule_jobs()` will not survive a restart.
- Verify the server is running from the project root — relative path resolution for config and playbooks depends on CWD.

### ImportError on startup
- Always use `uv run python -m scripts.server`, not `python scripts/server.py`. The latter breaks relative module imports within the `scripts/` package.

### Playbooks not distilling
- Delete `data/playbook_distilled.json` if it exists and re-run `distill_playbooks()`.
- Check that `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is set, depending on which model is configured in `config.json["models"]`.
- Verify the paths in `config.json["playbooks"]` point to files that exist.

### Benchmark analyzer returning empty results
- `X_BEARER_TOKEN` must be set in `.env`. The analyzer returns empty stats when the token is absent — no crash, but no competitive injection into prompts either.
- Confirm the handles in `config.json["benchmark_accounts"]` are correct and the accounts are public.

### Sunday flex pillar always defaults to the first pillar
- No calibration data exists yet. The flex resolver calls `get_lowest_engagement_pillar()`, which needs published post history to work.
- Run the engine for several weeks to accumulate engagement data, or place a Twitter data export in `data/` and ensure `archive_analyzer.py` can parse it.
- Until calibration data exists, flex defaults to `pillars[0]` — this is expected behavior.

### BOFU posts never generated
- `newsletter_url` is empty in `config.json`. This is intentional dormancy. The system will automatically start generating BOFU posts as soon as `newsletter_url` is filled in with a valid URL. No code change or restart required — the check runs at call time in `cadence.py`.

### Posts published at wrong time
- The publish time is controlled by `publish_time_utc` in `config.json` or `POST_TIME_UTC` in `.env`. The env var takes precedence.
- The scheduler reads this value at startup. After changing it, restart the scheduler process.

---

## Data files

These files live in `data/` and are generated at runtime. None are committed to version control.

| File | Safe to delete? | Effect of deletion |
|---|---|---|
| `data/queue.json` | Yes | Loses today's drafted and queued posts. Regenerate via the dashboard or `POST /api/posts/generate`. |
| `data/playbook_distilled.json` | Yes | Generator falls back to reading full markdown playbook files on next run. Re-distill with `distill_playbooks()` to restore the cache. |
| `data/benchmark_insights.json` | Yes | Scorer and generator skip benchmark injection on the next run. Re-run `benchmark_analyzer` to regenerate. |
| `data/benchmark_report.json` | Yes | No effect on the pipeline. Informational output from the analyzer only. |
| `data/score_calibration.json` | Yes | Loses engagement calibration used for scoring and flex pillar selection. Regenerates automatically after the next published post. |

---

## Credential rotation

1. Update the relevant values in `.env`.
2. Restart the scheduler process and the server process.
3. No other changes needed. Credentials are read from `.env` at process startup.

---

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | If using Anthropic models | Required when any `config.json["models"]` value starts with `claude-` |
| `OPENAI_API_KEY` | If using OpenAI models | Required when any `config.json["models"]` value starts with `gpt-` |
| `X_CONSUMER_KEY` | Yes (for publishing) | X API OAuth credentials |
| `X_CONSUMER_SECRET` | Yes (for publishing) | X API OAuth credentials |
| `X_BEARER_TOKEN` | Yes (for reading) | Required for benchmark analyzer and trend scanner |
| `X_ACCESS_TOKEN` | Yes (for publishing) | X API OAuth credentials |
| `X_ACCESS_TOKEN_SECRET` | Yes (for publishing) | X API OAuth credentials |
| `POST_TIME_UTC` | No | Overrides `publish_time_utc` from `config.json` if set |
| `DASHBOARD_PORT` | No | Defaults to `3000` if not set |

Copy `.env.example` to `.env` and fill in values before the first run.

---

## Known deferred issues

These are pre-existing issues inherited from the source repository. Do not attempt to fix them unless explicitly planned.

- `tests/test_playbook_refresher.py` — 8 tests fail because they patch `scripts.playbook_refresher.PLAYBOOK_PATHS`, a constant that does not exist. The module uses a `_playbook_paths()` function instead. Fixing requires rewriting either the tests or the module interface. Deferred.
- `tests/test_content_generator.py` — ImportError for `PLAYBOOK_PATHS` for the same reason. The file is excluded from test collection. Deferred.
- `datetime.utcnow()` deprecation warnings in `x_publisher.py` — cosmetic only. No functional impact. Will be addressed in a future cleanup pass.

All other tests (80) pass. Run `uv run pytest tests/ -v` to verify.
