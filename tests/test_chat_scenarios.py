"""Live end-to-end scenarios for POST /chat: 50 prompts against a running server.

Exercises both the model call (real Gemini API, via `provider="gemini"`) and the
parent agent's stage-routing decision (`ParentAgent.pick_agent`, see
`agents/parent_agent.py`). Opt-in only, since each scenario makes a real, billed
API call: set RUN_LIVE_CHAT_TESTS=1 and have the target server running with a
GEMINI_API_KEY configured. Point at a non-default server with CHAT_TEST_BASE_URL.
"""

import os

import httpx
import pytest

BASE_URL = os.getenv("CHAT_TEST_BASE_URL", "http://localhost:8000")

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_CHAT_TESTS") != "1",
    reason="Set RUN_LIVE_CHAT_TESTS=1 to run live /chat scenarios against a running server.",
)

EARLY_STAGE_PROMPTS = [
    "I just opened my duka last month, how do I decide what stock to buy first?",
    "Should I extend credit to regular customers or insist on cash only?",
    "How do I set prices when I don't yet know my true costs?",
    "What's the simplest way to track daily sales without an accountant?",
    "A supplier is offering a bulk discount I can't fully afford yet, take it or pass?",
    "How many product lines should a brand-new duka carry to start?",
    "Should I rent a bigger shop now or wait until I have more customers?",
    "How do I know if my rent is too high for my current sales?",
    "What records do I need to keep from day one to avoid problems later?",
    "Is it worth hiring a part-time helper this early, or run it alone?",
    "How should I decide between two nearby locations for my first shop?",
    "A customer wants a big order on credit, how do I decide whether to accept?",
    "What's a reasonable starting markup for grocery items?",
    "Should I take a small loan to buy a fridge for cold drinks?",
    "How do I choose which supplier to commit to first?",
    "What's the first financial milestone I should aim for in year one?",
]

GROWTH_STAGE_PROMPTS = [
    "Sales are growing fast but stockouts are hurting me, how do I fix reordering?",
    "Should I open a second location or invest in a bigger single store?",
    "How do I decide which staff member is ready to manage a shift alone?",
    "My best-selling product's supplier just raised prices, switch or absorb the cost?",
    "How should I split my budget between restocking and marketing this quarter?",
    "Is it time to introduce a POS system instead of manual records?",
    "How do I decide which slow-moving products to discontinue?",
    "Should I negotiate longer payment terms with suppliers now that I order more?",
    "How do I plan inventory for an upcoming holiday sales spike?",
    "What's the right way to decide if a second location is actually profitable?",
    "Should I take on a business partner to fund faster expansion?",
    "How do I balance offering credit to loyal customers against cash flow needs?",
    "My competitor cut prices nearby, should I match them or differentiate?",
    "How do I decide which of three suppliers offers the best long-term deal?",
    "Is it time to hire a dedicated person for procurement?",
    "How should I decide between reinvesting profit or taking a draw this quarter?",
]

MATURE_STAGE_PROMPTS = [
    "Across five locations, how should I decide where to cut costs first?",
    "Should I centralize procurement across all my branches or let each manage its own?",
    "How do I decide which underperforming branch to close or restructure?",
    "What's the right approach to negotiate an exclusive supply contract at our volume?",
    "How should I structure regional manager incentives to align with company goals?",
    "Should we diversify into a new product category or deepen our current lines?",
    "How do I decide whether to invest in a warehouse versus more retail locations?",
    "What's the best way to evaluate a franchise expansion opportunity?",
    "How should I decide on a data-driven approach to seasonal inventory across branches?",
    "Is it time to formalize a credit policy company-wide instead of per-branch discretion?",
    "How do I decide which branches should pilot a new loyalty program first?",
    "Should we bring logistics in-house or continue outsourcing delivery?",
    "How do I decide the right debt-to-equity mix for funding our next expansion?",
    "What's the right framework for deciding annual capital expenditure across branches?",
    "How should I decide whether to acquire a smaller competitor or grow organically?",
    "How do I decide which branch managers are ready for equity participation?",
]

EDGE_CASE_PROMPTS = [
    ("What should I focus on this month?", None),
    ("What should I focus on this month?", "unknown_stage"),
]

SCENARIOS: list[tuple[str, str | None]] = (
    [(p, "early_stage") for p in EARLY_STAGE_PROMPTS]
    + [(p, "growth_stage") for p in GROWTH_STAGE_PROMPTS]
    + [(p, "mature_stage") for p in MATURE_STAGE_PROMPTS]
    + EDGE_CASE_PROMPTS
)

EXPECTED_AGENT_FOR_LEVEL = {
    "early_stage": "early_stage",
    "growth_stage": "growth_stage",
    "mature_stage": "mature_stage",
    None: "early_stage",  # ParentAgent's default_agent
    "unknown_stage": "early_stage",  # falls back to default_agent
}


@pytest.mark.parametrize(
    "prompt,level",
    SCENARIOS,
    ids=[f"{level or 'no-level'}-{i}" for i, (_, level) in enumerate(SCENARIOS)],
)
def test_chat_scenario(prompt: str, level: str | None) -> None:
    """Send a real prompt through /chat and check the model responds and routing is correct."""
    payload = {"prompt": prompt, "level": level, "provider": "gemini"}
    response = httpx.post(f"{BASE_URL}/chat", json=payload, timeout=60)

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["agent"] == EXPECTED_AGENT_FOR_LEVEL[level]
    assert isinstance(body["response"], str)
    assert body["response"].strip()
