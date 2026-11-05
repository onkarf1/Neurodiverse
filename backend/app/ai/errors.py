class AIError(Exception):
    """Base class for failures talking to the AI model."""


class AIUnavailableError(AIError):
    """Temporary: timeout, connection failure, rate limit, or a gateway server error.
    Safe to retry later."""


class AIProviderError(AIError):
    """The gateway rejected the request (bad key, bad request, unknown model) or the
    provider isn't configured. Not fixed by retrying; needs attention."""


class AIResponseError(AIError):
    """The model's reply didn't match the expected format, even after a retry."""
