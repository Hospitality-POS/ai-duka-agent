# AI Lining Dashboard & Chat — App Integration Guide

How the Flutter app loads the AI Lining dashboard and the "Start a Chat" screen from the
Duka AI Engine. Every value on the dashboard comes from one endpoint; the chat answers from
that same data.

## 1. Setup

### Base URL

| Environment | Base URL |
|---|---|
| Docker (`docker compose up`) | `http://<host-ip>:8000` |
| Local dev on the office LAN | `http://192.168.100.57:8001` (the host's IP can change; check `ipconfig`) |

A phone on the same Wi-Fi can reach the engine at the host's LAN IP. `localhost` won't
work from a phone, and on the Android emulator the host machine is `http://10.0.2.2:<port>`.

**Plain HTTP in dev builds.** Android blocks cleartext HTTP by default: add
`android:usesCleartextTraffic="true"` to the debug `AndroidManifest.xml` (or a network
security config for the dev host). On iOS, add an `NSAppTransportSecurity` exception for the dev
host. Don't ship either to production; production should be HTTPS.

### Authentication

The engine keeps no user sessions of its own. It forwards the user's Parent Backend
token to the Parent Backend on every call.

1. Log the user in against the Parent Backend: `POST /users/login` (with the
   `companycode` header). Keep the returned token and `shopId`.
2. Send the token **and the same tenant code** to the Duka AI Engine on **every**
   dashboard and chat request:

   ```http
   Authorization: Bearer <token from /users/login>
   companycode: <the tenant code you logged in with>
   ```

   Without `companycode` the Parent Backend answers "Tenant code required" and the engine
   returns `502` (unless the server has a default set in `PARENT_BACKEND_COMPANY_CODE`).

3. Use `shopId` as the `{user_id}` path segment and as `userId` in chat. Despite the name,
   the engine treats it as the shop's BasePoint `_id` (a Mongo ObjectId string like
   `67841c7f52c7b8888375503b`), **not** the app's user id.

| Request has… | Engine returns |
|---|---|
| A bearer token | Live data for that shop, from the Parent Backend's `GET /biashara-ai/dashboard` |
| No token | `200` with **static demo data** ("Silikhe's Shop"), the same shape as live data |

A missing token doesn't cause an error. It returns demo data, so if the dashboard shows
"Silikhe's Shop" for a real user, the token isn't being sent.

## 2. Loading the dashboard

### Which route to call

- **Opening the dashboard / pull-to-refresh:** `GET /ai-lining/{shopId}/dashboard`. It returns
  every section in one response.
- **Refreshing one card:** that section's route (table below). Each one fetches the full
  dashboard from the Parent Backend anyway, so if you need more than one section, call
  `/dashboard` instead.

| Method | Path | Returns | Widget |
|---|---|---|---|
| GET | `/ai-lining/{shopId}/dashboard` | Every section below | Whole screen |
| GET | `/ai-lining/{shopId}/header` | `header` | Shop name, role, AI health strip |
| GET | `/ai-lining/{shopId}/daily-observation` | `dailyObservation` | Hourly sales chart |
| GET | `/ai-lining/{shopId}/watched-product` | `watchedProduct` | Watched product card |
| GET | `/ai-lining/{shopId}/alert` | `alert` **or `null`** | Alert banner |
| GET | `/ai-lining/{shopId}/whats-happening` | `whatsHappening` | "What's happening" card |
| GET | `/ai-lining/{shopId}/insights` | `insights[]` | Insight cards |
| GET | `/ai-lining/{shopId}/sales-performance` | `salesPerformance` | Monthly sales chart |
| GET | `/ai-lining/{shopId}/my-stock` | `myStock` | Stock capital card |
| GET | `/ai-lining/{shopId}/chat-card` | `chat` | "Start a Chat" entry card |
| POST | `/ai-lining/{shopId}/insights/apply` | `{success, message}` | Insight "Apply" button |
| POST | `/ai-lining/{shopId}/alerts/action` | `{success, message}` | Alert "See what to do" |

### Response: `GET /ai-lining/{shopId}/dashboard`

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
    "quickPrompts": ["Why did sales peak at this time?", "Compare this to last week", "Explain this trend in plain terms"]
  },
  "watchedProduct": {
    "amount": "Ksh 1250",
    "subtitle": "Morning Coffee Sales",
    "salesLabel": "Sales",
    "salesValue": "Ksh 23,000",
    "trend": [2.0, 2.6, 2.3, 3.2, 3.0, 3.8, 4.4, 4.1, 5.0],
    "markerIndex": 6,
    "recommendation": "You're Likely To Run Out Tomorrow Around 10:00 AM.",
    "quickPrompts": ["..."]
  },
  "alert": {
    "id": "low_stock_morning_coffee",
    "title": "Morning Coffee",
    "message": "You may run out of Morning Coffee before your busiest sales period.",
    "actionLabel": "See what to do"
  },
  "whatsHappening": {
    "observation": "More Customers Are Buying Coffee During The Morning Rush.",
    "implication": "This Is Increasing Your Daily Revenue, But Your Current Stock May Not Last Through Tomorrow.",
    "stockLabel": "Stock remaining",
    "stockValue": "78 units",
    "stockStatus": "Low Stock"
  },
  "insights": [
    { "id": "insight_1", "text": "Your Morning Coffee sales are performing exceptionally today. ..." }
  ],
  "salesPerformance": {
    "monthlySales": [3.2, 4.6, 3.4, 5.2, 4.0, 3.0, 4.2, 5.4, 4.8, 3.6, 4.4, 5.0],
    "monthLabels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "highlightIndex": 7,
    "annotation": "4600 Live sales in May",
    "stockPercent": "30%",
    "stockNote": "You have 30% more stock available than last month, helping you stay ahead of demand.",
    "quickPrompts": ["..."]
  },
  "myStock": {
    "capitalLabel": "Total Capital",
    "capitalValue": "Ksh 274,000",
    "note": "Orders Coming From Suppliers Which Exceeds The Capital By 2%",
    "quickPrompts": ["Break down this total for me", "Compare this to last month", "What's driving this number?"]
  },
  "chat": { "title": "Start a Chat", "subtitle": "Real-time chatting with business analytics" }
}
```

The full demo payload is in [`ai_lining_dashboard_sample.json`](ai_lining_dashboard_sample.json),
which is useful as a test fixture for `fromJson`.

### Rendering rules

- **Field names are camelCase and match the widget props 1:1**, so `fromJson` is a straight
  copy with no renaming.
- **Display strings are pre-formatted.** `aiHealth`, `peakSales`, `amount`, `salesValue`,
  `capitalValue`, `stockValue` and the percentages arrive ready to show (`"Ksh 274,000"`,
  `"87%"`). Render them as-is and don't parse them into numbers.
- **Chart arrays are plain numbers.** `hourlySales`, `trend` and `monthlySales` are
  `List<double>` (JSON may send `4200` or `4.2`, so read with `(e as num).toDouble()`).
  `peakIndex`, `markerIndex` and `highlightIndex` index into their array to mark the
  highlighted point.
- **`monthLabels` has one label per `monthlySales` point (12).** Use it instead of a
  hardcoded label list.
- **Nullable fields.** Build the widget so these don't crash:
  - `alert`: `null` when nothing needs attention. Hide the alert banner.
  - `salesPerformance.stockPercent`: `null` when the shop has no stock-movement history yet.
    `stockNote` still explains why, so show the note and skip the percentage.
- **Zeros are valid data.** A new shop, or one with no sales today, returns zero-filled
  charts. Don't treat all-zero as a loading or error state.

### Buttons

- **Insight "Apply"** (`onApplyInsight`): `POST /ai-lining/{shopId}/insights/apply` with
  `{"insight_id": insight.id}`.
- **Alert "See what to do"** (`onSeeWhatToDo`): `POST /ai-lining/{shopId}/alerts/action` with
  `{"alert_id": alert.id}`. A natural follow-up is to open the chat with a prompt about
  the alert (see below).

Both return `200 {"success": true, "message": "..."}`. A `404` means the id is stale (the
insight or alert has rotated out), so refetch that section. Note that these actions are
**acknowledged but not yet stored** on the Parent Backend. Update the UI optimistically,
but don't rely on the choice persisting across reloads yet.

## 3. Chat

The chat answers from the shop's live dashboard data, so it can say things like
"your Morning Coffee stock (78 units) won't last past 10 AM tomorrow" instead of generic
advice.

### `POST /chat`

```http
POST /chat
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "prompt": "Why did sales peak at this time?",
  "userId": "67841c7f52c7b8888375503b",
  "level": "early_stage"
}
```

| Field | Required | Notes |
|---|---|---|
| `prompt` | Yes | The user's message. |
| `userId` | For shop-aware answers | The shop id (same as `{shopId}` above). Without it, the chat gives general business advice. |
| `level` | No | `early_stage`, `growth_stage` or `mature_stage`: the business's growth stage, which picks the advisor. Anything else (or omitted) uses `early_stage`. |
| `provider` | No | `gemini` (default), `openrouter`, `openai`, `deepseek`, `anthropic`. Leave it unset unless you're told otherwise. |
| `model`, `apiKey` | No | Leave unset: the server uses its own configured model and key. |

Response `200`:

```json
{ "agent": "early_stage", "response": "Your peak was 6:30–9:30 AM because ..." }
```

`response` is plain text with the occasional markdown bullet list. Render it with a
markdown widget (e.g. `flutter_markdown`) or strip `*`/`-` markers. Replies are short by
design (3–6 sentences, written for a phone screen).

**Latency:** a chat call makes a live model request, typically a few seconds and longer
when the model provider is busy. Show a typing indicator and use a generous timeout
(60 s).

### Quick prompts

Every card with `quickPrompts` shows them as chips. Tapping a chip should open the chat
and send the chip text as `prompt`, with the same `userId` and token. Because the chat
already has the whole dashboard, "Why did sales peak at this time?" gets answered from the
shop's real peak window. You don't need to send the card data along.

The chat is **stateless**: each `/chat` call is independent and the engine doesn't
remember earlier messages. Keep the conversation history on the app side for display.

## 4. Errors

Errors come back as `{"detail": "<message>"}`.

| Status | Meaning | What the app should do |
|---|---|---|
| `401` / `403` | The Parent Backend rejected the token (expired or revoked) | Send the user to log in again |
| `404` on a GET | The Parent Backend doesn't recognise the shop id | Check you're sending `shopId` from login, not a user id |
| `404` on a POST | Stale insight or alert id | Refetch that section |
| `400` on `/chat` | Unknown `provider` or no API key configured server-side | Report it; it's a config issue, not the user's fault |
| `502` | The Parent Backend is down or returned an error; `detail` carries its status and message | Show "Couldn't load your data, pull to retry"; log `detail` for debugging |
| `500` on `/chat` | The AI model is unavailable after all fallbacks (usually a demand spike) | Show "The assistant is busy, try again in a moment" with a retry |

If the Parent Backend fails during a **chat** request, the chat still answers, just without
shop data. That case doesn't produce an error.

## 5. Dart reference

A minimal service matching the contract above, using the `http` package:

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;

class DukaApiException implements Exception {
  DukaApiException(this.statusCode, this.detail);
  final int statusCode;
  final String detail;
  bool get needsLogin => statusCode == 401 || statusCode == 403;
}

class DukaApi {
  DukaApi({
    required this.baseUrl,
    required this.token,
    required this.companyCode,
    required this.shopId,
  });

  final String baseUrl; // e.g. http://192.168.100.57:8001
  final String token;   // from Parent Backend POST /users/login
  final String companyCode; // the tenant code sent to /users/login
  final String shopId;  // `shopId` from the same login response

  Map<String, String> get _headers => {
        'Authorization': 'Bearer $token',
        'companycode': companyCode,
        'Content-Type': 'application/json',
      };

  Future<Map<String, dynamic>> _send(Future<http.Response> request) async {
    final response = await request;
    final body = jsonDecode(response.body);
    if (response.statusCode != 200) {
      throw DukaApiException(response.statusCode, body['detail']?.toString() ?? '');
    }
    return body as Map<String, dynamic>;
  }

  Future<AiLiningDashboard> getDashboard() async => AiLiningDashboard.fromJson(await _send(
        http.get(Uri.parse('$baseUrl/ai-lining/$shopId/dashboard'), headers: _headers)));

  Future<String> chat(String prompt, {String? level}) async {
    final body = await _send(http
        .post(
          Uri.parse('$baseUrl/chat'),
          headers: _headers,
          body: jsonEncode({'prompt': prompt, 'userId': shopId, 'level': ?level}),
        )
        .timeout(const Duration(seconds: 60)));
    return body['response'] as String;
  }

  Future<void> applyInsight(String insightId) => _send(http.post(
      Uri.parse('$baseUrl/ai-lining/$shopId/insights/apply'),
      headers: _headers,
      body: jsonEncode({'insight_id': insightId})));

  Future<void> actOnAlert(String alertId) => _send(http.post(
      Uri.parse('$baseUrl/ai-lining/$shopId/alerts/action'),
      headers: _headers,
      body: jsonEncode({'alert_id': alertId})));
}
```

(`'level': ?level` is Dart 3.8's null-aware map element. On older SDKs, use
`if (level != null) 'level': level`.)

Model classes follow the JSON 1:1. The two nullable spots look like this:

```dart
class AiLiningDashboard {
  AiLiningDashboard.fromJson(Map<String, dynamic> json)
      : header = Header.fromJson(json['header']),
        alert = json['alert'] == null ? null : Alert.fromJson(json['alert']),
        salesPerformance = SalesPerformance.fromJson(json['salesPerformance']);
        // ...dailyObservation, watchedProduct, whatsHappening, insights, myStock, chat

  final Header header;
  final Alert? alert; // null -> hide the alert banner
  final SalesPerformance salesPerformance;
}

class SalesPerformance {
  SalesPerformance.fromJson(Map<String, dynamic> json)
      : monthlySales = (json['monthlySales'] as List).map((e) => (e as num).toDouble()).toList(),
        monthLabels = List<String>.from(json['monthLabels']),
        highlightIndex = json['highlightIndex'] as int,
        stockPercent = json['stockPercent'] as String?, // null -> show stockNote only
        stockNote = json['stockNote'] as String;
        // ...annotation, quickPrompts

  final List<double> monthlySales;
  final List<String> monthLabels;
  final int highlightIndex;
  final String? stockPercent;
  final String stockNote;
}
```
