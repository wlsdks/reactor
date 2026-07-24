from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from shlex import quote
from typing import Protocol, TextIO, cast
from urllib.parse import quote as url_quote
from urllib.parse import urlencode

import httpx

from reactor.context.diagnostics import context_manifest_diagnostics
from reactor.evals.langsmith_dataset import (
    build_langsmith_eval_sync_dry_run_report,
    build_langsmith_eval_sync_dry_run_report_for_suite,
    candidate_workflow_tag_from_case_ids,
    feedback_review_queue_action,
    feedback_review_queue_candidate_review_action,
    feedback_review_queue_export_action,
    feedback_review_queue_memory_lifecycle_action,
    langsmith_feedback_workflow_review_action,
    langsmith_trace_grading_value,
    trace_deterministic_eval_summary_value,
)
from reactor.evals.regression_suite_apply import (
    apply_promoted_eval_case,
    langsmith_dry_run_summary,
    promoted_eval_suite_snapshot,
    regression_suite_summary,
    regression_suite_summary_for_suite,
)
from reactor.kernel.citations import is_citation_safe_id
from reactor.observability.tracing import redact_span_attribute_value
from reactor.rag.ingestion_candidate_ids import (
    command_slug,
    is_command_slug,
    rag_candidate_case_id,
    rag_candidate_slug_from_case_id,
    rag_candidate_workflow_tag,
)
from reactor.release.readiness_actions import (
    HARDENING_SUITE_REPORT_FILE,
    readiness_report_args_for_reports,
)

CITATION_MARKER_PLACEHOLDERS = frozenset({"[replace-with-source-id]"})


@dataclass(frozen=True)
class RunCliHttpResult:
    ok: bool
    status_code: int
    body: dict[str, object] | list[object] | None = None
    error: str | None = None


class RunsHttpProbe(Protocol):
    def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult: ...

    def post_json(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> RunCliHttpResult: ...


def path_segment(value: str) -> str:
    return url_quote(value, safe="")


class HttpRunsProbe:
    def __init__(self, *, base_url: str, timeout_seconds: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def get_json(self, path: str, headers: dict[str, str]) -> RunCliHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.get(f"{self._base_url}{path}", headers=headers)
            return result_from_response(response)
        except httpx.HTTPError as error:
            return RunCliHttpResult(ok=False, status_code=0, error=str(error))

    def post_json(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> RunCliHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{self._base_url}{path}",
                    headers=headers,
                    json=payload,
                )
            return result_from_response(response)
        except httpx.HTTPError as error:
            return RunCliHttpResult(ok=False, status_code=0, error=str(error))


def result_from_response(response: httpx.Response) -> RunCliHttpResult:
    if response.status_code >= 400:
        return RunCliHttpResult(
            ok=False,
            status_code=response.status_code,
            error=response.text,
        )
    try:
        body = response.json()
    except ValueError:
        return RunCliHttpResult(
            ok=False,
            status_code=response.status_code,
            error="invalid_response",
        )
    if not isinstance(body, dict | list):
        return RunCliHttpResult(
            ok=False,
            status_code=response.status_code,
            error="invalid_response",
        )
    return RunCliHttpResult(
        ok=True,
        status_code=response.status_code,
        body=cast(dict[str, object] | list[object], body),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reactor-runs",
        description="Create, inspect, and replay Reactor runs through the public API.",
    )
    parser.add_argument("--base-url", default="", help="Reactor API base URL")
    parser.add_argument("--tenant-id", default="", help="Tenant id header")
    parser.add_argument("--user-id", default="", help="User id header")
    parser.add_argument("--role", default="", help="Optional Reactor role header")
    parser.add_argument("--token", default="", help="Optional bearer token")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a run")
    create.add_argument("--message", required=True, help="User message for the run")
    create.add_argument("--thread-id", default="", help="Optional thread id")
    create.add_argument("--checkpoint-ns", default="", help="Optional checkpoint namespace")
    create.add_argument("--metadata-json", default="{}", help="Optional JSON object metadata")
    create.add_argument(
        "--preflight-first",
        action="store_true",
        help="Run /v1/runs/preflight before creating the run",
    )
    create.add_argument(
        "--diagnose-after-create",
        action="store_true",
        help="Fetch run status, stream events, and tool invocations after creating the run",
    )
    create.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    preflight = subparsers.add_parser("preflight", help="Inspect run policy before creating a run")
    preflight.add_argument("--message", required=True, help="User message to preflight")
    preflight.add_argument("--thread-id", default="", help="Optional thread id")
    preflight.add_argument("--checkpoint-ns", default="", help="Optional checkpoint namespace")
    preflight.add_argument("--metadata-json", default="{}", help="Optional JSON object metadata")
    preflight.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    status = subparsers.add_parser("status", help="Fetch run status and metadata")
    status.add_argument("run_id")
    status.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    replay = subparsers.add_parser("replay", help="Replay persisted stream events")
    replay.add_argument("run_id")
    replay.add_argument(
        "--after-sequence",
        type=int,
        default=0,
        help="Only replay stream events after this persisted sequence",
    )
    replay.add_argument(
        "--event-type",
        default="",
        help="Only replay one stream event type, for example run.stream.token",
    )
    replay.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    cancel = subparsers.add_parser("cancel", help="Cancel a run")
    cancel.add_argument("run_id")
    cancel.add_argument("--reason", default="", help="Optional cancellation reason")
    cancel.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    resume = subparsers.add_parser("resume", help="Resume a run waiting on approval")
    resume.add_argument("run_id")
    resume.add_argument("--approval-id", required=True, help="Approval id to decide")
    resume.add_argument("--reject", action="store_true", help="Reject instead of approve")
    resume.add_argument("--reason", default="", help="Optional decision reason")
    resume.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    fork = subparsers.add_parser("fork", help="Fork a run from checkpoint provenance")
    fork.add_argument("run_id")
    fork.add_argument("--message", default="", help="Optional replacement message")
    fork.add_argument("--thread-id", default="", help="Optional target thread id")
    fork.add_argument("--checkpoint-ns", default="", help="Optional target checkpoint namespace")
    fork.add_argument("--checkpoint-id", default="", help="Optional source checkpoint id")
    fork.add_argument("--metadata-json", default="{}", help="Optional JSON object metadata")
    fork.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    diagnose = subparsers.add_parser(
        "diagnose",
        help="Fetch run status, stream events, and tool invocations in one report",
    )
    diagnose.add_argument("run_id")
    diagnose.add_argument("--tool-limit", type=int, default=100, help="Maximum tool records")
    diagnose.add_argument("--tool-status", default="", help="Optional tool invocation status")
    diagnose.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    tool_invocations = subparsers.add_parser(
        "tool-invocations",
        help="List run-scoped tool invocation audit records",
    )
    tool_invocations.add_argument("run_id")
    tool_invocations.add_argument("--status", default="", help="Optional tool invocation status")
    tool_invocations.add_argument(
        "--limit", type=int, default=100, help="Maximum records to return"
    )
    tool_invocations.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    promote_eval = subparsers.add_parser(
        "promote-eval",
        help="Promote a persisted run into an agent eval case",
    )
    promote_eval.add_argument("run_id")
    promote_eval.add_argument("--case-id", default="", help="Optional eval case id")
    promote_eval.add_argument("--name", default="", help="Optional eval case name")
    promote_eval.add_argument("--case-file", default="", help="Optional promoted case JSON path")
    promote_eval.add_argument(
        "--run-file",
        default="",
        help="Optional promoted eval run fixture JSON path",
    )
    promote_eval.add_argument(
        "--apply-suite-file",
        default="",
        help="Optional regression suite JSON path to apply the promoted case to",
    )
    promote_eval.add_argument(
        "--apply-dataset-name",
        default="reactor-regression",
        help="Dataset name used while validating the applied promoted case",
    )
    promote_eval.add_argument(
        "--apply-replace",
        action="store_true",
        help="Replace existing case/run ids while applying to a suite",
    )
    promote_eval.add_argument(
        "--apply-dry-run",
        action="store_true",
        help="Validate suite application without writing the suite",
    )
    promote_eval.add_argument(
        "--apply-require-source-run-id",
        action="store_true",
        help="Reject suite application unless the promoted case has sourceRunId",
    )
    promote_eval.add_argument(
        "--apply-require-run-file",
        action="store_true",
        help="Reject suite application unless --run-file is supplied",
    )
    promote_eval.add_argument(
        "--apply-require-context-diagnostics",
        action="store_true",
        help="Reject suite application unless the run fixture has context diagnostics",
    )
    promote_eval.add_argument(
        "--apply-suite-summary",
        action="store_true",
        help="Include source-controlled suite coverage summary after apply.",
    )
    promote_eval.add_argument(
        "--langsmith-dry-run-report-file",
        default="",
        help="Optional LangSmith eval sync dry-run report output path after suite apply",
    )
    promote_eval.add_argument(
        "--feedback-review-status",
        default="",
        help="Review status to preserve in the generated LangSmith dry-run report",
    )
    promote_eval.add_argument(
        "--feedback-review-tag",
        action="append",
        default=[],
        help="Review tag to preserve in the generated LangSmith dry-run report",
    )
    promote_eval.add_argument(
        "--feedback-review-note",
        default="",
        help="Review note to preserve in the generated LangSmith dry-run report",
    )
    promote_eval.add_argument(
        "--expected-answer",
        action="append",
        default=[],
        help="Expected answer substring",
    )
    promote_eval.add_argument(
        "--forbidden-answer",
        action="append",
        default=[],
        help="Forbidden answer substring",
    )
    promote_eval.add_argument(
        "--expected-tool",
        action="append",
        default=[],
        help="Expected tool name",
    )
    promote_eval.add_argument(
        "--forbidden-tool",
        action="append",
        default=[],
        help="Forbidden tool name",
    )
    promote_eval.add_argument(
        "--expected-exposed-tool",
        action="append",
        default=[],
        help="Expected model-visible tool name",
    )
    promote_eval.add_argument(
        "--forbidden-exposed-tool",
        action="append",
        default=[],
        help="Forbidden model-visible tool name",
    )
    promote_eval.add_argument(
        "--max-tool-exposure-count",
        type=int,
        default=None,
        help="Maximum model-visible tool count",
    )
    promote_eval.add_argument(
        "--min-score",
        type=float,
        default=1.0,
        help="Minimum passing eval score",
    )
    promote_eval.add_argument(
        "--disabled",
        action="store_true",
        help="Create the promoted eval case disabled",
    )
    promote_eval.add_argument("--tag", action="append", default=[], help="Eval case tag")
    promote_eval.add_argument(
        "--feedback-source",
        action="append",
        default=[],
        help="Feedback source label to store as feedback-source:* eval provenance",
    )
    promote_eval.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    http_probe: RunsHttpProbe | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    environ: Mapping[str, str] = os.environ,
) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    base_url = (args.base_url or environ.get("REACTOR_API_BASE_URL", "")).strip()
    if not base_url:
        stderr.write("missing --base-url or REACTOR_API_BASE_URL\n")
        return 2

    tenant_id = (args.tenant_id or environ.get("REACTOR_TENANT_ID", "local")).strip()
    user_id = (args.user_id or environ.get("REACTOR_USER_ID", "cli-user")).strip()
    probe = http_probe or HttpRunsProbe(base_url=base_url, timeout_seconds=args.timeout)
    headers = request_headers(args, environ, tenant_id=tenant_id, user_id=user_id)

    validation_error = validate_command_args(args)
    if validation_error:
        stderr.write(f"{validation_error}\n")
        return 2

    result = dispatch_command(args, probe, headers)
    if not result.ok:
        stderr.write(f"reactor-runs request failed ({result.status_code}): {result.error}\n")
        return 1

    output_body: dict[str, object] | list[object] | None = public_command_body(
        args.command,
        result.body,
    )
    if args.command == "promote-eval" and args.case_file:
        write_json_file(Path(args.case_file), result.body)
    if args.command == "promote-eval" and args.run_file:
        run_fixture = promoted_eval_run_fixture(
            args.run_id,
            result.body,
            probe=probe,
            headers=headers,
        )
        if not run_fixture.ok:
            stderr.write(
                "reactor-runs run fixture export failed "
                f"({run_fixture.status_code}): {run_fixture.error}\n"
            )
            return 1
        write_json_file(Path(args.run_file), run_fixture.body)
    if args.command == "promote-eval" and args.apply_suite_file:
        if not args.case_file:
            stderr.write("reactor-runs suite apply requires --case-file\n")
            return 2
        try:
            suite_apply = apply_promoted_eval_case(
                suite_file=Path(args.apply_suite_file),
                case_file=Path(args.case_file),
                run_file=Path(args.run_file) if args.run_file else None,
                dataset_name=args.apply_dataset_name,
                replace=bool(args.apply_replace),
                dry_run=bool(args.apply_dry_run),
                require_source_run_id=bool(args.apply_require_source_run_id),
                require_run_file=bool(args.apply_require_run_file),
                require_context_diagnostics=bool(args.apply_require_context_diagnostics),
            )
        except ValueError as error:
            stderr.write(f"reactor-runs suite apply failed: {error}\n")
            return 1
        suite_apply["persistCommand"] = suite_apply_persist_command(args)
        if args.langsmith_dry_run_report_file:
            langsmith_report_file = Path(args.langsmith_dry_run_report_file)
            apply_suite_file = Path(args.apply_suite_file)
            if args.apply_dry_run:
                langsmith_report = build_langsmith_eval_sync_dry_run_report_for_suite(
                    suite=promoted_eval_suite_snapshot(
                        suite_file=apply_suite_file,
                        case_file=Path(args.case_file),
                        run_file=Path(args.run_file) if args.run_file else None,
                        replace=bool(args.apply_replace),
                    ),
                    suite_file=apply_suite_file,
                    dataset_name=args.apply_dataset_name,
                    report_file=langsmith_report_file,
                    feedback_review_status=args.feedback_review_status,
                    feedback_review_tags=tuple(args.feedback_review_tag or ()),
                    feedback_review_note=args.feedback_review_note,
                )
            else:
                langsmith_report = build_langsmith_eval_sync_dry_run_report(
                    suite_file=apply_suite_file,
                    dataset_name=args.apply_dataset_name,
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
            suite_apply["langsmithDryRun"] = langsmith_dry_run_summary(
                langsmith_report,
                report_file=langsmith_report_file,
                case_file=Path(args.case_file) if args.case_file else None,
                run_file=Path(args.run_file) if args.run_file else None,
                persist_command=str(suite_apply.get("persistCommand") or ""),
                summary_command=suite_apply_summary_command(args),
            )
        output_body = {"promotedCase": result.body, "suiteApply": suite_apply}
        if args.apply_suite_summary:
            apply_suite_file = Path(args.apply_suite_file)
            if args.apply_dry_run:
                output_body["suiteSummary"] = regression_suite_summary_for_suite(
                    suite=promoted_eval_suite_snapshot(
                        suite_file=apply_suite_file,
                        case_file=Path(args.case_file),
                        run_file=Path(args.run_file) if args.run_file else None,
                        replace=bool(args.apply_replace),
                    ),
                    suite_file=apply_suite_file,
                )
            else:
                output_body["suiteSummary"] = regression_suite_summary(apply_suite_file)

    if getattr(args, "output", "json") == "table":
        if args.command == "diagnose":
            stdout.write(format_diagnose_table(result.body))
        elif args.command == "preflight":
            stdout.write(format_preflight_table(result.body))
        elif args.command == "replay":
            stdout.write(format_replay_table(result.body, run_id=args.run_id))
        elif args.command == "tool-invocations":
            stdout.write(format_tool_invocations_table(result.body))
        elif args.command in {"cancel", "resume"}:
            stdout.write(format_run_result_table(result.body))
        elif args.command == "fork":
            stdout.write(format_fork_table(result.body))
        elif args.command == "promote-eval":
            stdout.write(format_eval_case_table(output_body))
        elif args.command == "create":
            stdout.write(format_create_table(result.body))
        else:
            stdout.write(format_status_table(result.body))
    else:
        stdout.write(json.dumps(output_body, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


def validate_command_args(args: argparse.Namespace) -> str:
    if args.command == "promote-eval":
        return validate_promote_eval_args(args)
    return ""


def validate_promote_eval_args(args: argparse.Namespace) -> str:
    expected_answer_error = validate_expected_answer_placeholders(args.expected_answer)
    if expected_answer_error:
        return expected_answer_error
    if not promote_eval_targets_rag_candidate_suite(args):
        return ""
    candidate_case_id_error = validate_rag_candidate_case_id(str(args.case_id or ""))
    if not candidate_case_id_error:
        return ""
    if args.apply_suite_file:
        return candidate_case_id_error.replace("promotion", "suite apply")
    return candidate_case_id_error


def validate_expected_answer_placeholders(values: Sequence[str]) -> str:
    for value in values:
        normalized = value.strip().lower()
        if any(placeholder in normalized for placeholder in CITATION_MARKER_PLACEHOLDERS):
            return "promote-eval expected answer cannot use placeholder citation marker"
    return ""


def validate_rag_candidate_case_id(case_id: str) -> str:
    if not case_id.startswith("case_rag_candidate_"):
        return "RAG ingestion candidate promotion requires --case-id case_rag_candidate_*"
    candidate_slug = rag_candidate_slug_from_case_id(case_id)
    if candidate_slug is None and not case_id.removeprefix("case_rag_candidate_").strip():
        return "RAG ingestion candidate promotion requires --case-id case_rag_candidate_*"
    if candidate_slug is None:
        return "RAG ingestion candidate promotion requires slugged --case-id"
    return ""


def promote_eval_targets_rag_candidate_suite(args: argparse.Namespace) -> bool:
    tags = set(getattr(args, "tag", []) or [])
    if "collection:rag-ingestion-candidate" in tags:
        return True
    if not getattr(args, "apply_suite_file", ""):
        return False
    suite_file = str(getattr(args, "apply_suite_file", "") or "")
    dataset_name = str(getattr(args, "apply_dataset_name", "") or "")
    return (
        dataset_name == "reactor-rag-ingestion-candidate" or "rag-ingestion-candidate" in suite_file
    )


def public_command_body(
    command: str,
    body: dict[str, object] | list[object] | None,
) -> dict[str, object] | list[object] | None:
    if command == "diagnose":
        return diagnose_projection(body)
    if command == "create":
        return create_projection(body)
    if command == "replay":
        return replay_projection(body)
    if command == "status":
        return run_status_projection(body)
    return body


def create_projection(
    body: dict[str, object] | list[object] | None,
) -> dict[str, object] | list[object] | None:
    if not isinstance(body, Mapping):
        return body
    typed_body = cast(Mapping[str, object], body)
    diagnostics = typed_body.get("diagnostics")
    if not isinstance(diagnostics, Mapping):
        return body
    projected = dict(typed_body)
    projected["diagnostics"] = diagnose_projection(cast(dict[str, object], diagnostics))
    return projected


def replay_projection(
    body: dict[str, object] | list[object] | None,
) -> dict[str, object] | list[object] | None:
    if isinstance(body, list):
        projected = project_diagnose_stream_body(body)
        return cast(list[object], projected) if isinstance(projected, list) else []
    if isinstance(body, dict) or body is None:
        return body
    return None


def diagnose_projection(
    body: dict[str, object] | list[object] | None,
) -> dict[str, object]:
    if not isinstance(body, Mapping):
        return {}
    typed_body = cast(Mapping[str, object], body)
    projected: dict[str, object] = {}
    for key in ("runId", "run_id"):
        if key in typed_body:
            projected[key] = typed_body[key]
    section_specs = (
        ("status", project_diagnose_status_body),
        ("streamEvents", project_diagnose_stream_body),
        ("toolInvocations", project_diagnose_tool_body),
    )
    for section_name, projector in section_specs:
        section = typed_body.get(section_name)
        if isinstance(section, Mapping):
            projected[section_name] = diagnose_section_projection(
                cast(Mapping[str, object], section),
                projector,
            )
    next_actions = typed_body.get("nextActions")
    if isinstance(next_actions, Sequence) and not isinstance(next_actions, str):
        projected["nextActions"] = list(cast(Sequence[object], next_actions))
    return projected


def diagnose_section_projection(
    section: Mapping[str, object],
    body_projector: Callable[[object], object],
) -> dict[str, object]:
    projected: dict[str, object] = {}
    for key in ("ok", "statusCode", "error"):
        if key in section:
            projected[key] = section[key]
    if "body" in section:
        projected["body"] = body_projector(section["body"])
    return projected


def project_diagnose_status_body(body: object) -> object:
    if not isinstance(body, Mapping):
        return body
    return run_status_projection(cast(Mapping[str, object], body))


def project_diagnose_stream_body(body: object) -> object:
    if not isinstance(body, Sequence) or isinstance(body, str):
        return body
    projected: list[dict[str, object]] = []
    for item in cast(Sequence[object], body):
        if not isinstance(item, Mapping):
            continue
        typed_item = cast(Mapping[str, object], item)
        projected_item: dict[str, object] = {}
        for key in ("sequence", "event_type", "eventType", "node", "name"):
            if key in typed_item:
                projected_item[key] = typed_item[key]
        projected.append(projected_item)
    return projected


def project_diagnose_tool_body(body: object) -> object:
    if not isinstance(body, Sequence) or isinstance(body, str):
        return body
    projected: list[dict[str, object]] = []
    for item in cast(Sequence[object], body):
        if not isinstance(item, Mapping):
            continue
        typed_item = cast(Mapping[str, object], item)
        projected_item: dict[str, object] = {}
        for key in ("id", "runId", "run_id", "toolId", "tool_id", "status", "success"):
            if key in typed_item:
                projected_item[key] = typed_item[key]
        error = tool_error_projection(typed_item.get("error"))
        if error is not None:
            projected_item["error"] = error
        projected.append(projected_item)
    return projected


def tool_error_projection(error: object) -> dict[str, object] | None:
    if isinstance(error, Mapping):
        typed_error = cast(Mapping[str, object], error)
        message = typed_error.get("message")
        if isinstance(message, str) and message.strip():
            return {"message": message.strip()}
        code = typed_error.get("code")
        if isinstance(code, str) and code.strip():
            return {"code": code.strip()}
        return {}
    if isinstance(error, str) and error.strip():
        return {"message": error.strip()}
    return None


def run_status_projection(
    body: Mapping[str, object] | dict[str, object] | list[object] | None,
) -> dict[str, object]:
    if not isinstance(body, Mapping):
        return {}
    typed_body = cast(Mapping[str, object], body)
    projected: dict[str, object] = {}
    for key in (
        "run_id",
        "runId",
        "status",
        "thread_id",
        "threadId",
        "checkpoint_ns",
        "checkpointNs",
        "last_checkpoint_id",
        "lastCheckpointId",
        "created_at",
        "createdAt",
        "updated_at",
        "updatedAt",
        "metadata",
    ):
        if key in typed_body:
            value = typed_body[key]
            projected[key] = run_metadata_projection(value) if key == "metadata" else value
    return projected


PRIVATE_METADATA_KEYS = {
    "input",
    "input_payload",
    "output",
    "output_payload",
    "payload",
    "raw_input",
    "raw_output",
    "raw_user_input",
    "request",
    "response",
    "tool_input",
    "tool_output",
}


def run_metadata_projection(value: object) -> object:
    if not isinstance(value, Mapping):
        return value
    projected: dict[str, object] = {}
    for key, item in cast(Mapping[object, object], value).items():
        if not isinstance(key, str):
            continue
        if key in PRIVATE_METADATA_KEYS:
            continue
        projected[key] = item
    return projected


def request_headers(
    args: argparse.Namespace,
    environ: Mapping[str, str],
    *,
    tenant_id: str,
    user_id: str,
) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "X-Reactor-Tenant-Id": tenant_id,
        "X-Reactor-User-Id": user_id,
    }
    role = (args.role or environ.get("REACTOR_ROLE", "")).strip()
    if role:
        headers["X-Reactor-Role"] = role
    token = (args.token or environ.get("REACTOR_API_TOKEN", "")).strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def dispatch_command(
    args: argparse.Namespace,
    probe: RunsHttpProbe,
    headers: dict[str, str],
) -> RunCliHttpResult:
    if args.command == "create":
        return create_run(args, probe=probe, headers=headers)
    if args.command == "preflight":
        payload = run_create_payload(args, include_empty_metadata=True)
        return probe.post_json("/v1/runs/preflight", headers=headers, payload=payload)
    if args.command == "status":
        return probe.get_json(f"/v1/runs/{path_segment(args.run_id)}", headers=headers)
    if args.command == "replay":
        query: dict[str, object] = {}
        if args.after_sequence:
            query["after_sequence"] = args.after_sequence
        if args.event_type:
            query["event_type"] = args.event_type
        suffix = f"?{urlencode(query)}" if query else ""
        return probe.get_json(
            f"/v1/runs/{path_segment(args.run_id)}/stream-events{suffix}",
            headers=headers,
        )
    if args.command == "cancel":
        payload: dict[str, object] = {}
        if args.reason:
            payload["reason"] = args.reason
        return probe.post_json(
            f"/v1/runs/{path_segment(args.run_id)}/cancel",
            headers=headers,
            payload=payload,
        )
    if args.command == "resume":
        payload = {
            "approvalId": args.approval_id,
            "approved": not args.reject,
        }
        if args.reason:
            payload["reason"] = args.reason
        return probe.post_json(
            f"/v1/runs/{path_segment(args.run_id)}/resume",
            headers=headers,
            payload=payload,
        )
    if args.command == "fork":
        payload = {"metadata": metadata_from_json(args.metadata_json)}
        if args.message:
            payload["message"] = args.message
        if args.thread_id:
            payload["threadId"] = args.thread_id
        if args.checkpoint_ns:
            payload["checkpointNs"] = args.checkpoint_ns
        if args.checkpoint_id:
            payload["checkpointId"] = args.checkpoint_id
        return probe.post_json(
            f"/v1/runs/{path_segment(args.run_id)}/fork",
            headers=headers,
            payload=payload,
        )
    if args.command == "diagnose":
        return diagnose_run(
            args.run_id,
            probe=probe,
            headers=headers,
            tool_limit=args.tool_limit,
            tool_status=args.tool_status,
        )
    if args.command == "tool-invocations":
        query: dict[str, object] = {"limit": args.limit}
        if args.status:
            query["status"] = args.status
        return probe.get_json(
            f"/v1/runs/{path_segment(args.run_id)}/tool-invocations?{urlencode(query)}",
            headers=headers,
        )
    if args.command == "promote-eval":
        return probe.post_json(
            "/v1/admin/agent-eval/cases/promote",
            headers=headers,
            payload=promote_eval_payload(args),
        )
    raise AssertionError(f"unsupported command: {args.command}")


def create_run(
    args: argparse.Namespace,
    *,
    probe: RunsHttpProbe,
    headers: dict[str, str],
) -> RunCliHttpResult:
    payload = run_create_payload(args, include_empty_metadata=False)
    if not args.preflight_first:
        created = probe.post_json("/v1/runs", headers=headers, payload=payload)
        return created_with_optional_diagnostics(created, args=args, probe=probe, headers=headers)
    preflight = probe.post_json("/v1/runs/preflight", headers=headers, payload=payload)
    if not preflight.ok:
        return preflight
    if not preflight_ready(preflight.body):
        return RunCliHttpResult(
            ok=False,
            status_code=preflight.status_code,
            error=json.dumps(preflight.body, sort_keys=True, separators=(",", ":")),
        )
    created = probe.post_json("/v1/runs", headers=headers, payload=payload)
    if not created.ok:
        return created
    combined = RunCliHttpResult(
        ok=True,
        status_code=created.status_code,
        body={"preflight": preflight.body, "run": created.body},
    )
    return created_with_optional_diagnostics(combined, args=args, probe=probe, headers=headers)


def created_with_optional_diagnostics(
    created: RunCliHttpResult,
    *,
    args: argparse.Namespace,
    probe: RunsHttpProbe,
    headers: dict[str, str],
) -> RunCliHttpResult:
    if not args.diagnose_after_create:
        return created
    run_id = created_run_id(created.body)
    if run_id is None:
        return RunCliHttpResult(ok=False, status_code=0, error="missing_created_run_id")
    diagnostics = diagnose_run(
        run_id,
        probe=probe,
        headers=headers,
        tool_limit=100,
    )
    if not diagnostics.ok:
        return diagnostics
    return RunCliHttpResult(
        ok=True,
        status_code=created.status_code,
        body={"run": created.body, "diagnostics": diagnostics.body},
    )


def created_run_id(body: dict[str, object] | list[object] | None) -> str | None:
    if not isinstance(body, dict):
        return None
    direct = optional_text(body.get("run_id")) or optional_text(body.get("runId"))
    if direct is not None:
        return direct
    run = body.get("run")
    if isinstance(run, dict):
        typed_run = cast(dict[object, object], run)
        return optional_text(typed_run.get("run_id")) or optional_text(typed_run.get("runId"))
    return None


def run_create_payload(
    args: argparse.Namespace,
    *,
    include_empty_metadata: bool,
) -> dict[str, object]:
    payload: dict[str, object] = {"message": args.message}
    metadata = metadata_from_json(args.metadata_json)
    if metadata or include_empty_metadata:
        payload["metadata"] = metadata
    if args.thread_id:
        payload["threadId"] = args.thread_id
    if args.checkpoint_ns:
        payload["checkpointNs"] = args.checkpoint_ns
    return payload


def promote_eval_payload(args: argparse.Namespace) -> dict[str, object]:
    payload: dict[str, object] = {"runId": args.run_id}
    if args.case_id:
        payload["id"] = args.case_id
    if args.name:
        payload["name"] = args.name
    if args.expected_answer:
        payload["expectedAnswerContains"] = list(args.expected_answer)
    if args.forbidden_answer:
        payload["forbiddenAnswerContains"] = list(args.forbidden_answer)
    if args.expected_tool:
        payload["expectedToolNames"] = list(args.expected_tool)
    if args.forbidden_tool:
        payload["forbiddenToolNames"] = list(args.forbidden_tool)
    if args.expected_exposed_tool:
        payload["expectedExposedToolNames"] = list(args.expected_exposed_tool)
    if args.forbidden_exposed_tool:
        payload["forbiddenExposedToolNames"] = list(args.forbidden_exposed_tool)
    if args.max_tool_exposure_count is not None:
        payload["maxToolExposureCount"] = args.max_tool_exposure_count
    if args.min_score != 1.0:
        payload["minScore"] = args.min_score
    if args.disabled:
        payload["enabled"] = False
    tags = list(args.tag)
    tags.extend(expected_citation_tags_from_expected_answers(args.expected_answer, tags=tags))
    if promote_eval_targets_rag_candidate_suite(args):
        tags.append("collection:rag-ingestion-candidate")
        candidate_slug = rag_candidate_slug_from_case_id(str(args.case_id or ""))
        if candidate_slug is not None:
            tags.append(rag_candidate_workflow_tag(candidate_slug))
    tags.extend(
        f"feedback-source:{command_slug(feedback_source)}"
        for feedback_source in args.feedback_source
        if feedback_source.strip()
    )
    if tags:
        payload["tags"] = dedupe_strings(tags)
    return payload


def expected_citation_tags_from_expected_answers(
    expected_answers: Sequence[str],
    *,
    tags: Sequence[str],
) -> list[str]:
    if "documents-ask" not in {tag.strip() for tag in tags}:
        return []
    citation_tags: list[str] = []
    for answer in expected_answers:
        value = answer.strip()
        if not value.startswith("[") or not value.endswith("]"):
            continue
        citation_id = value[1:-1].strip()
        if is_citation_safe_id(citation_id):
            citation_tags.append(f"expected-citation:{citation_id}")
    return citation_tags


def write_json_file(path: Path, payload: dict[str, object] | list[object] | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def preflight_ready(body: dict[str, object] | list[object] | None) -> bool:
    return isinstance(body, dict) and body.get("status") == "ready"


def diagnose_run(
    run_id: str,
    *,
    probe: RunsHttpProbe,
    headers: dict[str, str],
    tool_limit: int,
    tool_status: str = "",
) -> RunCliHttpResult:
    encoded_run_id = path_segment(run_id)
    status_result = probe.get_json(f"/v1/runs/{encoded_run_id}", headers=headers)
    stream_result = probe.get_json(f"/v1/runs/{encoded_run_id}/stream-events", headers=headers)
    tool_query: dict[str, object] = {"limit": tool_limit}
    if tool_status:
        tool_query["status"] = tool_status
    tool_result = probe.get_json(
        f"/v1/runs/{encoded_run_id}/tool-invocations?{urlencode(tool_query)}",
        headers=headers,
    )
    body: dict[str, object] = {
        "runId": run_id,
        "status": diagnostic_section(status_result),
        "streamEvents": diagnostic_section(stream_result),
        "toolInvocations": diagnostic_section(tool_result),
    }
    next_actions = diagnose_next_actions(run_id, status_result.body, stream_result.body)
    next_actions.extend(tool_reconciliation_next_actions(run_id, tool_result.body))
    if next_actions:
        body["nextActions"] = next_actions
    return RunCliHttpResult(
        ok=True,
        status_code=200,
        body=body,
    )


def diagnose_next_actions(
    run_id: str,
    status_body: dict[str, object] | list[object] | None,
    stream_body: dict[str, object] | list[object] | None = None,
) -> list[dict[str, object]]:
    if not isinstance(status_body, dict):
        return []
    status = normalize_run_status_for_diagnostics(str(status_body.get("status") or ""))
    if status == "completed":
        return completed_run_next_actions(run_id, status_body, stream_body)
    if status == "running":
        return running_run_next_actions(run_id, status_body, stream_body)
    if status not in {"failed", "error", "cancelled"}:
        return []
    quoted_run_id = quote(run_id)
    actions: list[dict[str, object]] = terminal_run_replay_next_actions(run_id, stream_body)
    actions.extend(terminal_run_checkpoint_next_actions(run_id, status_body))
    tags = failed_run_eval_tags(status_body)
    case_id = failed_run_eval_case_id(run_id, tags)
    suite_file = "tests/fixtures/agent-eval/regression-suite.json"
    dataset_arg = ""
    report_file = "reports/langsmith-eval-sync-dry-run.json"
    case_file = "promoted-case.json"
    run_file = "promoted-run.json"
    candidate_tag = next((tag for tag in tags if tag.startswith("rag-candidate:")), "")
    if "collection:rag-ingestion-candidate" in tags:
        suite_file = "evals/regression/rag-ingestion-candidate.json"
        dataset_arg = "--apply-dataset-name reactor-rag-ingestion-candidate "
        report_file = f"artifacts/langsmith/rag-ingestion-candidate-{case_id}.json"
        case_file = f"evals/cases/{case_id}.json"
        run_file = f"evals/runs/{command_slug(run_id)}.json"
    required_readiness_reports = ["langsmith_eval_sync"]
    readiness_reports = {"langsmith_eval_sync": report_file}
    if dataset_arg or "documents-ask" in tags:
        required_readiness_reports = ["hardening_suite", "langsmith_eval_sync"]
        readiness_reports = {
            "hardening_suite": HARDENING_SUITE_REPORT_FILE,
            "langsmith_eval_sync": report_file,
        }
    readiness_report_arg = readiness_report_args_for_reports(
        required_reports=required_readiness_reports,
        report_files=readiness_reports,
    )
    tag_args = " ".join(f"--tag {quote(tag)}" for tag in tags)
    actions.append(
        {
            "id": "promote-eval",
            "label": "Promote failed run into a source-controlled eval case",
            "evalCaseId": case_id,
            "sourceRunId": run_id,
            "caseFile": case_file,
            "runFile": run_file,
            "suiteFile": suite_file,
            **({"datasetName": "reactor-rag-ingestion-candidate"} if dataset_arg else {}),
            **({"candidateTag": candidate_tag} if candidate_tag else {}),
            "reportFile": report_file,
            "readinessReportArg": readiness_report_arg,
            "requiredReadinessReports": required_readiness_reports,
            "readinessReports": readiness_reports,
            "evalTags": tags,
            "command": (
                f"reactor-runs promote-eval {quoted_run_id} --case-id {quote(case_id)} "
                f"--case-file {quote(case_file)} --run-file {quote(run_file)} "
                f"{tag_args} "
                f"--apply-suite-file {suite_file} "
                f"{dataset_arg}"
                "--apply-dry-run --apply-require-source-run-id "
                "--apply-require-run-file --apply-require-context-diagnostics "
                "--apply-suite-summary "
                f"--langsmith-dry-run-report-file {report_file} "
                "--output table"
            ),
        }
    )
    return actions


def normalize_run_status_for_diagnostics(status: str) -> str:
    return {
        "started": "running",
        "succeeded": "completed",
    }.get(status, status)


def tool_reconciliation_next_actions(
    run_id: str,
    tool_body: dict[str, object] | list[object] | None,
) -> list[dict[str, object]]:
    if not has_tool_invocation_status(tool_body, "requires_reconciliation"):
        return []
    quoted_run_id = quote(run_id)
    return [
        {
            "id": "inspect-reconciliation-tools",
            "label": "Inspect tool invocations that require operator reconciliation",
            "sourceRunId": run_id,
            "toolStatus": "requires_reconciliation",
            "command": (
                f"reactor-runs tool-invocations {quoted_run_id} "
                "--status requires_reconciliation --output table"
            ),
        }
    ]


def has_tool_invocation_status(
    tool_body: dict[str, object] | list[object] | None,
    status: str,
) -> bool:
    if not isinstance(tool_body, list):
        return False
    for item in tool_body:
        if not isinstance(item, dict):
            continue
        if str(cast(dict[object, object], item).get("status") or "") == status:
            return True
    return False


def failed_run_eval_case_id(run_id: str, tags: Sequence[str]) -> str:
    for tag in tags:
        candidate = tag.removeprefix("rag-candidate:")
        if candidate != tag and is_command_slug(candidate):
            return rag_candidate_case_id(candidate)
    return f"case_{safe_command_id(run_id)}"


def terminal_run_replay_next_actions(
    run_id: str,
    stream_body: dict[str, object] | list[object] | None = None,
) -> list[dict[str, object]]:
    if not has_persisted_stream_events(stream_body):
        return []
    quoted_run_id = quote(run_id)
    return [
        {
            "id": "replay-stream",
            "label": "Replay this terminal run's persisted LangGraph stream events",
            "sourceRunId": run_id,
            "command": f"reactor-runs replay {quoted_run_id} --output table",
        }
    ]


def terminal_run_checkpoint_next_actions(
    run_id: str,
    status_body: Mapping[str, object],
) -> list[dict[str, object]]:
    thread_id = optional_text(status_body.get("thread_id")) or optional_text(
        status_body.get("threadId")
    )
    checkpoint_ns = optional_text(status_body.get("checkpoint_ns")) or optional_text(
        status_body.get("checkpointNs")
    )
    checkpoint_id = optional_text(status_body.get("last_checkpoint_id")) or optional_text(
        status_body.get("lastCheckpointId")
    )
    if checkpoint_ns is None or checkpoint_id is None:
        return []
    quoted_run_id = quote(run_id)
    quoted_checkpoint_ns = quote(checkpoint_ns)
    quoted_checkpoint_id = quote(checkpoint_id)
    return [
        {
            "id": "fork-checkpoint",
            "label": "Fork this terminal run from its latest LangGraph checkpoint",
            "sourceRunId": run_id,
            **({"threadId": thread_id} if thread_id is not None else {}),
            "checkpointNs": checkpoint_ns,
            "checkpointId": checkpoint_id,
            "command": (
                f"reactor-runs fork {quoted_run_id} --checkpoint-ns {quoted_checkpoint_ns} "
                f"--checkpoint-id {quoted_checkpoint_id} --output table"
            ),
        },
        {
            "id": "inspect-state-history",
            "label": "Inspect this terminal run's LangGraph checkpoint state history",
            "sourceRunId": run_id,
            **({"threadId": thread_id} if thread_id is not None else {}),
            "checkpointNs": checkpoint_ns,
            "checkpointId": checkpoint_id,
            "command": f"reactor-admin state-history {quoted_run_id} --output table",
        },
    ]


def failed_run_eval_tags(status_body: Mapping[str, object]) -> list[str]:
    tags = ["promoted-from-failed-run", "run-diagnostics"]
    metadata = status_body.get("metadata")
    run_tags = string_sequence_from_mapping(status_body, "tags")
    if isinstance(metadata, Mapping):
        typed_metadata = cast(Mapping[str, object], metadata)
        run_tags.extend(string_sequence_from_mapping(typed_metadata, "tags"))
        run_tags.extend(string_sequence_from_mapping(typed_metadata, "workflowTags"))
        run_tags.extend(feedback_review_queue_tags(typed_metadata.get("feedbackReviewQueue")))
    run_tags.extend(feedback_review_queue_tags(status_body.get("feedbackReviewQueue")))
    if "collection:rag-ingestion-candidate" in run_tags:
        tags.append("collection:rag-ingestion-candidate")
    tags.extend(
        tag
        for tag in run_tags
        if tag.startswith("rag-candidate:")
        and is_command_slug(tag.removeprefix("rag-candidate:").strip())
    )
    tags.extend(
        tag
        for tag in run_tags
        if tag.startswith("expected-citation:")
        and is_citation_safe_id(tag.removeprefix("expected-citation:").strip())
    )
    tags.extend(tag for tag in run_tags if tag in {"memory", "rag", "grounding", "documents-ask"})
    return dedupe_strings(tags)


def feedback_review_queue_tags(value: object) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    queue = cast(Mapping[object, object], value)
    tags: list[str] = []
    workflow_tag_counts = queue.get("workflowTagCounts")
    workflow_counts: Mapping[object, object] = {}
    if isinstance(workflow_tag_counts, Mapping):
        workflow_counts = cast(Mapping[object, object], workflow_tag_counts)
    case_ids = string_list_value(queue.get("caseIds"))
    candidate_tag = candidate_workflow_tag_from_case_ids(case_ids)
    if candidate_tag:
        if positive_workflow_count(workflow_counts, "collection:rag-ingestion-candidate"):
            tags.append("collection:rag-ingestion-candidate")
        tags.append(candidate_tag)
    for tag in ("memory", "rag", "grounding", "documents-ask"):
        if positive_workflow_count(workflow_counts, tag):
            tags.append(tag)
    return tags


def positive_workflow_count(workflow_counts: Mapping[object, object], tag: str) -> bool:
    count = workflow_counts.get(tag)
    return isinstance(count, int) and not isinstance(count, bool) and count > 0


def dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def running_run_next_actions(
    run_id: str,
    status_body: Mapping[str, object],
    stream_body: dict[str, object] | list[object] | None = None,
) -> list[dict[str, object]]:
    quoted_run_id = quote(run_id)
    cancel_command = (
        f"reactor-runs cancel {quoted_run_id} "
        f"--reason {quote('operator requested cancellation')} --output table"
    )
    thread_id = optional_text(status_body.get("thread_id")) or optional_text(
        status_body.get("threadId")
    )
    thread_metadata = {"threadId": thread_id} if thread_id is not None else {}
    actions = running_run_replay_next_actions(run_id, stream_body, thread_id=thread_id)
    approval_id = pending_approval_id(stream_body)
    if approval_id is None:
        actions.append(
            {
                "id": "cancel-run",
                "label": "Cancel this running Reactor run",
                "sourceRunId": run_id,
                **thread_metadata,
                "command": cancel_command,
            }
        )
        return actions
    quoted_approval_id = quote(approval_id)
    actions.extend(
        [
            {
                "id": "resume-approval",
                "label": "Resume this interrupted LangGraph run with the pending approval",
                "sourceRunId": run_id,
                **thread_metadata,
                "approvalId": approval_id,
                "command": (
                    f"reactor-runs resume {quoted_run_id} --approval-id {quoted_approval_id} "
                    "--output table"
                ),
            },
            {
                "id": "reject-approval",
                "label": "Reject this pending LangGraph approval and resume the run",
                "sourceRunId": run_id,
                **thread_metadata,
                "approvalId": approval_id,
                "command": (
                    f"reactor-runs resume {quoted_run_id} --approval-id {quoted_approval_id} "
                    "--reject --reason 'operator rejected approval' --output table"
                ),
            },
            {
                "id": "cancel-run",
                "label": "Cancel this running Reactor run",
                "sourceRunId": run_id,
                **thread_metadata,
                "command": cancel_command,
            },
        ]
    )
    return actions


def running_run_replay_next_actions(
    run_id: str,
    stream_body: dict[str, object] | list[object] | None = None,
    *,
    thread_id: str | None = None,
) -> list[dict[str, object]]:
    if not has_persisted_stream_events(stream_body):
        return []
    quoted_run_id = quote(run_id)
    return [
        {
            "id": "replay-stream",
            "label": "Replay this running run's persisted LangGraph stream events",
            "sourceRunId": run_id,
            **({"threadId": thread_id} if thread_id is not None else {}),
            "command": f"reactor-runs replay {quoted_run_id} --output table",
        }
    ]


def pending_approval_id(stream_body: dict[str, object] | list[object] | None) -> str | None:
    if not isinstance(stream_body, list):
        return None
    for item in reversed(stream_body):
        if not isinstance(item, dict):
            continue
        typed_item = cast(dict[object, object], item)
        event_type = typed_item.get("event_type") or typed_item.get("eventType")
        if event_type != "run.stream.approval":
            continue
        payload = typed_item.get("payload")
        if not isinstance(payload, dict):
            continue
        typed_payload = cast(dict[object, object], payload)
        approval_status = typed_payload.get("approval_status") or typed_payload.get(
            "approvalStatus"
        )
        if approval_status != "pending":
            continue
        approval_id = typed_payload.get("approval_id") or typed_payload.get("approvalId")
        if isinstance(approval_id, str) and approval_id.strip():
            return approval_id.strip()
    return None


def completed_run_next_actions(
    run_id: str,
    status_body: dict[str, object],
    stream_body: dict[str, object] | list[object] | None = None,
) -> list[dict[str, object]]:
    thread_id = optional_text(status_body.get("thread_id")) or optional_text(
        status_body.get("threadId")
    )
    checkpoint_ns = optional_text(status_body.get("checkpoint_ns")) or optional_text(
        status_body.get("checkpointNs")
    )
    checkpoint_id = optional_text(status_body.get("last_checkpoint_id")) or optional_text(
        status_body.get("lastCheckpointId")
    )
    quoted_run_id = quote(run_id)
    actions: list[dict[str, object]] = []
    if has_persisted_stream_events(stream_body):
        actions.append(
            {
                "id": "replay-stream",
                "label": "Replay this run's persisted LangGraph stream events",
                "sourceRunId": run_id,
                **({"threadId": thread_id} if thread_id is not None else {}),
                **({"checkpointNs": checkpoint_ns} if checkpoint_ns is not None else {}),
                **({"checkpointId": checkpoint_id} if checkpoint_id is not None else {}),
                "command": f"reactor-runs replay {quoted_run_id} --output table",
            }
        )
    if checkpoint_ns is None or checkpoint_id is None:
        return actions
    quoted_checkpoint_ns = quote(checkpoint_ns)
    quoted_checkpoint_id = quote(checkpoint_id)
    actions.append(
        {
            "id": "fork-checkpoint",
            "label": "Fork this completed run from its latest LangGraph checkpoint",
            "sourceRunId": run_id,
            **({"threadId": thread_id} if thread_id is not None else {}),
            "checkpointNs": checkpoint_ns,
            "checkpointId": checkpoint_id,
            "command": (
                f"reactor-runs fork {quoted_run_id} --checkpoint-ns {quoted_checkpoint_ns} "
                f"--checkpoint-id {quoted_checkpoint_id} --output table"
            ),
        }
    )
    actions.append(
        {
            "id": "inspect-state-history",
            "label": "Inspect this run's LangGraph checkpoint state history",
            "sourceRunId": run_id,
            **({"threadId": thread_id} if thread_id is not None else {}),
            "checkpointNs": checkpoint_ns,
            "checkpointId": checkpoint_id,
            "command": f"reactor-admin state-history {quoted_run_id} --output table",
        }
    )
    return actions


def has_persisted_stream_events(body: dict[str, object] | list[object] | None) -> bool:
    if not isinstance(body, list):
        return False
    for item in body:
        if not isinstance(item, dict):
            continue
        typed_item = cast(dict[object, object], item)
        event_type = typed_item.get("event_type") or typed_item.get("eventType")
        if isinstance(event_type, str) and event_type.startswith("run.stream."):
            return True
    return False


def safe_command_id(value: str) -> str:
    return command_slug(value, fallback="run")


def diagnostic_section(result: RunCliHttpResult) -> dict[str, object]:
    section: dict[str, object] = {
        "ok": result.ok,
        "statusCode": result.status_code,
    }
    if result.ok:
        section["body"] = result.body
    else:
        section["error"] = result.error
    return section


def promoted_eval_run_fixture(
    run_id: str,
    case_body: dict[str, object] | list[object] | None,
    *,
    probe: RunsHttpProbe,
    headers: dict[str, str],
) -> RunCliHttpResult:
    if not isinstance(case_body, dict):
        return RunCliHttpResult(ok=False, status_code=0, error="invalid_eval_case_response")
    case_id = optional_text(case_body.get("id"))
    if case_id is None:
        return RunCliHttpResult(ok=False, status_code=0, error="missing_eval_case_id")

    encoded_run_id = path_segment(run_id)
    status_result = probe.get_json(f"/v1/runs/{encoded_run_id}", headers=headers)
    if not status_result.ok:
        return status_result
    if not isinstance(status_result.body, dict):
        return RunCliHttpResult(ok=False, status_code=0, error="invalid_run_response")

    tool_result = probe.get_json(
        f"/v1/runs/{encoded_run_id}/tool-invocations?{urlencode({'limit': 100})}",
        headers=headers,
    )
    if not tool_result.ok:
        return tool_result
    if not isinstance(tool_result.body, list):
        return RunCliHttpResult(ok=False, status_code=0, error="invalid_tool_invocations_response")

    run_body = status_result.body
    metadata = run_metadata(run_body)
    tool_calls = tool_call_fixtures(tool_result.body)
    exposed_tools: list[str] = string_sequence_from_mapping(
        metadata,
        "exposedToolNames",
        "exposed_tool_names",
    ) or sorted(tool_call_names(tool_calls))
    fixture: dict[str, object] = {
        "runId": run_id,
        "evalCaseId": case_id,
        "userInput": first_text(
            run_body.get("input_text"),
            run_body.get("inputText"),
            run_body.get("message"),
            case_body.get("userInput"),
        )
        or "",
        "agentType": first_text(
            metadata.get("agentType"),
            metadata.get("agent_type"),
            case_body.get("agentType"),
        )
        or "unknown",
        "model": first_text(metadata.get("model"), case_body.get("model")) or "unknown",
        "finalAnswer": first_text(
            run_body.get("response_text"),
            run_body.get("responseText"),
            run_body.get("response"),
            run_body.get("content"),
        )
        or "",
        "toolCalls": tool_calls,
        "toolExposure": {"count": len(exposed_tools), "names": exposed_tools},
        "retrievedChunks": retrieved_chunk_fixtures(metadata.get("retrievedChunks")),
        "errors": string_sequence_from_mapping(
            metadata,
            "errors",
            "failureReasons",
            "failure_reasons",
            "error",
        ),
    }
    diagnostics = promoted_eval_context_manifest_diagnostics(metadata)
    if diagnostics:
        fixture["contextManifestDiagnostics"] = diagnostics
    return RunCliHttpResult(ok=True, status_code=200, body=fixture)


def promoted_eval_context_manifest_diagnostics(metadata: Mapping[str, object]) -> dict[str, object]:
    explicit_diagnostics = mapping_table_value(
        metadata,
        "contextManifestDiagnostics",
        "context_manifest_diagnostics",
    )
    if explicit_diagnostics:
        return explicit_diagnostics
    context_manifest = mapping_table_value(metadata, "contextManifest", "context_manifest")
    if not context_manifest:
        return {}
    return context_manifest_diagnostics(context_manifest)


def run_metadata(run_body: Mapping[str, object]) -> Mapping[str, object]:
    metadata = run_body.get("metadata")
    if isinstance(metadata, Mapping):
        return cast(Mapping[str, object], metadata)
    return {}


def tool_call_fixtures(items: Sequence[object]) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, Mapping):
            continue
        typed_item = cast(Mapping[str, object], item)
        tool_name = first_text(
            typed_item.get("toolId"),
            typed_item.get("tool_id"),
            typed_item.get("toolName"),
            typed_item.get("name"),
        )
        if tool_name is None:
            continue
        calls.append(
            {
                "step": index,
                "toolName": tool_name,
                "arguments": {},
                "success": tool_invocation_success(typed_item),
            }
        )
    return calls


def tool_call_names(tool_calls: Sequence[Mapping[str, object]]) -> set[str]:
    names: set[str] = set()
    for call in tool_calls:
        tool_name = optional_text(call.get("toolName"))
        if tool_name is not None:
            names.add(tool_name)
    return names


def tool_invocation_success(item: Mapping[str, object]) -> bool:
    success = item.get("success")
    if isinstance(success, bool):
        return success
    return item.get("status") != "failed"


def retrieved_chunk_fixtures(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list | tuple):
        return []
    chunks: list[dict[str, object]] = []
    for item in cast(Sequence[object], value):
        if isinstance(item, Mapping):
            chunks.append(dict(cast(Mapping[str, object], item)))
    return chunks


def first_text(*values: object) -> str | None:
    for value in values:
        text = optional_text(value)
        if text is not None:
            return text
    return None


def optional_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def string_sequence_from_mapping(mapping: Mapping[str, object], *keys: str) -> list[str]:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return [value]
        if isinstance(value, list | tuple):
            items = cast(Sequence[object], value)
            return [item for item in items if isinstance(item, str) and item.strip()]
    return []


def format_status_table(body: dict[str, object] | list[object] | None) -> str:
    if not isinstance(body, dict):
        return "FIELD  VALUE\n"
    run_id = table_value(body, "run_id", "runId")
    thread_id = table_value(body, "thread_id", "threadId")
    checkpoint_ns = table_value(body, "checkpoint_ns", "checkpointNs")
    last_checkpoint_id = table_value(body, "last_checkpoint_id", "lastCheckpointId")
    metadata = mapping_table_value(body, "metadata")
    middleware_policy = mapping_table_value(metadata, "langchainMiddlewarePolicy")
    middleware_policy_body = mapping_table_value(middleware_policy, "policy")
    middleware_chain = mapping_table_value(metadata, "langchainMiddlewareChain")
    structured_output = mapping_table_value(metadata, "structuredOutput", "structured_output")
    ignored_schema = mapping_table_value(structured_output, "ignoredSchema", "ignored_schema")
    token_usage = token_usage_table_mapping(metadata)
    checkpoint_provenance = mapping_table_value(
        metadata,
        "checkpointProvenance",
        "checkpoint_provenance",
    )
    graph_store_runtime = mapping_table_value(
        checkpoint_provenance,
        "graphStoreRuntime",
        "graph_store_runtime",
    )
    provider_fallback = mapping_table_value(metadata, "providerFallback", "provider_fallback")
    tool_budget = mapping_table_value(
        metadata,
        "resolvedToolProfileBudget",
        "resolved_tool_profile_budget",
    )
    rows = [
        ("run_id", run_id),
        ("status", table_value(body, "status")),
        ("thread_id", thread_id),
        ("checkpoint_ns", checkpoint_ns),
        ("last_checkpoint_id", last_checkpoint_id),
        ("checkpoint_store", table_value(checkpoint_provenance, "store")),
        (
            "graph_durable_store",
            table_value(graph_store_runtime, "durableStore", "durable_store"),
        ),
        ("graph_local_store", table_value(graph_store_runtime, "localStore", "local_store")),
        ("created_at", table_value(body, "created_at", "createdAt")),
        ("updated_at", table_value(body, "updated_at", "updatedAt")),
        ("model_provider", table_value(metadata, "model_provider", "modelProvider")),
        ("selected_model", table_value(metadata, "selected_model", "selectedModel")),
        (
            "model_fallback_used",
            bool_table_value(table_value(metadata, "model_fallback_used", "modelFallbackUsed")),
        ),
        (
            "provider_fallback_from",
            provider_model_summary(
                provider_fallback,
                "from_provider",
                "fromProvider",
                "from_model",
                "fromModel",
            ),
        ),
        (
            "provider_fallback_to",
            provider_model_summary(
                provider_fallback,
                "to_provider",
                "toProvider",
                "to_model",
                "toModel",
            ),
        ),
        ("provider_fallback_reason", table_value(provider_fallback, "reason")),
        (
            "provider_fallback_latency_ms",
            table_value(provider_fallback, "latency_ms", "latencyMs"),
        ),
        ("provider_fallback_cost_usd", table_value(provider_fallback, "cost_usd", "costUsd")),
        ("tool_profile_budget_source", table_value(tool_budget, "source")),
        ("tool_profile_budget_max", table_value(tool_budget, "maxTools", "max_tools")),
        ("tool_profile_configured_tools", table_value(tool_budget, "configuredToolCount")),
        ("tool_profile_active_tools", table_value(tool_budget, "activeToolCount")),
        (
            "tool_profile_active_tool_names",
            comma_separated_table_value(tool_budget, "activeTools", "active_tools"),
        ),
        ("tool_profile_dropped_tools", table_value(tool_budget, "droppedToolCount")),
        (
            "tool_profile_drop_reasons",
            dropped_tool_reason_summary(table_value(tool_budget, "dropped_tools", "droppedTools"))
            or None,
        ),
        (
            "tool_profile_dropped_sample",
            dropped_tool_sample_summary(table_value(tool_budget, "dropped_tools", "droppedTools"))
            or None,
        ),
        ("langchain_middleware_status", table_value(middleware_policy, "status")),
        ("langchain_middleware_source", table_value(middleware_policy, "source")),
        ("langchain_model_limit", table_value(middleware_policy_body, "modelCallRunLimit")),
        ("langchain_tool_limit", table_value(middleware_policy_body, "toolCallRunLimit")),
        ("langchain_model_retries", table_value(middleware_policy_body, "modelRetryMaxRetries")),
        ("langchain_tool_retries", table_value(middleware_policy_body, "toolRetryMaxRetries")),
        (
            "langchain_middleware_chain",
            comma_separated_table_value(middleware_chain, "middleware"),
        ),
        ("langchain_middleware_pii", table_value(middleware_chain, "piiRuleCount")),
        ("langchain_middleware_hitl", table_value(middleware_chain, "hitlToolCount")),
        (
            "langchain_middleware_models",
            table_value(middleware_chain, "fallbackModelCount"),
        ),
        ("structured_output_strategy", table_value(structured_output, "strategy")),
        ("structured_output_status", table_value(structured_output, "status")),
        (
            "structured_output_schema_source",
            table_value(structured_output, "schemaSource", "schema_source"),
        ),
        (
            "structured_output_citation_policy",
            table_value(structured_output, "citationPolicy", "citation_policy"),
        ),
        (
            "structured_output_citation_count",
            table_value(structured_output, "citationCount", "citation_count"),
        ),
        (
            "structured_output_allowed_citations",
            sequence_count_table_value(
                table_value(structured_output, "allowedCitationIds", "allowed_citation_ids")
            ),
        ),
        ("structured_output_ignored_reason", table_value(ignored_schema, "reason")),
        ("input_tokens", token_usage_value(token_usage, "input")),
        ("output_tokens", token_usage_value(token_usage, "output")),
        ("total_tokens", token_usage_value(token_usage, "total")),
        ("cached_tokens", token_usage_value(token_usage, "cached")),
        ("reasoning_tokens", token_usage_value(token_usage, "reasoning")),
        ("response_text", table_value(body, "response_text", "responseText")),
    ]
    has_checkpoint_context = any(
        isinstance(value, str) and value.strip()
        for value in (thread_id, checkpoint_ns, last_checkpoint_id)
    )
    next_action_rows = run_result_next_action_rows(body.get("nextActions"))
    if next_action_rows:
        rows.extend(next_action_rows)
    elif isinstance(run_id, str) and run_id.strip() and has_checkpoint_context:
        quoted_run_id = quote(run_id)
        rows.extend(
            [
                ("diagnoseAction", f"reactor-runs diagnose {quoted_run_id} --output table"),
                (
                    "stateHistoryAction",
                    f"reactor-admin state-history {quoted_run_id} --output table",
                ),
                ("replayAction", f"reactor-runs replay {quoted_run_id} --output table"),
            ]
        )
    rows = [(field, value) for field, value in rows if value is not None]
    width = max([len("FIELD"), *(len(field) for field, _ in rows)])
    lines = [f"{'FIELD':<{width}}  VALUE"]
    lines.extend(f"{field:<{width}}  {value}" for field, value in rows)
    return "\n".join(lines) + "\n"


def table_value(body: dict[str, object], *keys: str) -> object | None:
    for key in keys:
        value = body.get(key)
        if value is not None:
            return value
    return None


def bool_table_value(value: object) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    return None


def sequence_count_table_value(value: object) -> int | None:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return None
    return len(cast(Sequence[object], value))


def mapping_table_value(body: Mapping[str, object], *keys: str) -> dict[str, object]:
    value = table_value(dict(body), *keys)
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return {str(key): item for key, item in mapping.items()}
    return {}


def token_usage_table_mapping(body: Mapping[str, object]) -> dict[str, object]:
    return mapping_table_value(body, "tokenUsage", "token_usage", "usageMetadata", "usage_metadata")


def token_usage_value(token_usage: Mapping[str, object], field: str) -> object | None:
    usage = dict(token_usage)
    if field == "input":
        return table_value(usage, "inputTokens", "input_tokens")
    if field == "output":
        return table_value(usage, "outputTokens", "output_tokens")
    if field == "total":
        return table_value(usage, "totalTokens", "total_tokens")
    if field == "cached":
        return table_value(usage, "cachedTokens", "cached_tokens") or table_value(
            mapping_table_value(usage, "inputTokenDetails", "input_token_details"),
            "cacheRead",
            "cache_read",
        )
    if field == "reasoning":
        return table_value(usage, "reasoningTokens", "reasoning_tokens") or table_value(
            mapping_table_value(usage, "outputTokenDetails", "output_token_details"),
            "reasoningTokens",
            "reasoning_tokens",
            "reasoning",
        )
    return None


def provider_model_summary(
    body: Mapping[str, object],
    provider_key: str,
    provider_alias: str,
    model_key: str,
    model_alias: str,
) -> str | None:
    provider = table_value(dict(body), provider_key, provider_alias)
    model = table_value(dict(body), model_key, model_alias)
    if isinstance(provider, str) and provider.strip() and isinstance(model, str) and model.strip():
        return f"{provider.strip()}/{model.strip()}"
    return None


def comma_separated_table_value(body: Mapping[str, object], *keys: str) -> str | None:
    value = table_value(dict(body), *keys)
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, list | tuple):
        sequence = cast(Sequence[object], value)
        items = [item for item in sequence if isinstance(item, str) and item.strip()]
        if items:
            return ", ".join(items)
    return None


def mapping_count_summary(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    mapping = cast(Mapping[object, object], value)
    parts = [
        f"{key}={item}"
        for key, item in sorted(mapping.items())
        if isinstance(key, str) and isinstance(item, int) and not isinstance(item, bool)
    ]
    return ",".join(parts) or None


def format_create_table(body: dict[str, object] | list[object] | None) -> str:
    if not isinstance(body, dict):
        return "FIELD  VALUE\n"
    diagnostics = body.get("diagnostics")
    run_with_diagnostics = body.get("run")
    if isinstance(diagnostics, dict) and isinstance(run_with_diagnostics, dict):
        return format_create_diagnostics_table(
            run=cast(dict[object, object], run_with_diagnostics),
            diagnostics=cast(dict[object, object], diagnostics),
        )
    preflight = body.get("preflight")
    run = body.get("run")
    if isinstance(preflight, dict) and isinstance(run, dict):
        return format_preflight_create_table(
            preflight=cast(dict[str, object], preflight),
            run=cast(dict[str, object], run),
        )
    return format_run_result_table(body)


def format_create_diagnostics_table(
    *,
    run: dict[object, object],
    diagnostics: dict[object, object],
) -> str:
    diagnostic_status = diagnose_section_body(diagnostics, "status")
    stream_events = diagnose_section_body(diagnostics, "streamEvents")
    tool_invocations = diagnose_section_body(diagnostics, "toolInvocations")
    tools = cast(list[object], tool_invocations) if isinstance(tool_invocations, list) else []
    failed_count, _ = failed_tool_summary(tools)
    rows: list[tuple[str, object]] = [
        ("run.run_id", run.get("run_id") or run.get("runId")),
        ("run.status", run.get("status")),
        (
            "diagnostics.status",
            diagnostic_status.get("status") if isinstance(diagnostic_status, dict) else None,
        ),
        (
            "diagnostics.events",
            len(cast(list[object], stream_events)) if isinstance(stream_events, list) else 0,
        ),
        ("diagnostics.tools", len(tools)),
        ("diagnostics.failed", failed_count),
        ("diagnostics.nextAction", diagnose_next_action_summary(diagnostics.get("nextActions"))),
        (
            "diagnostics.nextActionIds",
            next_action_field_summary(diagnostics.get("nextActions"), "id"),
        ),
        (
            "diagnostics.sourceRunIds",
            next_action_field_summary(diagnostics.get("nextActions"), "sourceRunId"),
        ),
        (
            "diagnostics.approvalIds",
            next_action_field_summary(diagnostics.get("nextActions"), "approvalId"),
        ),
    ]
    rows.extend(run_result_next_action_rows(run.get("nextActions")))
    visible_rows = [(field, value) for field, value in rows if value is not None and value != ""]
    width = max([len("FIELD"), *(len(field) for field, _ in visible_rows)])
    lines = [f"{'FIELD':<{width}}  VALUE"]
    lines.extend(f"{field:<{width}}  {value}" for field, value in visible_rows)
    return "\n".join(lines) + "\n"


def next_action_field_summary(value: object, field_name: str) -> str | None:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return None
    items: list[str] = []
    seen: set[str] = set()
    for action in cast(Sequence[object], value):
        if not isinstance(action, Mapping):
            continue
        field_value = cast(Mapping[object, object], action).get(field_name)
        if not isinstance(field_value, str) or not field_value.strip():
            continue
        normalized = field_value.strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return ",".join(items) if items else None


def diagnose_section_body(diagnostics: dict[object, object], section_name: str) -> object:
    section = diagnostics.get(section_name)
    if not isinstance(section, dict):
        return None
    return cast(dict[object, object], section).get("body")


def format_preflight_create_table(
    *,
    preflight: dict[str, object],
    run: dict[str, object],
) -> str:
    rows = [
        ("preflight.status", preflight.get("status")),
        ("preflight.runtime", preflight.get("runtime")),
        ("preflight.threadId", preflight.get("threadId")),
        ("preflight.model", preflight_model_summary(preflight.get("model"))),
        ("run.run_id", run.get("run_id")),
        ("run.status", run.get("status")),
    ]
    rows.extend(run_result_next_action_rows(run.get("nextActions")))
    present_rows = [(field, value) for field, value in rows if value is not None and value != ""]
    width = max([len("FIELD"), *(len(field) for field, _ in present_rows)])
    lines = [f"{'FIELD':<{width}}  VALUE"]
    lines.extend(f"{field:<{width}}  {value}" for field, value in present_rows)
    return "\n".join(lines) + "\n"


def format_run_result_table(body: dict[str, object] | list[object] | None) -> str:
    if not isinstance(body, dict):
        return "FIELD  VALUE\n"
    run_id = optional_text(body.get("run_id")) or optional_text(body.get("runId"))
    approval_id = table_value(body, "approval_id", "approvalId")
    rows = [
        ("run_id", run_id),
        ("status", table_value(body, "status")),
        ("approval_id", approval_id),
        ("approved", bool_table_value(table_value(body, "approved"))),
        ("response", table_value(body, "response")),
        ("response_text", table_value(body, "response_text", "responseText")),
    ]
    next_action_rows = run_result_next_action_rows(body.get("nextActions"))
    if next_action_rows:
        rows.extend(next_action_rows)
    elif run_id is not None:
        quoted_run_id = quote(run_id)
        rows.append(("diagnoseAction", f"reactor-runs diagnose {quoted_run_id} --output table"))
        rows.append(
            (
                "stateHistoryAction",
                f"reactor-admin state-history {quoted_run_id} --output table",
            )
        )
        rows.append(("replayAction", f"reactor-runs replay {quoted_run_id} --output table"))
    rows = [(field, value) for field, value in rows if value is not None]
    width = max([len("FIELD"), *(len(field) for field, _ in rows)])
    lines = [f"{'FIELD':<{width}}  VALUE"]
    lines.extend(f"{field:<{width}}  {value}" for field, value in rows)
    return "\n".join(lines) + "\n"


def run_result_next_action_rows(value: object) -> list[tuple[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[tuple[str, str]] = []
    field_by_action_id = {
        "diagnose-run": "nextAction",
        "inspect-state-history": "stateHistoryAction",
        "replay-stream": "replayAction",
        "fork-checkpoint": "forkAction",
        "cancel-run": "cancelAction",
    }
    for action in cast(list[object], value):
        if not isinstance(action, dict):
            continue
        typed_action = cast(dict[object, object], action)
        action_id = typed_action.get("id")
        command = typed_action.get("command")
        if not isinstance(action_id, str) or not isinstance(command, str):
            continue
        normalized_action_id = action_id.strip()
        field = field_by_action_id.get(normalized_action_id)
        if field is None and normalized_action_id:
            field = f"nextAction.{safe_next_action_id(normalized_action_id)}"
        if field is not None and command.strip():
            rows.append((field, executable_next_action(command.strip())))
            for metadata_field in (
                "sourceRunId",
                "threadId",
                "checkpointNs",
                "checkpointId",
                "approvalId",
            ):
                metadata_value = typed_action.get(metadata_field)
                if isinstance(metadata_value, str) and metadata_value.strip():
                    rows.append((f"{field}.{metadata_field}", metadata_value.strip()))
    return rows


def format_fork_table(body: dict[str, object] | list[object] | None) -> str:
    if not isinstance(body, dict):
        return "FIELD  VALUE\n"
    provenance = mapping_table_value(body, "provenance")
    rows = [
        ("run_id", table_value(body, "run_id", "runId")),
        ("source_run_id", table_value(body, "source_run_id", "sourceRunId")),
        ("thread_id", table_value(body, "thread_id", "threadId")),
        ("checkpoint_ns", table_value(body, "checkpoint_ns", "checkpointNs")),
        ("status", body.get("status")),
        ("provenance_source", table_value(provenance, "source")),
        (
            "forked_from_checkpoint_id",
            table_value(provenance, "forked_from_checkpoint_id", "forkedFromCheckpointId"),
        ),
        (
            "fork_target_thread_id",
            table_value(provenance, "fork_target_thread_id", "forkTargetThreadId"),
        ),
        (
            "fork_target_checkpoint_ns",
            table_value(provenance, "fork_target_checkpoint_ns", "forkTargetCheckpointNs"),
        ),
        ("response", table_value(body, "response")),
        ("response_text", table_value(body, "response_text", "responseText")),
    ]
    run_id = optional_text(body.get("run_id")) or optional_text(body.get("runId"))
    next_action_rows = run_result_next_action_rows(body.get("nextActions"))
    if next_action_rows:
        rows.extend(next_action_rows)
    elif run_id is not None:
        quoted_run_id = quote(run_id)
        rows.append(("nextAction", f"reactor-runs diagnose {quoted_run_id} --output table"))
        rows.append(
            (
                "stateHistoryAction",
                f"reactor-admin state-history {quoted_run_id} --output table",
            )
        )
        rows.append(("replayAction", f"reactor-runs replay {quoted_run_id} --output table"))
    rows = [(field, value) for field, value in rows if value is not None]
    width = max([len("FIELD"), *(len(field) for field, _ in rows)])
    lines = [f"{'FIELD':<{width}}  VALUE"]
    lines.extend(f"{field:<{width}}  {value}" for field, value in rows)
    return "\n".join(lines) + "\n"


def format_eval_case_table(body: dict[str, object] | list[object] | None) -> str:
    if not isinstance(body, dict):
        return "FIELD  VALUE\n"
    case_body = body.get("promotedCase")
    suite_apply = body.get("suiteApply")
    suite_summary = body.get("suiteSummary")
    if isinstance(case_body, dict):
        body = cast(dict[str, object], case_body)
    rows = [
        ("id", body.get("id")),
        ("sourceRunId", body.get("sourceRunId")),
        ("assertionCount", body.get("assertionCount")),
        ("minScore", body.get("minScore")),
        ("enabled", bool_text(body.get("enabled"))),
    ]
    if isinstance(suite_apply, dict):
        typed_suite_apply = cast(dict[object, object], suite_apply)
        rows.extend(
            [
                ("suiteStatus", typed_suite_apply.get("status")),
                ("suiteCaseCount", typed_suite_apply.get("caseCount")),
                ("runStatus", typed_suite_apply.get("runStatus")),
                ("runId", typed_suite_apply.get("runId")),
                ("runCount", typed_suite_apply.get("runCount")),
                ("suitePersistCommand", typed_suite_apply.get("persistCommand")),
            ]
        )
        coverage = typed_suite_apply.get("promotionCoverage")
        if isinstance(coverage, dict):
            typed_coverage = cast(dict[object, object], coverage)
            rows.extend(
                [
                    (
                        "coverageCitationMarkers",
                        bool_table_value(typed_coverage.get("citationMarkersPresent")),
                    ),
                    (
                        "coverageRunCitationMarkers",
                        bool_table_value(typed_coverage.get("runCitationMarkersPresent")),
                    ),
                ]
            )
        langsmith_dry_run = typed_suite_apply.get("langsmithDryRun")
        if isinstance(langsmith_dry_run, dict):
            typed_langsmith_dry_run = cast(dict[object, object], langsmith_dry_run)
            langsmith_dry_run_table: dict[str, object] = {
                str(key): value for key, value in typed_langsmith_dry_run.items()
            }
            deterministic_summary = trace_deterministic_eval_summary_value(
                langsmith_trace_grading_value(langsmith_dry_run_table)
            )
            release_gate = typed_langsmith_dry_run.get("releaseGate")
            typed_release_gate = (
                cast(dict[object, object], release_gate) if isinstance(release_gate, dict) else {}
            )
            feedback_review_queue = typed_langsmith_dry_run.get("feedbackReviewQueue")
            typed_feedback_review_queue = (
                cast(dict[object, object], feedback_review_queue)
                if isinstance(feedback_review_queue, dict)
                else {}
            )
            feedback_queue_review_action = feedback_review_queue_action(
                {
                    str(key): value
                    for key, value in typed_feedback_review_queue.items()
                    if isinstance(key, str)
                }
            )
            feedback_queue_candidate_action = feedback_review_queue_candidate_review_action(
                {
                    str(key): value
                    for key, value in typed_feedback_review_queue.items()
                    if isinstance(key, str)
                }
            )
            feedback_queue_export_action = feedback_review_queue_export_action(
                {
                    str(key): value
                    for key, value in typed_feedback_review_queue.items()
                    if isinstance(key, str)
                }
            )
            feedback_queue_memory_action = feedback_review_queue_memory_lifecycle_action(
                {
                    str(key): value
                    for key, value in typed_feedback_review_queue.items()
                    if isinstance(key, str)
                }
            )
            rows.extend(
                [
                    ("langsmithStatus", typed_langsmith_dry_run.get("status")),
                    ("langsmithDataset", typed_langsmith_dry_run.get("datasetName")),
                    ("langsmithExamples", typed_langsmith_dry_run.get("examples")),
                    (
                        "langsmithCaseIds",
                        comma_separated_table_value(langsmith_dry_run_table, "caseIds"),
                    ),
                    (
                        "langsmithMetadataIds",
                        comma_separated_table_value(langsmith_dry_run_table, "metadataCaseIds"),
                    ),
                    (
                        "langsmithSourceRunIds",
                        len(string_list_value(typed_langsmith_dry_run.get("sourceRunIds"))),
                    ),
                    (
                        "langsmithCaseSourceRunMappings",
                        string_mapping_count(typed_langsmith_dry_run.get("caseSourceRunIds")),
                    ),
                    (
                        "langsmithSplitCounts",
                        mapping_count_summary(typed_langsmith_dry_run.get("splitCounts")),
                    ),
                    ("langsmithSourceSuite", typed_langsmith_dry_run.get("sourceSuite")),
                    ("langsmithFeedbackCases", typed_langsmith_dry_run.get("feedbackCases")),
                    ("langsmithFeedbackIds", typed_langsmith_dry_run.get("feedbackIds")),
                    (
                        "langsmithFeedbackIdList",
                        comma_separated_table_value(langsmith_dry_run_table, "feedbackIdList"),
                    ),
                    (
                        "langsmithFeedbackReviewIds",
                        comma_separated_table_value(langsmith_dry_run_table, "feedbackReviewIds"),
                    ),
                    (
                        "langsmithFeedbackRatings",
                        mapping_count_summary(typed_langsmith_dry_run.get("feedbackRatings")),
                    ),
                    (
                        "langsmithFeedbackSources",
                        mapping_count_summary(typed_langsmith_dry_run.get("feedbackSources")),
                    ),
                    (
                        "langsmithFeedbackReviewAction",
                        langsmith_feedback_review_action(typed_langsmith_dry_run),
                    ),
                    (
                        "langsmithFeedbackQueueCases",
                        string_list_count(typed_feedback_review_queue.get("caseIds")),
                    ),
                    (
                        "langsmithFeedbackQueueRatings",
                        mapping_count_summary(
                            typed_feedback_review_queue.get("feedbackRatingCounts")
                        ),
                    ),
                    (
                        "langsmithFeedbackQueueSources",
                        mapping_count_summary(
                            typed_feedback_review_queue.get("feedbackSourceCounts")
                        ),
                    ),
                    (
                        "langsmithFeedbackQueueWorkflows",
                        mapping_count_summary(typed_feedback_review_queue.get("workflowTagCounts")),
                    ),
                    (
                        "langsmithFeedbackQueueReviewAction",
                        feedback_queue_review_action
                        or typed_feedback_review_queue.get("reviewAction"),
                    ),
                    (
                        "langsmithFeedbackQueueExportAction",
                        feedback_queue_export_action
                        or typed_feedback_review_queue.get("exportAction"),
                    ),
                    (
                        "langsmithFeedbackQueueCandidateAction",
                        feedback_queue_candidate_action
                        or typed_feedback_review_queue.get("candidateReviewAction"),
                    ),
                    (
                        "langsmithFeedbackQueueBulkReviewAction",
                        typed_feedback_review_queue.get("bulkReviewAction"),
                    ),
                    (
                        "langsmithFeedbackQueueMemoryAction",
                        feedback_queue_memory_action
                        or typed_feedback_review_queue.get("memoryLifecycleAction"),
                    ),
                    (
                        "langsmithGroundingCases",
                        typed_langsmith_dry_run.get("groundingCitationCases"),
                    ),
                    (
                        "langsmithGroundingCited",
                        typed_langsmith_dry_run.get("groundingCitedChunks"),
                    ),
                    (
                        "langsmithGroundingUncited",
                        typed_langsmith_dry_run.get("groundingUncitedChunks"),
                    ),
                    (
                        "langsmithGroundingDocuments",
                        comma_separated_table_value(
                            langsmith_dry_run_table,
                            "groundingCitationDocuments",
                        ),
                    ),
                    ("langsmithGradedRuns", typed_langsmith_dry_run.get("gradedRuns")),
                    (
                        "langsmithMissingRun",
                        typed_langsmith_dry_run.get("missingRunCases"),
                    ),
                    (
                        "langsmithDeterministicFailedCases",
                        typed_langsmith_dry_run.get("deterministicEvalFailedCases")
                        or deterministic_summary.get("deterministicEvalFailedCases"),
                    ),
                    (
                        "langsmithDeterministicMissingExpected",
                        comma_separated_table_value(
                            langsmith_dry_run_table
                            if "deterministicEvalMissingExpected" in langsmith_dry_run_table
                            else deterministic_summary,
                            "deterministicEvalMissingExpected",
                        ),
                    ),
                    ("langsmithReleaseGate", typed_release_gate.get("status")),
                    ("langsmithGateReason", typed_release_gate.get("reason")),
                    ("langsmithRequiredReport", typed_release_gate.get("requiredReport")),
                    ("langsmithReleaseNext", release_gate_next_action(typed_release_gate)),
                    ("langsmithReleasePlan", release_gate_remediation_plan(typed_release_gate)),
                    (
                        "langsmithReleaseGateRemediationCommand",
                        release_gate_remediation_command(typed_release_gate),
                    ),
                    ("langsmithSyncCommand", typed_langsmith_dry_run.get("syncCommand")),
                    (
                        "langsmithLiveSyncCommand",
                        typed_langsmith_dry_run.get("liveSyncCommand"),
                    ),
                    (
                        "langsmithPersistCommand",
                        typed_langsmith_dry_run.get("persistCommand"),
                    ),
                    (
                        "langsmithSummaryCommand",
                        typed_langsmith_dry_run.get("summaryCommand"),
                    ),
                    (
                        "langsmithReadinessCommand",
                        typed_langsmith_dry_run.get("readinessCommand"),
                    ),
                    (
                        "langsmithProductBoundaryReadinessCommand",
                        typed_langsmith_dry_run.get("productBoundaryReadinessCommand"),
                    ),
                    ("langsmithReportFile", typed_langsmith_dry_run.get("reportFile")),
                ]
            )
            rows.extend(langsmith_next_action_rows(typed_langsmith_dry_run.get("nextActions")))
    if isinstance(suite_summary, dict):
        typed_suite_summary = cast(dict[object, object], suite_summary)
        rows.extend(
            [
                ("suiteCoveredCases", typed_suite_summary.get("coveredCases")),
                ("suiteMissingRuns", typed_suite_summary.get("missingRuns")),
            ]
        )
    if not isinstance(suite_apply, dict):
        next_action = eval_case_suite_apply_next_action(body)
        if next_action:
            rows.append(("nextAction", next_action))
    present_rows = [(field, value) for field, value in rows if value is not None and value != ""]
    width = max([len("FIELD"), *(len(field) for field, _ in present_rows)])
    lines = [f"{'FIELD':<{width}}  VALUE"]
    lines.extend(f"{field:<{width}}  {value}" for field, value in present_rows)
    return "\n".join(lines) + "\n"


def eval_case_suite_apply_next_action(case: Mapping[str, object]) -> str:
    case_id = optional_text(case.get("id"))
    source_run_id = optional_text(case.get("sourceRunId"))
    if case_id is None or source_run_id is None:
        return ""
    raw_tags = string_sequence_from_mapping(case, "tags")
    tags = set(raw_tags)
    suite_file = "tests/fixtures/agent-eval/regression-suite.json"
    dataset_arg = ""
    promoted_case_args = ""
    report_file = "reports/langsmith-eval-sync-dry-run.json"
    case_file = "promoted-case.json"
    run_file = "promoted-run.json"
    if "collection:rag-ingestion-candidate" in tags:
        suite_file = "evals/regression/rag-ingestion-candidate.json"
        dataset_arg = "--apply-dataset-name reactor-rag-ingestion-candidate "
        report_file = f"artifacts/langsmith/rag-ingestion-candidate-{case_id}.json"
        case_file = f"evals/cases/{case_id}.json"
        run_file = f"evals/runs/{command_slug(source_run_id)}.json"
        expected_answer_args = "".join(
            f"--expected-answer {quote(expected_answer)} "
            for expected_answer in string_sequence_from_mapping(case, "expectedAnswerContains")
        )
        tag_args = "".join(f"--tag {quote(tag)} " for tag in dedupe_strings(raw_tags))
        promoted_case_args = f"{expected_answer_args}{tag_args}"
    dry_run_arg = "" if "collection:rag-ingestion-candidate" in tags else "--apply-dry-run "
    return (
        f"reactor-runs promote-eval {source_run_id} --case-id {case_id} "
        f"{promoted_case_args}"
        f"--case-file {case_file} --run-file {run_file} "
        f"--apply-suite-file {suite_file} "
        f"{dataset_arg}"
        f"{dry_run_arg}--apply-require-source-run-id "
        "--apply-require-run-file --apply-require-context-diagnostics "
        "--apply-suite-summary "
        f"--langsmith-dry-run-report-file {report_file} "
        "--output table"
    )


def langsmith_next_action_rows(value: object) -> list[tuple[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    rows: list[tuple[str, object]] = []
    action_ids: list[str] = []
    for index, action in enumerate(cast(Sequence[object], value), start=1):
        if not isinstance(action, Mapping):
            continue
        mapping = cast(Mapping[object, object], action)
        command = mapping.get("command")
        if not isinstance(command, str) or not command.strip():
            continue
        action_id = mapping.get("id")
        normalized_id = (
            safe_next_action_id(action_id.strip())
            if isinstance(action_id, str) and action_id.strip()
            else str(index)
        )
        action_ids.append(normalized_id)
        rows.append(
            (
                f"langsmithNextAction.{normalized_id}",
                executable_next_action(command.strip()),
            )
        )
        feedback_id = mapping.get("feedbackId")
        if isinstance(feedback_id, str) and feedback_id.strip():
            rows.append((f"langsmithNextAction.{normalized_id}.feedbackId", feedback_id.strip()))
        for field_name in (
            "evalCaseId",
            "sourceRunId",
            "candidateTag",
            "requiredReviewNote",
            "recommendedVersionBump",
            "recommendedTagPattern",
            "latestTagCommand",
            "recommendedTagSource",
            "replatformReadinessFile",
            "smokePlanFile",
            "releaseEvidenceFile",
        ):
            field_value = mapping.get(field_name)
            if isinstance(field_value, str) and field_value.strip():
                rows.append(
                    (
                        f"langsmithNextAction.{normalized_id}.{field_name}",
                        field_value.strip(),
                    )
                )
        remediation_command = mapping.get("remediationCommand")
        if isinstance(remediation_command, str) and remediation_command.strip():
            rows.append(
                (
                    f"langsmithNextAction.{normalized_id}.remediationCommand",
                    executable_next_action(remediation_command.strip()),
                )
            )
        release_readiness_command = mapping.get("releaseReadinessCommand")
        if isinstance(release_readiness_command, str) and release_readiness_command.strip():
            rows.append(
                (
                    f"langsmithNextAction.{normalized_id}.releaseReadinessCommand",
                    executable_next_action(release_readiness_command.strip()),
                )
            )
        readiness_report_arg = mapping.get("readinessReportArg")
        if isinstance(readiness_report_arg, str) and readiness_report_arg.strip():
            rows.append(
                (
                    f"langsmithNextAction.{normalized_id}.readinessReportArg",
                    readiness_report_arg.strip(),
                )
            )
        for index, env_group in enumerate(
            required_env_any_of_parts(mapping.get("requiredEnvAnyOf"))
        ):
            rows.append(
                (
                    f"langsmithNextAction.{normalized_id}.requiredEnvAnyOf.{index}",
                    env_group,
                )
            )
        missing_env_any_of = string_list_value(mapping.get("missingEnvAnyOf"))
        if missing_env_any_of:
            rows.append(
                (
                    f"langsmithNextAction.{normalized_id}.missingEnvAnyOf",
                    ",".join(missing_env_any_of),
                )
            )
        recommended_env = string_list_value(mapping.get("recommendedEnv"))
        if recommended_env:
            rows.append(
                (
                    f"langsmithNextAction.{normalized_id}.recommendedEnv",
                    ",".join(recommended_env),
                )
            )
        depends_on_action_ids = action_string_list_field(mapping, "dependsOnActionIds")
        if depends_on_action_ids:
            rows.append(
                (
                    f"langsmithNextAction.{normalized_id}.dependsOnActionIds",
                    ",".join(depends_on_action_ids),
                )
            )
        required_reports = action_required_readiness_reports(mapping)
        if required_reports:
            rows.append(
                (
                    f"langsmithNextAction.{normalized_id}.requiredReadinessReports",
                    ",".join(required_reports),
                )
            )
        minor_boundary_reports = action_minor_boundary_reports(mapping)
        if minor_boundary_reports:
            rows.append(
                (
                    f"langsmithNextAction.{normalized_id}.minorBoundaryReports",
                    ",".join(minor_boundary_reports),
                )
            )
        for field_name in ("minorBlockedReports", "minorBoundaryMissingEvidence"):
            values = action_string_list_field(mapping, field_name)
            if values:
                rows.append(
                    (
                        f"langsmithNextAction.{normalized_id}.{field_name}",
                        ",".join(values),
                    )
                )
        rows.extend(langsmith_next_action_readiness_report_rows(normalized_id, mapping))
    if action_ids:
        rows.insert(0, ("langsmithNextActionIds", ",".join(action_ids)))
    return rows


def action_required_readiness_reports(action: Mapping[object, object]) -> list[str]:
    value = action.get("requiredReadinessReports")
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [
        report.strip()
        for report in cast(Sequence[object], value)
        if isinstance(report, str) and report.strip()
    ]


def action_minor_boundary_reports(action: Mapping[object, object]) -> list[str]:
    return action_string_list_field(action, "minorBoundaryReports")


def action_string_list_field(action: Mapping[object, object], field_name: str) -> list[str]:
    value = action.get(field_name)
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [
        report.strip()
        for report in cast(Sequence[object], value)
        if isinstance(report, str) and report.strip()
    ]


def langsmith_next_action_readiness_report_rows(
    action_id: str,
    action: Mapping[object, object],
) -> list[tuple[str, object]]:
    value = action.get("readinessReports")
    if not isinstance(value, Mapping):
        return []
    rows: list[tuple[str, object]] = []
    for report_name, report_file in sorted(
        cast(Mapping[object, object], value).items(),
        key=lambda item: str(item[0]),
    ):
        if not isinstance(report_name, str) or not isinstance(report_file, str):
            continue
        report_name = report_name.strip()
        report_file = report_file.strip()
        if report_name and report_file:
            rows.append(
                (
                    f"langsmithNextAction.{action_id}.readinessReports.{report_name}",
                    report_file,
                )
            )
    return rows


def suite_apply_persist_command(args: argparse.Namespace) -> str:
    command = (
        f"reactor-runs promote-eval {quote(args.run_id)} --case-id {quote(args.case_id)} "
        f"--case-file {quote(args.case_file)} "
    )
    if args.run_file:
        command = f"{command}--run-file {quote(args.run_file)} "
    command = f"{command}--apply-suite-file {quote(args.apply_suite_file)} "
    if args.apply_dataset_name != "reactor-regression":
        command = f"{command}--apply-dataset-name {quote(args.apply_dataset_name)} "
    if args.apply_replace:
        command = f"{command}--apply-replace "
    if args.apply_require_source_run_id:
        command = f"{command}--apply-require-source-run-id "
    if args.apply_require_run_file:
        command = f"{command}--apply-require-run-file "
    if args.apply_require_context_diagnostics:
        command = f"{command}--apply-require-context-diagnostics "
    if args.apply_suite_summary:
        command = f"{command}--apply-suite-summary "
    if args.langsmith_dry_run_report_file:
        command = (
            f"{command}--langsmith-dry-run-report-file {quote(args.langsmith_dry_run_report_file)} "
        )
    command = f"{command}{feedback_review_command_args(args)}"
    return f"{command}--output table"


def feedback_review_command_args(args: argparse.Namespace) -> str:
    command = ""
    if args.feedback_review_status:
        command = f"{command}--feedback-review-status {quote(args.feedback_review_status)} "
    for tag in args.feedback_review_tag or ():
        command = f"{command}--feedback-review-tag {quote(tag)} "
    if args.feedback_review_note:
        command = f"{command}--feedback-review-note {quote(args.feedback_review_note)} "
    return command


def suite_apply_summary_command(args: argparse.Namespace) -> str:
    command = f"reactor-agent-eval-apply --suite-file {quote(args.apply_suite_file)} "
    if args.apply_dataset_name != "reactor-regression":
        command = f"{command}--dataset-name {quote(args.apply_dataset_name)} "
    else:
        command = f"{command}--dataset-name reactor-regression "
    command = f"{command}--summary "
    if args.langsmith_dry_run_report_file:
        command = (
            f"{command}--langsmith-dry-run-report-file {quote(args.langsmith_dry_run_report_file)} "
        )
    return f"{command}--output table"


def langsmith_feedback_review_action(summary: Mapping[object, object]) -> str:
    feedback_ids = string_list_value(summary.get("feedbackIdList"))
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
    return "reactor-admin feedback --limit 10 --output table"


def string_list_value(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [
        item for item in cast(Sequence[object], value) if isinstance(item, str) and item.strip()
    ]


def required_env_any_of_parts(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    parts: list[str] = []
    for group in cast(Sequence[object], value):
        if not isinstance(group, Sequence) or isinstance(group, str | bytes | bytearray):
            continue
        env_names = [
            env_name.strip()
            for env_name in cast(Sequence[object], group)
            if isinstance(env_name, str) and env_name.strip()
        ]
        if env_names:
            parts.append("|".join(env_names))
    return parts


def string_list_count(value: object) -> int | None:
    count = len(string_list_value(value))
    return count if count > 0 else None


def string_mapping_count(value: object) -> int | None:
    if not isinstance(value, Mapping):
        return None
    count = sum(
        1
        for key, item in cast(Mapping[object, object], value).items()
        if isinstance(key, str) and key.strip() and isinstance(item, str) and item.strip()
    )
    return count if count > 0 else None


def release_gate_next_action(release_gate: Mapping[object, object]) -> str:
    remediation = release_gate.get("remediation")
    if not isinstance(remediation, Sequence) or isinstance(remediation, str):
        return ""
    for item in cast(Sequence[object], remediation):
        if isinstance(item, str) and item.strip():
            return item.strip()
    return ""


def release_gate_remediation_plan(release_gate: Mapping[object, object]) -> str:
    remediation = release_gate.get("remediation")
    if not isinstance(remediation, Sequence) or isinstance(remediation, str):
        return ""
    actions = [
        item.strip()
        for item in cast(Sequence[object], remediation)
        if isinstance(item, str) and item.strip()
    ]
    return " | ".join(actions)


def release_gate_remediation_command(release_gate: Mapping[object, object]) -> str:
    command = release_gate.get("remediationCommand")
    return command.strip() if isinstance(command, str) else ""


def format_preflight_table(body: dict[str, object] | list[object] | None) -> str:
    if not isinstance(body, dict):
        return "FIELD  VALUE\n"
    middleware_chain = mapping_table_value(body, "middlewareChain", "middleware_chain")
    tool_profile_budget = mapping_table_value(body, "toolProfileBudget", "tool_profile_budget")
    structured_output = mapping_table_value(body, "structuredOutput", "structured_output")
    rows = [
        ("status", body.get("status")),
        ("runtime", body.get("runtime")),
        ("threadId", body.get("threadId")),
        ("checkpointNs", body.get("checkpointNs")),
        ("model", preflight_model_summary(body.get("model"))),
        ("middlewareCount", table_value(middleware_chain, "count")),
        (
            "middlewareChain",
            comma_separated_table_value(middleware_chain, "middleware"),
        ),
        ("activeTools", preflight_active_tools_summary(tool_profile_budget)),
        ("structuredOutput", table_value(structured_output, "strategy")),
        ("structuredStatus", table_value(structured_output, "status")),
    ]
    present_rows = [(field, value) for field, value in rows if value]
    width = max([len("FIELD"), *(len(field) for field, _ in present_rows)])
    lines = [f"{'FIELD':<{width}}  VALUE"]
    lines.extend(f"{field:<{width}}  {value}" for field, value in present_rows)
    return "\n".join(lines) + "\n"


def preflight_active_tools_summary(tool_profile_budget: dict[str, object]) -> str:
    active = table_value(tool_profile_budget, "activeToolCount", "active_tool_count")
    configured = table_value(
        tool_profile_budget,
        "configuredToolCount",
        "configured_tool_count",
    )
    if active is None:
        return ""
    if configured is None:
        return str(active)
    return f"{active}/{configured}"


def preflight_model_summary(model: object) -> str:
    if not isinstance(model, dict):
        return ""
    typed_model = cast(dict[object, object], model)
    provider = typed_model.get("provider")
    name = typed_model.get("name")
    if isinstance(provider, str) and provider and isinstance(name, str) and name:
        return f"{provider}/{name}"
    if isinstance(name, str):
        return name
    return ""


def format_replay_table(
    body: dict[str, object] | list[object] | None,
    *,
    run_id: str | None = None,
) -> str:
    if not isinstance(body, list):
        return "SEQ  EVENT  SUMMARY\n"
    rows = [
        stream_event_table_row(cast(dict[object, object], item))
        for item in body
        if isinstance(item, dict)
    ]
    widths = (
        max([len("SEQ"), *(len(row[0]) for row in rows)]),
        max([len("EVENT"), *(len(row[1]) for row in rows)]),
        max([len("NODE"), *(len(row[2]) for row in rows)]),
        max([len("TRACE"), *(len(row[3]) for row in rows)]),
    )
    lines = [
        f"{'SEQ':<{widths[0]}}  {'EVENT':<{widths[1]}}  {'NODE':<{widths[2]}}  "
        f"{'TRACE':<{widths[3]}}  SUMMARY"
    ]
    lines.extend(
        f"{sequence:<{widths[0]}}  {event_type:<{widths[1]}}  {graph_node:<{widths[2]}}  "
        f"{trace_id:<{widths[3]}}  {summary}"
        for sequence, event_type, graph_node, trace_id, summary in rows
    )
    if run_id:
        quoted_run_id = quote(run_id)
        latest_sequence = latest_stream_sequence(body)
        lines.extend(
            (
                "",
                "FIELD               VALUE",
                f"diagnoseAction      reactor-runs diagnose {quoted_run_id} --output table",
                f"stateHistoryAction  reactor-admin state-history {quoted_run_id} --output table",
            )
        )
        if latest_sequence is not None:
            lines.append(
                "replayNextAction    "
                f"reactor-runs replay {quoted_run_id} --after-sequence {latest_sequence} "
                "--output table"
            )
    return "\n".join(lines) + "\n"


def latest_stream_sequence(body: list[object]) -> int | None:
    sequences: list[int] = []
    for item in body:
        if not isinstance(item, dict):
            continue
        sequence = cast(dict[object, object], item).get("sequence")
        if isinstance(sequence, int) and not isinstance(sequence, bool):
            sequences.append(sequence)
    return max(sequences) if sequences else None


def stream_event_table_row(item: dict[object, object]) -> tuple[str, str, str, str, str]:
    payload = item.get("payload")
    return (
        str(item.get("sequence") or ""),
        str(item.get("event_type") or item.get("eventType") or ""),
        stream_event_graph_node(payload),
        stream_event_trace_id(payload),
        stream_event_summary(payload),
    )


def stream_event_graph_node(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    typed_payload = cast(dict[object, object], payload)
    graph_node = typed_payload.get("graph_node") or typed_payload.get("graphNode")
    return graph_node if isinstance(graph_node, str) else ""


def stream_event_trace_id(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    typed_payload = cast(dict[object, object], payload)
    trace_id = typed_payload.get("trace_id") or typed_payload.get("traceId")
    return trace_id if isinstance(trace_id, str) else ""


def stream_event_summary(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    typed_payload = cast(dict[object, object], payload)
    text = typed_payload.get("text")
    parts: list[str] = []
    seen_labels: set[str] = set()
    if isinstance(text, str) and text:
        parts.append(f"text={redact_span_attribute_value(text)}")
        seen_labels.add("text")
    for field, label in (
        ("run_id", "streamRun"),
        ("runId", "streamRun"),
        ("approval_status", "approvalStatus"),
        ("approvalStatus", "approvalStatus"),
        ("approval_id", "approvalId"),
        ("approvalId", "approvalId"),
        ("status", "status"),
        ("error", "error"),
        ("tool_id", "toolId"),
        ("toolId", "toolId"),
        ("mode", "mode"),
        ("version", "version"),
    ):
        value = typed_payload.get(field)
        if label not in seen_labels and isinstance(value, str) and value.strip():
            parts.append(f"{label}={value.strip()}")
            seen_labels.add(label)
    parent_count = stream_event_parent_count(typed_payload)
    if parent_count:
        parts.append(f"parentRuns={parent_count}")
    return " ".join(parts)


def stream_event_parent_count(payload: Mapping[object, object]) -> int:
    parent_ids = payload.get("parent_ids") or payload.get("parentIds")
    if not isinstance(parent_ids, Sequence) or isinstance(parent_ids, str):
        return 0
    count = 0
    for item in cast(Sequence[object], parent_ids):
        if isinstance(item, str) and item.strip():
            count += 1
    return count


def format_diagnose_table(body: dict[str, object] | list[object] | None) -> str:
    if not isinstance(body, dict):
        return "SECTION  OK  STATUS  SUMMARY\n"
    sections = ("status", "streamEvents", "toolInvocations")
    rows: list[tuple[str, str, str, str]] = []
    for section_name in sections:
        section = body.get(section_name)
        if isinstance(section, dict):
            typed_section = cast(dict[object, object], section)
            rows.append(
                (
                    section_name,
                    section_ok(typed_section),
                    section_status_code(typed_section),
                    diagnose_section_summary(section_name, typed_section),
                )
            )
    rows.extend(diagnose_next_action_rows(body.get("nextActions")))
    widths = (
        max([len("SECTION"), *(len(row[0]) for row in rows)]),
        max([len("OK"), *(len(row[1]) for row in rows)]),
        max([len("STATUS"), *(len(row[2]) for row in rows)]),
    )
    lines = [f"{'SECTION':<{widths[0]}}  {'OK':<{widths[1]}}  {'STATUS':<{widths[2]}}  SUMMARY"]
    lines.extend(
        f"{section:<{widths[0]}}  {ok:<{widths[1]}}  {status:<{widths[2]}}  {summary}"
        for section, ok, status, summary in rows
    )
    return "\n".join(lines) + "\n"


def diagnose_next_action_summary(value: object) -> str:
    if not isinstance(value, list) or not value:
        return ""
    next_actions = cast(list[object], value)
    commands: list[str] = []
    for action in next_actions:
        if not isinstance(action, dict):
            continue
        typed_action = cast(dict[object, object], action)
        command = typed_action.get("command")
        if isinstance(command, str) and command.strip():
            commands.append(executable_next_action(command.strip()))
    return "; ".join(commands)


def diagnose_next_action_rows(value: object) -> list[tuple[str, str, str, str]]:
    if not isinstance(value, list) or not value:
        return []
    rows: list[tuple[str, str, str, str]] = []
    for index, action in enumerate(cast(list[object], value), start=1):
        if not isinstance(action, dict):
            continue
        typed_action = cast(dict[object, object], action)
        command = typed_action.get("command")
        if not isinstance(command, str) or not command.strip():
            continue
        action_id = typed_action.get("id")
        row_id = (
            safe_next_action_id(action_id.strip())
            if isinstance(action_id, str) and action_id.strip()
            else str(index)
        )
        rows.append((f"nextAction.{row_id}", "true", "-", executable_next_action(command.strip())))
        for field_name in (
            "evalCaseId",
            "sourceRunId",
            "candidateTag",
            "threadId",
            "caseFile",
            "runFile",
            "suiteFile",
            "datasetName",
            "reportFile",
            "readinessReportArg",
            "checkpointNs",
            "checkpointId",
            "approvalId",
            "toolStatus",
        ):
            field_value = typed_action.get(field_name)
            if isinstance(field_value, str) and field_value.strip():
                rows.append((f"nextAction.{row_id}.{field_name}", "true", "-", field_value.strip()))
        required_reports = action_string_sequence_summary(
            typed_action.get("requiredReadinessReports")
        )
        if required_reports:
            rows.append(
                (
                    f"nextAction.{row_id}.requiredReadinessReports",
                    "true",
                    "-",
                    required_reports,
                )
            )
        eval_tags = action_string_sequence_summary(typed_action.get("evalTags"))
        if eval_tags:
            rows.append((f"nextAction.{row_id}.evalTags", "true", "-", eval_tags))
        readiness_reports = action_string_mapping(typed_action.get("readinessReports"))
        for report_name, report_file in readiness_reports.items():
            rows.append(
                (
                    f"nextAction.{row_id}.readinessReports.{report_name}",
                    "true",
                    "-",
                    report_file,
                )
            )
    return rows


def action_string_sequence_summary(value: object) -> str:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return ""
    strings = [str(item).strip() for item in cast(Sequence[object], value)]
    return ",".join(item for item in strings if item)


def action_string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str] = {}
    for raw_key, raw_value in cast(Mapping[object, object], value).items():
        key = str(raw_key).strip()
        item = str(raw_value).strip()
        if key and item:
            result[key] = item
    return result


def executable_next_action(command: str) -> str:
    return command.replace("VERIFY_TIMESTAMP", "$(date -u +%Y-%m-%dT%H:%M:%SZ)")


def safe_next_action_id(value: str) -> str:
    return (
        "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_")
        or "action"
    )


def format_tool_invocations_table(body: dict[str, object] | list[object] | None) -> str:
    if not isinstance(body, list):
        return "ID  TOOL  STATUS  SUCCESS  ERROR\n"
    rows = [
        tool_invocation_table_row(cast(dict[object, object], item))
        for item in body
        if isinstance(item, dict)
    ]
    widths = (
        max([len("ID"), *(len(row[0]) for row in rows)]),
        max([len("TOOL"), *(len(row[1]) for row in rows)]),
        max([len("STATUS"), *(len(row[2]) for row in rows)]),
        max([len("SUCCESS"), *(len(row[3]) for row in rows)]),
    )
    lines = [
        f"{'ID':<{widths[0]}}  {'TOOL':<{widths[1]}}  "
        f"{'STATUS':<{widths[2]}}  {'SUCCESS':<{widths[3]}}  ERROR"
    ]
    lines.extend(
        f"{tool_id:<{widths[0]}}  {tool_name:<{widths[1]}}  "
        f"{status:<{widths[2]}}  {success:<{widths[3]}}  {error}"
        for tool_id, tool_name, status, success, error in rows
    )
    return "\n".join(lines) + "\n"


def tool_invocation_table_row(item: dict[object, object]) -> tuple[str, str, str, str, str]:
    return (
        str(item.get("id") or ""),
        str(item.get("toolId") or item.get("tool_id") or ""),
        str(item.get("status") or ""),
        bool_text(item.get("success")),
        tool_invocation_error_summary(item.get("error")),
    )


def bool_text(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return ""


def tool_invocation_error_summary(error: object) -> str:
    if isinstance(error, dict):
        typed_error = cast(dict[object, object], error)
        message = typed_error.get("message")
        if isinstance(message, str):
            return message
        return json.dumps(typed_error, sort_keys=True, separators=(",", ":"))
    if isinstance(error, str):
        return error
    return ""


def section_ok(section: dict[object, object]) -> str:
    return "true" if section.get("ok") is True else "false"


def section_status_code(section: dict[object, object]) -> str:
    status_code = section.get("statusCode")
    return str(status_code) if status_code is not None else ""


def diagnose_section_summary(section_name: str, section: dict[object, object]) -> str:
    if section.get("ok") is not True:
        return str(section.get("error") or "")
    body = section.get("body")
    if section_name == "status" and isinstance(body, dict):
        status_body = cast(dict[object, object], body)
        return status_diagnostics_summary(status_body)
    if section_name == "streamEvents" and isinstance(body, list):
        stream_events = cast(list[object], body)
        event_counts = stream_event_type_counts(stream_events)
        traced_count = traced_stream_event_count(stream_events)
        summary = f"events={len(stream_events)}"
        if stream_events:
            summary = f"{summary} traced={traced_count}/{len(stream_events)}"
        if event_counts:
            event_parts = [
                f"{event_type}={event_counts[event_type]}" for event_type in event_counts
            ]
            summary = " ".join([summary, *event_parts])
        return summary
    if section_name == "toolInvocations" and isinstance(body, list):
        tool_invocations = cast(list[object], body)
        failed_count, failed_tools = failed_tool_summary(tool_invocations)
        summary = f"tools={len(tool_invocations)} failed={failed_count}"
        if failed_tools:
            summary = f"{summary} failedTools={','.join(failed_tools)}"
        recovery_summary = approval_recovery_summary(tool_invocations)
        if recovery_summary:
            summary = f"{summary} {recovery_summary}"
        return summary
    return ""


def traced_stream_event_count(stream_events: Sequence[object]) -> int:
    return sum(
        1
        for event in stream_events
        if isinstance(event, dict)
        and stream_event_trace_id(cast(dict[object, object], event).get("payload"))
    )


def stream_event_type_counts(stream_events: Sequence[object]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in stream_events:
        if not isinstance(item, dict):
            continue
        typed_item = cast(dict[object, object], item)
        event_type = typed_item.get("event_type") or typed_item.get("eventType")
        if not isinstance(event_type, str) or not event_type.strip():
            continue
        if not event_type.startswith("run.stream."):
            continue
        normalized = event_type.removeprefix("run.stream.").strip()
        if normalized:
            counts[normalized] += 1
    return dict(sorted(counts.items()))


def status_diagnostics_summary(status_body: dict[object, object]) -> str:
    parts = [str(status_body.get("status") or "")]
    metadata = status_body.get("metadata")
    metadata_mapping = cast(dict[str, object], metadata) if isinstance(metadata, dict) else {}
    provider = table_value(metadata_mapping, "model_provider", "modelProvider")
    model = table_value(metadata_mapping, "selected_model", "selectedModel")
    fallback = bool_table_value(
        table_value(metadata_mapping, "model_fallback_used", "modelFallbackUsed")
    )
    provider_fallback = mapping_table_value(
        metadata_mapping,
        "providerFallback",
        "provider_fallback",
    )
    fallback_from = provider_model_summary(
        provider_fallback,
        "from_provider",
        "fromProvider",
        "from_model",
        "fromModel",
    )
    fallback_to = provider_model_summary(
        provider_fallback,
        "to_provider",
        "toProvider",
        "to_model",
        "toModel",
    )
    fallback_reason = table_value(provider_fallback, "reason")
    fallback_latency_ms = table_value(provider_fallback, "latency_ms", "latencyMs")
    fallback_cost_usd = table_value(provider_fallback, "cost_usd", "costUsd")
    token_usage = token_usage_table_mapping(metadata_mapping)
    total_tokens = token_usage_value(token_usage, "total")
    input_tokens = token_usage_value(token_usage, "input")
    output_tokens = token_usage_value(token_usage, "output")
    cached_tokens = token_usage_value(token_usage, "cached")
    reasoning_tokens = token_usage_value(token_usage, "reasoning")
    checkpoint_provenance = mapping_table_value(
        metadata_mapping,
        "checkpointProvenance",
        "checkpoint_provenance",
    )
    graph_store_runtime = mapping_table_value(
        checkpoint_provenance,
        "graphStoreRuntime",
        "graph_store_runtime",
    )
    checkpoint_store = table_value(checkpoint_provenance, "store")
    graph_durable_store = table_value(graph_store_runtime, "durableStore", "durable_store")
    graph_local_store = table_value(graph_store_runtime, "localStore", "local_store")
    middleware_policy = mapping_table_value(metadata_mapping, "langchainMiddlewarePolicy")
    middleware_policy_body = mapping_table_value(middleware_policy, "policy")
    middleware_chain = mapping_table_value(metadata_mapping, "langchainMiddlewareChain")
    middleware_status = table_value(middleware_policy, "status")
    middleware_source = table_value(middleware_policy, "source")
    middleware_model_limit = table_value(middleware_policy_body, "modelCallRunLimit")
    middleware_tool_limit = table_value(middleware_policy_body, "toolCallRunLimit")
    middleware_model_retries = table_value(middleware_policy_body, "modelRetryMaxRetries")
    middleware_tool_retries = table_value(middleware_policy_body, "toolRetryMaxRetries")
    middleware_count = table_value(middleware_chain, "count")
    middleware_names = comma_separated_table_value(middleware_chain, "middleware")
    middleware_pii_count = table_value(middleware_chain, "piiRuleCount")
    middleware_hitl_count = table_value(middleware_chain, "hitlToolCount")
    middleware_model_count = table_value(middleware_chain, "fallbackModelCount")
    structured_output = mapping_table_value(
        metadata_mapping,
        "structuredOutput",
        "structured_output",
    )
    ignored_schema = mapping_table_value(structured_output, "ignoredSchema", "ignored_schema")
    structured_strategy = table_value(structured_output, "strategy")
    structured_status = table_value(structured_output, "status")
    structured_schema_source = table_value(structured_output, "schemaSource", "schema_source")
    structured_citation_policy = table_value(
        structured_output,
        "citationPolicy",
        "citation_policy",
    )
    structured_citation_count = table_value(
        structured_output,
        "citationCount",
        "citation_count",
    )
    structured_allowed_citation_count = sequence_count_table_value(
        table_value(structured_output, "allowedCitationIds", "allowed_citation_ids")
    )
    structured_ignored_reason = table_value(ignored_schema, "reason")
    tool_budget = mapping_table_value(
        metadata_mapping,
        "resolvedToolProfileBudget",
        "resolved_tool_profile_budget",
    )
    tool_budget_source = table_value(tool_budget, "source")
    tool_budget_max = table_value(tool_budget, "maxTools", "max_tools")
    configured_tool_count = table_value(
        tool_budget,
        "configuredToolCount",
        "configured_tool_count",
    )
    active_tool_count = table_value(tool_budget, "activeToolCount", "active_tool_count")
    active_tool_names = comma_separated_table_value(tool_budget, "activeTools", "active_tools")
    dropped_tool_count = table_value(tool_budget, "droppedToolCount", "dropped_tool_count")
    dropped_tool_reasons = dropped_tool_reason_summary(
        table_value(tool_budget, "dropped_tools", "droppedTools")
    )
    dropped_tool_sample = dropped_tool_sample_summary(
        table_value(tool_budget, "dropped_tools", "droppedTools")
    )
    if provider is not None:
        parts.append(f"provider={provider}")
    if model is not None:
        parts.append(f"model={model}")
    if fallback is not None:
        parts.append(f"fallback={fallback}")
    if fallback_from is not None:
        parts.append(f"fallbackFrom={fallback_from}")
    if fallback_to is not None:
        parts.append(f"fallbackTo={fallback_to}")
    if fallback_reason is not None:
        parts.append(f"fallbackReason={fallback_reason}")
    if fallback_latency_ms is not None:
        parts.append(f"fallbackLatencyMs={fallback_latency_ms}")
    if fallback_cost_usd is not None:
        parts.append(f"fallbackCostUsd={fallback_cost_usd}")
    if checkpoint_store is not None:
        parts.append(f"checkpointStore={checkpoint_store}")
    if graph_durable_store is not None:
        parts.append(f"graphDurableStore={graph_durable_store}")
    if graph_local_store is not None:
        parts.append(f"graphLocalStore={graph_local_store}")
    if middleware_status is not None:
        parts.append(f"middleware={middleware_status}")
    if middleware_source is not None:
        parts.append(f"middlewareSource={middleware_source}")
    if middleware_model_limit is not None:
        parts.append(f"middlewareModelLimit={middleware_model_limit}")
    if middleware_tool_limit is not None:
        parts.append(f"middlewareToolLimit={middleware_tool_limit}")
    if middleware_model_retries is not None:
        parts.append(f"middlewareModelRetries={middleware_model_retries}")
    if middleware_tool_retries is not None:
        parts.append(f"middlewareToolRetries={middleware_tool_retries}")
    if middleware_count is not None:
        parts.append(f"middlewareCount={middleware_count}")
    if middleware_pii_count is not None:
        parts.append(f"middlewarePii={middleware_pii_count}")
    if middleware_hitl_count is not None:
        parts.append(f"middlewareHitl={middleware_hitl_count}")
    if middleware_model_count is not None:
        parts.append(f"middlewareModels={middleware_model_count}")
    if middleware_names is not None:
        parts.append(f"middlewareChain={middleware_names.replace(', ', ',')}")
    if structured_strategy is not None:
        parts.append(f"structuredOutput={structured_strategy}")
    if structured_status is not None:
        parts.append(f"structuredStatus={structured_status}")
    if structured_schema_source is not None:
        parts.append(f"structuredSchemaSource={structured_schema_source}")
    if structured_citation_policy is not None:
        parts.append(f"structuredCitationPolicy={structured_citation_policy}")
    if structured_citation_count is not None:
        parts.append(f"structuredCitations={structured_citation_count}")
    if structured_allowed_citation_count is not None:
        parts.append(f"structuredAllowedCitations={structured_allowed_citation_count}")
    if structured_ignored_reason is not None:
        parts.append(f"structuredIgnored={structured_ignored_reason}")
    if tool_budget_source is not None:
        parts.append(f"toolBudgetSource={tool_budget_source}")
    if tool_budget_max is not None:
        parts.append(f"toolBudgetMax={tool_budget_max}")
    if active_tool_count is not None and configured_tool_count is not None:
        parts.append(f"activeTools={active_tool_count}/{configured_tool_count}")
    elif active_tool_count is not None:
        parts.append(f"activeTools={active_tool_count}")
    if dropped_tool_count is not None:
        parts.append(f"droppedTools={dropped_tool_count}")
    if dropped_tool_reasons:
        parts.append(f"dropReasons={dropped_tool_reasons}")
    if dropped_tool_sample:
        parts.append(f"droppedToolSample={dropped_tool_sample}")
    if active_tool_names is not None:
        parts.append(f"activeToolNames={active_tool_names.replace(', ', ',')}")
    if total_tokens is not None:
        parts.append(f"tokens={total_tokens}")
    if input_tokens is not None:
        parts.append(f"input={input_tokens}")
    if output_tokens is not None:
        parts.append(f"output={output_tokens}")
    if cached_tokens is not None:
        parts.append(f"cached={cached_tokens}")
    if reasoning_tokens is not None:
        parts.append(f"reasoning={reasoning_tokens}")
    return " ".join(part for part in parts if part)


def dropped_tool_reason_summary(value: object) -> str:
    if not isinstance(value, list | tuple):
        return ""
    counts: Counter[str] = Counter()
    for item in cast(Sequence[object], value):
        if not isinstance(item, dict):
            continue
        typed_item = cast(dict[object, object], item)
        reason = typed_item.get("reason")
        if isinstance(reason, str) and reason.strip():
            counts[reason.strip()] += 1
    return ",".join(f"{reason}={counts[reason]}" for reason in sorted(counts))


def dropped_tool_sample_summary(value: object) -> str:
    if not isinstance(value, list | tuple):
        return ""
    samples: list[str] = []
    for item in cast(Sequence[object], value):
        if not isinstance(item, dict):
            continue
        typed_item = cast(dict[object, object], item)
        name = first_text(
            typed_item.get("name"),
            typed_item.get("toolName"),
            typed_item.get("tool_name"),
            typed_item.get("id"),
            typed_item.get("toolId"),
            typed_item.get("tool_id"),
        )
        reason = first_text(typed_item.get("reason"))
        if name is None or reason is None:
            continue
        samples.append(f"{name}:{reason}")
    return ",".join(samples)


def failed_tool_summary(tool_invocations: Sequence[object]) -> tuple[int, list[str]]:
    names: list[str] = []
    failed_count = 0
    for item in tool_invocations:
        if not isinstance(item, dict):
            continue
        typed_item = cast(dict[object, object], item)
        if str(typed_item.get("status") or "") != "failed":
            continue
        failed_count += 1
        tool_name = str(typed_item.get("toolId") or typed_item.get("tool_id") or "")
        if tool_name and tool_name not in names:
            names.append(tool_name)
    return failed_count, names


def approval_recovery_summary(tool_invocations: Sequence[object]) -> str:
    approval_ids: set[str] = set()
    risk_levels: set[str] = set()
    idempotency_keys: set[str] = set()
    for item in tool_invocations:
        if not isinstance(item, dict):
            continue
        typed_item = cast(dict[object, object], item)
        string_item = {str(key): value for key, value in typed_item.items()}
        approval_id = first_text(
            typed_item.get("approvalId"),
            typed_item.get("approval_id"),
        )
        if approval_id is None:
            continue
        approval_ids.add(approval_id)
        idempotency_key = first_text(
            typed_item.get("idempotencyKey"),
            typed_item.get("idempotency_key"),
        )
        if idempotency_key is not None:
            idempotency_keys.add(idempotency_key)
        execution = mapping_table_value(string_item, "execution")
        risk_level = first_text(
            typed_item.get("riskLevel"),
            typed_item.get("risk_level"),
            execution.get("riskLevel"),
            execution.get("risk_level"),
        )
        if risk_level is not None:
            risk_levels.add(risk_level)
    if not approval_ids:
        return ""
    parts = [f"pendingApprovals={len(approval_ids)}"]
    parts.append(f"approvalIds={','.join(sorted(approval_ids))}")
    if risk_levels:
        parts.append(f"riskLevels={','.join(sorted(risk_levels))}")
    if idempotency_keys:
        parts.append(f"idempotencyKeys={','.join(sorted(idempotency_keys))}")
    return " ".join(parts)


def metadata_from_json(raw: str) -> dict[str, object]:
    parsed = json.loads(raw or "{}")
    if not isinstance(parsed, dict):
        raise ValueError("--metadata-json must be a JSON object")
    return cast(dict[str, object], parsed)


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
