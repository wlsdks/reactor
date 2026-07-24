from __future__ import annotations

from urllib.parse import urlsplit


def require_absolute_http_url(value: str, *, field_name: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an absolute http or https URL")
    return candidate
