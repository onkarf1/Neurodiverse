import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, cast

import httpx2
from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam

from app.ai.errors import AIProviderError, AIUnavailableError
from app.core.config import Settings

_LONE_SURROGATE = re.compile(r"[\ud800-\udfff]")


def _encodable(text: str) -> str:
    """Lone surrogates can't be sent as UTF-8; replace them rather than fail the request."""
    return _LONE_SURROGATE.sub("\ufffd", text)


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


class LLMProvider(Protocol):
    """Anything that turns chat messages into a reply. Services depend on this, not on a
    vendor, so the model or gateway can change without touching business rules."""

    model: str

    async def complete(self, messages: Sequence[Message]) -> str: ...


class OpenAICompatibleProvider:
    """Chat completions from an OpenAI-compatible gateway, such as ASU's."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._timeout_seconds = timeout_seconds
        # max_retries=0: no hidden retries; callers decide. The time limit is enforced around
        # the whole call in complete(), so the SDK's per-read timeouts aren't relied on.
        self._client = AsyncOpenAI(
            base_url=base_url, api_key=api_key, max_retries=0, http_client=http_client
        )

    async def complete(self, messages: Sequence[Message]) -> str:
        payload = cast(
            list[ChatCompletionMessageParam],
            [{"role": m.role, "content": _encodable(m.content)} for m in messages],
        )
        try:
            # Caps the whole call, including a reply that arrives one byte at a time.
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._client.chat.completions.create(
                    model=self.model, messages=payload, temperature=0
                )
        except (APIConnectionError, RateLimitError, InternalServerError, TimeoutError) as exc:
            # APIConnectionError also covers the SDK's own timeouts.
            raise AIUnavailableError(type(exc).__name__) from exc
        except APIStatusError as exc:
            raise AIProviderError(
                f"AI gateway rejected the request (HTTP {exc.status_code})"
            ) from exc
        if not response.choices:
            return ""
        return response.choices[0].message.content or ""

    async def close(self) -> None:
        await self._client.close()


def create_provider(settings: Settings) -> OpenAICompatibleProvider:
    if settings.asu_air_api_key is None:
        raise AIProviderError("ASU_AIR_API_KEY is not set, so the AI features are unavailable.")
    return OpenAICompatibleProvider(
        base_url=settings.ai_base_url,
        api_key=settings.asu_air_api_key.get_secret_value(),
        model=settings.ai_model,
        timeout_seconds=settings.ai_timeout_seconds,
    )
