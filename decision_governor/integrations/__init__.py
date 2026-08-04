"""Card G-7: integrations behind extras.

The submodules themselves import their optional dependencies lazily
(never at module top), so these re-exports are safe on the base install:
importing this package must never require `[fastapi]` or `[llm]`.
"""
from decision_governor.integrations.fastapi import GovernorMiddleware
from decision_governor.integrations.llm_judge import (
    AnthropicProvider,
    LLMJudgeCheck,
    OpenAICompatibleProvider,
    Provider,
    is_floating_alias,
)

__all__ = [
    "AnthropicProvider",
    "GovernorMiddleware",
    "LLMJudgeCheck",
    "OpenAICompatibleProvider",
    "Provider",
    "is_floating_alias",
]
