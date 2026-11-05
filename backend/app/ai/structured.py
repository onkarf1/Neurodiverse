import logging
import re
from collections.abc import Sequence

from pydantic import BaseModel, ValidationError

from app.ai.errors import AIResponseError
from app.ai.provider import LLMProvider, Message

logger = logging.getLogger(__name__)

# A closed reasoning block at the very start of a reply, where models put it. Never matched
# elsewhere, so values that mention <think> are left untouched. An unclosed block is kept, so a
# fenced answer after it can still be found.
_LEADING_THINKING = re.compile(r"\A<think>.*?</think>", re.DOTALL)
# Fences only count at the start of a line, so backticks inside a JSON string (for example a
# worksheet quoting code) never split a block. Any language tag, in any case.
_FENCED = re.compile(r"^```[^\r\n`]*\r?\n(.*?)^```[ \t]*\r?$", re.DOTALL | re.MULTILINE)
_CORRECTION = (
    "Your previous reply was not valid JSON in the required format. Reply again with only "
    "the JSON object, with no other text."
)


def _json_candidates(reply: str) -> list[str]:
    """In order: the reply without a leading reasoning block (often plain JSON), then each
    fenced block, so an example code block before the answer can't hide it."""
    answer = _LEADING_THINKING.sub("", reply.strip(), count=1).strip()
    blocks = [block.strip() for block in _FENCED.findall(answer)]
    return list(dict.fromkeys([answer, *blocks]))  # unique, order kept


def _parse[T: BaseModel](reply: str, schema: type[T]) -> T:
    """The first candidate that matches `schema`; otherwise the error for the whole reply."""
    first, *others = _json_candidates(reply)
    try:
        return schema.model_validate_json(first)
    except ValidationError as error:
        for candidate in others:
            try:
                return schema.model_validate_json(candidate)
            except ValidationError:
                continue
        raise error from None


async def complete_json[T: BaseModel](
    provider: LLMProvider, messages: Sequence[Message], schema: type[T]
) -> T:
    """Asks for JSON matching `schema`. One retry with a correction note, then gives up.

    Neither prompts nor replies are logged: they can contain student text.
    """
    attempt_messages = list(messages)
    for attempt in (1, 2):
        reply = await provider.complete(attempt_messages)
        try:
            return _parse(reply, schema)
        except ValidationError as exc:
            logger.warning(
                "AI reply did not match the expected format",
                extra={
                    "attempt": attempt,
                    "problems": exc.error_count(),
                    "schema": schema.__name__,
                },
            )
            attempt_messages = [
                *messages,
                Message("assistant", reply),
                Message("user", _CORRECTION),
            ]
    raise AIResponseError(f"AI reply did not match {schema.__name__} after a retry")
