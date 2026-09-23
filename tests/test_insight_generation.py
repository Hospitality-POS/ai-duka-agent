from ai_lining.analytics import compute_daily_observation, compute_watched_product
from ai_lining.insight_generation import generate_insights


class _StubModelClient:
    def __init__(self, response: str | None = None, raise_error: bool = False):
        self._response = response
        self._raise_error = raise_error

    def complete(self, prompt: str) -> str:
        if self._raise_error:
            raise RuntimeError("model unavailable")
        return self._response


def _sample_metrics():
    orders = [
        {
            "created_at": "2026-01-15T07:00:00",
            "line_items": [{"product_id": "prod1", "quantity": 2, "unit_price": 500}],
        }
    ]
    watched_product, _alert = compute_watched_product(
        orders, {"prod1": 10}, {"prod1": "Morning Coffee"}, 1, 2.0
    )
    daily_observation = compute_daily_observation(orders, [])
    return watched_product, daily_observation


def test_generate_insights_parses_up_to_three_lines() -> None:
    watched_product, daily_observation = _sample_metrics()
    client = _StubModelClient(response="Insight one\n- Insight two\n* Insight three\nInsight four")

    insights = generate_insights(client, watched_product, daily_observation)

    assert [i.text for i in insights] == ["Insight one", "Insight two", "Insight three"]
    assert [i.id for i in insights] == ["insight_1", "insight_2", "insight_3"]


def test_generate_insights_falls_back_on_model_failure() -> None:
    watched_product, daily_observation = _sample_metrics()
    client = _StubModelClient(raise_error=True)

    insights = generate_insights(client, watched_product, daily_observation)

    assert len(insights) == 1
    assert insights[0].id == "insight_unavailable"
