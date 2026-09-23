import httpx
import pytest

from setup.parent_backend import BasePointParentBackendClient

CATALOG_RESPONSES = {
    "/product/products/getproducts/all": [
        {
            "name": "Beverages",
            "products": [{"_id": "prod1", "name": "Morning Coffee"}],
        }
    ],
    "/product-inventory": [{"_id": "prod1", "unit_id": "unit1", "quantity": 42}],
}


def _client_with_routes(routes: dict[str, object]) -> BasePointParentBackendClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["companycode"] == "co1"
        assert request.headers["Authorization"] == "Bearer tok1"
        return httpx.Response(200, json=routes[request.url.path])

    client = BasePointParentBackendClient(company_code="co1", api_key="tok1")
    client._client = httpx.Client(
        base_url=client._client.base_url,
        headers=client._client.headers,
        transport=httpx.MockTransport(handler),
    )
    return client


def test_get_catalog_merges_inventory() -> None:
    client = _client_with_routes(CATALOG_RESPONSES)
    catalog = client.get_catalog("shop1")
    assert catalog == [
        {
            "_id": "prod1",
            "name": "Morning Coffee",
            "category_path": "Beverages",
            "unit_id": "unit1",
            "quantity": 42,
        }
    ]


def test_list_orders_flattens_line_items_and_payments() -> None:
    routes = {
        "/orders": [
            {
                "_id": "ord1",
                "order_items": [{"product_id": "prod1", "quantity": 2}],
                "order_payments": [{"method": "cash", "amount": 500}],
                "vat_breakdown": [{"rate": 0.16, "amount": 80}],
            }
        ]
    }
    client = _client_with_routes(routes)
    orders = client.list_orders("shop1", "2026-01-01", "2026-01-31")
    assert orders[0]["line_items"] == [{"product_id": "prod1", "quantity": 2}]
    assert orders[0]["payments"] == [{"method": "cash", "amount": 500}]
    assert orders[0]["tax_breakdown"] == [{"rate": 0.16, "amount": 80}]


def test_list_procurement_adds_outstanding_quantity() -> None:
    routes = {
        "/purchase-orders": [
            {"_id": "po1", "po_items": [{"quantity_ordered": 100, "quantity_received": 60}]}
        ],
        "/delivery": [{"purchase_order_id": {"_id": "po1"}, "delivery_items": [{"quantity": 60}]}],
    }
    client = _client_with_routes(routes)
    procurement = client.list_procurement("shop1")
    assert procurement[0]["outstanding_qty"] == 40
    assert procurement[0]["deliveries"] == routes["/delivery"]


def test_get_stock_levels_composes_inventory_deliveries_and_orders() -> None:
    routes = {
        "/product-inventory": [{"_id": "prod1", "quantity": 42}],
        "/delivery": [{"_id": "del1"}],
        "/orders": [{"_id": "ord1"}],
    }
    client = _client_with_routes(routes)
    stock_levels = client.get_stock_levels("shop1")
    assert stock_levels == [
        {
            "inventory": [{"_id": "prod1", "quantity": 42}],
            "deliveries": [{"_id": "del1"}],
            "orders": [{"_id": "ord1"}],
        }
    ]


@pytest.mark.parametrize(
    "method_name,args",
    [
        ("list_locations", ("shop1",)),
        ("list_invoices", ("shop1",)),
        ("get_day_summary", ("shop1",)),
        ("create_sale", ("shop1", {})),
    ],
)
def test_unbacked_methods_raise_not_implemented(method_name: str, args: tuple) -> None:
    client = BasePointParentBackendClient(company_code="co1", api_key="tok1")
    with pytest.raises(NotImplementedError):
        getattr(client, method_name)(*args)
