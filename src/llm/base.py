"""Provider-agnostic interface between the host's agent loop and an LLM API."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    """A normalized reply: a list of content blocks plus why the model stopped."""

    content: list[dict[str, Any]]
    stop_reason: str
    raw: dict[str, Any] = field(default_factory=dict)

    def text(self) -> str:
        return "\n".join(b.get("text", "") for b in self.content if b.get("type") == "text")

    def tool_uses(self) -> list[dict[str, Any]]:
        return [b for b in self.content if b.get("type") == "tool_use"]


class LLMProvider(ABC):
    @abstractmethod
    async def send(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str,
    ) -> LLMResponse:
        """Send one turn to the model and return its normalized reply."""

    @abstractmethod
    async def close(self) -> None:
        ...
