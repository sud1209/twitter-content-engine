# Configuration Reference — `config.json`

This file documents every key in `config.json`. All user-specific values live here. Nothing is hardcoded in scripts. The singleton accessor is `scripts/config_loader.py → get_config()`.

---

## Identity fields

### `handle`
- **Type:** string
- **Example:** `"YOUR_HANDLE"`
- **Controls:** The X/Twitter username used in profile links and display contexts throughout the dashboard and playbook refresher.
- **Effect of changing:** Updates wherever the handle is interpolated. Does not affect API authentication — credentials live in `.env`.
- **Note:** Strip the leading `@`. This value is PII — see the PII section in `CLAUDE.md` before a public push.

### `display_name`
- **Type:** string
- **Example:** `"Your Name"`
- **Controls:** The human-readable name shown in the dashboard header and used by the LLM as the author identity when building prompts.
- **Effect of changing:** Takes effect immediately on next prompt build or dashboard reload.

### `bio`
- **Type:** string
- **Example:** `"Builder. Writer. Curious about AI, cricket, and everything in between."`
- **Controls:** Injected into the system prompt so the LLM understands the author's positioning. Also shown in the dashboard.
- **Effect of changing:** Takes effect on the next content generation call. Consider re-distilling playbooks after a major bio change.

### `avatar_initial`
- **Type:** string (single character)
- **Example:** `"Y"`
- **Controls:** The letter rendered in the dashboard avatar placeholder when no profile image is set.
- **Effect of changing:** Purely cosmetic. Update to the first letter of `display_name`.

### `profile_url`
- **Type:** string (URL)
- **Example:** `"https://x.com/YOUR_HANDLE"`
- **Controls:** Used in dashboard links and any outbound references to the account.
- **Effect of changing:** Cosmetic only; does not affect posting logic.

---

## Timing

### `publish_time_utc`
- **Type:** string (`"HH:MM"` format, 24-hour UTC)
- **Example:** `"15:30"`
- **Controls:** The time at which `scheduler.py` fires the publish job each day. Maps to 21:00 IST when set to `"15:30"`.
- **Effect of changing:** The scheduler reads this at startup. Restart the scheduler after changing.
- **Note:** Can also be overridden by the `POST_TIME_UTC` environment variable in `.env`. The env var takes precedence.

### `timezone`
- **Type:** string (IANA timezone name)
- **Example:** `"Asia/Kolkata"`
- **Controls:** Used for display purposes in the dashboard (converting UTC times to local). Does not affect when jobs fire — all scheduling is UTC-based.
- **Effect of changing:** Dashboard timestamps will reflect the new timezone on next reload.

---

## URLs

### `newsletter_url`
- **Type:** string (URL or empty string)
- **Example:** `""` (empty until a newsletter is launched)
- **Controls:** Activates or suppresses the BOFU funnel. When empty, `cadence.py` silently downgrades any `funnel: "BOFU"` cadence entry to `"TOFU"`. When filled in, BOFU posts with newsletter CTAs are generated automatically on days where the cadence specifies BOFU.
- **Effect of changing:** Set the URL to activate BOFU. Clear it to revert to dormancy. No code changes required.
- **Note:** This is the single switch for the newsletter CTA system. The generator receives whatever `get_todays_pillar()` returns — it has no awareness of this field directly.

---

## Models

### `models.generation`
- **Type:** string (model identifier)
- **Example:** `"claude-haiku-4-5-20251001"`
- **Controls:** The model used by `content_generator.py` to generate post drafts.
- **Effect of changing:** Takes effect on the next generation call. Higher-capability models produce better hooks at higher cost and latency.
- **Routing logic:** If the value starts with `claude-`, requests are routed to Anthropic via `llm_client.complete()` and `ANTHROPIC_API_KEY` must be set. Any other prefix routes to OpenAI and requires `OPENAI_API_KEY`.

### `models.scoring`
- **Type:** string (model identifier)
- **Example:** `"claude-haiku-4-5-20251001"`
- **Controls:** The model used by the post scorer to rank drafts before queuing.
- **Effect of changing:** Takes effect on the next scoring pass. Using a stronger model here improves draft selection quality.
- **Routing logic:** Same prefix-based routing as `models.generation`. Each field can use a different provider independently.

#### Supported model values

| Value | Provider | Tier |
|---|---|---|
| `claude-haiku-4-5-20251001` | Anthropic | Fast, cheap, default |
| `claude-sonnet-4-6` | Anthropic | Higher quality, higher cost |
| `gpt-4o-mini` | OpenAI | Fast, cheap |
| `gpt-4o` | OpenAI | Higher quality |

To switch: edit `config.json["models"]`. No code changes needed.

---

## Content pillars

### `pillars`
- **Type:** array of strings
- **Example:** `["AI Innovations", "Sports & Cricket", "eSports & Dota 2", "Literature", "Gaming & Experimental Cooking"]`
- **Controls:** The canonical list of content pillars. Used by the cadence system, trend scanner, and performance analyzer. Order does not affect scheduling — cadence assignments govern that.
- **Effect of changing:** Add or remove pillars here first, then update `cadence` and `pillar_keywords` to match. If a pillar name in `cadence` does not appear in `pillars`, behavior is undefined.

---

## Cadence

### `cadence`
- **Type:** object mapping weekday number string to `{pillar, funnel}`
- **Keys:** `"0"` through `"6"` (Monday = `"0"`, Sunday = `"6"`)
- **Controls:** Which pillar and funnel stage are active on each day of the week. Read by `cadence.py → get_todays_pillar()`.
- **Effect of changing:** Takes effect the next time `get_todays_pillar()` is called (next generation run or scheduler tick).

#### Funnel values

| Value | Behavior |
|---|---|
| `"TOFU"` | Awareness-only post. Hook-first, broad appeal, no CTA and no soft follow ask. Discovery-oriented. |
| `"MOFU"` | Depth/expertise signal. Soft engagement CTA (e.g., reply, retweet). Assumes some audience familiarity. |
| `"BOFU"` | Newsletter/Substack CTA. Dormant until `newsletter_url` is non-empty. Automatically downgrades to `"TOFU"` when dormant. |

#### Special case: `"flex"` pillar (Sunday)
When a cadence entry has `"pillar": "flex"`, the engine resolves the actual pillar at runtime by calling `performance_analyzer.get_lowest_engagement_pillar()`. This returns whichever pillar has the lowest recent engagement, so Sunday becomes a recovery slot for underperforming content.

If no calibration data exists (no published posts yet, no Twitter export in `data/`), flex defaults to the first entry in the `pillars` array. Run the engine for several weeks, or place a Twitter data export in `data/` and run `archive_analyzer.py`, to populate calibration data.

#### Default weekly cadence

| Day | Key | Pillar | Funnel |
|---|---|---|---|
| Monday | `"0"` | AI Innovations | TOFU |
| Tuesday | `"1"` | Sports & Cricket | MOFU |
| Wednesday | `"2"` | eSports & Dota 2 | TOFU |
| Thursday | `"3"` | Literature | MOFU |
| Friday | `"4"` | Gaming & Experimental Cooking | TOFU |
| Saturday | `"5"` | AI Innovations | MOFU |
| Sunday | `"6"` | flex | TOFU |

---

## Playbooks

### `playbooks`
- **Type:** object with keys `voice`, `twitter`, `strategy`
- **Values:** Relative paths from project root to markdown playbook files
- **Example:**
  ```json
  {
    "voice": "docs/playbooks/voice-playbook-sud.md",
    "twitter": "docs/playbooks/twitter-playbook-sud.md",
    "strategy": "docs/playbooks/x-posts-strategy-sud.md"
  }
  ```
- **Controls:** Which playbook files are loaded into LLM prompts during content generation and used as the source for playbook refresh.
- **Effect of changing:** Point to different files to swap playbook sets entirely.
- **Note:** `content_generator.py` first checks for `data/playbook_distilled.json` (a pre-processed cache). If the cache exists, the full markdown files are not read. If the cache is absent or stale, the generator falls back to these paths. After editing playbook files, delete `data/playbook_distilled.json` and re-run `distill_playbooks()` to regenerate the cache.

---

## Pillar keywords

### `pillar_keywords`
- **Type:** object mapping pillar name to array of keyword strings
- **Example:**
  ```json
  {
    "AI Innovations": ["AI agents", "LLM", "GPT", "machine learning"],
    "Sports & Cricket": ["cricket", "IPL", "Test match"]
  }
  ```
- **Controls:** Used exclusively by `trend_scanner.py → rank_pillars()`. When the trend scanner fetches RSS feeds, it scores each non-primary pillar by counting how many of its keywords appear in the feed items. The top-scoring pillars become the "trending non-primary" posts in the daily pipeline (3 of the 8 generated posts).
- **Effect of changing:** Add broader keywords to increase sensitivity; add narrower ones to reduce false positives. Keywords are matched case-insensitively.
- **Note:** The primary pillar for the day (from `cadence`) is excluded from this ranking — it is always included regardless of trend score.

---

## Benchmark accounts

### `benchmark_accounts`
- **Type:** array of strings (X/Twitter handles, without `@`)
- **Example:** `["karpathy", "paraschopra", "sidin"]`
- **Controls:** The competitive accounts analyzed by `scripts/benchmark_analyzer.py`. Their recent posts are fetched via the X API and used to populate `docs/competitive-benchmark-sud.md` and inject insights into the scorer and generator prompts.
- **Effect of changing:** Add or remove handles to change the competitive set. The analyzer has no hardcoded handles anywhere in code — this array is the sole source.
- **Note:** Fetching requires `X_BEARER_TOKEN` to be set in `.env`. The analyzer returns empty stats gracefully when the token is absent — no crash, no injection.

---

## Adapting this engine for a different account

1. Update `handle`, `display_name`, `bio`, `avatar_initial`, `profile_url`
2. Replace the `pillars` array with the new account's content topics
3. Rewrite the `cadence` map to assign pillars to days
4. Rewrite `pillar_keywords` to match the new pillars
5. Update `benchmark_accounts` to the relevant competitive accounts
6. Replace the three playbook files at the paths referenced in `playbooks` (keep the same three keys)
7. Delete `data/playbook_distilled.json` if it exists
8. Run `uv run python -c "from scripts.content_generator import distill_playbooks; distill_playbooks()"` to rebuild the cache
9. Update `.env` with the account's X API credentials and `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`
