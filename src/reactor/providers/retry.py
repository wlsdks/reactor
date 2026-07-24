from __future__ import annotations

import anthropic
import openai
from google.genai.errors import ServerError as GoogleServerError

TRANSIENT_HTTP_STATUS_CODES = frozenset({408, 409, 425, 429})
TRANSIENT_PROVIDER_EXCEPTIONS = (
    TimeoutError,
    ConnectionError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
    anthropic.OverloadedError,
    anthropic.RetryableError,
    GoogleServerError,
)


def is_transient_retry_exception(exception: Exception) -> bool:
    if isinstance(exception, TRANSIENT_PROVIDER_EXCEPTIONS):
        return True
    status_code = getattr(exception, "status_code", None)
    return (
        isinstance(status_code, int)
        and not isinstance(status_code, bool)
        and (status_code in TRANSIENT_HTTP_STATUS_CODES or 500 <= status_code <= 599)
    )
