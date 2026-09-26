"""HTTP client for the Parent Backend Engine (the BasePoint Hospitality POS API).

Only `get_catalog`, `list_orders`, `get_stock_levels`, and `list_procurement` are backed by
real endpoints, verified against live responses from
https://api.hospitality.reliatech.co.ke on 2026-09-23: `/product-inventory` items and
`/product/products/getproducts/all` products are both keyed by their own `_id` (no separate
`product_id` foreign key); `/purchase-orders`' `po_items` track `quantity_ordered` and
`quantity_received` directly (not a single `quantity`); list endpoints return a bare array
when there are results but a `{"data": [...]}` envelope on an empty result (see
`_list_body`). `get_dashboard`, `list_locations`, and `list_invoices` follow the Parent
Backend team's answers in `docs/parent_backend_api_responses.md`; `create_sale` and
`get_day_summary` are not wired up yet and raise NotImplementedError.
"""

from __future__ import annotations

import os

import httpx

PARENT_BACKEND_BASE_URL = os.getenv(
    "PARENT_BACKEND_BASE_URL", "https://api.hospitality.reliatech.co.ke"
)


def _list_body(response: httpx.Response) -> list[dict]:
    """Unwrap a list endpoint's body: a bare array, or `{"data": [...]}` on an empty result."""
    body = response.json()
    return body["data"] if isinstance(body, dict) else body


class BasePointParentBackendClient:
    """A `ParentBackendClient` (see `setup/business_identity.py`) backed by the real BasePoint API."""

    def __init__(
        self,
        base_url: str = PARENT_BACKEND_BASE_URL,
        company_code: str | None = None,
        api_key: str | None = None,
    ) -> None:
        company_code = company_code or os.getenv("PARENT_BACKEND_COMPANY_CODE", "")
        api_key = api_key or os.getenv("PARENT_BACKEND_API_KEY", "")
        self._client = httpx.Client(
            base_url=base_url,
            headers={"companycode": company_code, "Authorization": f"Bearer {api_key}"},
        )

    def get_catalog(self, user_id: str) -> list[dict]:
        """Fetch the product catalog grouped by category, merged with each product's stock unit."""
        categories = _list_body(self._client.get("/product/products/getproducts/all"))
        inventory = _list_body(self._client.get("/product-inventory"))
        inventory_by_id = {item["_id"]: item for item in inventory}

        catalog = []
        for category in categories:
            category_path = category.get("category_path", category.get("name"))
            for product in category.get("products", []):
                stock = inventory_by_id.get(product.get("_id"), {})
                catalog.append(
                    {
                        **product,
                        "category_path": category_path,
                        "unit_id": stock.get("unit_id"),
                        "quantity": stock.get("quantity", product.get("quantity")),
                    }
                )
        return catalog

    def list_orders(self, user_id: str, start_date: str, end_date: str) -> list[dict]:
        """Fetch a shop's orders in a date range, flattened to line items, payments, and tax."""
        orders = _list_body(
            self._client.get(
                "/orders",
                params={"shop_id": user_id, "start_date": start_date, "end_date": end_date},
            )
        )
        return [
            {
                **order,
                "line_items": order.get("order_items", []),
                "payments": order.get("order_payments", []),
                "tax_breakdown": order.get("vat_breakdown", []),
            }
            for order in orders
        ]

    def get_stock_levels(self, user_id: str) -> list[dict]:
        """Compose current stock levels from inventory, incoming deliveries, and recent orders."""
        inventory = _list_body(self._client.get("/product-inventory"))
        deliveries = _list_body(self._client.get("/delivery"))
        orders = _list_body(self._client.get("/orders", params={"shop_id": user_id}))
        return [{"inventory": inventory, "deliveries": deliveries, "orders": orders}]

    def list_procurement(self, user_id: str) -> list[dict]:
        """Fetch purchase orders joined with their deliveries, adding outstanding quantity."""
        purchase_orders = _list_body(self._client.get("/purchase-orders"))
        deliveries = _list_body(self._client.get("/delivery"))

        def _po_id(delivery: dict) -> str | None:
            po_ref = delivery.get("purchase_order_id")
            return po_ref.get("_id") if isinstance(po_ref, dict) else po_ref

        deliveries_by_po: dict[str, list[dict]] = {}
        for delivery in deliveries:
            deliveries_by_po.setdefault(_po_id(delivery), []).append(delivery)

        procurement = []
        for order in purchase_orders:
            outstanding_qty = sum(
                item.get("quantity_ordered", 0) - item.get("quantity_received", 0)
                for item in order.get("po_items", [])
            )
            procurement.append(
                {
                    **order,
                    "deliveries": deliveries_by_po.get(order.get("_id"), []),
                    "outstanding_qty": outstanding_qty,
                }
            )
        return procurement

    def get_dashboard(self, user_id: str) -> dict:
        """Fetch a shop's full AI Lining dashboard, computed by the Parent Backend from live data."""
        response = self._client.get("/biashara-ai/dashboard", params={"shop_id": user_id})
        response.raise_for_status()
        return response.json()

    def list_locations(self, user_id: str) -> list[dict]:
        """Fetch the shop's own record as a one-item list, or an empty list if it doesn't exist."""
        response = self._client.get(f"/shops/{user_id}")
        if response.status_code == 404:
            return []
        response.raise_for_status()
        return [response.json()]

    def list_invoices(self, user_id: str) -> list[dict]:
        """Fetch the shop's customer invoices (POS sales and manual bookkeeping invoices)."""
        return _list_body(
            self._client.get(
                "/accounting/invoices", params={"shop_id": user_id, "direction": "customer"}
            )
        )

    def get_day_summary(self, user_id: str) -> dict:
        """Raise: no endpoint exists yet to compose a day summary from."""
        raise NotImplementedError("No day-summary endpoint exists in the Parent Backend API yet.")

    def create_sale(self, user_id: str, cart_payload: dict) -> dict:
        """Raise: the cart -> `POST /orders/create` checkout flow is not wired up yet."""
        raise NotImplementedError("create_sale (cart -> /orders/create) is not wired up yet.")
