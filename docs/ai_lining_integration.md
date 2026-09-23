# AI Lining Dashboard — Integration Guide

How the Flutter app consumes the AI Lining dashboard endpoints exposed by `main.py`.

## Base URL

Local dev: `http://localhost:8000` (`uvicorn main:app --reload`). No auth is enforced yet —
every route takes `user_id` as a path parameter and returns that user's data.

## Data source note

The response **shape is unchanged and final** — `fromJson` doesn't need to change. What's
changed is where the values come from, and this matters for how the app should behave:

| Section | Backed by |
|---|---|
| `dailyObservation` | **Real** — today's orders vs. yesterday's, bucketed hourly |
| `watchedProduct` | **Real** — highest sales-velocity product over the last 7 days |
| `alert` | **Real** — fires when the watched product's days-of-stock ≤ 2 |
| `insights` | **Real** — generated per request by an LLM (Gemini/OpenRouter) from the two sections above |
| `header`, `whatsHappening`, `salesPerformance`, `myStock` | **Still mock** — no shop-listing, historical-stock, or cost-field data source exists yet on the Parent Backend |
| `chat` | Static, unlikely to ever be dynamic |

This only applies once the backend has `PARENT_BACKEND_API_KEY` (and a model-provider key)
configured — with neither set, every section falls back to the old static mock, exactly as
before. Both states return `200` with the same JSON shape, so there's no client-side flag
to check; you just may see the four "real" sections start reflecting the shop's actual
numbers on shops with order history.

### What "real" changes for the client

- **`user_id` in the path must be the shop's real BasePoint `_id`** (a Mongo ObjectId
  string, e.g. `67841c7f52c7b8888375503b`), not an app-internal user id — `list_orders`,
  `get_catalog`, etc. are all called with it as `shop_id`. Passing the wrong id won't
  error; it'll just return data for whichever shop that id happens to match, or empty/zero
  values if it matches nothing.
- **A shop with no orders in the last day/week isn't an error.** `dailyObservation` will
  come back as all-zero buckets, and `watchedProduct`/`alert` will reflect whatever
  historical orders exist. Don't treat all-zero as a loading/error state.
- **`insights` now costs a real LLM call per dashboard load.** Expect `/dashboard` and
  `/insights` to be noticeably slower (and occasionally to return the fallback insight
  `"Insights are temporarily unavailable - check back shortly."` if the model call fails)
  than they were against the static mock. If the dashboard has a loading skeleton, keep it
  — this is no longer an instant response.

## Endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/ai-lining/{user_id}/dashboard` | Full dashboard (all sections in one payload) |
| GET | `/ai-lining/{user_id}/header` | `Header` |
| GET | `/ai-lining/{user_id}/daily-observation` | `DailyObservation` |
| GET | `/ai-lining/{user_id}/watched-product` | `WatchedProduct` |
| GET | `/ai-lining/{user_id}/alert` | `Alert` or `null` |
| GET | `/ai-lining/{user_id}/whats-happening` | `WhatsHappening` |
| GET | `/ai-lining/{user_id}/insights` | `Insight[]` |
| GET | `/ai-lining/{user_id}/sales-performance` | `SalesPerformance` |
| GET | `/ai-lining/{user_id}/my-stock` | `MyStock` |
| GET | `/ai-lining/{user_id}/chat-card` | `ChatCard` |
| POST | `/ai-lining/{user_id}/insights/apply` | `{"success": bool, "message": str}` |
| POST | `/ai-lining/{user_id}/alerts/action` | `{"success": bool, "message": str}` |

Section fields are camelCase and match the widget props 1:1 (see
`src/ai_lining/models.py`) — `fromJson` should be a straight field copy, no renaming.

### Which route to call

- **First paint**: call `/dashboard` once. It returns every section in the shape shown
  at the bottom of this doc.
- **Refreshing a single card** (e.g. after a quick-prompt answer changes the daily
  observation): call that section's own route instead of re-fetching the whole
  dashboard.

## Request/response examples

### `GET /ai-lining/u1/dashboard`

```json
{
  "header": { "shopName": "Silikhe's Shop", "role": "Store Manager", "aiHealth": "87%" },
  "dailyObservation": {
    "hourlySales": [4200, 3800, 5200, 4600, 6100, 5400, 9000, 5800, 4900, 6300, 5100, 4400],
    "peakIndex": 6,
    "peakSales": "2000 Sales",
    "peakWindow": "From 6:30 - 9:30AM",
    "performancePercent": "30%",
    "performanceNote": "Your sales performance is 30% better compare to last month",
    "quickPrompts": ["Why did sales peak at this time?", "..."]
  },
  "watchedProduct": { "...": "..." },
  "alert": { "id": "low_stock_morning_coffee", "title": "...", "message": "...", "actionLabel": "..." },
  "whatsHappening": { "...": "..." },
  "insights": [{ "id": "insight_1", "text": "..." }],
  "salesPerformance": { "...": "..." },
  "myStock": { "...": "..." },
  "chat": { "title": "Start a Chat", "subtitle": "Real-time chatting with business analytics" }
}
```

`alert` is `null` when there's nothing to surface — check for that before rendering the
alert card rather than assuming it's always present.

### `POST /ai-lining/u1/insights/apply`

Request:

```json
{ "insight_id": "insight_1" }
```

Success (200):

```json
{ "success": true, "message": "Insight applied." }
```

Unknown id (404):

```json
{ "detail": "Insight 'insight_1' was not found for this user." }
```

### `POST /ai-lining/u1/alerts/action`

Same shape, keyed on `alert_id` against the id from the last `/alert` (or `/dashboard`)
response.

```json
{ "alert_id": "low_stock_morning_coffee" }
```

## Wiring up `onApplyInsight` / `onSeeWhatToDo`

Both callbacks were no-ops client-side. Now that each `Insight` and `Alert` carries an
`id`, wire them to the two POST routes above:

- `onApplyInsight(insight)` → `POST /ai-lining/{userId}/insights/apply` with
  `{"insight_id": insight.id}`.
- `onSeeWhatToDo(alert)` → `POST /ai-lining/{userId}/alerts/action` with
  `{"alert_id": alert.id}`.

A 404 means the id is stale (e.g. the insight/alert already rotated out) — refetch the
relevant section rather than treating it as a hard failure.

## Quick prompts

`quickPrompts` (in `dailyObservation`, `watchedProduct`, `salesPerformance`, `myStock`)
are plain strings now driven by the backend, not hardcoded per card. Render them as-is;
there's no id to round-trip yet since tapping one is expected to just seed the chat input,
not call back to the API.

## Error handling

All endpoints return standard FastAPI error bodies: `{"detail": "<message>"}`. Section
GET routes don't 404 on an unknown/wrong `user_id` — with the mock data source they return
the same static values regardless of id; with the real data source, a bad shop id returns
`200` with empty/zero values (see above) rather than a 404. Don't treat a `200` alone as
confirmation the shop id you passed was valid.

## Known gap to fix alongside this

`monthLabels` in the Flutter app's `ai_lining_controller.dart` (line 26) currently
hardcodes 4 entries (`['Jan','Mar','May','Jul']`) against 12 `monthlySales` points.
`/sales-performance` and `/dashboard` both return all 12 labels — once the controller
consumes the API response instead of its hardcoded fields, this mismatch goes away on
its own; no separate fix needed if the migration is done in one pass.
