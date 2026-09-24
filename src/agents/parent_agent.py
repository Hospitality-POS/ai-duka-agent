"""The parent agent: routes a user prompt to the right specialist agent and back.

Flow: a user prompt reaches `ParentAgent.handle()` -> the parent picks the specialist
agent for the business's growth stage (`BusinessLevel.level`, from
`business_growth_strategy/leveling_engine.py`) -> the prompt is sent to that agent ->
the agent processes it with a `ChatModelClient` using its stage's session system prompt
(from `early_stage.py` / `growth_stage.py` / `mature_stage.py`) -> the agent's answer is
returned to the parent -> the parent returns it, ready for the caller (a FastAPI route)
to send back to the user.
"""

from __future__ import annotations

from typing import Protocol

from business_growth_strategy import early_stage, growth_stage, mature_stage
from setup.business_identity import ChatModelClient


class Agent(Protocol):
    """A specialist that turns a user prompt into an answer."""

    name: str

    def handle(self, prompt: str) -> str: ...


REPLY_STYLE_INSTRUCTION = (
    "Reply style: this is a chat, not an essay. Answer only what was asked, in 3-6 short "
    "sentences or a tight bullet list - a busy shop owner needs to read this on their phone "
    "in a few seconds. Skip session topics the user didn't ask about. Only go deeper, cite a "
    "formula, or cover another topic if the user explicitly asks for it."
)


class StageAdvisorAgent:
    """Answers business-growth questions using one growth stage's session system prompt."""

    def __init__(self, name: str, system_prompt: str, model_client: ChatModelClient) -> None:
        self.name = name
        self._system_prompt = system_prompt
        self._model_client = model_client

    def handle(self, prompt: str) -> str:
        """Send the stage's system prompt plus the user's question to the model."""
        return self._model_client.complete(
            f"{self._system_prompt}\n\n{REPLY_STYLE_INSTRUCTION}\n\nUser question: {prompt}"
        )


STAGE_PROMPT_BUILDERS = {
    "early_stage": early_stage.full_session_system_prompt,
    "growth_stage": growth_stage.full_session_system_prompt,
    "mature_stage": mature_stage.full_session_system_prompt,
}


def build_stage_advisor_agents(model_client: ChatModelClient) -> dict[str, Agent]:
    """Build one stage-advisor agent per growth stage, all sharing the given model client."""
    return {
        stage: StageAdvisorAgent(stage, build_prompt(), model_client)
        for stage, build_prompt in STAGE_PROMPT_BUILDERS.items()
    }


class ParentAgent:
    """Routes a user prompt to the agent for the business's growth stage and returns its answer."""

    def __init__(self, agents: dict[str, Agent], default_agent: str = "early_stage") -> None:
        self._agents = agents
        self._default_agent = default_agent

    def pick_agent(self, level: str | None) -> Agent:
        """Return the agent assigned to `level`, falling back to the default agent."""
        return self._agents.get(level, self._agents[self._default_agent])

    def handle(self, prompt: str, level: str | None) -> str:
        """Route `prompt` to the agent for `level` and return that agent's answer."""
        agent = self.pick_agent(level)
        return agent.handle(prompt)
