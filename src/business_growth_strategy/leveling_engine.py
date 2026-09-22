"""The business grouping engine: assigns a business to a growth-stage level.

`BusinessLevelingEngine` implements both the `BusinessLevelingEngine` and
`GoalOrientedAgent` protocols from `setup/business_identity.py`: it scores a
`BusinessBlueprint`'s data volume (locations, catalog, orders, invoices,
procurement) to classify the business as early/growth/mature stage,
cross-checks that against the business's declared age, attaches the matching
stage's system prompt (from `early_stage.py`, `growth_stage.py`,
`mature_stage.py`) to the level, and then reuses that same prompt to ask a
`ChatModelClient` for the business's goals. One instance can be injected for
both the `leveling_engine` and `goal_agent` parameters of
`onboard_or_refresh_business`.
"""

from __future__ import annotations

import json

from business_growth_strategy import early_stage, growth_stage, mature_stage
from setup.business_identity import BusinessBlueprint, BusinessLevel, ChatModelClient, Goal

STAGE_EARLY = "early_stage"
STAGE_GROWTH = "growth_stage"
STAGE_MATURE = "mature_stage"

STAGE_SYSTEM_PROMPTS = {
    STAGE_EARLY: early_stage.full_session_system_prompt,
    STAGE_GROWTH: growth_stage.full_session_system_prompt,
    STAGE_MATURE: mature_stage.full_session_system_prompt,
}

# Weights turn raw record counts into one comparable "scale score".
LOCATION_WEIGHT = 15
CATALOG_ITEM_WEIGHT = 1
ORDER_WEIGHT = 2
INVOICE_WEIGHT = 1
PROCUREMENT_WEIGHT = 1

GROWTH_STAGE_SCORE_THRESHOLD = 50
MATURE_STAGE_SCORE_THRESHOLD = 200

GROWTH_STAGE_MIN_AGE_YEARS = 2
MATURE_STAGE_MIN_AGE_YEARS = 5

GOAL_COUNT = 3


def compute_scale_score(blueprint: BusinessBlueprint) -> int:
    """Return a weighted score summarizing a business's operating data volume."""
    return (
        len(blueprint.locations) * LOCATION_WEIGHT
        + len(blueprint.catalog) * CATALOG_ITEM_WEIGHT
        + len(blueprint.orders) * ORDER_WEIGHT
        + len(blueprint.invoices) * INVOICE_WEIGHT
        + len(blueprint.procurement) * PROCUREMENT_WEIGHT
    )


def classify_by_scale(scale_score: int) -> str:
    """Map a scale score to the growth-stage level it corresponds to."""
    if scale_score >= MATURE_STAGE_SCORE_THRESHOLD:
        return STAGE_MATURE
    if scale_score >= GROWTH_STAGE_SCORE_THRESHOLD:
        return STAGE_GROWTH
    return STAGE_EARLY


def classify_by_age(business_age_years: int) -> str:
    """Map a business's age in years to the growth-stage level it corresponds to."""
    if business_age_years >= MATURE_STAGE_MIN_AGE_YEARS:
        return STAGE_MATURE
    if business_age_years >= GROWTH_STAGE_MIN_AGE_YEARS:
        return STAGE_GROWTH
    return STAGE_EARLY


def build_goal_allocation_prompt(blueprint: BusinessBlueprint, level: BusinessLevel) -> str:
    """Compose the prompt asking the model for SMART goals fitting this business's stage."""
    narrative = (
        blueprint.digital_instance.narrative if blueprint.digital_instance else "unavailable"
    )
    return (
        f"{level.target['system_prompt']}\n\n"
        f"Business narrative: {narrative}\n"
        f"Assigned growth stage: {level.level}\n\n"
        f"Propose exactly {GOAL_COUNT} SMART goals for this business. Respond with ONLY a "
        "JSON array of objects, each with the keys 'name', 'description', and 'condition' "
        "(the measurable success condition), and no other text."
    )


def _strip_markdown_fence(response: str) -> str:
    """Strip a leading/trailing ```json ... ``` fence, since models add one despite instructions."""
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.removesuffix("```").strip()
    return text


def parse_goals_response(response: str) -> list[Goal]:
    """Parse the model's JSON goal list into `Goal` objects, skipping malformed entries."""
    try:
        raw_goals = json.loads(_strip_markdown_fence(response))
    except json.JSONDecodeError:
        return []

    if not isinstance(raw_goals, list):
        return []

    return [
        Goal(name=item["name"], description=item["description"], condition=item["condition"])
        for item in raw_goals
        if isinstance(item, dict) and {"name", "description", "condition"} <= item.keys()
    ]


class BusinessLevelingEngine:
    """Groups a business into its growth stage and allocates that stage's goals."""

    def __init__(self, model_client: ChatModelClient) -> None:
        self._model_client = model_client

    def assess(self, blueprint: BusinessBlueprint) -> BusinessLevel:
        """Score a blueprint and return its assigned growth-stage level and target."""
        if blueprint.onboarding_answers is not None:
            stage = STAGE_EARLY
            target = {"system_prompt": STAGE_SYSTEM_PROMPTS[stage](), "scale_score": 0}
            return BusinessLevel(level=stage, target=target, exceptions=[])

        scale_score = compute_scale_score(blueprint)
        stage = classify_by_scale(scale_score)
        exceptions: list[str] = []

        if blueprint.business_age_years is not None:
            stage_by_age = classify_by_age(blueprint.business_age_years)
            if stage_by_age != stage:
                exceptions.append(
                    f"Business age ({blueprint.business_age_years} years) suggests the "
                    f"'{stage_by_age}' stage, but current performance data places it at "
                    f"'{stage}'; grouping by performance data."
                )

        target = {"system_prompt": STAGE_SYSTEM_PROMPTS[stage](), "scale_score": scale_score}
        return BusinessLevel(level=stage, target=target, exceptions=exceptions)

    def allocate_goals(self, blueprint: BusinessBlueprint, level: BusinessLevel) -> list[Goal]:
        """Ask the model for SMART goals matching the business's assigned growth stage."""
        prompt = build_goal_allocation_prompt(blueprint, level)
        response = self._model_client.complete(prompt)
        return parse_goals_response(response)
