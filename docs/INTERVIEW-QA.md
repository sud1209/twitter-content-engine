# Technical Interview Q&A — twitter-content-engine

---

## 1. Architecture & Design

**Walk me through the overall architecture. What is the single most important structural decision you made?**

The single most important decision was making `config.json` the only place where user-specific values live. Every script imports `get_config()` from `scripts/config_loader.py` — a module-level singleton that reads the file once and caches the result in `_config`. That means pillar names, the cadence schedule, playbook file paths, the Twitter handle, the benchmark accounts list, and the publish time are all in one place. The failure mode of the alternative — hardcoding values in individual scripts — is that you end up chasing a string like `"15:30"` across five files the first time you want to change your post time, and you miss one. Config-driven design makes the codebase portable: someone else clones it, edits `config.json`, and it works.

**Why Flask instead of FastAPI for the dashboard?**

The dashboard is a localhost approval UI, not a public API. Flask's synchronous request handling is completely adequate for a single user hitting five endpoints. FastAPI's primary advantages — async I/O, automatic OpenAPI docs, Pydantic validation — add real value at scale or when building a public API, but they add complexity for no gain here. The long-running operations (generation, scoring, playbook refresh) are already offloaded to daemon threads via `threading.Thread`, so the fact that Flask is synchronous doesn't block the main loop. If this ever needed to serve concurrent users, FastAPI with async generators would be the right move. For a personal tool, it's over-engineering.

**Why APScheduler with `BlockingScheduler` and not a system cron?**

System cron requires the process to cold-start every time, which means re-importing all modules, re-loading config, and re-loading the LLM client on every job. APScheduler's `BlockingScheduler` keeps the process alive, so subsequent jobs fire faster. More importantly, `schedule_jobs()` in `scripts/scheduler.py` reads `publish_time_utc` from config at startup and registers the publish job dynamically — `pub_hour, pub_minute = map(int, publish_time.split(":"))`. With system cron you'd have to edit the crontab manually every time the user changes their publish time. The tradeoff is that the scheduler process has to stay running; if the machine sleeps it misses jobs. For a personal posting tool, that's an acceptable tradeoff.

**Why does the scheduler register jobs only through `schedule_jobs()` and never with bare `scheduler.add_job()` calls at module level?**

If you call `scheduler.add_job()` at module import time, the job gets registered whenever any other module imports `scheduler.py` — including during tests. That means tests that import anything from the scheduler trigger real job registration, which then tries to fire against live APIs. Wrapping all four jobs inside `schedule_jobs()` means no job is registered until you explicitly call that function, which only happens in the `if __name__ == "__main__"` block. The design note in CLAUDE.md is explicit: always call `schedule_jobs()` at startup, never add bare module-level calls.

**Why does the pipeline require manual approval instead of auto-posting?**

Auto-posting is a one-way door. A hallucinated number, an accidentally sycophantic opener, or a misfire on a trending controversy can't be taken back once it's live. The scoring pipeline produces a composite score with `TARGET_THRESHOLD = 9.25`, but that threshold reflects predicted quality based on rubric dimensions — it cannot detect posts that are factually wrong, contextually tone-deaf on a news day, or just personally embarrassing. Manual approval in the dashboard means a human sees the post, the score breakdown, and the pillar label before anything touches the X API. The time cost is about 30 seconds per day; the risk reduction is asymmetric.

**How does `config_loader.py`'s singleton prevent redundant file reads?**

The module declares `_config: dict | None = None` at module level. `get_config()` checks if `_config is None` before opening the file; on first call it reads and parses `config.json`, assigns the result to `_config`, and returns it. Every subsequent call in the same process returns the already-parsed dict. This matters because `get_config()` is called in tight inner loops — for example, `_pillar_keywords()` in `trend_scanner.py` calls it every time `rank_topics()` runs. Without the singleton, you'd be doing a file open and JSON parse on every pillar scoring pass during the multi-pillar pipeline.

**Why are all scripts invoked as `uv run python -m scripts.X` rather than `python scripts/X.py`?**

All relative path strings in the codebase assume the CWD is the project root. `_DISTILLED_PATH = "data/playbook_distilled.json"` in `content_generator.py`, `CALIBRATION_PATH = "data/score_calibration.json"` in `performance_analyzer.py`, and the config path computed in `config_loader.py` with `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` all resolve correctly only when the process starts from the project root. Running `python scripts/content_generator.py` from a different directory silently writes or reads the wrong `data/` directory. The `uv run python -m` invocation forces the project root to be on `sys.path` and guarantees the CWD is correct.

**Why is `config.json` gitignored rather than committed?**

`config.json` contains the Twitter handle, display name, and profile URL. Those are PII, and the pattern of committing a secrets file "just this once" is how accidental doxxing happens. The solution is `config.example.json` with placeholder values checked in, and `config.json` in `.gitignore`. This is the same pattern used for `.env` / `.env.example`. Anyone cloning the repo copies the example, fills in their values, and runs `first_run.py`.

---

## 2. LLM Integration & Token Efficiency

**How does `llm_client.py` decide which provider to use, and why that approach?**

`complete()` in `scripts/llm_client.py` checks `if model.startswith("claude")` and routes to the Anthropic `messages.create()` API; everything else routes to OpenAI's `chat.completions.create()`. The model names live in `config.json["models"]` — currently `"generation": "claude-haiku-4-5-20251001"` and `"scoring": "claude-haiku-4-5-20251001"`. To switch providers for any task, you change one string in config. The alternative — separate functions `call_anthropic()` and `call_openai()` scattered across files — means every call site has to know which provider it's using. The single `complete(model, system, user, max_tokens)` signature makes all call sites identical regardless of provider.

**Why Claude Haiku for both generation and scoring instead of GPT-4o or Sonnet?**

Haiku is fast and cheap, and both generation and scoring are latency-sensitive: the pipeline runs at 07:00 UTC and must finish before the user wakes up. A full generation + scoring pass for 8 primary posts plus 9 trending-pillar candidates (3 each for 3 pillars) involves multiple batched API calls. At Sonnet or GPT-4o pricing, that adds up to a non-trivial daily cost for a personal tool. Haiku's instruction-following is good enough for structured JSON scoring output and constrained creative generation with an explicit rubric. The quality difference versus Sonnet narrows significantly when you give the model a tight system prompt with hard rules and a numbered output format — both of which the scorer and generator do.

**How does `batch_score_posts()` work and why batch instead of per-post scoring?**

`batch_score_posts()` in `scripts/post_scorer.py` builds a single prompt that contains the shared scoring rubric, benchmark patterns, calibration data, and then all N post texts formatted as `POST 1: """text"""`, `POST 2: """text"""`, etc. It sends one API call and asks the model to return a JSON array of N score objects. Per-post scoring would require N API calls for N posts, which during the multi-pillar pipeline means 8 calls for primary candidates alone. Batching reduces that to one call. The tradeoff is that the model has to maintain context across all N posts and produce parseable JSON for each — which is why `_strip_fences()` exists to handle cases where the model wraps the array in markdown code fences.

**What is the max-5-call constraint in `score_all_posts()` and how is it enforced?**

`score_all_posts()` enforces a maximum of 5 API calls for any N posts: 1 initial `batch_score_posts()` call, then up to 2 regeneration attempts where each attempt is 1 `batch_regenerate_posts()` call + 1 `batch_score_posts()` call = 2 calls per attempt. The constant `MAX_REGENERATION_ATTEMPTS = 2` controls this. After 2 attempts, any post still below `TARGET_THRESHOLD = 9.25` gets `status = "below_target"` and is returned as-is rather than triggering more calls. The failure mode of unbounded retries is obvious: a batch of low-quality posts could spiral into dozens of API calls on a bad day. The 5-call cap means worst-case cost is always predictable.

**What is the playbook distillation and why does it exist?**

`distill_playbooks()` in `scripts/content_generator.py` reads all three playbook markdown files (voice, twitter, strategy), sends them to Haiku in a single call asking for a compact JSON summary with each value under 350 words, and writes the result to `data/playbook_distilled.json`. The full playbooks together are approximately 4,500 tokens. The distilled cache is approximately 1,000 tokens. Every generation call includes the playbooks in the system prompt — at 8 drafts per primary pillar and 3 more per trending pillar, you're calling `build_system_prompt()` four times per pipeline run. The distillation saves roughly 3,500 tokens per call, which at Haiku pricing across daily runs adds up over time and also keeps the system prompt shorter so more of the context window is available for trend data and benchmark injection.

**How is benchmark data injected into the system prompt and scorer, and what happens when the file doesn't exist?**

`_load_benchmark_insights()` in `content_generator.py` tries to open `data/benchmark_insights.json`, validates that it has both `"top_posts"` and `"patterns"` keys, and returns `None` on any failure including `FileNotFoundError`. The injection block in `build_system_prompt()` is wrapped in a bare `try/except Exception: pass`, so if the file is absent the prompt builds cleanly without benchmark data. The scorer has the same pattern in `_build_shared_scoring_context()`. This is intentional: `benchmark_insights.json` is produced by running `scripts/benchmark_analyzer.py` manually, a step that requires valid X API credentials. The system must be usable before that step is completed.

**Why does `playbook_refresher.py` use OpenAI while everything else uses Anthropic Haiku?**

The playbook refresher synthesis prompt is more complex — it needs to reason about trending content, compare it against existing playbook rules, and generate a structured diff that gets appended to markdown files. That task benefits from a slightly more capable model than Haiku. The separate OpenAI dependency for this one use case was a deliberate tradeoff: keeping it isolated in `playbook_refresher.py` means the rest of the system has no OpenAI dependency. If you want to switch it to Claude Sonnet, you change the model string in config and it routes correctly through `llm_client.py`'s prefix check.

---

## 3. Scoring Pipeline

**Walk me through the 6-dimension rubric and why those specific weights.**

The six dimensions in `DIMENSIONS` are: `hook_strength` (25%), `tone_compliance` (20%), `x_algorithm_optimization` (20%), `data_specificity` (15%), `pillar_alignment` (15%), `cta_quality` (5%). Hook strength gets the highest weight because the hook is the only part of the post most readers will see — if it doesn't stop the scroll, nothing else matters. Tone compliance and X algorithm optimization share 20% each because they're both about post mechanics: one governs voice consistency (no em-dashes, no hashtags, no hedging), the other governs reply/retweet bait which drives the 27x and 20x multipliers. Data specificity and pillar alignment are support dimensions at 15% each. CTA quality is 5% because TOFU posts don't rely on CTAs for success — a bold claim with no explicit CTA can score maximum on cta_quality.

**Why did you drop `funnel_stage_accuracy` as a scoring dimension?**

The original rubric had 7 dimensions including `funnel_stage_accuracy` at 15%. I dropped it because every post in this system is TOFU — the cadence for all 6 non-flex days and flex Sunday generates only TOFU content, with BOFU dormant until `newsletter_url` is set. A dimension where every post scores 10/10 wastes 15% of the scoring weight on a constant. Dropping it let me redistribute that weight to dimensions that actually differentiate good posts from bad ones. The test `test_dimension_keys()` in `tests/test_post_scorer.py` explicitly asserts that `"funnel_stage_accuracy"` is not in the dimension keys — it's a regression test for this decision.

**What is the +0.5 calibration offset in `compute_composite_score()` and why is it there?**

`compute_composite_score()` computes the weighted sum and then adds `0.5` before returning. Early testing showed that Haiku's scoring distribution was systematically conservative — posts that were clearly above the quality floor were coming out at 7.8-8.2 when they should be 8.3-8.7. Rather than rewrite the scoring prompt, which would have unpredictable effects on relative ordering, I added a fixed offset to shift the distribution up. The `+0.5` is applied uniformly to all posts so it doesn't change their ranking relative to each other — it only affects whether they clear `QUALITY_FLOOR = 8.0` and `TARGET_THRESHOLD = 9.25`. The test `test_compute_composite_score_includes_offset()` verifies that all-zero scores return `0.5`, not `0.0`.

**What is the difference between `QUALITY_FLOOR` and `TARGET_THRESHOLD`?**

`QUALITY_FLOOR = 8.0` is the minimum score a post needs to survive the regeneration process — posts below the floor trigger `batch_regenerate_posts()`. `TARGET_THRESHOLD = 9.25` is the score above which a post gets `status = "ready"` and appears highlighted in the dashboard. Posts between 8.0 and 9.25 that aren't regenerated up to threshold get `status = "below_target"` and are still visible in the dashboard for manual approval, but they're marked so the user knows they're second-tier. The two-threshold design gives the pipeline somewhere to land gracefully when regeneration doesn't get a post above 9.25 — discarding all below-threshold posts would leave the queue empty on bad generation days.

**What happens when `never_list_violation = true` comes back from the scorer?**

`compute_composite_score()` checks `if never_list_violation: return 0.0` before doing any weighted calculation. A score of `0.0` is returned and the post gets `status = "below_target"`. The never-list violation flag is set by the scorer when the post contains any hashtag — the rubric instructs the model: "CRITICAL: If post contains ANY hashtag (#), mark never_list_violation = true." The `validate_post()` function in `content_generator.py` also hard-rejects hashtags before scoring, so by the time a post reaches `batch_score_posts()` it should already be hashtag-free. The double enforcement exists because `batch_score_posts()` can also be called directly from `_rescore_post()` after a user edit, bypassing `validate_post()`.

**Why does `score_all_posts()` also get the trend context mid-flight when regenerating?**

`batch_regenerate_posts()` takes a `trend_context` parameter and injects up to 500 characters of it into the regeneration prompt as "Trend context to leverage." When `score_all_posts()` enters the regeneration loop, it calls `get_todays_pillar()` and then `get_trends()` at that point to get fresh context. The reason is that regeneration is asking the model to rewrite posts by fixing specific weak dimensions, and giving it current trend context makes the rewrites more specific and data-anchored. An alternative would be to pass trend context in from the call site, but `score_all_posts()` is also called from the scheduler's `run_morning_pipeline()` which doesn't have trend context handy. Fetching it inside the function keeps the API clean.

**What does `regenerate_if_below_floor()` actually do now and why keep it?**

`regenerate_if_below_floor()` in `scripts/post_scorer.py` is a one-liner: `results = score_all_posts([post]); return results[0] if results else post`. It wraps `score_all_posts()` for the single-post case. It's kept because `server.py`'s `_rescore_post()` calls `regenerate_if_below_floor(post)`, and the regen endpoint in `_regen()` also calls it. Removing it would require updating those call sites. The function is documented as "Legacy single-post wrapper" so anyone reading the code knows not to build new features on it — new code should call `score_all_posts()` directly.

---

## 4. Content Generation

**How does `build_system_prompt()` work at a high level?**

`build_system_prompt()` in `scripts/content_generator.py` assembles the system prompt in layers. It starts with the persona definition (handle, bio), then injects all three playbooks (voice, twitter, strategy) from `load_playbooks()`. Then it specifies the pillar and funnel for the day and lists the six constraints: Harry Dry hook test, data requirement, adversarial frame requirement, tone rules, CTA rules, and length guidance. It ends with the forbidden AI fingerprints list. Optionally, if `load_calibration()` returns data, it appends performance calibration showing average engagement score, blind spots (posts the scorer rated high but performed poorly), and undervalued signals (posts scored lower that outperformed). Then if `_load_benchmark_insights()` returns data, it appends benchmark hook patterns, CTA patterns, engagement drivers, and reply triggers from the top competitor posts. Both optional sections are wrapped in bare `try/except Exception: pass` so failures are silent.

**What are the four adversarial frames and why are they required?**

The four frames are: COMPETITIVE DISADVANTAGE ("If you're still [old way], your peers are already [beating you how]"), TRUTH NOBODY ADMITS ("The real reason [authority] won't discuss [topic] is [specific truth]"), TIMESTAMP OBSOLESCENCE ("Anyone still [old way] in 2026 is [consequence]"), and INVERSE RISK ("People think [belief] is risky. Real risk is [opposite]. [Data]"). They're required because they're structurally adversarial — they create tension, imply stakes, and make a reader feel that not engaging is a loss. Vague observation hooks like "AI is changing everything" generate passive likes; adversarial frames generate replies and retweets because they're falsifiable and debate-inviting. Reply=27x like in the X algorithm, so the return on an adversarial hook that generates one reply is 27x a passive liker.

**Walk me through the Harry Dry hook test and how it's operationalized.**

Harry Dry's three tests are embedded in the scoring rubric description for `hook_strength`: "Can I visualize it? Can I falsify it? Can nobody else say this?" All three must pass for a 9+. In the generation prompt, I give strong vs. weak examples inline: strong is "GPT-4o's context window is 128k tokens — 32x the average attention span of a Twitter thread"; weak is "AI models are getting better every month." The first is visualizable (you can picture a context window), falsifiable (you could check the number), and specific to someone who tracks AI specs. The second is none of those things. The scorer is told explicitly: "9+ only if all 3 pass. Vague claims or clichés = 5 max."

**Why does `validate_post()` run before scoring rather than after?**

`validate_post()` runs inside `generate()` before posts are added to the candidate list, which means invalid posts are never passed to `score_all_posts()`. The reason for pre-score rejection is cost and time: scoring is an API call. A post with an em-dash or a weak CTA like "what do you think" is guaranteed to fail tone compliance and cta_quality; scoring it wastes tokens. More importantly, the never-list violations in the scoring rubric (hashtags) mean a post with a hashtag would score 0.0 — that's wasted API cost for a deterministic outcome. Pre-score filtering catches the easy cases for free and preserves the scoring budget for posts that might actually improve through regeneration.

**What hard rules does `validate_post()` enforce and what are the boundaries?**

Four checks: (1) hashtag check — both regular `#` and fullwidth Unicode `\uff03` (the test `test_validate_post_rejects_fullwidth_hashtag()` covers this edge case); (2) em-dash check — Unicode `\u2014`; (3) soft question endings — checks for phrases like `"what's your "`, `"how do you "`, `"what does your "` in the final 80 characters only, not the full text; (4) weak CTA phrases — `_WEAK_CTA_PHRASES` list checked anywhere in the text (case-insensitive). The final-80-chars scope for soft questions is intentional: a post that opens with "How do top AI labs manage inference cost? They don't." is fine; the question is in the hook position where it creates tension. A post that ends with "How do you handle this?" is a passive engagement beg. The test `test_validate_post_accepts_post_with_question_in_body_not_end()` validates this boundary explicitly.

**Why `NUM_DRAFTS = 8` and not a smaller number?**

Eight drafts give the scoring pipeline enough variation to find posts that pass both `validate_post()` and score above `TARGET_THRESHOLD = 9.25`. In practice, a non-trivial fraction of LLM-generated drafts fail validation (hashtags slipping through, weak CTAs, em-dashes). If you start with 4 drafts and 2 fail validation, you have 2 candidates — if neither hits 9.25, the regeneration loop runs on both, consuming API calls that would have been unnecessary with a larger initial batch. Eight is the empirical minimum that reliably yields at least 5 scoreable candidates. The `server.py` pipeline keeps top 5 from 8 primary candidates — so you need at least 5 post-validation drafts to fill the primary slot.

---

## 5. Multi-Pillar Pipeline

**Why 5 posts from the primary pillar and 1 each from 3 trending pillars, not some other ratio?**

The ratio comes from the publishing reality: only 1 post is published per day. The user needs 5 primary-pillar candidates to have meaningful choice at approval time — if you only generate 2 and they're both mediocre, there's no real choice. The 3 trending-pillar posts (1 each from the top 3 trending non-primary pillars) are opportunistic: if a topic is spiking in the RSS feeds today, there might be a better post to publish than today's scheduled pillar. Generating 3 trending-pillar posts (1 each rather than 5 each) keeps the total queue at 8 posts without overwhelming the approval UI. Three is also the minimum to meaningfully represent cross-pillar coverage given 6 pillars minus today's primary.

**How does the pipeline select the 3 trending non-primary pillars?**

`rank_pillars()` in `scripts/trend_scanner.py` takes the full `all_topics` list (already fetched), iterates over every pillar except the excluded one, and scores each pillar by summing keyword hits across all topics. Keywords come from `config["pillar_keywords"]`. It sorts by score descending and returns the top 3 pillar names. If every pillar scores 0 (no RSS keyword hits at all), it falls back to the first 3 pillars in config order. The important detail is that `rank_pillars()` takes the already-fetched `all_topics` list rather than triggering a new RSS fetch — the same list is also passed to `rank_topics()` and `build_trend_context()` for each pillar.

**Why RSS keyword signal for trending pillar selection rather than actual engagement signal?**

Engagement signal from X API would require an API call per pillar per day. RSS keyword signal is a free byproduct of the RSS fetch that happens anyway. More fundamentally, the goal of trending pillar selection is to catch topics that are breaking in the news today, not to optimize for historical engagement patterns — that's what `get_lowest_engagement_pillar()` is for on flex Sundays. RSS captures what's happening right now; historical engagement captures what has worked before. They answer different questions. Using engagement data for trending selection would mean a pillar with historically high engagement always wins, which defeats the purpose of dynamically responding to the news cycle.

**Why is `get_all_topics()` called exactly once in `_run_posts_pipeline()` and passed around?**

`get_all_topics()` calls `scan_rss_feeds()` which fetches 10 RSS feeds and optionally `fetch_competitor_posts()` which makes X API calls. The pipeline needs this data three times: once for `rank_pillars()`, and once per trending pillar for `rank_topics()` and `build_trend_context()`. If each of those called `get_all_topics()` internally, you'd make 10+ HTTP requests to the same RSS feeds in the span of a few seconds, likely getting rate-limited or returning stale data on the second hit. Fetching once and passing the list is the obvious solution. The `run()` function in `trend_scanner.py` calls `get_all_topics()` internally for single-pillar use (standalone mode), but `_run_posts_pipeline()` uses the lower-level `get_all_topics()` directly and passes the result to `rank_pillars()`, `rank_topics()`, and `build_trend_context()`.

**All 8 posts in the pipeline use today's funnel — why not let each pillar use its own configured funnel?**

Funnel stage drives CTA style and depth. If the primary pillar is TOFU and a trending pillar's configured funnel is MOFU, you'd have posts with soft engagement CTAs next to posts with depth-signal CTAs in the same daily queue. The user would have to track which post is which funnel before approving. The simpler and more coherent design is: today's funnel applies to all posts today. The funnel is set by `get_todays_pillar()` which reads the cadence entry for today's weekday. TOFU Monday means all 8 posts on Monday are TOFU regardless of which trending pillars showed up.

---

## 6. Cadence & Scheduling

**How does flex Sunday work end-to-end?**

In `config.json`, the cadence entry for weekday `"6"` (Sunday) has `pillar: "flex"`. `get_todays_pillar()` in `scripts/cadence.py` reads this entry, sees `pillar == "flex"`, and calls `get_lowest_engagement_pillar(cfg.get("pillars", [pillar]))` — but only at that point, not at import time. `get_lowest_engagement_pillar()` reads `data/score_calibration.json` via `load_calibration()`, finds the pillar with the lowest `avg_engagement` score in `by_pillar`, and returns its name. If calibration data isn't available or doesn't have data for any of the configured pillars, it falls back to `pillars[0]`. The resolved pillar name is returned as if it were a hardcoded cadence entry — nothing downstream knows it was resolved dynamically.

**Why is the BOFU dormancy check in `cadence.py` and not in `content_generator.py`?**

`cadence.py` is the single source of truth for pillar and funnel. Every consumer — `content_generator.py`, `server.py`, `scheduler.py` — calls `get_todays_pillar()` and trusts the result. If the BOFU check lived in `content_generator.py`, then `server.py`'s `_run_posts_pipeline()` would need to duplicate the check, and any future consumer would need to remember to add it too. Placing it in `cadence.py` means the funnel fallback is enforced once, transparently, before anything downstream sees the value. The check is three lines: `if funnel == "BOFU" and not cfg.get("newsletter_url"): funnel = "TOFU"`. When the user fills in `newsletter_url`, BOFU activates automatically without any other code change.

**Explain the deferred import pattern in `cadence.py` for `get_lowest_engagement_pillar`.**

`scripts/performance_analyzer.py` imports from `scripts/post_queue.py`. `scripts/post_queue.py` has no circular dependency. But if `performance_analyzer.py` ever needed to import from `scripts/cadence.py` — which is plausible given that analysis might want to know today's pillar — a circular import would form. The deferred import in `cadence.py` places `from scripts.performance_analyzer import get_lowest_engagement_pillar` inside the `if pillar == "flex":` block, so it only executes on Sunday (or whenever flex resolves). Monday through Saturday, the import never fires. This avoids the circular import without restructuring either module. It also makes the happy path (non-flex days) slightly faster because the performance_analyzer module isn't loaded at all.

**Why does the scheduler use `BlockingScheduler` at the top level but daemon threads inside `server.py`?**

`scheduler.py` is a standalone process — the `BlockingScheduler` keeps the process alive with `scheduler.start()` at the bottom of `if __name__ == "__main__"`. `server.py` is a Flask app that needs to serve HTTP requests while long-running operations (post generation, scoring, playbook refresh) proceed in the background. Using `threading.Thread(target=..., daemon=True)` inside Flask endpoints means the operation runs concurrently with the server loop and terminates when the main process exits (daemon=True). The two patterns serve different contexts: blocking scheduler for the dedicated scheduler process, daemon threads for the dashboard server. They could be unified into one process, but keeping them separate means the dashboard can run without the scheduler and vice versa.

---

## 7. Benchmark & Performance

**What does `benchmark_analyzer.py` do and why is it a standalone manual utility rather than a scheduled job?**

`run_benchmark()` in `scripts/benchmark_analyzer.py` fetches up to 50 original tweets from each of the benchmark accounts (`@karpathy`, `@paraschopra`, `@sidin` — all read from `config["benchmark_accounts"]`), computes a weighted engagement score for each tweet using `likes + (retweets * 20) + (replies * 27)`, builds aggregate stats, takes the top 10 posts by score, sends them to the LLM to extract structured patterns (hook patterns, CTA patterns, engagement drivers, reply triggers), and writes two files: `data/benchmark_report.json` and `data/benchmark_insights.json`. It's manual because the X API free tier has tight rate limits on user timeline fetches. Scheduling it daily would burn the rate limit budget and likely get the account flagged. Running it monthly or on demand is the right operational cadence.

**How are X algorithm weights (Reply=27x, Repost=20x) operationalized in the system?**

The weights appear in three places. In `benchmark_analyzer.py`, `compute_weighted_score()` returns `likes + (retweets * 20) + (replies * 27)` — this is how all benchmark posts and published posts are ranked. In `post_scorer.py`, `SCORING_RUBRIC` includes the line "Score each post on 6 dimensions (0-10 integers). Use X Algorithm weights: Reply=27x like, Repost=20x like" and the `x_algorithm_optimization` dimension description says "9+ = ZERO hashtags + specific falsifiable claim someone argues back at." In `build_system_prompt()` in `content_generator.py`, the benchmark injection block notes "(27x replies + 20x retweets + 1x likes)" when showing top benchmark posts. The weights are not hardcoded as magic numbers in one place — they're in `WEIGHT_REPLY = 27` and `WEIGHT_RETWEET = 20` constants in `benchmark_analyzer.py` and surfaced as context to the model everywhere the scoring influences generation.

**How does the velocity monitor work and why T+30 and T+60?**

`check_velocity()` in `scripts/velocity_monitor.py` takes a `tweet_id`, calls `get_tweet_metrics()` to fetch current `likes`, `retweets`, `replies`, `impressions` from the X API, stores the snapshot in the post's queue record under `velocity_metrics["T+30"]` or `"T+60"`, and fires a desktop notification via `scripts/notifier.py` if any metric exceeds `ARCHIVE_MEDIANS["default"] * TRACTION_MULTIPLIER` (1.5x). T+30 and T+60 minutes are the standard engagement velocity checkpoints because X's algorithm amplifies posts early — if a post is gaining replies in the first 30 minutes, the algorithm will push it to more followers. Knowing at T+30 that a post is gaining traction lets the user reply to comments immediately, which itself generates more replies and feeds back into the 27x multiplier.

**How does `get_lowest_engagement_pillar()` handle the cold-start case where there's no calibration data yet?**

`get_lowest_engagement_pillar()` in `performance_analyzer.py` calls `load_calibration()` first. `load_calibration()` returns `None` if `data/score_calibration.json` doesn't exist or if `post_count < 5`. If `load_calibration()` returns `None`, `get_lowest_engagement_pillar()` immediately returns `pillars[0]` — the first pillar in the config list. If calibration data exists but none of the requested pillars appear in `by_pillar` (because none have been posted yet), the function builds an empty `known` dict and again returns `pillars[0]`. The 5-post minimum threshold in `load_calibration()` prevents the calibration from influencing the system with statistically meaningless sample sizes.

**Why does `performance_analyzer.py` flag posts with predicted score >=9.0 and actual engagement <50% of average as blind spots?**

A blind spot is a case where the scorer was confident but reality disagreed. Posts with `score >= 9.0` are ones the model thought were near-perfect. If their actual engagement is below half the average, that's evidence the scorer is miscalibrated for some pattern — perhaps it over-rewards a specific hook structure that doesn't resonate with the actual audience. By surfacing these in `build_system_prompt()` and `_build_shared_scoring_context()`, I'm telling both the generator and the scorer "this kind of post, which you think is great, actually underperforms — don't do it or give it lower weight." The threshold of 50% below average is conservative enough to avoid false positives from statistical noise.

---

## 8. Testing & Reliability

**How are the tests structured and what do they cover?**

Tests live in `tests/` and are run with `uv run pytest tests/ -v`. There are 18 test files covering every script. The tests split into three categories: unit tests for pure functions (e.g., `test_compute_composite_score_weighted()` in `test_post_scorer.py` which manually computes the expected weighted sum and compares), mock-based tests for LLM-dependent code (e.g., `test_batch_score_posts_returns_posts_with_scores()` which patches `scripts.post_scorer.llm_complete`), and integration-style tests for pipeline flows (e.g., `test_server.py` uses Flask's test client against `create_app()`). Dimension correctness — weight sum equals 100, exactly 6 dimensions, no `funnel_stage_accuracy` — is tested with dedicated unit tests so that any future rubric change that breaks invariants fails immediately.

**Why do batch scorer tests patch at `scripts.post_scorer.llm_complete` and not `scripts.llm_client.complete`?**

When Python resolves `from scripts.llm_client import complete as llm_complete` in `post_scorer.py`, it binds the name `llm_complete` in the `scripts.post_scorer` module namespace. Patching `scripts.llm_client.complete` replaces the function in `llm_client`'s namespace, but `post_scorer` already has a reference to the original. Patching `scripts.post_scorer.llm_complete` replaces the binding in the namespace where it's actually called. This is the standard Python mocking gotcha: patch where the name is used, not where it's defined. Every test that mocks an imported function in this codebase follows this pattern.

**What are the known pre-existing test failures and why aren't they fixed?**

`tests/test_playbook_refresher.py` has 8 failing tests. They fail because they patch `scripts.playbook_refresher.PLAYBOOK_PATHS` — a constant that doesn't exist. The module doesn't export a `PLAYBOOK_PATHS` constant; it uses a `_playbook_paths()` function that reads from config at call time. Fixing this requires either changing the module interface to expose the constant (which changes runtime behavior) or rewriting the tests to patch `_playbook_paths` (which requires understanding the function signature and return type). It was a pre-existing condition in the source repo, and CLAUDE.md explicitly marks these as deferred. The remaining 119 tests all pass, so the test suite is reliable for everything outside playbook refresh.

**How does `test_validate_post_accepts_post_with_question_in_body_not_end()` test a boundary case?**

This test constructs a post that opens with "How do top AI labs manage inference cost?" — a phrase that matches `"how do you "` only if you're checking the whole text. The `validate_post()` function only checks `_SOFT_QUESTION_ENDINGS` against `text.lower()[-80:]`, the last 80 characters. Since the question is in the first sentence of a multi-sentence post, it falls outside the final 80 characters and validation passes. The test confirms that legitimate rhetorical questions as hooks aren't rejected. Without this boundary, a stricter implementation that checked the whole text would reject many good hook patterns.

**How does the test suite handle the fact that `get_config()` reads from a real `config.json` that is gitignored?**

Tests that need config values typically either mock `get_config()` directly via `monkeypatch` or provide the specific config keys they need. `tests/fixtures/` contains supporting data. The `config.json` file must exist at project root for the test suite to run, which is satisfied by the `config.example.json` → `config.json` setup step in `first_run.py`. Tests that exercise the full pipeline (server tests, cadence tests) depend on a valid `config.json`. This is a pragmatic choice: having a test-only config fixture that duplicates the entire config schema would create maintenance burden. The tradeoff is that tests can't run on a machine without `config.json`, which is acceptable for a single-developer project.

**How is `test_compute_composite_score_weighted()` structured to verify the weight calculation?**

The test manually computes the expected result: `hook_strength=8` at 25% = 2.00, `tone_compliance=6` at 20% = 1.20, `x_algorithm_optimization=7` at 20% = 1.40, `data_specificity=10` at 15% = 1.50, `pillar_alignment=9` at 15% = 1.35, `cta_quality=4` at 5% = 0.20. Sum = 7.65. Plus the +0.5 offset = 8.15. The test then calls `compute_composite_score(scores)` and asserts `abs(result - expected) < 0.01`. The floating-point tolerance is intentional — `round(total, 2)` in the implementation can produce minor float rounding differences. This test structure serves as living documentation of the exact weight-times-score arithmetic.

---

## 9. Operational Concerns

**What happens if the user runs a script from the wrong directory?**

Most scripts use relative path strings that are interpreted relative to CWD. `data/playbook_distilled.json`, `data/queue.json`, `data/score_calibration.json`, and `data/benchmark_insights.json` are all relative paths. `config_loader.py` uses `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` to find the project root regardless of CWD — so config loading is robust. But `_DISTILLED_PATH = "data/playbook_distilled.json"` in `content_generator.py` is not. If you run `python scripts/content_generator.py` from the `scripts/` directory, it tries to open `scripts/data/playbook_distilled.json` which doesn't exist, silently falls back to the full playbooks, then tries to open those via config paths — which are also relative and break. The solution is explicit: always use `uv run python -m scripts.content_generator` from the project root.

**How does playbook distillation fit into the operational workflow?**

Distillation is a one-time step that a user runs manually after setting up the system: `uv run python -c "from scripts.content_generator import distill_playbooks; distill_playbooks()"`. It costs one Haiku API call and writes `data/playbook_distilled.json`. From that point forward, `load_playbooks()` checks for the distilled file first and uses it. If the user significantly updates the playbook markdown files, they re-run distillation. There's no automatic cache invalidation — the check is simply whether the distilled file exists and has all three keys (`voice`, `twitter`, `strategy`). A stale distilled cache that no longer reflects updated playbooks is a silent failure mode; the expectation is that the user knows to re-distill after significant playbook edits.

**Why is `post_queue.py` a file-based JSON store rather than a database?**

The queue holds at most a handful of posts at any time — daily generation produces 8, publishing removes approved ones, and at end of day the queue is cleared. SQLite or any database would add a dependency and operational overhead (migrations, connection management) for a structure that never holds more than ~20 rows and never needs joins or queries beyond "give me all posts where status == X". File-based JSON is trivially inspectable, trivially backed up, and trivially debuggable — you can `cat data/queue.json` to see the entire state of the system. The failure mode (concurrent writes from multiple threads corrupting the file) is mitigated by the fact that the dashboard server serializes queue mutations via individual function calls, and Flask's GIL prevents true parallel execution on CPython.

**How does the dashboard handle concurrent generation requests?**

`_run_posts_pipeline()` in `server.py` is protected by `_posts_refresh_lock` (a `threading.Lock`) and `_posts_refresh_status["running"]`. The `/api/posts/generate` endpoint checks `if _posts_refresh_status["running"]: return jsonify({"ok": False, "error": "Already running"}), 409` before starting a new thread. If a second request arrives while generation is running, it gets a 409 response immediately. The client polls `/api/posts/generate/status` to check when the run is complete. This pattern — lock + status dict + polling endpoint — is also used for the playbook refresh endpoint. It's simpler than async or websockets for a use case where there's one user and generation takes 15-30 seconds.

**What is `first_run.py` and what does it do?**

`first_run.py` is the setup wizard that a new user runs once. It calls `uv sync` to install dependencies, validates that the required `.env` variables are present, and writes the MCP server configuration with key `"twitter-content-engine"`. It's the entry point for getting the system operational without having to manually trace dependencies through README files. The MCP config enables Claude Code to interact with the dashboard's API endpoints directly, which is how the server becomes visible in the Claude Code MCP server list.

**Why is `benchmark_analyzer.py` described as writing to `data/benchmark_insights.json` rather than a database, and how do downstream consumers handle missing data?**

Both `content_generator.py`'s `_load_benchmark_insights()` and `post_scorer.py`'s `_build_shared_scoring_context()` wrap the file open in bare `try/except Exception: pass` or explicit `FileNotFoundError` catches and return `None` or empty data. This means benchmark data is opt-in enrichment: the system runs correctly at day zero with no benchmark data, and silently gets richer prompts and more calibrated scoring once you run the benchmark analyzer. Writing to a JSON file (rather than a database table) keeps the output human-readable and easily swappable — you could manually write a `benchmark_insights.json` with custom patterns and the system would pick them up on the next generation run with no code changes.
