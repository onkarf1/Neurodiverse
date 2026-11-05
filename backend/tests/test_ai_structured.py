import logging
from collections.abc import Sequence

import pytest
from pydantic import BaseModel

from app.ai.errors import AIResponseError, AIUnavailableError
from app.ai.provider import Message
from app.ai.structured import complete_json

pytestmark = pytest.mark.anyio

PROMPT = [Message("system", "Return JSON."), Message("user", "private worksheet text")]


class Verdict(BaseModel):
    aligned: bool
    reason: str


class ScriptedProvider:
    model = "scripted"

    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.calls: list[list[Message]] = []

    async def complete(self, messages: Sequence[Message]) -> str:
        self.calls.append(list(messages))
        return self.replies.pop(0)


GOOD = '{"aligned": false, "reason": "steps are pre-ordered"}'


@pytest.mark.parametrize(
    "reply",
    [
        GOOD,
        f"```json\n{GOOD}\n```",
        f"```\n{GOOD}\n```",
        f"```JSON\n{GOOD}\n```",
        f"<think>planning...</think>\n{GOOD}",
        f"Example:\n```python\nprint('x')\n```\nAnswer:\n```json\n{GOOD}\n```",
    ],
    ids=[
        "plain",
        "json fence",
        "bare fence",
        "uppercase fence",
        "thinking block",
        "example block first",
    ],
)
async def test_valid_replies_are_parsed(reply: str) -> None:
    provider = ScriptedProvider([reply])

    verdict = await complete_json(provider, PROMPT, Verdict)

    assert verdict == Verdict(aligned=False, reason="steps are pre-ordered")
    assert len(provider.calls) == 1


BACKTICK_REASON = "Type ```print(x)``` in the box"
BACKTICK_JSON = f'{{"aligned": true, "reason": "{BACKTICK_REASON}"}}'


@pytest.mark.parametrize(
    "reply",
    [BACKTICK_JSON, f"```json\n{BACKTICK_JSON}\n```"],
    ids=["plain JSON", "fenced JSON"],
)
async def test_backticks_inside_values_are_kept(reply: str) -> None:
    # Worksheets can quote code or Markdown; that must not break parsing or cost a retry.
    provider = ScriptedProvider([reply])

    verdict = await complete_json(provider, PROMPT, Verdict)

    assert verdict.reason == BACKTICK_REASON
    assert len(provider.calls) == 1


@pytest.mark.parametrize(
    "bad_reply",
    ["not json", '{"aligned": "maybe"}', '{"reason": "missing field"}', ""],
    ids=["not json", "wrong type", "missing field", "empty"],
)
async def test_one_retry_with_a_correction_note_then_success(bad_reply: str) -> None:
    provider = ScriptedProvider([bad_reply, GOOD])

    verdict = await complete_json(provider, PROMPT, Verdict)

    assert verdict.aligned is False
    assert len(provider.calls) == 2
    retry = provider.calls[1]
    assert retry[: len(PROMPT)] == PROMPT
    assert retry[-2] == Message("assistant", bad_reply)
    assert retry[-1].role == "user"
    assert "JSON" in retry[-1].content


async def test_gives_up_after_exactly_one_retry() -> None:
    provider = ScriptedProvider(["nope", "still nope", GOOD])

    with pytest.raises(AIResponseError):
        await complete_json(provider, PROMPT, Verdict)

    assert len(provider.calls) == 2


async def test_model_text_is_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    # Replies can echo student text, so only counts and types may be logged.
    caplog.set_level(logging.DEBUG)
    provider = ScriptedProvider(['{"aligned": "private worksheet text"}', "private reply text"])

    with pytest.raises(AIResponseError):
        await complete_json(provider, PROMPT, Verdict)

    # Check every field of every record, not just the formatted text: extra fields count too.
    everything_logged = " ".join(f"{r.getMessage()} {vars(r)}" for r in caplog.records)
    assert "private" not in everything_logged
    assert any("expected format" in r.getMessage() for r in caplog.records)


async def test_unavailable_gateway_is_not_retried() -> None:
    # The one retry is for malformed replies only; retrying an outage would just double the
    # wait before the user sees "try again shortly".
    class DownProvider:
        model = "down"
        calls = 0

        async def complete(self, messages: Sequence[Message]) -> str:
            DownProvider.calls += 1
            raise AIUnavailableError("timeout")

    with pytest.raises(AIUnavailableError):
        await complete_json(DownProvider(), PROMPT, Verdict)

    assert DownProvider.calls == 1


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        (
            '{"aligned": true, "reason": "students type <think> first"}',
            "students type <think> first",
        ),
        ('{"aligned": true, "reason": "<think>x</think> y"}', "<think>x</think> y"),
        ('<think>hmm</think>\n{"aligned": true, "reason": "use <think>"}', "use <think>"),
        ('```json\n{"aligned": true, "reason": "<think>a</think> b"}\n```', "<think>a</think> b"),
        (
            '<think>never closed\n```json\n{"aligned": true, "reason": "</think>"}\n```',
            "</think>",
        ),
    ],
    ids=[
        "opening tag in a value",
        "whole block in a value",
        "reasoning first, tag in a value",
        "fenced, whole block in a value",
        "unclosed reasoning, then fenced answer",
    ],
)
async def test_reasoning_tags_inside_values_are_never_altered(reply: str, reason: str) -> None:
    # Only a reasoning block at the very start of a reply is removed; text inside values (for
    # example quoted evidence) must come back exactly as the model wrote it.
    provider = ScriptedProvider([reply])

    verdict = await complete_json(provider, PROMPT, Verdict)

    assert verdict.reason == reason
    assert len(provider.calls) == 1
