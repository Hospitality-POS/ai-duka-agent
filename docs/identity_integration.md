# Business Digital Identity — App Integration Guide

How the Flutter app builds a shop's **digital identity** once, stores it, and reuses it.
The identity is an AI-written profile of the business: a short narrative, a growth-stage
**level**, and three goals. The level then tunes every chat answer to the shop's stage.

Same setup as the dashboard (base URL, `Authorization: Bearer`, `companycode` header,
using `shopId` as the id). See [`ai_lining_integration.md`](ai_lining_integration.md#1-setup).

## 1. When to call it: once

Call `POST /identity/{shopId}` **once per shop**, right after the user turns on the AI
feature, then store the result on the device. Don't call it on every launch:

- Each call rebuilds the identity from scratch with two AI model calls, so it's slow
  (usually 5–20 s) and costs money.
- **The server doesn't remember it.** "Once" is up to the app: if the app calls again, the
  server builds a new identity.

Call it again only when:

- the user taps a **"Refresh my business profile"** action (e.g. in settings), or
- the app has no stored identity for the current shop (fresh install, logout, shop switch).

## 2. Flow

```
User enables AI feature
        │
        ▼
Stored identity for this shopId? ── yes ──► use it (skip to step 4)
        │ no
        ▼
POST /identity/{shopId}  {}          ◄── "Building your business profile…" screen
        │
        ├── 200 ─────────────────────────► store it ─► show identity screen
        │
        └── 422 (shop not in Parent Backend = new business)
                │
                ▼
        GET /identity/questions ─► onboarding form
                │
                ▼
        POST /identity/{shopId}  {"answers": {...}} ─► 200 ─► store ─► show
```

### Step 1: try building from the shop's data

```http
POST /identity/67841c7f52c7b8888375503b
Authorization: Bearer <token>
companycode: <tenant code>
Content-Type: application/json

{}
```

For a shop the Parent Backend knows, the engine reads its last 30 days of orders plus
its catalog, invoices and purchase orders, and builds the identity from them. The user
doesn't have to type anything.

### Step 2: if `422`, show the onboarding questions

A `422` means the Parent Backend has no record of this shop, so there's no data to build
from and the user answers a few questions instead.

```http
GET /identity/questions
```

```json
{
  "questions": [
    "What does your business sell?",
    "How many locations do you operate?",
    "What is your primary goal for using this AI feature?",
    "How do you currently track stock and sales?"
  ]
}
```

Render one text field per question, in order. Don't hardcode the list, because it can
change on the server.

### Step 3: send the answers

Key each answer by the **exact question text**:

```json
{
  "answers": {
    "What does your business sell?": "Coffee, pastries and breakfast snacks",
    "How many locations do you operate?": "1",
    "What is your primary goal for using this AI feature?": "Stop running out of stock",
    "How do you currently track stock and sales?": "Notebook and M-Pesa statements"
  }
}
```

Answers are ignored for shops the Parent Backend already knows. For those, the shop's
real data always wins.

### Step 4: response `200`

```json
{
  "user_id": "67841c7f52c7b8888375503b",
  "narrative": "Silikhe's Shop is a single-location coffee duka whose sales peak during the morning rush...",
  "level": "early_stage",
  "level_exceptions": [],
  "goals": [
    {
      "name": "Eliminate morning stockouts",
      "description": "Keep Morning Coffee in stock through the 6:30–9:30 AM peak.",
      "condition": "Zero stockout days on coffee for 4 consecutive weeks"
    }
  ]
}
```

| Field | Notes |
|---|---|
| `user_id` | The shop id you sent. |
| `narrative` | Plain-text profile, a few sentences long. **Can be `null`** if the model call failed; see below. |
| `level` | `early_stage`, `growth_stage` or `mature_stage`. **Store this and send it with every `/chat` call.** |
| `level_exceptions` | Usually empty. Notes where the level is uncertain; you can hide these from users. |
| `goals` | Usually 3 goals, each with `name`, `description` and `condition` (how success is measured). **Can be `[]`** if the model's answer couldn't be read. |

## 3. What to show

**While building:** a full-screen progress state ("Building your business profile…").
It takes several seconds, so use a 60 s request timeout, not the default.

**Identity screen:**

- **Header:** a stage badge from `level`:

  | `level` | Badge label |
  |---|---|
  | `early_stage` | Early stage |
  | `growth_stage` | Growing |
  | `mature_stage` | Established |

- **"About your business":** the `narrative`.
- **"Your goals":** one card per goal, with `name` as the title, `description` as the body,
  and `condition` as a smaller "Success looks like: …" line.
- **Continue** → the dashboard.

**Partial results:** if `narrative` is `null` or `goals` is empty, show what you have
plus a "Try again" button that repeats the POST. Still store `level`; it's always present
on a `200`.

## 4. Storing and reusing it

Store the whole `200` response on the device (e.g. `shared_preferences` as JSON), keyed
by shop, with the time it was built:

```dart
// key: 'identity:<shopId>'
{ "generatedAt": "2026-09-26T08:30:00Z", "identity": { ...the 200 response... } }
```

- **Every chat:** send the stored `level` as `/chat`'s `level`, so the advisor for the shop's
  stage answers.
- **Logout or shop switch:** clear it (or keep it keyed by shop and just switch keys).
- **Refresh:** "Refresh my business profile" repeats step 1 and overwrites the stored copy.
  A shop that has grown can move up a level.

## 5. Errors

| Status | Meaning | What the app should do |
|---|---|---|
| `401` | No bearer token sent, or the Parent Backend rejected it | Send the user to log in again |
| `422` | Shop unknown to the Parent Backend and no `answers` sent | Show the onboarding questions (step 2) |
| `502` | The Parent Backend is down or returned an error (`detail` says which) | "Couldn't reach your shop data, try again" |
| `503` | No AI model key is configured on the server | A config issue, so report it; don't retry in a loop |
| `500` | The AI model is overloaded | "Busy right now, try again in a moment" with retry |

Unlike the dashboard, identity has **no demo fallback**: if the Parent Backend is down,
you get a `502`. The identity would otherwise describe the demo shop instead of the user's.

## 6. Dart reference

Add to the `DukaApi` service from [`ai_lining_integration.md`](ai_lining_integration.md#5-dart-reference):

```dart
class ShopNotOnboarded implements Exception {}

Future<List<String>> identityQuestions() async {
  final body = await _send(http.get(Uri.parse('$baseUrl/identity/questions'), headers: _headers));
  return List<String>.from(body['questions']);
}

/// Throws [ShopNotOnboarded] when the shop needs onboarding answers first.
Future<Map<String, dynamic>> buildIdentity({Map<String, String>? answers}) async {
  try {
    return await _send(http
        .post(
          Uri.parse('$baseUrl/identity/$shopId'),
          headers: _headers,
          body: jsonEncode({if (answers != null) 'answers': answers}),
        )
        .timeout(const Duration(seconds: 60)));
  } on DukaApiException catch (e) {
    if (e.statusCode == 422) throw ShopNotOnboarded();
    rethrow;
  }
}
```

```dart
Future<Map<String, dynamic>> loadOrBuildIdentity(DukaApi api, SharedPreferences prefs) async {
  final key = 'identity:${api.shopId}';
  final stored = prefs.getString(key);
  if (stored != null) return jsonDecode(stored)['identity'];

  Map<String, dynamic> identity;
  try {
    identity = await api.buildIdentity();
  } on ShopNotOnboarded {
    final questions = await api.identityQuestions();
    final answers = await showOnboardingForm(questions); // your UI; returns {question: answer}
    identity = await api.buildIdentity(answers: answers);
  }

  await prefs.setString(key, jsonEncode({
    'generatedAt': DateTime.now().toUtc().toIso8601String(),
    'identity': identity,
  }));
  return identity;
}

// Every chat afterwards:
// api.chat(prompt, level: identity['level'] as String);
```
