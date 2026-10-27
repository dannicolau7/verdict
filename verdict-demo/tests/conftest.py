"""A scripted stand-in for the Anthropic client, so tests need no API key."""

from types import SimpleNamespace

import pytest


def tool_use(id_, name, **input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def text(t):
    return SimpleNamespace(type="text", text=t)


def thinking():
    return SimpleNamespace(type="thinking", thinking="", signature="sig")


def reply(*blocks, stop_reason=None):
    if stop_reason is None:
        stop_reason = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason,
                           usage=SimpleNamespace(input_tokens=1000, output_tokens=100))


class FakeClient:
    def __init__(self, *replies):
        self._replies = list(replies)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._replies:
            raise AssertionError("agent made more API calls than scripted")
        return self._replies.pop(0)


@pytest.fixture
def h():
    return SimpleNamespace(tool_use=tool_use, text=text, thinking=thinking, reply=reply,
                           FakeClient=FakeClient)
