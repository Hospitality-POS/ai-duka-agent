"""Business identity onboarding/refresh flow.

Orchestrates the path described in the onboarding flowchart: once a user has
enabled the AI feature, the engine checks whether they are an existing user
(with data already in the Parent Backend Engine) or a new user (who instead
answers an onboarding questionnaire). Both paths converge on a
:class:`BusinessBlueprint`, which the identity agent turns into a
:class:`BusinessDigitalInstance` — a narrative "digital twin" of the
business. The blueprint is persisted to the vector database, scored by the
business leveling engine, and handed to the goal-oriented agent.

The Parent Backend Engine, vector store, leveling engine, goal-oriented
agent, and chat model client are external systems that don't exist in this
repo yet, so they are expressed as ``Protocol`` interfaces. Callers inject
real implementations (e.g. the OpenRouter/Gemini clients from
`model_provider.py`) once those systems are built; nothing here makes
network calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from encryption.rsa_crypto import encrypt_rsa


# --------------------------------------------------------------------------
# Data shapes
# --------------------------------------------------------------------------


@dataclass
class BusinessBlueprint:
    """A snapshot of a business assembled from either live data or onboarding answers."""

    user_id: str
    locations: list[dict] = field(default_factory=list)
    catalog: list[dict] = field(default_factory=list)
    orders: list[dict] = field(default_factory=list)
    stock_levels: list[dict] = field(default_factory=list)
    invoices: list[dict] = field(default_factory=list)
    procurement: list[dict] = field(default_factory=list)
    day_summary: dict | None = None
    onboarding_answers: dict[str, str] | None = None
    business_age_years: int | None = None
    digital_instance: "BusinessDigitalInstance | None" = None


@dataclass
class BusinessDigitalInstance:
    """The AI-generated "digital instance" of a business: a narrative identity."""

    user_id: str
    narrative: str
    key_facts: dict = field(default_factory=dict)


@dataclass
class BusinessLevel:
    """Result of the business leveling/grouping engine."""

    level: str
    target: dict
    exceptions: list[str] = field(default_factory=list)


@dataclass
class Goal:
    """A single goal allocated to the business by the goal-oriented agent."""

    name: str
    description: str
    condition: str


# --------------------------------------------------------------------------
# External system interfaces
# --------------------------------------------------------------------------


class ParentBackendClient(Protocol):
    """Read/write access to the Parent Backend Engine's business APIs."""

    def list_locations(self, user_id: str) -> list[dict]: ...
    def get_catalog(self, user_id: str) -> list[dict]: ...
    def list_orders(self, user_id: str, start_date: str, end_date: str) -> list[dict]: ...
    def get_stock_levels(self, user_id: str) -> list[dict]: ...
    def list_invoices(self, user_id: str) -> list[dict]: ...
    def list_procurement(self, user_id: str) -> list[dict]: ...
    def get_day_summary(self, user_id: str) -> dict: ...
    def create_sale(self, user_id: str, cart_payload: dict) -> dict: ...


class VectorStore(Protocol):
    """Storage used for the chatting feature's quick-response lookups."""

    def upsert(self, user_id: str, blueprint: BusinessBlueprint) -> None: ...


class BusinessLevelingEngine(Protocol):
    """Scores a business and assigns it a level/target ("grouping business")."""

    def assess(self, blueprint: BusinessBlueprint) -> BusinessLevel: ...


class GoalOrientedAgent(Protocol):
    """Allocates goals to a business based on its blueprint and level."""

    def allocate_goals(self, blueprint: BusinessBlueprint, level: BusinessLevel) -> list[Goal]: ...


class ChatModelClient(Protocol):
    """A chat-completion model (OpenRouter or Gemini, see `model_provider.py`)."""

    def complete(self, prompt: str) -> str: ...


# --------------------------------------------------------------------------
# Existing-user path
# --------------------------------------------------------------------------


def is_existing_user(user_id: str, parent_backend: ParentBackendClient) -> bool:
    """Return True if the Parent Backend Engine already has data for this user."""
    return bool(parent_backend.list_locations(user_id))


def build_blueprint_from_backend(
    user_id: str, parent_backend: ParentBackendClient, start_date: str, end_date: str
) -> BusinessBlueprint:
    """Call the Parent Backend Engine and compose a current blueprint of the user."""
    return BusinessBlueprint(
        user_id=user_id,
        locations=parent_backend.list_locations(user_id),
        catalog=parent_backend.get_catalog(user_id),
        orders=parent_backend.list_orders(user_id, start_date, end_date),
        stock_levels=parent_backend.get_stock_levels(user_id),
        invoices=parent_backend.list_invoices(user_id),
        procurement=parent_backend.list_procurement(user_id),
        day_summary=parent_backend.get_day_summary(user_id),
    )


# --------------------------------------------------------------------------
# New-user path
# --------------------------------------------------------------------------

ONBOARDING_QUESTIONS: list[str] = [
    "What does your business sell?",
    "How many locations do you operate?",
    "What is your primary goal for using this AI feature?",
    "How do you currently track stock and sales?",
]


def get_onboarding_questions() -> list[str]:
    """Return the ordered questions the app should present to a new user."""
    return list(ONBOARDING_QUESTIONS)


def build_blueprint_from_answers(user_id: str, answers: dict[str, str]) -> BusinessBlueprint:
    """Compose a blueprint for a new user from their onboarding answers."""
    return BusinessBlueprint(user_id=user_id, onboarding_answers=answers)


# --------------------------------------------------------------------------
# Business identity agent
# --------------------------------------------------------------------------


def build_identity_prompt(blueprint: BusinessBlueprint) -> str:
    """Compose the prompt used to turn a blueprint into a digital instance."""
    if blueprint.onboarding_answers is not None:
        facts = "\n".join(
            f"- {question}: {answer}" for question, answer in blueprint.onboarding_answers.items()
        )
    else:
        facts = (
            f"- Locations: {len(blueprint.locations)}\n"
            f"- Catalog items: {len(blueprint.catalog)}\n"
            f"- Orders: {len(blueprint.orders)}\n"
            f"- Stock levels: {len(blueprint.stock_levels)}\n"
            f"- Invoices: {len(blueprint.invoices)}\n"
            f"- Procurement records: {len(blueprint.procurement)}\n"
            f"- Day summary: {blueprint.day_summary or 'unavailable'}"
        )
    return (
        "You are building a digital identity profile for a small business, based on the "
        "facts below. Write a concise narrative describing what the business does, how it "
        "operates, and what stands out about it.\n\n"
        f"{facts}"
    )


def create_digital_instance(
    blueprint: BusinessBlueprint, model_client: ChatModelClient
) -> tuple[BusinessDigitalInstance | None, str]:
    """Use the chat model to synthesize a digital instance from a business blueprint."""
    prompt = build_identity_prompt(blueprint)
    try:
        narrative = model_client.complete(prompt)
    except Exception as exc:  # pragma: no cover - defensive branch
        return None, f"An error occurred while generating the digital instance: {exc}"

    if not narrative:
        return None, "The chat model returned an empty digital instance."

    key_facts = blueprint.onboarding_answers or {
        "locations": len(blueprint.locations),
        "catalog_items": len(blueprint.catalog),
        "orders": len(blueprint.orders),
    }
    instance = BusinessDigitalInstance(
        user_id=blueprint.user_id, narrative=narrative, key_facts=key_facts
    )
    return instance, "Digital instance created successfully."


# --------------------------------------------------------------------------
# Shared downstream steps
# --------------------------------------------------------------------------


def onboard_or_refresh_business(
    user_id: str,
    parent_backend: ParentBackendClient,
    vector_store: VectorStore,
    leveling_engine: BusinessLevelingEngine,
    goal_agent: GoalOrientedAgent,
    model_client: ChatModelClient,
    start_date: str,
    end_date: str,
    onboarding_answers: dict[str, str] | None = None,
) -> tuple[BusinessBlueprint, BusinessLevel, list[Goal]]:
    """Run the full onboarding/refresh flow for a user and return the results.

    For an existing user, `onboarding_answers` is ignored and data is pulled
    from the Parent Backend Engine. For a new user, pass their answers to
    `get_onboarding_questions()` here instead of hitting the backend.
    """
    if is_existing_user(user_id, parent_backend):
        blueprint = build_blueprint_from_backend(user_id, parent_backend, start_date, end_date)
    else:
        blueprint = build_blueprint_from_answers(user_id, onboarding_answers or {})

    instance, _message = create_digital_instance(blueprint, model_client)
    blueprint.digital_instance = instance

    vector_store.upsert(user_id, blueprint)
    level = leveling_engine.assess(blueprint)
    goals = goal_agent.allocate_goals(blueprint, level)
    return blueprint, level, goals


# --------------------------------------------------------------------------
# Response assembly
# --------------------------------------------------------------------------


def build_user_response(blueprint: BusinessBlueprint, level: BusinessLevel, goals: list[Goal]) -> dict:
    """Assemble the JSON-able response describing a business's level and allocated goals."""
    return {
        "user_id": blueprint.user_id,
        "narrative": blueprint.digital_instance.narrative if blueprint.digital_instance else None,
        "level": level.level,
        "level_exceptions": level.exceptions,
        "goals": [
            {"name": goal.name, "description": goal.description, "condition": goal.condition}
            for goal in goals
        ],
    }


def encrypt_user_response(response: dict, public_key) -> bytes:
    """Serialize a user response to JSON and RSA-encrypt it for transport back to the user.

    RSA-OAEP can only encrypt a payload smaller than the key size (roughly 190 bytes
    for a 2048-bit key with SHA-256 padding), so keep `response` compact - e.g. goal
    names and a level, not full narratives - or encrypt is expected to raise.
    """
    return encrypt_rsa(json.dumps(response), public_key)
