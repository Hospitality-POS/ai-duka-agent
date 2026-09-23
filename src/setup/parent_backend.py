"""HTTP client for the Parent Backend Engine (the BasePoint Hospitality POS API).

Only `get_catalog`, `list_orders`, `get_stock_levels`, and `list_procurement` are backed by
real endpoints, confirmed against the Biggie API Postman collection. `list_locations`,
`list_invoices`, `create_sale`, and `get_day_summary` have no matching endpoint yet (no
`/shops` or `/cart` namespace exists in that collection) and raise NotImplementedError
until those are confirmed.
"""

from __future__ import annotations

import os

import httpx

PARENT_BACKEND_BASE_URL = os.getenv(
    "PARENT_BACKEND_BASE_URL", "https://api.hospitality.reliatech.co.ke"
)


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
        categories = self._client.get("/product/products/getproducts/all").json()
        inventory = self._client.get("/product-inventory").json()
        inventory_by_product = {item["product_id"]: item for item in inventory}

        catalog = []
        for category in categories:
            category_path = category.get("category_path", category.get("name"))
            for product in category.get("products", []):
                stock = inventory_by_product.get(product.get("_id"), {})
                catalog.append(
                    {
                        **product,
                        "category_path": category_path,
                        "unit_id": stock.get("unit_id"),
                        "quantity": stock.get("quantity"),
                    }
                )
        return catalog

    def list_orders(self, user_id: str, start_date: str, end_date: str) -> list[dict]:
        """Fetch a shop's orders in a date range, flattened to line items, payments, and tax."""
        orders = self._client.get(
            "/orders",
            params={"shop_id": user_id, "start_date": start_date, "end_date": end_date},
        ).json()
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
        inventory = self._client.get("/product-inventory").json()
        deliveries = self._client.get("/delivery").json()
        orders = self._client.get("/orders", params={"shop_id": user_id}).json()
        return [{"inventory": inventory, "deliveries": deliveries, "orders": orders}]

    def list_procurement(self, user_id: str) -> list[dict]:
        """Fetch purchase orders joined with their deliveries, adding outstanding quantity."""
        purchase_orders = self._client.get("/purchase-orders").json()
        deliveries = self._client.get("/delivery").json()

        deliveries_by_po: dict[str, list[dict]] = {}
        for delivery in deliveries:
            deliveries_by_po.setdefault(delivery.get("purchase_order_id"), []).append(delivery)

        procurement = []
        for order in purchase_orders:
            po_deliveries = deliveries_by_po.get(order.get("_id"), [])
            delivered_qty = sum(d.get("quantity", 0) for d in po_deliveries)
            ordered_qty = sum(item.get("quantity", 0) for item in order.get("items", []))
            procurement.append(
                {
                    **order,
                    "deliveries": po_deliveries,
                    "outstanding_qty": ordered_qty - delivered_qty,
                }
            )
        return procurement

    def list_locations(self, user_id: str) -> list[dict]:
        """Raise: no shop-listing endpoint exists in the Parent Backend API yet."""
        raise NotImplementedError("No /shops endpoint exists in the Parent Backend API yet.")

    def list_invoices(self, user_id: str) -> list[dict]:
        """Raise: no invoices endpoint exists in the Parent Backend API yet."""
        raise NotImplementedError("No /cart/invoices endpoint exists in the Parent Backend API yet.")

    def get_day_summary(self, user_id: str) -> dict:
        """Raise: no endpoint exists yet to compose a day summary from."""
        raise NotImplementedError("No /cart/invoices endpoint exists in the Parent Backend API yet.")

    def create_sale(self, user_id: str, cart_payload: dict) -> dict:
        """Raise: no cart/checkout endpoint exists in the Parent Backend API yet."""
        raise NotImplementedError("No /cart or /checkout endpoint exists in the Parent Backend API yet.")
