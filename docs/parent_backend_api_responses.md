# Parent Backend Engine — Responses to Outstanding API Requests

Answers to `parent_backend_api_requests.md`, checked against the actual Biggie API
codebase. Every request needs the `companycode` header (tenant routing) and, where
noted, an `Authorization: Bearer <token>` header from `POST /users/login`.

## TL;DR — one call for the dashboard

`GET /biashara-ai/dashboard?shop_id=<id>` returns the full AI Lining payload —
`header`, `dailyObservation`, `watchedProduct`, `alert`, `whatsHappening`,
`insights`, `salesPerformance`, `myStock`, `chat` — computed from live data.
If `shop_id` is omitted it falls back to the shop assigned to the logged-in user.

| # | Need | Verdict | What to use |
|---|---|---|---|
| 1 | Single-shop lookup | Already exists | `GET /shops/:id` or `GET /shops` |
| 2 | `role` field | Already exists | `role` / `roleData.role_type` from `POST /users/login`, or JWT |
| 3 | `aiHealth` | Computed by the API | `header.aiHealth` in the dashboard response |
| 4 | Historical stock | **New endpoint** | `GET /product-inventory/stock-at?shop_id&date` |
| 5 | `supplier_price` = cost | Confirmed | `supplier_price` on `/product-inventory` items |
| 6 | Cart/checkout | Already exists | `POST /orders/create` finalizes the sale |
| 7 | Invoices | Already exists | `GET /accounting/invoices` (recommended) |

---

## 1. Single-shop lookup — `header.shopName`, `list_locations`

Both routes exist and are mounted at **two prefixes** (`/shops` and `/api/shops`);
they were simply missing from the Postman export.

- `GET /shops` — all shops (adds `staff_count` and `daily_revenue` per shop)
- `GET /shops/:id` — one shop: `_id`, `name`, `location`, `pos_mode`, `hotel_settings`, ...

```http
GET /shops/67841c7f52c7b8888375503b
companycode: <tenant code>
```

Also covered automatically: `GET /biashara-ai/dashboard?shop_id=...` puts
`shop.name` straight into `header.shopName`.

## 2. The "role" field — `header.role`

`POST /users/login` already returns everything needed:

```json
{
  "role": "manager",
  "roleData": { "role_type": "manager", "permissions": [], "description": "" },
  "rolePermissions": [],
  "shopId": "..."
}
```

- `role` / `roleData.role_type` is the display source. The same `role` string is
  embedded in the JWT, so the dashboard endpoint maps it for you
  (`manager` → `Store Manager`, `cashier` → `Cashier`, `admin` → `Admin`, etc.).
- `GET /users/:id` and `GET /users/shop/:shop_id` also attach `user.role`
  (`{ role_type, permissions, description }`) if you need it post-login.

## 3. "AI health" definition — `header.aiHealth`

Now computed server-side: the share of dashboard sections populated with real
data (shop found, role resolved, sales today, watched product, monthly sales,
inventory catalog). Example: `"aiHealth": "87%"`. No client work needed.

## 4. Historical stock snapshots — `salesPerformance.stockPercent`

**New endpoint:**

```http
GET /product-inventory/stock-at?shop_id=<id>&date=2026-08-26
companycode: <tenant code>
```

- `date` — ISO date or timestamp (EAT). Defaults to 30 days ago.
- Returns per-item `quantity_as_of` + `current_quantity` + `change_since`, and
  `totals` for the whole shop.

Reconstruction walks back every recorded movement after `date`: `inventory_usage`
outbound (signed `newQuantity − previousQuantity`), confirmed `delivery_items`
inbound, and `transfer_items` in/out. Caveat: manual quantity edits via
`PUT /product-inventory/:id` are not logged as movements, so reconstruction is
only as accurate as the movement records.

The dashboard endpoint uses the same logic for `salesPerformance.stockPercent` /
`stockNote`; when no movement history exists it returns `stockPercent: null` with
an explanatory `stockNote`.

## 5. Confirm the "cost" field — `myStock.capitalValue`

Confirmed: **`supplier_price` is unit cost** on `Product_Inventory`. It's mapped
to `cost_price` in the SmartReja sync, used as the purchase price on delivery
items, and is the cost basis for profit-margin analytics. `capitalValue` in the
dashboard response is `Σ(quantity × supplier_price)` over active items for the
shop. Items without `supplier_price` contribute 0 — worth checking data coverage
per tenant.

## 6. Cart/checkout — `create_sale`

The full POS flow already exists; **`POST /orders/create` is the finalize step**:

1. `POST /cart/create-cart` — `{ table_id, shop_id, created_by }` opens a cart
2. `POST /cart/add-item-to-cart` — `{ cart_id, product_id, product_type, quantity, price }`
3. `PUT /cart/send-cart` / `PUT /cart/print-cart` — kitchen/bill printing (optional)
4. `POST /orders/create` — `{ cart_id, method_id, shop_id, updated_by }` (or
   `payment_splits` for split tender) → creates the Order, OrderItems,
   OrderPayments, **and the Invoice** in one transaction.

`orders/create` also deducts inventory and posts the journal entry when the
accounting module is on. For the AI engine's `create_sale`, treat it as:
open cart → add items → `POST /orders/create` with the cart id.

## 7. Invoices — `list_invoices`

Both endpoints read the **same `Invoice` collection** — POS sales land there via
`orders/create`, manual bookkeeping invoices via the accounting UI.

- **`GET /accounting/invoices` — recommended.** Paginated
  (`page`, `limit`), filterable by `direction` (`customer`/`supplier`), `status`,
  `source`, `customer_id`, `supplier_id`, `from`/`to`, `search`.
- `GET /cart/invoices` — same data, POS-flavoured filters (`tableName`,
  `orderNo`, `invoiceNo`, `posted`) but no pagination. Fine for receipt-style
  lookups.

For `list_invoices`, use `/accounting/invoices?shop_id=<id>&direction=customer`.
