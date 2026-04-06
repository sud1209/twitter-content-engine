# API Reference — twitter-content-engine Dashboard

Base URL: `http://localhost:3000`

The port is configurable via the `DASHBOARD_PORT` environment variable (default: `3000`).

All request and response bodies are JSON. All successful responses return HTTP 200 unless noted. Error responses include an `"error"` string field.

---

## Config

### `GET /api/config`

Returns the subset of `config.json` values used by the dashboard UI.

**Response**

```json
{
  "handle": "YOUR_HANDLE",
  "display_name": "Your Name",
  "avatar_initial": "Y",
  "publish_time_utc": "15:30"
}
```

---

## Posts

### `GET /api/posts/today`

Returns all posts in the queue that are not skipped and not published. This is the primary data source for the dashboard approval view.

**Response** — array of post objects

```json
[
  {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "text": "Anyone still pitching eSports as a niche hobby in 2026 is losing ground fast...",
    "pillar": "eSports & Dota 2",
    "funnel": "TOFU",
    "score": 9.41,
    "score_breakdown": {
      "hook_strength": 9,
      "tone_compliance": 10,
      "x_algorithm_optimization": 9,
      "data_specificity": 8,
      "pillar_alignment": 9,
      "cta_quality": 9
    },
    "never_list_violation": false,
    "status": "ready"
  }
]
```

Post status values:
- `pending_score` — generated, not yet scored
- `ready` — scored >= 9.25
- `below_target` — scored >= 8.0 and < 9.25
- `approved` — manually approved for publishing
- `rejected` — manually rejected
- `published` — posted to X

---

### `POST /api/posts/<post_id>/approve`

Sets the post's status to `approved`.

**Response**

```json
{ "ok": true }
```

---

### `POST /api/posts/<post_id>/reject`

Sets the post's status to `rejected`.

**Response**

```json
{ "ok": true }
```

---

### `POST /api/posts/<post_id>/unapprove`

Reverts an approved (or rejected) post back to its pre-approval status. Sets status to `"scored"` if the post has a score, otherwise `"pending"`.

**Response**

```json
{ "ok": true }
```

**Error (post not found)**

```json
{ "error": "not found" }
```
HTTP 404.

---

### `POST /api/posts/<post_id>/edit`

Replaces the post text. Resets the score fields and triggers an asynchronous re-score via `regenerate_if_below_floor`. The score update is not reflected in this response — poll `/api/posts/today` to see the updated score.

**Request body**

```json
{ "text": "New post text here." }
```

**Response**

```json
{ "ok": true }
```

**Error (missing text)**

```json
{ "error": "text is required" }
```
HTTP 400.

**Error (post not found)**

```json
{ "error": "not found" }
```
HTTP 404.

---

### `POST /api/posts/<post_id>/regen`

Regenerates a post in place. Runs asynchronously in a background thread: fetches fresh trend context, generates new drafts for the same pillar and funnel, scores the first valid draft, and replaces the original post at the same queue position. The post ID changes after successful regeneration.

**Response** (immediate — regeneration runs in background)

```json
{ "ok": true }
```

Poll `/api/posts/<post_id>/regen/status` to track completion.

---

### `GET /api/posts/<post_id>/regen/status`

Returns the current state of a regeneration job for the given `post_id`. Note: once the post is replaced, the original `post_id` no longer exists in the queue.

**Response**

```json
{ "status": "running", "error": null }
```

Status values:
- `"running"` — background thread is active
- `"done"` — regeneration completed successfully
- `"error"` — regeneration failed; see `"error"` field for message
- `"unknown"` — no regeneration job found for this ID

---

## Pipeline

### `POST /api/posts/generate`

Kicks off the full 8-post generation pipeline in a background thread. The pipeline:
1. Clears all non-published posts from the queue.
2. Fetches all RSS and competitor topics once.
3. Generates 8 primary-pillar candidates, scores them, keeps the top 5.
4. For each of the 3 top trending non-primary pillars: generates 3 candidates, scores them, keeps the top 1.
5. Writes all surviving posts (up to 8) to the queue.

Returns HTTP 409 if a generation job is already running.

**Response**

```json
{ "ok": true, "started": true }
```

**Error (already running)**

```json
{ "ok": false, "error": "Already running" }
```
HTTP 409.

---

### `GET /api/posts/generate/status`

Returns the current state of the generation pipeline.

**Response**

```json
{ "running": false, "done": true, "error": null }
```

Fields:
- `running` — `true` while the pipeline is active
- `done` — `true` after the pipeline has completed (success or error)
- `error` — `null` on success; error message string on failure

---

## Performance

### `GET /api/performance`

Returns all published posts sorted by `published_at` descending. Used to populate the performance history view.

**Response** — array of post objects with `status == "published"`, sorted newest first.

```json
[
  {
    "id": "abc123",
    "text": "The real reason cricket coverage...",
    "pillar": "Sports & Cricket",
    "funnel": "MOFU",
    "score": 9.6,
    "status": "published",
    "published_at": "2026-04-05T15:30:00Z",
    "actual_engagement": {
      "likes": 42,
      "retweets": 7,
      "replies": 3,
      "quotes": 1
    }
  }
]
```

`actual_engagement` is populated by the scheduler's analysis job when X API credentials are configured. It may be absent for recently published posts.

---

## Playbooks

### `POST /api/playbooks/refresh`

Two-phase endpoint for refreshing the playbook files with new benchmark and trend data.

**Phase 1 — Start refresh** (body: `{}` or no body)

Launches a background job that fetches competitor posts and synthesises a trend update via LLM. Returns immediately.

```json
{ "ok": true, "started": true }
```

Returns HTTP 409 if a refresh is already in progress.

**Phase 2 — Confirm write** (body: `{"confirm": true}`)

Confirms the pending update and writes it to the playbook files.

```json
{ "ok": true, "written": true }
```

---

### `GET /api/playbooks/refresh/status`

Returns the current state of the playbook refresh job.

**Response**

```json
{
  "running": false,
  "done": true,
  "error": null,
  "preview": "## Trend Update — 2026-04-06\n..."
}
```

Fields vary by implementation state. `preview` contains the generated content pending confirmation.

---

### `GET /api/playbooks/last-updated`

Returns the modification timestamp of the most recently changed playbook file.

**Response**

```json
{ "timestamp": 1744041600.0 }
```

`timestamp` is a Unix epoch float (seconds). Returns `null` if no playbook files are found.

```json
{ "timestamp": null }
```
