from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from shlex import quote
from shlex import split as shell_split
from typing import Any, Protocol, cast
from uuid import UUID, uuid5

from langsmith import Client as LangSmithClient
from langsmith import schemas as langsmith_schemas
from langsmith.utils import LangSmithAuthError

from reactor.api.next_actions import (
    blocked_next_action_ids,
    next_action_states,
    ready_next_action_ids,
)
from reactor.context.diagnostics import ALLOWED_MEMORY_STATUS_COUNT_LABELS
from reactor.evals.langsmith_retry import retry_langsmith_write
from reactor.evals.models import AgentEvalCaseRecord
from reactor.evals.suite import (
    AgentEvalRegressionSuite,
    AgentEvalRunFixture,
    AgentTraceGrade,
    AgentTraceGrader,
    validate_eval_suite_records,
)
from reactor.feedback.workflow import feedback_review_closed
from reactor.kernel.citations import is_citation_safe_id
from reactor.memory.lifecycle_actions import MEMORY_LIFECYCLE_GATE_ACTION
from reactor.rag.ingestion_candidate_actions import (
    RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
    RAG_CANDIDATE_REVIEW_ACTION,
    rag_candidate_eval_apply_action_command,
    rag_candidate_feedback_bulk_review_action,
    rag_candidate_review_action,
)
from reactor.rag.ingestion_candidate_ids import (
    command_slug,
    is_command_slug,
    rag_candidate_case_id,
    rag_candidate_slug_from_case_id,
    rag_candidate_workflow_tag,
)
from reactor.release.env_values import is_placeholder_env_value
from reactor.release.readiness_actions import (
    HARDENING_SUITE_REPORT_FILE,
    LANGSMITH_SYNC_RECOMMENDED_ENV,
    LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
    LATEST_TAG_COMMAND,
    RECOMMENDED_TAG_SOURCE,
    RELEASE_EVIDENCE_FILE,
    RELEASE_READINESS_FILE,
    RELEASE_SMOKE_PLAN_FILE,
    RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
    RELEASE_SMOKE_PREFLIGHT_FILE,
    REPLATFORM_READINESS_FILE,
    langsmith_release_readiness_command,
    rag_ingestion_lifecycle_remediation_command,
    readiness_report_args_for_reports,
    release_readiness_command_for_reports,
)

LANGSMITH_EXAMPLE_NAMESPACE = UUID("7be9d406-66d5-4f1b-9697-392c9f387f77")
SECRET_SHAPED_VALUE_RE = re.compile(
    r"(?i)("
    r"\b(?:api[_-]?key|access[_-]?token|secret[_-]?key|password)\s*[:=]\s*\S{8,}"
    r"|"
    r"\b(?:sk|rk|pk|xox[baprs]|gh[pousr]|github_pat)_[A-Za-z0-9_\-]{8,}"
    r"|"
    r"\b(?:sk|rk|pk)-[A-Za-z0-9_\-]{12,}"
    r")"
)
LANGSMITH_EVAL_DATA_TYPE = "kv"
RAG_CANDIDATE_DATASET_NAME = "reactor-rag-ingestion-candidate"
RAG_CANDIDATE_SOURCE_SUITE = "evals/regression/rag-ingestion-candidate.json"
CITATION_MARKER_PLACEHOLDERS = frozenset({"[replace-with-source-id]"})
LANGSMITH_EVAL_EXAMPLE_CONTRACT: dict[str, object] = {
    "dataType": LANGSMITH_EVAL_DATA_TYPE,
    "requiredExampleFields": ["id", "inputs", "outputs", "metadata", "split"],
    "inputFields": ["user_input"],
    "metadataCaseIdField": "reactorCaseId",
    "metadataFields": [
        "reactorCaseId",
        "tenantId",
        "name",
        "tags",
        "agentType",
        "model",
        "sourceRunId",
        "enabled",
    ],
    "rawExampleValuesIncluded": False,
    "citationMarkerContract": {
        "ragExpectedAnswersRequireBracketedMarkers": True,
        "markerPattern": "[source-label]",
        "rawExampleValuesIncluded": False,
    },
    "secretScan": {
        "enabled": True,
        "scansKeys": True,
        "scansValues": True,
        "beforeCreateExamples": True,
    },
}
LANGSMITH_EVAL_SDK_CONTRACT: dict[str, object] = {
    "sdk": "langsmith",
    "client": "langsmith.Client",
    "datasetApi": "create_dataset",
    "exampleApi": "create_examples",
    "lookupApi": "has_dataset",
    "dataType": LANGSMITH_EVAL_DATA_TYPE,
    "maxConcurrency": 1,
    "deterministicExampleIds": True,
    "sourceControlledCases": True,
}
MEMORY_LIFECYCLE_ACTION = MEMORY_LIFECYCLE_GATE_ACTION


class LangSmithEvalDatasetSecretError(ValueError):
    """Raised when an eval case contains values that look like live secrets."""


class LangSmithDatasetClient(Protocol):
    def has_dataset(self, *, dataset_name: str) -> bool: ...

    def create_dataset(
        self,
        dataset_name: str,
        *,
        description: str | None = None,
        data_type: langsmith_schemas.DataType = langsmith_schemas.DataType.kv,
        metadata: dict[str, Any] | None = None,
    ) -> object: ...

    def create_examples(
        self,
        *,
        dataset_name: str,
        examples: list[dict[str, Any]],
        max_concurrency: int = 1,
    ) -> object: ...

    def list_examples(
        self,
        *,
        dataset_name: str,
        example_ids: Sequence[str],
        limit: int | None = None,
    ) -> Iterable[object]: ...

    def update_examples(
        self,
        *,
        dataset_name: str,
        updates: Sequence[dict[str, Any]],
    ) -> object: ...


@dataclass(frozen=True)
class LangSmithEvalDatasetExporter:
    client: LangSmithDatasetClient
    max_write_attempts: int = 3

    def export_cases(
        self,
        *,
        dataset_name: str,
        cases: Sequence[AgentEvalCaseRecord],
        description: str | None = None,
        source_suite: str | None = None,
    ) -> dict[str, object]:
        reject_duplicate_case_ids(cases)
        validate_langsmith_eval_cases(cases, dataset_name=dataset_name)
        examples = [langsmith_example_from_case(case, dataset_name=dataset_name) for case in cases]
        reject_secret_shaped_example_values(examples)
        dataset_metadata = langsmith_dataset_metadata(source_suite=source_suite)
        created = False
        if not self.client.has_dataset(dataset_name=dataset_name):
            self.client.create_dataset(
                dataset_name,
                description=description,
                data_type=langsmith_schemas.DataType.kv,
                metadata=dataset_metadata,
            )
            created = True
        existing_example_ids: set[str] = (
            set()
            if created or not examples
            else set(
                langsmith_existing_example_ids(
                    self.client.list_examples(
                        dataset_name=dataset_name,
                        example_ids=langsmith_example_ids(examples),
                        limit=len(examples),
                    )
                )
            )
        )
        new_examples = [
            example for example in examples if example["id"] not in existing_example_ids
        ]
        updated_examples = [
            example for example in examples if example["id"] in existing_example_ids
        ]
        if new_examples:
            retry_langsmith_write(
                lambda: self.client.create_examples(
                    dataset_name=dataset_name,
                    examples=new_examples,
                    max_concurrency=1,
                ),
                max_attempts=self.max_write_attempts,
            )
        if updated_examples:
            retry_langsmith_write(
                lambda: self.client.update_examples(
                    dataset_name=dataset_name,
                    updates=updated_examples,
                ),
                max_attempts=self.max_write_attempts,
            )
        return {
            "datasetName": dataset_name,
            "dataType": LANGSMITH_EVAL_DATA_TYPE,
            "datasetMetadata": dataset_metadata,
            "created": created,
            "examples": len(examples),
            "exampleIds": langsmith_example_ids(examples),
            "caseIds": [case.id for case in cases],
            "metadataCaseIds": langsmith_metadata_case_ids(examples),
            "sourceRunIds": langsmith_source_run_ids(examples),
            "caseSourceRunIds": langsmith_case_source_run_ids(examples),
            "splitCounts": langsmith_split_counts(examples),
            **optional_feedback_promotion_summary(examples),
            **optional_feedback_review_queue_summary(examples),
            "exampleContract": langsmith_eval_example_contract(),
            "sdkContract": langsmith_eval_sdk_contract(),
        }


def reject_duplicate_case_ids(cases: Sequence[AgentEvalCaseRecord]) -> None:
    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            raise ValueError(f"duplicate LangSmith eval case id: {case.id}")
        seen.add(case.id)


def langsmith_existing_example_ids(examples: Iterable[object]) -> tuple[str, ...]:
    existing_ids: list[str] = []
    for example in examples:
        example_id: object | None
        if isinstance(example, Mapping):
            example_id = cast(Mapping[object, object], example).get("id")
        else:
            example_id = cast(object, getattr(example, "id", None))
        if example_id is not None:
            existing_ids.append(str(example_id))
    return tuple(existing_ids)


def langsmith_example_from_case(
    case: AgentEvalCaseRecord,
    *,
    dataset_name: str,
) -> dict[str, Any]:
    return {
        "id": str(deterministic_langsmith_example_id(dataset_name=dataset_name, case_id=case.id)),
        "inputs": {
            "user_input": case.user_input,
        },
        "outputs": omit_none_values(
            {
                "expected_answer_contains": list(case.expected_answer_contains),
                "forbidden_answer_contains": list(case.forbidden_answer_contains),
                "expected_tool_names": list(case.expected_tool_names),
                "forbidden_tool_names": list(case.forbidden_tool_names),
                "expected_exposed_tool_names": list(case.expected_exposed_tool_names),
                "forbidden_exposed_tool_names": list(case.forbidden_exposed_tool_names),
                "max_tool_exposure_count": case.max_tool_exposure_count,
                "min_score": case.min_score,
            }
        ),
        "metadata": omit_none_values(
            {
                "reactorCaseId": case.id,
                "tenantId": case.tenant_id,
                "name": case.name,
                "tags": list(case.tags),
                "agentType": case.agent_type,
                "model": case.model,
                "sourceRunId": case.source_run_id,
                "enabled": case.enabled,
            }
        ),
        "split": "regression" if case.enabled else "disabled",
    }


def langsmith_example_ids(examples: Sequence[Mapping[str, Any]]) -> list[str]:
    return [example_id for example in examples if isinstance(example_id := example.get("id"), str)]


def langsmith_metadata_case_ids(examples: Sequence[Mapping[str, Any]]) -> list[str]:
    case_ids: list[str] = []
    for example in examples:
        metadata = example.get("metadata")
        if isinstance(metadata, Mapping):
            metadata_mapping = cast(Mapping[str, object], metadata)
            case_id = metadata_mapping.get("reactorCaseId")
            if isinstance(case_id, str):
                case_ids.append(case_id)
    return case_ids


def langsmith_source_run_ids(examples: Sequence[Mapping[str, Any]]) -> list[str]:
    source_run_ids: list[str] = []
    for example in examples:
        metadata = example.get("metadata")
        if isinstance(metadata, Mapping):
            metadata_mapping = cast(Mapping[str, object], metadata)
            source_run_id = metadata_mapping.get("sourceRunId")
            if isinstance(source_run_id, str) and source_run_id.strip():
                source_run_ids.append(source_run_id)
    return source_run_ids


def langsmith_case_source_run_ids(examples: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    case_source_run_ids: dict[str, str] = {}
    for example in examples:
        metadata = example.get("metadata")
        if isinstance(metadata, Mapping):
            metadata_mapping = cast(Mapping[str, object], metadata)
            case_id = metadata_mapping.get("reactorCaseId")
            source_run_id = metadata_mapping.get("sourceRunId")
            if (
                isinstance(case_id, str)
                and case_id.strip()
                and isinstance(source_run_id, str)
                and source_run_id.strip()
            ):
                case_source_run_ids[case_id] = source_run_id
    return case_source_run_ids


def langsmith_split_counts(examples: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for example in examples:
        split = example.get("split")
        if isinstance(split, str) and split.strip():
            counts[split] += 1
    return dict(sorted(counts.items()))


def string_list_value(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    sequence = cast(Sequence[object], value)
    return [item for item in sequence if isinstance(item, str)]


def deterministic_langsmith_example_id(*, dataset_name: str, case_id: str) -> UUID:
    return uuid5(LANGSMITH_EXAMPLE_NAMESPACE, f"{dataset_name}:{case_id}")


def omit_none_values(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def reject_secret_shaped_example_values(examples: Sequence[dict[str, Any]]) -> None:
    for example in examples:
        case_id = str(example.get("metadata", {}).get("reactorCaseId", "unknown"))
        secret_path = first_secret_shaped_value_path(example)
        if secret_path is not None:
            raise LangSmithEvalDatasetSecretError(
                f"LangSmith eval case {case_id} contains secret-shaped value at {secret_path}"
            )


def first_secret_shaped_value_path(value: Any, *, path: str = "$") -> str | None:
    if isinstance(value, str):
        if SECRET_SHAPED_VALUE_RE.search(value):
            return path
        return None
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        for key, item in mapping.items():
            key_path = f"{path}.{key}"
            if isinstance(key, str) and SECRET_SHAPED_VALUE_RE.search(key):
                return f"{path}.<secret-key>"
            found = first_secret_shaped_value_path(item, path=key_path)
            if found is not None:
                return found
        return None
    if isinstance(value, Sequence):
        sequence = cast(Sequence[object], value)
        for index, item in enumerate(sequence):
            found = first_secret_shaped_value_path(item, path=f"{path}[{index}]")
            if found is not None:
                return found
    return None


def validate_langsmith_eval_cases(
    cases: Sequence[AgentEvalCaseRecord],
    *,
    dataset_name: str,
) -> None:
    for case in cases:
        case.validate()
    validate_rag_candidate_langsmith_cases(cases, dataset_name=dataset_name)
    reject_secret_shaped_example_values(
        [langsmith_example_from_case(case, dataset_name=dataset_name) for case in cases]
    )


def validate_rag_candidate_langsmith_cases(
    cases: Sequence[AgentEvalCaseRecord],
    *,
    dataset_name: str,
) -> None:
    if dataset_name != RAG_CANDIDATE_DATASET_NAME:
        return
    for case in cases:
        if not case.id.startswith("case_rag_candidate_"):
            raise ValueError(
                "RAG ingestion candidate LangSmith sync requires case id case_rag_candidate_*"
            )
        if rag_candidate_slug_from_case_id(case.id) is None:
            raise ValueError("RAG ingestion candidate LangSmith sync requires slugged case id")


def langsmith_next_action_state_fields(
    actions: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    states = next_action_states(actions)
    if not states:
        return {}
    return {
        "readyNextActionIds": ready_next_action_ids(actions),
        "blockedNextActionIds": blocked_next_action_ids(actions),
        "nextActionStates": states,
    }


def build_langsmith_eval_sync_dry_run_report(
    *,
    suite_file: Path,
    dataset_name: str,
    report_file: Path | None = None,
    feedback_review_status: str = "",
    feedback_review_tags: Sequence[str] = (),
    feedback_review_note: str = "",
    required_readiness_reports: Sequence[str] = (),
    readiness_reports: Mapping[str, str] | None = None,
) -> dict[str, object]:
    suite = AgentEvalRegressionSuite.load(suite_file)
    return build_langsmith_eval_sync_dry_run_report_for_suite(
        suite=suite,
        suite_file=suite_file,
        dataset_name=dataset_name,
        report_file=report_file,
        feedback_review_status=feedback_review_status,
        feedback_review_tags=feedback_review_tags,
        feedback_review_note=feedback_review_note,
        required_readiness_reports=required_readiness_reports,
        readiness_reports=readiness_reports,
    )


def build_langsmith_eval_sync_dry_run_report_for_suite(
    *,
    suite: AgentEvalRegressionSuite,
    suite_file: Path,
    dataset_name: str,
    report_file: Path | None = None,
    feedback_review_status: str = "",
    feedback_review_tags: Sequence[str] = (),
    feedback_review_note: str = "",
    required_readiness_reports: Sequence[str] = (),
    readiness_reports: Mapping[str, str] | None = None,
) -> dict[str, object]:
    validate_eval_suite_records(cases=suite.cases, runs=suite.runs)
    cases = suite.enabled_cases
    validate_langsmith_eval_cases(cases, dataset_name=dataset_name)
    examples = [langsmith_example_from_case(case, dataset_name=dataset_name) for case in cases]
    result = {
        "datasetName": dataset_name,
        "dataType": LANGSMITH_EVAL_DATA_TYPE,
        "datasetMetadata": langsmith_dataset_metadata(source_suite=str(suite_file)),
        "created": False,
        "examples": len(cases),
        "exampleIds": langsmith_example_ids(examples),
        "caseIds": [case.id for case in cases],
        "metadataCaseIds": langsmith_metadata_case_ids(examples),
        "sourceRunIds": langsmith_source_run_ids(examples),
        "caseSourceRunIds": langsmith_case_source_run_ids(examples),
        "splitCounts": langsmith_split_counts(examples),
        **optional_suite_context_manifest_diagnostics(suite=suite, cases=cases),
        **optional_feedback_promotion_summary(examples),
        **optional_feedback_review_queue_summary(examples),
        **optional_feedback_promotion_coverage(suite=suite, cases=cases),
        "missingEnvAnyOf": langsmith_missing_env_groups(),
        "requiresHardeningReadiness": any(
            feedback_case_requires_citation_markers(case) for case in cases
        ),
        "exampleContract": langsmith_eval_example_contract(),
        "sdkContract": langsmith_eval_sdk_contract(),
    }
    apply_feedback_review_closure(
        result,
        status=feedback_review_status,
        tags=feedback_review_tags,
        note=feedback_review_note,
    )
    return langsmith_eval_sync_report(
        result,
        suite_file=suite_file,
        dataset_name=dataset_name,
        dry_run=True,
        report_file=report_file,
        trace_grading=trace_grading_summary(suite),
        required_readiness_reports=required_readiness_reports,
        readiness_reports=readiness_reports,
    )


def apply_feedback_review_closure(
    result: dict[str, object],
    *,
    status: str,
    tags: Sequence[str],
    note: str,
) -> None:
    clean_status = status.strip()
    clean_tags = [tag.strip() for tag in tags if tag.strip()]
    clean_note = note.strip()
    if not clean_status and not clean_tags and not clean_note:
        return
    feedback_promotion = result.get("feedbackPromotion")
    if isinstance(feedback_promotion, Mapping):
        updated = dict(cast(Mapping[str, object], feedback_promotion))
        if clean_status:
            updated["reviewStatus"] = clean_status
        if clean_tags:
            updated["reviewTags"] = clean_tags
        if clean_note:
            updated["reviewNote"] = clean_note
        result["feedbackPromotion"] = updated
    feedback_review_queue = result.get("feedbackReviewQueue")
    if isinstance(feedback_review_queue, Mapping):
        updated = dict(cast(Mapping[str, object], feedback_review_queue))
        if clean_status:
            updated["reviewStatus"] = clean_status
        if clean_tags:
            updated["reviewTags"] = clean_tags
        if clean_note:
            updated["reviewNote"] = clean_note
        result["feedbackReviewQueue"] = updated


def langsmith_eval_sync_auth_failure_report(
    *,
    suite: AgentEvalRegressionSuite,
    suite_file: Path,
    dataset_name: str,
    report_file: Path | None,
    required_readiness_reports: Sequence[str] = (),
    readiness_reports: Mapping[str, str] | None = None,
) -> dict[str, object]:
    cases = suite.enabled_cases
    examples = [langsmith_example_from_case(case, dataset_name=dataset_name) for case in cases]
    source_suite = str(suite_file)
    command_parts = [
        "uv run reactor-langsmith-eval-sync",
        f"--suite-file {quote(source_suite)}",
        f"--dataset-name {quote(dataset_name)}",
    ]
    if report_file is not None:
        command_parts.append(f"--report-file {quote(str(report_file))}")
    explicit_required_readiness_reports = normalized_readiness_report_names(
        required_readiness_reports
    )
    explicit_readiness_reports = dict(readiness_reports or {})
    if explicit_required_readiness_reports:
        report_files = readiness_reports_for_required_reports(
            required_reports=explicit_required_readiness_reports,
            explicit_reports=explicit_readiness_reports,
            report_file=report_file,
        )
    elif report_file is not None:
        report_files = {"langsmith_eval_sync": str(report_file)}
    else:
        report_files = {}
    required_reports = (
        explicit_required_readiness_reports
        if explicit_required_readiness_reports
        else (["langsmith_eval_sync"] if report_file is not None else [])
    )
    for required_report in explicit_required_readiness_reports:
        command_parts.append(f"--required-readiness-report {quote(required_report)}")
    for report_name in explicit_required_readiness_reports:
        report_path = report_files.get(report_name)
        if report_path:
            command_parts.append(f"--readiness-report {quote(report_name)}={quote(report_path)}")
    command = " ".join(command_parts)
    preflight_command = f"{command} --preflight-only --output table"
    handoff_metadata = langsmith_suite_handoff_metadata(examples)
    readiness_report_arg = (
        readiness_report_args_for_reports(
            required_reports=required_reports,
            report_files=report_files,
        )
        if required_reports and report_files
        else ""
    )
    release_readiness_command = (
        release_readiness_command_for_reports(
            required_reports=required_reports,
            report_files=report_files,
        )
        if readiness_report_arg
        else ""
    )
    readiness_handoff = (
        {
            "readinessReportArg": readiness_report_arg,
            "requiredReadinessReports": required_reports,
            "readinessReports": report_files,
            "releaseReadinessFile": RELEASE_READINESS_FILE,
            "releaseReadinessCommand": release_readiness_command,
            "preflightFile": RELEASE_SMOKE_PREFLIGHT_FILE,
            "preflightEnvTemplate": RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
        }
        if readiness_report_arg and release_readiness_command
        else {}
    )
    next_actions = [
        {
            "id": "rerun-preflight-langsmith",
            "label": "Rerun the LangSmith eval sync preflight after setting credentials",
            "command": preflight_command,
            "envFileCommand": langsmith_env_file_command(preflight_command),
            "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
            "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
            **readiness_handoff,
            **handoff_metadata,
        },
        {
            "id": "sync-langsmith",
            "label": "Rerun the LangSmith eval sync after credentials are fixed",
            "command": command,
            "envFileCommand": langsmith_env_file_command(command),
            "dependsOnActionIds": ["rerun-preflight-langsmith"],
            "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
            "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
            **readiness_handoff,
            **handoff_metadata,
        },
    ]
    release_gate = {
        "status": "blocked",
        "blocksReleaseReadiness": True,
        "reason": "langsmith_auth_failed",
        "requiredReport": "langsmith_eval_sync",
        "remediation": [
            "set_langsmith_api_key",
            "rerun_reactor_langsmith_eval_sync",
            "include_passed_langsmith_eval_sync_report_in_release_readiness",
        ],
        "remediationCommand": command,
    }
    evidence = {
        "artifact": str(report_file) if report_file is not None else "stdout",
        "command": command,
        "owner": "reactor.evals",
        "mode": "langsmith_dataset_sync",
        "datasetName": dataset_name,
        "sourceSuite": source_suite,
        "remediationCommand": command,
        "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
        "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
        **readiness_handoff,
        "nextActions": next_actions,
        **langsmith_next_action_state_fields(next_actions),
    }
    return {
        "ok": False,
        "status": "blocked",
        "scope": "langsmith_eval_dataset_sync",
        "failure": "langsmith_auth_failed",
        "datasetName": dataset_name,
        "sourceSuite": source_suite,
        "dryRun": False,
        "examples": len(cases),
        "caseIds": [case.id for case in cases],
        "exampleIds": langsmith_example_ids(examples),
        "metadataCaseIds": langsmith_metadata_case_ids(examples),
        "sourceRunIds": langsmith_source_run_ids(examples),
        "caseSourceRunIds": langsmith_case_source_run_ids(examples),
        "splitCounts": langsmith_split_counts(examples),
        "remediationCommand": command,
        "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
        "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
        **readiness_handoff,
        "nextActions": next_actions,
        **langsmith_next_action_state_fields(next_actions),
        "releaseGate": release_gate,
        "evidence": evidence,
        "source": {
            "suiteFile": source_suite,
            "caseIds": [case.id for case in cases],
        },
    }


def langsmith_env_file_unreadable_report(
    *,
    suite: AgentEvalRegressionSuite,
    suite_file: Path,
    dataset_name: str,
    report_file: Path | None,
    env_file: str,
) -> dict[str, object]:
    cases = suite.enabled_cases
    examples = [langsmith_example_from_case(case, dataset_name=dataset_name) for case in cases]
    command_parts = [
        "uv run reactor-langsmith-eval-sync",
        f"--suite-file {quote(str(suite_file))}",
        f"--dataset-name {quote(dataset_name)}",
    ]
    if report_file is not None:
        command_parts.append(f"--report-file {quote(str(report_file))}")
    preflight_command = f"{' '.join(command_parts)} --preflight-only --output table"
    remediation_command = langsmith_env_file_command(preflight_command)
    return {
        "ok": False,
        "status": "blocked",
        "scope": "langsmith_eval_dataset_sync",
        "failure": "langsmith_env_file_unreadable",
        "datasetName": dataset_name,
        "sourceSuite": str(suite_file),
        **({"reportFile": str(report_file)} if report_file is not None else {}),
        "envFile": env_file,
        "dryRun": False,
        "examples": len(cases),
        "caseIds": [case.id for case in cases],
        "exampleIds": langsmith_example_ids(examples),
        "metadataCaseIds": langsmith_metadata_case_ids(examples),
        "sourceRunIds": langsmith_source_run_ids(examples),
        "caseSourceRunIds": langsmith_case_source_run_ids(examples),
        "splitCounts": langsmith_split_counts(examples),
        "remediationCommand": remediation_command,
        "preflightEnvTemplate": RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
        "releaseGateReason": "langsmith_env_file_unreadable",
        "releaseGate": {
            "status": "blocked",
            "blocksReleaseReadiness": True,
            "reason": "langsmith_env_file_unreadable",
            "requiredReport": "langsmith_eval_sync",
            "remediation": [
                "fix_langsmith_env_file_path",
                "rerun_reactor_langsmith_eval_sync_preflight",
            ],
            "remediationCommand": remediation_command,
        },
        "evidence": {
            "artifact": str(report_file) if report_file is not None else "stdout",
            "owner": "reactor.evals",
            "mode": "langsmith_dataset_sync",
            "datasetName": dataset_name,
            "sourceSuite": str(suite_file),
            "envFile": env_file,
            "remediationCommand": remediation_command,
            "preflightEnvTemplate": RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
        },
    }


def langsmith_eval_sync_preflight_report(
    *,
    suite: AgentEvalRegressionSuite,
    suite_file: Path,
    dataset_name: str,
    report_file: Path | None,
    environ: Mapping[str, str] | None = None,
    feedback_review_status: str = "",
    feedback_review_tags: Sequence[str] = (),
    feedback_review_note: str = "",
    required_readiness_reports: Sequence[str] = (),
    readiness_reports: Mapping[str, str] | None = None,
) -> dict[str, object]:
    env = os.environ if environ is None else environ
    source_suite = str(suite_file)
    cases = suite.enabled_cases
    examples = [langsmith_example_from_case(case, dataset_name=dataset_name) for case in cases]
    missing_groups = langsmith_missing_env_groups(env)
    placeholder_env = langsmith_placeholder_env_names(env)
    ok = not missing_groups
    status = "ready" if ok else "blocked"
    failure = None if ok else "missing_langsmith_credentials"
    live_sync_command_parts = [
        "uv run reactor-langsmith-eval-sync",
        f"--suite-file {quote(source_suite)}",
        f"--dataset-name {quote(dataset_name)}",
    ]
    explicit_required_readiness_reports = normalized_readiness_report_names(
        required_readiness_reports
    )
    explicit_readiness_reports = dict(readiness_reports or {})
    if explicit_required_readiness_reports:
        report_files = readiness_reports_for_required_reports(
            required_reports=explicit_required_readiness_reports,
            explicit_reports=explicit_readiness_reports,
            report_file=report_file,
        )
    elif report_file is not None:
        report_files = {"langsmith_eval_sync": str(report_file)}
    else:
        report_files = {}
    required_reports = (
        explicit_required_readiness_reports
        if explicit_required_readiness_reports
        else (["langsmith_eval_sync"] if report_file is not None else [])
    )
    live_report_file = (
        report_files.get("langsmith_eval_sync")
        if explicit_required_readiness_reports
        else str(report_file)
        if report_file is not None
        else ""
    )
    if live_report_file:
        live_sync_command_parts.append(f"--report-file {quote(live_report_file)}")
    review_closure_args = feedback_promotion_review_closure_command_args(
        {
            "reviewStatus": feedback_review_status,
            "reviewTags": list(feedback_review_tags),
            "reviewNote": feedback_review_note,
        }
    )
    live_sync_command_parts.extend(review_closure_args)
    for required_report in explicit_required_readiness_reports:
        live_sync_command_parts.append(f"--required-readiness-report {quote(required_report)}")
    for report_name in explicit_required_readiness_reports:
        report_path = report_files.get(report_name)
        if report_path:
            live_sync_command_parts.append(
                f"--readiness-report {quote(report_name)}={quote(report_path)}"
            )
    live_sync_command = " ".join(live_sync_command_parts)
    preflight_base_command = live_sync_command
    if report_file is not None and live_report_file and live_report_file != str(report_file):
        preflight_base_command = preflight_base_command.replace(
            f"--report-file {quote(live_report_file)}",
            f"--report-file {quote(str(report_file))}",
            1,
        )
    preflight_command = f"{preflight_base_command} --preflight-only --output table"
    readiness_report_arg = (
        readiness_report_args_for_reports(
            required_reports=required_reports,
            report_files=report_files,
        )
        if required_reports and report_files
        else ""
    )
    release_readiness_command = (
        release_readiness_command_for_reports(
            required_reports=required_reports,
            report_files=report_files,
        )
        if readiness_report_arg
        else ""
    )
    readiness_handoff = (
        {
            "readinessReportArg": readiness_report_arg,
            "requiredReadinessReports": required_reports,
            "readinessReports": report_files,
            "releaseReadinessFile": RELEASE_READINESS_FILE,
            "releaseReadinessCommand": release_readiness_command,
            "preflightFile": RELEASE_SMOKE_PREFLIGHT_FILE,
            "preflightEnvTemplate": RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
        }
        if readiness_report_arg and release_readiness_command
        else {}
    )
    next_actions = []
    handoff_metadata = langsmith_suite_handoff_metadata(examples)
    review_note_handoff = (
        {"requiredReviewNote": feedback_review_note.strip()} if feedback_review_note.strip() else {}
    )
    if missing_groups:
        next_actions = [
            {
                "id": "rerun-preflight-langsmith",
                "label": "Rerun the LangSmith eval sync preflight after setting credentials",
                "command": preflight_command,
                "envFileCommand": langsmith_env_file_command(preflight_command),
                **({"reportFile": str(report_file)} if report_file is not None else {}),
                "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
                "missingEnvAnyOf": missing_groups,
                "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
                **readiness_handoff,
                **handoff_metadata,
                **review_note_handoff,
            },
            {
                "id": "sync-langsmith",
                "label": "Run the LangSmith eval sync after preflight passes",
                "command": live_sync_command,
                "envFileCommand": langsmith_env_file_command(live_sync_command),
                **({"reportFile": live_report_file} if live_report_file else {}),
                "dependsOnActionIds": ["rerun-preflight-langsmith"],
                "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
                "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
                **readiness_handoff,
                **handoff_metadata,
                **review_note_handoff,
            },
        ]
    elif live_sync_command.strip():
        next_actions = [
            {
                "id": "sync-langsmith",
                "label": "Run the LangSmith eval sync after preflight passes",
                "command": live_sync_command,
                "envFileCommand": langsmith_env_file_command(live_sync_command),
                **({"reportFile": live_report_file} if live_report_file else {}),
                "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
                "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
                **readiness_handoff,
                **handoff_metadata,
                **review_note_handoff,
            },
        ]
    release_gate = {
        "status": "ready" if ok else "blocked",
        "blocksReleaseReadiness": not ok,
        "reason": None if ok else "missing_langsmith_credentials",
        "requiredReport": "langsmith_eval_sync",
        "remediation": []
        if ok
        else [
            "set_langsmith_api_key",
            "rerun_reactor_langsmith_eval_sync_preflight",
            "rerun_reactor_langsmith_eval_sync",
        ],
    }
    next_action_state_fields = langsmith_next_action_state_fields(next_actions)
    return {
        "ok": ok,
        "status": status,
        "scope": "langsmith_eval_dataset_sync_preflight",
        **({"failure": failure} if failure else {}),
        "datasetName": dataset_name,
        "sourceSuite": source_suite,
        **({"reportFile": str(report_file)} if report_file is not None else {}),
        "dryRun": False,
        "examples": len(cases),
        "caseIds": [case.id for case in cases],
        "exampleIds": langsmith_example_ids(examples),
        "metadataCaseIds": langsmith_metadata_case_ids(examples),
        "sourceRunIds": langsmith_source_run_ids(examples),
        "caseSourceRunIds": langsmith_case_source_run_ids(examples),
        "splitCounts": langsmith_split_counts(examples),
        "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
        "missingEnvAnyOf": missing_groups,
        **({"placeholderEnv": placeholder_env} if placeholder_env else {}),
        "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
        "liveSyncCommand": live_sync_command,
        "syncCommand": live_sync_command,
        **readiness_handoff,
        **({"nextActions": next_actions, **next_action_state_fields} if next_actions else {}),
        "releaseGateReason": release_gate["reason"],
        "releaseGate": release_gate,
        "evidence": {
            "artifact": str(report_file) if report_file is not None else "stdout",
            "owner": "reactor.evals",
            "mode": "langsmith_dataset_sync_preflight",
            "datasetName": dataset_name,
            "sourceSuite": source_suite,
            "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
            "missingEnvAnyOf": missing_groups,
            **({"placeholderEnv": placeholder_env} if placeholder_env else {}),
            "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
            "liveSyncCommand": live_sync_command,
            "syncCommand": live_sync_command,
            **readiness_handoff,
            **({"nextActions": next_actions, **next_action_state_fields} if next_actions else {}),
        },
    }


def langsmith_missing_env_groups(environ: Mapping[str, str] | None = None) -> list[str]:
    env = os.environ if environ is None else environ
    return [
        "|".join(group)
        for group in LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF
        if not any(langsmith_env_value(env, name) for name in group)
    ]


def langsmith_env_value(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "").strip()
    return "" if is_placeholder_env_value(value) else value


def langsmith_placeholder_env_names(environ: Mapping[str, str]) -> list[str]:
    names = {
        name
        for group in LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF
        for name in group
        if is_placeholder_env_value(environ.get(name, ""))
    }
    return sorted(names)


def langsmith_env_file_command(command: str) -> str:
    env_file_arg = f"--env-file {quote(RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE)}"
    if env_file_arg in command:
        return command
    return f"{command} {env_file_arg}"


def read_langsmith_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        values[key.strip()] = value.strip()
    return values


def merged_langsmith_environ(env_file_values: Sequence[str]) -> dict[str, str]:
    merged = dict(os.environ)
    merged.update(env_file_values_from_paths(env_file_values))
    return merged


@contextmanager
def langsmith_env_files(env_file_values: Sequence[str]):
    values = env_file_values_from_paths(env_file_values) if env_file_values else {}
    if not values:
        yield
        return
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, prior in previous.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior


def env_file_values_from_paths(env_file_values: Sequence[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for value in env_file_values:
        values.update(read_langsmith_env_file(Path(value)))
    return values


def langsmith_suite_handoff_metadata(examples: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    return {
        "caseIds": langsmith_metadata_case_ids(examples),
        "sourceRunIds": langsmith_source_run_ids(examples),
        "caseSourceRunIds": langsmith_case_source_run_ids(examples),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync Reactor source-controlled eval cases to a LangSmith dataset."
    )
    parser.add_argument(
        "--suite-file",
        required=True,
        help="Agent eval regression suite JSON file.",
    )
    parser.add_argument("--dataset-name", required=True, help="Target LangSmith dataset name.")
    parser.add_argument("--description", default=None, help="Dataset description when created.")
    parser.add_argument("--report-file", default=None, help="Optional JSON report output path.")
    parser.add_argument(
        "--env-file",
        action="append",
        dest="env_files",
        default=None,
        help="Optional .env file values used for LangSmith preflight and sync.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report without network IO.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Check LangSmith sync environment readiness without network IO.",
    )
    parser.add_argument(
        "--feedback-review-status",
        default="",
        help="Optional review status to preserve in feedback promotion evidence.",
    )
    parser.add_argument(
        "--feedback-review-tag",
        action="append",
        dest="feedback_review_tags",
        default=None,
        help="Optional review tag to preserve in feedback promotion evidence; may be repeated.",
    )
    parser.add_argument(
        "--feedback-review-note",
        default="",
        help="Optional review note to preserve in feedback promotion evidence.",
    )
    parser.add_argument(
        "--required-readiness-report",
        action="append",
        dest="required_readiness_reports",
        default=None,
        help="Required release readiness report name; may be repeated.",
    )
    parser.add_argument(
        "--readiness-report",
        action="append",
        dest="readiness_report_specs",
        default=None,
        help="Release readiness report mapping as name=path; may be repeated.",
    )
    parser.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format for stdout.",
    )
    args = parser.parse_args(argv)

    suite_file = Path(args.suite_file)
    suite = AgentEvalRegressionSuite.load(suite_file)
    cases = suite.enabled_cases
    validate_langsmith_eval_cases(cases, dataset_name=args.dataset_name)
    required_readiness_reports = normalized_readiness_report_names(
        args.required_readiness_reports or ()
    )
    readiness_reports = parse_readiness_report_specs(args.readiness_report_specs or ())
    env_files = tuple(args.env_files or ())
    env_file_environ: dict[str, str] | None = None
    report: dict[str, object] | None
    try:
        env_file_environ = merged_langsmith_environ(env_files) if env_files else None
    except OSError:
        report = langsmith_env_file_unreadable_report(
            suite=suite,
            suite_file=suite_file,
            dataset_name=args.dataset_name,
            report_file=Path(args.report_file) if args.report_file else None,
            env_file=next((value.strip() for value in env_files if value.strip()), ""),
        )
    else:
        report = None
    if report is None and args.preflight_only:
        report = langsmith_eval_sync_preflight_report(
            suite=suite,
            suite_file=suite_file,
            dataset_name=args.dataset_name,
            report_file=Path(args.report_file) if args.report_file else None,
            environ=env_file_environ,
            feedback_review_status=args.feedback_review_status,
            feedback_review_tags=tuple(args.feedback_review_tags or ()),
            feedback_review_note=args.feedback_review_note,
            required_readiness_reports=required_readiness_reports,
            readiness_reports=readiness_reports,
        )
    elif report is None and args.dry_run:
        report = build_langsmith_eval_sync_dry_run_report(
            suite_file=suite_file,
            dataset_name=args.dataset_name,
            report_file=Path(args.report_file) if args.report_file else None,
            feedback_review_status=args.feedback_review_status,
            feedback_review_tags=tuple(args.feedback_review_tags or ()),
            feedback_review_note=args.feedback_review_note,
            required_readiness_reports=required_readiness_reports,
            readiness_reports=readiness_reports,
        )
    elif report is None:
        if env_file_environ is not None and langsmith_missing_env_groups(env_file_environ):
            report = langsmith_eval_sync_preflight_report(
                suite=suite,
                suite_file=suite_file,
                dataset_name=args.dataset_name,
                report_file=Path(args.report_file) if args.report_file else None,
                environ=env_file_environ,
                feedback_review_status=args.feedback_review_status,
                feedback_review_tags=tuple(args.feedback_review_tags or ()),
                feedback_review_note=args.feedback_review_note,
                required_readiness_reports=required_readiness_reports,
                readiness_reports=readiness_reports,
            )
        else:
            try:
                with langsmith_env_files(env_files):
                    result = LangSmithEvalDatasetExporter(LangSmithClient()).export_cases(
                        dataset_name=args.dataset_name,
                        cases=cases,
                        description=args.description,
                        source_suite=str(suite_file),
                    )
                result.update(optional_suite_context_manifest_diagnostics(suite=suite, cases=cases))
                result.update(optional_feedback_promotion_coverage(suite=suite, cases=cases))
                apply_feedback_review_closure(
                    result,
                    status=args.feedback_review_status,
                    tags=tuple(args.feedback_review_tags or ()),
                    note=args.feedback_review_note,
                )
                report = langsmith_eval_sync_report(
                    result,
                    suite_file=suite_file,
                    dataset_name=args.dataset_name,
                    dry_run=False,
                    report_file=Path(args.report_file) if args.report_file else None,
                    trace_grading=trace_grading_summary(suite),
                    required_readiness_reports=required_readiness_reports,
                    readiness_reports=readiness_reports,
                )
            except LangSmithAuthError:
                report = langsmith_eval_sync_auth_failure_report(
                    suite=suite,
                    suite_file=suite_file,
                    dataset_name=args.dataset_name,
                    report_file=Path(args.report_file) if args.report_file else None,
                    required_readiness_reports=required_readiness_reports,
                    readiness_reports=readiness_reports,
                )
    encoded = json.dumps(report, indent=2, sort_keys=True)
    if args.report_file:
        report_path = Path(args.report_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(encoded + "\n", encoding="utf-8")
        if args.output == "table":
            print(format_langsmith_eval_sync_table(report), end="")
        else:
            print(encoded)
    else:
        if args.output == "table":
            print(format_langsmith_eval_sync_table(report), end="")
        else:
            print(encoded)
    return (
        1
        if report.get("failure")
        in {
            "langsmith_auth_failed",
            "langsmith_env_file_unreadable",
            "missing_langsmith_credentials",
        }
        else 0
    )


def format_langsmith_eval_sync_table(report: Mapping[str, object]) -> str:
    feedback_promotion = feedback_promotion_summary_value(report.get("feedbackPromotion"))
    feedback_review_queue = feedback_review_queue_summary_value(report.get("feedbackReviewQueue"))
    feedback_review_actions = (
        langsmith_feedback_review_actions(feedback_promotion) if feedback_promotion else []
    )
    trace_grading = langsmith_trace_grading_value(report)
    grounding_summary = trace_grounding_citation_summary_value(trace_grading)
    deterministic_summary = trace_deterministic_eval_summary_value(trace_grading)
    context_diagnostics = context_manifest_diagnostics_mapping(report)
    product_boundary = langsmith_product_boundary_summary_parts(
        report.get("productCapabilityBoundary")
    )
    has_readiness_command = bool(report.get("readinessCommand"))
    rows = [
        ("status", report.get("status")),
        ("datasetName", report.get("datasetName")),
        ("dryRun", bool_text(report.get("dryRun"))),
        ("examples", report.get("examples")),
        ("caseIds", len(string_list_value(report.get("caseIds", ())))),
        (
            "feedbackCases",
            len(string_list_value(feedback_promotion.get("caseIds", ())))
            if feedback_promotion
            else None,
        ),
        (
            "feedbackIds",
            len(string_list_value(feedback_promotion.get("feedbackIds", ())))
            if feedback_promotion
            else None,
        ),
        (
            "feedbackReviewIds",
            ",".join(string_list_value(feedback_promotion.get("feedbackReviewIds", ())))
            if feedback_promotion
            else None,
        ),
        (
            "feedbackCaseIds",
            ",".join(string_list_value(feedback_promotion.get("caseIds", ())))
            if feedback_promotion
            else None,
        ),
        (
            "feedbackRatings",
            split_counts_summary(feedback_promotion.get("feedbackRatingCounts"))
            if feedback_promotion
            else None,
        ),
        (
            "feedbackSources",
            split_counts_summary(feedback_promotion.get("feedbackSourceCounts"))
            if feedback_promotion
            else None,
        ),
        (
            "feedbackWorkflows",
            split_counts_summary(feedback_promotion.get("workflowTagCounts"))
            if feedback_promotion
            else None,
        ),
        (
            "feedbackExpectedCitations",
            split_counts_summary(feedback_promotion.get("expectedCitationCounts"))
            if feedback_promotion
            else None,
        ),
        (
            "feedbackReviewAction",
            feedback_review_actions[0] if len(feedback_review_actions) == 1 else None,
        ),
        (
            "feedbackReviewActions",
            "; ".join(feedback_review_actions) if len(feedback_review_actions) > 1 else None,
        ),
        (
            "feedbackBulkReviewAction",
            feedback_promotion.get("bulkReviewAction") if feedback_promotion else None,
        ),
        (
            "feedbackReleaseReadinessCommand",
            feedback_promotion.get("releaseReadinessCommand") if feedback_promotion else None,
        ),
        (
            "feedbackQueueCases",
            len(string_list_value(feedback_review_queue.get("caseIds", ())))
            if feedback_review_queue
            else None,
        ),
        (
            "feedbackQueueCandidateTag",
            feedback_review_queue.get("candidateTag") if feedback_review_queue else None,
        ),
        (
            "feedbackQueueRatings",
            split_counts_summary(feedback_review_queue.get("feedbackRatingCounts"))
            if feedback_review_queue
            else None,
        ),
        (
            "feedbackQueueSources",
            split_counts_summary(feedback_review_queue.get("feedbackSourceCounts"))
            if feedback_review_queue
            else None,
        ),
        (
            "feedbackQueueWorkflows",
            split_counts_summary(feedback_review_queue.get("workflowTagCounts"))
            if feedback_review_queue
            else None,
        ),
        (
            "feedbackQueueExpectedCitations",
            split_counts_summary(feedback_review_queue.get("expectedCitationCounts"))
            if feedback_review_queue
            else None,
        ),
        (
            "feedbackQueueReviewAction",
            feedback_review_queue.get("reviewAction") if feedback_review_queue else None,
        ),
        (
            "feedbackQueueExportAction",
            feedback_review_queue.get("exportAction") if feedback_review_queue else None,
        ),
        (
            "feedbackQueueCandidateAction",
            feedback_review_queue.get("candidateReviewAction") if feedback_review_queue else None,
        ),
        (
            "feedbackQueueMemoryAction",
            feedback_review_queue.get("memoryLifecycleAction") if feedback_review_queue else None,
        ),
        ("groundingCitationCases", grounding_summary.get("groundingCitationCases")),
        ("groundingCitedChunks", grounding_summary.get("groundingCitedChunks")),
        ("groundingUncitedChunks", grounding_summary.get("groundingUncitedChunks")),
        (
            "groundingCitationDocuments",
            ",".join(string_list_value(grounding_summary.get("groundingCitationDocuments", ()))),
        ),
        (
            "citationWorkflowEvalCaseIds",
            ",".join(string_list_value(context_diagnostics.get("citationWorkflowEvalCaseIds", ()))),
        ),
        (
            "citationWorkflowTags",
            ",".join(string_list_value(context_diagnostics.get("citationWorkflowTags", ()))),
        ),
        (
            "deterministicEvalFailedCases",
            deterministic_summary.get("deterministicEvalFailedCases"),
        ),
        (
            "deterministicEvalMissingExpected",
            ",".join(
                string_list_value(deterministic_summary.get("deterministicEvalMissingExpected", ()))
            ),
        ),
        ("sourceRunIds", len(string_list_value(report.get("sourceRunIds", ())))),
        (
            "caseSourceRunMappings",
            len(string_mapping_value(report.get("caseSourceRunIds", {}))),
        ),
        ("splitCounts", split_counts_summary(report.get("splitCounts"))),
        ("sourceSuite", langsmith_source_suite_value(report)),
        ("examplePayloads", langsmith_example_payload_summary(report.get("exampleContract"))),
        (
            "citationMarkers",
            langsmith_citation_marker_summary(report.get("exampleContract")),
        ),
        ("secretScan", langsmith_secret_scan_summary(report.get("exampleContract"))),
        ("sdkClient", langsmith_sdk_contract_field(report.get("sdkContract"), "client")),
        ("sdkDatasetApi", langsmith_sdk_contract_field(report.get("sdkContract"), "datasetApi")),
        ("sdkExampleApi", langsmith_sdk_contract_field(report.get("sdkContract"), "exampleApi")),
        ("releaseGate", release_gate_status(report.get("releaseGate"))),
        ("releaseGateReason", release_gate_reason(report.get("releaseGate"))),
        ("releaseGateNext", release_gate_next_action(report.get("releaseGate"))),
        (
            "releaseGateRemediationCommand",
            release_gate_remediation_command(report.get("releaseGate")),
        ),
        *required_env_any_of_rows(report.get("requiredEnvAnyOf")),
        ("missingEnvAnyOf", ",".join(string_list_value(report.get("missingEnvAnyOf", ())))),
        ("recommendedEnv", ",".join(string_list_value(report.get("recommendedEnv", ())))),
        ("productCapability", product_boundary.get("productCapability")),
        (
            "productBoundaryMinorEligible",
            product_boundary.get("productBoundaryMinorEligible"),
        ),
        ("productBoundaryEvidence", product_boundary.get("productBoundaryEvidence")),
        ("productBoundaryMissing", product_boundary.get("productBoundaryMissing")),
        (
            "minorBoundaryResolvedEvidence",
            ",".join(string_list_value(report.get("minorBoundaryResolvedEvidence"))),
        ),
        (
            "productBoundaryRemediationAction",
            product_boundary_remediation_action(product_boundary),
        ),
        (
            "productBoundaryFeedbackReviewAction",
            product_boundary_feedback_review_action(report, product_boundary),
        ),
        ("ragCandidateEvalApplyAction", report.get("ragCandidateEvalApplyAction")),
        ("productBoundaryReadinessCommand", report.get("productBoundaryReadinessCommand")),
        ("liveSyncCommand", report.get("liveSyncCommand")),
        ("readinessCommand", report.get("readinessCommand")),
        ("remediationCommand", report.get("remediationCommand")),
        ("readinessReportArg", report.get("readinessReportArg")),
        (
            "replatformReadinessFile",
            report.get("replatformReadinessFile")
            or (REPLATFORM_READINESS_FILE if has_readiness_command else None),
        ),
        (
            "smokePlanFile",
            report.get("smokePlanFile")
            or (RELEASE_SMOKE_PLAN_FILE if has_readiness_command else None),
        ),
        (
            "preflightFile",
            report.get("preflightFile")
            or (RELEASE_SMOKE_PREFLIGHT_FILE if has_readiness_command else None),
        ),
        (
            "preflightEnvTemplate",
            report.get("preflightEnvTemplate")
            or (RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE if has_readiness_command else None),
        ),
        (
            "releaseEvidenceFile",
            report.get("releaseEvidenceFile")
            or (RELEASE_EVIDENCE_FILE if has_readiness_command else None),
        ),
        (
            "releaseReadinessFile",
            report.get("releaseReadinessFile")
            or (RELEASE_READINESS_FILE if has_readiness_command else None),
        ),
    ]
    required_readiness_reports = string_list_value(report.get("requiredReadinessReports"))
    if required_readiness_reports:
        rows.append(("requiredReadinessReports", ",".join(required_readiness_reports)))
    readiness_reports = report.get("readinessReports")
    if isinstance(readiness_reports, Mapping):
        for report_name, report_file in sorted(
            cast(Mapping[object, object], readiness_reports).items(),
            key=lambda item: str(item[0]),
        ):
            if isinstance(report_name, str) and isinstance(report_file, str):
                report_name = report_name.strip()
                report_file = report_file.strip()
                if report_name and report_file:
                    rows.append((f"readinessReports.{report_name}", report_file))
    resolved_by_reports = report.get("minorBoundaryResolvedByReports")
    if isinstance(resolved_by_reports, Mapping):
        for evidence_name, report_name in sorted(
            cast(Mapping[object, object], resolved_by_reports).items(),
            key=lambda item: str(item[0]),
        ):
            if isinstance(evidence_name, str) and isinstance(report_name, str):
                evidence_name = evidence_name.strip()
                report_name = report_name.strip()
                if evidence_name and report_name:
                    rows.append(
                        (
                            f"minorBoundaryResolvedByReports.{evidence_name}",
                            report_name,
                        )
                    )
    rows.extend(langsmith_next_action_rows(report.get("nextActions")))
    present_rows = [
        (field, str(value)) for field, value in rows if value is not None and value != ""
    ]
    width = max([len("FIELD"), *(len(field) for field, _ in present_rows)])
    lines = [f"{'FIELD':<{width}}  VALUE"]
    lines.extend(f"{field:<{width}}  {value}" for field, value in present_rows)
    return "\n".join(lines) + "\n"


def langsmith_next_action_rows(value: object) -> list[tuple[str, str]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    rows: list[tuple[str, str]] = []
    action_ids: list[str] = []
    for item in cast(Sequence[object], value):
        if not isinstance(item, Mapping):
            continue
        action = cast(Mapping[object, object], item)
        action_id = action.get("id")
        if not isinstance(action_id, str) or not action_id.strip():
            continue
        action_id = action_id.strip()
        action_ids.append(action_id)
        action_prefix = f"nextAction.{action_id}"
        command = action.get("command")
        if isinstance(command, str) and command.strip():
            rows.append((action_prefix, command.strip()))
        for field_name in (
            "envFileCommand",
            "reportFile",
            "preflightFile",
            "preflightEnvTemplate",
            "releaseReadinessFile",
            "releaseReadinessCommand",
            "remediationCommand",
            "replatformReadinessFile",
            "smokePlanFile",
            "releaseEvidenceFile",
            "latestTagCommand",
            "recommendedTagSource",
            "recommendedVersionBump",
            "recommendedTagPattern",
            "candidateTag",
            "evalCaseId",
            "sourceRunId",
            "requiredReviewNote",
            "regenerateReportCommand",
        ):
            field_value = action.get(field_name)
            if isinstance(field_value, str) and field_value.strip():
                rows.append((f"{action_prefix}.{field_name}", field_value.strip()))
        minor_boundary_reports = string_list_value(action.get("minorBoundaryReports"))
        if minor_boundary_reports:
            rows.append(
                (
                    f"{action_prefix}.minorBoundaryReports",
                    ",".join(minor_boundary_reports),
                )
            )
        minor_blocked_reports = string_list_value(action.get("minorBlockedReports"))
        if minor_blocked_reports:
            rows.append(
                (
                    f"{action_prefix}.minorBlockedReports",
                    ",".join(minor_blocked_reports),
                )
            )
        minor_boundary_missing = string_list_value(action.get("minorBoundaryMissingEvidence"))
        if minor_boundary_missing:
            rows.append(
                (
                    f"{action_prefix}.minorBoundaryMissingEvidence",
                    ",".join(minor_boundary_missing),
                )
            )
        product_boundary_missing = string_list_value(action.get("productBoundaryMissing"))
        if product_boundary_missing:
            rows.append(
                (
                    f"{action_prefix}.productBoundaryMissing",
                    ",".join(product_boundary_missing),
                )
            )
        expected_resolved_reports = action.get("productBoundaryExpectedResolvedByReports")
        if isinstance(expected_resolved_reports, Mapping):
            for evidence_name, report_name in sorted(
                cast(Mapping[object, object], expected_resolved_reports).items(),
                key=lambda entry: str(entry[0]),
            ):
                if isinstance(evidence_name, str) and isinstance(report_name, str):
                    evidence_name = evidence_name.strip()
                    report_name = report_name.strip()
                    if evidence_name and report_name:
                        rows.append(
                            (
                                f"{action_prefix}."
                                f"productBoundaryExpectedResolvedByReports.{evidence_name}",
                                report_name,
                            )
                        )
        readiness_report_arg = action.get("readinessReportArg")
        if isinstance(readiness_report_arg, str) and readiness_report_arg.strip():
            rows.append((f"{action_prefix}.readinessReportArg", readiness_report_arg.strip()))
        required_reports = string_list_value(action.get("requiredReadinessReports"))
        if required_reports:
            rows.append((f"{action_prefix}.requiredReadinessReports", ",".join(required_reports)))
        required_env_any_of = action.get("requiredEnvAnyOf")
        if isinstance(required_env_any_of, Sequence) and not isinstance(
            required_env_any_of, str | bytes | bytearray
        ):
            for index, group in enumerate(cast(Sequence[object], required_env_any_of)):
                env_names = string_list_value(group)
                if env_names:
                    rows.append((f"{action_prefix}.requiredEnvAnyOf.{index}", "|".join(env_names)))
        missing_env_any_of = string_list_value(action.get("missingEnvAnyOf"))
        if missing_env_any_of:
            rows.append((f"{action_prefix}.missingEnvAnyOf", ",".join(missing_env_any_of)))
        recommended_env = string_list_value(action.get("recommendedEnv"))
        if recommended_env:
            rows.append((f"{action_prefix}.recommendedEnv", ",".join(recommended_env)))
        depends_on_action_ids = string_list_value(action.get("dependsOnActionIds"))
        if depends_on_action_ids:
            rows.append(
                (
                    f"{action_prefix}.dependsOnActionIds",
                    ",".join(depends_on_action_ids),
                )
            )
        workflow_tags = string_list_value(action.get("workflowTags"))
        if workflow_tags:
            rows.append((f"{action_prefix}.workflowTags", ",".join(workflow_tags)))
        feedback_tags = string_list_value(action.get("feedbackTags"))
        if feedback_tags:
            rows.append((f"{action_prefix}.feedbackTags", ",".join(feedback_tags)))
        case_ids = string_list_value(action.get("caseIds"))
        if case_ids:
            rows.append((f"{action_prefix}.caseIds", ",".join(case_ids)))
        source_run_ids = string_list_value(action.get("sourceRunIds"))
        if source_run_ids:
            rows.append((f"{action_prefix}.sourceRunIds", ",".join(source_run_ids)))
        case_source_run_ids = action.get("caseSourceRunIds")
        if isinstance(case_source_run_ids, Mapping):
            for case_id, source_run_id in sorted(
                cast(Mapping[object, object], case_source_run_ids).items(),
                key=lambda entry: str(entry[0]),
            ):
                if isinstance(case_id, str) and isinstance(source_run_id, str):
                    case_id = case_id.strip()
                    source_run_id = source_run_id.strip()
                    if case_id and source_run_id:
                        rows.append((f"{action_prefix}.caseSourceRunIds.{case_id}", source_run_id))
        readiness_reports = action.get("readinessReports")
        if isinstance(readiness_reports, Mapping):
            for report_name, report_file in sorted(
                cast(Mapping[object, object], readiness_reports).items(),
                key=lambda entry: str(entry[0]),
            ):
                if isinstance(report_name, str) and isinstance(report_file, str):
                    report_name = report_name.strip()
                    report_file = report_file.strip()
                    if report_name and report_file:
                        rows.append(
                            (f"{action_prefix}.readinessReports.{report_name}", report_file)
                        )
    if action_ids:
        rows.insert(0, ("nextActions", ",".join(action_ids)))
    return rows


def required_env_any_of_rows(value: object) -> list[tuple[str, str]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    rows: list[tuple[str, str]] = []
    for index, group in enumerate(cast(Sequence[object], value)):
        env_names = string_list_value(group)
        if env_names:
            rows.append((f"requiredEnvAnyOf.{index}", "|".join(env_names)))
    return rows


def langsmith_product_boundary_summary_parts(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    boundary = cast(Mapping[object, object], value)
    parts: dict[str, str] = {}
    capability = boundary.get("capability")
    if isinstance(capability, str) and capability.strip():
        parts["productCapability"] = capability.strip()
    minor_eligible = boundary.get("minorEligible")
    if isinstance(minor_eligible, bool):
        parts["productBoundaryMinorEligible"] = bool_text(minor_eligible)
    evidence = ",".join(string_list_value(boundary.get("evidence", ())))
    if evidence:
        parts["productBoundaryEvidence"] = evidence
    missing_evidence = ",".join(string_list_value(boundary.get("missingEvidence", ())))
    if missing_evidence:
        parts["productBoundaryMissing"] = missing_evidence
        if "rag_ingestion_lifecycle" in {
            item.strip() for item in missing_evidence.split(",") if item.strip()
        }:
            parts["productBoundaryRemediationAction"] = (
                rag_ingestion_lifecycle_remediation_command()
            )
    return parts


def product_boundary_remediation_action(product_boundary: Mapping[str, str]) -> str:
    missing = product_boundary.get("productBoundaryMissing", "")
    missing_items = {item.strip() for item in missing.split(",") if item.strip()}
    if "rag_ingestion_lifecycle" not in missing_items:
        return ""
    return rag_ingestion_lifecycle_remediation_command()


def product_boundary_feedback_review_action(
    report: Mapping[str, object],
    product_boundary: Mapping[str, str],
) -> str:
    missing = product_boundary.get("productBoundaryMissing", "")
    missing_items = {item.strip() for item in missing.split(",") if item.strip()}
    if "feedback_promotion.reviewed_feedback" not in missing_items:
        return ""
    for key in ("feedbackReviewQueue", "feedbackPromotion"):
        value = report.get(key)
        if not isinstance(value, Mapping):
            continue
        action = cast(Mapping[object, object], value).get("bulkReviewAction")
        if isinstance(action, str) and action.strip():
            return action.strip()
    return ""


def product_boundary_action_handoff(
    product_boundary: Mapping[str, object] | None,
    *,
    required_readiness_reports: Sequence[str],
    resolve_expected_reports: bool = False,
) -> dict[str, object]:
    if product_boundary is None:
        return {}
    missing = string_list_value(product_boundary.get("missingEvidence"))
    if not missing:
        return {}
    expected_resolved_by_reports: dict[str, str] = {}
    if "rag_ingestion_lifecycle" in missing and "hardening_suite" in required_readiness_reports:
        expected_resolved_by_reports["rag_ingestion_lifecycle"] = "hardening_suite"
    remaining_missing = [item for item in missing if item not in expected_resolved_by_reports]
    handoff: dict[str, object] = {}
    if expected_resolved_by_reports:
        handoff["productBoundaryExpectedResolvedByReports"] = expected_resolved_by_reports
    if expected_resolved_by_reports and resolve_expected_reports:
        resolved_evidence = list(expected_resolved_by_reports)
        resolved_boundary = {
            key: value for key, value in product_boundary.items() if key != "missingEvidence"
        }
        resolved_boundary["missingEvidence"] = remaining_missing
        handoff["productCapabilityBoundary"] = resolved_boundary
        handoff["minorBoundaryResolvedEvidence"] = resolved_evidence
        handoff["minorBoundaryResolvedByReports"] = expected_resolved_by_reports
    if remaining_missing:
        handoff["minorBlockedReports"] = ["langsmith_eval_sync"]
        handoff["minorBoundaryMissingEvidence"] = remaining_missing
        handoff["productBoundaryMissing"] = remaining_missing
    return handoff


def langsmith_product_boundary_readiness_command(
    *,
    report_file: Path | None,
    product_boundary: Mapping[str, object],
) -> str:
    if report_file is None:
        return ""
    missing = product_boundary.get("missingEvidence")
    missing_items = set(string_list_value(missing if missing is not None else ()))
    if "rag_ingestion_lifecycle" not in missing_items:
        return ""
    return release_readiness_command_for_reports(
        required_reports=("hardening_suite", "langsmith_eval_sync"),
        report_files={
            "hardening_suite": HARDENING_SUITE_REPORT_FILE,
            "langsmith_eval_sync": str(report_file),
        },
    )


def langsmith_trace_grading_value(report: Mapping[str, object]) -> object:
    trace_grading = report.get("traceGrading")
    if isinstance(trace_grading, Mapping):
        return dict(cast(Mapping[object, object], trace_grading))
    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping):
        return None
    evidence_trace_grading = cast(Mapping[object, object], evidence).get("traceGrading")
    if isinstance(evidence_trace_grading, Mapping):
        return dict(cast(Mapping[object, object], evidence_trace_grading))
    return None


def trace_grounding_citation_summary_value(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    trace_grading = cast(Mapping[object, object], value)
    grades = trace_grading.get("grades")
    if not isinstance(grades, Sequence) or isinstance(grades, str | bytes):
        return {}
    citation_cases = 0
    cited_chunks = 0
    uncited_chunks = 0
    citation_documents: list[str] = []
    seen_documents: set[str] = set()
    for grade in cast(Sequence[object], grades):
        if not isinstance(grade, Mapping):
            continue
        dimensions = cast(Mapping[object, object], grade).get("dimensions")
        if not isinstance(dimensions, Sequence) or isinstance(dimensions, str | bytes):
            continue
        for dimension in cast(Sequence[object], dimensions):
            if not isinstance(dimension, Mapping):
                continue
            dimension_mapping = cast(Mapping[object, object], dimension)
            if dimension_mapping.get("name") != "grounding":
                continue
            evidence = dimension_mapping.get("evidence")
            if not isinstance(evidence, Mapping):
                continue
            evidence_mapping = cast(Mapping[object, object], evidence)
            cited = evidence_mapping.get("cited")
            uncited = evidence_mapping.get("uncited")
            if not isinstance(cited, int) or isinstance(cited, bool) or cited <= 0:
                continue
            citation_cases += 1
            cited_chunks += cited
            if isinstance(uncited, int) and not isinstance(uncited, bool) and uncited > 0:
                uncited_chunks += uncited
            for document in string_list_value(evidence_mapping.get("citedDocuments", ())):
                if document not in seen_documents:
                    seen_documents.add(document)
                    citation_documents.append(document)
    if citation_cases <= 0:
        return {}
    summary: dict[str, object] = {
        "groundingCitationCases": citation_cases,
        "groundingCitedChunks": cited_chunks,
        "groundingUncitedChunks": uncited_chunks,
    }
    if citation_documents:
        summary["groundingCitationDocuments"] = citation_documents
    return summary


def trace_deterministic_eval_summary_value(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    trace_grading = cast(Mapping[object, object], value)
    grades = trace_grading.get("grades")
    if not isinstance(grades, Sequence) or isinstance(grades, str | bytes):
        return {}
    failed_cases = 0
    missing_expected: list[str] = []
    seen_missing: set[str] = set()
    for grade in cast(Sequence[object], grades):
        if not isinstance(grade, Mapping):
            continue
        dimensions = cast(Mapping[object, object], grade).get("dimensions")
        if not isinstance(dimensions, Sequence) or isinstance(dimensions, str | bytes):
            continue
        for dimension in cast(Sequence[object], dimensions):
            if not isinstance(dimension, Mapping):
                continue
            dimension_mapping = cast(Mapping[object, object], dimension)
            if dimension_mapping.get("name") != "deterministic_eval":
                continue
            evidence = dimension_mapping.get("evidence")
            if not isinstance(evidence, Mapping):
                continue
            evidence_mapping = cast(Mapping[object, object], evidence)
            failures = string_list_value(evidence_mapping.get("reasons", ()))
            if failures:
                failed_cases += 1
            for expected in string_list_value(
                evidence_mapping.get("missingExpectedAnswerContains", ())
            ):
                if expected not in seen_missing:
                    seen_missing.add(expected)
                    missing_expected.append(expected)
    if failed_cases <= 0:
        return {}
    return {
        "deterministicEvalFailedCases": failed_cases,
        "deterministicEvalMissingExpected": missing_expected,
    }


def bool_text(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return ""


def split_counts_summary(value: object) -> str:
    counts = int_mapping_value(value)
    return ",".join(f"{key}={counts[key]}" for key in sorted(counts))


def langsmith_source_suite_value(report: Mapping[str, object]) -> str:
    source_suite = report.get("sourceSuite")
    if isinstance(source_suite, str) and source_suite.strip():
        return source_suite.strip()
    dataset_metadata = report.get("datasetMetadata")
    if not isinstance(dataset_metadata, Mapping):
        return ""
    metadata_source_suite = cast(Mapping[object, object], dataset_metadata).get("sourceSuite")
    return metadata_source_suite.strip() if isinstance(metadata_source_suite, str) else ""


def langsmith_example_payload_summary(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    raw_values_included = cast(Mapping[object, object], value).get("rawExampleValuesIncluded")
    if raw_values_included is False:
        return "metadata_only"
    if raw_values_included is True:
        return "raw_values_included"
    return ""


def langsmith_citation_marker_summary(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    citation_contract = cast(Mapping[object, object], value).get("citationMarkerContract")
    if not isinstance(citation_contract, Mapping):
        return ""
    citation_mapping = cast(Mapping[object, object], citation_contract)
    if (
        citation_mapping.get("ragExpectedAnswersRequireBracketedMarkers") is True
        and citation_mapping.get("markerPattern") == "[source-label]"
        and citation_mapping.get("rawExampleValuesIncluded") is False
    ):
        return "bracketed_required"
    return ""


def context_manifest_diagnostics_mapping(report: Mapping[str, object]) -> dict[str, object]:
    diagnostics = report.get("contextManifestDiagnostics")
    return dict(cast(Mapping[str, object], diagnostics)) if isinstance(diagnostics, Mapping) else {}


def langsmith_secret_scan_summary(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    secret_scan = cast(Mapping[object, object], value).get("secretScan")
    if not isinstance(secret_scan, Mapping):
        return ""
    secret_scan_mapping = cast(Mapping[object, object], secret_scan)
    if secret_scan_mapping.get("enabled") is not True:
        return "disabled" if secret_scan_mapping.get("enabled") is False else ""
    if secret_scan_mapping.get("beforeCreateExamples") is True:
        return "before_create_examples"
    return "enabled"


def langsmith_sdk_contract_field(value: object, field: str) -> str:
    if not isinstance(value, Mapping):
        return ""
    item = cast(Mapping[object, object], value).get(field)
    return item.strip() if isinstance(item, str) else ""


def release_gate_status(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    status = cast(Mapping[object, object], value).get("status")
    return status if isinstance(status, str) else ""


def release_gate_reason(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    reason = cast(Mapping[object, object], value).get("reason")
    return reason if isinstance(reason, str) else ""


def release_gate_next_action(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    remediation = cast(Mapping[object, object], value).get("remediation")
    if not isinstance(remediation, Sequence) or isinstance(remediation, str):
        return ""
    for item in cast(Sequence[object], remediation):
        if isinstance(item, str) and item.strip():
            return item.strip()
    return ""


def release_gate_remediation_command(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    command = cast(Mapping[object, object], value).get("remediationCommand")
    return command.strip() if isinstance(command, str) else ""


def langsmith_eval_sync_report(
    result: Mapping[str, object],
    *,
    suite_file: Path,
    dataset_name: str,
    dry_run: bool,
    report_file: Path | None,
    trace_grading: Mapping[str, object] | None = None,
    required_readiness_reports: Sequence[str] = (),
    readiness_reports: Mapping[str, str] | None = None,
) -> dict[str, object]:
    examples = result.get("examples", 0)
    enabled_cases = examples if isinstance(examples, int) and not isinstance(examples, bool) else 0
    example_ids = string_list_value(result.get("exampleIds", ()))
    case_ids = string_list_value(result.get("caseIds", ()))
    metadata_case_ids = string_list_value(result.get("metadataCaseIds", ()))
    source_run_ids = string_list_value(result.get("sourceRunIds", ()))
    case_source_run_ids = string_mapping_value(result.get("caseSourceRunIds", {}))
    split_counts = int_mapping_value(result.get("splitCounts", {}))
    if not split_counts and enabled_cases:
        split_counts = {"regression": enabled_cases}
    source_suite = str(suite_file)
    dataset_metadata_value = result.get("datasetMetadata")
    dataset_metadata = (
        dict(cast(Mapping[str, object], dataset_metadata_value))
        if isinstance(dataset_metadata_value, Mapping)
        else langsmith_dataset_metadata(source_suite=source_suite)
    )
    data_type = result.get("dataType")
    if not isinstance(data_type, str) or not data_type.strip():
        data_type = LANGSMITH_EVAL_DATA_TYPE
    example_contract_value = result.get("exampleContract")
    example_contract = (
        dict(cast(Mapping[str, object], example_contract_value))
        if isinstance(example_contract_value, Mapping)
        else langsmith_eval_example_contract()
    )
    sdk_contract_value = result.get("sdkContract")
    sdk_contract = (
        dict(cast(Mapping[str, object], sdk_contract_value))
        if isinstance(sdk_contract_value, Mapping)
        else langsmith_eval_sdk_contract()
    )
    feedback_promotion = feedback_promotion_summary_value(result.get("feedbackPromotion"))
    feedback_review_queue = feedback_review_queue_summary_value(result.get("feedbackReviewQueue"))
    promotion_coverage = promotion_coverage_summary_value(result.get("promotionCoverage"))
    missing_env_any_of = string_list_value(result.get("missingEnvAnyOf", ()))
    context_manifest_diagnostics_value = result.get("contextManifestDiagnostics")
    context_manifest_diagnostics = (
        dict(cast(Mapping[str, object], context_manifest_diagnostics_value))
        if isinstance(context_manifest_diagnostics_value, Mapping)
        else {}
    )
    context_manifest_diagnostics_missing = not context_manifest_diagnostics
    context_manifest_diagnostics_failed = bool(
        context_manifest_diagnostics
        and langsmith_context_manifest_diagnostics_failed(context_manifest_diagnostics)
    )
    provenance_missing = langsmith_source_run_provenance_missing(
        enabled_cases=enabled_cases,
        case_ids=case_ids,
        source_run_ids=source_run_ids,
        case_source_run_ids=case_source_run_ids,
    )
    feedback_promotion_source_missing = feedback_source_counts_missing(feedback_promotion)
    feedback_review_queue_source_missing = feedback_source_counts_missing(feedback_review_queue)
    trace_grading_failed = langsmith_trace_grading_failed(trace_grading)
    status = (
        "skipped"
        if dry_run
        else "failed"
        if (
            provenance_missing
            or feedback_promotion_source_missing
            or feedback_review_queue_source_missing
            or trace_grading_failed
            or context_manifest_diagnostics_missing
            or context_manifest_diagnostics_failed
        )
        else "passed"
    )
    command_parts = [
        "uv run reactor-langsmith-eval-sync",
        f"--suite-file {quote(str(suite_file))}",
        f"--dataset-name {quote(dataset_name)}",
    ]
    review_report_command_parts = [*command_parts, "--dry-run"]
    live_command_parts = list(command_parts)
    if dry_run:
        command_parts.append("--dry-run")
    if report_file is not None:
        command_parts.append(f"--report-file {quote(str(report_file))}")
        review_report_command_parts.append(f"--report-file {quote(str(report_file))}")
        live_command_parts.append(f"--report-file {quote(str(report_file))}")
    base_report_command = " ".join(review_report_command_parts)
    review_closure_args = feedback_promotion_review_closure_command_args(
        feedback_promotion
    ) or feedback_promotion_review_closure_command_args(feedback_review_queue)
    if review_closure_args:
        command_parts.extend(review_closure_args)
        live_command_parts.extend(review_closure_args)
    explicit_required_readiness_reports = normalized_readiness_report_names(
        required_readiness_reports
    )
    explicit_readiness_reports = dict(readiness_reports or {})
    for required_report in explicit_required_readiness_reports:
        command_parts.append(f"--required-readiness-report {quote(required_report)}")
        live_command_parts.append(f"--required-readiness-report {quote(required_report)}")
    for report_name in explicit_required_readiness_reports:
        report_path = explicit_readiness_reports.get(report_name)
        if report_path:
            command_parts.append(f"--readiness-report {quote(report_name)}={quote(report_path)}")
            live_command_parts.append(
                f"--readiness-report {quote(report_name)}={quote(report_path)}"
            )
    live_sync_command = " ".join(live_command_parts)
    readiness_command = langsmith_readiness_command(report_file)
    product_boundary = rag_candidate_product_capability_boundary(
        dataset_name=dataset_name,
        source_suite=source_suite,
        feedback_promotion=feedback_promotion,
        feedback_review_queue=feedback_review_queue,
        case_ids=case_ids,
        context_manifest_diagnostics=context_manifest_diagnostics,
        trace_grading=trace_grading,
        readiness_command=readiness_command,
    )
    product_boundary_readiness_command = langsmith_product_boundary_readiness_command(
        report_file=report_file,
        product_boundary=product_boundary,
    )
    rag_candidate_eval_action = rag_candidate_eval_apply_action(
        dataset_name=dataset_name,
        source_suite=source_suite,
        case_ids=case_ids,
        case_source_run_ids=case_source_run_ids,
        feedback_review_queue=feedback_review_queue,
    )
    requires_hardening_readiness = result.get("requiresHardeningReadiness") is True
    candidate_readiness_command = rag_candidate_readiness_command(
        dataset_name=dataset_name,
        source_suite=source_suite,
        report_file=report_file,
    )
    if candidate_readiness_command or (
        requires_hardening_readiness and readiness_command and report_file is not None
    ):
        if candidate_readiness_command:
            readiness_command = candidate_readiness_command
        required_readiness_reports = ["hardening_suite", "langsmith_eval_sync"]
        readiness_reports = {
            "hardening_suite": HARDENING_SUITE_REPORT_FILE,
            "langsmith_eval_sync": str(report_file),
        }
        if not candidate_readiness_command:
            readiness_command = release_readiness_command_for_reports(
                required_reports=required_readiness_reports,
                report_files=readiness_reports,
            )
    else:
        required_readiness_reports = ["langsmith_eval_sync"] if readiness_command else []
        readiness_reports = (
            {"langsmith_eval_sync": str(report_file)}
            if readiness_command and report_file is not None
            else {}
        )
    if explicit_required_readiness_reports:
        required_readiness_reports = explicit_required_readiness_reports
        readiness_reports = readiness_reports_for_required_reports(
            required_reports=required_readiness_reports,
            explicit_reports=explicit_readiness_reports,
            report_file=report_file,
        )
        readiness_command = release_readiness_command_for_reports(
            required_reports=required_readiness_reports,
            report_files=readiness_reports,
        )
    product_boundary_handoff = product_boundary_action_handoff(
        product_boundary,
        required_readiness_reports=required_readiness_reports,
        resolve_expected_reports=bool(explicit_required_readiness_reports),
    )
    readiness_report_arg = (
        readiness_report_args_for_reports(
            required_reports=required_readiness_reports,
            report_files=readiness_reports,
        )
        if readiness_command and required_readiness_reports and readiness_reports
        else ""
    )
    live_sync_command = command_with_readiness_report_args(
        live_sync_command,
        required_readiness_reports=required_readiness_reports,
        readiness_report_arg=readiness_report_arg,
    )
    minor_boundary_reports = (
        required_readiness_reports
        if candidate_readiness_command and "hardening_suite" in required_readiness_reports
        else []
    )
    if feedback_promotion and readiness_command:
        feedback_promotion.setdefault("releaseReadinessCommand", readiness_command)
    feedback_bulk_review_action = feedback_promotion.get("bulkReviewAction")
    feedback_bulk_review_actions = (
        [str(feedback_bulk_review_action)] if feedback_bulk_review_action else []
    )
    feedback_bulk_review_report_regeneration_commands = (
        {
            str(feedback_bulk_review_action): feedback_review_report_regeneration_command(
                base_report_command,
                bulk_review_command=str(feedback_bulk_review_action),
            )
        }
        if feedback_bulk_review_action
        else {}
    )
    feedback_queue_bulk_review_action = feedback_review_queue.get("bulkReviewAction")
    feedback_queue_bulk_review_actions = (
        [str(feedback_queue_bulk_review_action)] if feedback_queue_bulk_review_action else []
    )
    feedback_queue_bulk_review_report_regeneration_commands = (
        {
            str(feedback_queue_bulk_review_action): feedback_review_report_regeneration_command(
                base_report_command,
                bulk_review_command=str(feedback_queue_bulk_review_action),
            )
        }
        if feedback_queue_bulk_review_action
        else {}
    )
    review_note_value = feedback_review_queue.get("reviewNote")
    required_review_note = (
        review_note_value.strip()
        if isinstance(review_note_value, str) and review_note_value.strip()
        else ""
    )
    next_actions = [
        *langsmith_report_artifact_actions(
            dry_run=dry_run,
            suite_file=suite_file,
            dataset_name=dataset_name,
            report_file=report_file,
        ),
        *langsmith_report_next_actions(
            dry_run=dry_run,
            live_sync_command=live_sync_command,
            live_report_file=report_file,
            readiness_command=readiness_command,
            readiness_report_arg=readiness_report_arg,
            required_readiness_reports=required_readiness_reports,
            readiness_reports=readiness_reports,
            minor_boundary_reports=minor_boundary_reports,
            missing_env_any_of=missing_env_any_of,
            feedback_review_actions=(
                []
                if feedback_promotion_review_closed(feedback_promotion)
                else langsmith_feedback_review_actions(feedback_promotion)
                if feedback_promotion
                else []
            ),
            feedback_bulk_review_actions=feedback_bulk_review_actions,
            feedback_bulk_review_report_regeneration_commands=(
                feedback_bulk_review_report_regeneration_commands
            ),
            feedback_queue_review_actions=(
                [str(feedback_review_queue["reviewAction"])]
                if feedback_review_queue.get("reviewAction")
                else []
            ),
            feedback_queue_bulk_review_actions=feedback_queue_bulk_review_actions,
            feedback_queue_bulk_review_report_regeneration_commands=(
                feedback_queue_bulk_review_report_regeneration_commands
            ),
            candidate_review_actions=(
                [str(feedback_review_queue["candidateReviewAction"])]
                if feedback_review_queue.get("candidateReviewAction")
                else []
            ),
            required_review_note=required_review_note,
            product_boundary=product_boundary,
            resolve_product_boundary_expected_reports=bool(explicit_required_readiness_reports),
            case_source_run_ids=case_source_run_ids,
        ),
    ]
    next_action_state_fields = langsmith_next_action_state_fields(next_actions)
    evidence: dict[str, object] = {
        "artifact": str(report_file) if report_file is not None else "stdout",
        "command": " ".join(command_parts),
        "owner": "reactor.evals",
        "mode": "langsmith_dataset_sync_dry_run" if dry_run else "langsmith_dataset_sync",
        "datasetName": dataset_name,
        "dataType": data_type,
        "datasetMetadata": dataset_metadata,
        "sourceSuite": source_suite,
        "enabledCases": enabled_cases,
        "exampleIds": example_ids,
        "caseIds": case_ids,
        "metadataCaseIds": metadata_case_ids,
        "sourceRunIds": source_run_ids,
        "caseSourceRunIds": case_source_run_ids,
        "splitCounts": split_counts,
        "exampleContract": example_contract,
        "sdkContract": sdk_contract,
    }
    if dry_run:
        evidence["liveSyncCommand"] = live_sync_command
        evidence["syncCommand"] = live_sync_command
        evidence["requiredEnvAnyOf"] = LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF
        evidence["missingEnvAnyOf"] = missing_env_any_of
        evidence["recommendedEnv"] = LANGSMITH_SYNC_RECOMMENDED_ENV
    else:
        evidence["syncCommand"] = live_sync_command
    if readiness_command:
        evidence["readinessCommand"] = readiness_command
        evidence["remediationCommand"] = readiness_command
        evidence["readinessReportArg"] = readiness_report_arg
        evidence["requiredReadinessReports"] = required_readiness_reports
        evidence["readinessReports"] = readiness_reports
        evidence["replatformReadinessFile"] = REPLATFORM_READINESS_FILE
        evidence["smokePlanFile"] = RELEASE_SMOKE_PLAN_FILE
        evidence["preflightFile"] = RELEASE_SMOKE_PREFLIGHT_FILE
        evidence["preflightEnvTemplate"] = RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE
        evidence["releaseEvidenceFile"] = RELEASE_EVIDENCE_FILE
        evidence["releaseReadinessFile"] = RELEASE_READINESS_FILE
        if next_actions:
            evidence["nextActions"] = next_actions
            evidence.update(next_action_state_fields)
    elif next_actions:
        evidence["nextActions"] = next_actions
        evidence.update(next_action_state_fields)
    if trace_grading is not None:
        evidence["traceGrading"] = dict(trace_grading)
    if context_manifest_diagnostics:
        evidence["contextManifestDiagnostics"] = context_manifest_diagnostics
    if feedback_promotion:
        evidence["feedbackPromotion"] = feedback_promotion
    if feedback_review_queue:
        evidence["feedbackReviewQueue"] = feedback_review_queue
    if promotion_coverage:
        evidence["promotionCoverage"] = promotion_coverage
    if product_boundary:
        evidence["productCapabilityBoundary"] = product_boundary
    if product_boundary_handoff:
        evidence.update(product_boundary_handoff)
    if product_boundary_readiness_command:
        evidence["productBoundaryReadinessCommand"] = product_boundary_readiness_command
    if rag_candidate_eval_action:
        evidence["ragCandidateEvalApplyAction"] = rag_candidate_eval_action
    source: dict[str, object] = {
        "suiteFile": source_suite,
        "enabledCases": enabled_cases,
        "datasetMetadata": dataset_metadata,
        "caseIds": case_ids,
        "metadataCaseIds": metadata_case_ids,
        "sourceRunIds": source_run_ids,
        "caseSourceRunIds": case_source_run_ids,
        "splitCounts": split_counts,
    }
    if feedback_promotion:
        source["feedbackPromotion"] = feedback_promotion
    if feedback_review_queue:
        source["feedbackReviewQueue"] = feedback_review_queue
    if promotion_coverage:
        source["promotionCoverage"] = promotion_coverage
    if context_manifest_diagnostics:
        source["contextManifestDiagnostics"] = context_manifest_diagnostics
    if product_boundary:
        source["productCapabilityBoundary"] = product_boundary
    if product_boundary_handoff:
        source.update(product_boundary_handoff)
    if product_boundary_readiness_command:
        source["productBoundaryReadinessCommand"] = product_boundary_readiness_command
    if rag_candidate_eval_action:
        source["ragCandidateEvalApplyAction"] = rag_candidate_eval_action
    release_gate = langsmith_eval_sync_release_gate(
        dry_run=dry_run,
        provenance_missing=provenance_missing,
        feedback_promotion_source_missing=feedback_promotion_source_missing,
        feedback_review_queue_source_missing=feedback_review_queue_source_missing,
        feedback_review_queue_remediation_command=feedback_review_queue_remediation_command(
            feedback_review_queue
        ),
        trace_grading_failed=trace_grading_failed,
        context_manifest_diagnostics_missing=context_manifest_diagnostics_missing,
        context_manifest_diagnostics_failed=context_manifest_diagnostics_failed,
    )
    return {
        "ok": (
            not dry_run
            and not provenance_missing
            and not feedback_promotion_source_missing
            and not feedback_review_queue_source_missing
            and not trace_grading_failed
            and not context_manifest_diagnostics_missing
            and not context_manifest_diagnostics_failed
        ),
        "status": status,
        "scope": "langsmith_eval_dataset_sync",
        "evidence": evidence,
        "datasetName": dataset_name,
        "dataType": data_type,
        "datasetMetadata": dataset_metadata,
        "sourceSuite": source_suite,
        "dryRun": dry_run,
        "created": bool(result.get("created", False)),
        "examples": enabled_cases,
        "exampleIds": example_ids,
        "caseIds": case_ids,
        "metadataCaseIds": metadata_case_ids,
        "sourceRunIds": source_run_ids,
        "caseSourceRunIds": case_source_run_ids,
        "splitCounts": split_counts,
        **(
            {"contextManifestDiagnostics": context_manifest_diagnostics}
            if context_manifest_diagnostics
            else {}
        ),
        "exampleContract": example_contract,
        "sdkContract": sdk_contract,
        "releaseGateReason": release_gate.get("reason"),
        "releaseGate": release_gate,
        "source": source,
        **({"traceGrading": dict(trace_grading)} if trace_grading is not None else {}),
        "syncCommand": live_sync_command,
        **(
            {
                "liveSyncCommand": live_sync_command,
                "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
                "missingEnvAnyOf": missing_env_any_of,
                "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
            }
            if dry_run
            else {}
        ),
        **({"readinessCommand": readiness_command} if readiness_command else {}),
        **(
            {
                "remediationCommand": readiness_command,
                "readinessReportArg": readiness_report_arg,
                "requiredReadinessReports": required_readiness_reports,
                "readinessReports": readiness_reports,
                "replatformReadinessFile": REPLATFORM_READINESS_FILE,
                "smokePlanFile": RELEASE_SMOKE_PLAN_FILE,
                "preflightFile": RELEASE_SMOKE_PREFLIGHT_FILE,
                "preflightEnvTemplate": RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
                "releaseEvidenceFile": RELEASE_EVIDENCE_FILE,
                "releaseReadinessFile": RELEASE_READINESS_FILE,
                **(
                    {"nextActions": next_actions, **next_action_state_fields}
                    if next_actions
                    else {}
                ),
            }
            if readiness_command
            else {}
        ),
        **(
            {"nextActions": next_actions, **next_action_state_fields}
            if next_actions and not readiness_command
            else {}
        ),
        **({"feedbackPromotion": feedback_promotion} if feedback_promotion else {}),
        **({"feedbackReviewQueue": feedback_review_queue} if feedback_review_queue else {}),
        **({"promotionCoverage": promotion_coverage} if promotion_coverage else {}),
        **({"productCapabilityBoundary": product_boundary} if product_boundary else {}),
        **product_boundary_handoff,
        **(
            {"productBoundaryReadinessCommand": product_boundary_readiness_command}
            if product_boundary_readiness_command
            else {}
        ),
        **(
            {"ragCandidateEvalApplyAction": rag_candidate_eval_action}
            if rag_candidate_eval_action
            else {}
        ),
    }


def langsmith_report_next_actions(
    *,
    dry_run: bool,
    live_sync_command: str,
    live_report_file: Path | None = None,
    readiness_command: str,
    readiness_report_arg: str,
    required_readiness_reports: list[str],
    readiness_reports: dict[str, str],
    minor_boundary_reports: Sequence[str] = (),
    missing_env_any_of: Sequence[str] = (),
    feedback_review_actions: Sequence[str] = (),
    feedback_bulk_review_actions: Sequence[str] = (),
    feedback_bulk_review_report_regeneration_commands: Mapping[str, str] | None = None,
    feedback_queue_review_actions: Sequence[str] = (),
    feedback_queue_bulk_review_actions: Sequence[str] = (),
    feedback_queue_bulk_review_report_regeneration_commands: Mapping[str, str] | None = None,
    candidate_review_actions: Sequence[str] = (),
    required_review_note: str = "",
    product_boundary: Mapping[str, object] | None = None,
    resolve_product_boundary_expected_reports: bool = False,
    case_source_run_ids: Mapping[str, str] | None = None,
) -> list[dict[str, object]]:
    if not readiness_command or not readiness_report_arg:
        return []
    actions: list[dict[str, object]] = []
    for command in feedback_queue_review_actions:
        actions.append(
            langsmith_feedback_queue_review_next_action(
                command,
                case_source_run_ids=case_source_run_ids,
            )
        )
    for command in feedback_queue_bulk_review_actions:
        action = langsmith_feedback_queue_bulk_review_next_action(
            command,
            case_source_run_ids=case_source_run_ids,
            regenerate_report_command=(
                feedback_queue_bulk_review_report_regeneration_commands or {}
            ).get(command, ""),
        )
        add_readiness_metadata(
            action,
            release_readiness_command=readiness_command,
            readiness_report_arg=readiness_report_arg,
            required_readiness_reports=required_readiness_reports,
            readiness_reports=readiness_reports,
        )
        actions.append(action)
    for command in candidate_review_actions:
        actions.append(
            langsmith_candidate_review_next_action(
                command,
                case_source_run_ids=case_source_run_ids,
            )
        )
    for command in feedback_review_actions:
        actions.append(langsmith_feedback_review_next_action(command))
    for command in feedback_bulk_review_actions:
        action = langsmith_feedback_bulk_review_next_action(
            command,
            case_source_run_ids=case_source_run_ids,
            regenerate_report_command=(feedback_bulk_review_report_regeneration_commands or {}).get(
                command, ""
            ),
        )
        add_readiness_metadata(
            action,
            release_readiness_command=readiness_command,
            readiness_report_arg=readiness_report_arg,
            required_readiness_reports=required_readiness_reports,
            readiness_reports=readiness_reports,
        )
        actions.append(action)
    sync_action_created = dry_run and bool(live_sync_command.strip())
    if sync_action_created:
        preflight_report_file = (
            langsmith_preflight_report_file(live_report_file)
            if live_report_file is not None
            else None
        )
        preflight_command = langsmith_preflight_command_for_live_sync(
            live_sync_command.strip(),
            live_report_file=live_report_file,
        )
        review_note_handoff = (
            {"requiredReviewNote": required_review_note.strip()}
            if required_review_note.strip()
            else {}
        )
        actions.append(
            {
                "id": "preflight-langsmith",
                "label": "Preflight the LangSmith eval sync credentials",
                "command": preflight_command,
                "envFileCommand": langsmith_env_file_command(preflight_command),
                **(
                    {"reportFile": str(preflight_report_file)}
                    if preflight_report_file is not None
                    else {}
                ),
                "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
                **({"missingEnvAnyOf": missing_env_any_of} if missing_env_any_of else {}),
                "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
                "preflightFile": RELEASE_SMOKE_PREFLIGHT_FILE,
                "preflightEnvTemplate": RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
                "releaseReadinessFile": RELEASE_READINESS_FILE,
                "releaseReadinessCommand": readiness_command,
                "remediationCommand": preflight_command,
                "readinessReportArg": readiness_report_arg,
                "requiredReadinessReports": required_readiness_reports,
                "readinessReports": readiness_reports,
                **review_note_handoff,
            }
        )
        actions.append(
            {
                "id": "sync-langsmith",
                "label": "Run the LangSmith eval sync without dry-run",
                "command": live_sync_command.strip(),
                "envFileCommand": langsmith_env_file_command(live_sync_command.strip()),
                **({"reportFile": str(live_report_file)} if live_report_file is not None else {}),
                "dependsOnActionIds": ["preflight-langsmith"],
                "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
                "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
                "preflightFile": RELEASE_SMOKE_PREFLIGHT_FILE,
                "preflightEnvTemplate": RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
                "releaseReadinessFile": RELEASE_READINESS_FILE,
                "releaseReadinessCommand": readiness_command,
                "remediationCommand": live_sync_command.strip(),
                "readinessReportArg": readiness_report_arg,
                "requiredReadinessReports": required_readiness_reports,
                "readinessReports": readiness_reports,
                **review_note_handoff,
            }
        )
    if "hardening_suite" in required_readiness_reports and not minor_boundary_reports:
        actions.append(
            {
                "id": "generate-hardening-suite",
                "label": "Generate the hardening suite report required for minor boundary review",
                "command": rag_ingestion_lifecycle_remediation_command(),
                "readinessReportArg": (
                    f"--readiness-report hardening_suite={HARDENING_SUITE_REPORT_FILE}"
                ),
                "releaseReadinessCommand": readiness_command,
                "requiredReadinessReports": required_readiness_reports,
                "readinessReports": readiness_reports,
            }
        )
    label = "Refresh release readiness with the LangSmith eval sync report"
    if minor_boundary_reports:
        label = "Refresh release readiness with candidate LangSmith and hardening reports"
    elif "hardening_suite" in required_readiness_reports:
        label = "Refresh release readiness with promoted LangSmith and hardening reports"
    actions.append(
        {
            "id": "refresh-release-readiness",
            "label": label,
            "command": readiness_command,
            "envFileCommand": langsmith_env_file_command(readiness_command),
            **({"dependsOnActionIds": ["sync-langsmith"]} if sync_action_created else {}),
            "remediationCommand": readiness_command,
            "latestTagCommand": LATEST_TAG_COMMAND,
            "recommendedTagSource": RECOMMENDED_TAG_SOURCE,
            "replatformReadinessFile": REPLATFORM_READINESS_FILE,
            "smokePlanFile": RELEASE_SMOKE_PLAN_FILE,
            "releaseEvidenceFile": RELEASE_EVIDENCE_FILE,
            "releaseReadinessFile": RELEASE_READINESS_FILE,
            "readinessReportArg": readiness_report_arg,
            "requiredReadinessReports": required_readiness_reports,
            "readinessReports": readiness_reports,
            **(
                {"requiredReviewNote": required_review_note.strip()}
                if required_review_note.strip()
                else {}
            ),
            **(
                {"minorBoundaryReports": list(minor_boundary_reports)}
                if minor_boundary_reports
                else {}
            ),
            **product_boundary_action_handoff(
                product_boundary,
                required_readiness_reports=required_readiness_reports,
                resolve_expected_reports=resolve_product_boundary_expected_reports,
            ),
        }
    )
    return actions


def langsmith_preflight_command_for_live_sync(
    live_sync_command: str,
    *,
    live_report_file: Path | None,
) -> str:
    command = live_sync_command.strip()
    if live_report_file is not None:
        live_report_arg = f"--report-file {quote(str(live_report_file))}"
        preflight_report_arg = (
            f"--report-file {quote(str(langsmith_preflight_report_file(live_report_file)))}"
        )
        command = command.replace(live_report_arg, preflight_report_arg, 1)
    return f"{command} --preflight-only --output table"


def langsmith_preflight_report_file(live_report_file: Path) -> Path:
    stem = live_report_file.stem
    if stem.endswith("-preflight"):
        return live_report_file
    if stem.endswith("-dry-run"):
        stem = stem.removesuffix("-dry-run")
    return live_report_file.with_name(f"{stem}-preflight{live_report_file.suffix}")


def command_with_readiness_report_args(
    command: str,
    *,
    required_readiness_reports: Sequence[str],
    readiness_report_arg: str,
) -> str:
    command = command.strip()
    if not command:
        return ""
    parts = [command]
    for report_name in required_readiness_reports:
        required_arg = f"--required-readiness-report {quote(report_name)}"
        if required_arg not in command:
            parts.append(required_arg)
    readiness_report_arg = readiness_report_arg.strip()
    if readiness_report_arg and readiness_report_arg not in command:
        parts.append(readiness_report_arg)
    return " ".join(parts)


def add_readiness_metadata(
    action: dict[str, object],
    *,
    release_readiness_command: str = "",
    readiness_report_arg: str,
    required_readiness_reports: Sequence[str],
    readiness_reports: Mapping[str, str],
) -> None:
    if release_readiness_command.strip():
        action["releaseReadinessCommand"] = release_readiness_command.strip()
    if readiness_report_arg:
        action["readinessReportArg"] = readiness_report_arg
    if required_readiness_reports:
        action["requiredReadinessReports"] = list(required_readiness_reports)
    if readiness_reports:
        action["readinessReports"] = dict(readiness_reports)


def langsmith_report_artifact_actions(
    *,
    dry_run: bool,
    suite_file: Path,
    dataset_name: str,
    report_file: Path | None,
) -> list[dict[str, object]]:
    if not dry_run or report_file is not None:
        return []
    report_path = default_langsmith_dry_run_report_file(dataset_name)
    required_readiness_reports = (
        ["hardening_suite", "langsmith_eval_sync"]
        if dataset_name == RAG_CANDIDATE_DATASET_NAME
        else ["langsmith_eval_sync"]
    )
    readiness_reports = {
        **(
            {"hardening_suite": HARDENING_SUITE_REPORT_FILE}
            if "hardening_suite" in required_readiness_reports
            else {}
        ),
        "langsmith_eval_sync": str(report_path),
    }
    readiness_report_arg = readiness_report_args_for_reports(
        required_reports=required_readiness_reports,
        report_files=readiness_reports,
    )
    return [
        {
            "id": "rerun-with-report-file",
            "label": "Re-run the LangSmith dry-run with a report artifact for readiness",
            "command": (
                "uv run reactor-langsmith-eval-sync "
                f"--suite-file {quote(str(suite_file))} "
                f"--dataset-name {quote(dataset_name)} "
                "--dry-run "
                f"--report-file {quote(str(report_path))} "
                "--output table"
            ),
            "reportFile": str(report_path),
            "readinessReportArg": readiness_report_arg,
            "requiredReadinessReports": required_readiness_reports,
            "readinessReports": readiness_reports,
        }
    ]


def default_langsmith_dry_run_report_file(dataset_name: str) -> Path:
    if dataset_name == RAG_CANDIDATE_DATASET_NAME:
        return Path("artifacts/langsmith/rag-ingestion-candidate-dry-run.json")
    return Path(f"artifacts/langsmith/{command_slug(dataset_name)}-dry-run.json")


def langsmith_feedback_review_next_action(command: str) -> dict[str, object]:
    action: dict[str, object] = {
        "id": "review-feedback",
        "label": "Review feedback promoted into the LangSmith eval report",
        "command": command,
    }
    parts = shell_split(command)
    if "--feedback-id" in parts:
        feedback_id_index = parts.index("--feedback-id") + 1
        if feedback_id_index < len(parts):
            feedback_id = parts[feedback_id_index]
            action["id"] = f"review-feedback-{feedback_id}"
            action["feedbackId"] = feedback_id
    return action


def feedback_review_closure_args_from_bulk_review_command(command: str) -> list[str]:
    parts = shell_split(command)
    args: list[str] = []
    if "--status" in parts:
        status_index = parts.index("--status") + 1
        if status_index < len(parts):
            args.append(f"--feedback-review-status {quote(parts[status_index])}")
    for index, part in enumerate(parts[:-1]):
        if part == "--tag":
            args.append(f"--feedback-review-tag {quote(parts[index + 1])}")
    if "--note" in parts:
        note_index = parts.index("--note") + 1
        if note_index < len(parts):
            args.append(f"--feedback-review-note {quote(parts[note_index])}")
    return args


def feedback_review_report_regeneration_command(
    base_report_command: str,
    *,
    bulk_review_command: str,
) -> str:
    closure_args = feedback_review_closure_args_from_bulk_review_command(bulk_review_command)
    if not base_report_command.strip() or not closure_args:
        return ""
    return f"{base_report_command.strip()} {' '.join(closure_args)}"


def langsmith_feedback_bulk_review_next_action(
    command: str,
    *,
    case_source_run_ids: Mapping[str, str] | None = None,
    regenerate_report_command: str = "",
) -> dict[str, object]:
    action: dict[str, object] = {
        "id": "bulk-review-feedback",
        "label": "Close promoted feedback after LangSmith eval handoff is reviewed",
        "command": command,
    }
    if regenerate_report_command.strip():
        action["regenerateReportCommand"] = regenerate_report_command.strip()
    parts = shell_split(command)
    candidate_tags = [
        parts[index + 1]
        for index, part in enumerate(parts[:-1])
        if part == "--candidate-tag" and valid_candidate_workflow_tag(parts[index + 1])
    ]
    if len(candidate_tags) == 1:
        candidate_tag = candidate_tags[0]
        candidate_id = candidate_tag.removeprefix("rag-candidate:")
        action["id"] = f"bulk-review-feedback-{candidate_id}"
        action["label"] = (
            "Close promoted RAG candidate feedback after LangSmith eval handoff is reviewed"
        )
        action["candidateTag"] = candidate_tag
        canonical_eval_case_id = rag_candidate_case_id(candidate_id)
        legacy_eval_case_id = f"case-rag-candidate-{candidate_id}"
        eval_case_id = canonical_eval_case_id
        if case_source_run_ids and legacy_eval_case_id in case_source_run_ids:
            eval_case_id = legacy_eval_case_id
        action["evalCaseId"] = eval_case_id
        if case_source_run_ids and case_source_run_ids.get(eval_case_id):
            action["sourceRunId"] = case_source_run_ids[eval_case_id]
        action["requiredReviewNote"] = RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE
    return action


def langsmith_feedback_queue_bulk_review_next_action(
    command: str,
    *,
    case_source_run_ids: Mapping[str, str] | None = None,
    regenerate_report_command: str = "",
) -> dict[str, object]:
    action: dict[str, object] = {
        "id": "bulk-review-feedback-queue",
        "label": "Close queued feedback after the LangSmith eval handoff is reviewed",
        "command": command,
    }
    if regenerate_report_command.strip():
        action["regenerateReportCommand"] = regenerate_report_command.strip()
    parts = shell_split(command)
    candidate_tags = [
        parts[index + 1]
        for index, part in enumerate(parts[:-1])
        if part == "--candidate-tag" and valid_candidate_workflow_tag(parts[index + 1])
    ]
    if len(candidate_tags) == 1:
        candidate_tag = candidate_tags[0]
        candidate_id = candidate_tag.removeprefix("rag-candidate:")
        action["candidateTag"] = candidate_tag
        canonical_eval_case_id = rag_candidate_case_id(candidate_id)
        legacy_eval_case_id = f"case-rag-candidate-{candidate_id}"
        eval_case_id = canonical_eval_case_id
        if case_source_run_ids and legacy_eval_case_id in case_source_run_ids:
            eval_case_id = legacy_eval_case_id
        action["evalCaseId"] = eval_case_id
        if case_source_run_ids and case_source_run_ids.get(eval_case_id):
            action["sourceRunId"] = case_source_run_ids[eval_case_id]
        action["requiredReviewNote"] = RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE
    return action


def langsmith_feedback_queue_review_next_action(
    command: str,
    *,
    case_source_run_ids: Mapping[str, str] | None = None,
) -> dict[str, object]:
    action: dict[str, object] = {
        "id": "review-feedback-queue",
        "label": "Review feedback waiting for LangSmith eval source metadata",
        "command": command,
    }
    parts = shell_split(command)
    candidate_tags = [
        parts[index + 1]
        for index, part in enumerate(parts[:-1])
        if part == "--tag" and valid_candidate_workflow_tag(parts[index + 1])
    ]
    if len(candidate_tags) == 1:
        candidate_id = candidate_tags[0].removeprefix("rag-candidate:")
        canonical_eval_case_id = rag_candidate_case_id(candidate_id)
        legacy_eval_case_id = f"case-rag-candidate-{candidate_id}"
        eval_case_id = canonical_eval_case_id
        if case_source_run_ids and legacy_eval_case_id in case_source_run_ids:
            eval_case_id = legacy_eval_case_id
        action["evalCaseId"] = eval_case_id
        if case_source_run_ids and case_source_run_ids.get(eval_case_id):
            action["sourceRunId"] = case_source_run_ids[eval_case_id]
    return action


def langsmith_candidate_review_next_action(
    command: str,
    *,
    case_source_run_ids: Mapping[str, str] | None = None,
) -> dict[str, object]:
    action: dict[str, object] = {
        "id": "review-rag-candidates",
        "label": "Review the RAG ingestion candidates behind the LangSmith report",
        "command": command,
    }
    parts = shell_split(command)
    candidate_tags = [
        parts[index + 1]
        for index, part in enumerate(parts[:-1])
        if part == "--tag" and valid_candidate_workflow_tag(parts[index + 1])
    ]
    if len(candidate_tags) == 1:
        candidate_tag = candidate_tags[0]
        candidate_id = candidate_tag.removeprefix("rag-candidate:")
        action["id"] = f"review-rag-candidate-{candidate_id}"
        action["label"] = "Review the RAG ingestion candidate behind the LangSmith report"
        action["candidateTag"] = candidate_tag
        eval_case_id = rag_candidate_case_id(candidate_id)
        action["evalCaseId"] = eval_case_id
        if case_source_run_ids and case_source_run_ids.get(eval_case_id):
            action["sourceRunId"] = case_source_run_ids[eval_case_id]
    return action


def rag_candidate_product_capability_boundary(
    *,
    dataset_name: str,
    source_suite: str,
    feedback_promotion: Mapping[str, object],
    feedback_review_queue: Mapping[str, object],
    case_ids: Sequence[str],
    context_manifest_diagnostics: Mapping[str, object],
    trace_grading: Mapping[str, object] | None,
    readiness_command: str,
) -> dict[str, object]:
    if dataset_name != RAG_CANDIDATE_DATASET_NAME:
        return {}
    if not source_suite:
        return {}
    has_feedback_review_queue = bool(feedback_review_queue) and bool(
        int_mapping_value(feedback_review_queue.get("feedbackSourceCounts", {}))
    )
    has_feedback_promotion = bool(feedback_promotion) and bool(
        int_mapping_value(feedback_promotion.get("feedbackSourceCounts", {}))
    )
    has_reviewed_feedback = (
        has_feedback_promotion and feedback_promotion_review_closed(feedback_promotion)
    ) or (has_feedback_review_queue and feedback_promotion_review_closed(feedback_review_queue))
    if not has_feedback_review_queue and not has_feedback_promotion:
        return {}
    if not isinstance(trace_grading, Mapping):
        return {}
    if trace_grading.get("failed") != 0:
        return {}
    graded_runs = trace_grading.get("gradedRuns")
    if not isinstance(graded_runs, int) or isinstance(graded_runs, bool) or graded_runs < 1:
        return {}
    if not readiness_command:
        return {}
    evidence: list[str] = []
    if has_feedback_review_queue:
        evidence.append("rag_ingestion_candidate_feedback_queue")
    if has_reviewed_feedback:
        evidence.append("feedback_promotion.reviewed_feedback")
    evidence.extend(
        [
            "langsmith_trace_grading",
            "release_readiness_command",
        ]
    )
    missing_evidence = [
        "rag_ingestion_lifecycle",
        *missing_rag_candidate_citation_workflow_evidence(
            diagnostics=context_manifest_diagnostics,
            case_ids=case_ids,
        ),
    ]
    if not has_reviewed_feedback:
        missing_evidence.append("feedback_promotion.reviewed_feedback")
    return {
        "minorEligible": False,
        "capability": "rag_ingest_to_feedback_eval_langsmith_readiness",
        "evidence": evidence,
        "missingEvidence": missing_evidence,
    }


def rag_candidate_eval_apply_action(
    *,
    dataset_name: str,
    source_suite: str,
    case_ids: Sequence[str],
    case_source_run_ids: Mapping[str, str],
    feedback_review_queue: Mapping[str, object],
) -> str:
    if dataset_name != RAG_CANDIDATE_DATASET_NAME or source_suite != RAG_CANDIDATE_SOURCE_SUITE:
        return ""
    if len(case_ids) != 1:
        return ""
    case_id = case_ids[0]
    candidate_slug = rag_candidate_slug_from_case_id(case_id)
    if candidate_slug is None:
        return ""
    source_run_id = case_source_run_ids.get(case_id, "")
    if not source_run_id.strip():
        return ""
    return rag_candidate_eval_apply_action_command(
        source_run_id=source_run_id,
        case_id=case_id,
        source_suite=RAG_CANDIDATE_SOURCE_SUITE,
        dataset_name=RAG_CANDIDATE_DATASET_NAME,
        feedback_source=single_feedback_source_from_queue(feedback_review_queue),
        extra_tags=expected_citation_tags_from_queue(feedback_review_queue),
        feedback_review_status=clean_string_value(feedback_review_queue.get("reviewStatus")),
        feedback_review_tags=string_list_value(feedback_review_queue.get("reviewTags", ())),
        feedback_review_note=clean_string_value(feedback_review_queue.get("reviewNote")),
    )


def clean_string_value(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def expected_citation_tags_from_queue(feedback_review_queue: Mapping[str, object]) -> list[str]:
    expected_citation_counts = feedback_review_queue.get("expectedCitationCounts")
    if not isinstance(expected_citation_counts, Mapping):
        return []
    return [
        f"expected-citation:{citation_id.strip()}"
        for citation_id, count in cast(Mapping[object, object], expected_citation_counts).items()
        if isinstance(citation_id, str)
        and citation_id.strip()
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count > 0
    ]


def single_feedback_source_from_queue(feedback_review_queue: Mapping[str, object]) -> str:
    source_counts = feedback_review_queue.get("feedbackSourceCounts")
    if not isinstance(source_counts, Mapping):
        return ""
    sources = [
        source.strip()
        for source, count in cast(Mapping[object, object], source_counts).items()
        if isinstance(source, str)
        and source.strip()
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count > 0
    ]
    if len(sources) != 1:
        return ""
    return sources[0]


def missing_rag_candidate_citation_workflow_evidence(
    *,
    diagnostics: Mapping[str, object],
    case_ids: Sequence[str],
) -> list[str]:
    workflow_case_ids = set(string_list_value(diagnostics.get("citationWorkflowEvalCaseIds")))
    workflow_tags = set(string_list_value(diagnostics.get("citationWorkflowTags")))
    expected_workflow_tags = {
        rag_candidate_workflow_tag(slug)
        for case_id in case_ids
        for slug in [rag_candidate_slug_from_case_id(case_id)]
        if slug is not None
    }
    missing: list[str] = []
    if not workflow_case_ids or not set(case_ids).issubset(workflow_case_ids):
        missing.append("context_manifest_diagnostics.citationWorkflowEvalCaseIds")
    if not expected_workflow_tags or not expected_workflow_tags.issubset(workflow_tags):
        missing.append("context_manifest_diagnostics.citationWorkflowTags")
    return missing


def rag_candidate_readiness_command(
    *,
    dataset_name: str,
    source_suite: str,
    report_file: Path | None,
) -> str:
    if dataset_name != RAG_CANDIDATE_DATASET_NAME or not source_suite or report_file is None:
        return ""
    return release_readiness_command_for_reports(
        required_reports=("hardening_suite", "langsmith_eval_sync"),
        report_files={
            "hardening_suite": HARDENING_SUITE_REPORT_FILE,
            "langsmith_eval_sync": str(report_file),
        },
    )


def feedback_source_counts_missing(feedback_promotion: Mapping[str, object]) -> bool:
    return bool(feedback_promotion) and not int_mapping_value(
        feedback_promotion.get("feedbackSourceCounts", {})
    )


def feedback_review_queue_remediation_command(feedback_review_queue: Mapping[str, object]) -> str:
    review_action = feedback_review_queue.get("reviewAction")
    return review_action.strip() if isinstance(review_action, str) else ""


def langsmith_readiness_command(report_file: Path | None) -> str:
    if report_file is None:
        return ""
    return langsmith_release_readiness_command(str(report_file))


def int_mapping_value(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    mapping = cast(Mapping[object, object], value)
    return {
        key: item
        for key, item in mapping.items()
        if isinstance(key, str) and isinstance(item, int) and not isinstance(item, bool)
    }


def int_value(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def positive_int_value(value: object) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return None
    return value


def non_negative_int_value(value: object) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return value


def optional_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    mapping = cast(Mapping[object, object], value)
    return {key: item for key, item in mapping.items() if isinstance(key, str)}


def memory_status_count_mapping_valid(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    mapping = cast(Mapping[object, object], value)
    return all(
        isinstance(key, str)
        and key in ALLOWED_MEMORY_STATUS_COUNT_LABELS
        and isinstance(item, int)
        and not isinstance(item, bool)
        and item >= 0
        for key, item in mapping.items()
    )


def string_mapping_value(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    mapping = cast(Mapping[object, object], value)
    return {
        key: item
        for key, item in mapping.items()
        if isinstance(key, str) and key.strip() and isinstance(item, str) and item.strip()
    }


def normalized_readiness_report_names(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        name = value.strip()
        if not name or name in seen:
            continue
        result.append(name)
        seen.add(name)
    return result


def parse_readiness_report_specs(values: Sequence[str]) -> dict[str, str]:
    reports: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--readiness-report must use name=path")
        name, path = value.split("=", 1)
        clean_name = name.strip()
        clean_path = path.strip()
        if not clean_name or not clean_path:
            raise ValueError("--readiness-report must use name=path")
        if clean_name in reports:
            raise ValueError(f"duplicate --readiness-report name: {clean_name}")
        reports[clean_name] = clean_path
    return reports


def readiness_reports_for_required_reports(
    *,
    required_reports: Sequence[str],
    explicit_reports: Mapping[str, str],
    report_file: Path | None,
) -> dict[str, str]:
    reports: dict[str, str] = {}
    for report_name in required_reports:
        explicit_path = explicit_reports.get(report_name)
        if explicit_path:
            reports[report_name] = explicit_path
        elif report_name == "langsmith_eval_sync" and report_file is not None:
            reports[report_name] = str(report_file)
        elif report_name == "hardening_suite":
            reports[report_name] = HARDENING_SUITE_REPORT_FILE
    missing_reports = [
        report_name for report_name in required_reports if report_name not in reports
    ]
    if missing_reports:
        missing = ", ".join(missing_reports)
        raise ValueError(f"missing --readiness-report for required report(s): {missing}")
    return reports


def optional_suite_context_manifest_diagnostics(
    *,
    suite: AgentEvalRegressionSuite,
    cases: Sequence[AgentEvalCaseRecord],
) -> dict[str, object]:
    diagnostics_items: list[Mapping[str, object]] = []
    for case in cases:
        run = suite.find_run_for_case(case.id)
        if run is None or not run.context_manifest_diagnostics:
            continue
        diagnostics_items.append(run.context_manifest_diagnostics)
    if not diagnostics_items:
        return {}

    memory_status_counts: Counter[str] = Counter()
    skipped_memory_status_counts: Counter[str] = Counter()
    findings: list[dict[str, object]] = []
    citation_count = 0
    chunk_count = 0
    cited_chunk_count = 0
    uncited_chunk_count = 0
    rag_grounding_policy: dict[str, object] = {}
    citation_workflow_eval_case_ids: list[str] = []
    citation_workflow_tags: list[str] = []
    passed = True
    for diagnostics in diagnostics_items:
        if diagnostics.get("ok") is not True or diagnostics.get("status") != "passed":
            passed = False
        memory_status_counts.update(int_mapping_value(diagnostics.get("memoryStatusCounts", {})))
        skipped_memory_status_counts.update(
            int_mapping_value(diagnostics.get("skippedMemoryStatusCounts", {}))
        )
        findings.extend(context_manifest_finding_values(diagnostics.get("findings", ())))
        citation_count += int_value(diagnostics.get("citationCount"))
        chunk_count += int_value(diagnostics.get("chunkCount"))
        cited_chunk_count += int_value(diagnostics.get("citedChunkCount"))
        uncited_chunk_count += int_value(diagnostics.get("uncitedChunkCount"))
        policy = optional_mapping(diagnostics.get("ragGroundingPolicy"))
        if policy and not rag_grounding_policy:
            rag_grounding_policy = dict(policy)
        elif policy != rag_grounding_policy:
            passed = False
        for citation in context_diagnostics_citation_items(diagnostics):
            append_unique_string(
                citation_workflow_eval_case_ids,
                citation.get("evalCaseId"),
            )
            for tag in string_list_value(citation.get("workflowTags", ())):
                append_unique_string(citation_workflow_tags, tag)
    if rag_grounding_policy and (
        cited_chunk_count + uncited_chunk_count != chunk_count
        or (chunk_count > 0 and citation_count <= 0)
    ):
        passed = False

    context_manifest_diagnostics: dict[str, object] = {
        "ok": passed,
        "status": "passed" if passed else "failed",
        "memoryStatusCounts": dict(sorted(memory_status_counts.items())),
        "skippedMemoryStatusCounts": dict(sorted(skipped_memory_status_counts.items())),
    }
    if findings:
        context_manifest_diagnostics["findings"] = findings
    if rag_grounding_policy:
        context_manifest_diagnostics.update(
            {
                "ragGroundingPolicy": rag_grounding_policy,
                "citationCount": citation_count,
                "chunkCount": chunk_count,
                "citedChunkCount": cited_chunk_count,
                "uncitedChunkCount": uncited_chunk_count,
            }
        )
    if citation_workflow_eval_case_ids:
        context_manifest_diagnostics["citationWorkflowEvalCaseIds"] = (
            citation_workflow_eval_case_ids
        )
    if citation_workflow_tags:
        context_manifest_diagnostics["citationWorkflowTags"] = citation_workflow_tags
    return {"contextManifestDiagnostics": context_manifest_diagnostics}


def context_diagnostics_citation_items(
    diagnostics: Mapping[str, object],
) -> list[Mapping[str, object]]:
    citations: list[Mapping[str, object]] = []
    citations.extend(mapping_items(diagnostics.get("citations", ())))
    metadata = diagnostics.get("metadata")
    if isinstance(metadata, Mapping):
        citations.extend(mapping_items(cast(Mapping[str, object], metadata).get("citations", ())))
    for section in mapping_items(diagnostics.get("sections", ())):
        section_metadata = section.get("metadata")
        if isinstance(section_metadata, Mapping):
            citations.extend(
                mapping_items(cast(Mapping[str, object], section_metadata).get("citations", ()))
            )
    return citations


def mapping_items(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    items: list[Mapping[str, object]] = []
    for item in cast(Sequence[object], value):
        if isinstance(item, Mapping):
            items.append(cast(Mapping[str, object], item))
    return items


def append_unique_string(items: list[str], value: object) -> None:
    if isinstance(value, str) and value and value not in items:
        items.append(value)


def context_manifest_finding_values(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    findings: list[dict[str, object]] = []
    for item in cast(Sequence[object], value):
        if not isinstance(item, Mapping):
            continue
        finding: dict[str, object] = {}
        for key, entry in cast(Mapping[object, object], item).items():
            if not isinstance(key, str) or not key.strip():
                continue
            if isinstance(entry, str | int | bool) or entry is None:
                finding[key.strip()] = entry
        if isinstance(finding.get("code"), str) and str(finding["code"]).strip():
            findings.append(finding)
    return findings


def langsmith_context_manifest_diagnostics_failed(diagnostics: Mapping[str, object]) -> bool:
    required_fields = {
        "ok",
        "status",
        "ragGroundingPolicy",
        "citationCount",
        "chunkCount",
        "citedChunkCount",
        "uncitedChunkCount",
        "memoryStatusCounts",
        "skippedMemoryStatusCounts",
    }
    allowed_fields = required_fields | {
        "citationWorkflowEvalCaseIds",
        "citationWorkflowTags",
        "findings",
    }
    if not required_fields.issubset(diagnostics) or set(diagnostics) - allowed_fields:
        return True
    for field_name in ("citationWorkflowEvalCaseIds", "citationWorkflowTags"):
        values = diagnostics.get(field_name)
        if values is None:
            continue
        if not isinstance(values, Sequence) or isinstance(values, str | bytes):
            return True
        if not all(isinstance(value, str) and value for value in cast(Sequence[object], values)):
            return True
    if diagnostics.get("ok") is not True or diagnostics.get("status") != "passed":
        return True
    if diagnostics.get("findings") is not None:
        return True
    skipped_memory_status_counts = int_mapping_value(
        diagnostics.get("skippedMemoryStatusCounts", {})
    )
    if not memory_status_count_mapping_valid(
        diagnostics.get("memoryStatusCounts")
    ) or not memory_status_count_mapping_valid(diagnostics.get("skippedMemoryStatusCounts")):
        return True
    if skipped_memory_status_counts.get("active", 0) != 0:
        return True
    return langsmith_rag_context_diagnostics_failed(diagnostics)


def langsmith_rag_context_diagnostics_failed(diagnostics: Mapping[str, object]) -> bool:
    rag_policy = optional_mapping(diagnostics.get("ragGroundingPolicy"))
    if set(rag_policy) != {
        "citationTracking",
        "uncitedChunksTracked",
        "aclEvidence",
        "rawAclMetadataVisible",
    }:
        return True
    if (
        rag_policy.get("citationTracking") != "required"
        or rag_policy.get("uncitedChunksTracked") is not True
        or rag_policy.get("aclEvidence") != "acl_hash_only"
        or rag_policy.get("rawAclMetadataVisible") is not False
    ):
        return True
    citation_count = positive_int_value(diagnostics.get("citationCount"))
    chunk_count = positive_int_value(diagnostics.get("chunkCount"))
    cited_chunk_count = positive_int_value(diagnostics.get("citedChunkCount"))
    uncited_chunk_count = non_negative_int_value(diagnostics.get("uncitedChunkCount"))
    if (
        citation_count is None
        or chunk_count is None
        or cited_chunk_count is None
        or uncited_chunk_count is None
    ):
        return True
    return cited_chunk_count + uncited_chunk_count != chunk_count


def langsmith_source_run_provenance_missing(
    *,
    enabled_cases: int,
    case_ids: Sequence[str],
    source_run_ids: Sequence[str],
    case_source_run_ids: Mapping[str, str],
) -> bool:
    if enabled_cases <= 0:
        return True
    if len(case_ids) != enabled_cases or len(set(case_ids)) != enabled_cases:
        return True
    if len(source_run_ids) != enabled_cases or len(set(source_run_ids)) != enabled_cases:
        return True
    if set(case_source_run_ids) != set(case_ids):
        return True
    return set(case_source_run_ids.values()) != set(source_run_ids)


def optional_feedback_promotion_summary(
    examples: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, object]]:
    summary = feedback_promotion_summary_from_examples(examples)
    return {"feedbackPromotion": summary} if summary else {}


def optional_feedback_review_queue_summary(
    examples: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, object]]:
    summary = feedback_review_queue_summary_from_examples(examples)
    return {"feedbackReviewQueue": summary} if summary else {}


def feedback_promotion_summary_from_examples(
    examples: Sequence[Mapping[str, Any]],
) -> dict[str, object]:
    case_ids: list[str] = []
    feedback_ids: list[str] = []
    rating_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    workflow_tag_counts: Counter[str] = Counter()
    expected_citation_counts: Counter[str] = Counter()
    seen_case_ids: set[str] = set()
    seen_feedback_ids: set[str] = set()
    for example in examples:
        metadata = example.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        metadata_mapping = cast(Mapping[str, object], metadata)
        case_id = metadata_mapping.get("reactorCaseId")
        if not isinstance(case_id, str) or not case_id.strip():
            continue
        tags = string_list_value(metadata_mapping.get("tags", ()))
        example_feedback_ids = feedback_ids_from_tags(tags)
        if not example_feedback_ids:
            continue
        if case_id not in seen_case_ids:
            seen_case_ids.add(case_id)
            case_ids.append(case_id)
        for feedback_id in example_feedback_ids:
            if feedback_id not in seen_feedback_ids:
                seen_feedback_ids.add(feedback_id)
                feedback_ids.append(feedback_id)
        for rating in feedback_ratings_from_tags(tags):
            rating_counts[rating] += 1
        for source in feedback_sources_from_tags(tags):
            source_counts[source] += 1
        for tag in workflow_tags_from_feedback_case_tags(tags):
            workflow_tag_counts[tag] += 1
        expected_citation_ids = {
            *expected_citation_ids_from_tags(tags),
            *expected_citation_ids_from_example_outputs(example.get("outputs")),
        }
        for citation_id in expected_citation_ids:
            expected_citation_counts[citation_id] += 1
    if not case_ids:
        return {}
    summary: dict[str, object] = {
        "caseIds": case_ids,
        "feedbackIds": feedback_ids,
        "feedbackReviewIds": feedback_ids,
        "feedbackRatingCounts": dict(sorted(rating_counts.items())),
    }
    if workflow_tag_counts:
        summary["workflowTagCounts"] = dict(sorted(workflow_tag_counts.items()))
    if expected_citation_counts:
        summary["expectedCitationCounts"] = dict(sorted(expected_citation_counts.items()))
    if source_counts:
        summary["feedbackSourceCounts"] = dict(sorted(source_counts.items()))
    bulk_review_action = langsmith_feedback_bulk_review_action(summary)
    if bulk_review_action:
        summary["bulkReviewAction"] = bulk_review_action
    return summary


def feedback_review_queue_summary_from_examples(
    examples: Sequence[Mapping[str, Any]],
) -> dict[str, object]:
    case_ids: list[str] = []
    seen_case_ids: set[str] = set()
    rating_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    workflow_tag_counts: Counter[str] = Counter()
    expected_citation_counts: Counter[str] = Counter()
    for example in examples:
        metadata = example.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        metadata_mapping = cast(Mapping[str, object], metadata)
        case_id = metadata_mapping.get("reactorCaseId")
        if not isinstance(case_id, str) or not case_id.strip():
            continue
        tags = string_list_value(metadata_mapping.get("tags", ()))
        if feedback_ids_from_tags(tags):
            continue
        ratings = feedback_ratings_from_tags(tags)
        if not ratings:
            continue
        if case_id not in seen_case_ids:
            seen_case_ids.add(case_id)
            case_ids.append(case_id)
        for rating in ratings:
            rating_counts[rating] += 1
        for source in feedback_sources_from_tags(tags):
            source_counts[source] += 1
        for tag in workflow_tags_from_feedback_case_tags(tags):
            workflow_tag_counts[tag] += 1
        expected_citation_ids = {
            *expected_citation_ids_from_tags(tags),
            *expected_citation_ids_from_example_outputs(example.get("outputs")),
        }
        for citation_id in expected_citation_ids:
            expected_citation_counts[citation_id] += 1
    if not case_ids:
        return {}
    candidate_workflow_tag = candidate_workflow_tag_from_case_ids(case_ids)
    if candidate_workflow_tag:
        workflow_tag_counts[candidate_workflow_tag] = max(
            workflow_tag_counts[candidate_workflow_tag],
            len(case_ids),
        )
    else:
        candidate_tags = sorted(
            tag
            for tag, count in workflow_tag_counts.items()
            if tag.startswith("rag-candidate:") and valid_candidate_workflow_tag(tag) and count > 0
        )
        if len(candidate_tags) == 1:
            candidate_workflow_tag = candidate_tags[0]
    summary: dict[str, object] = {
        "caseIds": case_ids,
        "feedbackRatingCounts": dict(sorted(rating_counts.items())),
    }
    if candidate_workflow_tag:
        summary["candidateTag"] = candidate_workflow_tag
    if workflow_tag_counts:
        summary["workflowTagCounts"] = dict(sorted(workflow_tag_counts.items()))
    if expected_citation_counts:
        summary["expectedCitationCounts"] = dict(sorted(expected_citation_counts.items()))
    if source_counts:
        summary["feedbackSourceCounts"] = dict(sorted(source_counts.items()))
    review_action = feedback_review_queue_action(summary)
    if review_action:
        summary["reviewAction"] = review_action
    export_action = feedback_review_queue_export_action(summary)
    if export_action:
        summary["exportAction"] = export_action
    candidate_review_action = feedback_review_queue_candidate_review_action(summary)
    if candidate_review_action:
        summary["candidateReviewAction"] = candidate_review_action
    bulk_review_action = feedback_review_queue_bulk_review_action(summary)
    if bulk_review_action:
        summary["bulkReviewAction"] = bulk_review_action
    memory_lifecycle_action = feedback_review_queue_memory_lifecycle_action(summary)
    if memory_lifecycle_action:
        summary["memoryLifecycleAction"] = memory_lifecycle_action
    return summary


def workflow_tags_from_feedback_case_tags(tags: Sequence[str]) -> list[str]:
    return [
        tag
        for tag in tags
        if tag.strip()
        and not tag.startswith("feedback:")
        and not tag.startswith("feedback-rating:")
        and not tag.startswith("feedback-source:")
        and tag not in {"exported-from-cli", "regression"}
    ]


def safe_feedback_workflow_tag_counts(value: object) -> dict[str, int]:
    counts = int_mapping_value(value)
    return {
        tag: count
        for tag, count in counts.items()
        if not tag.startswith("expected-citation:")
        or is_citation_safe_id(tag.removeprefix("expected-citation:").strip())
    }


def expected_citation_ids_from_tags(tags: Sequence[str]) -> list[str]:
    return [
        citation_id
        for tag in tags
        if tag.startswith("expected-citation:")
        and (citation_id := tag.removeprefix("expected-citation:").strip())
        and is_citation_safe_id(citation_id)
    ]


def expected_citation_ids_from_example_outputs(outputs: object) -> list[str]:
    if not isinstance(outputs, Mapping):
        return []
    expected_answers = string_list_value(
        cast(Mapping[object, object], outputs).get("expected_answer_contains", ())
    )
    return [
        citation_id
        for answer in expected_answers
        if is_bracketed_citation_marker(answer)
        and (citation_id := answer.strip()[1:-1].strip())
        and is_citation_safe_id(citation_id)
    ]


def feedback_ids_from_tags(tags: Sequence[str]) -> list[str]:
    return [
        feedback_id
        for tag in tags
        if tag.startswith("feedback:") and (feedback_id := tag.removeprefix("feedback:").strip())
    ]


def feedback_ratings_from_tags(tags: Sequence[str]) -> list[str]:
    return [
        rating
        for tag in tags
        if tag.startswith("feedback-rating:")
        and (rating := tag.removeprefix("feedback-rating:").strip())
    ]


def feedback_sources_from_tags(tags: Sequence[str]) -> list[str]:
    return [
        source
        for tag in tags
        if tag.startswith("feedback-source:")
        and (source := tag.removeprefix("feedback-source:").strip())
    ]


def feedback_promotion_summary_value(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    mapping = cast(Mapping[object, object], value)
    case_ids = string_list_value(mapping.get("caseIds", ()))
    feedback_ids = string_list_value(mapping.get("feedbackIds", ()))
    if not case_ids or not feedback_ids:
        return {}
    summary: dict[str, object] = {
        "caseIds": case_ids,
        "feedbackIds": feedback_ids,
        "feedbackReviewIds": string_list_value(mapping.get("feedbackReviewIds", feedback_ids)),
        "feedbackRatingCounts": int_mapping_value(mapping.get("feedbackRatingCounts", {})),
    }
    workflow_tag_counts = safe_feedback_workflow_tag_counts(mapping.get("workflowTagCounts", {}))
    if workflow_tag_counts:
        summary["workflowTagCounts"] = workflow_tag_counts
    expected_citation_counts = {
        citation_id: count
        for citation_id, count in int_mapping_value(
            mapping.get("expectedCitationCounts", {})
        ).items()
        if is_citation_safe_id(citation_id)
    }
    if expected_citation_counts:
        summary["expectedCitationCounts"] = expected_citation_counts
    source_counts = int_mapping_value(mapping.get("feedbackSourceCounts", {}))
    if source_counts:
        summary["feedbackSourceCounts"] = source_counts
    review_status = mapping.get("reviewStatus")
    if isinstance(review_status, str) and review_status.strip():
        summary["reviewStatus"] = review_status.strip()
    review_tags = string_list_value(mapping.get("reviewTags", ()))
    if review_tags:
        summary["reviewTags"] = review_tags
    review_note = mapping.get("reviewNote")
    if isinstance(review_note, str) and review_note.strip():
        summary["reviewNote"] = review_note.strip()
    release_readiness_command = mapping.get("releaseReadinessCommand")
    if isinstance(release_readiness_command, str) and release_readiness_command.strip():
        summary["releaseReadinessCommand"] = release_readiness_command.strip()
    if not feedback_promotion_review_closed(summary):
        review_actions = langsmith_feedback_review_actions(summary)
        if len(review_actions) == 1:
            summary["reviewAction"] = review_actions[0]
        elif review_actions:
            summary["reviewActions"] = review_actions
        bulk_review_action = langsmith_feedback_bulk_review_action(summary)
        if bulk_review_action:
            summary["bulkReviewAction"] = bulk_review_action
    return summary


def feedback_promotion_review_closed(feedback_promotion: Mapping[str, object]) -> bool:
    return feedback_review_closed(feedback_promotion)


def feedback_promotion_review_closure_command_args(
    feedback_promotion: Mapping[str, object],
) -> list[str]:
    if not feedback_promotion_review_closed(feedback_promotion):
        return []
    review_status = feedback_promotion.get("reviewStatus")
    review_note = feedback_promotion.get("reviewNote")
    args = (
        [f"--feedback-review-status {quote(review_status.strip())}"]
        if isinstance(review_status, str)
        else []
    )
    args.extend(
        f"--feedback-review-tag {quote(tag)}"
        for tag in string_list_value(feedback_promotion.get("reviewTags", ()))
    )
    if isinstance(review_note, str) and review_note.strip():
        args.append(f"--feedback-review-note {quote(review_note.strip())}")
    return args


def feedback_review_queue_summary_value(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    mapping = cast(Mapping[object, object], value)
    case_ids = string_list_value(mapping.get("caseIds", ()))
    rating_counts = int_mapping_value(mapping.get("feedbackRatingCounts", {}))
    workflow_tag_counts = safe_feedback_workflow_tag_counts(mapping.get("workflowTagCounts", {}))
    source_counts = int_mapping_value(mapping.get("feedbackSourceCounts", {}))
    if not case_ids or not rating_counts or not workflow_tag_counts:
        return {}
    summary: dict[str, object] = {
        "caseIds": case_ids,
        "feedbackRatingCounts": rating_counts,
        "workflowTagCounts": workflow_tag_counts,
    }
    candidate_tag = mapping.get("candidateTag")
    if isinstance(candidate_tag, str) and candidate_tag.strip():
        summary["candidateTag"] = candidate_tag.strip()
    else:
        candidate_workflow_tag = candidate_workflow_tag_from_case_ids(case_ids)
        if candidate_workflow_tag:
            summary["candidateTag"] = candidate_workflow_tag
    if source_counts:
        summary["feedbackSourceCounts"] = source_counts
    expected_citation_counts = {
        citation_id: count
        for citation_id, count in int_mapping_value(
            mapping.get("expectedCitationCounts", {})
        ).items()
        if is_citation_safe_id(citation_id)
    }
    if expected_citation_counts:
        summary["expectedCitationCounts"] = expected_citation_counts
    review_status = mapping.get("reviewStatus")
    if isinstance(review_status, str) and review_status.strip():
        summary["reviewStatus"] = review_status.strip()
    review_tags = string_list_value(mapping.get("reviewTags", ()))
    if review_tags:
        summary["reviewTags"] = review_tags
    review_note = mapping.get("reviewNote")
    if isinstance(review_note, str) and review_note.strip():
        summary["reviewNote"] = review_note.strip()
    if not feedback_promotion_review_closed(summary):
        review_action = feedback_review_queue_action(summary)
        if review_action:
            summary["reviewAction"] = review_action
        export_action = feedback_review_queue_export_action(summary)
        if export_action:
            summary["exportAction"] = export_action
        candidate_review_action = feedback_review_queue_candidate_review_action(summary)
        if candidate_review_action:
            summary["candidateReviewAction"] = candidate_review_action
        bulk_review_action = feedback_review_queue_bulk_review_action(summary)
        if bulk_review_action:
            summary["bulkReviewAction"] = bulk_review_action
        memory_lifecycle_action = feedback_review_queue_memory_lifecycle_action(summary)
        if memory_lifecycle_action:
            summary["memoryLifecycleAction"] = memory_lifecycle_action
    return summary


def optional_feedback_promotion_coverage(
    *,
    suite: AgentEvalRegressionSuite,
    cases: Sequence[AgentEvalCaseRecord],
) -> dict[str, object]:
    promoted_cases = tuple(
        case
        for case in cases
        if feedback_ids_from_tags(case.tags) or feedback_ratings_from_tags(case.tags)
    )
    if not promoted_cases:
        return {}
    runs = [suite.find_run_for_case(case.id) for case in promoted_cases]
    coverage: dict[str, object] = {
        "sourceRunIdPresent": all(
            case.source_run_id is not None and bool(case.source_run_id.strip())
            for case in promoted_cases
        ),
        "runFixturePresent": all(run is not None for run in runs),
        "runFixtureMatchedCase": all(
            run is not None and run.run_id == case.source_run_id
            for case, run in zip(promoted_cases, runs, strict=True)
        ),
        "runContextDiagnosticsPresent": all(
            run is not None and bool(run.context_manifest_diagnostics) for run in runs
        ),
        "requiredSourceRunId": True,
        "requiredRunFile": True,
        "requiredContextDiagnostics": True,
    }
    if any(feedback_case_requires_citation_markers(case) for case in promoted_cases):
        coverage.update(
            {
                "citationMarkersRequired": True,
                "citationMarkersPresent": all(
                    feedback_case_has_citation_markers(case) for case in promoted_cases
                ),
                "runCitationMarkersPresent": all(
                    run is not None
                    and feedback_run_has_citation_markers(case=case, final_answer=run.final_answer)
                    for case, run in zip(promoted_cases, runs, strict=True)
                ),
                "citationFailureAllowsMissingRunCitation": all(
                    feedback_case_allows_missing_run_citation_markers(case)
                    for case in promoted_cases
                    if feedback_case_requires_citation_markers(case)
                ),
            }
        )
        if any(feedback_run_has_context_citation_evidence(run) for run in runs):
            coverage.update(
                {
                    "contextCitationEvalCaseIdMatched": all(
                        run is not None
                        and run.eval_case_id == case.id
                        and run.run_id == case.source_run_id
                        and feedback_run_has_context_citation_evidence(run)
                        for case, run in zip(promoted_cases, runs, strict=True)
                        if feedback_case_requires_citation_markers(case)
                    ),
                    "contextCitationWorkflowTagMatched": all(
                        feedback_case_has_context_citation_workflow(case)
                        and run is not None
                        and feedback_run_has_context_citation_evidence(run)
                        for case, run in zip(promoted_cases, runs, strict=True)
                        if feedback_case_requires_citation_markers(case)
                    ),
                }
            )
    return {"promotionCoverage": coverage}


def promotion_coverage_summary_value(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    mapping = cast(Mapping[object, object], value)
    summary = {key: value for key, value in mapping.items() if isinstance(key, str)}
    if not summary or not all(isinstance(item, bool) for item in summary.values()):
        return {}
    return summary


def feedback_case_requires_citation_markers(case: AgentEvalCaseRecord) -> bool:
    return "documents-ask" in set(case.tags)


def feedback_case_has_citation_markers(case: AgentEvalCaseRecord) -> bool:
    return any(is_bracketed_citation_marker(item) for item in case.expected_answer_contains)


def feedback_case_allows_missing_run_citation_markers(case: AgentEvalCaseRecord) -> bool:
    return "citation-failure" in set(case.tags)


def feedback_case_has_context_citation_workflow(case: AgentEvalCaseRecord) -> bool:
    tags = set(case.tags)
    return {"documents-ask", "grounding", "rag"}.issubset(tags)


def feedback_run_has_context_citation_evidence(run: AgentEvalRunFixture | None) -> bool:
    if run is None:
        return False
    diagnostics = run.context_manifest_diagnostics
    return bool(diagnostics) and not langsmith_rag_context_diagnostics_failed(diagnostics)


def feedback_run_has_citation_markers(
    *,
    case: AgentEvalCaseRecord,
    final_answer: str,
) -> bool:
    if not feedback_case_requires_citation_markers(case):
        return False
    citation_markers = [
        marker for marker in case.expected_answer_contains if is_bracketed_citation_marker(marker)
    ]
    if not citation_markers:
        return False
    return all(marker in final_answer for marker in citation_markers)


def is_bracketed_citation_marker(value: str) -> bool:
    stripped = value.strip()
    return (
        len(stripped) > 2
        and stripped.startswith("[")
        and stripped.endswith("]")
        and stripped.lower() not in CITATION_MARKER_PLACEHOLDERS
    )


def langsmith_feedback_review_actions(feedback_promotion: Mapping[str, object]) -> list[str]:
    feedback_ids = string_list_value(feedback_promotion.get("feedbackIds", ()))
    workflow_action = langsmith_feedback_workflow_review_action(feedback_promotion, feedback_ids)
    if workflow_action:
        return [workflow_action]
    return [
        f"reactor-admin feedback --feedback-id {quote(feedback_id)} --output table"
        for feedback_id in feedback_ids
    ]


def langsmith_feedback_bulk_review_action(feedback_promotion: Mapping[str, object]) -> str:
    feedback_ids = string_list_value(
        feedback_promotion.get(
            "feedbackReviewIds",
            feedback_promotion.get("feedbackIds", ()),
        )
    )
    if not feedback_ids:
        return ""
    case_ids = string_list_value(feedback_promotion.get("caseIds", ()))
    required_workflow_count = max(len(case_ids), len(feedback_ids))
    workflow_counts = int_mapping_value(feedback_promotion.get("workflowTagCounts", {}))
    candidate_tag = candidate_workflow_tag_from_case_ids(case_ids)
    if not candidate_tag:
        candidate_tags = sorted(
            tag
            for tag, count in workflow_counts.items()
            if tag.startswith("rag-candidate:") and valid_candidate_workflow_tag(tag) and count > 0
        )
        candidate_tag = candidate_tags[0] if len(candidate_tags) == 1 else ""
    if candidate_tag:
        source_counts = int_mapping_value(feedback_promotion.get("feedbackSourceCounts", {}))
        sources = [
            source.strip()
            for source, count in sorted(source_counts.items())
            if source.strip() and count > 0
        ]
        source = sources[0] if len(sources) == 1 else ""
        return rag_candidate_feedback_bulk_review_action(candidate_tag, source=source)
    common_workflow_tags = [
        tag
        for tag, count in sorted(workflow_counts.items())
        if tag.strip() and count == required_workflow_count
    ]
    expected_citation_tags = [
        f"expected-citation:{citation_id}"
        for citation_id, count in sorted(
            int_mapping_value(feedback_promotion.get("expectedCitationCounts", {})).items()
        )
        if count == required_workflow_count and is_citation_safe_id(citation_id)
    ]
    review_tags = list(
        dict.fromkeys(["promoted", "langsmith", *expected_citation_tags, *common_workflow_tags])
    )
    tag_args = " ".join(f"--tag {quote(tag)}" for tag in review_tags)
    id_args = " ".join(quote(feedback_id) for feedback_id in feedback_ids)
    return (
        f"reactor-admin feedback-bulk-review {id_args} --status done {tag_args} "
        f"--note {quote(RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE)} --output table"
    )


def langsmith_feedback_workflow_review_action(
    feedback_promotion: Mapping[str, object],
    feedback_ids: Sequence[str],
) -> str:
    if len(feedback_ids) <= 1:
        return ""
    workflow_counts = int_mapping_value(feedback_promotion.get("workflowTagCounts", {}))
    workflow_tag = preferred_feedback_workflow_tag(
        workflow_counts,
        required_count=len(feedback_ids),
    )
    if not workflow_tag:
        return ""
    rating_counts = int_mapping_value(feedback_promotion.get("feedbackRatingCounts", {}))
    rating = next(
        (
            rating.strip()
            for rating, count in sorted(rating_counts.items())
            if rating.strip() and count > 0
        ),
        "",
    )
    rating_arg = f"--rating {quote(rating)} " if rating else ""
    source_arg = feedback_source_filter_arg(
        feedback_promotion.get("feedbackSourceCounts", {}),
    )
    collection_tag_arg = (
        "--tag collection:rag-ingestion-candidate "
        if workflow_tag.startswith("rag-candidate:")
        else ""
    )
    return (
        f"reactor-admin feedback {rating_arg}"
        f"{source_arg}"
        f"--review-status inbox {collection_tag_arg}"
        f"--tag {quote(workflow_tag)} --limit 10 --output table"
    )


def feedback_review_queue_action(summary: Mapping[str, object]) -> str:
    case_ids = string_list_value(summary.get("caseIds", ()))
    if not case_ids:
        return ""
    workflow_counts = int_mapping_value(summary.get("workflowTagCounts", {}))
    workflow_tag = preferred_feedback_workflow_tag(
        workflow_counts,
        required_count=len(case_ids),
    )
    if not workflow_tag.startswith("rag-candidate:"):
        workflow_tag = candidate_workflow_tag_from_case_ids(case_ids) or workflow_tag
    if not workflow_tag:
        return ""
    rating_counts = int_mapping_value(summary.get("feedbackRatingCounts", {}))
    rating = next(
        (
            rating.strip()
            for rating, count in sorted(rating_counts.items())
            if rating.strip() and count > 0
        ),
        "",
    )
    if not rating:
        return ""
    source_arg = feedback_source_filter_arg(summary.get("feedbackSourceCounts", {}))
    case_id_arg = f"--case-id {quote(case_ids[0])} " if len(case_ids) == 1 else ""
    collection_tag_arg = (
        "--tag collection:rag-ingestion-candidate "
        if workflow_tag.startswith("rag-candidate:")
        else ""
    )
    return (
        f"reactor-admin feedback --rating {quote(rating)} "
        f"{source_arg}"
        f"--review-status inbox {case_id_arg}{collection_tag_arg}"
        f"--tag {quote(workflow_tag)} "
        "--limit 10 --output table"
    )


def feedback_review_queue_export_action(summary: Mapping[str, object]) -> str:
    review_action = feedback_review_queue_action(summary)
    if not review_action:
        return ""
    export_action = review_action.replace(
        "reactor-admin feedback ",
        "reactor-admin feedback-export ",
        1,
    ).replace("--output table", "--output json")
    return export_action


def feedback_review_queue_memory_lifecycle_action(summary: Mapping[str, object]) -> str:
    workflow_counts = int_mapping_value(summary.get("workflowTagCounts", {}))
    return MEMORY_LIFECYCLE_ACTION if workflow_counts.get("memory", 0) > 0 else ""


def feedback_review_queue_candidate_review_action(summary: Mapping[str, object]) -> str:
    case_ids = string_list_value(summary.get("caseIds", ()))
    candidate_tag = candidate_workflow_tag_from_case_ids(case_ids)
    if candidate_tag:
        return rag_candidate_review_action(candidate_tag)
    workflow_counts = int_mapping_value(summary.get("workflowTagCounts", {}))
    candidate_tags = sorted(
        tag
        for tag, count in workflow_counts.items()
        if tag.startswith("rag-candidate:") and valid_candidate_workflow_tag(tag) and count > 0
    )
    if len(candidate_tags) == 1:
        return rag_candidate_review_action(candidate_tags[0])
    has_candidate_tag = bool(candidate_tags)
    return (
        RAG_CANDIDATE_REVIEW_ACTION
        if workflow_counts.get("collection:rag-ingestion-candidate", 0) > 0 or has_candidate_tag
        else ""
    )


def feedback_review_queue_bulk_review_action(summary: Mapping[str, object]) -> str:
    candidate_tag_value = summary.get("candidateTag")
    candidate_tag = (
        candidate_tag_value.strip()
        if isinstance(candidate_tag_value, str) and candidate_tag_value.strip()
        else candidate_workflow_tag_from_case_ids(string_list_value(summary.get("caseIds", ())))
    )
    if not valid_candidate_workflow_tag(candidate_tag):
        workflow_counts = int_mapping_value(summary.get("workflowTagCounts", {}))
        candidate_tags = sorted(
            tag
            for tag, count in workflow_counts.items()
            if tag.startswith("rag-candidate:") and valid_candidate_workflow_tag(tag) and count > 0
        )
        candidate_tag = candidate_tags[0] if len(candidate_tags) == 1 else ""
    if not valid_candidate_workflow_tag(candidate_tag):
        return ""
    source_counts = int_mapping_value(summary.get("feedbackSourceCounts", {}))
    sources = [
        source.strip()
        for source, count in sorted(source_counts.items())
        if source.strip() and count > 0
    ]
    source = sources[0] if len(sources) == 1 else ""
    expected_citation_tags = [
        f"expected-citation:{citation_id}"
        for citation_id, count in sorted(
            int_mapping_value(summary.get("expectedCitationCounts", {})).items()
        )
        if count > 0 and is_citation_safe_id(citation_id)
    ]
    return rag_candidate_feedback_bulk_review_action(
        candidate_tag,
        source=source,
        extra_review_tags=expected_citation_tags,
    )


def candidate_workflow_tag_from_case_ids(case_ids: Sequence[str]) -> str:
    candidate_ids: list[str] = []
    for case_id in case_ids:
        stripped = case_id.strip()
        candidate_id = ""
        for prefix in ("case-rag-candidate-", "case_rag_candidate_"):
            if stripped.startswith(prefix):
                candidate_id = stripped.removeprefix(prefix).strip()
                break
        if not candidate_id or command_slug(candidate_id) != candidate_id:
            return ""
        candidate_ids.append(candidate_id)
    if not candidate_ids or len(set(candidate_ids)) != 1:
        return ""
    return f"rag-candidate:{candidate_ids[0]}"


def preferred_feedback_workflow_tag(
    workflow_counts: Mapping[str, int],
    *,
    required_count: int,
) -> str:
    eligible = sorted(
        tag.strip()
        for tag, count in workflow_counts.items()
        if tag.strip() and count >= required_count and not tag.startswith("expected-citation:")
    )
    for prefix in ("rag-candidate:",):
        for tag in eligible:
            if tag.startswith(prefix) and valid_candidate_workflow_tag(tag):
                return tag
    if "memory" in eligible:
        return "memory"
    for tag in eligible:
        if tag.startswith("collection:"):
            return tag
    if "grounding" in eligible:
        return "grounding"
    if "rag" in eligible:
        return "rag"
    return eligible[0] if eligible else ""


def feedback_source_filter_arg(source_counts: object) -> str:
    sources = [
        source
        for source, count in int_mapping_value(source_counts).items()
        if source.strip() and count > 0
    ]
    return f"--source {quote(sources[0])} " if len(sources) == 1 else ""


def valid_candidate_workflow_tag(tag: str) -> bool:
    prefix = "rag-candidate:"
    if not tag.startswith(prefix):
        return False
    candidate_slug = tag.removeprefix(prefix).strip()
    return is_command_slug(candidate_slug)


def langsmith_feedback_review_action(feedback_promotion: Mapping[str, object]) -> str:
    review_actions = langsmith_feedback_review_actions(feedback_promotion)
    if not review_actions:
        return ""
    if len(review_actions) == 1:
        return review_actions[0]
    rating_counts = int_mapping_value(feedback_promotion.get("feedbackRatingCounts", {}))
    for rating, count in sorted(rating_counts.items()):
        if count > 0 and rating.strip():
            return (
                f"reactor-admin feedback --rating {quote(rating.strip())} --limit 10 --output table"
            )
    return "reactor-admin feedback --limit 10 --output table"


def langsmith_dataset_metadata(*, source_suite: str | None = None) -> dict[str, object]:
    metadata: dict[str, object] = {
        "source": "reactor",
        "kind": "agent_eval",
        "dataType": LANGSMITH_EVAL_DATA_TYPE,
    }
    if source_suite is not None and source_suite.strip():
        metadata["sourceSuite"] = source_suite.strip()
    return metadata


def langsmith_eval_example_contract() -> dict[str, object]:
    return dict(LANGSMITH_EVAL_EXAMPLE_CONTRACT)


def langsmith_eval_sdk_contract() -> dict[str, object]:
    return dict(LANGSMITH_EVAL_SDK_CONTRACT)


def langsmith_eval_sync_release_gate(
    *,
    dry_run: bool,
    provenance_missing: bool = False,
    feedback_promotion_source_missing: bool = False,
    feedback_review_queue_source_missing: bool = False,
    feedback_review_queue_remediation_command: str = "",
    trace_grading_failed: bool = False,
    context_manifest_diagnostics_missing: bool = False,
    context_manifest_diagnostics_failed: bool = False,
) -> dict[str, object]:
    if (
        not dry_run
        and not provenance_missing
        and not feedback_promotion_source_missing
        and not feedback_review_queue_source_missing
        and not trace_grading_failed
        and not context_manifest_diagnostics_missing
        and not context_manifest_diagnostics_failed
    ):
        return {
            "status": "ready",
            "blocksReleaseReadiness": False,
            "reason": None,
            "requiredReport": "langsmith_eval_sync",
            "remediation": [],
        }
    if provenance_missing:
        return {
            "status": "blocked",
            "blocksReleaseReadiness": True,
            "reason": "missing_source_run_provenance",
            "requiredReport": "langsmith_eval_sync",
            "remediation": [
                "regenerate_langsmith_eval_sync_with_source_run_ids",
                "promote_eval_cases_with_source_run_id",
            ],
        }
    if feedback_promotion_source_missing:
        return {
            "status": "blocked",
            "blocksReleaseReadiness": True,
            "reason": "feedback_promotion_source_missing",
            "requiredReport": "langsmith_eval_sync",
            "remediation": [
                "rerun_reactor_langsmith_eval_sync_with_feedback_source_counts",
                "resubmit_feedback_with_source_metadata",
            ],
        }
    if feedback_review_queue_source_missing:
        gate: dict[str, object] = {
            "status": "blocked",
            "blocksReleaseReadiness": True,
            "reason": "feedback_review_queue_source_missing",
            "requiredReport": "langsmith_eval_sync",
            "remediation": [
                "rerun_reactor_langsmith_eval_sync_with_feedback_source_counts",
                "resubmit_feedback_with_source_metadata",
            ],
        }
        if feedback_review_queue_remediation_command.strip():
            gate["remediationCommand"] = feedback_review_queue_remediation_command.strip()
        return gate
    if not dry_run and trace_grading_failed:
        return {
            "status": "blocked",
            "blocksReleaseReadiness": True,
            "reason": "trace_grading_failed",
            "requiredReport": "langsmith_eval_sync",
            "remediation": [
                "fix_failing_regression_eval_cases",
                "rerun_reactor_langsmith_eval_sync",
            ],
        }
    if not dry_run and context_manifest_diagnostics_missing:
        return {
            "status": "blocked",
            "blocksReleaseReadiness": True,
            "reason": "missing_context_manifest_diagnostics",
            "requiredReport": "langsmith_eval_sync",
            "remediation": [
                "rerun_reactor_langsmith_eval_sync_with_context_manifest_diagnostics",
                "promote_eval_cases_with_run_context_manifest_diagnostics",
            ],
        }
    if not dry_run and context_manifest_diagnostics_failed:
        return {
            "status": "blocked",
            "blocksReleaseReadiness": True,
            "reason": "context_manifest_diagnostics_failed",
            "requiredReport": "langsmith_eval_sync",
            "remediation": [
                "fix_context_manifest_diagnostics_failures",
                "rerun_reactor_langsmith_eval_sync",
            ],
        }
    return {
        "status": "blocked",
        "blocksReleaseReadiness": True,
        "reason": "dry_run_only",
        "requiredReport": "langsmith_eval_sync",
        "remediation": [
            "run_reactor_langsmith_eval_sync_without_dry_run",
            "include_passed_langsmith_eval_sync_report_in_release_readiness",
        ],
    }


def langsmith_trace_grading_failed(trace_grading: Mapping[str, object] | None) -> bool:
    if trace_grading is None:
        return False
    failed = trace_grading.get("failed")
    return isinstance(failed, int) and not isinstance(failed, bool) and failed > 0


def trace_grading_summary(suite: AgentEvalRegressionSuite) -> dict[str, object]:
    grader = AgentTraceGrader()
    case_ids = [case.id for case in suite.enabled_cases]
    grades = [
        grader.grade(case, run)
        for case in suite.enabled_cases
        if (run := suite.find_run_for_case(case.id)) is not None
    ]
    summary: dict[str, object] = {
        "enabledCases": len(case_ids),
        "gradedRuns": len(grades),
        "passed": sum(1 for grade in grades if grade.passed),
        "failed": sum(1 for grade in grades if not grade.passed),
        "caseIds": case_ids,
        "grades": [trace_grade_payload(grade) for grade in grades],
    }
    missing_run_case_ids = [
        case.id for case in suite.enabled_cases if suite.find_run_for_case(case.id) is None
    ]
    if missing_run_case_ids:
        summary["missingRunCaseIds"] = missing_run_case_ids
    poisoning_safety = poisoning_safety_summary(grades)
    if poisoning_safety is not None:
        summary["poisoningSafety"] = poisoning_safety
    return summary


def trace_grade_payload(grade: AgentTraceGrade) -> dict[str, object]:
    return {
        "caseId": grade.case_id,
        "runId": grade.run_id,
        "passed": grade.passed,
        "score": grade.score,
        "dimensions": [
            {
                "name": dimension.name,
                "score": dimension.score,
                "evidence": dimension.evidence,
            }
            for dimension in grade.dimensions
        ],
    }


def poisoning_safety_summary(grades: Sequence[AgentTraceGrade]) -> dict[str, object] | None:
    for grade in grades:
        for dimension in grade.dimensions:
            if dimension.name != "safety":
                continue
            evidence = dimension.evidence
            poisoned_chunks = evidence.get("poisonedChunks")
            if not isinstance(poisoned_chunks, int) or isinstance(poisoned_chunks, bool):
                continue
            if poisoned_chunks <= 0:
                continue
            poisoning_reasons = string_list_value(evidence.get("poisoningReasons", ()))
            poisoned_documents = string_list_value(evidence.get("poisonedChunkDocuments", ()))
            return {
                "caseId": grade.case_id,
                "runId": grade.run_id,
                "poisonedChunks": poisoned_chunks,
                "poisoningReasons": poisoning_reasons,
                "poisonedChunkDocuments": poisoned_documents,
            }
    return None
