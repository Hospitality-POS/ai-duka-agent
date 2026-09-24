# Parent Backend Engine — Outstanding API Requests

What the Duka AI Engine still needs from the Parent Backend Engine (BasePoint API) to
finish replacing mock data in the AI Lining dashboard and the business-identity onboarding
flow. Checked against the Biggie API Postman collection and live responses from
`https://api.hospitality.reliatech.co.ke` on 2026-09-23.

## Summary

| # | Need | Status | Blocks |
|---|---|---|---|
| 1 | Single-shop lookup (`GET /shops` or `/shops/:id`) | Missing from collection, but the data model clearly exists | `header.shopName`, `list_locations` |
| 2 | Confirm the "role" field on a user/staff record | Likely already solved — needs confirmation | `header.role` |
| 3 | Define what "AI health" measures | Design question, not necessarily an API | `header.aiHealth` |
| 4 | Historical stock snapshots (past point-in-time quantity) | Likely doesn't exist yet | `salesPerformance.stockPercent`/`stockNote` |
| 5 | Confirm `supplier_price` is the "cost" field | Likely already solved — needs confirmation | `myStock.capitalValue` |
| 6 | Cart/checkout endpoint, or confirm `POST /orders/create` is it | Needs confirmation | `create_sale` |
| 7 | Confirm which invoices endpoint is the real one | Needs confirmation | `list_invoices` |

---

## 1. Single-shop lookup

**Need:** an endpoint that returns one shop's own record — at minimum `_id`, `name`.

**Why:** `header.shopName` in the AI Lining dashboard, and `list_locations` in the
onboarding flow (`business_identity.py`), have no data source. The dashboard currently
falls back to mock data for this field.

**What we already know:** the shop model clearly exists server-side — a populated
`shop_id` field inside `/purchase-orders` and `/delivery` responses returns a full nested
object:

```json
{
  "_id": "67841c7f52c7b8888375503b",
  "name": "shop 2",
  "location": { "address": "...", "city": "...", "country": "Kenya" },
  "pos_mode": "restaurant",
  "hotel_settings": { "...": "..." }
}
```

There's no `GET /shops` or `GET /shops/:id` in the Postman collection — please confirm
whether this route exists but was omitted from the export, or genuinely doesn't exist yet.

---

## 2. The "role" field

**Need:** confirmation of where a staff member's display role (e.g. "Store Manager") comes
from.

**Why:** `header.role` in the AI Lining dashboard.

**What we already know:** `POST /users/login` already returns:

```json
{ "roleData": { "role_type": "admin", "permissions": [], "description": "" } }
```

If `GET /users/:id` or `GET /users/shop/:shop_id` returns the same `roleData` shape, no new
endpoint is needed — just confirmation that `roleData.role_type` (or an equivalent field)
is the right source, and whether it needs mapping to a friendlier label (e.g.
`"manager"` → `"Store Manager"`).

---

## 3. "AI health" definition

**Need:** a decision, not necessarily an API — what does `aiHealth: "87%"` represent?

**Why:** it's a `header` field with no defined meaning yet. It may not be a Parent Backend
concept at all; it could instead be something the Duka AI Engine computes itself (e.g. the
percentage of dashboard sections successfully populated with real vs. fallback data for
that shop).

**Ask:** confirm whether this should come from an external metric, or be computed locally.

---

## 4. Historical stock snapshots

**Need:** a way to read a shop's stock quantity as of a past date (not just current).

**Why:** `salesPerformance.stockPercent` and `stockNote` ("You have 30% more stock
available than last month") require comparing current stock to a past point in time.
`GET /product-inventory` only returns the current snapshot.

**Ask:** does an audit-log, stock-history, or inventory-movement endpoint exist? If not,
the Duka AI Engine will need to start recording its own periodic snapshots going forward —
in which case this section stays on mock data until enough history accumulates regardless.

---

## 5. Confirm the "cost" field for capital calculations

**Need:** confirmation that `supplier_price` on a `/product-inventory` item is the correct
field to use as unit cost.

**Why:** `myStock.capitalValue` = Σ(quantity × cost) across the catalog. We already saw a
`supplier_price` field distinct from the selling `price`:

```json
{ "name": "USB-C Cable", "quantity": 5, "price": 150, "supplier_price": 80 }
```

**Ask:** confirm `supplier_price` is unit cost (not, say, a negotiated bulk rate that
doesn't reflect current on-hand stock cost), and whether it's populated consistently across
all products.

---

## 6. Cart/checkout endpoint

**Need:** confirmation of the real sale-creation flow.

**Why:** `create_sale` in the onboarding Protocol (`business_identity.py`) expects a
cart/checkout-style flow. The Postman collection only has `POST /orders/create`.

**Ask:** is `POST /orders/create` the actual entry point for creating a sale, or is there a
separate cart flow (hold cart → apply payment → finalize) not included in this collection
export?

---

## 7. Confirm the invoices endpoint

**Need:** confirmation of which invoices concept `list_invoices` should use.

**Why:** the collection has `GET /accounting/invoices` (bookkeeping/AR invoices) but no
`/cart/invoices`. These may be different concepts — accounting invoices for
receivables/bookkeeping vs. a POS sale receipt.

**Ask:** confirm whether `GET /accounting/invoices` is the right source, or point us to the
correct one if POS sale invoices are tracked separately.
