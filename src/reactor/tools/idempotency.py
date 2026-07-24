from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def build_tool_idempotency_key(
    *,
    tenant_id: str,
    run_id: str,
    qualified_name: str,
    input_payload: Mapping[str, Any],
    trusted_user_groups: tuple[str, ...] = (),
    tool_call_id: str | None = None,
) -> str:
    identity: dict[str, object] = {
        "input": dict(input_payload),
        "trusted_user_groups": sorted(
            group.strip() for group in trusted_user_groups if group.strip()
        ),
    }
    if tool_call_id is not None:
        identity["tool_call_id"] = tool_call_id
    canonical_payload = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    return f"tool:{tenant_id}:{run_id}:{qualified_name}:{digest}"
