from __future__ import annotations

import pytest
from pydantic import ValidationError

from reactor.api.routers.runs import (
    ForkRunRequest,
    ResumeRunRequest,
    fork_run_metadata,
    public_run_event_payload,
    structured_output_diagnostics_response,
)
from reactor.persistence.run_store import SessionRunRecord
from reactor.runs.service import resolved_structured_output


@pytest.mark.parametrize("approved", [1, 0, "true", "false"])
def test_resume_run_request_requires_strict_boolean_approval(approved: object) -> None:
    with pytest.raises(ValidationError):
        ResumeRunRequest.model_validate(
            {
                "approvalId": "approval_1",
                "approved": approved,
            }
        )


def test_structured_output_diagnostics_exposes_schema_less_citation_contract() -> None:
    manifest = {
        "sections": {
            "rag_context": {
                "metadata": {
                    "chunk_count": 1,
                    "citations": [{"citation_id": "rag:policy:0"}],
                }
            }
        }
    }

    diagnostics = structured_output_diagnostics_response(
        resolved_structured_output({"responseFormat": "JSON"}),
        context_manifest=manifest,
    )

    assert diagnostics.response_format_mode == "json_object"
    assert diagnostics.output_schema == {
        "type": "object",
        "properties": {
            "citations": {
                "type": "array",
                "items": {"type": "string", "enum": ["rag:policy:0"]},
                "minItems": 1,
                "uniqueItems": True,
            }
        },
        "required": ["citations"],
    }
    assert diagnostics.citation_boundary == {
        "status": "enforced",
        "source": "context_manifest",
        "citationIds": ["rag:policy:0"],
        "requiredMetadata": [
            "structured_output_allowed_citation_ids",
            "structured_output_citation_policy",
            "structured_output_citation_count",
        ],
    }


def test_structured_output_diagnostics_ignores_invalid_response_format() -> None:
    diagnostics = structured_output_diagnostics_response(
        resolved_structured_output({"responseFormat": "XML"}),
    )

    assert diagnostics.status == "ignored"
    assert diagnostics.format == "TEXT"
    assert diagnostics.strategy == "reactor_boundary"
    assert diagnostics.response_format_mode == "none"
    assert diagnostics.fallback_reason == "invalid_response_format"
    assert diagnostics.ignored_format == {
        "status": "ignored",
        "reason": "invalid_response_format",
        "source": "metadata.responseFormat",
        "value": "XML",
    }


def test_fork_run_metadata_strips_untrusted_checkpoint_keys() -> None:
    metadata = fork_run_metadata(
        SessionRunRecord(
            run_id="run_source",
            tenant_id="tenant_1",
            user_id="user_1",
            thread_id="thread_source",
            checkpoint_ns="reactor",
            status="completed",
            input_text="source prompt",
            response_text="source answer",
            created_at="2026-07-01T00:00:00Z",
            updated_at="2026-07-01T00:00:00Z",
            metadata={
                "checkpointId": "source_spoof",
                "checkpoint_id": "source_spoof_snake",
                "last_checkpoint_id": "checkpoint_latest",
                "personaId": "analyst",
            },
        ),
        ForkRunRequest(
            message="branch",
            threadId="thread_fork",
            checkpointNs="fork_ns",
            metadata={
                "checkpointId": "body_spoof",
                "checkpoint_id": "body_spoof_snake",
                "experiment": "safe-branch",
            },
        ),
        target_thread_id="thread_fork",
        target_checkpoint_ns="fork_ns",
    )

    assert metadata["forkedFromCheckpointId"] == "checkpoint_latest"
    assert metadata["personaId"] == "analyst"
    assert metadata["experiment"] == "safe-branch"
    assert "checkpointId" not in metadata
    assert "checkpoint_id" not in metadata


def test_public_run_event_payload_omits_raw_operator_reason() -> None:
    payload = public_run_event_payload(
        {
            "cancelled_by": "user_1",
            "reason": "private operator reason sk-test-secret",
            "raw_user_input": "private prompt",
        }
    )

    assert payload == {"cancelled_by": "user_1", "reasonPresent": True}
