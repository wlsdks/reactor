from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def readiness_item_with_input_provenance(
    *,
    name: str,
    report: dict[str, Any],
    artifact: str,
    expected_commit: str,
    current_commit: str,
    max_input_age_seconds: int,
    generated_at: datetime,
    item_factory: Callable[..., dict[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    item = item_factory(name=name, report=report, artifact=artifact)
    artifact_path = Path(artifact)
    input_generated_at = generated_at
    if artifact_path.is_file():
        input_generated_at = datetime.fromtimestamp(artifact_path.stat().st_mtime, UTC)
    provenance: dict[str, object] = {
        "name": name,
        "artifact": artifact,
        "commitSha": current_commit,
        "generatedAt": input_generated_at.isoformat().replace("+00:00", "Z"),
        "inputHash": canonical_report_hash(report),
    }
    failure = input_provenance_failure(
        expected_commit=expected_commit,
        current_commit=current_commit,
        input_generated_at=input_generated_at,
        generated_at=generated_at,
        max_input_age_seconds=max_input_age_seconds,
    )
    if failure:
        item["ok"] = False
        item["status"] = "failed"
        item["failure"] = failure
        provenance["failure"] = failure
    item["inputProvenance"] = provenance
    return item, provenance


def input_provenance_failure(
    *,
    expected_commit: str,
    current_commit: str,
    input_generated_at: datetime,
    generated_at: datetime,
    max_input_age_seconds: int,
) -> str:
    if expected_commit and current_commit != expected_commit:
        return (
            f"readiness HEAD mismatch: expected {expected_commit}, "
            f"current {current_commit or 'unknown'}"
        )
    if input_generated_at > generated_at + timedelta(seconds=5):
        return "readiness input generatedAt is in the future"
    if (
        max_input_age_seconds > 0
        and (generated_at - input_generated_at).total_seconds() > max_input_age_seconds
    ):
        return "stale readiness input evidence"
    return ""


def canonical_report_hash(report: Mapping[str, object]) -> str:
    return canonical_json_hash(report)


def readiness_inputs_hash(inputs: Sequence[Mapping[str, object]]) -> str:
    return canonical_json_hash(inputs)


def canonical_json_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
