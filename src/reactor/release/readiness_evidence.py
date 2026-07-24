from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from reactor.context.diagnostics import ALLOWED_MEMORY_STATUS_COUNT_LABELS
from reactor.rag.ingestion_candidate_actions import (
    RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
    rag_candidate_eval_apply_action_command,
    rag_candidate_review_action,
)
from reactor.rag.ingestion_candidate_ids import (
    is_command_slug,
)
from reactor.release.input_provenance import (
    readiness_inputs_hash,
    readiness_item_with_input_provenance,
)
from reactor.release.readiness import current_git_commit, write_report
from reactor.release.readiness_actions import (
    HARDENING_SUITE_REPORT_FILE,
    rag_ingestion_lifecycle_remediation_command,
    readiness_report_args_for_reports,
)
from reactor.release.readiness_contracts import (
    RAG_CANDIDATE_SOURCE_SUITE,
    candidate_workflow_tag_from_case_ids,
    feedback_promotion_review_closed,
    feedback_review_queue_action,
    feedback_review_queue_bulk_review_action,
    feedback_review_queue_candidate_review_action,
    feedback_review_queue_export_action,
    feedback_review_queue_memory_lifecycle_action,
    langsmith_feedback_promotion_contract_failure,
    observability_target_has_secret,
    readiness_contract_failure,
    valid_candidate_workflow_tag,
)

ReportInput = tuple[str, Path]
ReportPayloadInput = tuple[str, dict[str, Any], str]
PRESERVED_EVIDENCE_FIELDS = (
    "observabilitySdk",
    "observabilityTarget",
    "privacy",
    "feedbackLoop",
    "graphTopology",
    "toolProfileBudget",
    "toolInvocationLifecycle",
    "durableRunQueue",
    "outboxInboxLifecycle",
    "redisCoordination",
    "researchAnswerContract",
    "guardBlock",
    "contextManifest",
    "contextManifestDiagnostics",
    "langchainMiddlewareChain",
    "langchainMiddlewarePolicy",
    "langchainSerializationBoundary",
    "contextManagementLifecycle",
    "usageCostLifecycle",
    "checkpointProvenance",
    "structuredOutput",
    "datasetName",
    "dataType",
    "datasetMetadata",
    "sourceSuite",
    "enabledCases",
    "exampleIds",
    "caseIds",
    "metadataCaseIds",
    "sourceRunIds",
    "caseSourceRunIds",
    "caseFile",
    "runFile",
    "splitCounts",
    "syncCommand",
    "liveSyncCommand",
    "readinessCommand",
    "releaseReadinessCommand",
    "remediationCommand",
    "ragCandidateEvalApplyAction",
    "readinessReportArg",
    "requiredReadinessReports",
    "requiredEnvAnyOf",
    "missingEnvAnyOf",
    "recommendedEnv",
    "readinessReports",
    "nextActions",
    "readyLocalContractActions",
    "envFile",
    "preflightFile",
    "preflightEnvTemplate",
    "preflightEnvTemplateRefreshPath",
    "preflightEnvTemplateRefreshCommand",
    "preflightEnvFileCommand",
    "releaseSmokeEnvFileCommand",
    "preflightSummary",
    "preflightMissingEnv",
    "preflightMissingAnyOf",
    "preflightRecommendedEnv",
    "preflightBlockedGates",
    "smokeRunSummary",
    "smokeRunMissingEnv",
    "smokeRunMissingAnyOf",
    "smokeRunRecommendedEnv",
    "smokeRunBlockedGates",
    "exampleContract",
    "sdkContract",
    "feedbackPromotion",
    "feedbackReviewQueue",
    "productCapabilityBoundary",
    "productBoundaryExpectedResolvedByReports",
    "minorBoundaryResolvedEvidence",
    "minorBoundaryResolvedByReports",
    "productBoundaryReadinessCommand",
    "promotionCoverage",
    "traceGrading",
    "releaseGateReason",
    "releaseGate",
    "selectedTags",
    "a2aProtocol",
    "apiBoundary",
    "mcpPreflight",
    "slackMcpSurfacePolicy",
    "memoryMaintenanceLifecycle",
    "ragIngestionLifecycle",
    "artifactLifecycle",
    "promptReleaseLifecycle",
    "approvalLifecycle",
    "providerFallbackPolicy",
    "langgraphFaultTolerance",
    "checkpointRetentionPolicy",
    "streamingEventContract",
    "backendProviderIntegration",
    "providerRuntimeSmoke",
    "slackGatewaySmoke",
    "releaseEvidence",
)
MEMORY_CONTRACT_AREAS = (
    "manager",
    "statuses",
    "consolidation",
    "review",
    "privacy",
    "dependencies",
)


def build_release_readiness_report(
    reports: Sequence[ReportInput],
    *,
    required_reports: Sequence[str] = (),
    latest_tag: str = "",
) -> dict[str, object]:
    items = [readiness_item(name=name, path=path) for name, path in reports]
    return build_release_readiness_report_from_items(
        items,
        required_reports=required_reports,
        latest_tag=latest_tag,
    )


def build_release_readiness_report_from_payloads(
    reports: Sequence[ReportPayloadInput],
    *,
    required_reports: Sequence[str] = (),
    latest_tag: str = "",
    expected_commit: str = "",
    current_commit_sha: str = "",
    max_input_age_seconds: int = 0,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    now = generated_at or datetime.now(UTC)
    current_commit = (current_commit_sha or current_git_commit()) if expected_commit else ""
    provenanced = [
        readiness_item_with_input_provenance(
            name=name,
            report=report,
            artifact=artifact,
            expected_commit=expected_commit,
            current_commit=current_commit,
            max_input_age_seconds=max_input_age_seconds,
            generated_at=now,
            item_factory=readiness_item_from_report,
        )
        for name, report, artifact in reports
    ]
    result = build_release_readiness_report_from_items(
        [item for item, _ in provenanced],
        required_reports=required_reports,
        latest_tag=latest_tag,
    )
    if expected_commit:
        inputs = [provenance for _, provenance in provenanced]
        result["provenance"] = {
            "commitSha": current_commit,
            "expectedCommitSha": expected_commit,
            "generatedAt": now.isoformat().replace("+00:00", "Z"),
            "inputHash": readiness_inputs_hash(inputs),
            "inputs": inputs,
        }
    return result


def build_release_readiness_report_from_items(
    items: Sequence[dict[str, object]],
    *,
    required_reports: Sequence[str] = (),
    latest_tag: str = "",
) -> dict[str, object]:
    items = [
        readiness_item_with_action_state_contract(readiness_item_with_env_remediation_action(item))
        for item in items
    ]
    explicit_required_names = normalized_required_reports(required_reports)
    feedback_loop_required_names = feedback_loop_required_report_names(items)
    explicit_missing_items = missing_required_report_items(items, explicit_required_names)
    items_with_explicit_missing = [*items, *explicit_missing_items]
    feedback_loop_missing_items = missing_feedback_loop_report_items(
        items_with_explicit_missing,
        feedback_loop_required_names,
    )
    items_with_feedback_missing = [*items_with_explicit_missing, *feedback_loop_missing_items]
    item_required_names = item_required_report_names(items_with_feedback_missing)
    item_required_missing_items = missing_required_report_items(
        items_with_feedback_missing,
        item_required_names,
    )
    all_items = apply_cross_report_product_boundary(
        apply_feedback_loop_consistency(
            [*items_with_feedback_missing, *item_required_missing_items]
        )
    )
    summary = Counter(item["status"] for item in all_items)
    passed = int(summary.get("passed", 0))
    failed = int(summary.get("failed", 0))
    skipped = int(summary.get("skipped", 0))
    blocked = int(summary.get("blocked", 0))
    total = len(all_items)
    ok = total > 0 and failed == 0 and skipped == 0 and blocked == 0 and passed == total
    summary_report: dict[str, object] = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
    }
    if blocked:
        summary_report["blocked"] = blocked
    report: dict[str, object] = {
        "ok": ok,
        "status": readiness_status(total=total, failed=failed, skipped=skipped, blocked=blocked),
        "scope": "release_readiness",
        "summary": summary_report,
        "items": all_items,
    }
    aggregate_required_names = normalized_required_reports(
        [*explicit_required_names, *item_required_names]
    )
    warnings = release_readiness_warnings(all_items)
    report["tagRecommendation"] = tag_recommendation(
        all_items,
        ok=ok,
        status=cast(str, report["status"]),
        latest_tag=latest_tag,
        warnings=warnings,
        aggregate_required_reports=aggregate_required_names,
    )
    report.update(release_readiness_next_action_state_handoff(report["tagRecommendation"]))
    tag_contract_failure = tag_recommendation_contract_failure(report["tagRecommendation"])
    if tag_contract_failure:
        report["ok"] = False
        report["status"] = "failed"
        report["failure"] = tag_contract_failure
    if aggregate_required_names:
        report["requiredReports"] = aggregate_required_names
    if feedback_loop_required_names:
        report["feedbackLoopRequiredReports"] = feedback_loop_required_names
    missing_reports = missing_report_names(
        items,
        [*aggregate_required_names, *feedback_loop_required_names],
    )
    if aggregate_required_names or feedback_loop_required_names:
        report["missingReports"] = missing_reports
    if warnings:
        report["warnings"] = warnings
    if report["ok"] is not True:
        report["failureSummary"] = readiness_failure_summary(report)
    return report


def release_readiness_next_action_state_handoff(
    recommendation: object,
) -> dict[str, object]:
    if not isinstance(recommendation, Mapping):
        return {}
    recommendation_mapping = cast(Mapping[object, object], recommendation)
    blocking_actions = recommendation_mapping.get("blockingNextActions")
    if not isinstance(blocking_actions, Sequence) or isinstance(
        blocking_actions, str | bytes | bytearray
    ):
        return {}
    ready_ids: list[str] = []
    blocked_ids: list[str] = []
    states: dict[str, str] = {}
    for action in cast(Sequence[object], blocking_actions):
        if not isinstance(action, Mapping):
            continue
        action_mapping = cast(Mapping[object, object], action)
        for action_id in string_sequence_value(action_mapping.get("readyNextActionIds")):
            if action_id not in ready_ids:
                ready_ids.append(action_id)
            states.setdefault(action_id, "ready")
        local_contract_actions = action_mapping.get("readyLocalContractActions")
        if isinstance(local_contract_actions, Sequence) and not isinstance(
            local_contract_actions,
            str | bytes | bytearray,
        ):
            for local_contract_action in cast(Sequence[object], local_contract_actions):
                if not isinstance(local_contract_action, Mapping):
                    continue
                action_id = cast(Mapping[object, object], local_contract_action).get("id")
                if not isinstance(action_id, str) or not action_id.strip():
                    continue
                normalized_action_id = action_id.strip()
                if normalized_action_id not in ready_ids:
                    ready_ids.append(normalized_action_id)
                states.setdefault(normalized_action_id, "ready")
        for action_id in string_sequence_value(action_mapping.get("blockedNextActionIds")):
            if action_id not in blocked_ids:
                blocked_ids.append(action_id)
            states.setdefault(action_id, "blocked")
        action_states = action_mapping.get("nextActionStates")
        if isinstance(action_states, Mapping):
            for action_id, state in cast(Mapping[object, object], action_states).items():
                if not isinstance(action_id, str) or not action_id.strip():
                    continue
                if not isinstance(state, str) or state.strip() not in {"ready", "blocked"}:
                    continue
                normalized_action_id = action_id.strip()
                normalized_state = state.strip()
                states[normalized_action_id] = normalized_state
                target = ready_ids if normalized_state == "ready" else blocked_ids
                if normalized_action_id not in target:
                    target.append(normalized_action_id)
    handoff: dict[str, object] = {}
    if ready_ids:
        handoff["readyNextActionIds"] = ready_ids
    if blocked_ids:
        handoff["blockedNextActionIds"] = blocked_ids
    if states:
        handoff["nextActionStates"] = states
    return handoff


def tag_recommendation(
    items: Sequence[Mapping[str, object]],
    *,
    ok: bool,
    status: str,
    latest_tag: str = "",
    warnings: Sequence[Mapping[str, object]] = (),
    aggregate_required_reports: Sequence[str] = (),
) -> dict[str, object]:
    passed_reports = readiness_item_names_with_status(items, "passed")
    blocking_reports = [
        name for name in readiness_item_names(items) if name not in set(passed_reports)
    ]
    minor_boundary_reports = minor_version_boundary_reports(items)
    policy = "version tags are only for release-worthy batches or deployment candidates"
    if ok:
        recommended_bump = "minor" if minor_boundary_reports else "patch"
        next_action = (
            "verify clean worktree and choose the next minor version tag"
            if minor_boundary_reports
            else "verify clean worktree and choose the next patch version tag"
        )
        recommendation: dict[str, object] = {
            "status": "eligible",
            "reason": "required release readiness reports passed",
            "eligible": True,
            "recommendedVersionBump": recommended_bump,
            "recommendedTagPattern": "v1.2.0" if minor_boundary_reports else "v1.0.x",
            "minorEligible": bool(minor_boundary_reports),
            "policy": policy,
            "passedReports": passed_reports,
            "nextAction": next_action,
        }
        if minor_boundary_reports:
            recommendation["minorBoundaryReports"] = minor_boundary_reports
            release_readiness_command = minor_boundary_release_readiness_command(
                items,
                minor_boundary_reports,
            )
            if release_readiness_command:
                recommendation["releaseReadinessCommand"] = release_readiness_command
        else:
            recommendation["minorBlockedReason"] = "no passed product capability boundary evidence"
            recommendation.update(minor_boundary_remediation(items))
        warning_reports = readiness_warning_report_names(warnings)
        if warning_reports:
            recommendation["status"] = "eligible_with_warnings"
            recommendation["reason"] = "required release readiness reports passed with warnings"
            recommendation["warningReports"] = warning_reports
            recommendation["warningReviewRequired"] = True
            recommendation["nextAction"] = f"review release readiness warnings, then {next_action}"
        recommendation.update(
            tag_selection(
                latest_tag=latest_tag,
                recommended_bump=recommended_bump,
            )
        )
        return recommendation
    reason = "release readiness failed" if status == "failed" else "release readiness is blocked"
    deferred_recommendation: dict[str, object] = {
        "status": "defer",
        "reason": reason,
        "eligible": False,
        "recommendedVersionBump": "none",
        "recommendedTagPattern": "none",
        "minorEligible": False,
        "policy": policy,
        "blockingReports": blocking_reports,
        "passedReports": passed_reports,
        "nextAction": "resolve blocked/skipped release readiness reports before tagging",
    }
    blocker_hierarchy = release_blocker_hierarchy(items, blocking_reports)
    if blocker_hierarchy:
        deferred_recommendation.update(blocker_hierarchy)
        root_blocking_reports = string_sequence_value(blocker_hierarchy.get("rootBlockingReports"))
        root_next_actions = blocking_root_next_actions(items, root_blocking_reports)
        if root_next_actions:
            deferred_recommendation["blockingNextActions"] = root_next_actions
    elif "preflight" in blocking_reports:
        root_next_actions = blocking_root_next_actions(items, blocking_reports)
        if root_next_actions:
            deferred_recommendation["rootBlockingReports"] = [
                action["report"]
                for action in root_next_actions
                if isinstance(action.get("report"), str)
            ]
            deferred_recommendation["blockingNextActions"] = root_next_actions
    deferred_recommendation.update(minor_boundary_resolved_handoff(items))
    deferred_recommendation.update(blocking_minor_boundary_remediation(items))
    env_remediation = blocking_env_remediation(items)
    if release_smoke_env_remediation(env_remediation):
        deferred_recommendation.update(env_remediation)
        deferred_recommendation.update(missing_required_report_handoff(items))
        return deferred_recommendation
    release_gate_handoff = blocking_release_gate_handoff(items)
    if release_gate_handoff:
        deferred_recommendation.update(release_gate_handoff)
        return deferred_recommendation
    next_action = preferred_blocking_next_action(items)
    next_action_id = string_field(next_action, "id") if next_action else ""
    if next_action_id:
        deferred_recommendation["nextAction"] = f"run nextAction.{next_action_id} before tagging"
        deferred_recommendation["nextActionId"] = next_action_id
        deferred_recommendation.update(preferred_next_action_state_handoff(items, next_action_id))
        next_action_command = string_field(next_action, "command")
        if next_action_command:
            deferred_recommendation["nextActionCommand"] = next_action_command
        next_action_env_file_command = string_field(next_action, "envFileCommand")
        if next_action_env_file_command:
            deferred_recommendation["nextActionEnvFileCommand"] = next_action_env_file_command
        release_readiness_command = string_field(next_action, "releaseReadinessCommand")
        if release_readiness_command:
            deferred_recommendation["releaseReadinessCommand"] = release_readiness_command
        for identity_key in (
            "feedbackId",
            "evalCaseId",
            "sourceRunId",
            "candidateTag",
            "requiredReviewNote",
        ):
            identity_value = string_field(next_action, identity_key)
            if identity_value:
                deferred_recommendation[identity_key] = identity_value
        for tag_key in ("feedbackTags", "workflowTags"):
            tag_values = string_sequence_value(next_action.get(tag_key))
            if tag_values:
                deferred_recommendation[tag_key] = tag_values
        remediation_command = string_field(next_action, "remediationCommand")
        if remediation_command:
            deferred_recommendation["remediationCommand"] = remediation_command
        required_env_any_of = next_action.get("requiredEnvAnyOf")
        if required_env_any_of is not None:
            deferred_recommendation["requiredEnvAnyOf"] = required_env_any_of
        missing_env_any_of = next_action.get("missingEnvAnyOf")
        if missing_env_any_of is not None:
            deferred_recommendation["missingEnvAnyOf"] = missing_env_any_of
        recommended_env = next_action.get("recommendedEnv")
        if recommended_env is not None:
            deferred_recommendation["recommendedEnv"] = recommended_env
        for handoff_key in ("preflightFile", "preflightEnvTemplate", "releaseReadinessFile"):
            handoff_value = string_field(next_action, handoff_key)
            if handoff_value:
                deferred_recommendation[handoff_key] = handoff_value
        aggregate_readiness_reports = aggregate_readiness_report_files_for_action(
            items=items,
            required_reports=aggregate_required_reports,
            next_action=next_action,
        )
        readiness_report_arg = (
            readiness_report_args_for_reports(
                required_reports=aggregate_required_reports,
                report_files=aggregate_readiness_reports,
            )
            if aggregate_readiness_reports
            else string_field(next_action, "readinessReportArg")
        )
        if readiness_report_arg:
            deferred_recommendation["readinessReportArg"] = readiness_report_arg
        required_readiness_reports = (
            list(aggregate_required_reports)
            if aggregate_readiness_reports
            else next_action.get("requiredReadinessReports")
        )
        if required_readiness_reports is not None:
            deferred_recommendation["requiredReadinessReports"] = required_readiness_reports
        readiness_reports = (
            aggregate_readiness_reports
            if aggregate_readiness_reports
            else next_action.get("readinessReports")
        )
        if readiness_reports is not None:
            deferred_recommendation["readinessReports"] = readiness_reports
        deferred_recommendation.update(blocking_env_action_metadata(items, next_action_id))
    else:
        deferred_recommendation.update(env_remediation)
    return deferred_recommendation


def preferred_next_action_state_handoff(
    items: Sequence[Mapping[str, object]],
    next_action_id: str,
) -> dict[str, object]:
    for item in items:
        next_actions = item.get("nextActions")
        if not isinstance(next_actions, Sequence) or isinstance(
            next_actions,
            str | bytes | bytearray,
        ):
            continue
        for action in cast(Sequence[object], next_actions):
            if not isinstance(action, Mapping):
                continue
            action_id = cast(Mapping[object, object], action).get("id")
            if not isinstance(action_id, str) or action_id.strip() != next_action_id:
                continue
            handoff: dict[str, object] = {}
            add_action_state_handoff(handoff, item)
            return handoff
    return {}


def blocking_root_next_actions(
    items: Sequence[Mapping[str, object]],
    root_blocking_reports: Sequence[str],
) -> list[dict[str, object]]:
    root_report_set = {name for name in root_blocking_reports if name}
    if not root_report_set:
        return []
    actions: list[dict[str, object]] = []
    for item in items:
        name = item.get("name")
        if not isinstance(name, str) or name not in root_report_set:
            continue
        remediation = blocking_env_remediation([item])
        handoff: dict[str, object]
        if release_smoke_env_remediation(remediation):
            handoff = {"report": name, **remediation}
        else:
            action = preferred_blocking_next_action([item])
            if not action:
                handoff = {"report": name, **remediation} if remediation else {}
            else:
                handoff = blocking_next_action_handoff(name, action)
        if not handoff and source_has_ready_local_contract_actions(item):
            handoff = {"report": name}
        add_action_state_handoff(handoff, item)
        add_ready_local_contract_action_handoff(handoff, item)
        release_gate_reason_value = string_field(dict(item), "releaseGateReason")
        if release_gate_reason_value:
            handoff["releaseGateReason"] = release_gate_reason_value
        if handoff:
            actions.append(handoff)
    return actions


def add_action_state_handoff(
    handoff: dict[str, object],
    source: Mapping[str, object],
) -> None:
    ready_ids = string_sequence_value(source.get("readyNextActionIds"))
    blocked_ids = string_sequence_value(source.get("blockedNextActionIds"))
    if ready_ids:
        handoff["readyNextActionIds"] = ready_ids
    if blocked_ids:
        handoff["blockedNextActionIds"] = blocked_ids
    states = action_states_handoff(source, ready_ids=ready_ids, blocked_ids=blocked_ids)
    if states:
        handoff["nextActionStates"] = states


def add_ready_local_contract_action_handoff(
    handoff: dict[str, object],
    source: Mapping[str, object],
) -> None:
    actions = source.get("readyLocalContractActions")
    if isinstance(actions, Sequence) and not isinstance(actions, str | bytes | bytearray):
        filtered: list[dict[str, object]] = []
        for action in cast(Sequence[object], actions):
            if not isinstance(action, Mapping):
                continue
            action_mapping = {
                key: value
                for key, value in cast(Mapping[object, object], action).items()
                if isinstance(key, str)
            }
            if action_mapping:
                filtered.append(action_mapping)
        if filtered:
            handoff["readyLocalContractActions"] = filtered


def source_has_ready_local_contract_actions(source: Mapping[str, object]) -> bool:
    actions = source.get("readyLocalContractActions")
    if not isinstance(actions, Sequence) or isinstance(actions, str | bytes | bytearray):
        return False
    return any(isinstance(action, Mapping) for action in cast(Sequence[object], actions))


def action_states_handoff(
    source: Mapping[str, object],
    *,
    ready_ids: Sequence[str] = (),
    blocked_ids: Sequence[str] = (),
) -> dict[str, str]:
    source_states = source.get("nextActionStates")
    if isinstance(source_states, Mapping):
        states = {
            action_id.strip(): state.strip()
            for action_id, state in cast(Mapping[object, object], source_states).items()
            if isinstance(action_id, str)
            and action_id.strip()
            and isinstance(state, str)
            and state.strip()
        }
        if states:
            return states
    return {
        **{action_id: "ready" for action_id in ready_ids},
        **{action_id: "blocked" for action_id in blocked_ids},
    }


def blocking_next_action_handoff(
    report_name: str,
    next_action: Mapping[str, object],
) -> dict[str, object]:
    action_id = string_field(dict(next_action), "id")
    handoff: dict[str, object] = {"report": report_name}
    if action_id:
        handoff["nextAction"] = f"run nextAction.{action_id} before tagging"
        handoff["nextActionId"] = action_id
    command = string_field(dict(next_action), "command")
    if command:
        handoff["nextActionCommand"] = command
    env_file_command = string_field(dict(next_action), "envFileCommand")
    if env_file_command:
        handoff["nextActionEnvFileCommand"] = env_file_command
    for key in (
        "releaseReadinessCommand",
        "remediationCommand",
        "preflightFile",
        "preflightEnvTemplate",
        "releaseReadinessFile",
        "reportFile",
        "readinessReportArg",
    ):
        value = string_field(dict(next_action), key)
        if value:
            handoff[key] = value
    for key in (
        "requiredEnvAnyOf",
        "missingEnvAnyOf",
        "recommendedEnv",
        "requiredReadinessReports",
        "readinessReports",
        "readyNextActionIds",
        "blockedNextActionIds",
        "nextActionStates",
    ):
        value = next_action.get(key)
        if value is not None:
            handoff[key] = value
    for key in ("feedbackId", "evalCaseId", "sourceRunId", "candidateTag", "requiredReviewNote"):
        value = string_field(dict(next_action), key)
        if value:
            handoff[key] = value
    return handoff


def release_blocker_hierarchy(
    items: Sequence[Mapping[str, object]],
    blocking_reports: Sequence[str],
) -> dict[str, object]:
    blocking_set = set(blocking_reports)
    if "release_evidence" not in blocking_set or "smoke_run" not in blocking_set:
        return {}
    smoke_run_blocked = any(
        item.get("name") == "smoke_run" and item.get("status") in {"blocked", "failed", "skipped"}
        for item in items
    )
    release_evidence_missing = any(
        item.get("name") == "release_evidence"
        and item.get("status") in {"blocked", "failed", "skipped"}
        for item in items
    )
    if not smoke_run_blocked or not release_evidence_missing:
        return {}
    root_blocking_reports = [report for report in blocking_reports if report != "release_evidence"]
    return {
        "rootBlockingReports": root_blocking_reports,
        "downstreamBlockedReports": ["release_evidence"],
    }


def tag_recommendation_contract_failure(value: object) -> str:
    if not isinstance(value, Mapping):
        return "tag recommendation contract missing"
    recommendation = cast(Mapping[object, object], value)
    action_state_failure = tag_recommendation_action_state_failure(recommendation)
    if action_state_failure:
        return action_state_failure
    if (
        recommendation.get("eligible") is True
        and recommendation.get("recommendedVersionBump") == "minor"
        and recommendation.get("minorEligible") is True
    ):
        release_readiness_command = recommendation.get("releaseReadinessCommand")
        if (
            not isinstance(release_readiness_command, str)
            or "uv run reactor-release-smoke-run" not in release_readiness_command
        ):
            return "tag recommendation contract missing"
    return ""


def tag_recommendation_action_state_failure(
    recommendation: Mapping[object, object],
) -> str:
    next_action_id = recommendation.get("nextActionId")
    if isinstance(next_action_id, str) and next_action_id.strip():
        if action_state_mismatch(
            action_id=next_action_id.strip(),
            source=recommendation,
        ):
            return "tag recommendation action-state contract mismatch"
    blocking_actions = recommendation.get("blockingNextActions")
    if isinstance(blocking_actions, Sequence) and not isinstance(
        blocking_actions,
        str | bytes | bytearray,
    ):
        for action in cast(Sequence[object], blocking_actions):
            if not isinstance(action, Mapping):
                continue
            action_id = cast(Mapping[object, object], action).get("nextActionId")
            if not isinstance(action_id, str) or not action_id.strip():
                continue
            if action_state_mismatch(
                action_id=action_id.strip(),
                source=cast(Mapping[object, object], action),
            ):
                return "tag recommendation action-state contract mismatch"
    return ""


def action_state_mismatch(
    *,
    action_id: str,
    source: Mapping[object, object],
) -> bool:
    ready_action_ids = string_sequence_value(source.get("readyNextActionIds"))
    blocked_action_ids = string_sequence_value(source.get("blockedNextActionIds"))
    if ready_action_ids and action_id not in ready_action_ids:
        return True
    if action_id in blocked_action_ids:
        return True
    return False


def readiness_item_action_state_contract_failure(item: Mapping[str, object]) -> str | None:
    ready_action_ids = set(string_sequence_value(item.get("readyNextActionIds")))
    blocked_action_ids = set(string_sequence_value(item.get("blockedNextActionIds")))
    if ready_action_ids & blocked_action_ids:
        return "readiness item action-state contract mismatch"
    next_action_states = action_states_handoff(item)
    if not ready_action_ids and not blocked_action_ids and not next_action_states:
        return None
    for action_id in ready_action_ids:
        if next_action_states.get(action_id) not in {"", "ready", None}:
            return "readiness item action-state contract mismatch"
    for action_id in blocked_action_ids:
        if next_action_states.get(action_id) not in {"", "blocked", None}:
            return "readiness item action-state contract mismatch"

    next_actions = item.get("nextActions")
    if not isinstance(next_actions, Sequence) or isinstance(
        next_actions,
        str | bytes | bytearray,
    ):
        return "readiness item action-state contract mismatch"

    action_ids: set[str] = set()
    ready_blocked_by_dependencies: set[str] = set()
    action_dependencies: dict[str, list[str]] = {}
    for action in cast(Sequence[object], next_actions):
        if not isinstance(action, Mapping):
            continue
        action_mapping = cast(Mapping[object, object], action)
        action_id_value = action_mapping.get("id")
        if not isinstance(action_id_value, str) or not action_id_value.strip():
            continue
        action_id = action_id_value.strip()
        if action_id in action_ids:
            return "readiness item action-state contract mismatch"
        action_ids.add(action_id)
        dependency_ids = string_sequence_value(action_mapping.get("dependsOnActionIds"))
        action_dependencies[action_id] = dependency_ids

    for action_id, dependency_ids in action_dependencies.items():
        if not set(dependency_ids).issubset(action_ids):
            return "readiness item action-state contract mismatch"
        if action_id in ready_action_ids and dependency_ids:
            ready_blocked_by_dependencies.add(action_id)
        if next_action_states.get(action_id) == "ready" and dependency_ids:
            ready_blocked_by_dependencies.add(action_id)

    if readiness_action_dependencies_have_cycle(action_dependencies):
        return "readiness item action-state contract mismatch"
    if next_action_states and not set(next_action_states).issubset(action_ids):
        return "readiness item action-state contract mismatch"
    if any(state not in {"ready", "blocked"} for state in next_action_states.values()):
        return "readiness item action-state contract mismatch"
    if not ready_action_ids.issubset(action_ids):
        return "readiness item action-state contract mismatch"
    if ready_blocked_by_dependencies:
        return "readiness item action-state contract mismatch"
    return None


def readiness_action_dependencies_have_cycle(
    action_dependencies: Mapping[str, Sequence[str]],
) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(action_id: str) -> bool:
        if action_id in visiting:
            return True
        if action_id in visited:
            return False
        visiting.add(action_id)
        for dependency_id in action_dependencies.get(action_id, ()):
            if visit(dependency_id):
                return True
        visiting.remove(action_id)
        visited.add(action_id)
        return False

    return any(visit(action_id) for action_id in action_dependencies)


def readiness_item_with_action_state_contract(item: dict[str, object]) -> dict[str, object]:
    item = readiness_item_with_derived_action_state_fields(item)
    failure = readiness_item_action_state_contract_failure(item)
    if failure is None:
        return item
    updated = dict(item)
    updated["ok"] = False
    updated["status"] = "failed"
    updated["failure"] = failure
    return updated


def readiness_item_with_derived_action_state_fields(item: dict[str, object]) -> dict[str, object]:
    next_actions = item.get("nextActions")
    if not isinstance(next_actions, Sequence) or isinstance(next_actions, str | bytes | bytearray):
        return item
    ready_ids = string_sequence_value(item.get("readyNextActionIds"))
    blocked_ids = string_sequence_value(item.get("blockedNextActionIds"))
    states = action_states_handoff(item, ready_ids=ready_ids, blocked_ids=blocked_ids)
    if ready_ids and blocked_ids and states:
        return item
    derived_ready_ids: list[str] = []
    derived_blocked_ids: list[str] = []
    derived_states: dict[str, str] = {}
    for action in cast(Sequence[object], next_actions):
        if not isinstance(action, Mapping):
            continue
        action_mapping = cast(Mapping[object, object], action)
        action_id = action_mapping.get("id")
        if not isinstance(action_id, str) or not action_id.strip():
            continue
        normalized_action_id = action_id.strip()
        dependencies = string_sequence_value(action_mapping.get("dependsOnActionIds"))
        if dependencies:
            derived_blocked_ids.append(normalized_action_id)
            derived_states[normalized_action_id] = "blocked"
        else:
            derived_ready_ids.append(normalized_action_id)
            derived_states[normalized_action_id] = "ready"
    if not derived_states:
        return item
    updated = dict(item)
    if not ready_ids and derived_ready_ids:
        updated["readyNextActionIds"] = derived_ready_ids
    if not blocked_ids and derived_blocked_ids:
        updated["blockedNextActionIds"] = derived_blocked_ids
    if not states:
        updated["nextActionStates"] = derived_states
    return updated


def readiness_item_with_env_remediation_action(item: dict[str, object]) -> dict[str, object]:
    existing_actions = item.get("nextActions")
    if (
        isinstance(existing_actions, Sequence)
        and not isinstance(existing_actions, str | bytes | bytearray)
        and existing_actions
    ):
        return item
    remediation = blocking_env_remediation([item])
    if not release_smoke_env_remediation(remediation):
        return item

    command = string_field(cast(dict[str, Any], remediation), "preflightEnvFileCommand")
    if not command:
        command = string_field(cast(dict[str, Any], remediation), "remediationCommand")
    action: dict[str, object] = {
        "id": "set-release-smoke-preflight-env",
        "label": "Set release smoke preflight environment before tagging",
    }
    if command:
        action["command"] = command
    for field_name in (
        "remediationCommand",
        "releaseSmokeEnvFileCommand",
        "missingEnv",
        "missingEnvAnyOf",
        "requiredEnvAnyOf",
        "recommendedEnv",
        "preflightEnvTemplate",
        "preflightEnvTemplateRefreshPath",
        "preflightEnvTemplateRefreshCommand",
    ):
        value = remediation.get(field_name)
        if value is not None:
            action[field_name] = value

    updated = dict(item)
    updated["nextActions"] = [action]
    return updated


def aggregate_readiness_report_files(
    *,
    items: Sequence[Mapping[str, object]],
    required_reports: Sequence[str],
) -> dict[str, str]:
    names = normalized_required_reports(required_reports)
    if not names:
        return {}
    available: dict[str, str] = {}
    for item in items:
        name_value = item.get("name")
        name = name_value.strip() if isinstance(name_value, str) else ""
        if not name:
            continue
        report_file_value = item.get("reportFile") or item.get("artifact")
        report_file = report_file_value.strip() if isinstance(report_file_value, str) else ""
        if report_file:
            available[name] = report_file
    selected = {name: available.get(name, "") for name in names}
    if any(not value for value in selected.values()):
        return {}
    return selected


def aggregate_readiness_report_files_for_action(
    *,
    items: Sequence[Mapping[str, object]],
    required_reports: Sequence[str],
    next_action: Mapping[str, Any],
) -> dict[str, str]:
    action_id_value = next_action.get("id")
    action_id = action_id_value.strip() if isinstance(action_id_value, str) else ""
    if action_id not in {
        "preflight-langsmith",
        "rerun-preflight-langsmith",
        "sync-langsmith",
        "refresh-release-readiness",
    }:
        return {}
    aggregate_names = normalized_required_reports(required_reports)
    if not aggregate_names:
        return {}
    selected_required_reports = next_action.get("requiredReadinessReports")
    selected_names = (
        normalized_required_reports(cast(Sequence[str], selected_required_reports))
        if isinstance(selected_required_reports, Sequence)
        and not isinstance(selected_required_reports, str | bytes | bytearray)
        else []
    )
    if selected_names and set(aggregate_names).issubset(set(selected_names)):
        return {}
    return aggregate_readiness_report_files(items=items, required_reports=aggregate_names)


def blocking_env_action_metadata(
    items: Sequence[Mapping[str, object]],
    selected_action_id: str,
) -> dict[str, object]:
    for item in items:
        if item.get("status") == "passed":
            continue
        next_actions = item.get("nextActions")
        if not isinstance(next_actions, Sequence) or isinstance(
            next_actions, str | bytes | bytearray
        ):
            continue
        for action in cast(Sequence[object], next_actions):
            if not isinstance(action, Mapping):
                continue
            action_mapping = cast(Mapping[object, object], action)
            action_id_value = action_mapping.get("id")
            action_id = action_id_value.strip() if isinstance(action_id_value, str) else ""
            missing_env_any_of = action_mapping.get("missingEnvAnyOf")
            if not action_id or action_id == selected_action_id or missing_env_any_of is None:
                continue
            metadata: dict[str, object] = {
                "blockingEnvActionId": action_id,
                "blockingMissingEnvAnyOf": missing_env_any_of,
            }
            required_env_any_of = action_mapping.get("requiredEnvAnyOf")
            if required_env_any_of is not None:
                metadata["blockingRequiredEnvAnyOf"] = required_env_any_of
            recommended_env = action_mapping.get("recommendedEnv")
            if recommended_env is not None:
                metadata["blockingRecommendedEnv"] = recommended_env
            return metadata
    return {}


def blocking_env_remediation(items: Sequence[Mapping[str, object]]) -> dict[str, object]:
    for item in items:
        if item.get("status") == "passed":
            continue
        smoke_run_missing_env = item.get("smokeRunMissingEnv")
        smoke_run_missing_any_of = item.get("smokeRunMissingAnyOf")
        smoke_run_missing_env_summary = string_sequence_summary(smoke_run_missing_env)
        smoke_run_missing_any_of_summary = string_sequence_summary(smoke_run_missing_any_of)
        if (
            isinstance(smoke_run_missing_env, Sequence)
            and not isinstance(smoke_run_missing_env, str | bytes | bytearray)
            and smoke_run_missing_env_summary
        ) or (
            isinstance(smoke_run_missing_any_of, Sequence)
            and not isinstance(smoke_run_missing_any_of, str | bytes | bytearray)
            and smoke_run_missing_any_of_summary
        ):
            remediation = {
                "nextAction": "set release smoke preflight environment before tagging",
            }
            if isinstance(smoke_run_missing_env, Sequence) and not isinstance(
                smoke_run_missing_env, str | bytes | bytearray
            ):
                remediation["missingEnv"] = list(cast(Sequence[object], smoke_run_missing_env))
            if isinstance(smoke_run_missing_any_of, Sequence) and not isinstance(
                smoke_run_missing_any_of, str | bytes | bytearray
            ):
                missing_any_of = list(cast(Sequence[object], smoke_run_missing_any_of))
                remediation["missingEnvAnyOf"] = missing_any_of
                required_env_any_of = env_any_of_groups_from_summary(missing_any_of)
                if required_env_any_of:
                    remediation["requiredEnvAnyOf"] = required_env_any_of
            smoke_run_recommended_env = item.get("smokeRunRecommendedEnv")
            if isinstance(smoke_run_recommended_env, Sequence) and not isinstance(
                smoke_run_recommended_env, str | bytes | bytearray
            ):
                recommended_env = string_sequence_value(
                    cast(Sequence[object], smoke_run_recommended_env)
                )
                if recommended_env:
                    remediation["recommendedEnv"] = recommended_env
            preflight_env_template = item.get("preflightEnvTemplate")
            if isinstance(preflight_env_template, str) and preflight_env_template.strip():
                remediation["preflightEnvTemplate"] = preflight_env_template.strip()
            copy_release_env_handoff_fields(item, remediation)
            return remediation
        preflight_missing_env = item.get("preflightMissingEnv")
        preflight_missing_any_of = item.get("preflightMissingAnyOf")
        preflight_missing_env_summary = string_sequence_summary(preflight_missing_env)
        preflight_missing_any_of_summary = string_sequence_summary(preflight_missing_any_of)
        if (
            isinstance(preflight_missing_env, Sequence)
            and not isinstance(preflight_missing_env, str | bytes | bytearray)
            and preflight_missing_env_summary
        ) or (
            isinstance(preflight_missing_any_of, Sequence)
            and not isinstance(preflight_missing_any_of, str | bytes | bytearray)
            and preflight_missing_any_of_summary
        ):
            remediation: dict[str, object] = {
                "nextAction": "set release smoke preflight environment before tagging",
            }
            if isinstance(preflight_missing_env, Sequence) and not isinstance(
                preflight_missing_env, str | bytes | bytearray
            ):
                remediation["missingEnv"] = list(cast(Sequence[object], preflight_missing_env))
            if isinstance(preflight_missing_any_of, Sequence) and not isinstance(
                preflight_missing_any_of, str | bytes | bytearray
            ):
                missing_any_of = list(cast(Sequence[object], preflight_missing_any_of))
                remediation["missingEnvAnyOf"] = missing_any_of
                required_env_any_of = env_any_of_groups_from_summary(missing_any_of)
                if required_env_any_of:
                    remediation["requiredEnvAnyOf"] = required_env_any_of
            remediation_command = item.get("remediationCommand")
            if isinstance(remediation_command, str) and remediation_command.strip():
                remediation["remediationCommand"] = remediation_command.strip()
            preflight_env_template = item.get("preflightEnvTemplate")
            if isinstance(preflight_env_template, str) and preflight_env_template.strip():
                remediation["preflightEnvTemplate"] = preflight_env_template.strip()
            copy_release_env_handoff_fields(item, remediation)
            preflight_recommended_env = item.get("preflightRecommendedEnv")
            if isinstance(preflight_recommended_env, Sequence) and not isinstance(
                preflight_recommended_env, str | bytes | bytearray
            ):
                recommended_env = string_sequence_value(
                    cast(Sequence[object], preflight_recommended_env)
                )
                if recommended_env:
                    remediation["recommendedEnv"] = recommended_env
            return remediation
        missing_env_any_of = item.get("missingEnvAnyOf")
        if not isinstance(missing_env_any_of, Sequence) or isinstance(
            missing_env_any_of, str | bytes | bytearray
        ):
            continue
        remediation: dict[str, object] = {
            "nextAction": "set LangSmith credentials before tagging",
            "missingEnvAnyOf": list(cast(Sequence[object], missing_env_any_of)),
        }
        for item_key, recommendation_key in (
            ("requiredEnvAnyOf", "requiredEnvAnyOf"),
            ("recommendedEnv", "recommendedEnv"),
            ("liveSyncCommand", "nextActionCommand"),
        ):
            value = item.get(item_key)
            if value is not None:
                remediation[recommendation_key] = value
        return remediation
    item_remediation = blocking_item_remediation(items)
    if item_remediation:
        return item_remediation
    return {}


def copy_release_env_handoff_fields(
    item: Mapping[str, object], remediation: dict[str, object]
) -> None:
    for field_name in (
        "preflightEnvTemplateRefreshPath",
        "preflightEnvTemplateRefreshCommand",
        "preflightEnvFileCommand",
        "releaseSmokeEnvFileCommand",
        "remediationCommand",
    ):
        value = item.get(field_name)
        if isinstance(value, str) and value.strip():
            remediation[field_name] = value.strip()


def env_any_of_groups_from_summary(value: object) -> list[list[str]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    groups: list[list[str]] = []
    for raw_group in cast(Sequence[object], value):
        if not isinstance(raw_group, str):
            continue
        group = [item.strip() for item in raw_group.split("|") if item.strip()]
        if group:
            groups.append(group)
    return groups


def release_smoke_env_remediation(remediation: Mapping[str, object]) -> bool:
    return remediation.get("nextAction") == "set release smoke preflight environment before tagging"


def blocking_item_remediation(items: Sequence[Mapping[str, object]]) -> dict[str, object]:
    for item in items:
        if item.get("status") == "passed":
            continue
        remediation: dict[str, object] = {}
        for item_key, recommendation_key in (
            ("remediationCommand", "remediationCommand"),
            ("readinessReportArg", "readinessReportArg"),
        ):
            value = item.get(item_key)
            if isinstance(value, str) and value.strip():
                remediation[recommendation_key] = value.strip()
        if remediation:
            return remediation
    return {}


def missing_required_report_handoff(items: Sequence[Mapping[str, object]]) -> dict[str, object]:
    required_reports: list[str] = []
    readiness_report_args: list[str] = []
    for item in items:
        if item.get("failure") != "required report missing":
            continue
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            required_reports.append(name.strip())
        readiness_report_arg = item.get("readinessReportArg")
        if isinstance(readiness_report_arg, str) and readiness_report_arg.strip():
            readiness_report_args.append(readiness_report_arg.strip())
    handoff: dict[str, object] = {}
    normalized_reports = normalized_required_reports(required_reports)
    if normalized_reports:
        handoff["requiredReadinessReports"] = normalized_reports
    if readiness_report_args:
        handoff["readinessReportArg"] = " ".join(readiness_report_args)
    return handoff


def blocking_release_gate_handoff(items: Sequence[Mapping[str, object]]) -> dict[str, object]:
    for item in items:
        if item.get("status") == "passed" or item.get("name") != "hardening_suite":
            continue
        release_gate = item.get("releaseGate")
        if not isinstance(release_gate, Mapping):
            continue
        release_gate_mapping = cast(Mapping[object, object], release_gate)
        if release_gate_mapping.get("reason") != "dry_run_only":
            continue
        command = rag_ingestion_lifecycle_remediation_command()
        return {
            "nextAction": "run hardening_suite release gate before tagging",
            "nextActionCommand": command,
            "readinessReportArg": (
                f"--readiness-report hardening_suite={HARDENING_SUITE_REPORT_FILE}"
            ),
            "requiredReadinessReports": ["hardening_suite"],
            "readinessReports": {"hardening_suite": HARDENING_SUITE_REPORT_FILE},
        }
    return {}


def preferred_blocking_next_action(
    items: Sequence[Mapping[str, object]],
) -> dict[str, Any]:
    fallback = first_blocking_next_action(items)
    credential_preflight_action = first_missing_env_preflight_action(items)
    if credential_preflight_action:
        return credential_preflight_action
    feedback_review_action = first_feedback_review_next_action(items)
    if feedback_review_action:
        return feedback_review_action
    for preferred_id in ("sync-langsmith", "preflight-langsmith", "refresh-release-readiness"):
        for item in items:
            if item.get("status") == "passed":
                continue
            next_actions = item.get("nextActions")
            if not isinstance(next_actions, Sequence) or isinstance(
                next_actions, str | bytes | bytearray
            ):
                continue
            for action in cast(Sequence[object], next_actions):
                if not isinstance(action, Mapping):
                    continue
                action_mapping = cast(Mapping[object, object], action)
                action_id = action_mapping.get("id")
                if action_id == preferred_id:
                    return dict(cast(Mapping[str, Any], action_mapping))
    hardening_action = hardening_lifecycle_next_action(items)
    if hardening_action:
        return hardening_action
    return fallback


def first_missing_env_preflight_action(
    items: Sequence[Mapping[str, object]],
) -> dict[str, Any]:
    for item in items:
        if item.get("status") == "passed":
            continue
        next_actions = item.get("nextActions")
        if not isinstance(next_actions, Sequence) or isinstance(
            next_actions,
            str | bytes | bytearray,
        ):
            continue
        for action in cast(Sequence[object], next_actions):
            if not isinstance(action, Mapping):
                continue
            action_mapping = cast(Mapping[object, object], action)
            action_id = action_mapping.get("id")
            if action_id not in {"rerun-preflight-langsmith", "preflight-langsmith"}:
                continue
            missing_env_any_of = action_mapping.get("missingEnvAnyOf")
            if isinstance(missing_env_any_of, Sequence) and not isinstance(
                missing_env_any_of,
                str | bytes | bytearray,
            ):
                return dict(cast(Mapping[str, Any], action_mapping))
    return {}


def first_feedback_review_next_action(
    items: Sequence[Mapping[str, object]],
) -> dict[str, Any]:
    for item in items:
        if item.get("status") == "passed":
            continue
        next_actions = item.get("nextActions")
        if not isinstance(next_actions, Sequence) or isinstance(
            next_actions,
            str | bytes | bytearray,
        ):
            continue
        fallback_review_action: Mapping[str, object] | None = None
        for action in cast(Sequence[object], next_actions):
            if not isinstance(action, Mapping):
                continue
            action_mapping = cast(Mapping[object, object], action)
            action_id = action_mapping.get("id")
            if not isinstance(action_id, str):
                continue
            if action_id == "bulk-review-feedback" or action_id.startswith("bulk-review-feedback-"):
                return dict(cast(Mapping[str, Any], action_mapping))
            if action_id == "review-done":
                return dict(cast(Mapping[str, Any], action_mapping))
            if fallback_review_action is None and (
                action_id == "review-feedback" or action_id.startswith("review-feedback-")
            ):
                fallback_review_action = cast(Mapping[str, object], action_mapping)
        if fallback_review_action is not None:
            return dict(fallback_review_action)
    return {}


def hardening_lifecycle_next_action(
    items: Sequence[Mapping[str, object]],
) -> dict[str, Any]:
    for item in items:
        if item.get("status") == "passed":
            continue
        boundary = item.get("productCapabilityBoundary")
        if not isinstance(boundary, Mapping):
            continue
        boundary_mapping = cast(Mapping[object, object], boundary)
        missing_evidence = boundary_mapping.get("missingEvidence")
        if not isinstance(missing_evidence, Sequence) or isinstance(
            missing_evidence, str | bytes | bytearray
        ):
            continue
        missing_items = {
            evidence.strip()
            for evidence in cast(Sequence[object], missing_evidence)
            if isinstance(evidence, str) and evidence.strip()
        }
        if "rag_ingestion_lifecycle" not in missing_items:
            continue
        resolved_evidence = item.get("productBoundaryResolvedEvidence")
        resolved_items = {
            evidence.strip()
            for evidence in (
                cast(Sequence[object], resolved_evidence)
                if isinstance(resolved_evidence, Sequence)
                and not isinstance(resolved_evidence, str | bytes | bytearray)
                else ()
            )
            if isinstance(evidence, str) and evidence.strip()
        }
        if "rag_ingestion_lifecycle" in resolved_items:
            continue
        action: dict[str, Any] = {
            "id": "generate-hardening-suite",
            "command": rag_ingestion_lifecycle_remediation_command(),
        }
        for field_name in (
            "readinessCommand",
            "readinessReportArg",
            "requiredReadinessReports",
            "readinessReports",
        ):
            field_value = item.get(field_name)
            if field_value:
                action[
                    "releaseReadinessCommand" if field_name == "readinessCommand" else field_name
                ] = field_value
        if "readinessReportArg" not in action:
            action["readinessReportArg"] = (
                f"--readiness-report hardening_suite={HARDENING_SUITE_REPORT_FILE}"
            )
        if "requiredReadinessReports" not in action:
            action["requiredReadinessReports"] = ["hardening_suite"]
        if "readinessReports" not in action:
            action["readinessReports"] = {"hardening_suite": HARDENING_SUITE_REPORT_FILE}
        return action
    return {}


def first_blocking_next_action(
    items: Sequence[Mapping[str, object]],
) -> dict[str, Any]:
    for item in items:
        if item.get("status") == "passed":
            continue
        next_actions = item.get("nextActions")
        if not isinstance(next_actions, Sequence) or isinstance(
            next_actions, str | bytes | bytearray
        ):
            continue
        for action in cast(Sequence[object], next_actions):
            if isinstance(action, Mapping):
                return dict(cast(Mapping[str, Any], action))
    return {}


def readiness_warning_report_names(warnings: Sequence[Mapping[str, object]]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        name = warning.get("name")
        if not isinstance(name, str):
            continue
        normalized = name.strip()
        if normalized and normalized not in seen:
            names.append(normalized)
            seen.add(normalized)
    return names


def tag_selection(*, latest_tag: str, recommended_bump: str) -> dict[str, object]:
    normalized_latest_tag = latest_tag.strip()
    if not normalized_latest_tag:
        return {}
    match = re.fullmatch(
        r"v(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)",
        normalized_latest_tag,
    )
    if match is None:
        return {
            "latestTag": normalized_latest_tag,
            "tagSelectionReason": "latestTag is not a vMAJOR.MINOR.PATCH tag",
        }
    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch"))
    if recommended_bump == "minor":
        recommended_tag = f"v{major}.{minor + 1}.0"
        reason = "next minor tag after latestTag"
    elif recommended_bump == "patch":
        recommended_tag = f"v{major}.{minor}.{patch + 1}"
        reason = "next patch tag after latestTag"
    else:
        return {
            "latestTag": normalized_latest_tag,
            "tagSelectionReason": "no tag selected for current recommendation",
        }
    return {
        "latestTag": normalized_latest_tag,
        "recommendedTag": recommended_tag,
        "tagSelectionReason": reason,
    }


def minor_version_boundary_reports(items: Sequence[Mapping[str, object]]) -> list[str]:
    reports: list[str] = []
    for item in items:
        if item.get("status") != "passed":
            continue
        boundary = item.get("productCapabilityBoundary")
        if not isinstance(boundary, Mapping):
            continue
        typed_boundary = cast(Mapping[object, object], boundary)
        if product_capability_boundary_minor_eligible(typed_boundary):
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                reports.append(name)
    return reports


def minor_boundary_release_readiness_command(
    items: Sequence[Mapping[str, object]],
    report_names: Sequence[str],
) -> str:
    report_name_set = {name for name in report_names if name}
    for item in items:
        name = item.get("name")
        if not isinstance(name, str) or name not in report_name_set:
            continue
        for field_name in (
            "productBoundaryReadinessCommand",
            "releaseReadinessCommand",
            "readinessCommand",
        ):
            value = item.get(field_name)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def minor_boundary_remediation(items: Sequence[Mapping[str, object]]) -> dict[str, object]:
    blocked_reports: list[str] = []
    missing_evidence: list[str] = []
    remediation_command = ""
    for item in items:
        if item.get("status") != "passed":
            continue
        boundary = item.get("productCapabilityBoundary")
        if not isinstance(boundary, Mapping):
            continue
        typed_boundary = cast(Mapping[object, object], boundary)
        if product_capability_boundary_minor_eligible(typed_boundary):
            continue
        item_missing = string_sequence_value(typed_boundary.get("missingEvidence", ()))
        if not item_missing:
            continue
        name = item_name(item)
        if name:
            blocked_reports.append(name)
        for evidence in item_missing:
            if evidence not in missing_evidence:
                missing_evidence.append(evidence)
        if not remediation_command:
            remediation_action = minor_boundary_remediation_action(item, item_missing)
            if remediation_action.strip():
                remediation_command = remediation_action.strip()
    if not blocked_reports and not missing_evidence and not remediation_command:
        return {}
    remediation: dict[str, object] = {}
    if blocked_reports:
        remediation["minorBlockedReports"] = blocked_reports
    if missing_evidence:
        remediation["minorBoundaryMissingEvidence"] = missing_evidence
    if remediation_command:
        remediation["minorBoundaryRemediationCommand"] = remediation_command
    return remediation


def blocking_minor_boundary_remediation(
    items: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    blocked_reports: list[str] = []
    missing_evidence: list[str] = []
    remediation_command = ""
    for item in items:
        if item.get("status") == "passed":
            continue
        boundary = item.get("productCapabilityBoundary")
        if not isinstance(boundary, Mapping):
            continue
        typed_boundary = cast(Mapping[object, object], boundary)
        if product_capability_boundary_minor_eligible(typed_boundary):
            continue
        item_missing = string_sequence_value(typed_boundary.get("missingEvidence", ()))
        if item_missing:
            name = item_name(item)
            if name and name not in blocked_reports:
                blocked_reports.append(name)
        for evidence in item_missing:
            if evidence not in missing_evidence:
                missing_evidence.append(evidence)
        if item_missing and not remediation_command:
            remediation_action = minor_boundary_remediation_action(item, item_missing)
            if remediation_action.strip():
                remediation_command = remediation_action.strip()
    if not missing_evidence and not remediation_command:
        return {}
    remediation: dict[str, object] = {}
    if blocked_reports:
        remediation["minorBlockedReports"] = blocked_reports
    if missing_evidence:
        remediation["minorBoundaryMissingEvidence"] = missing_evidence
    if remediation_command:
        remediation["minorBoundaryRemediationCommand"] = remediation_command
    return remediation


def minor_boundary_resolved_handoff(items: Sequence[Mapping[str, object]]) -> dict[str, object]:
    resolved_evidence: list[str] = []
    resolved_by_reports: dict[str, str] = {}
    for item in items:
        for field_name in ("productBoundaryResolvedEvidence", "minorBoundaryResolvedEvidence"):
            for evidence in string_sequence_value(item.get(field_name, ())):
                if evidence not in resolved_evidence:
                    resolved_evidence.append(evidence)
        for field_name in ("productBoundaryResolvedByReports", "minorBoundaryResolvedByReports"):
            raw_resolved_by_reports = item.get(field_name)
            if not isinstance(raw_resolved_by_reports, Mapping):
                continue
            for key, value in cast(Mapping[object, object], raw_resolved_by_reports).items():
                if not isinstance(key, str) or not key.strip():
                    continue
                if not isinstance(value, str) or not value.strip():
                    continue
                resolved_by_reports[key.strip()] = value.strip()
    if not resolved_evidence and not resolved_by_reports:
        return {}
    handoff: dict[str, object] = {}
    if resolved_evidence:
        handoff["minorBoundaryResolvedEvidence"] = resolved_evidence
    if resolved_by_reports:
        handoff["minorBoundaryResolvedByReports"] = resolved_by_reports
    return handoff


def minor_boundary_remediation_action(
    item: Mapping[str, object],
    missing_evidence: Sequence[str],
) -> str:
    missing_items = {evidence for evidence in missing_evidence if evidence}
    if "rag_ingestion_lifecycle" in missing_items:
        return rag_ingestion_lifecycle_remediation_command()
    if missing_items and all(
        evidence.startswith("feedback_promotion.") for evidence in missing_items
    ):
        feedback_review_action = product_boundary_feedback_review_action(
            cast(Mapping[object, object], item)
        )
        if feedback_review_action:
            return feedback_review_action
    eval_apply_action = item.get("ragCandidateEvalApplyAction")
    if isinstance(eval_apply_action, str) and eval_apply_action.strip():
        return eval_apply_action.strip()
    return ""


def product_capability_boundary_minor_eligible(boundary: Mapping[object, object]) -> bool:
    capability = boundary.get("capability")
    evidence = boundary.get("evidence")
    missing_evidence = boundary.get("missingEvidence")
    return (
        boundary.get("minorEligible") is True
        and isinstance(capability, str)
        and bool(capability.strip())
        and isinstance(evidence, Sequence)
        and not isinstance(evidence, str | bytes | bytearray)
        and any(isinstance(item, str) and item.strip() for item in cast(Sequence[object], evidence))
        and (
            missing_evidence is None
            or (
                isinstance(missing_evidence, Sequence)
                and not isinstance(missing_evidence, str | bytes | bytearray)
                and not any(
                    isinstance(item, str) and item.strip()
                    for item in cast(Sequence[object], missing_evidence)
                )
            )
        )
    )


def readiness_item_names_with_status(
    items: Sequence[Mapping[str, object]],
    status: str,
) -> list[str]:
    return [
        name for item in items if item.get("status") == status for name in [item_name(item)] if name
    ]


def readiness_item_names(items: Sequence[Mapping[str, object]]) -> list[str]:
    return [name for item in items for name in [item_name(item)] if name]


def item_name(item: Mapping[str, object]) -> str:
    name = item.get("name")
    return name.strip() if isinstance(name, str) else ""


def release_readiness_warnings(items: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    for item in items:
        lifecycle = item.get("memoryMaintenanceLifecycle")
        if not isinstance(lifecycle, Mapping):
            continue
        dependency_warnings = cast(Mapping[object, object], lifecycle).get("dependencyWarnings")
        if not isinstance(dependency_warnings, Mapping):
            continue
        warning_mapping = cast(Mapping[object, object], dependency_warnings)
        if warning_mapping.get("status") != "review_required":
            continue
        findings = warning_mapping.get("findings")
        if not isinstance(findings, Sequence) or isinstance(findings, str | bytes | bytearray):
            continue
        item_name = item.get("name")
        warnings.append(
            {
                "name": item_name if isinstance(item_name, str) else "",
                "source": "memoryMaintenanceLifecycle.dependencyWarnings",
                "status": "review_required",
                "findings": list(cast(Sequence[object], findings)),
                "remediation": "review LangMem/trustcall/LangGraph dependency update",
                "reviewCommand": warning_mapping.get("reviewCommand"),
                "remediationCommand": warning_mapping.get("remediationCommand"),
            }
        )
    return warnings


def missing_required_report_items(
    items: Sequence[dict[str, object]],
    required_reports: Sequence[str],
) -> list[dict[str, object]]:
    return [
        missing_required_report_item(name) for name in missing_report_names(items, required_reports)
    ]


def missing_feedback_loop_report_items(
    items: Sequence[dict[str, object]],
    required_reports: Sequence[str],
) -> list[dict[str, object]]:
    return [
        missing_feedback_loop_report_item(name)
        for name in missing_report_names(items, required_reports)
    ]


def missing_report_names(
    items: Sequence[dict[str, object]],
    required_reports: Sequence[str],
) -> list[str]:
    present = {item.get("name") for item in items}
    return [name for name in normalized_required_reports(required_reports) if name not in present]


def item_required_report_names(items: Sequence[Mapping[str, object]]) -> list[str]:
    required: list[str] = []
    for item in items:
        value = item.get("requiredReadinessReports")
        if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
            continue
        required.extend(
            name.strip()
            for name in cast(Sequence[object], value)
            if isinstance(name, str) and name.strip()
        )
    return normalized_required_reports(required)


def normalized_required_reports(required_reports: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(name.strip() for name in required_reports if name.strip()))


def missing_required_report_item(name: str) -> dict[str, object]:
    item: dict[str, object] = {
        "name": name,
        "ok": False,
        "status": "skipped",
        "scope": "",
        "artifact": "",
        "owner": "",
        "mode": "",
        "failure": "required report missing",
    }
    item.update(missing_report_remediation_fields(name))
    return item


def missing_report_remediation_fields(name: str) -> dict[str, object]:
    if name == "smoke_run":
        return {
            "remediationCommand": (
                "uv run reactor-release-smoke-run "
                "--plan reports/release/release-smoke-plan.local.json "
                "--preflight-file reports/release/release-smoke-preflight.local.json "
                "--env-file reports/release/release-smoke-preflight.local.env "
                "--preflight-only "
                "--readiness-output reports/release-readiness.json"
            ),
            "readinessReportArg": "--readiness-report smoke_run=reports/release-smoke-run.json",
        }
    if name == "release_evidence":
        return {
            "remediationCommand": (
                "uv run reactor-release-smoke-run "
                "--plan reports/release/release-smoke-plan.local.json "
                "--report-file reports/release-smoke-run.json "
                "--verified-at <ISO-8601> "
                "--evidence-output reports/release-evidence.json"
            ),
            "readinessReportArg": (
                "--readiness-report release_evidence=reports/release-evidence.json"
            ),
        }
    if name == "hardening_suite":
        return {
            "remediationCommand": (
                "uv run reactor-hardening-suite --report-file reports/hardening-suite.json"
            ),
            "readinessReportArg": (
                "--readiness-report hardening_suite=reports/hardening-suite.json"
            ),
        }
    if name == "observability_smoke":
        return {
            "remediationCommand": (
                "uv run reactor-observability-smoke --output reports/observability-smoke.json"
            ),
            "readinessReportArg": (
                "--readiness-report observability_smoke=reports/observability-smoke.json"
            ),
        }
    if name != "langsmith_eval_sync":
        return {}
    return {
        "remediationCommand": (
            "uv run reactor-langsmith-eval-sync "
            "--suite-file tests/fixtures/agent-eval/regression-suite.json "
            "--dataset-name reactor-regression "
            "--report-file reports/langsmith-eval-sync.json "
            "--required-readiness-report langsmith_eval_sync "
            "--readiness-report langsmith_eval_sync=reports/langsmith-eval-sync.json"
        ),
        "readinessReportArg": (
            "--readiness-report langsmith_eval_sync=reports/langsmith-eval-sync.json"
        ),
    }


def missing_feedback_loop_report_item(name: str) -> dict[str, object]:
    item = missing_required_report_item(name)
    item["failure"] = "feedback loop gate missing"
    return item


def feedback_loop_required_report_names(items: Sequence[dict[str, object]]) -> list[str]:
    required: list[str] = []
    for item in items:
        if item.get("name") != "observability_smoke" or item.get("status") != "passed":
            continue
        feedback_loop = item.get("feedbackLoop")
        if not isinstance(feedback_loop, Mapping):
            continue
        if feedback_loop.get("offlineGate") == "langsmith_eval_dataset_sync":
            required.append("langsmith_eval_sync")
    return normalized_required_reports(required)


def apply_feedback_loop_consistency(
    items: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    expected_source_suite = feedback_loop_source_suite(items)
    expected_promoted_case_ids = feedback_loop_promoted_case_ids(items)
    if not expected_source_suite and not expected_promoted_case_ids:
        return [dict(item) for item in items]
    checked_items: list[dict[str, object]] = []
    for item in items:
        checked_item = dict(item)
        is_passed_langsmith_sync = (
            checked_item.get("name") == "langsmith_eval_sync"
            and checked_item.get("status") == "passed"
        )
        if is_passed_langsmith_sync:
            if expected_source_suite and checked_item.get("sourceSuite") != expected_source_suite:
                checked_item["ok"] = False
                checked_item["status"] = "failed"
                checked_item["failure"] = "feedback loop source suite mismatch"
            elif expected_promoted_case_ids and not langsmith_sync_contains_cases(
                checked_item,
                expected_promoted_case_ids,
            ):
                checked_item["ok"] = False
                checked_item["status"] = "failed"
                checked_item["failure"] = "feedback loop promoted case mismatch"
            elif (
                expected_promoted_case_ids
                and not langsmith_sync_feedback_promotion_contains_cases(
                    checked_item,
                    expected_promoted_case_ids,
                )
            ):
                checked_item["ok"] = False
                checked_item["status"] = "failed"
                checked_item["failure"] = "feedback loop promotion evidence missing"
        checked_items.append(checked_item)
    return checked_items


def feedback_loop_source_suite(items: Sequence[dict[str, object]]) -> str:
    for item in items:
        if item.get("name") != "observability_smoke" or item.get("status") != "passed":
            continue
        feedback_loop = item.get("feedbackLoop")
        if not isinstance(feedback_loop, Mapping):
            continue
        feedback_loop_mapping = cast(Mapping[str, object], feedback_loop)
        if feedback_loop_mapping.get("offlineGate") != "langsmith_eval_dataset_sync":
            continue
        source_suite = feedback_loop_mapping.get("sourceSuite")
        if isinstance(source_suite, str) and source_suite.strip():
            return source_suite
    return ""


def feedback_loop_promoted_case_ids(items: Sequence[dict[str, object]]) -> list[str]:
    for item in items:
        if item.get("name") != "observability_smoke" or item.get("status") != "passed":
            continue
        feedback_loop = item.get("feedbackLoop")
        if not isinstance(feedback_loop, Mapping):
            continue
        feedback_loop_mapping = cast(Mapping[str, object], feedback_loop)
        if feedback_loop_mapping.get("offlineGate") != "langsmith_eval_dataset_sync":
            continue
        promoted_case_ids = feedback_loop_mapping.get("promotedCaseIds")
        if isinstance(promoted_case_ids, Sequence) and not isinstance(
            promoted_case_ids, str | bytes | bytearray
        ):
            return [
                case_id
                for case_id in cast(Sequence[object], promoted_case_ids)
                if isinstance(case_id, str) and case_id.strip()
            ]
    return []


def langsmith_sync_contains_cases(
    item: Mapping[str, object],
    expected_case_ids: Sequence[str],
) -> bool:
    case_ids = item.get("caseIds")
    if not isinstance(case_ids, Sequence) or isinstance(case_ids, str | bytes | bytearray):
        return False
    synced_case_ids = {
        case_id for case_id in cast(Sequence[object], case_ids) if isinstance(case_id, str)
    }
    return set(expected_case_ids).issubset(synced_case_ids)


def langsmith_sync_feedback_promotion_contains_cases(
    item: Mapping[str, object],
    expected_case_ids: Sequence[str],
) -> bool:
    feedback_promotion = item.get("feedbackPromotion")
    if not isinstance(feedback_promotion, Mapping):
        return False
    promotion_mapping = cast(Mapping[object, object], feedback_promotion)
    promoted_case_ids = promotion_mapping.get("caseIds")
    if not isinstance(promoted_case_ids, Sequence) or isinstance(
        promoted_case_ids, str | bytes | bytearray
    ):
        return False
    promoted_case_id_set = {
        case_id for case_id in cast(Sequence[object], promoted_case_ids) if isinstance(case_id, str)
    }
    return set(expected_case_ids).issubset(promoted_case_id_set)


def readiness_status(*, total: int, failed: int, skipped: int, blocked: int = 0) -> str:
    if failed > 0:
        return "failed"
    if total == 0 or skipped > 0 or blocked > 0:
        return "blocked"
    return "passed"


def readiness_item(*, name: str, path: Path) -> dict[str, object]:
    try:
        report = read_json_object(path)
    except FileNotFoundError:
        return failed_report_file_item(
            name=name, path=path, failure="readiness report file missing"
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        return failed_item(name=name, path=path, failure=str(error))
    return readiness_item_from_report(name=name, report=report, artifact=str(path))


def readiness_item_from_report(
    *,
    name: str,
    report: dict[str, Any],
    artifact: str,
) -> dict[str, object]:
    ok = report.get("ok")
    if not isinstance(ok, bool):
        return failed_item(name=name, path=Path(artifact), failure="report missing boolean ok")

    if is_langsmith_preflight_report(name=name, report=report):
        return langsmith_preflight_not_release_gate_item(report=report, artifact=artifact)

    status = string_field(report, "status")
    if status not in {"passed", "failed", "skipped", "blocked"}:
        return failed_item(name=name, path=Path(artifact), failure="report missing valid status")
    if ok != (status == "passed"):
        return failed_item(name=name, path=Path(artifact), failure="report ok/status mismatch")

    evidence = mapping_field(report, "evidence")
    evidence_artifact = string_field(evidence, "artifact") or artifact
    item: dict[str, object] = {
        "name": name,
        "ok": ok,
        "status": status,
        "scope": string_field(report, "scope"),
        "artifact": evidence_artifact,
        "owner": string_field(evidence, "owner"),
        "mode": string_field(evidence, "mode"),
    }
    if name == "langsmith_eval_sync":
        item["reportFile"] = artifact
    item.update(preserved_evidence_fields(evidence))
    item.update(preserved_report_fields(report, existing=item))
    if name == "preflight":
        ready_local_contract_actions = ready_local_contract_actions_from_preflight(report)
        if ready_local_contract_actions:
            item["readyLocalContractActions"] = ready_local_contract_actions
    item.update(derived_evidence_fields(evidence))
    contract_failure = readiness_contract_failure(
        name=name,
        item=item,
    ) or readiness_item_action_state_contract_failure(item)
    if contract_failure is not None:
        item["ok"] = False
        item["status"] = "failed"
        item["failure"] = contract_failure
    if status == "skipped":
        skipped_reason = string_field(report, "error") or release_gate_reason(
            item.get("releaseGate")
        )
        if skipped_reason:
            item["failure"] = skipped_reason
    if status == "blocked":
        blocked_reason = string_field(report, "error") or release_gate_reason(
            item.get("releaseGate")
        )
        if blocked_reason:
            item["failure"] = blocked_reason
    if status == "failed":
        item["failure"] = string_field(report, "error") or "report status failed"
    return item


def is_langsmith_preflight_report(*, name: str, report: Mapping[str, Any]) -> bool:
    return (
        name == "langsmith_eval_sync"
        and report.get("scope") == "langsmith_eval_dataset_sync_preflight"
    )


def ready_local_contract_actions_from_preflight(
    report: Mapping[str, object],
) -> list[dict[str, str]]:
    steps = report.get("steps")
    if not isinstance(steps, Sequence) or isinstance(steps, str | bytes | bytearray):
        return []
    actions: list[dict[str, str]] = []
    for step in cast(Sequence[object], steps):
        if not isinstance(step, Mapping):
            continue
        step_mapping = cast(Mapping[str, object], step)
        if step_mapping.get("status") != "ready":
            continue
        if step_mapping.get("evidence_scope") != "local_contract":
            continue
        code = string_field(dict(step_mapping), "code")
        command_parts = string_sequence_value(step_mapping.get("command"))
        if not code or not command_parts:
            continue
        action: dict[str, str] = {
            "id": f"run-{action_id_slug(code)}",
            "code": code,
            "command": shlex.join(command_parts),
        }
        evidence_uri = string_field(dict(step_mapping), "evidence_uri")
        if evidence_uri:
            action["evidenceUri"] = evidence_uri
        actions.append(action)
    return actions


def action_id_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").lower()
    return slug or "action"


def langsmith_preflight_not_release_gate_item(
    *,
    report: dict[str, Any],
    artifact: str,
) -> dict[str, object]:
    item: dict[str, object] = {
        "name": "langsmith_eval_sync",
        "ok": False,
        "status": "failed",
        "scope": "langsmith_eval_dataset_sync_preflight",
        "artifact": artifact,
        "owner": "",
        "mode": "",
        "reportFile": artifact,
        "failure": "langsmith_preflight_only_not_release_gate",
        "releaseGate": {
            "status": "blocked",
            "blocksReleaseReadiness": True,
            "reason": "langsmith_preflight_only_not_release_gate",
            "requiredReport": "langsmith_eval_sync",
            "remediation": [
                "run_reactor_langsmith_eval_sync_without_preflight_only",
                "include_passed_langsmith_eval_sync_report_in_release_readiness",
            ],
        },
    }
    for key in (
        "datasetName",
        "sourceSuite",
        "requiredEnvAnyOf",
        "missingEnvAnyOf",
        "recommendedEnv",
        "releaseReadinessFile",
        "readinessReportArg",
        "requiredReadinessReports",
        "readinessReports",
        "readyNextActionIds",
        "blockedNextActionIds",
        "nextActions",
        "liveSyncCommand",
    ):
        value = report.get(key)
        if value is not None:
            item[key] = value
    return item


def failed_item(*, name: str, path: Path, failure: str) -> dict[str, object]:
    return {
        "name": name,
        "ok": False,
        "status": "failed",
        "scope": "",
        "artifact": str(path),
        "owner": "",
        "mode": "",
        "failure": failure,
    }


def failed_report_file_item(*, name: str, path: Path, failure: str) -> dict[str, object]:
    item = failed_item(name=name, path=path, failure=failure)
    item.update(missing_report_remediation_fields(name))
    if "readinessReportArg" in item:
        item["readinessReportArg"] = f"--readiness-report {name}={path}"
    return item


def release_gate_reason(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    release_gate = cast(Mapping[str, object], value)
    reason = release_gate.get("reason")
    return reason.strip() if isinstance(reason, str) and reason.strip() else ""


def release_gate_summary(item: Mapping[object, object]) -> str:
    release_gate = item.get("releaseGate")
    if not isinstance(release_gate, Mapping):
        return ""
    release_gate_mapping = cast(Mapping[object, object], release_gate)
    parts: list[str] = []
    status = release_gate_mapping.get("status")
    if isinstance(status, str) and status.strip():
        parts.append(f"releaseGate={status.strip()}")
    reason = release_gate_mapping.get("reason")
    if isinstance(reason, str) and reason.strip():
        parts.append(f"gateReason={reason.strip()}")
    remediation_command = release_gate_mapping.get("remediationCommand")
    if isinstance(remediation_command, str) and remediation_command.strip():
        parts.append(
            f"releaseGateRemediationCommand={summary_quoted_value(remediation_command.strip())}"
        )
    remediation = release_gate_mapping.get("remediation")
    if isinstance(remediation, Sequence) and not isinstance(remediation, str | bytes | bytearray):
        remediation_items = [
            item.strip()
            for item in cast(Sequence[object], remediation)
            if isinstance(item, str) and item.strip()
        ]
        if remediation_items:
            parts.append(f"releaseNext={remediation_items[0]}")
            parts.append(f"releasePlan={','.join(remediation_items)}")
    return " ".join(parts)


def read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"readiness report must contain a JSON object: {path}")
    return cast(dict[str, Any], payload)


def string_field(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    return value.strip() if isinstance(value, str) else ""


def mapping_field(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    value = mapping.get(key)
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def preserved_evidence_fields(evidence: dict[str, Any]) -> dict[str, object]:
    preserved: dict[str, object] = {}
    for key in PRESERVED_EVIDENCE_FIELDS:
        value = evidence.get(key)
        if value is None:
            continue
        if key == "observabilityTarget" and observability_target_has_secret(value):
            continue
        preserved[key] = value
    return preserved


def preserved_report_fields(
    report: dict[str, Any],
    *,
    existing: Mapping[str, object],
) -> dict[str, object]:
    preserved: dict[str, object] = {}
    for key in (
        "failure",
        "releaseGate",
        "requiredEnvAnyOf",
        "readyNextActionIds",
        "blockedNextActionIds",
        "nextActions",
        "envFile",
        "releaseGateReason",
    ):
        if key in existing:
            continue
        value = report.get(key)
        if value is not None:
            preserved[key] = value
    return preserved


def derived_evidence_fields(evidence: dict[str, Any]) -> dict[str, object]:
    derived: dict[str, object] = {}
    tool_output_guard = tool_output_guard_from_context_manifest(evidence.get("contextManifest"))
    if tool_output_guard:
        derived["toolOutputGuard"] = tool_output_guard
    if string_field(evidence, "ragCandidateEvalApplyAction"):
        rag_candidate_action = ""
    else:
        rag_candidate_action = rag_candidate_eval_apply_action(evidence)
    if rag_candidate_action:
        derived["ragCandidateEvalApplyAction"] = rag_candidate_action
    product_boundary = product_capability_boundary(evidence)
    if product_boundary:
        derived["productCapabilityBoundary"] = product_boundary
    return derived


def product_capability_boundary(evidence: Mapping[str, object]) -> dict[str, object]:
    if evidence.get("sourceSuite") != RAG_CANDIDATE_SOURCE_SUITE:
        return {}
    if not isinstance(evidence.get("ragIngestionLifecycle"), Mapping):
        return {}
    if not isinstance(evidence.get("feedbackReviewQueue"), Mapping):
        return {}
    if not isinstance(evidence.get("readinessCommand"), str):
        return {}
    trace_grading = evidence.get("traceGrading")
    if not isinstance(trace_grading, Mapping):
        return {}
    typed_trace_grading = cast(Mapping[object, object], trace_grading)
    if typed_trace_grading.get("failed") != 0:
        return {}
    graded_runs = typed_trace_grading.get("gradedRuns")
    if not isinstance(graded_runs, int) or isinstance(graded_runs, bool) or graded_runs < 1:
        return {}
    missing_promotion_coverage = missing_eval_promotion_apply_coverage(
        evidence.get("promotionCoverage")
    )
    missing_citation_workflow = missing_rag_citation_workflow_evidence(
        evidence.get("contextManifestDiagnostics"),
        evidence.get("caseIds"),
    )
    missing_feedback_promotion = missing_feedback_promotion_review_evidence(
        evidence.get("feedbackPromotion") or evidence.get("feedbackReviewQueue"),
        case_ids=evidence.get("caseIds"),
        promotion_coverage=evidence.get("promotionCoverage"),
    )
    missing_boundary_evidence = [
        *missing_promotion_coverage,
        *missing_citation_workflow,
        *missing_feedback_promotion,
    ]
    if missing_boundary_evidence:
        return {
            "minorEligible": False,
            "capability": "rag_ingest_to_feedback_eval_langsmith_readiness",
            "evidence": [
                "rag_ingestion_lifecycle",
                "rag_ingestion_candidate_feedback_queue",
                "langsmith_trace_grading",
                "release_readiness_command",
            ],
            "missingEvidence": missing_boundary_evidence,
        }
    return {
        "minorEligible": True,
        "capability": "rag_ingest_to_feedback_eval_langsmith_readiness",
        "evidence": [
            "rag_ingestion_lifecycle",
            "rag_ingestion_candidate_feedback_queue",
            "eval_promotion_apply_coverage",
            "feedback_promotion.reviewed_feedback",
            "feedback_promotion_review",
            "context_manifest_diagnostics_citation_workflow",
            "langsmith_trace_grading",
            "release_readiness_command",
        ],
    }


def eval_promotion_apply_coverage_passed(promotion_coverage: object) -> bool:
    return not missing_eval_promotion_apply_coverage(promotion_coverage)


def missing_eval_promotion_apply_coverage(promotion_coverage: object) -> list[str]:
    if not isinstance(promotion_coverage, Mapping):
        return ["eval_promotion_apply_coverage"]
    coverage = cast(Mapping[object, object], promotion_coverage)
    return [
        f"eval_promotion_apply_coverage.{key}"
        for key in (
            "sourceRunIdPresent",
            "runFixturePresent",
            "runFixtureMatchedCase",
            "runContextDiagnosticsPresent",
            "requiredSourceRunId",
            "requiredRunFile",
            "requiredContextDiagnostics",
            "contextCitationEvalCaseIdMatched",
            "contextCitationWorkflowTagMatched",
        )
        if coverage.get(key) is not True
    ]


def missing_rag_citation_workflow_evidence(
    diagnostics: object,
    case_ids: object,
) -> list[str]:
    missing: list[str] = []
    if not isinstance(diagnostics, Mapping):
        return [
            "context_manifest_diagnostics.citationWorkflowEvalCaseIds",
            "context_manifest_diagnostics.citationWorkflowTags",
        ]
    diagnostics_mapping = cast(Mapping[object, object], diagnostics)
    workflow_case_ids = string_items(diagnostics_mapping.get("citationWorkflowEvalCaseIds"))
    workflow_tags = string_items(diagnostics_mapping.get("citationWorkflowTags"))
    expected_case_ids = string_items(case_ids)
    if not workflow_case_ids or (
        expected_case_ids and not set(expected_case_ids).issubset(workflow_case_ids)
    ):
        missing.append("context_manifest_diagnostics.citationWorkflowEvalCaseIds")
    if not any(tag.startswith("rag-candidate:") for tag in workflow_tags):
        missing.append("context_manifest_diagnostics.citationWorkflowTags")
    return missing


def missing_feedback_promotion_review_evidence(
    feedback_promotion: object,
    *,
    case_ids: object,
    promotion_coverage: object,
) -> list[str]:
    if not isinstance(feedback_promotion, Mapping):
        return ["feedback_promotion.reviewed_feedback"]
    promotion = cast(Mapping[object, object], feedback_promotion)
    missing: list[str] = []
    review_ids = string_items(promotion.get("feedbackReviewIds"))
    feedback_source_counts = promotion.get("feedbackSourceCounts")
    has_review_queue_counts = isinstance(feedback_source_counts, Mapping) and any(
        isinstance(count, int) and not isinstance(count, bool) and count > 0
        for count in cast(Mapping[object, object], feedback_source_counts).values()
    )
    if not review_ids and has_review_queue_counts:
        closure_missing = missing_feedback_promotion_review_closure(promotion)
        return [] if not closure_missing else ["feedback_promotion.reviewed_feedback"]
    if not review_ids and not has_review_queue_counts:
        missing.append("feedback_promotion.feedbackReviewIds")
    if missing:
        return missing
    closure_missing = missing_feedback_promotion_review_closure(promotion)
    if closure_missing:
        return closure_missing
    promotion_case_ids = string_items(case_ids)
    if langsmith_feedback_promotion_contract_failure(
        feedback_promotion=cast(Mapping[str, object], feedback_promotion),
        case_id_set=set(promotion_case_ids),
        promotion_coverage=promotion_coverage,
    ):
        missing.append("feedback_promotion.contract")
    return missing


def missing_feedback_promotion_review_closure(
    promotion: Mapping[object, object],
) -> list[str]:
    typed_promotion = {key: value for key, value in promotion.items() if isinstance(key, str)}
    if feedback_promotion_review_closed(typed_promotion):
        return []
    missing: list[str] = []
    review_status = promotion.get("reviewStatus")
    if not isinstance(review_status, str) or review_status.strip().lower() != "done":
        missing.append("feedback_promotion.reviewStatus")
    review_tags = string_items(promotion.get("reviewTags"))
    normalized_tags = {tag.strip().lower() for tag in review_tags if tag.strip()}
    if not {"promoted", "langsmith"}.issubset(normalized_tags):
        missing.append("feedback_promotion.reviewTags")
    review_note = promotion.get("reviewNote")
    if (
        not isinstance(review_note, str)
        or review_note.strip() != RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE
    ):
        missing.append("feedback_promotion.reviewNote")
    return missing


def string_items(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [
        item.strip()
        for item in cast(Sequence[object], value)
        if isinstance(item, str) and item.strip()
    ]


def apply_cross_report_product_boundary(
    items: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    lifecycle_report_name, lifecycle = passed_rag_ingestion_lifecycle_report(items)
    if not lifecycle:
        return list(items)
    updated_items: list[dict[str, object]] = []
    for item in items:
        if item.get("status") != "passed":
            updated_items.append(
                item_with_resolved_rag_ingestion_lifecycle(
                    item,
                    source_report=lifecycle_report_name,
                )
            )
            continue
        merged_item = dict(item)
        merged_item["ragIngestionLifecycle"] = lifecycle
        product_boundary = product_capability_boundary(merged_item)
        if product_boundary:
            merged_item["productCapabilityBoundary"] = product_boundary
            merged_item.pop("ragIngestionLifecycle", None)
            updated_items.append(merged_item)
            continue
        updated_items.append(item)
    return updated_items


def passed_rag_ingestion_lifecycle_report(
    items: Sequence[Mapping[str, object]],
) -> tuple[str, dict[str, object]]:
    for item in items:
        if item.get("status") != "passed":
            continue
        lifecycle = item.get("ragIngestionLifecycle")
        if not isinstance(lifecycle, Mapping):
            continue
        name = item.get("name")
        source_report = name.strip() if isinstance(name, str) and name.strip() else "unknown"
        return source_report, dict(cast(Mapping[str, object], lifecycle))
    return "", {}


def passed_rag_ingestion_lifecycle(
    items: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    return passed_rag_ingestion_lifecycle_report(items)[1]


def item_with_resolved_rag_ingestion_lifecycle(
    item: dict[str, object],
    *,
    source_report: str,
) -> dict[str, object]:
    boundary = item.get("productCapabilityBoundary")
    if not isinstance(boundary, Mapping):
        return item
    boundary_mapping = cast(Mapping[object, object], boundary)
    raw_missing_evidence = boundary_mapping.get("missingEvidence")
    if not isinstance(raw_missing_evidence, Sequence) or isinstance(
        raw_missing_evidence, str | bytes | bytearray
    ):
        return item
    missing_items = {
        evidence.strip()
        for evidence in cast(Sequence[object], raw_missing_evidence)
        if isinstance(evidence, str) and evidence.strip()
    }
    if "rag_ingestion_lifecycle" not in missing_items:
        return item
    resolved_item = dict(item)
    resolved_boundary = dict(cast(Mapping[str, object], boundary_mapping))
    remaining_missing = [
        evidence.strip()
        for evidence in cast(Sequence[object], raw_missing_evidence)
        if isinstance(evidence, str)
        and evidence.strip()
        and evidence.strip() != "rag_ingestion_lifecycle"
    ]
    if remaining_missing:
        resolved_boundary["missingEvidence"] = remaining_missing
    else:
        resolved_boundary.pop("missingEvidence", None)
    resolved_item["productCapabilityBoundary"] = resolved_boundary
    resolved_item["productBoundaryResolvedEvidence"] = ["rag_ingestion_lifecycle"]
    resolved_item["productBoundaryResolvedByReports"] = {
        "rag_ingestion_lifecycle": source_report or "unknown"
    }
    expected_resolved_by_reports = item.get("productBoundaryExpectedResolvedByReports")
    if isinstance(expected_resolved_by_reports, Mapping):
        resolved_item["productBoundaryExpectedResolvedByReports"] = dict(
            cast(Mapping[str, object], expected_resolved_by_reports)
        )
    resolved_item = without_resolved_hardening_next_actions(resolved_item)
    if (
        resolved_item.get("status") == "failed"
        and resolved_item.get("failure") == "langsmith eval sync contract missing"
        and readiness_contract_failure(
            name=str(resolved_item.get("name") or ""),
            item=resolved_item,
        )
        is None
    ):
        resolved_item["ok"] = True
        resolved_item["status"] = "passed"
        resolved_item.pop("failure", None)
    return resolved_item


def without_resolved_hardening_next_actions(item: dict[str, object]) -> dict[str, object]:
    next_actions = item.get("nextActions")
    if not isinstance(next_actions, Sequence) or isinstance(next_actions, str | bytes | bytearray):
        return item
    filtered_actions: list[object] = []
    removed = False
    for action in cast(Sequence[object], next_actions):
        if isinstance(action, Mapping):
            action_mapping = cast(Mapping[object, object], action)
            action_id = action_mapping.get("id")
            if action_id == "generate-hardening-suite":
                removed = True
                continue
        filtered_actions.append(cast(object, action))
    if not removed:
        return item
    updated_item = dict(item)
    updated_item["nextActions"] = filtered_actions
    updated_item.pop("readyNextActionIds", None)
    updated_item.pop("blockedNextActionIds", None)
    updated_item.pop("nextActionStates", None)
    return readiness_item_with_derived_action_state_fields(updated_item)


def rag_candidate_eval_apply_action(evidence: Mapping[str, object]) -> str:
    if evidence.get("sourceSuite") != RAG_CANDIDATE_SOURCE_SUITE:
        return ""
    case_ids = evidence.get("caseIds")
    if not isinstance(case_ids, Sequence) or isinstance(case_ids, str | bytes | bytearray):
        return ""
    typed_case_ids: list[str] = []
    for case_id_value in cast(Sequence[object], case_ids):
        if isinstance(case_id_value, str):
            typed_case_ids.append(case_id_value)
    if len(typed_case_ids) != 1:
        return ""
    case_id = typed_case_ids[0]
    case_source_run_ids = evidence.get("caseSourceRunIds")
    if not isinstance(case_source_run_ids, Mapping):
        return ""
    source_run_id = cast(Mapping[object, object], case_source_run_ids).get(case_id)
    if not isinstance(source_run_id, str) or not source_run_id.strip():
        return ""
    return rag_candidate_eval_apply_action_command(
        source_run_id=source_run_id,
        case_id=case_id,
        source_suite=RAG_CANDIDATE_SOURCE_SUITE,
        dataset_name="reactor-rag-ingestion-candidate",
        feedback_source=rag_candidate_feedback_source(evidence),
        extra_tags=rag_candidate_expected_citation_tags(evidence),
    )


def rag_candidate_expected_citation_tags(evidence: Mapping[str, object]) -> list[str]:
    review_queue = evidence.get("feedbackReviewQueue")
    if not isinstance(review_queue, Mapping):
        return []
    expected_citation_counts = cast(Mapping[object, object], review_queue).get(
        "expectedCitationCounts"
    )
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


def rag_candidate_feedback_source(evidence: Mapping[str, object]) -> str:
    review_queue = evidence.get("feedbackReviewQueue")
    if not isinstance(review_queue, Mapping):
        return ""
    source_counts = cast(Mapping[object, object], review_queue).get("feedbackSourceCounts")
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


def tool_output_guard_from_context_manifest(context_manifest: object) -> dict[str, object]:
    if not isinstance(context_manifest, Mapping):
        return {}
    manifest = cast(Mapping[str, object], context_manifest)
    sections = manifest.get("sections")
    if not isinstance(sections, Sequence) or isinstance(sections, str | bytes | bytearray):
        return {}
    for section in cast(Sequence[object], sections):
        if not isinstance(section, Mapping):
            continue
        section_mapping = cast(Mapping[str, object], section)
        if section_mapping.get("name") != "tool_outputs":
            continue
        metadata = section_mapping.get("metadata")
        return dict(cast(Mapping[str, object], metadata)) if isinstance(metadata, Mapping) else {}
    return {}


def parse_report_input(value: str) -> ReportInput:
    name, separator, report_path = value.partition("=")
    if not separator or not name.strip() or not report_path.strip():
        raise ValueError("--report must use name=path")
    return name.strip(), Path(report_path.strip())


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate Reactor release evidence reports into readiness JSON."
    )
    parser.add_argument(
        "--report",
        action="append",
        default=[],
        help="Named report input in name=path form.",
    )
    parser.add_argument(
        "--required-report",
        action="append",
        default=[],
        help="Report name required for readiness.",
    )
    parser.add_argument(
        "--latest-tag",
        default="",
        help="Latest stable version tag, used to select the next concrete tag.",
    )
    parser.add_argument("--output", required=True, help="Path to write readiness JSON.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report_inputs = [parse_report_input(value) for value in cast(list[str], args.report)]
    seen_report_names: set[str] = set()
    for name, _ in report_inputs:
        if name in seen_report_names:
            raise ValueError(f"duplicate --report name: {name}")
        seen_report_names.add(name)
    report = build_release_readiness_report(
        report_inputs,
        required_reports=cast(list[str], args.required_report),
        latest_tag=str(args.latest_tag),
    )
    output_path = Path(str(args.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        write_report(report, output)
    if not report["ok"]:
        print(readiness_failure_summary(report), file=sys.stderr)
    return 0 if report["ok"] else 1


def readiness_failure_summary(report: Mapping[str, object]) -> str:
    summary = f"release_readiness status={report.get('status')}"
    missing_reports = string_sequence_summary(report.get("missingReports"))
    if missing_reports:
        summary = f"{summary} missingReports={missing_reports}"
    lines = [summary]
    tag_summary = tag_recommendation_summary(report.get("tagRecommendation"))
    if tag_summary:
        lines.append(tag_summary)
    items = report.get("items")
    if isinstance(items, Sequence) and not isinstance(items, str | bytes | bytearray):
        for item in cast(Sequence[object], items):
            if not isinstance(item, Mapping):
                continue
            item_mapping = cast(Mapping[object, object], item)
            if item_mapping.get("status") == "passed":
                continue
            name = item_mapping.get("name") or "unknown"
            status = item_mapping.get("status") or "unknown"
            failure = item_mapping.get("failure") or "readiness item not passed"
            feedback_review_ids = feedback_review_ids_summary(item_mapping)
            suffix = f" feedbackReviewIds={feedback_review_ids}" if feedback_review_ids else ""
            dataset_name = item_string_summary(item_mapping, "datasetName")
            if dataset_name:
                suffix = f"{suffix} datasetName={dataset_name}"
            report_file = item_string_summary(item_mapping, "reportFile")
            if report_file:
                suffix = f"{suffix} reportFile={summary_quoted_value(report_file)}"
            case_file = item_string_summary(item_mapping, "caseFile")
            if case_file:
                suffix = f"{suffix} caseFile={summary_quoted_value(case_file)}"
            run_file = item_string_summary(item_mapping, "runFile")
            if run_file:
                suffix = f"{suffix} runFile={summary_quoted_value(run_file)}"
            env_file = item_string_summary(item_mapping, "envFile")
            if env_file:
                suffix = f"{suffix} envFile={summary_quoted_value(env_file)}"
            preflight_file = item_string_summary(item_mapping, "preflightFile")
            if preflight_file:
                suffix = f"{suffix} preflightFile={summary_quoted_value(preflight_file)}"
            preflight_env_template = item_string_summary(item_mapping, "preflightEnvTemplate")
            if preflight_env_template:
                suffix = (
                    f"{suffix} preflightEnvTemplate={summary_quoted_value(preflight_env_template)}"
                )
            for field_name in (
                "replatformReadinessFile",
                "smokePlanFile",
                "releaseEvidenceFile",
                "releaseReadinessFile",
            ):
                field_value = item_string_summary(item_mapping, field_name)
                if field_value:
                    suffix = f"{suffix} {field_name}={summary_quoted_value(field_value)}"
            preflight_summary = preflight_summary_counts(item_mapping.get("preflightSummary"))
            if preflight_summary:
                suffix = f"{suffix} preflightSummary={preflight_summary}"
            preflight_missing_env = string_sequence_summary(item_mapping.get("preflightMissingEnv"))
            if preflight_missing_env:
                suffix = f"{suffix} preflightMissingEnv={preflight_missing_env}"
            preflight_missing_any_of = string_sequence_summary(
                item_mapping.get("preflightMissingAnyOf")
            )
            if preflight_missing_any_of:
                suffix = f"{suffix} preflightMissingAnyOf={preflight_missing_any_of}"
            preflight_recommended_env = string_sequence_summary(
                item_mapping.get("preflightRecommendedEnv")
            )
            if preflight_recommended_env:
                suffix = f"{suffix} preflightRecommendedEnv={preflight_recommended_env}"
            smoke_run_summary = preflight_summary_counts(item_mapping.get("smokeRunSummary"))
            if smoke_run_summary:
                suffix = f"{suffix} smokeRunSummary={smoke_run_summary}"
            smoke_run_missing_env = string_sequence_summary(item_mapping.get("smokeRunMissingEnv"))
            if smoke_run_missing_env:
                suffix = f"{suffix} smokeRunMissingEnv={smoke_run_missing_env}"
            smoke_run_missing_any_of = string_sequence_summary(
                item_mapping.get("smokeRunMissingAnyOf")
            )
            if smoke_run_missing_any_of:
                suffix = f"{suffix} smokeRunMissingAnyOf={smoke_run_missing_any_of}"
            smoke_run_recommended_env = string_sequence_summary(
                item_mapping.get("smokeRunRecommendedEnv")
            )
            if smoke_run_recommended_env:
                suffix = f"{suffix} smokeRunRecommendedEnv={smoke_run_recommended_env}"
            required_env_any_of = required_env_any_of_summary(item_mapping.get("requiredEnvAnyOf"))
            if required_env_any_of:
                suffix = f"{suffix} {required_env_any_of}"
            missing_env_any_of = string_sequence_summary(item_mapping.get("missingEnvAnyOf"))
            if missing_env_any_of:
                suffix = f"{suffix} missingEnvAnyOf={missing_env_any_of}"
            recommended_env = string_sequence_summary(item_mapping.get("recommendedEnv"))
            if recommended_env:
                suffix = f"{suffix} recommendedEnv={recommended_env}"
            source_suite = item_string_summary(item_mapping, "sourceSuite")
            if source_suite:
                suffix = f"{suffix} sourceSuite={source_suite}"
            live_sync_command = item_string_summary(item_mapping, "liveSyncCommand")
            if live_sync_command:
                suffix = f"{suffix} liveSyncCommand={summary_quoted_value(live_sync_command)}"
            readiness_command = item_string_summary(item_mapping, "readinessCommand")
            if readiness_command:
                suffix = f"{suffix} readinessCommand={summary_quoted_value(readiness_command)}"
            next_actions = next_actions_summary(item_mapping)
            if next_actions:
                suffix = f"{suffix} {next_actions}"
            local_contract_actions = ready_local_contract_actions_summary(
                item_mapping,
                prefix="readyLocalContractActions",
            )
            if local_contract_actions:
                suffix = f"{suffix} {' '.join(local_contract_actions)}"
            release_gate = release_gate_summary(item_mapping)
            if release_gate:
                suffix = f"{suffix} {release_gate}"
            feedback_ratings = feedback_counts_summary(item_mapping, "feedbackRatingCounts")
            if feedback_ratings:
                suffix = f"{suffix} feedbackRatings={feedback_ratings}"
            feedback_sources = feedback_counts_summary(item_mapping, "feedbackSourceCounts")
            if feedback_sources:
                suffix = f"{suffix} feedbackSources={feedback_sources}"
            feedback_workflows = feedback_counts_summary(item_mapping, "workflowTagCounts")
            if feedback_workflows:
                suffix = f"{suffix} feedbackWorkflows={feedback_workflows}"
            promotion_coverage = promotion_coverage_summary(item_mapping)
            if promotion_coverage:
                suffix = f"{suffix} promotionCoverage={promotion_coverage}"
            source_run_count = string_sequence_count_summary(item_mapping.get("sourceRunIds"))
            if source_run_count:
                suffix = f"{suffix} sourceRunIds={source_run_count}"
            case_source_run_count = string_mapping_count_summary(
                item_mapping.get("caseSourceRunIds")
            )
            if case_source_run_count:
                suffix = f"{suffix} caseSourceRunMappings={case_source_run_count}"
            review_action = feedback_review_action_summary(item_mapping)
            if review_action:
                suffix = f"{suffix} reviewAction={summary_quoted_value(review_action)}"
            review_actions = feedback_review_actions_summary(item_mapping)
            if review_actions:
                suffix = f"{suffix} reviewActions={summary_quoted_value(review_actions)}"
            bulk_review_action = feedback_bulk_review_action_summary(item_mapping)
            if bulk_review_action:
                suffix = (
                    f"{suffix} feedbackBulkReviewAction={summary_quoted_value(bulk_review_action)}"
                )
            release_readiness_command = feedback_release_readiness_command_summary(item_mapping)
            if release_readiness_command:
                suffix = (
                    f"{suffix} releaseReadinessCommand="
                    f"{summary_quoted_value(release_readiness_command)}"
                )
            citation_markers = langsmith_citation_marker_summary(item_mapping)
            if citation_markers:
                suffix = f"{suffix} citationMarkers={citation_markers}"
            trace_grading = langsmith_trace_grading_summary(item_mapping)
            if trace_grading:
                suffix = f"{suffix} traceGrading={trace_grading}"
            trace_failed_cases = langsmith_trace_failed_cases_summary(item_mapping)
            if trace_failed_cases:
                suffix = f"{suffix} traceFailedCases={trace_failed_cases}"
            deterministic_missing = langsmith_deterministic_missing_expected_summary(item_mapping)
            if deterministic_missing:
                suffix = f"{suffix} deterministicEvalMissingExpected={deterministic_missing}"
            queue_cases = feedback_queue_case_count_summary(item_mapping)
            if queue_cases:
                suffix = f"{suffix} feedbackQueueCases={queue_cases}"
            queue_ratings = feedback_queue_counts_summary(
                item_mapping,
                "feedbackRatingCounts",
            )
            if queue_ratings:
                suffix = f"{suffix} feedbackQueueRatings={queue_ratings}"
            queue_sources = feedback_queue_counts_summary(
                item_mapping,
                "feedbackSourceCounts",
            )
            if queue_sources:
                suffix = f"{suffix} feedbackQueueSources={queue_sources}"
            queue_workflows = feedback_queue_counts_summary(
                item_mapping,
                "workflowTagCounts",
            )
            if queue_workflows:
                suffix = f"{suffix} feedbackQueueWorkflows={queue_workflows}"
            queue_expected_citations = feedback_queue_counts_summary(
                item_mapping,
                "expectedCitationCounts",
            )
            if queue_expected_citations:
                suffix = f"{suffix} feedbackQueueExpectedCitations={queue_expected_citations}"
            queue_action = feedback_queue_review_action_summary(item_mapping)
            if queue_action:
                suffix = f"{suffix} feedbackQueueReviewAction={summary_quoted_value(queue_action)}"
            queue_export_action = feedback_queue_export_action_summary(item_mapping)
            if queue_export_action:
                suffix = (
                    f"{suffix} feedbackQueueExportAction="
                    f"{summary_quoted_value(queue_export_action)}"
                )
            queue_candidate_action = feedback_queue_candidate_action_summary(item_mapping)
            if queue_candidate_action:
                suffix = (
                    f"{suffix} feedbackQueueCandidateAction="
                    f"{summary_quoted_value(queue_candidate_action)}"
                )
            queue_bulk_review_action = feedback_queue_bulk_review_action_summary(item_mapping)
            if queue_bulk_review_action:
                suffix = (
                    f"{suffix} feedbackQueueBulkReviewAction="
                    f"{summary_quoted_value(queue_bulk_review_action)}"
                )
            queue_memory_action = feedback_queue_memory_action_summary(item_mapping)
            if queue_memory_action:
                suffix = (
                    f"{suffix} feedbackQueueMemoryAction="
                    f"{summary_quoted_value(queue_memory_action)}"
                )
            memory_status_counts = memory_status_counts_summary(item_mapping)
            if memory_status_counts:
                suffix = f"{suffix} memoryStatusCounts={memory_status_counts}"
            skipped_memory_status_counts = skipped_memory_status_counts_summary(item_mapping)
            if skipped_memory_status_counts:
                suffix = f"{suffix} skippedMemoryStatusCounts={skipped_memory_status_counts}"
            memory_admission_policy = memory_admission_policy_summary(item_mapping)
            if memory_admission_policy:
                suffix = (
                    f"{suffix} memoryAdmissionPolicy="
                    f"{summary_quoted_value(memory_admission_policy)}"
                )
            invalid_memory_status_labels = invalid_memory_status_labels_summary(item_mapping)
            if invalid_memory_status_labels:
                suffix = f"{suffix} invalidMemoryStatusLabels={invalid_memory_status_labels}"
            context_findings = context_diagnostic_findings_summary(item_mapping)
            if context_findings:
                suffix = f"{suffix} contextFindings={context_findings}"
            memory_contract_areas = memory_contract_areas_summary(item_mapping)
            if memory_contract_areas:
                suffix = f"{suffix} memoryContractAreas={memory_contract_areas}"
            memory_action = memory_lifecycle_action_summary(item_mapping)
            if memory_action:
                suffix = f"{suffix} memoryLifecycleAction='{memory_action}'"
            memory_proposal_actions = memory_proposal_next_actions_summary(item_mapping)
            if memory_proposal_actions:
                suffix = (
                    f"{suffix} memoryProposalNextActions="
                    f"{summary_quoted_value(memory_proposal_actions)}"
                )
            memory_sensors = memory_verification_sensors_summary(item_mapping)
            if memory_sensors:
                suffix = (
                    f"{suffix} memoryVerificationSensors={summary_quoted_value(memory_sensors)}"
                )
            memory_contracts = memory_verification_contracts_summary(item_mapping)
            if memory_contracts:
                suffix = (
                    f"{suffix} memoryReadinessContracts={summary_quoted_value(memory_contracts)}"
                )
            memory_artifacts = memory_verification_artifact_outputs_summary(item_mapping)
            if memory_artifacts:
                suffix = f"{suffix} memoryArtifactOutputs={summary_quoted_value(memory_artifacts)}"
            memory_covers = memory_verification_covers_summary(item_mapping)
            if memory_covers:
                suffix = f"{suffix} memoryVerificationCovers={summary_quoted_value(memory_covers)}"
            memory_dependency_details = memory_dependency_warning_summary(item_mapping)
            if memory_dependency_details:
                suffix = f"{suffix} {memory_dependency_details}"
            stream_terminal_details = stream_terminal_next_actions_summary(item_mapping)
            if stream_terminal_details:
                suffix = f"{suffix} {stream_terminal_details}"
            rag_sensors = rag_verification_sensors_summary(item_mapping)
            if rag_sensors:
                suffix = f"{suffix} ragVerificationSensors={summary_quoted_value(rag_sensors)}"
            rag_candidate_action = item_string_summary(
                item_mapping, "ragCandidateEvalApplyAction"
            ) or rag_candidate_eval_apply_action(cast(Mapping[str, object], item_mapping))
            if rag_candidate_action:
                suffix = (
                    f"{suffix} ragCandidateEvalApplyAction="
                    f"{summary_quoted_value(rag_candidate_action)}"
                )
            product_boundary = product_boundary_summary(item_mapping)
            if product_boundary:
                suffix = f"{suffix} {product_boundary}"
            product_boundary_readiness_command = item_string_summary(
                item_mapping,
                "productBoundaryReadinessCommand",
            )
            if product_boundary_readiness_command:
                suffix = (
                    f"{suffix} productBoundaryReadinessCommand="
                    f"{summary_quoted_value(product_boundary_readiness_command)}"
                )
            required_readiness_reports = string_sequence_summary(
                item_mapping.get("requiredReadinessReports")
            )
            if required_readiness_reports:
                suffix = f"{suffix} requiredReadinessReports={required_readiness_reports}"
            readiness_reports = equals_string_mapping_summary(item_mapping.get("readinessReports"))
            if readiness_reports:
                suffix = f"{suffix} readinessReports={readiness_reports}"
            api_boundary = api_boundary_summary(item_mapping)
            if api_boundary:
                suffix = f"{suffix} {api_boundary}"
            remediation_command = item_string_summary(item_mapping, "remediationCommand")
            if remediation_command:
                suffix = f"{suffix} remediationCommand={summary_quoted_value(remediation_command)}"
            readiness_report_arg = item_string_summary(item_mapping, "readinessReportArg")
            if readiness_report_arg:
                suffix = f"{suffix} readinessReportArg={summary_quoted_value(readiness_report_arg)}"
            lines.append(f"- {name}: status={status} failure={failure}{suffix}")
    warnings = report.get("warnings")
    if isinstance(warnings, Sequence) and not isinstance(warnings, str | bytes | bytearray):
        for warning in cast(Sequence[object], warnings):
            if not isinstance(warning, Mapping):
                continue
            warning_mapping = cast(Mapping[object, object], warning)
            lines.append(readiness_warning_summary_line(warning_mapping))
    return "\n".join(lines)


def tag_recommendation_summary(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    recommendation = cast(Mapping[object, object], value)
    parts = [
        "tagRecommendation",
        f"status={recommendation.get('status') or 'unknown'}",
        f"eligible={bool_summary(recommendation.get('eligible'))}",
        f"recommendedVersionBump={recommendation.get('recommendedVersionBump') or 'unknown'}",
        f"recommendedTagPattern={recommendation.get('recommendedTagPattern') or 'unknown'}",
        f"minorEligible={bool_summary(recommendation.get('minorEligible'))}",
    ]
    latest_tag = recommendation.get("latestTag")
    if isinstance(latest_tag, str) and latest_tag.strip():
        parts.append(f"latestTag={latest_tag.strip()}")
    recommended_tag = recommendation.get("recommendedTag")
    if isinstance(recommended_tag, str) and recommended_tag.strip():
        parts.append(f"recommendedTag={recommended_tag.strip()}")
    tag_selection_reason = recommendation.get("tagSelectionReason")
    if isinstance(tag_selection_reason, str) and tag_selection_reason.strip():
        parts.append(f"tagSelectionReason={summary_quoted_value(tag_selection_reason.strip())}")
    blocking_reports = string_sequence_summary(recommendation.get("blockingReports"))
    if blocking_reports:
        parts.append(f"blockingReports={blocking_reports}")
    root_blocking_reports = string_sequence_summary(recommendation.get("rootBlockingReports"))
    if root_blocking_reports:
        parts.append(f"rootBlockingReports={root_blocking_reports}")
    downstream_blocked_reports = string_sequence_summary(
        recommendation.get("downstreamBlockedReports")
    )
    if downstream_blocked_reports:
        parts.append(f"downstreamBlockedReports={downstream_blocked_reports}")
    minor_boundary_reports = string_sequence_summary(recommendation.get("minorBoundaryReports"))
    if minor_boundary_reports:
        parts.append(f"minorBoundaryReports={minor_boundary_reports}")
    passed_reports = string_sequence_summary(recommendation.get("passedReports"))
    if passed_reports:
        parts.append(f"passedReports={passed_reports}")
    warning_reports = string_sequence_summary(recommendation.get("warningReports"))
    if warning_reports:
        parts.append(f"warningReports={warning_reports}")
    warning_review_required = recommendation.get("warningReviewRequired")
    if warning_review_required is not None:
        parts.append(f"warningReviewRequired={bool_summary(warning_review_required)}")
    minor_blocked_reason = recommendation.get("minorBlockedReason")
    if isinstance(minor_blocked_reason, str) and minor_blocked_reason.strip():
        parts.append(f"minorBlockedReason={summary_quoted_value(minor_blocked_reason.strip())}")
    minor_blocked_reports = string_sequence_summary(recommendation.get("minorBlockedReports"))
    if minor_blocked_reports:
        parts.append(f"minorBlockedReports={minor_blocked_reports}")
    minor_boundary_missing = string_sequence_summary(
        recommendation.get("minorBoundaryMissingEvidence")
    )
    if minor_boundary_missing:
        parts.append(f"minorBoundaryMissing={minor_boundary_missing}")
    minor_boundary_resolved = string_sequence_summary(
        recommendation.get("minorBoundaryResolvedEvidence")
    )
    if minor_boundary_resolved:
        parts.append(f"minorBoundaryResolved={minor_boundary_resolved}")
    minor_boundary_resolved_by_reports = recommendation.get("minorBoundaryResolvedByReports")
    if isinstance(minor_boundary_resolved_by_reports, Mapping):
        for evidence_name, report_name in sorted(
            cast(Mapping[object, object], minor_boundary_resolved_by_reports).items()
        ):
            if not isinstance(evidence_name, str) or not evidence_name.strip():
                continue
            if not isinstance(report_name, str) or not report_name.strip():
                continue
            parts.append(f"minorBoundaryResolvedBy.{evidence_name.strip()}={report_name.strip()}")
    minor_boundary_remediation_command = recommendation.get("minorBoundaryRemediationCommand")
    if (
        isinstance(minor_boundary_remediation_command, str)
        and minor_boundary_remediation_command.strip()
    ):
        minor_boundary_remediation_command = normalize_rag_candidate_eval_apply_action(
            minor_boundary_remediation_command.strip()
        )
        parts.append(
            "minorBoundaryRemediationCommand="
            f"{summary_quoted_value(minor_boundary_remediation_command)}"
        )
    next_action = recommendation.get("nextAction")
    if isinstance(next_action, str) and next_action.strip():
        parts.append(f"nextAction={summary_quoted_value(next_action.strip())}")
    next_action_id = recommendation.get("nextActionId")
    if isinstance(next_action_id, str) and next_action_id.strip():
        parts.append(f"nextActionId={next_action_id.strip()}")
    for field_name in ("readyNextActionIds", "blockedNextActionIds"):
        action_ids = string_sequence_summary(recommendation.get(field_name))
        if action_ids:
            parts.append(f"{field_name}={action_ids}")
    next_action_states = action_state_mapping_summary(recommendation.get("nextActionStates"))
    if next_action_states:
        parts.append(f"nextActionStates={next_action_states}")
    next_action_command = recommendation.get("nextActionCommand")
    if isinstance(next_action_command, str) and next_action_command.strip():
        parts.append(f"nextActionCommand={summary_quoted_value(next_action_command.strip())}")
    next_action_env_file_command = recommendation.get("nextActionEnvFileCommand")
    if isinstance(next_action_env_file_command, str) and next_action_env_file_command.strip():
        parts.append(
            f"nextActionEnvFileCommand={summary_quoted_value(next_action_env_file_command.strip())}"
        )
    release_readiness_command = recommendation.get("releaseReadinessCommand")
    if isinstance(release_readiness_command, str) and release_readiness_command.strip():
        parts.append(
            f"releaseReadinessCommand={summary_quoted_value(release_readiness_command.strip())}"
        )
    for handoff_key in (
        "preflightFile",
        "preflightEnvTemplate",
        "preflightEnvTemplateRefreshPath",
        "preflightEnvTemplateRefreshCommand",
        "preflightEnvFileCommand",
        "releaseSmokeEnvFileCommand",
        "releaseReadinessFile",
    ):
        handoff_value = recommendation.get(handoff_key)
        if isinstance(handoff_value, str) and handoff_value.strip():
            parts.append(f"{handoff_key}={summary_quoted_value(handoff_value.strip())}")
    for identity_key in (
        "feedbackId",
        "evalCaseId",
        "sourceRunId",
        "candidateTag",
        "requiredReviewNote",
    ):
        identity_value = recommendation.get(identity_key)
        if isinstance(identity_value, str) and identity_value.strip():
            parts.append(f"{identity_key}={summary_quoted_value(identity_value.strip())}")
    for tag_key in ("feedbackTags", "workflowTags"):
        tag_values = string_sequence_summary(recommendation.get(tag_key))
        if tag_values:
            parts.append(f"{tag_key}={tag_values}")
    remediation_command = recommendation.get("remediationCommand")
    if isinstance(remediation_command, str) and remediation_command.strip():
        parts.append(f"remediationCommand={summary_quoted_value(remediation_command.strip())}")
    readiness_report_arg = recommendation.get("readinessReportArg")
    if isinstance(readiness_report_arg, str) and readiness_report_arg.strip():
        parts.append(f"readinessReportArg={summary_quoted_value(readiness_report_arg.strip())}")
    required_readiness_reports = string_sequence_summary(
        recommendation.get("requiredReadinessReports")
    )
    if required_readiness_reports:
        parts.append(f"requiredReadinessReports={required_readiness_reports}")
    readiness_reports = equals_string_mapping_summary(recommendation.get("readinessReports"))
    if readiness_reports:
        parts.append(f"readinessReports={readiness_reports}")
    required_env_any_of = required_env_any_of_summary(recommendation.get("requiredEnvAnyOf"))
    if required_env_any_of:
        parts.append(required_env_any_of)
    missing_env = string_sequence_summary(recommendation.get("missingEnv"))
    if missing_env:
        parts.append(f"missingEnv={missing_env}")
    missing_env_any_of = string_sequence_summary(recommendation.get("missingEnvAnyOf"))
    if missing_env_any_of:
        parts.append(f"missingEnvAnyOf={missing_env_any_of}")
    recommended_env = string_sequence_summary(recommendation.get("recommendedEnv"))
    if recommended_env:
        parts.append(f"recommendedEnv={recommended_env}")
    blocking_env_action_id = recommendation.get("blockingEnvActionId")
    if isinstance(blocking_env_action_id, str) and blocking_env_action_id.strip():
        parts.append(f"blockingEnvActionId={blocking_env_action_id.strip()}")
    blocking_required_env_any_of = required_env_any_of_summary(
        recommendation.get("blockingRequiredEnvAnyOf"),
        prefix="blockingRequiredEnvAnyOf",
    )
    if blocking_required_env_any_of:
        parts.append(blocking_required_env_any_of)
    blocking_missing_env_any_of = string_sequence_summary(
        recommendation.get("blockingMissingEnvAnyOf")
    )
    if blocking_missing_env_any_of:
        parts.append(f"blockingMissingEnvAnyOf={blocking_missing_env_any_of}")
    blocking_recommended_env = string_sequence_summary(recommendation.get("blockingRecommendedEnv"))
    if blocking_recommended_env:
        parts.append(f"blockingRecommendedEnv={blocking_recommended_env}")
    parts.extend(blocking_next_actions_summary(recommendation.get("blockingNextActions")))
    return " ".join(parts)


def blocking_next_actions_summary(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    action_parts: list[str] = []
    reports: list[str] = []
    for action in cast(Sequence[object], value):
        if not isinstance(action, Mapping):
            continue
        action_mapping = cast(Mapping[object, object], action)
        report = action_mapping.get("report")
        if not isinstance(report, str) or not report.strip():
            continue
        report_name = report.strip()
        reports.append(report_name)
        for field_name in (
            "nextAction",
            "nextActionId",
            "nextActionCommand",
            "nextActionEnvFileCommand",
            "preflightEnvFileCommand",
            "releaseSmokeEnvFileCommand",
            "preflightEnvTemplateRefreshPath",
            "preflightEnvTemplateRefreshCommand",
            "releaseReadinessCommand",
            "remediationCommand",
            "preflightFile",
            "preflightEnvTemplate",
            "releaseReadinessFile",
            "reportFile",
            "readinessReportArg",
            "requiredReviewNote",
            "releaseGateReason",
        ):
            value = action_mapping.get(field_name)
            if not isinstance(value, str) or not value.strip():
                continue
            rendered = (
                value.strip()
                if field_name in {"nextActionId", "releaseGateReason"}
                else summary_quoted_value(value.strip())
            )
            action_parts.append(f"blockingNextAction.{report_name}.{field_name}={rendered}")
        for field_name in (
            "missingEnv",
            "missingEnvAnyOf",
            "recommendedEnv",
            "requiredReadinessReports",
            "readyNextActionIds",
            "blockedNextActionIds",
        ):
            summary = string_sequence_summary(action_mapping.get(field_name))
            if summary:
                action_parts.append(f"blockingNextAction.{report_name}.{field_name}={summary}")
        readiness_reports = equals_string_mapping_summary(action_mapping.get("readinessReports"))
        if readiness_reports:
            for report_file_pair in readiness_reports.split(","):
                report_name_value, report_file = report_file_pair.split("=", maxsplit=1)
                action_parts.append(
                    f"blockingNextAction.{report_name}.readinessReports."
                    f"{report_name_value}={report_file}"
                )
        next_action_states = action_state_mapping_summary(action_mapping.get("nextActionStates"))
        if next_action_states:
            action_parts.append(
                f"blockingNextAction.{report_name}.nextActionStates={next_action_states}"
            )
        required_env_any_of = required_env_any_of_summary(
            action_mapping.get("requiredEnvAnyOf"),
            prefix=f"blockingNextAction.{report_name}.requiredEnvAnyOf",
        )
        if required_env_any_of:
            action_parts.append(required_env_any_of)
        action_parts.extend(
            ready_local_contract_actions_summary(
                action_mapping,
                prefix=f"blockingNextAction.{report_name}.readyLocalContractActions",
            )
        )
    if not reports:
        return []
    return [f"blockingNextActions={','.join(reports)}", *action_parts]


def action_state_mapping_summary(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    parts = [
        f"{action_id.strip()}={state.strip()}"
        for action_id, state in cast(Mapping[object, object], value).items()
        if isinstance(action_id, str)
        and action_id.strip()
        and isinstance(state, str)
        and state.strip()
    ]
    return ",".join(parts)


def readiness_warning_summary_line(warning: Mapping[object, object]) -> str:
    name = warning.get("name") or "unknown"
    source = warning.get("source") or "unknown"
    status = warning.get("status") or "unknown"
    remediation = warning.get("remediation")
    suffix = f" remediation='{remediation}'" if isinstance(remediation, str) else ""
    review_command = warning.get("reviewCommand")
    if isinstance(review_command, str):
        suffix = f"{suffix} reviewCommand='{review_command}'"
    remediation_command = warning.get("remediationCommand")
    if isinstance(remediation_command, str):
        suffix = f"{suffix} remediationCommand='{remediation_command}'"
    return f"- warning {name}: source={source} status={status}{suffix}"


def product_boundary_summary(item: Mapping[object, object]) -> str:
    boundary = item.get("productCapabilityBoundary")
    if not isinstance(boundary, Mapping):
        return ""
    boundary_mapping = cast(Mapping[object, object], boundary)
    capability = boundary_mapping.get("capability")
    parts: list[str] = []
    if isinstance(capability, str) and capability.strip():
        parts.append(f"productCapability={capability.strip()}")
    parts.append(
        f"productBoundaryMinorEligible={bool_summary(boundary_mapping.get('minorEligible'))}"
    )
    evidence = string_sequence_summary(boundary_mapping.get("evidence"))
    if evidence:
        parts.append(f"productBoundaryEvidence={evidence}")
    resolved_evidence = string_sequence_summary(item.get("productBoundaryResolvedEvidence"))
    resolved_items = {item.strip() for item in resolved_evidence.split(",") if item.strip()}
    if resolved_evidence:
        parts.append(f"productBoundaryResolved={resolved_evidence}")
    expected_resolved_by = item.get("productBoundaryExpectedResolvedByReports")
    if isinstance(expected_resolved_by, Mapping):
        expected_mapping = cast(Mapping[object, object], expected_resolved_by)
        for evidence_name, report_name in sorted(expected_mapping.items()):
            if not isinstance(evidence_name, str) or not evidence_name.strip():
                continue
            if not isinstance(report_name, str) or not report_name.strip():
                continue
            parts.append(
                f"productBoundaryExpectedResolvedBy.{evidence_name.strip()}={report_name.strip()}"
            )
    resolved_by = item.get("productBoundaryResolvedByReports")
    if isinstance(resolved_by, Mapping):
        resolved_by_mapping = cast(Mapping[object, object], resolved_by)
        for evidence_name, report_name in sorted(resolved_by_mapping.items()):
            if not isinstance(evidence_name, str) or not evidence_name.strip():
                continue
            if not isinstance(report_name, str) or not report_name.strip():
                continue
            parts.append(f"productBoundaryResolvedBy.{evidence_name.strip()}={report_name.strip()}")
    missing_evidence = string_sequence_summary(boundary_mapping.get("missingEvidence"))
    if missing_evidence:
        parts.append(f"productBoundaryMissing={missing_evidence}")
        missing_items = {item.strip() for item in missing_evidence.split(",") if item.strip()}
        if (
            "rag_ingestion_lifecycle" in missing_items
            and "rag_ingestion_lifecycle" not in resolved_items
        ):
            parts.append(
                "productBoundaryRemediationAction="
                f"{summary_quoted_value(rag_ingestion_lifecycle_remediation_command())}"
            )
        if any(
            missing_item == "eval_promotion_apply_coverage"
            or missing_item.startswith("eval_promotion_apply_coverage.")
            or missing_item.startswith("context_manifest_diagnostics.citationWorkflow")
            for missing_item in missing_items
        ):
            eval_apply_action = item.get("ragCandidateEvalApplyAction")
            if isinstance(eval_apply_action, str) and eval_apply_action.strip():
                parts.append(
                    "productBoundaryRemediationAction="
                    f"{summary_quoted_value(eval_apply_action.strip())}"
                )
        if any(
            missing_item.startswith("feedback_promotion.") and missing_item not in resolved_items
            for missing_item in missing_items
        ):
            feedback_review_action = product_boundary_feedback_review_action(item)
            if feedback_review_action:
                parts.append(
                    "productBoundaryFeedbackReviewAction="
                    f"{summary_quoted_value(feedback_review_action)}"
                )
    return " ".join(parts)


def product_boundary_feedback_review_action(item: Mapping[object, object]) -> str:
    queue_action = feedback_queue_bulk_review_action_summary(item)
    if queue_action:
        return queue_action
    feedback_promotion = item.get("feedbackPromotion")
    if isinstance(feedback_promotion, Mapping):
        action = cast(Mapping[object, object], feedback_promotion).get("bulkReviewAction")
        if isinstance(action, str) and action.strip():
            return action.strip()
    return ""


def next_actions_summary(item: Mapping[object, object]) -> str:
    next_actions = item.get("nextActions")
    if not isinstance(next_actions, Sequence) or isinstance(next_actions, str | bytes | bytearray):
        return ""
    ids: list[str] = []
    commands: list[str] = []
    for action in cast(Sequence[object], next_actions):
        if not isinstance(action, Mapping):
            continue
        action_mapping = cast(Mapping[object, object], action)
        action_id = action_mapping.get("id")
        command = action_mapping.get("command")
        if not isinstance(action_id, str) or not action_id.strip():
            continue
        action_id = action_id.strip()
        ids.append(action_id)
        if isinstance(command, str) and command.strip():
            commands.append(f"nextAction.{action_id}={summary_quoted_value(command.strip())}")
        env_file_command = action_mapping.get("envFileCommand")
        if isinstance(env_file_command, str) and env_file_command.strip():
            commands.append(
                f"nextAction.{action_id}.envFileCommand="
                f"{summary_quoted_value(env_file_command.strip())}"
            )
        feedback_id = action_mapping.get("feedbackId")
        if isinstance(feedback_id, str) and feedback_id.strip():
            commands.append(f"nextAction.{action_id}.feedbackId={feedback_id.strip()}")
        for field_name in (
            "reportFile",
            "preflightFile",
            "preflightEnvTemplate",
            "preflightEnvTemplateRefreshPath",
            "preflightEnvTemplateRefreshCommand",
            "releaseSmokeEnvFileCommand",
            "releaseReadinessFile",
        ):
            field_value = action_mapping.get(field_name)
            if isinstance(field_value, str) and field_value.strip():
                commands.append(
                    f"nextAction.{action_id}.{field_name}="
                    f"{summary_quoted_value(field_value.strip())}"
                )
        remediation_command = action_mapping.get("remediationCommand")
        if isinstance(remediation_command, str) and remediation_command.strip():
            commands.append(
                f"nextAction.{action_id}.remediationCommand="
                f"{summary_quoted_value(remediation_command.strip())}"
            )
        release_readiness_command = action_mapping.get("releaseReadinessCommand")
        if isinstance(release_readiness_command, str) and release_readiness_command.strip():
            commands.append(
                f"nextAction.{action_id}.releaseReadinessCommand="
                f"{summary_quoted_value(release_readiness_command.strip())}"
            )
        readiness_report_arg = action_mapping.get("readinessReportArg")
        if isinstance(readiness_report_arg, str) and readiness_report_arg.strip():
            commands.append(
                f"nextAction.{action_id}.readinessReportArg="
                f"{summary_quoted_value(readiness_report_arg.strip())}"
            )
        for field_name in (
            "sourceReport",
            "latestTagCommand",
            "recommendedTagSource",
            "recommendedVersionBump",
            "recommendedTagPattern",
            "candidateTag",
            "evalCaseId",
            "sourceRunId",
            "requiredReviewNote",
        ):
            field_value = action_mapping.get(field_name)
            if isinstance(field_value, str) and field_value.strip():
                commands.append(
                    f"nextAction.{action_id}.{field_name}="
                    f"{summary_quoted_value(field_value.strip())}"
                )
        minor_boundary_reports = string_sequence_summary(action_mapping.get("minorBoundaryReports"))
        if minor_boundary_reports:
            commands.append(f"nextAction.{action_id}.minorBoundaryReports={minor_boundary_reports}")
        workflow_tags = string_sequence_summary(action_mapping.get("workflowTags"))
        if workflow_tags:
            commands.append(f"nextAction.{action_id}.workflowTags={workflow_tags}")
        feedback_tags = string_sequence_summary(action_mapping.get("feedbackTags"))
        if feedback_tags:
            commands.append(f"nextAction.{action_id}.feedbackTags={feedback_tags}")
        required_reports = string_sequence_summary(action_mapping.get("requiredReadinessReports"))
        if required_reports:
            commands.append(f"nextAction.{action_id}.requiredReadinessReports={required_reports}")
        for field_name in ("requiredEnv", "missingEnv", "recommendedEnv"):
            env_names = string_sequence_summary(action_mapping.get(field_name))
            if env_names:
                commands.append(f"nextAction.{action_id}.{field_name}={env_names}")
        required_env_any_of = action_mapping.get("requiredEnvAnyOf")
        if isinstance(required_env_any_of, Sequence) and not isinstance(
            required_env_any_of, str | bytes | bytearray
        ):
            for index, group in enumerate(cast(Sequence[object], required_env_any_of)):
                if not isinstance(group, Sequence) or isinstance(group, str | bytes | bytearray):
                    continue
                env_names = [
                    item.strip()
                    for item in cast(Sequence[object], group)
                    if isinstance(item, str) and item.strip()
                ]
                if env_names:
                    commands.append(
                        f"nextAction.{action_id}.requiredEnvAnyOf.{index}={'|'.join(env_names)}"
                    )
        missing_env_any_of = string_sequence_summary(action_mapping.get("missingEnvAnyOf"))
        if missing_env_any_of:
            commands.append(f"nextAction.{action_id}.missingEnvAnyOf={missing_env_any_of}")
        depends_on_action_ids = string_sequence_summary(action_mapping.get("dependsOnActionIds"))
        if depends_on_action_ids:
            commands.append(f"nextAction.{action_id}.dependsOnActionIds={depends_on_action_ids}")
        readiness_reports = equals_string_mapping_summary(action_mapping.get("readinessReports"))
        if readiness_reports:
            for report_name, report_file in (
                pair.split("=", maxsplit=1) for pair in readiness_reports.split(",")
            ):
                commands.append(
                    f"nextAction.{action_id}.readinessReports.{report_name}={report_file}"
                )
    if not ids:
        return ""
    parts = [f"nextActions={','.join(ids)}"]
    parts.extend(commands)
    return " ".join(parts)


def ready_local_contract_actions_summary(
    item: Mapping[object, object],
    *,
    prefix: str,
) -> list[str]:
    actions = item.get("readyLocalContractActions")
    if not isinstance(actions, Sequence) or isinstance(actions, str | bytes | bytearray):
        return []
    ids: list[str] = []
    commands: list[str] = []
    for action in cast(Sequence[object], actions):
        if not isinstance(action, Mapping):
            continue
        action_mapping = cast(Mapping[object, object], action)
        action_id = action_mapping.get("id")
        command = action_mapping.get("command")
        if not isinstance(action_id, str) or not action_id.strip():
            continue
        normalized_action_id = action_id.strip()
        ids.append(normalized_action_id)
        if isinstance(command, str) and command.strip():
            commands.append(
                f"{prefix}.{normalized_action_id}={summary_quoted_value(command.strip())}"
            )
    if not ids:
        return []
    return [f"{prefix}={','.join(ids)}", *commands]


def summary_quoted_value(value: str) -> str:
    if "'" in value:
        return json.dumps(value)
    return f"'{value}'"


def normalize_rag_candidate_eval_apply_action(command: str) -> str:
    if (
        "reactor-runs promote-eval" not in command
        or "rag-ingestion-candidate" not in command
        or "--apply-dry-run" not in command
    ):
        return command
    try:
        parts = shlex.split(command)
    except ValueError:
        return command
    return shlex.join(part for part in parts if part != "--apply-dry-run")


def item_string_summary(item: Mapping[object, object], field_name: str) -> str:
    value = item.get(field_name)
    return value.strip() if isinstance(value, str) else ""


def bool_summary(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return "unknown"


def feedback_review_ids_summary(item: Mapping[object, object]) -> str:
    feedback_promotion = item.get("feedbackPromotion")
    if not isinstance(feedback_promotion, Mapping):
        return ""
    review_ids = cast(Mapping[object, object], feedback_promotion).get("feedbackReviewIds")
    if not isinstance(review_ids, Sequence) or isinstance(review_ids, str | bytes | bytearray):
        return ""
    return ",".join(
        review_id.strip()
        for review_id in cast(Sequence[object], review_ids)
        if isinstance(review_id, str) and review_id.strip()
    )


def feedback_review_action_summary(item: Mapping[object, object]) -> str:
    feedback_promotion = item.get("feedbackPromotion")
    if not isinstance(feedback_promotion, Mapping):
        return ""
    review_action = cast(Mapping[object, object], feedback_promotion).get("reviewAction")
    return review_action.strip() if isinstance(review_action, str) else ""


def feedback_review_actions_summary(item: Mapping[object, object]) -> str:
    feedback_promotion = item.get("feedbackPromotion")
    if not isinstance(feedback_promotion, Mapping):
        return ""
    review_actions = cast(Mapping[object, object], feedback_promotion).get("reviewActions")
    if not isinstance(review_actions, Sequence) or isinstance(
        review_actions, str | bytes | bytearray
    ):
        return ""
    actions = [
        action.strip()
        for action in cast(Sequence[object], review_actions)
        if isinstance(action, str) and action.strip()
    ]
    return "; ".join(actions)


def feedback_bulk_review_action_summary(item: Mapping[object, object]) -> str:
    feedback_promotion = item.get("feedbackPromotion")
    if not isinstance(feedback_promotion, Mapping):
        return ""
    bulk_review_action = cast(Mapping[object, object], feedback_promotion).get("bulkReviewAction")
    return bulk_review_action.strip() if isinstance(bulk_review_action, str) else ""


def feedback_release_readiness_command_summary(item: Mapping[object, object]) -> str:
    feedback_promotion = item.get("feedbackPromotion")
    if not isinstance(feedback_promotion, Mapping):
        return ""
    release_readiness_command = cast(Mapping[object, object], feedback_promotion).get(
        "releaseReadinessCommand"
    )
    return release_readiness_command.strip() if isinstance(release_readiness_command, str) else ""


def feedback_counts_summary(item: Mapping[object, object], key: str) -> str:
    feedback_promotion = item.get("feedbackPromotion")
    if not isinstance(feedback_promotion, Mapping):
        return ""
    counts = cast(Mapping[object, object], feedback_promotion).get(key)
    if not isinstance(counts, Mapping):
        return ""
    pairs = [
        (label.strip(), count)
        for label, count in cast(Mapping[object, object], counts).items()
        if isinstance(label, str)
        and label.strip()
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count > 0
    ]
    return ",".join(f"{label}={count}" for label, count in sorted(pairs))


def preflight_summary_counts(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    pairs = [
        (label.strip(), count)
        for label, count in cast(Mapping[object, object], value).items()
        if isinstance(label, str)
        and label.strip()
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count >= 0
    ]
    return ",".join(f"{label}={count}" for label, count in sorted(pairs))


def string_sequence_count_summary(value: object) -> str:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return ""
    count = sum(
        1 for item in cast(Sequence[object], value) if isinstance(item, str) and item.strip()
    )
    return str(count) if count > 0 else ""


def string_sequence_value(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [
        item.strip()
        for item in cast(Sequence[object], value)
        if isinstance(item, str) and item.strip()
    ]


def string_mapping_count_summary(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    count = sum(
        1
        for key, item in cast(Mapping[object, object], value).items()
        if isinstance(key, str) and key.strip() and isinstance(item, str) and item.strip()
    )
    return str(count) if count > 0 else ""


def string_mapping_summary(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    pairs = [
        (key.strip(), item.strip())
        for key, item in cast(Mapping[object, object], value).items()
        if isinstance(key, str) and key.strip() and isinstance(item, str) and item.strip()
    ]
    return ",".join(f"{key}{item}" for key, item in sorted(pairs))


def equals_string_mapping_summary(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    pairs = [
        (key.strip(), item.strip())
        for key, item in cast(Mapping[object, object], value).items()
        if isinstance(key, str) and key.strip() and isinstance(item, str) and item.strip()
    ]
    return ",".join(f"{key}={item}" for key, item in sorted(pairs))


def api_boundary_summary(item: Mapping[object, object]) -> str:
    boundary = item.get("apiBoundary")
    if not isinstance(boundary, Mapping):
        return ""
    boundary_mapping = cast(Mapping[object, object], boundary)
    parts: list[str] = []
    route_count = positive_int_summary(boundary_mapping.get("routeCount"))
    if route_count:
        parts.append(f"apiRoutes={route_count}")
    schema_count = positive_int_summary(boundary_mapping.get("schemaCount"))
    if schema_count:
        parts.append(f"apiSchemas={schema_count}")
    action_schemas = string_sequence_summary(boundary_mapping.get("nextActionSchemas"))
    if action_schemas:
        parts.append(f"apiNextActionSchemas={action_schemas}")
    action_fields = string_sequence_summary(boundary_mapping.get("nextActionSchemaFields"))
    if action_fields:
        parts.append(f"apiNextActionFields={action_fields}")
    run_action_fields = string_sequence_summary(
        boundary_mapping.get("runOperatorNextActionSchemaFields")
    )
    if run_action_fields:
        parts.append(f"apiRunOperatorNextActionFields={run_action_fields}")
    action_fields_non_empty = boundary_mapping.get("nextActionFieldsNonEmpty")
    if isinstance(action_fields_non_empty, bool):
        parts.append(f"apiNextActionFieldsNonEmpty={str(action_fields_non_empty).lower()}")
    return " ".join(parts)


def positive_int_summary(value: object) -> str:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return str(value)
    return ""


def string_sequence_summary(value: object) -> str:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return ""
    items = [item.strip() for item in cast(Sequence[object], value) if isinstance(item, str)]
    return ",".join(item for item in items if item)


def required_env_any_of_summary(value: object, *, prefix: str = "requiredEnvAnyOf") -> str:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return ""
    parts: list[str] = []
    for index, group in enumerate(cast(Sequence[object], value)):
        if not isinstance(group, Sequence) or isinstance(group, str | bytes | bytearray):
            continue
        env_names = [
            item.strip()
            for item in cast(Sequence[object], group)
            if isinstance(item, str) and item.strip()
        ]
        if env_names:
            parts.append(f"{prefix}.{index}={'|'.join(env_names)}")
    return " ".join(parts)


def feedback_queue_counts_summary(item: Mapping[object, object], key: str) -> str:
    queue = item.get("feedbackReviewQueue")
    if not isinstance(queue, Mapping):
        return ""
    counts = cast(Mapping[object, object], queue).get(key)
    if not isinstance(counts, Mapping):
        return ""
    pairs = [
        (label.strip(), count)
        for label, count in cast(Mapping[object, object], counts).items()
        if isinstance(label, str)
        and label.strip()
        and safe_summary_workflow_label(label.strip())
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count > 0
    ]
    return ",".join(f"{label}={count}" for label, count in sorted(pairs))


def safe_summary_workflow_label(label: str) -> bool:
    if not label.startswith("rag-candidate:"):
        return True
    candidate_slug = label.removeprefix("rag-candidate:").strip()
    return is_command_slug(candidate_slug)


def promotion_coverage_summary(item: Mapping[object, object]) -> str:
    coverage = item.get("promotionCoverage")
    if not isinstance(coverage, Mapping):
        return ""
    pairs = [
        (label.strip(), value)
        for label, value in cast(Mapping[object, object], coverage).items()
        if isinstance(label, str) and label.strip() and isinstance(value, bool)
    ]
    return ",".join(f"{label}={str(value).lower()}" for label, value in sorted(pairs))


def feedback_queue_case_count_summary(item: Mapping[object, object]) -> str:
    queue = item.get("feedbackReviewQueue")
    if not isinstance(queue, Mapping):
        return ""
    return string_sequence_count_summary(cast(Mapping[object, object], queue).get("caseIds"))


def feedback_queue_review_action_summary(item: Mapping[object, object]) -> str:
    queue = item.get("feedbackReviewQueue")
    if not isinstance(queue, Mapping):
        return ""
    queue_mapping = cast(Mapping[object, object], queue)
    case_ids = string_sequence_value(queue_mapping.get("caseIds"))
    recovered_action = feedback_review_queue_action(
        feedback_rating_counts=queue_mapping.get("feedbackRatingCounts"),
        feedback_source_counts=queue_mapping.get("feedbackSourceCounts"),
        workflow_tag_counts=queue_mapping.get("workflowTagCounts"),
        case_ids=case_ids,
        case_count=len(case_ids),
    )
    if recovered_action:
        return recovered_action
    review_action = queue_mapping.get("reviewAction")
    return review_action.strip() if isinstance(review_action, str) else ""


def feedback_queue_export_action_summary(item: Mapping[object, object]) -> str:
    queue = item.get("feedbackReviewQueue")
    if not isinstance(queue, Mapping):
        return ""
    queue_mapping = cast(Mapping[object, object], queue)
    case_ids = string_sequence_value(queue_mapping.get("caseIds"))
    recovered_action = feedback_review_queue_export_action(
        feedback_rating_counts=queue_mapping.get("feedbackRatingCounts"),
        feedback_source_counts=queue_mapping.get("feedbackSourceCounts"),
        workflow_tag_counts=queue_mapping.get("workflowTagCounts"),
        case_ids=case_ids,
        case_count=len(case_ids),
    )
    if recovered_action:
        return recovered_action
    export_action = queue_mapping.get("exportAction")
    return export_action.strip() if isinstance(export_action, str) else ""


def feedback_queue_candidate_action_summary(item: Mapping[object, object]) -> str:
    queue = item.get("feedbackReviewQueue")
    if not isinstance(queue, Mapping):
        return ""
    queue_mapping = cast(Mapping[object, object], queue)
    candidate_action = queue_mapping.get("candidateReviewAction")
    if isinstance(candidate_action, str) and candidate_action.strip():
        return candidate_action.strip()
    explicit_candidate_tag = feedback_queue_candidate_tag_summary(queue_mapping)
    if explicit_candidate_tag:
        return rag_candidate_review_action(explicit_candidate_tag)
    return feedback_review_queue_candidate_review_action(
        queue_mapping.get("workflowTagCounts"),
        case_ids=queue_mapping.get("caseIds"),
    )


def feedback_queue_bulk_review_action_summary(item: Mapping[object, object]) -> str:
    queue = item.get("feedbackReviewQueue")
    if not isinstance(queue, Mapping):
        return ""
    queue_mapping = cast(Mapping[object, object], queue)
    bulk_review_action = queue_mapping.get("bulkReviewAction")
    if isinstance(bulk_review_action, str) and bulk_review_action.strip():
        return bulk_review_action.strip()
    candidate_tag = feedback_queue_candidate_tag_summary(queue_mapping)
    if not candidate_tag:
        return ""
    return feedback_review_queue_bulk_review_action(
        candidate_tag,
        feedback_source_counts=queue_mapping.get("feedbackSourceCounts"),
        expected_citation_counts=queue_mapping.get("expectedCitationCounts"),
    )


def feedback_queue_candidate_tag_summary(queue_mapping: Mapping[object, object]) -> str:
    explicit_candidate_tag = queue_mapping.get("candidateTag")
    if isinstance(explicit_candidate_tag, str) and valid_candidate_workflow_tag(
        explicit_candidate_tag.strip()
    ):
        return explicit_candidate_tag.strip()
    case_ids = string_sequence_value(queue_mapping.get("caseIds"))
    return candidate_workflow_tag_from_case_ids(case_ids)


def feedback_queue_memory_action_summary(item: Mapping[object, object]) -> str:
    queue = item.get("feedbackReviewQueue")
    if not isinstance(queue, Mapping):
        return ""
    queue_mapping = cast(Mapping[object, object], queue)
    memory_action = queue_mapping.get("memoryLifecycleAction")
    if isinstance(memory_action, str) and memory_action.strip():
        return memory_action.strip()
    return feedback_review_queue_memory_lifecycle_action(queue_mapping.get("workflowTagCounts"))


def memory_lifecycle_action_summary(item: Mapping[object, object]) -> str:
    lifecycle = item.get("memoryMaintenanceLifecycle")
    if isinstance(lifecycle, Mapping):
        review_surface = cast(Mapping[object, object], lifecycle).get("reviewSurface")
        if isinstance(review_surface, Mapping):
            action = cast(Mapping[object, object], review_surface).get("lifecycleGateAction")
            if isinstance(action, str) and action.strip():
                return action.strip()
    return memory_lifecycle_action_from_context_diagnostics(item)


def memory_lifecycle_action_from_context_diagnostics(item: Mapping[object, object]) -> str:
    diagnostics = item.get("contextManifestDiagnostics")
    if not isinstance(diagnostics, Mapping):
        return ""
    diagnostics_mapping = cast(Mapping[object, object], diagnostics)
    skipped_counts = positive_memory_status_counts(
        diagnostics_mapping.get("skippedMemoryStatusCounts")
    )
    if skipped_counts:
        return feedback_review_queue_memory_lifecycle_action({"memory": 1})
    status_counts = positive_memory_status_counts(diagnostics_mapping.get("memoryStatusCounts"))
    if any(status != "active" for status in status_counts):
        return feedback_review_queue_memory_lifecycle_action({"memory": 1})
    return ""


def positive_memory_status_counts(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    counts: dict[str, int] = {}
    for label, count in cast(Mapping[object, object], value).items():
        if (
            isinstance(label, str)
            and label.strip()
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count > 0
        ):
            counts[label.strip()] = count
    return counts


def memory_proposal_next_actions_summary(item: Mapping[object, object]) -> str:
    lifecycle = item.get("memoryMaintenanceLifecycle")
    if not isinstance(lifecycle, Mapping):
        return ""
    review_surface = cast(Mapping[object, object], lifecycle).get("reviewSurface")
    if not isinstance(review_surface, Mapping):
        return ""
    action_ids = cast(Mapping[object, object], review_surface).get("proposalNextActionIds")
    if not isinstance(action_ids, Sequence) or isinstance(action_ids, str | bytes | bytearray):
        return ""
    names = [
        action_id.strip()
        for action_id in cast(Sequence[object], action_ids)
        if isinstance(action_id, str) and action_id.strip()
    ]
    return "; ".join(names)


def memory_verification_sensors_summary(item: Mapping[object, object]) -> str:
    lifecycle = item.get("memoryMaintenanceLifecycle")
    if not isinstance(lifecycle, Mapping):
        return ""
    sensors = cast(Mapping[object, object], lifecycle).get("verificationSensors")
    if not isinstance(sensors, Mapping):
        return ""
    focused_tests = cast(Mapping[object, object], sensors).get("focusedTests")
    if not isinstance(focused_tests, Sequence) or isinstance(
        focused_tests, str | bytes | bytearray
    ):
        return ""
    commands = [
        command.strip()
        for command in cast(Sequence[object], focused_tests)
        if isinstance(command, str) and command.strip()
    ]
    return "; ".join(commands)


def memory_verification_covers_summary(item: Mapping[object, object]) -> str:
    lifecycle = item.get("memoryMaintenanceLifecycle")
    if not isinstance(lifecycle, Mapping):
        return ""
    sensors = cast(Mapping[object, object], lifecycle).get("verificationSensors")
    if not isinstance(sensors, Mapping):
        return ""
    covers = cast(Mapping[object, object], sensors).get("covers")
    if not isinstance(covers, Sequence) or isinstance(covers, str | bytes | bytearray):
        return ""
    names = [
        name.strip()
        for name in cast(Sequence[object], covers)
        if isinstance(name, str) and name.strip()
    ]
    return "; ".join(names)


def memory_verification_contracts_summary(item: Mapping[object, object]) -> str:
    lifecycle = item.get("memoryMaintenanceLifecycle")
    if not isinstance(lifecycle, Mapping):
        return ""
    sensors = cast(Mapping[object, object], lifecycle).get("verificationSensors")
    if not isinstance(sensors, Mapping):
        return ""
    contracts = cast(Mapping[object, object], sensors).get("releaseReadinessContracts")
    if not isinstance(contracts, Sequence) or isinstance(contracts, str | bytes | bytearray):
        return ""
    names = [
        name.strip()
        for name in cast(Sequence[object], contracts)
        if isinstance(name, str) and name.strip()
    ]
    return "; ".join(names)


def memory_verification_artifact_outputs_summary(item: Mapping[object, object]) -> str:
    lifecycle = item.get("memoryMaintenanceLifecycle")
    if not isinstance(lifecycle, Mapping):
        return ""
    sensors = cast(Mapping[object, object], lifecycle).get("verificationSensors")
    if not isinstance(sensors, Mapping):
        return ""
    artifacts = cast(Mapping[object, object], sensors).get("artifactOutputs")
    if not isinstance(artifacts, Sequence) or isinstance(artifacts, str | bytes | bytearray):
        return ""
    names = [
        name.strip()
        for name in cast(Sequence[object], artifacts)
        if isinstance(name, str) and name.strip()
    ]
    return "; ".join(names)


def rag_verification_sensors_summary(item: Mapping[object, object]) -> str:
    lifecycle = item.get("ragIngestionLifecycle")
    if not isinstance(lifecycle, Mapping):
        return ""
    return verification_sensor_commands_summary(cast(Mapping[object, object], lifecycle))


def verification_sensor_commands_summary(lifecycle: Mapping[object, object]) -> str:
    sensors = lifecycle.get("verificationSensors")
    if not isinstance(sensors, Mapping):
        return ""
    focused_tests = cast(Mapping[object, object], sensors).get("focusedTests")
    if not isinstance(focused_tests, Sequence) or isinstance(
        focused_tests, str | bytes | bytearray
    ):
        return ""
    commands = [
        command.strip()
        for command in cast(Sequence[object], focused_tests)
        if isinstance(command, str) and command.strip()
    ]
    return "; ".join(commands)


def memory_contract_areas_summary(item: Mapping[object, object]) -> str:
    lifecycle = item.get("memoryMaintenanceLifecycle")
    if not isinstance(lifecycle, Mapping):
        return ""
    return ",".join(MEMORY_CONTRACT_AREAS)


def memory_dependency_warning_summary(item: Mapping[object, object]) -> str:
    lifecycle = item.get("memoryMaintenanceLifecycle")
    if not isinstance(lifecycle, Mapping):
        return ""
    dependency_warnings = cast(Mapping[object, object], lifecycle).get("dependencyWarnings")
    if not isinstance(dependency_warnings, Mapping):
        return ""
    warning_mapping = cast(Mapping[object, object], dependency_warnings)
    parts: list[str] = []
    findings = warning_mapping.get("findings")
    if isinstance(findings, Sequence) and not isinstance(findings, str | bytes | bytearray):
        finding_count = sum(
            1 for finding in cast(Sequence[object], findings) if isinstance(finding, Mapping)
        )
        if finding_count > 0:
            parts.append(f"memoryDependencyWarnings={finding_count}")
    checked_packages = string_sequence_value(warning_mapping.get("checkedPackages"))
    if checked_packages:
        parts.append(f"memoryDependencyPackages={','.join(sorted(checked_packages))}")
    direct_pins = string_mapping_summary(warning_mapping.get("directPins"))
    if direct_pins:
        parts.append(f"memoryDependencyDirectPins={direct_pins}")
    pin_source = item_string_summary(warning_mapping, "pinSource")
    if pin_source:
        parts.append(f"memoryDependencyPinSource={pin_source}")
    review_command = item_string_summary(warning_mapping, "reviewCommand")
    if review_command:
        parts.append(f"memoryDependencyReviewCommand={summary_quoted_value(review_command)}")
    remediation_command = item_string_summary(warning_mapping, "remediationCommand")
    if remediation_command:
        parts.append(
            f"memoryDependencyRemediationCommand={summary_quoted_value(remediation_command)}"
        )
    return " ".join(parts)


def stream_terminal_next_actions_summary(item: Mapping[object, object]) -> str:
    contract = item.get("streamingEventContract")
    if not isinstance(contract, Mapping):
        return ""
    terminal_actions = cast(Mapping[object, object], contract).get("terminalNextActions")
    if not isinstance(terminal_actions, Mapping):
        return "streamTerminalNextActions=missing"
    terminal_mapping = cast(Mapping[object, object], terminal_actions)
    parts: list[str] = []
    if terminal_mapping.get("includedInCompletedPayload") is not True:
        parts.append("streamTerminalNextActions=missing_from_completed_payload")
    action_ids = string_sequence_value(terminal_mapping.get("actionIds"))
    if action_ids:
        parts.append(f"streamTerminalActionIds={','.join(action_ids)}")
    commands = string_sequence_value(terminal_mapping.get("commands"))
    if commands:
        parts.append(f"streamTerminalCommands={summary_quoted_value('; '.join(commands))}")
    identity_fields = string_sequence_value(terminal_mapping.get("identityFields"))
    if identity_fields:
        parts.append(f"streamTerminalIdentityFields={','.join(identity_fields)}")
    return " ".join(parts)


def memory_status_counts_summary(item: Mapping[object, object]) -> str:
    diagnostics = item.get("contextManifestDiagnostics")
    if not isinstance(diagnostics, Mapping):
        return ""
    counts = cast(Mapping[object, object], diagnostics).get("memoryStatusCounts")
    return memory_diagnostic_counts_summary(counts)


def skipped_memory_status_counts_summary(item: Mapping[object, object]) -> str:
    diagnostics = item.get("contextManifestDiagnostics")
    if not isinstance(diagnostics, Mapping):
        return ""
    counts = cast(Mapping[object, object], diagnostics).get("skippedMemoryStatusCounts")
    return memory_diagnostic_counts_summary(counts)


def memory_admission_policy_summary(item: Mapping[object, object]) -> str:
    diagnostics = item.get("contextManifestDiagnostics")
    if not isinstance(diagnostics, Mapping):
        return ""
    policy = cast(Mapping[object, object], diagnostics).get("memoryAdmissionPolicy")
    if not isinstance(policy, Mapping):
        return ""
    policy_mapping = cast(Mapping[object, object], policy)
    fields = (
        "activeOnly",
        "missingStatusExcluded",
        "supersededExcluded",
        "tombstonedExcluded",
    )
    parts: list[str] = []
    for field in fields:
        value = policy_mapping.get(field)
        if isinstance(value, bool):
            parts.append(f"{field}={str(value).lower()}")
    return "; ".join(parts)


def invalid_memory_status_labels_summary(item: Mapping[object, object]) -> str:
    diagnostics = item.get("contextManifestDiagnostics")
    if not isinstance(diagnostics, Mapping):
        return ""
    labels: set[str] = set()
    diagnostics_mapping = cast(Mapping[object, object], diagnostics)
    for field_name in ("memoryStatusCounts", "skippedMemoryStatusCounts"):
        counts = diagnostics_mapping.get(field_name)
        if not isinstance(counts, Mapping):
            continue
        for label in cast(Mapping[object, object], counts):
            if isinstance(label, str) and label.strip():
                clean_label = label.strip()
                if clean_label not in ALLOWED_MEMORY_STATUS_COUNT_LABELS:
                    labels.add(clean_label)
    return ",".join(sorted(labels))


def memory_diagnostic_counts_summary(counts: object) -> str:
    if not isinstance(counts, Mapping):
        return ""
    pairs = [
        (label.strip(), count)
        for label, count in cast(Mapping[object, object], counts).items()
        if isinstance(label, str)
        and label.strip()
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count >= 0
    ]
    return ",".join(f"{label}={count}" for label, count in sorted(pairs))


def context_diagnostic_findings_summary(item: Mapping[object, object]) -> str:
    diagnostics = item.get("contextManifestDiagnostics")
    if not isinstance(diagnostics, Mapping):
        return ""
    findings = cast(Mapping[object, object], diagnostics).get("findings")
    if not isinstance(findings, Sequence) or isinstance(findings, str | bytes | bytearray):
        return ""
    codes: list[str] = []
    for finding in cast(Sequence[object], findings):
        if not isinstance(finding, Mapping):
            continue
        code = cast(Mapping[object, object], finding).get("code")
        if isinstance(code, str) and code.strip():
            codes.append(code.strip())
    return ",".join(dict.fromkeys(codes))


def langsmith_citation_marker_summary(item: Mapping[object, object]) -> str:
    example_contract = item.get("exampleContract")
    if not isinstance(example_contract, Mapping):
        return ""
    citation_contract = cast(Mapping[object, object], example_contract).get(
        "citationMarkerContract"
    )
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


def langsmith_trace_grading_summary(item: Mapping[object, object]) -> str:
    trace_grading = item.get("traceGrading")
    if not isinstance(trace_grading, Mapping):
        return ""
    trace_mapping = cast(Mapping[object, object], trace_grading)
    passed = trace_mapping.get("passed")
    failed = trace_mapping.get("failed")
    if (
        not isinstance(passed, int)
        or isinstance(passed, bool)
        or not isinstance(failed, int)
        or isinstance(failed, bool)
    ):
        return ""
    return f"passed={passed},failed={failed}"


def langsmith_trace_failed_cases_summary(item: Mapping[object, object]) -> str:
    trace_grading = item.get("traceGrading")
    if not isinstance(trace_grading, Mapping):
        return ""
    grades = cast(Mapping[object, object], trace_grading).get("grades")
    if not isinstance(grades, Sequence) or isinstance(grades, str | bytes | bytearray):
        return ""
    failed_cases: list[str] = []
    for grade in cast(Sequence[object], grades):
        if not isinstance(grade, Mapping):
            continue
        grade_mapping = cast(Mapping[object, object], grade)
        if grade_mapping.get("passed") is not False:
            continue
        case_id = grade_mapping.get("caseId")
        if isinstance(case_id, str) and case_id.strip():
            failed_cases.append(case_id.strip())
    return ",".join(dict.fromkeys(failed_cases))


def langsmith_deterministic_missing_expected_summary(item: Mapping[object, object]) -> str:
    trace_grading = item.get("traceGrading")
    if not isinstance(trace_grading, Mapping):
        return ""
    grades = cast(Mapping[object, object], trace_grading).get("grades")
    if not isinstance(grades, Sequence) or isinstance(grades, str | bytes | bytearray):
        return ""
    missing_expected: list[str] = []
    for grade in cast(Sequence[object], grades):
        if not isinstance(grade, Mapping):
            continue
        dimensions = cast(Mapping[object, object], grade).get("dimensions")
        if not isinstance(dimensions, Sequence) or isinstance(dimensions, str | bytes | bytearray):
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
            missing_values = cast(Mapping[object, object], evidence).get(
                "missingExpectedAnswerContains"
            )
            if not isinstance(missing_values, Sequence) or isinstance(
                missing_values, str | bytes | bytearray
            ):
                continue
            missing_expected.extend(
                value.strip()
                for value in cast(Sequence[object], missing_values)
                if isinstance(value, str) and value.strip()
            )
    return ",".join(dict.fromkeys(missing_expected))
