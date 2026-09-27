import httpx

from agents.parent_agent import ParentAgent, build_stage_advisor_agents
from ai_lining.chat_context import (
    INVENTORY_ITEM_LIMIT,
    build_chat_context,
    build_dashboard_context,
    build_inventory_context,
)
from ai_lining.dashboard import MockDashboardDataSource


class RecordingModelClient:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "ok"


def test_dashboard_context_includes_shop_data_but_not_ui_fields() -> None:
    context = build_dashboard_context("shop_1", MockDashboardDataSource())

    assert context is not None
    assert "Silikhe's Shop" in context
    assert "78 units" in context
    assert "Ksh 274,000" in context
    assert "quickPrompts" not in context
    assert "Start a Chat" not in context


def test_parent_agent_sends_context_before_user_question() -> None:
    model_client = RecordingModelClient()
    parent_agent = ParentAgent(build_stage_advisor_agents(model_client))

    parent_agent.handle("Should I restock coffee?", "early_stage", "SHOP DATA")

    prompt = model_client.prompts[0]
    assert prompt.index("SHOP DATA") < prompt.index("User question: Should I restock coffee?")


def test_parent_agent_omits_context_when_none() -> None:
    model_client = RecordingModelClient()
    ParentAgent(build_stage_advisor_agents(model_client)).handle("Hi", None)

    assert "live dashboard data" not in model_client.prompts[0]


class _StubInventoryBackend:
    def __init__(self, items: list[dict] | None = None, exc: Exception | None = None) -> None:
        self.items = items or []
        self.exc = exc

    def get_inventory(self, user_id: str) -> list[dict]:
        if self.exc:
            raise self.exc
        return self.items


INVENTORY = [
    {"_id": "p1", "name": "Sugar 1kg", "quantity": 40, "price": 180, "supplier_price": 150},
    {"_id": "p2", "name": "Morning Coffee", "quantity": 0, "price": 250, "supplier_price": 120},
    {"_id": "p3", "name": "Bread", "quantity": "12", "price": 65},
]


def test_inventory_context_lists_lowest_stock_first_with_totals() -> None:
    context = build_inventory_context("shop1", _StubInventoryBackend(INVENTORY))

    assert context is not None
    assert "3 items, 1 out of stock, total stock value at cost Ksh 6,000." in context
    assert context.index("Morning Coffee: 0 in stock") < context.index("Bread: 12 in stock")
    assert "Sugar 1kg: 40 in stock | sells Ksh 180 | costs Ksh 150" in context


def test_inventory_context_caps_long_catalogs() -> None:
    items = [{"name": f"Item {i}", "quantity": i} for i in range(INVENTORY_ITEM_LIMIT + 10)]
    context = build_inventory_context("shop1", _StubInventoryBackend(items))

    assert context is not None
    assert f"Listing the {INVENTORY_ITEM_LIMIT} lowest-stock items." in context
    assert f"Item {INVENTORY_ITEM_LIMIT + 9}:" not in context


def test_inventory_context_is_skipped_when_backend_is_down() -> None:
    backend = _StubInventoryBackend(exc=httpx.ConnectError("refused"))
    assert build_inventory_context("shop1", backend) is None


def test_chat_context_combines_dashboard_and_inventory() -> None:
    context = build_chat_context(
        "shop1", MockDashboardDataSource(), _StubInventoryBackend(INVENTORY)
    )

    assert context is not None
    assert "Silikhe's Shop" in context
    assert "Sugar 1kg: 40 in stock" in context
