"""Holds the running message history for one chat session.

Messages are stored in the Anthropic Messages API shape (role + content
blocks) so they can be passed straight through to LLMProvider.send without
translation. Keeping this history across turns is what lets the host answer
follow-up questions like "when was he born?" after "who was Alan Turing?".
"""

from __future__ import annotations

from typing import Any

DEFAULT_MAX_MESSAGES = 60


class Conversation:
    def __init__(self, system_prompt: str, max_messages: int = DEFAULT_MAX_MESSAGES):
        self.system_prompt = system_prompt
        self.max_messages = max_messages
        self.messages: list[dict[str, Any]] = []

    def add_user_text(self, text: str) -> None:
        self.messages.append({"role": "user", "content": [{"type": "text", "text": text}]})

    def add_assistant_blocks(self, content: list[dict[str, Any]]) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def add_tool_results(self, results: list[dict[str, Any]]) -> None:
        """results: list of {"type": "tool_result", "tool_use_id": ..., "content": ..., "is_error": ...}."""
        self.messages.append({"role": "user", "content": results})

    def history(self) -> list[dict[str, Any]]:
        self._trim()
        return self.messages

    def _trim(self) -> None:
        """Drop the oldest turns once the history grows past max_messages,
        keeping the list length manageable for the model's context window."""
        if len(self.messages) > self.max_messages:
            overflow = len(self.messages) - self.max_messages
            self.messages = self.messages[overflow:]

    def clear(self) -> None:
        self.messages.clear()
