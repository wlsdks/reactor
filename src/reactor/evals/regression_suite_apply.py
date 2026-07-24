from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from shlex import quote
from shlex import split as shell_split
from typing import cast

from reactor.evals.langsmith_dataset import (
    RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
    RAG_CANDIDATE_REVIEW_ACTION,
    build_langsmith_eval_sync_dry_run_report,
    build_langsmith_eval_sync_dry_run_report_for_suite,
    candidate_workflow_tag_from_case_ids,
    feedback_review_queue_action,
    feedback_review_queue_bulk_review_action,
    feedback_review_queue_candidate_review_action,
    feedback_review_queue_export_action,
    feedback_review_queue_memory_lifecycle_action,
    int_mapping_value,
    langsmith_env_file_command,
    langsmith_feedback_workflow_review_action,
    string_list_value,
    trace_deterministic_eval_summary_value,
    validate_langsmith_eval_cases,
)
from reactor.evals.models import (
    AgentEvalCaseRecord,
    is_bracketed_citation_marker,
    is_placeholder_citation_marker,
)
from reactor.evals.suite import (
    AgentEvalRegressionSuite,
    case_from_json,
    list_of_dicts,
    run_from_json,
)
from reactor.feedback.workflow import feedback_review_closed
from reactor.kernel.citations import is_citation_safe_id
from reactor.rag.ingestion_candidate_actions import rag_candidate_feedback_bulk_review_action
from reactor.rag.ingestion_candidate_ids import (
    rag_candidate_slug_from_case_id,
    rag_candidate_workflow_tag,
)
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
)

CITATION_MARKER_PLACEHOLDERS = frozenset({"[replace-with-source-id]"})


def apply_promoted_eval_case(
    *,
    suite_file: Path,
    case_file: Path,
    run_file: Path | None = None,
    dataset_name: str,
    replace: bool = False,
    dry_run: bool = False,
    require_source_run_id: bool = False,
    require_run_file: bool = False,
    require_context_diagnostics: bool = False,
) -> dict[str, object]:
    suite_data = regression_suite_data_from_file(suite_file)
    case_record = promoted_case_from_file(case_file)
    validate_promoted_case_citation_markers(case_record)
    validate_rag_candidate_eval_apply(
        suite_file=suite_file,
        dataset_name=dataset_name,
        case=case_record,
    )
    if require_source_run_id and not case_record.source_run_id:
        raise ValueError("sourceRunId is required for promoted eval cases")
    if require_run_file and run_file is None:
        raise ValueError("run-file is required when applying promoted eval cases")
    validate_langsmith_eval_cases([case_record], dataset_name=dataset_name)

    existing_cases = list(list_of_dicts(suite_data.get("cases")))
    case_payload = case_to_json(case_record)
    existing_index = next(
        (
            index
            for index, item in enumerate(existing_cases)
            if isinstance(item.get("id"), str) and item["id"] == case_record.id
        ),
        None,
    )
    if existing_index is not None and not replace:
        status = "unchanged"
    elif existing_index is not None:
        existing_cases[existing_index] = case_payload
        status = "replaced"
    else:
        existing_cases.append(case_payload)
        status = "added"

    suite_data["cases"] = existing_cases
    suite_data.setdefault("runs", [])
    run_report = apply_run_fixture(
        suite_data=suite_data,
        run_file=run_file,
        case=case_record,
        replace=replace,
        dry_run=dry_run,
    )
    if require_context_diagnostics and not run_report.get("contextManifestDiagnosticsPresent"):
        raise ValueError("context diagnostics are required when applying promoted eval cases")
    if require_context_diagnostics and apply_targets_rag_candidate_suite(
        suite_file=suite_file,
        dataset_name=dataset_name,
        case=case_record,
    ):
        validate_rag_candidate_context_citation_workflow(case=case_record, run_report=run_report)
    if dry_run:
        status = dry_run_status(status)
    else:
        suite_file.parent.mkdir(parents=True, exist_ok=True)
        suite_file.write_text(json.dumps(suite_data, indent=2, ensure_ascii=False) + "\n")
    report = apply_report(
        status=status,
        case=case_record,
        suite_file=suite_file,
        case_count=len(existing_cases),
        replaced=existing_index is not None,
        dry_run=dry_run,
        run_file=run_file,
        run_report=run_report,
        require_source_run_id=require_source_run_id,
        require_run_file=require_run_file,
        require_context_diagnostics=require_context_diagnostics,
    )
    report.update(run_report)
    return report


def validate_rag_candidate_eval_apply(
    *,
    suite_file: Path,
    dataset_name: str,
    case: AgentEvalCaseRecord,
) -> None:
    if not apply_targets_rag_candidate_suite(
        suite_file=suite_file,
        dataset_name=dataset_name,
        case=case,
    ):
        return
    if not case.id.startswith("case_rag_candidate_"):
        raise ValueError("RAG ingestion candidate eval apply requires case id case_rag_candidate_*")
    if rag_candidate_slug_from_case_id(case.id) is not None:
        return
    raise ValueError("RAG ingestion candidate eval apply requires slugged case id")


def apply_targets_rag_candidate_suite(
    *,
    suite_file: Path,
    dataset_name: str,
    case: AgentEvalCaseRecord,
) -> bool:
    return (
        dataset_name == "reactor-rag-ingestion-candidate"
        or "rag-ingestion-candidate" in str(suite_file)
        or "collection:rag-ingestion-candidate" in case.tags
    )


def apply_run_fixture(
    *,
    suite_data: dict[str, object],
    run_file: Path | None,
    case: AgentEvalCaseRecord,
    replace: bool,
    dry_run: bool,
) -> dict[str, object]:
    existing_runs = list(list_of_dicts(suite_data.get("runs")))
    if run_file is None:
        suite_data["runs"] = existing_runs
        return {}
    run_payload = json_object_from_file(run_file)
    run_fixture = run_from_json(run_payload)
    case_id = case.id
    if run_fixture.eval_case_id != case_id:
        raise ValueError(f"run fixture evalCaseId must match case id: {case_id}")
    if case.source_run_id is not None and run_fixture.run_id != case.source_run_id:
        raise ValueError(f"run fixture runId must match sourceRunId: {case.source_run_id}")
    validate_run_fixture_citation_markers(case=case, final_answer=run_fixture.final_answer)
    existing_index = next(
        (
            index
            for index, item in enumerate(existing_runs)
            if isinstance(item.get("runId"), str) and item["runId"] == run_fixture.run_id
        ),
        None,
    )
    if existing_index is None:
        existing_runs.append(run_payload)
        run_status = "added"
    elif replace:
        existing_runs[existing_index] = run_payload
        run_status = "replaced"
    else:
        run_status = "unchanged"
    if dry_run:
        run_status = dry_run_status(run_status)
    suite_data["runs"] = existing_runs
    report: dict[str, object] = {
        "runStatus": run_status,
        "runId": run_fixture.run_id,
        "runCount": len(existing_runs),
        "contextManifestDiagnosticsPresent": bool(run_fixture.context_manifest_diagnostics),
    }
    if promoted_case_requires_citation_markers(case):
        report["citationMarkersPresent"] = run_fixture_has_citation_markers(
            case=case,
            final_answer=run_fixture.final_answer,
        )
    report.update(
        rag_candidate_context_citation_workflow_coverage(
            case=case,
            diagnostics=run_fixture.context_manifest_diagnostics,
        )
    )
    return report


def dry_run_status(status: str) -> str:
    if status == "added":
        return "would_add"
    if status == "replaced":
        return "would_replace"
    return status


def promoted_case_from_file(path: Path) -> AgentEvalCaseRecord:
    return case_from_json(json_object_from_file(path))


def validate_promoted_case_citation_markers(case: AgentEvalCaseRecord) -> None:
    if not promoted_case_requires_citation_markers(case):
        return
    if promoted_case_has_placeholder_citation_markers(case):
        raise ValueError("documents-ask eval cases cannot use placeholder citation marker")
    if promoted_case_has_citation_markers(case):
        return
    raise ValueError("documents-ask eval cases require bracketed citations")


def promoted_case_requires_citation_markers(case: AgentEvalCaseRecord) -> bool:
    return "documents-ask" in set(case.tags)


def promoted_case_has_citation_markers(case: AgentEvalCaseRecord) -> bool:
    return any(is_bracketed_citation_marker(item) for item in case.expected_answer_contains)


def promoted_case_has_placeholder_citation_markers(case: AgentEvalCaseRecord) -> bool:
    return any(is_placeholder_citation_marker(item) for item in case.expected_answer_contains)


def validate_run_fixture_citation_markers(
    *,
    case: AgentEvalCaseRecord,
    final_answer: str,
) -> None:
    if not promoted_case_requires_citation_markers(case):
        return
    if promoted_case_allows_missing_run_citation_markers(case):
        return
    for marker in case.expected_answer_contains:
        if is_bracketed_citation_marker(marker) and marker not in final_answer:
            raise ValueError("run fixture finalAnswer must include expected citation")


def promoted_case_allows_missing_run_citation_markers(case: AgentEvalCaseRecord) -> bool:
    return "citation-failure" in set(case.tags)


def run_fixture_has_citation_markers(
    *,
    case: AgentEvalCaseRecord,
    final_answer: str,
) -> bool:
    if not promoted_case_requires_citation_markers(case):
        return False
    citation_markers = [
        marker for marker in case.expected_answer_contains if is_bracketed_citation_marker(marker)
    ]
    if not citation_markers:
        return False
    return all(marker in final_answer for marker in citation_markers)


def validate_rag_candidate_context_citation_workflow(
    *,
    case: AgentEvalCaseRecord,
    run_report: Mapping[str, object],
) -> None:
    slug = rag_candidate_slug_from_case_id(case.id)
    if slug is None:
        return
    if run_report.get("contextCitationEvalCaseIdMatched") is not True:
        raise ValueError(
            f"RAG ingestion candidate context citations must include evalCaseId {case.id}"
        )
    expected_tag = rag_candidate_workflow_tag(slug)
    if run_report.get("contextCitationWorkflowTagMatched") is not True:
        raise ValueError(
            f"RAG ingestion candidate context citations must include workflow tag {expected_tag}"
        )


def rag_candidate_context_citation_workflow_coverage(
    *,
    case: AgentEvalCaseRecord,
    diagnostics: Mapping[str, object],
) -> dict[str, bool]:
    slug = rag_candidate_slug_from_case_id(case.id)
    if slug is None:
        return {}
    expected_tag = rag_candidate_workflow_tag(slug)
    citations = context_diagnostics_citations(diagnostics)
    return {
        "contextCitationEvalCaseIdMatched": any(
            citation.get("evalCaseId") == case.id for citation in citations
        ),
        "contextCitationWorkflowTagMatched": any(
            expected_tag in string_list_value(citation.get("workflowTags", ()))
            for citation in citations
        ),
    }


def context_diagnostics_citations(diagnostics: Mapping[str, object]) -> list[Mapping[str, object]]:
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


def regression_suite_data_from_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"cases": [], "runs": []}
    return json_object_from_file(path)


def json_object_from_file(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"{path} must contain a JSON object")
    return dict(cast(Mapping[str, object], raw))


def case_to_json(case: AgentEvalCaseRecord) -> dict[str, object]:
    data: dict[str, object] = {
        "id": case.id,
        "name": case.name,
        "userInput": case.user_input,
        "expectedAnswerContains": list(case.expected_answer_contains),
        "forbiddenAnswerContains": list(case.forbidden_answer_contains),
        "expectedToolNames": list(case.expected_tool_names),
        "forbiddenToolNames": list(case.forbidden_tool_names),
        "expectedExposedToolNames": list(case.expected_exposed_tool_names),
        "forbiddenExposedToolNames": list(case.forbidden_exposed_tool_names),
        "enabled": case.enabled,
        "tags": list(case.tags),
        "minScore": case.min_score,
    }
    if case.max_tool_exposure_count is not None:
        data["maxToolExposureCount"] = case.max_tool_exposure_count
    if case.agent_type is not None:
        data["agentType"] = case.agent_type
    if case.model is not None:
        data["model"] = case.model
    if case.source_run_id is not None:
        data["sourceRunId"] = case.source_run_id
    return data


def apply_report(
    *,
    status: str,
    case: AgentEvalCaseRecord,
    suite_file: Path,
    case_count: int,
    replaced: bool,
    dry_run: bool,
    run_file: Path | None,
    run_report: Mapping[str, object],
    require_source_run_id: bool,
    require_run_file: bool,
    require_context_diagnostics: bool,
) -> dict[str, object]:
    promotion_coverage: dict[str, object] = {
        "sourceRunIdPresent": case.source_run_id is not None,
        "runFixturePresent": run_file is not None,
        "runFixtureMatchedCase": run_file is not None and "runId" in run_report,
        "runContextDiagnosticsPresent": bool(run_report.get("contextManifestDiagnosticsPresent")),
        "requiredSourceRunId": require_source_run_id,
        "requiredRunFile": require_run_file,
        "requiredContextDiagnostics": require_context_diagnostics,
    }
    if promoted_case_requires_citation_markers(case):
        promotion_coverage["citationMarkersRequired"] = True
        promotion_coverage["citationMarkersPresent"] = promoted_case_has_citation_markers(case)
        promotion_coverage["runCitationMarkersPresent"] = run_report.get("citationMarkersPresent")
        promotion_coverage["citationFailureAllowsMissingRunCitation"] = (
            promoted_case_allows_missing_run_citation_markers(case)
        )
    return {
        "status": status,
        "caseId": case.id,
        "sourceRunId": case.source_run_id,
        "suiteFile": str(suite_file),
        "caseCount": case_count,
        "replaced": replaced,
        "dryRun": dry_run,
        "promotionCoverage": promotion_coverage,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply a promoted Reactor eval case JSON payload to a regression suite."
    )
    parser.add_argument(
        "--suite-file",
        required=True,
        help="Agent eval regression suite JSON file.",
    )
    parser.add_argument("--case-file", default="", help="Promoted eval case JSON payload.")
    parser.add_argument("--run-file", default="", help="Optional promoted eval run fixture JSON.")
    parser.add_argument(
        "--dataset-name",
        default="reactor-regression",
        help="LangSmith dataset name used for deterministic validation.",
    )
    parser.add_argument("--replace", action="store_true", help="Replace an existing case id.")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing suite.")
    parser.add_argument(
        "--require-source-run-id",
        action="store_true",
        help="Reject promoted case payloads that do not carry sourceRunId.",
    )
    parser.add_argument(
        "--require-run-file",
        action="store_true",
        help="Reject promoted case payloads unless a matching --run-file is supplied.",
    )
    parser.add_argument(
        "--require-context-diagnostics",
        action="store_true",
        help="Reject promoted run fixtures unless context manifest diagnostics are present.",
    )
    parser.add_argument("--report-file", default="", help="Optional JSON report output path.")
    parser.add_argument(
        "--langsmith-dry-run-report-file",
        default="",
        help="Optional LangSmith eval sync dry-run report output path.",
    )
    parser.add_argument(
        "--feedback-review-status",
        default="",
        help="Optional feedback review status to preserve in LangSmith dry-run evidence.",
    )
    parser.add_argument(
        "--feedback-review-tag",
        action="append",
        default=[],
        help="Optional feedback review tag to preserve in LangSmith dry-run evidence.",
    )
    parser.add_argument(
        "--feedback-review-note",
        default="",
        help="Optional feedback review note to preserve in LangSmith dry-run evidence.",
    )
    parser.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format for stdout.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Summarize the source-controlled regression suite without applying a case.",
    )
    args = parser.parse_args(argv)
    if args.summary:
        suite_file = Path(args.suite_file)
        if args.dry_run and args.case_file:
            suite = promoted_eval_suite_snapshot(
                suite_file=suite_file,
                case_file=Path(args.case_file),
                run_file=Path(args.run_file) if args.run_file else None,
                replace=bool(args.replace),
            )
        else:
            suite = AgentEvalRegressionSuite.load(suite_file)
        report = regression_suite_summary_for_suite(
            suite=suite,
            suite_file=suite_file,
        )
        if args.langsmith_dry_run_report_file:
            langsmith_report_file = Path(args.langsmith_dry_run_report_file)
            langsmith_report = build_langsmith_eval_sync_dry_run_report_for_suite(
                suite=suite,
                suite_file=suite_file,
                dataset_name=args.dataset_name,
                report_file=langsmith_report_file,
                feedback_review_status=args.feedback_review_status,
                feedback_review_tags=tuple(args.feedback_review_tag or ()),
                feedback_review_note=args.feedback_review_note,
            )
            langsmith_report_file.parent.mkdir(parents=True, exist_ok=True)
            langsmith_report_file.write_text(
                json.dumps(langsmith_report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            report["langsmithDryRun"] = langsmith_dry_run_summary(
                langsmith_report,
                report_file=langsmith_report_file,
                summary_command=langsmith_summary_command(
                    suite_file=suite_file,
                    dataset_name=str(args.dataset_name),
                    report_file=langsmith_report_file,
                    feedback_review_status=str(args.feedback_review_status),
                    feedback_review_tags=tuple(args.feedback_review_tag or ()),
                    feedback_review_note=str(args.feedback_review_note),
                ),
            )
        emit_report(report, args)
        return 0
    if not args.case_file:
        parser.error("--case-file is required unless --summary is set")
    try:
        report = apply_promoted_eval_case(
            suite_file=Path(args.suite_file),
            case_file=Path(args.case_file),
            run_file=Path(args.run_file) if args.run_file else None,
            dataset_name=args.dataset_name,
            replace=bool(args.replace),
            dry_run=bool(args.dry_run),
            require_source_run_id=bool(args.require_source_run_id),
            require_run_file=bool(args.require_run_file),
            require_context_diagnostics=bool(args.require_context_diagnostics),
        )
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    if args.dry_run:
        report["persistCommand"] = apply_persist_command(args)
    if args.langsmith_dry_run_report_file:
        langsmith_report_file = Path(args.langsmith_dry_run_report_file)
        if args.dry_run:
            langsmith_report = build_langsmith_eval_sync_dry_run_report_for_suite(
                suite=promoted_eval_suite_snapshot(
                    suite_file=Path(args.suite_file),
                    case_file=Path(args.case_file),
                    run_file=Path(args.run_file) if args.run_file else None,
                    replace=bool(args.replace),
                ),
                suite_file=Path(args.suite_file),
                dataset_name=args.dataset_name,
                report_file=langsmith_report_file,
                feedback_review_status=args.feedback_review_status,
                feedback_review_tags=tuple(args.feedback_review_tag or ()),
                feedback_review_note=args.feedback_review_note,
            )
        else:
            langsmith_report = build_langsmith_eval_sync_dry_run_report(
                suite_file=Path(args.suite_file),
                dataset_name=args.dataset_name,
                report_file=langsmith_report_file,
                feedback_review_status=args.feedback_review_status,
                feedback_review_tags=tuple(args.feedback_review_tag or ()),
                feedback_review_note=args.feedback_review_note,
            )
        langsmith_report_file.parent.mkdir(parents=True, exist_ok=True)
        langsmith_report_file.write_text(
            json.dumps(langsmith_report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        report["langsmithDryRun"] = langsmith_dry_run_summary(
            langsmith_report,
            report_file=langsmith_report_file,
            persist_command=str(report.get("persistCommand") or ""),
        )
    emit_report(report, args)
    return 0


def promoted_eval_suite_snapshot(
    *,
    suite_file: Path,
    case_file: Path,
    run_file: Path | None,
    replace: bool,
) -> AgentEvalRegressionSuite:
    suite_data = regression_suite_data_from_file(suite_file)
    case_record = promoted_case_from_file(case_file)
    existing_cases = list(list_of_dicts(suite_data.get("cases")))
    case_payload = case_to_json(case_record)
    existing_index = next(
        (
            index
            for index, item in enumerate(existing_cases)
            if isinstance(item.get("id"), str) and item["id"] == case_record.id
        ),
        None,
    )
    if existing_index is None:
        existing_cases.append(case_payload)
    elif replace:
        existing_cases[existing_index] = case_payload
    suite_data["cases"] = existing_cases
    suite_data.setdefault("runs", [])
    apply_run_fixture(
        suite_data=suite_data,
        run_file=run_file,
        case=case_record,
        replace=replace,
        dry_run=False,
    )
    return regression_suite_from_data(suite_data)


def regression_suite_from_data(suite_data: Mapping[str, object]) -> AgentEvalRegressionSuite:
    return AgentEvalRegressionSuite.from_data(suite_data)


def emit_report(report: Mapping[str, object], args: argparse.Namespace) -> None:
    report_json = json.dumps(report, indent=2, sort_keys=True)
    if args.report_file:
        report_path = Path(args.report_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_json + "\n", encoding="utf-8")
    if args.output == "table":
        formatter = format_suite_summary_table if args.summary else format_apply_report_table
        print(formatter(report), end="")
    else:
        print(report_json)


def regression_suite_summary(suite_file: Path) -> dict[str, object]:
    suite = AgentEvalRegressionSuite.load(suite_file)
    return regression_suite_summary_for_suite(suite=suite, suite_file=suite_file)


def regression_suite_summary_for_suite(
    *,
    suite: AgentEvalRegressionSuite,
    suite_file: Path,
) -> dict[str, object]:
    enabled_cases = suite.enabled_cases
    missing_run_case_ids = [
        case.id for case in enabled_cases if suite.find_run_for_case(case.id) is None
    ]
    return {
        "suiteFile": str(suite_file),
        "caseCount": len(suite.cases),
        "enabledCases": len(enabled_cases),
        "disabledCases": len(suite.cases) - len(enabled_cases),
        "runCount": len(suite.runs),
        "coveredCases": len(enabled_cases) - len(missing_run_case_ids),
        "missingRuns": len(missing_run_case_ids),
        "missingRunIds": missing_run_case_ids,
        "caseIds": [case.id for case in suite.cases],
    }


def format_suite_summary_table(report: Mapping[str, object]) -> str:
    fields = (
        "suiteFile",
        "caseCount",
        "enabledCases",
        "disabledCases",
        "runCount",
        "coveredCases",
        "missingRuns",
        "missingRunIds",
        "caseIds",
    )
    rows = [
        (field, suite_summary_table_value(report[field]))
        for field in fields
        if report.get(field) is not None
    ]
    rows.extend(langsmith_dry_run_table_rows(report.get("langsmithDryRun")))
    width = max([len("FIELD"), *(len(field) for field, _ in rows)])
    lines = [f"{'FIELD':<{width}}  VALUE"]
    lines.extend(f"{field:<{width}}  {value}" for field, value in rows)
    return "\n".join(lines) + "\n"


def suite_summary_table_value(value: object) -> str:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        sequence = cast(Sequence[object], value)
        return ",".join(str(item) for item in sequence)
    return apply_report_table_value(value)


def langsmith_dry_run_summary(
    report: Mapping[str, object],
    *,
    report_file: Path,
    persist_command: str = "",
    summary_command: str = "",
    case_file: Path | None = None,
    run_file: Path | None = None,
) -> dict[str, object]:
    split_counts = int_mapping_value(report.get("splitCounts", {}))
    summary = {
        "status": report.get("status"),
        "datasetName": report.get("datasetName"),
        "examples": report.get("examples"),
        "caseIds": string_list_value(report.get("caseIds", ())),
        "metadataCaseIds": string_list_value(report.get("metadataCaseIds", ())),
        "sourceRunIds": string_list_value(report.get("sourceRunIds", ())),
        "caseSourceRunIds": string_string_mapping_value(report.get("caseSourceRunIds", {})),
        "reportFile": str(report_file),
    }
    if case_file is not None:
        summary["caseFile"] = str(case_file)
    if run_file is not None:
        summary["runFile"] = str(run_file)
    if split_counts:
        summary["splitCounts"] = split_counts
    source_suite = langsmith_source_suite_value(report)
    if source_suite:
        summary["sourceSuite"] = source_suite
    feedback_promotion = langsmith_feedback_promotion_summary(report)
    if feedback_promotion:
        summary.update(feedback_promotion)
        feedback_review_action = langsmith_feedback_review_action(
            cast(Mapping[object, object], summary)
        )
        if feedback_review_action:
            summary["feedbackReviewAction"] = feedback_review_action
        feedback_review_actions = langsmith_feedback_review_actions(
            cast(Mapping[object, object], summary)
        )
        if feedback_review_actions:
            summary["feedbackReviewActions"] = feedback_review_actions
    feedback_review_queue = langsmith_feedback_review_queue_summary(report)
    if feedback_review_queue:
        summary["feedbackReviewQueue"] = feedback_review_queue
    sync_command = langsmith_sync_command_value(report)
    if sync_command:
        summary["syncCommand"] = sync_command
    live_sync_command = langsmith_live_sync_command_value(report)
    if live_sync_command:
        summary["liveSyncCommand"] = live_sync_command
    if persist_command:
        summary["persistCommand"] = persist_command
    if summary_command:
        summary["summaryCommand"] = summary_command
    readiness_command = langsmith_report_string_value(report, "readinessCommand")
    if not readiness_command:
        readiness_command = langsmith_readiness_command(summary.get("reportFile"))
    if readiness_command:
        summary["preflightFile"] = RELEASE_SMOKE_PREFLIGHT_FILE
        summary["preflightEnvTemplate"] = RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE
        summary["replatformReadinessFile"] = REPLATFORM_READINESS_FILE
        summary["smokePlanFile"] = RELEASE_SMOKE_PLAN_FILE
        summary["releaseEvidenceFile"] = RELEASE_EVIDENCE_FILE
        summary["releaseReadinessFile"] = RELEASE_READINESS_FILE
        summary["readinessCommand"] = readiness_command
    required_readiness_reports = langsmith_report_string_list_value(
        report,
        "requiredReadinessReports",
    )
    if required_readiness_reports:
        summary["requiredReadinessReports"] = required_readiness_reports
    readiness_reports = langsmith_report_string_mapping_value(report, "readinessReports")
    if readiness_reports:
        summary["readinessReports"] = readiness_reports
    product_boundary = langsmith_report_mapping_value(report, "productCapabilityBoundary")
    if product_boundary:
        summary["productCapabilityBoundary"] = product_boundary
    product_boundary_readiness_command = langsmith_report_string_value(
        report,
        "productBoundaryReadinessCommand",
    )
    if product_boundary_readiness_command:
        summary["productBoundaryReadinessCommand"] = product_boundary_readiness_command
    trace_grading = trace_grading_summary_value(report)
    if trace_grading:
        summary.update(trace_grading)
    context_diagnostics = context_manifest_diagnostics_summary_value(report)
    if context_diagnostics:
        summary.update(context_diagnostics)
    release_gate = langsmith_release_gate_summary_value(report)
    if release_gate:
        summary["releaseGate"] = release_gate
    next_actions = langsmith_release_next_actions(summary) if release_gate else []
    next_actions.extend(langsmith_feedback_review_queue_next_actions(summary))
    if next_actions:
        summary["nextActions"] = next_actions
    return summary


def langsmith_summary_command(
    *,
    suite_file: Path,
    dataset_name: str,
    report_file: Path,
    feedback_review_status: str = "",
    feedback_review_tags: Sequence[str] = (),
    feedback_review_note: str = "",
) -> str:
    feedback_review_args = feedback_review_command_args(
        status=feedback_review_status,
        tags=feedback_review_tags,
        note=feedback_review_note,
    )
    return (
        "reactor-agent-eval-apply "
        f"--suite-file {quote(str(suite_file))} "
        f"--dataset-name {quote(dataset_name)} "
        "--summary "
        f"--langsmith-dry-run-report-file {quote(str(report_file))} "
        f"{feedback_review_args}"
        "--output table"
    )


def feedback_review_command_args(
    *,
    status: str = "",
    tags: Sequence[str] = (),
    note: str = "",
) -> str:
    parts: list[str] = []
    if status.strip():
        parts.append(f"--feedback-review-status {quote(status.strip())}")
    parts.extend(f"--feedback-review-tag {quote(tag.strip())}" for tag in tags if tag.strip())
    if note.strip():
        parts.append(f"--feedback-review-note {quote(note.strip())}")
    if not parts:
        return ""
    return f"{' '.join(parts)} "


def langsmith_release_next_actions(summary: Mapping[str, object]) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    required_reports = string_list_value(summary.get("requiredReadinessReports", ()))
    readiness_reports = string_string_mapping_value(summary.get("readinessReports", {}))
    if not required_reports or not readiness_reports:
        report_file = summary.get("reportFile")
        if isinstance(report_file, str) and report_file.strip():
            required_reports = ["langsmith_eval_sync"]
            readiness_reports = {"langsmith_eval_sync": report_file.strip()}
    minor_boundary_reports = (
        required_reports
        if "hardening_suite" in required_reports
        and isinstance(summary.get("productCapabilityBoundary"), Mapping)
        else []
    )
    feedback_review_action = summary.get("feedbackReviewAction")
    if isinstance(feedback_review_action, str) and feedback_review_action.strip():
        actions.append(langsmith_feedback_review_next_action(feedback_review_action.strip()))
    feedback_review_actions = string_list_value(summary.get("feedbackReviewActions", ()))
    for command in feedback_review_actions:
        actions.append(langsmith_feedback_review_next_action(command))
    bulk_review_action = summary.get("bulkReviewAction")
    if isinstance(bulk_review_action, str) and bulk_review_action.strip():
        actions.append(langsmith_feedback_bulk_review_next_action(bulk_review_action.strip()))
    readiness_command = summary.get("readinessCommand")
    live_sync_command = summary.get("liveSyncCommand")
    if isinstance(live_sync_command, str) and live_sync_command.strip():
        preflight_command = f"{live_sync_command.strip()} --preflight-only --output table"
        preflight_action: dict[str, object] = {
            "id": "preflight-langsmith",
            "label": "Preflight the LangSmith eval sync credentials",
            "command": preflight_command,
            "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
            "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
            "preflightFile": RELEASE_SMOKE_PREFLIGHT_FILE,
            "preflightEnvTemplate": RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
            "releaseReadinessFile": RELEASE_READINESS_FILE,
            "remediationCommand": preflight_command,
        }
        if isinstance(readiness_command, str) and readiness_command.strip():
            preflight_action["releaseReadinessCommand"] = readiness_command.strip()
        sync_action: dict[str, object] = {
            "id": "sync-langsmith",
            "label": "Run the LangSmith eval sync without dry-run",
            "command": live_sync_command.strip(),
            "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
            "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
            "preflightFile": RELEASE_SMOKE_PREFLIGHT_FILE,
            "preflightEnvTemplate": RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
            "releaseReadinessFile": RELEASE_READINESS_FILE,
            "remediationCommand": live_sync_command.strip(),
        }
        if isinstance(readiness_command, str) and readiness_command.strip():
            sync_action["releaseReadinessCommand"] = readiness_command.strip()
        if required_reports and readiness_reports:
            preflight_action["requiredReadinessReports"] = required_reports
            preflight_action["readinessReports"] = readiness_reports
            sync_action["requiredReadinessReports"] = required_reports
            sync_action["readinessReports"] = readiness_reports
            readiness_report_arg = readiness_report_args_for_reports(
                required_reports=required_reports,
                report_files=readiness_reports,
            )
            if readiness_report_arg:
                preflight_action["readinessReportArg"] = readiness_report_arg
                sync_action["readinessReportArg"] = readiness_report_arg
        actions.append(preflight_action)
        actions.append(sync_action)
    if "hardening_suite" in required_reports:
        actions.append(
            {
                "id": "generate-hardening-suite",
                "label": "Generate the hardening suite report required for minor boundary review",
                "command": rag_ingestion_lifecycle_remediation_command(),
                "readinessReportArg": (
                    f"--readiness-report hardening_suite={HARDENING_SUITE_REPORT_FILE}"
                ),
                **(
                    {"releaseReadinessCommand": readiness_command.strip()}
                    if isinstance(readiness_command, str) and readiness_command.strip()
                    else {}
                ),
                "requiredReadinessReports": required_reports,
                "readinessReports": readiness_reports,
            }
        )
    if isinstance(readiness_command, str) and readiness_command.strip():
        label = "Refresh release readiness with the LangSmith eval sync report"
        if minor_boundary_reports:
            label = "Refresh release readiness with candidate LangSmith and hardening reports"
        elif "hardening_suite" in required_reports:
            label = "Refresh release readiness with promoted LangSmith and hardening reports"
        readiness_action: dict[str, object] = {
            "id": "refresh-release-readiness",
            "label": label,
            "command": readiness_command.strip(),
            "envFileCommand": langsmith_env_file_command(readiness_command.strip()),
            "remediationCommand": readiness_command.strip(),
            "latestTagCommand": LATEST_TAG_COMMAND,
            "recommendedTagSource": RECOMMENDED_TAG_SOURCE,
            "replatformReadinessFile": REPLATFORM_READINESS_FILE,
            "smokePlanFile": RELEASE_SMOKE_PLAN_FILE,
            "releaseEvidenceFile": RELEASE_EVIDENCE_FILE,
            "releaseReadinessFile": RELEASE_READINESS_FILE,
        }
        if required_reports and readiness_reports:
            readiness_action["requiredReadinessReports"] = required_reports
            readiness_action["readinessReports"] = readiness_reports
            if minor_boundary_reports:
                readiness_action["minorBoundaryReports"] = minor_boundary_reports
            readiness_report_arg = readiness_report_args_for_reports(
                required_reports=required_reports,
                report_files=readiness_reports,
            )
            if readiness_report_arg:
                readiness_action["readinessReportArg"] = readiness_report_arg
        else:
            report_file = summary.get("reportFile")
            if isinstance(report_file, str) and report_file.strip():
                readiness_action["requiredReadinessReports"] = ["langsmith_eval_sync"]
                readiness_action["readinessReports"] = {
                    "langsmith_eval_sync": report_file.strip(),
                }
                readiness_action["readinessReportArg"] = (
                    f"--readiness-report langsmith_eval_sync={quote(report_file.strip())}"
                )
        actions.append(readiness_action)
    return actions


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


def langsmith_feedback_bulk_review_next_action(command: str) -> dict[str, object]:
    return {
        "id": "bulk-review-feedback",
        "label": "Close promoted feedback after LangSmith eval handoff is reviewed",
        "command": command,
    }


def langsmith_feedback_review_queue_next_actions(
    summary: Mapping[str, object],
) -> list[dict[str, object]]:
    feedback_review_queue = summary.get("feedbackReviewQueue")
    if not isinstance(feedback_review_queue, Mapping):
        return []
    queue = cast(Mapping[object, object], feedback_review_queue)
    actions: list[dict[str, object]] = []
    eval_case_id = feedback_review_queue_eval_case_id(queue)
    source_run_id = feedback_review_queue_source_run_id(summary, eval_case_id)
    review_action = queue.get("reviewAction")
    if isinstance(review_action, str) and review_action.strip():
        action: dict[str, object] = {
            "id": "review-feedback-queue",
            "label": "Review feedback waiting for LangSmith eval source metadata",
            "command": review_action.strip(),
        }
        if eval_case_id:
            action["evalCaseId"] = eval_case_id
        if source_run_id:
            action["sourceRunId"] = source_run_id
        actions.append(action)
    candidate_review_action = queue.get("candidateReviewAction")
    if isinstance(candidate_review_action, str) and candidate_review_action.strip():
        candidate_tag = queue.get("candidateTag")
        normalized_candidate_tag = (
            candidate_tag.strip()
            if isinstance(candidate_tag, str) and candidate_tag.strip()
            else ""
        )
        candidate_id = normalized_candidate_tag.removeprefix("rag-candidate:")
        action = {
            "id": f"review-rag-candidate-{candidate_id}"
            if candidate_id
            else "review-rag-candidates",
            "label": (
                "Review the RAG ingestion candidate behind the LangSmith report"
                if candidate_id
                else "Review the RAG ingestion candidates behind the LangSmith report"
            ),
            "command": candidate_review_action.strip(),
        }
        if normalized_candidate_tag:
            action["candidateTag"] = normalized_candidate_tag
        if eval_case_id:
            action["evalCaseId"] = eval_case_id
        if source_run_id:
            action["sourceRunId"] = source_run_id
        actions.append(action)
    bulk_review_action = queue.get("bulkReviewAction")
    if isinstance(bulk_review_action, str) and bulk_review_action.strip():
        action = {
            "id": "bulk-review-feedback-queue",
            "label": "Close queued feedback after the LangSmith eval handoff is reviewed",
            "command": bulk_review_action.strip(),
        }
        candidate_tag = queue.get("candidateTag")
        if isinstance(candidate_tag, str) and candidate_tag.strip():
            action["candidateTag"] = candidate_tag.strip()
        if eval_case_id:
            action["evalCaseId"] = eval_case_id
        if source_run_id:
            action["sourceRunId"] = source_run_id
        actions.append(action)
    memory_lifecycle_action = queue.get("memoryLifecycleAction")
    if isinstance(memory_lifecycle_action, str) and memory_lifecycle_action.strip():
        actions.append(
            {
                "id": "verify-memory-lifecycle",
                "label": "Verify memory lifecycle gates before closing feedback",
                "command": memory_lifecycle_action.strip(),
                "preflightFile": RELEASE_SMOKE_PREFLIGHT_FILE,
                "preflightEnvTemplate": RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
                "replatformReadinessFile": REPLATFORM_READINESS_FILE,
                "smokePlanFile": RELEASE_SMOKE_PLAN_FILE,
                "releaseEvidenceFile": RELEASE_EVIDENCE_FILE,
                "releaseReadinessFile": RELEASE_READINESS_FILE,
                "readinessReportArg": (
                    f"--readiness-report hardening_suite={HARDENING_SUITE_REPORT_FILE}"
                ),
                "requiredReadinessReports": ["hardening_suite"],
                "readinessReports": {"hardening_suite": HARDENING_SUITE_REPORT_FILE},
            }
        )
    return actions


def feedback_review_queue_eval_case_id(queue: Mapping[object, object]) -> str:
    case_ids = string_list_value(queue.get("caseIds", ()))
    if len(case_ids) == 1:
        return case_ids[0]
    return ""


def feedback_review_queue_source_run_id(
    summary: Mapping[str, object],
    eval_case_id: str,
) -> str:
    if not eval_case_id:
        return ""
    case_source_run_ids = summary.get("caseSourceRunIds")
    if not isinstance(case_source_run_ids, Mapping):
        return ""
    source_run_id = cast(Mapping[object, object], case_source_run_ids).get(eval_case_id)
    return source_run_id.strip() if isinstance(source_run_id, str) else ""


def langsmith_report_string_value(report: Mapping[str, object], field_name: str) -> str:
    value = report.get(field_name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping):
        return ""
    evidence_value = cast(Mapping[object, object], evidence).get(field_name)
    return (
        evidence_value.strip() if isinstance(evidence_value, str) and evidence_value.strip() else ""
    )


def langsmith_report_string_list_value(
    report: Mapping[str, object],
    field_name: str,
) -> list[str]:
    values = string_list_value(report.get(field_name, ()))
    if values:
        return values
    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping):
        return []
    return string_list_value(cast(Mapping[object, object], evidence).get(field_name, ()))


def langsmith_report_string_mapping_value(
    report: Mapping[str, object],
    field_name: str,
) -> dict[str, str]:
    mapping = string_string_mapping_value(report.get(field_name, {}))
    if mapping:
        return mapping
    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping):
        return {}
    return string_string_mapping_value(cast(Mapping[object, object], evidence).get(field_name, {}))


def langsmith_report_mapping_value(
    report: Mapping[str, object],
    field_name: str,
) -> dict[object, object]:
    value = report.get(field_name)
    if isinstance(value, Mapping):
        return dict(cast(Mapping[object, object], value))
    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping):
        return {}
    evidence_value = cast(Mapping[object, object], evidence).get(field_name)
    return (
        dict(cast(Mapping[object, object], evidence_value))
        if isinstance(evidence_value, Mapping)
        else {}
    )


def langsmith_source_suite_value(report: Mapping[str, object]) -> str:
    source = report.get("source")
    if not isinstance(source, Mapping):
        return ""
    suite_file = cast(Mapping[object, object], source).get("suiteFile")
    return suite_file.strip() if isinstance(suite_file, str) and suite_file.strip() else ""


def langsmith_feedback_review_queue_summary(report: Mapping[str, object]) -> dict[str, object]:
    feedback_review_queue = report.get("feedbackReviewQueue")
    if not isinstance(feedback_review_queue, Mapping):
        return {}
    queue_mapping = cast(Mapping[object, object], feedback_review_queue)
    summary: dict[str, object] = {}
    case_ids = string_list_value(queue_mapping.get("caseIds", ()))
    ratings = langsmith_feedback_rating_counts(queue_mapping.get("feedbackRatingCounts", {}))
    sources = langsmith_feedback_rating_counts(queue_mapping.get("feedbackSourceCounts", {}))
    workflows = langsmith_feedback_rating_counts(queue_mapping.get("workflowTagCounts", {}))
    review_action = queue_mapping.get("reviewAction")
    export_action = queue_mapping.get("exportAction")
    candidate_review_action = queue_mapping.get("candidateReviewAction")
    bulk_review_action = queue_mapping.get("bulkReviewAction")
    memory_lifecycle_action = queue_mapping.get("memoryLifecycleAction")
    candidate_tag = queue_mapping.get("candidateTag")
    review_status = queue_mapping.get("reviewStatus")
    review_tags = string_list_value(queue_mapping.get("reviewTags", ()))
    review_note = queue_mapping.get("reviewNote")
    if case_ids:
        summary["caseIds"] = case_ids
    if isinstance(candidate_tag, str) and candidate_tag.strip():
        summary["candidateTag"] = candidate_tag.strip()
    else:
        recovered_candidate_tag = candidate_workflow_tag_from_case_ids(case_ids)
        if recovered_candidate_tag:
            summary["candidateTag"] = recovered_candidate_tag
    if ratings:
        summary["feedbackRatingCounts"] = ratings
    if sources:
        summary["feedbackSourceCounts"] = sources
    if workflows:
        summary["workflowTagCounts"] = workflows
    if isinstance(review_status, str) and review_status.strip():
        summary["reviewStatus"] = review_status.strip()
    if review_tags:
        summary["reviewTags"] = review_tags
    if isinstance(review_note, str) and review_note.strip():
        summary["reviewNote"] = review_note.strip()
    if feedback_review_closed(summary):
        return summary
    if isinstance(review_action, str) and review_action.strip():
        summary["reviewAction"] = review_action.strip()
    else:
        fallback_review_action = feedback_review_queue_action(summary)
        if fallback_review_action:
            summary["reviewAction"] = fallback_review_action
    if isinstance(export_action, str) and export_action.strip():
        summary["exportAction"] = export_action.strip()
    else:
        fallback_export_action = feedback_review_queue_export_action(summary)
        if fallback_export_action:
            summary["exportAction"] = fallback_export_action
    if isinstance(candidate_review_action, str) and candidate_review_action.strip():
        summary["candidateReviewAction"] = candidate_review_action.strip()
    else:
        fallback_candidate_review_action = feedback_review_queue_candidate_review_action(summary)
        if fallback_candidate_review_action:
            summary["candidateReviewAction"] = fallback_candidate_review_action
    if isinstance(bulk_review_action, str) and bulk_review_action.strip():
        summary["bulkReviewAction"] = bulk_review_action.strip()
    else:
        fallback_bulk_review_action = feedback_review_queue_bulk_review_action(summary)
        if fallback_bulk_review_action:
            summary["bulkReviewAction"] = fallback_bulk_review_action
    if isinstance(memory_lifecycle_action, str) and memory_lifecycle_action.strip():
        summary["memoryLifecycleAction"] = memory_lifecycle_action.strip()
    else:
        fallback_memory_lifecycle_action = feedback_review_queue_memory_lifecycle_action(summary)
        if fallback_memory_lifecycle_action:
            summary["memoryLifecycleAction"] = fallback_memory_lifecycle_action
    return summary


def langsmith_feedback_promotion_summary(report: Mapping[str, object]) -> dict[str, object]:
    feedback_promotion = report.get("feedbackPromotion")
    if not isinstance(feedback_promotion, Mapping):
        return {}
    feedback_mapping = cast(Mapping[object, object], feedback_promotion)
    summary: dict[str, object] = {}
    case_ids = string_list_value(feedback_mapping.get("caseIds", ()))
    feedback_ids = string_list_value(feedback_mapping.get("feedbackIds", ()))
    ratings = langsmith_feedback_rating_counts(feedback_mapping.get("feedbackRatingCounts", {}))
    sources = langsmith_feedback_rating_counts(feedback_mapping.get("feedbackSourceCounts", {}))
    workflows = langsmith_feedback_rating_counts(feedback_mapping.get("workflowTagCounts", {}))
    expected_citations = langsmith_expected_citation_counts(
        feedback_mapping.get("expectedCitationCounts", {})
    )
    bulk_review_action = feedback_mapping.get("bulkReviewAction")
    if case_ids:
        summary["feedbackCases"] = len(case_ids)
    if feedback_ids:
        summary["feedbackIds"] = len(feedback_ids)
        summary["feedbackIdList"] = feedback_ids
        summary["feedbackReviewIds"] = feedback_ids
    if ratings:
        summary["feedbackRatings"] = ratings
    if sources:
        summary["feedbackSources"] = sources
    if workflows:
        summary["feedbackWorkflows"] = workflows
    if expected_citations:
        summary["feedbackExpectedCitations"] = expected_citations
    if isinstance(bulk_review_action, str) and bulk_review_action.strip():
        summary["bulkReviewAction"] = bulk_review_action.strip()
    else:
        recovered_bulk_review_action = langsmith_feedback_bulk_review_action(summary)
        if recovered_bulk_review_action:
            summary["bulkReviewAction"] = recovered_bulk_review_action
    return summary


def langsmith_feedback_bulk_review_action(summary: Mapping[str, object]) -> str:
    feedback_ids = string_list_value(
        summary.get(
            "feedbackReviewIds",
            summary.get("feedbackIdList", ()),
        )
    )
    if not feedback_ids:
        return ""
    case_ids = string_list_value(summary.get("caseIds", ()))
    feedback_case_count = summary.get("feedbackCases")
    required_workflow_count = max(len(case_ids), len(feedback_ids))
    if (
        not case_ids
        and isinstance(feedback_case_count, int)
        and not isinstance(feedback_case_count, bool)
        and feedback_case_count > 0
    ):
        required_workflow_count = max(feedback_case_count, len(feedback_ids))
    workflow_counts = langsmith_feedback_rating_counts(summary.get("feedbackWorkflows", {}))
    candidate_tag = candidate_workflow_tag_from_case_ids(case_ids)
    if not candidate_tag:
        candidate_tags = sorted(
            tag
            for tag, count in workflow_counts.items()
            if tag.startswith("rag-candidate:") and count > 0
        )
        candidate_tag = candidate_tags[0] if len(candidate_tags) == 1 else ""
    if candidate_tag:
        source_counts = langsmith_feedback_rating_counts(summary.get("feedbackSources", {}))
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
            langsmith_expected_citation_counts(summary.get("feedbackExpectedCitations", {})).items()
        )
        if count == required_workflow_count
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


def langsmith_feedback_rating_counts(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    mapping = cast(Mapping[object, object], value)
    return {
        key: count
        for key, count in mapping.items()
        if isinstance(key, str) and isinstance(count, int) and not isinstance(count, bool)
    }


def langsmith_expected_citation_counts(value: object) -> dict[str, int]:
    return {
        citation_id: count
        for citation_id, count in langsmith_feedback_rating_counts(value).items()
        if is_citation_safe_id(citation_id)
    }


def langsmith_sync_command_value(report: Mapping[str, object]) -> str:
    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping):
        return ""
    command = cast(Mapping[object, object], evidence).get("command")
    return command.strip() if isinstance(command, str) and command.strip() else ""


def langsmith_live_sync_command_value(report: Mapping[str, object]) -> str:
    command = report.get("liveSyncCommand")
    if isinstance(command, str) and command.strip():
        return command.strip()
    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping):
        return ""
    evidence_command = cast(Mapping[object, object], evidence).get("liveSyncCommand")
    return (
        evidence_command.strip()
        if isinstance(evidence_command, str) and evidence_command.strip()
        else ""
    )


def langsmith_release_gate_summary_value(report: Mapping[str, object]) -> dict[str, object]:
    release_gate = report.get("releaseGate")
    if not isinstance(release_gate, Mapping):
        return {}
    release_gate_mapping = cast(Mapping[object, object], release_gate)
    summary: dict[str, object] = {}
    status = release_gate_mapping.get("status")
    if isinstance(status, str) and status:
        summary["status"] = status
    reason = release_gate_mapping.get("reason")
    if isinstance(reason, str) and reason:
        summary["reason"] = reason
    required_report = release_gate_mapping.get("requiredReport")
    if isinstance(required_report, str) and required_report:
        summary["requiredReport"] = required_report
    remediation = string_list_value(release_gate_mapping.get("remediation", ()))
    if remediation:
        summary["remediation"] = remediation
    remediation_command = release_gate_mapping.get("remediationCommand")
    if isinstance(remediation_command, str) and remediation_command.strip():
        summary["remediationCommand"] = remediation_command.strip()
    return summary


def trace_grading_summary_value(report: Mapping[str, object]) -> dict[str, object]:
    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping):
        return {}
    evidence_mapping = cast(Mapping[object, object], evidence)
    trace_grading = evidence_mapping.get("traceGrading")
    if not isinstance(trace_grading, Mapping):
        return {}
    trace_grading_mapping = cast(Mapping[object, object], trace_grading)
    missing_run_case_ids = string_list_value(trace_grading_mapping.get("missingRunCaseIds", ()))
    summary: dict[str, object] = {}
    graded_runs = trace_grading_mapping.get("gradedRuns")
    if isinstance(graded_runs, int) and not isinstance(graded_runs, bool):
        summary["gradedRuns"] = graded_runs
    summary["missingRunCases"] = len(missing_run_case_ids)
    grounding_summary = grounding_citation_summary_value(trace_grading_mapping.get("grades"))
    if grounding_summary:
        summary.update(grounding_summary)
    deterministic_summary = trace_deterministic_eval_summary_value(trace_grading_mapping)
    if deterministic_summary:
        summary.update(deterministic_summary)
    return summary


def context_manifest_diagnostics_summary_value(report: Mapping[str, object]) -> dict[str, object]:
    evidence = report.get("evidence")
    if not isinstance(evidence, Mapping):
        return {}
    diagnostics = cast(Mapping[object, object], evidence).get("contextManifestDiagnostics")
    if not isinstance(diagnostics, Mapping):
        return {}
    diagnostics_mapping = cast(Mapping[object, object], diagnostics)
    summary: dict[str, object] = {}
    status = diagnostics_mapping.get("status")
    ok = diagnostics_mapping.get("ok")
    memory_status_counts = int_mapping_value(diagnostics_mapping.get("memoryStatusCounts", {}))
    skipped_memory_status_counts = int_mapping_value(
        diagnostics_mapping.get("skippedMemoryStatusCounts", {})
    )
    if ok is True or ok is False:
        summary["contextManifestDiagnosticsOk"] = ok
    if isinstance(status, str) and status.strip():
        summary["contextManifestDiagnosticsStatus"] = status.strip()
    finding_codes = context_manifest_finding_codes(diagnostics_mapping.get("findings", ()))
    if finding_codes:
        summary["contextManifestDiagnosticsFindings"] = finding_codes
    if memory_status_counts:
        summary["memoryStatusCounts"] = memory_status_counts
    if skipped_memory_status_counts:
        summary["skippedMemoryStatusCounts"] = skipped_memory_status_counts
    memory_lifecycle_action = memory_lifecycle_action_from_diagnostics(
        memory_status_counts=memory_status_counts,
        skipped_memory_status_counts=skipped_memory_status_counts,
    )
    if memory_lifecycle_action:
        summary["memoryLifecycleAction"] = memory_lifecycle_action
    return summary


def context_manifest_finding_codes(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    codes: list[str] = []
    for item in cast(Sequence[object], value):
        if not isinstance(item, Mapping):
            continue
        code = cast(Mapping[object, object], item).get("code")
        if isinstance(code, str) and code.strip():
            codes.append(code.strip())
    return codes


def memory_lifecycle_action_from_diagnostics(
    *,
    memory_status_counts: Mapping[str, int],
    skipped_memory_status_counts: Mapping[str, int],
) -> str:
    if skipped_memory_status_counts:
        return feedback_review_queue_memory_lifecycle_action({"workflowTagCounts": {"memory": 1}})
    if any(status != "active" for status in memory_status_counts):
        return feedback_review_queue_memory_lifecycle_action({"workflowTagCounts": {"memory": 1}})
    return ""


def grounding_citation_summary_value(value: object) -> dict[str, object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return {}
    citation_cases = 0
    cited_chunks = 0
    uncited_chunks = 0
    citation_documents: list[str] = []
    seen_documents: set[str] = set()
    for grade in cast(Sequence[object], value):
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


def format_apply_report_table(report: Mapping[str, object]) -> str:
    fields = (
        "status",
        "caseId",
        "sourceRunId",
        "runStatus",
        "runId",
        "dryRun",
        "caseCount",
        "runCount",
    )
    rows = [
        (field, apply_report_table_value(report[field]))
        for field in fields
        if report.get(field) is not None
    ]
    rows.extend(promotion_coverage_table_rows(report.get("promotionCoverage")))
    if report.get("persistCommand"):
        rows.append(("suitePersistCommand", apply_report_table_value(report["persistCommand"])))
    rows.extend(langsmith_dry_run_table_rows(report.get("langsmithDryRun")))
    width = max([len("FIELD"), *(len(field) for field, _ in rows)])
    lines = [f"{'FIELD':<{width}}  VALUE"]
    lines.extend(f"{field:<{width}}  {value}" for field, value in rows)
    return "\n".join(lines) + "\n"


def promotion_coverage_table_rows(value: object) -> list[tuple[str, str]]:
    if not isinstance(value, Mapping):
        return []
    coverage = cast(Mapping[object, object], value)
    rows: list[tuple[str, str]] = []
    for field, key in (
        ("coverageSourceRunId", "sourceRunIdPresent"),
        ("coverageRunFixture", "runFixturePresent"),
        ("coverageRunMatchedCase", "runFixtureMatchedCase"),
        ("coverageRunContextDiagnostics", "runContextDiagnosticsPresent"),
        ("coverageRequiredSource", "requiredSourceRunId"),
        ("coverageRequiredRunFile", "requiredRunFile"),
        ("coverageRequiredContextDiagnostics", "requiredContextDiagnostics"),
        ("coverageCitationMarkers", "citationMarkersPresent"),
        ("coverageRunCitationMarkers", "runCitationMarkersPresent"),
        ("coverageContextCitationEvalCaseId", "contextCitationEvalCaseIdMatched"),
        ("coverageContextCitationWorkflowTag", "contextCitationWorkflowTagMatched"),
        (
            "coverageCitationFailureAllowsMissing",
            "citationFailureAllowsMissingRunCitation",
        ),
    ):
        if key in coverage:
            rows.append((field, apply_report_table_value(coverage[key])))
    return rows


def apply_persist_command(args: argparse.Namespace) -> str:
    command = f"reactor-agent-eval-apply --case-file {quote(args.case_file)} "
    if args.run_file:
        command = f"{command}--run-file {quote(args.run_file)} "
    command = (
        f"{command}--suite-file {quote(args.suite_file)} --dataset-name {quote(args.dataset_name)} "
    )
    if args.replace:
        command = f"{command}--replace "
    if args.require_source_run_id:
        command = f"{command}--require-source-run-id "
    if args.require_run_file:
        command = f"{command}--require-run-file "
    if args.require_context_diagnostics:
        command = f"{command}--require-context-diagnostics "
    if args.langsmith_dry_run_report_file:
        command = (
            f"{command}--langsmith-dry-run-report-file {quote(args.langsmith_dry_run_report_file)} "
        )
    return f"{command}--output table"


def langsmith_dry_run_table_rows(value: object) -> list[tuple[str, str]]:
    if not isinstance(value, Mapping):
        return []
    summary = cast(Mapping[object, object], value)
    release_gate = summary.get("releaseGate")
    release_gate_mapping: Mapping[object, object] = (
        cast(Mapping[object, object], release_gate) if isinstance(release_gate, Mapping) else {}
    )
    remediation = string_list_value(release_gate_mapping.get("remediation", ()))
    rows: list[tuple[str, str]] = []

    def append_row(field: str, item: object) -> None:
        if item is not None and item != "":
            rows.append((field, apply_report_table_value(item)))

    append_row("langsmithDryRunStatus", summary.get("status"))
    append_row("langsmithDryRunDataset", summary.get("datasetName"))
    append_row("langsmithDryRunCases", len(string_list_value(summary.get("caseIds", ()))))
    append_row(
        "langsmithSourceRunIds",
        len(string_list_value(summary.get("sourceRunIds", ()))),
    )
    append_row(
        "langsmithCaseSourceRunMappings",
        len(string_string_mapping_value(summary.get("caseSourceRunIds", {}))),
    )
    append_row(
        "langsmithDryRunFeedbackIds",
        ",".join(string_list_value(summary.get("feedbackIdList", ()))),
    )
    append_row(
        "langsmithFeedbackReviewIds",
        ",".join(string_list_value(summary.get("feedbackReviewIds", ()))),
    )
    append_row(
        "langsmithDryRunFeedbackWorkflows",
        apply_report_mapping_summary(summary.get("feedbackWorkflows")),
    )
    append_row(
        "langsmithDryRunFeedbackSources",
        apply_report_mapping_summary(summary.get("feedbackSources")),
    )
    append_row(
        "langsmithDryRunExpectedCitations",
        apply_report_mapping_summary(summary.get("feedbackExpectedCitations")),
    )
    append_row("langsmithFeedbackReviewAction", langsmith_feedback_review_action(summary))
    append_row(
        "langsmithFeedbackReviewActions",
        ";".join(string_list_value(summary.get("feedbackReviewActions", ()))),
    )
    append_row("langsmithFeedbackBulkReviewAction", summary.get("bulkReviewAction"))
    feedback_review_queue = summary.get("feedbackReviewQueue")
    if isinstance(feedback_review_queue, Mapping):
        feedback_review_queue_mapping = cast(Mapping[object, object], feedback_review_queue)
        append_row(
            "langsmithFeedbackQueueCases",
            len(string_list_value(feedback_review_queue_mapping.get("caseIds", ()))),
        )
        append_row(
            "langsmithFeedbackQueueRatings",
            apply_report_mapping_summary(feedback_review_queue_mapping.get("feedbackRatingCounts")),
        )
        append_row(
            "langsmithFeedbackQueueSources",
            apply_report_mapping_summary(feedback_review_queue_mapping.get("feedbackSourceCounts")),
        )
        append_row(
            "langsmithFeedbackQueueWorkflows",
            apply_report_mapping_summary(feedback_review_queue_mapping.get("workflowTagCounts")),
        )
        append_row(
            "langsmithFeedbackQueueAction", feedback_review_queue_mapping.get("reviewAction")
        )
        queue_export_action = feedback_review_queue_mapping.get("exportAction")
        if not isinstance(queue_export_action, str) or not queue_export_action.strip():
            queue_export_action = feedback_review_queue_export_action(
                {
                    str(key): value
                    for key, value in feedback_review_queue_mapping.items()
                    if isinstance(key, str)
                }
            )
        append_row(
            "langsmithFeedbackQueueExportAction",
            queue_export_action,
        )
        queue_candidate_action = feedback_review_queue_mapping.get("candidateReviewAction")
        if not isinstance(queue_candidate_action, str) or not queue_candidate_action.strip():
            queue_workflows = int_mapping_value(
                feedback_review_queue_mapping.get("workflowTagCounts", {})
            )
            queue_candidate_action = (
                RAG_CANDIDATE_REVIEW_ACTION
                if queue_workflows.get("collection:rag-ingestion-candidate", 0) > 0
                else None
            )
        append_row(
            "langsmithFeedbackQueueCandidateAction",
            queue_candidate_action,
        )
        queue_bulk_review_action = feedback_review_queue_mapping.get("bulkReviewAction")
        if not isinstance(queue_bulk_review_action, str) or not queue_bulk_review_action.strip():
            queue_bulk_review_action = feedback_review_queue_bulk_review_action(
                {
                    str(key): value
                    for key, value in feedback_review_queue_mapping.items()
                    if isinstance(key, str)
                }
            )
        append_row(
            "langsmithFeedbackQueueBulkReviewAction",
            queue_bulk_review_action,
        )
        append_row(
            "langsmithFeedbackQueueMemoryAction",
            feedback_review_queue_mapping.get("memoryLifecycleAction"),
        )
    append_row("langsmithContextDiagnostics", summary.get("contextManifestDiagnosticsStatus"))
    append_row("langsmithContextDiagnosticsOk", summary.get("contextManifestDiagnosticsOk"))
    append_row(
        "langsmithContextDiagnosticsFindings",
        ",".join(string_list_value(summary.get("contextManifestDiagnosticsFindings", ()))),
    )
    append_row("langsmithGroundingCases", summary.get("groundingCitationCases"))
    append_row("langsmithGroundingCited", summary.get("groundingCitedChunks"))
    append_row("langsmithGroundingUncited", summary.get("groundingUncitedChunks"))
    append_row(
        "langsmithGroundingDocuments",
        ",".join(string_list_value(summary.get("groundingCitationDocuments", ()))),
    )
    append_row(
        "langsmithMemoryStatusCounts",
        apply_report_mapping_summary(summary.get("memoryStatusCounts")),
    )
    append_row(
        "langsmithSkippedMemoryStatusCounts",
        apply_report_mapping_summary(summary.get("skippedMemoryStatusCounts")),
    )
    append_row("langsmithMemoryLifecycleAction", summary.get("memoryLifecycleAction"))
    append_row("langsmithDryRunReport", summary.get("reportFile"))
    append_row("langsmithReplatformReadinessFile", summary.get("replatformReadinessFile"))
    append_row("langsmithSmokePlanFile", summary.get("smokePlanFile"))
    append_row("langsmithReleaseEvidenceFile", summary.get("releaseEvidenceFile"))
    append_row("langsmithReleaseReadinessFile", summary.get("releaseReadinessFile"))
    append_row("langsmithSyncCommand", summary.get("syncCommand"))
    append_row("langsmithLiveSyncCommand", summary.get("liveSyncCommand"))
    append_row("langsmithPersistCommand", summary.get("persistCommand"))
    append_row("langsmithSummaryCommand", summary.get("summaryCommand"))
    append_row("langsmithReadinessCommand", langsmith_readiness_command(summary.get("reportFile")))
    append_row(
        "langsmithProductBoundaryReadinessCommand",
        summary.get("productBoundaryReadinessCommand"),
    )
    rows.extend(langsmith_next_action_table_rows(summary.get("nextActions")))
    append_row("langsmithReleaseGate", release_gate_mapping.get("status"))
    append_row("langsmithReleaseGateReason", release_gate_mapping.get("reason"))
    append_row("langsmithReleaseGateNext", remediation[0] if remediation else None)
    append_row(
        "langsmithReleaseGateRemediationCommand",
        release_gate_mapping.get("remediationCommand"),
    )
    return rows


def langsmith_next_action_table_rows(value: object) -> list[tuple[str, str]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    rows: list[tuple[str, str]] = []
    action_ids: list[str] = []
    for item in cast(Sequence[object], value):
        if not isinstance(item, Mapping):
            continue
        action = cast(Mapping[object, object], item)
        action_id = action.get("id")
        command = action.get("command")
        if not (
            isinstance(action_id, str)
            and action_id.strip()
            and isinstance(command, str)
            and command.strip()
        ):
            continue
        normalized_action_id = action_id.strip()
        action_ids.append(normalized_action_id)
        action_prefix = f"langsmithNextAction.{normalized_action_id}"
        rows.append((action_prefix, command.strip()))
        remediation_command = action.get("remediationCommand")
        if isinstance(remediation_command, str) and remediation_command.strip():
            rows.append((f"{action_prefix}.remediationCommand", remediation_command.strip()))
        readiness_report_arg = action.get("readinessReportArg")
        if isinstance(readiness_report_arg, str) and readiness_report_arg.strip():
            rows.append((f"{action_prefix}.readinessReportArg", readiness_report_arg.strip()))
        for field_name in (
            "preflightFile",
            "preflightEnvTemplate",
            "replatformReadinessFile",
            "smokePlanFile",
            "releaseEvidenceFile",
            "releaseReadinessFile",
            "candidateTag",
            "evalCaseId",
            "sourceRunId",
            "requiredReviewNote",
            "latestTagCommand",
            "recommendedTagSource",
            "recommendedVersionBump",
            "recommendedTagPattern",
            "envFileCommand",
        ):
            field_value = action.get(field_name)
            if isinstance(field_value, str) and field_value.strip():
                rows.append((f"{action_prefix}.{field_name}", field_value.strip()))
        minor_boundary_reports = action.get("minorBoundaryReports")
        if isinstance(minor_boundary_reports, Sequence) and not isinstance(
            minor_boundary_reports, str | bytes | bytearray
        ):
            reports = [
                report.strip()
                for report in cast(Sequence[object], minor_boundary_reports)
                if isinstance(report, str) and report.strip()
            ]
            if reports:
                rows.append((f"{action_prefix}.minorBoundaryReports", ",".join(reports)))
        required_reports = action.get("requiredReadinessReports")
        if isinstance(required_reports, Sequence) and not isinstance(
            required_reports, str | bytes | bytearray
        ):
            reports = [
                report.strip()
                for report in cast(Sequence[object], required_reports)
                if isinstance(report, str) and report.strip()
            ]
            if reports:
                rows.append((f"{action_prefix}.requiredReadinessReports", ",".join(reports)))
        required_env_any_of = action.get("requiredEnvAnyOf")
        if isinstance(required_env_any_of, Sequence) and not isinstance(
            required_env_any_of, str | bytes | bytearray
        ):
            for index, group in enumerate(cast(Sequence[object], required_env_any_of)):
                if not isinstance(group, Sequence) or isinstance(group, str | bytes | bytearray):
                    continue
                env_names = [
                    env_name.strip()
                    for env_name in cast(Sequence[object], group)
                    if isinstance(env_name, str) and env_name.strip()
                ]
                if env_names:
                    rows.append(
                        (
                            f"{action_prefix}.requiredEnvAnyOf.{index}",
                            "|".join(env_names),
                        )
                    )
        recommended_env = action.get("recommendedEnv")
        if isinstance(recommended_env, Sequence) and not isinstance(
            recommended_env, str | bytes | bytearray
        ):
            env_names = [
                env_name.strip()
                for env_name in cast(Sequence[object], recommended_env)
                if isinstance(env_name, str) and env_name.strip()
            ]
            if env_names:
                rows.append((f"{action_prefix}.recommendedEnv", ",".join(env_names)))
        readiness_reports = action.get("readinessReports")
        if isinstance(readiness_reports, Mapping):
            for report_name, report_file in sorted(
                cast(Mapping[object, object], readiness_reports).items(),
                key=lambda item: str(item[0]),
            ):
                if isinstance(report_name, str) and isinstance(report_file, str):
                    report_name = report_name.strip()
                    report_file = report_file.strip()
                    if report_name and report_file:
                        rows.append(
                            (
                                f"{action_prefix}.readinessReports.{report_name}",
                                report_file,
                            )
                        )
    if action_ids:
        rows.insert(0, ("langsmithNextActionIds", ",".join(action_ids)))
    return rows


def langsmith_readiness_command(report_file: object) -> str:
    if not isinstance(report_file, str) or not report_file:
        return ""
    return langsmith_release_readiness_command(report_file)


def langsmith_feedback_review_action(summary: Mapping[object, object]) -> str:
    feedback_ids = string_list_value(summary.get("feedbackIdList", ()))
    if not feedback_ids:
        return ""
    if len(feedback_ids) == 1:
        return f"reactor-admin feedback --feedback-id {quote(feedback_ids[0])} --output table"
    workflow_action = langsmith_feedback_workflow_review_action(
        {
            "feedbackIds": feedback_ids,
            "feedbackRatingCounts": summary.get("feedbackRatings"),
            "feedbackSourceCounts": summary.get("feedbackSources"),
            "workflowTagCounts": summary.get("feedbackWorkflows"),
        },
        feedback_ids,
    )
    if workflow_action:
        return workflow_action
    ratings = summary.get("feedbackRatings")
    if isinstance(ratings, Mapping):
        typed_ratings = cast(Mapping[object, object], ratings)
        for rating in sorted(str(key) for key, count in typed_ratings.items() if count):
            if rating.strip():
                return (
                    f"reactor-admin feedback --rating {quote(rating.strip())} "
                    "--limit 10 --output table"
                )
    if len(feedback_ids) > 1:
        return ""
    return "reactor-admin feedback --limit 10 --output table"


def langsmith_feedback_review_actions(summary: Mapping[object, object]) -> list[str]:
    feedback_ids = string_list_value(summary.get("feedbackIdList", ()))
    if len(feedback_ids) <= 1:
        return []
    workflow_action = langsmith_feedback_workflow_review_action(
        {
            "feedbackIds": feedback_ids,
            "feedbackRatingCounts": summary.get("feedbackRatings"),
            "feedbackSourceCounts": summary.get("feedbackSources"),
            "workflowTagCounts": summary.get("feedbackWorkflows"),
        },
        feedback_ids,
    )
    if workflow_action:
        return []
    return [
        f"reactor-admin feedback --feedback-id {quote(feedback_id)} --output table"
        for feedback_id in feedback_ids
    ]


def apply_report_table_value(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def apply_report_mapping_summary(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    mapping = cast(Mapping[object, object], value)
    return ",".join(f"{key}={item}" for key, item in sorted(mapping.items()))


def string_string_mapping_value(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key.strip(): item.strip()
        for key, item in cast(Mapping[object, object], value).items()
        if isinstance(key, str) and key.strip() and isinstance(item, str) and item.strip()
    }
