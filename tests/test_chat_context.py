from agents.parent_agent import ParentAgent, build_stage_advisor_agents
from ai_lining.chat_context import build_dashboard_context
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
