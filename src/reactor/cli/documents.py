from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from shlex import quote
from typing import Protocol, TextIO, cast
from urllib.parse import urlencode

import httpx

from reactor.api.next_actions import (
    blocked_next_action_ids,
    next_action_states,
    ready_next_action_ids,
)
from reactor.evals.langsmith_dataset import (
    build_langsmith_eval_sync_dry_run_report,
    build_langsmith_eval_sync_dry_run_report_for_suite,
    langsmith_feedback_workflow_review_action,
    langsmith_product_boundary_summary_parts,
)
from reactor.evals.regression_suite_apply import (
    apply_promoted_eval_case,
    langsmith_dry_run_summary,
    promoted_eval_suite_snapshot,
    regression_suite_summary,
    regression_suite_summary_for_suite,
)
from reactor.kernel.citations import is_citation_safe_id
from reactor.rag.ingestion_candidate_actions import (
    RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
    rag_candidate_feedback_bulk_review_action,
)
from reactor.rag.ingestion_candidate_ids import (
    RAG_CANDIDATE_CASE_PREFIX,
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
    release_readiness_command_for_reports,
)
from reactor.release.readiness_contracts import (
    feedback_review_queue_action,
    feedback_review_queue_bulk_review_action,
    feedback_review_queue_candidate_review_action,
    feedback_review_queue_candidate_tag,
    feedback_review_queue_export_action,
    feedback_review_queue_memory_lifecycle_action,
)

DEFAULT_APPLY_DATASET_NAME = "reactor-regression"
VALID_FEEDBACK_RATINGS = frozenset({"thumbs_up", "thumbs_down"})


@dataclass(frozen=True)
class DocumentCliHttpResult:
    ok: bool
    status_code: int
    body: dict[str, object] | list[object] | None = None
    error: str | None = None


class DocumentsHttpProbe(Protocol):
    def get_json(self, path: str, headers: dict[str, str]) -> DocumentCliHttpResult: ...

    def post_json(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> DocumentCliHttpResult: ...

    def delete_json(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> DocumentCliHttpResult: ...


class HttpDocumentsProbe:
    def __init__(self, *, base_url: str, timeout_seconds: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def get_json(self, path: str, headers: dict[str, str]) -> DocumentCliHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.get(f"{self._base_url}{path}", headers=headers)
            return result_from_response(response)
        except httpx.HTTPError as error:
            return DocumentCliHttpResult(ok=False, status_code=0, error=str(error))

    def post_json(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> DocumentCliHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{self._base_url}{path}",
                    headers=headers,
                    json=payload,
                )
            return result_from_response(response)
        except httpx.HTTPError as error:
            return DocumentCliHttpResult(ok=False, status_code=0, error=str(error))

    def delete_json(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> DocumentCliHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.request(
                    "DELETE",
                    f"{self._base_url}{path}",
                    headers=headers,
                    json=payload,
                )
            if response.status_code == 204:
                return DocumentCliHttpResult(ok=True, status_code=204, body={"deleted": True})
            return result_from_response(response)
        except httpx.HTTPError as error:
            return DocumentCliHttpResult(ok=False, status_code=0, error=str(error))


def result_from_response(response: httpx.Response) -> DocumentCliHttpResult:
    if response.status_code >= 400:
        return DocumentCliHttpResult(
            ok=False,
            status_code=response.status_code,
            error=response.text,
        )
    try:
        body = response.json()
    except ValueError:
        return DocumentCliHttpResult(
            ok=False,
            status_code=response.status_code,
            error="invalid_response",
        )
    if not isinstance(body, dict | list):
        return DocumentCliHttpResult(
            ok=False,
            status_code=response.status_code,
            error="invalid_response",
        )
    return DocumentCliHttpResult(
        ok=True,
        status_code=response.status_code,
        body=cast(dict[str, object] | list[object], body),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reactor-documents",
        description="Add and search Reactor RAG documents through the public API.",
    )
    parser.add_argument("--base-url", default="", help="Reactor API base URL")
    parser.add_argument("--tenant-id", default="", help="Tenant id header")
    parser.add_argument("--user-id", default="", help="User id header")
    parser.add_argument("--role", default="", help="Optional Reactor role header")
    parser.add_argument("--token", default="", help="Optional bearer token")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="Add a RAG document")
    add.add_argument("--collection", default="", help="Optional RAG collection")
    content_source = add.add_mutually_exclusive_group(required=True)
    content_source.add_argument("--content", default="", help="Document content")
    content_source.add_argument("--file", default="", help="UTF-8 document file to ingest")
    add.add_argument("--metadata-json", default="{}", help="Optional JSON object metadata")
    add.add_argument("--title", default="", help="Optional document title metadata")
    add.add_argument("--source-uri", default="", help="Optional source URI metadata")
    add.add_argument(
        "--acl-visibility",
        choices=("public", "tenant", "private"),
        default="tenant",
        help="Document ACL visibility",
    )
    add.add_argument("--acl-user", action="append", default=[], help="Allowed user id")
    add.add_argument("--acl-group", action="append", default=[], help="Allowed group id")

    batch = subparsers.add_parser(
        "batch",
        help="Add RAG documents from a JSON manifest or document directory",
    )
    batch.add_argument("--collection", default="", help="Optional RAG collection")
    batch_source = batch.add_mutually_exclusive_group(required=True)
    batch_source.add_argument("--file", default="", help="UTF-8 JSON manifest with documents")
    batch_source.add_argument(
        "--directory", default="", help="Directory of UTF-8 documents to ingest"
    )
    batch.add_argument("--glob", default="*.md", help="Glob used with --directory")
    batch.add_argument(
        "--source-prefix",
        default="",
        help="Optional source URI prefix used with --directory",
    )
    batch.add_argument(
        "--acl-visibility",
        choices=("public", "tenant", "private"),
        default="tenant",
        help="Directory document ACL visibility",
    )
    batch.add_argument("--acl-user", action="append", default=[], help="Allowed user id")
    batch.add_argument("--acl-group", action="append", default=[], help="Allowed group id")

    list_parser = subparsers.add_parser("list", help="List RAG documents")
    list_parser.add_argument("--collection", default="", help="Optional RAG collection")
    list_parser.add_argument("--limit", type=int, default=100, help="Maximum documents")

    search = subparsers.add_parser("search", help="Search RAG documents")
    search.add_argument("--collection", default="", help="Optional RAG collection")
    search.add_argument("--query", required=True, help="Search query")
    search.add_argument("--top-k", type=int, default=5, help="Maximum documents")
    search.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.0,
        help="Minimum similarity score",
    )

    ask = subparsers.add_parser("ask", help="Search RAG documents and ask chat with context")
    ask.add_argument("--collection", default="", help="Optional RAG collection")
    ask.add_argument("--query", required=True, help="Question to answer")
    ask.add_argument("--top-k", type=int, default=5, help="Maximum documents")
    ask.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.0,
        help="Minimum similarity score",
    )
    ask.add_argument("--session-id", default="", help="Optional chat session id")
    ask.add_argument(
        "--require-citation",
        action="store_true",
        help="Fail when the chat answer does not cite any retrieved document id.",
    )
    ask.add_argument("--eval-case-id", default="", help="Optional eval case id to export")
    ask.add_argument("--eval-case-file", default="", help="Optional eval case JSON output path")
    ask.add_argument(
        "--eval-run-file", default="", help="Optional eval run fixture JSON output path"
    )
    ask.add_argument(
        "--feedback-id",
        action="append",
        default=[],
        help="Feedback id that motivated the exported eval case",
    )
    ask.add_argument(
        "--feedback-rating",
        action="append",
        default=[],
        help="Feedback rating that motivated the exported eval case",
    )
    ask.add_argument(
        "--feedback-source",
        action="append",
        default=[],
        help="Feedback source that motivated the exported eval case",
    )
    ask.add_argument(
        "--feedback-tag",
        action="append",
        default=[],
        help="Workflow tag that should route feedback review for the exported eval case",
    )
    ask.add_argument(
        "--apply-suite-file",
        default="",
        help="Optional regression suite JSON path to apply exported eval files to",
    )
    ask.add_argument(
        "--apply-dataset-name",
        default=DEFAULT_APPLY_DATASET_NAME,
        help="Dataset name used while validating applied eval files",
    )
    ask.add_argument(
        "--apply-replace",
        action="store_true",
        help="Replace existing case/run ids while applying to a suite",
    )
    ask.add_argument(
        "--apply-dry-run",
        action="store_true",
        help="Validate suite application without writing the suite",
    )
    ask.add_argument(
        "--apply-require-source-run-id",
        action="store_true",
        default=True,
        help="Require exported eval cases to preserve sourceRunId during suite application.",
    )
    ask.add_argument(
        "--apply-require-run-file",
        action="store_true",
        help="Reject suite application unless --eval-run-file is supplied",
    )
    ask.add_argument(
        "--apply-require-context-diagnostics",
        action="store_true",
        help="Reject suite application unless the eval run fixture has context diagnostics",
    )
    ask.add_argument(
        "--apply-suite-summary",
        action="store_true",
        help="Include source-controlled suite coverage summary after apply.",
    )
    ask.add_argument(
        "--langsmith-dry-run-report-file",
        default="",
        help="Optional LangSmith eval sync dry-run report output path after suite apply",
    )
    ask.add_argument(
        "--output",
        choices=("json", "summary"),
        default="json",
        help="Output format",
    )
    ask.add_argument(
        "--failure-output",
        choices=("text", "json"),
        default="text",
        help="Output format for recoverable ask failures",
    )

    delete = subparsers.add_parser("delete", help="Delete RAG documents")
    delete.add_argument("--collection", default="", help="Optional RAG collection")
    delete.add_argument("--id", action="append", required=True, help="Document id to delete")

    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    http_probe: DocumentsHttpProbe | None = None,
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
    probe = http_probe or HttpDocumentsProbe(base_url=base_url, timeout_seconds=args.timeout)
    headers = request_headers(args, environ, tenant_id=tenant_id, user_id=user_id)

    validation_error = validate_command_args(args)
    if validation_error:
        stderr.write(f"{validation_error}\n")
        return 2

    result = dispatch_command(args, probe, headers)
    if not result.ok:
        if (
            args.command == "ask"
            and getattr(args, "failure_output", "text") == "json"
            and isinstance(result.body, Mapping)
        ):
            stdout.write(json.dumps(result.body, sort_keys=True, separators=(",", ":")) + "\n")
            return 1
        stderr.write(f"reactor-documents request failed ({result.status_code}): {result.error}\n")
        return 1

    output_body: dict[str, object] | list[object] | None = result.body
    output_body = enrich_success_output_body(args, output_body)
    if args.command == "ask" and args.apply_suite_file:
        if not args.eval_case_file:
            stderr.write("reactor-documents suite apply requires --eval-case-file\n")
            return 2
        try:
            suite_apply = apply_promoted_eval_case(
                suite_file=Path(args.apply_suite_file),
                case_file=Path(args.eval_case_file),
                run_file=Path(args.eval_run_file) if args.eval_run_file else None,
                dataset_name=args.apply_dataset_name,
                replace=bool(args.apply_replace),
                dry_run=bool(args.apply_dry_run),
                require_source_run_id=bool(args.apply_require_source_run_id),
                require_run_file=bool(args.apply_require_run_file),
                require_context_diagnostics=bool(args.apply_require_context_diagnostics),
            )
        except ValueError as error:
            stderr.write(f"reactor-documents suite apply failed: {error}\n")
            return 1
        suite_apply["persistCommand"] = eval_artifacts_apply_command(
            case_file=str(args.eval_case_file) if args.eval_case_file else None,
            run_file=str(args.eval_run_file) if args.eval_run_file else None,
            dataset_name=str(args.apply_dataset_name) if args.apply_dataset_name else None,
            suite_file=str(args.apply_suite_file) if args.apply_suite_file else None,
            langsmith_report_file=(
                str(args.langsmith_dry_run_report_file)
                if args.langsmith_dry_run_report_file
                else None
            ),
            dry_run=False,
        )
        if args.langsmith_dry_run_report_file:
            langsmith_report_file = Path(args.langsmith_dry_run_report_file)
            apply_suite_file = Path(args.apply_suite_file)
            if args.apply_dry_run:
                langsmith_report = build_langsmith_eval_sync_dry_run_report_for_suite(
                    suite=promoted_eval_suite_snapshot(
                        suite_file=apply_suite_file,
                        case_file=Path(args.eval_case_file),
                        run_file=Path(args.eval_run_file) if args.eval_run_file else None,
                        replace=bool(args.apply_replace),
                    ),
                    suite_file=apply_suite_file,
                    dataset_name=args.apply_dataset_name,
                    report_file=langsmith_report_file,
                )
            else:
                langsmith_report = build_langsmith_eval_sync_dry_run_report(
                    suite_file=apply_suite_file,
                    dataset_name=args.apply_dataset_name,
                    report_file=langsmith_report_file,
                )
            langsmith_report_file.parent.mkdir(parents=True, exist_ok=True)
            langsmith_report_file.write_text(
                json.dumps(langsmith_report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            suite_apply["langsmithDryRun"] = langsmith_dry_run_summary(
                langsmith_report,
                report_file=langsmith_report_file,
                case_file=Path(args.eval_case_file) if args.eval_case_file else None,
                run_file=Path(args.eval_run_file) if args.eval_run_file else None,
                persist_command=eval_artifacts_apply_command(
                    case_file=str(args.eval_case_file) if args.eval_case_file else None,
                    run_file=str(args.eval_run_file) if args.eval_run_file else None,
                    dataset_name=(
                        str(args.apply_dataset_name) if args.apply_dataset_name else None
                    ),
                    suite_file=str(args.apply_suite_file) if args.apply_suite_file else None,
                    langsmith_report_file=(
                        str(args.langsmith_dry_run_report_file)
                        if args.langsmith_dry_run_report_file
                        else None
                    ),
                    dry_run=False,
                ),
                summary_command=eval_artifacts_summary_command(
                    dataset_name=(
                        str(args.apply_dataset_name) if args.apply_dataset_name else None
                    ),
                    suite_file=str(args.apply_suite_file) if args.apply_suite_file else None,
                    langsmith_report_file=(
                        str(args.langsmith_dry_run_report_file)
                        if args.langsmith_dry_run_report_file
                        else None
                    ),
                ),
            )
        output_body = {"chat": result.body, "suiteApply": suite_apply}
        if args.apply_suite_summary:
            apply_suite_file = Path(args.apply_suite_file)
            if args.apply_dry_run:
                output_body["suiteSummary"] = regression_suite_summary_for_suite(
                    suite=promoted_eval_suite_snapshot(
                        suite_file=apply_suite_file,
                        case_file=Path(args.eval_case_file),
                        run_file=Path(args.eval_run_file) if args.eval_run_file else None,
                        replace=bool(args.apply_replace),
                    ),
                    suite_file=apply_suite_file,
                )
            else:
                output_body["suiteSummary"] = regression_suite_summary(apply_suite_file)

    if getattr(args, "output", "json") == "summary":
        stdout.write(format_ask_summary(summary_output_body(args, output_body)))
    else:
        stdout.write(json.dumps(output_body, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


def enrich_success_output_body(
    args: argparse.Namespace,
    output_body: dict[str, object] | list[object] | None,
) -> dict[str, object] | list[object] | None:
    if args.command == "add":
        return enrich_add_output_body(args, output_body)
    if args.command == "batch":
        return enrich_batch_output_body(args, output_body)
    return output_body


def enrich_add_output_body(
    args: argparse.Namespace,
    output_body: dict[str, object] | list[object] | None,
) -> dict[str, object] | list[object] | None:
    if not isinstance(output_body, Mapping):
        return output_body
    mapping = dict(cast(Mapping[str, object], output_body))
    mapping["nextActions"] = document_add_next_actions(args, mapping)
    return mapping


def document_add_next_actions(
    args: argparse.Namespace,
    body: Mapping[str, object],
) -> list[dict[str, object]]:
    collection = str(args.collection or "").strip() or "default"
    document_id = optional_text(body.get("id")) or ""
    base_metadata: dict[str, object] = {"collection": collection}
    if document_id:
        base_metadata["documentId"] = document_id
    return document_ingest_next_actions(collection=collection, metadata=base_metadata)


def enrich_batch_output_body(
    args: argparse.Namespace,
    output_body: dict[str, object] | list[object] | None,
) -> dict[str, object] | list[object] | None:
    if not isinstance(output_body, Mapping):
        return output_body
    mapping = dict(cast(Mapping[str, object], output_body))
    mapping["nextActions"] = document_batch_next_actions(args, mapping)
    return mapping


def document_batch_next_actions(
    args: argparse.Namespace,
    body: Mapping[str, object],
) -> list[dict[str, object]]:
    collection = str(args.collection or "").strip() or "default"
    document_ids = string_list_value(body.get("ids"))
    base_metadata: dict[str, object] = {"collection": collection}
    if document_ids:
        base_metadata["documentIds"] = document_ids
    return document_ingest_next_actions(collection=collection, metadata=base_metadata)


def document_ingest_next_actions(
    *,
    collection: str,
    metadata: Mapping[str, object],
) -> list[dict[str, object]]:
    base_metadata = dict(metadata)
    return [
        {
            "id": "search-documents",
            "label": "Search the collection after ingest",
            "command": (
                "reactor-documents search "
                f"--collection {quote(collection)} --query <question> --top-k 5 --output table"
            ),
            **base_metadata,
        },
        {
            "id": "ask-with-citation",
            "label": "Ask with citation enforcement after ingest",
            "command": (
                "reactor-documents ask "
                f"--collection {quote(collection)} --query <question> "
                "--require-citation --failure-output json --output summary"
            ),
            **base_metadata,
            "requireCitation": True,
        },
    ]


def validate_command_args(args: argparse.Namespace) -> str:
    if args.command == "ask":
        return validate_ask_args(args)
    return ""


def validate_ask_args(args: argparse.Namespace) -> str:
    reserved_feedback_tag_error = validate_feedback_workflow_tags(args)
    if reserved_feedback_tag_error:
        return reserved_feedback_tag_error
    feedback_contract_error = validate_feedback_contract(args)
    if feedback_contract_error:
        return feedback_contract_error
    if not ask_targets_rag_candidate_eval(args):
        return ""
    eval_case_id = str(args.eval_case_id or "")
    candidate_case_id_error = validate_rag_candidate_case_id(eval_case_id)
    if not candidate_case_id_error:
        return ""
    return candidate_case_id_error


def validate_rag_candidate_case_id(eval_case_id: str) -> str:
    if not eval_case_id.startswith(RAG_CANDIDATE_CASE_PREFIX):
        return "RAG ingestion candidate documents ask requires --eval-case-id case_rag_candidate_*"
    candidate_slug = rag_candidate_slug_from_case_id(eval_case_id)
    if candidate_slug is None and not eval_case_id.removeprefix(RAG_CANDIDATE_CASE_PREFIX).strip():
        return "RAG ingestion candidate documents ask requires --eval-case-id case_rag_candidate_*"
    if candidate_slug is None:
        return "RAG ingestion candidate documents ask requires slugged --eval-case-id"
    return ""


def validate_feedback_contract(args: argparse.Namespace) -> str:
    feedback_ids = clean_string_values(getattr(args, "feedback_id", ()))
    feedback_ratings = clean_string_values(getattr(args, "feedback_rating", ()))
    if feedback_ids and not feedback_ratings:
        return "documents ask feedback-id requires --feedback-rating"
    if feedback_ids and len(feedback_ids) != len(feedback_ratings):
        return "documents ask feedback-id count must match --feedback-rating count"
    if any(command_slug(feedback_id) != feedback_id for feedback_id in feedback_ids):
        return "documents ask feedback-id must be command-safe"
    if any(rating not in VALID_FEEDBACK_RATINGS for rating in feedback_ratings):
        return "documents ask feedback-rating must be thumbs_up or thumbs_down"
    return ""


def validate_feedback_workflow_tags(args: argparse.Namespace) -> str:
    reserved_prefixes = ("feedback:", "feedback-rating:", "feedback-source:")
    reserved_values = {"exported-from-cli", "regression"}
    for tag in clean_string_values(getattr(args, "feedback_tag", ())):
        for prefix in reserved_prefixes:
            if tag.startswith(prefix):
                return f"documents ask feedback workflow tags cannot use reserved prefix: {prefix}"
        if tag in reserved_values:
            return f"documents ask feedback workflow tag is reserved: {tag}"
    return ""


def ask_targets_rag_candidate_eval(args: argparse.Namespace) -> bool:
    if str(getattr(args, "collection", "") or "").strip() == "rag-ingestion-candidate":
        return True
    if not getattr(args, "apply_suite_file", ""):
        return False
    suite_file = str(getattr(args, "apply_suite_file", "") or "")
    dataset_name = str(getattr(args, "apply_dataset_name", "") or "")
    return (
        dataset_name == "reactor-rag-ingestion-candidate" or "rag-ingestion-candidate" in suite_file
    )


def summary_output_body(
    args: argparse.Namespace,
    output_body: dict[str, object] | list[object] | None,
) -> dict[str, object] | list[object] | None:
    if args.command != "ask":
        return output_body
    artifacts = eval_artifact_summary(args)
    if not artifacts:
        return output_body
    artifacts = enrich_eval_artifact_summary_from_output(artifacts, output_body)
    if isinstance(output_body, Mapping) and "chat" in output_body:
        return {**cast(Mapping[str, object], output_body), "evalArtifacts": artifacts}
    return {"chat": output_body, "evalArtifacts": artifacts}


def enrich_eval_artifact_summary_from_output(
    artifacts: dict[str, object],
    output_body: object,
) -> dict[str, object]:
    if not eval_artifacts_has_handoff_intent(artifacts):
        return artifacts
    expected_tags = expected_citation_tags_from_output(output_body)
    if not expected_tags:
        return artifacts
    current_tags = string_list_value(artifacts.get("feedbackTags"))
    return {**artifacts, "feedbackTags": list(dict.fromkeys([*current_tags, *expected_tags]))}


def eval_artifacts_has_handoff_intent(artifacts: Mapping[str, object]) -> bool:
    return any(
        key in artifacts
        for key in (
            "caseId",
            "caseFile",
            "runFile",
            "datasetName",
            "applySuiteFile",
            "langsmithDryRunReportFile",
            "feedbackIds",
            "feedbackRatings",
            "feedbackTags",
        )
    )


def expected_citation_tags_from_output(output_body: object) -> list[str]:
    body: object = output_body
    if isinstance(output_body, Mapping):
        chat_body: object = cast(Mapping[str, object], output_body).get("chat")
        if isinstance(chat_body, Mapping):
            body = cast(Mapping[str, object], chat_body)
    if not isinstance(body, Mapping):
        return []
    mapping = cast(Mapping[str, object], body)
    answer = optional_text(mapping.get("content")) or ""
    retrieved_documents = mapping.get("retrievedDocuments")
    if not isinstance(retrieved_documents, Sequence) or isinstance(
        retrieved_documents, str | bytes
    ):
        return []
    labels = [
        label
        for item in cast(Sequence[object], retrieved_documents)
        if isinstance(item, Mapping)
        and (label := optional_text(cast(Mapping[str, object], item).get("id")))
        and label in set(answer_citations(answer))
    ]
    return [
        f"expected-citation:{label}"
        for label in labels
        if label != "unknown" and is_citation_safe_id(label)
    ]


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
    probe: DocumentsHttpProbe,
    headers: dict[str, str],
) -> DocumentCliHttpResult:
    if args.command == "add":
        payload: dict[str, object] = {
            "content": document_content_from_args(args),
            "metadata": document_metadata_from_args(args),
            "acl": {
                "visibility": args.acl_visibility,
                "users": list(args.acl_user),
                "groups": list(args.acl_group),
            },
        }
        return probe.post_json(document_path("/v1/documents", args.collection), headers, payload)
    if args.command == "batch":
        payload = (
            batch_payload_from_directory(args)
            if args.directory
            else batch_payload_from_file(args.file)
        )
        return probe.post_json(
            document_path("/v1/documents/batch", args.collection),
            headers,
            payload,
        )
    if args.command == "list":
        return probe.get_json(
            document_path("/v1/documents", args.collection, {"limit": args.limit}),
            headers,
        )
    if args.command == "search":
        payload: dict[str, object] = {
            "query": args.query,
            "topK": args.top_k,
            "similarityThreshold": args.similarity_threshold,
        }
        return probe.post_json(
            document_path("/v1/documents/search", args.collection),
            headers,
            payload,
        )
    if args.command == "ask":
        return ask_with_documents(args, probe=probe, headers=headers)
    if args.command == "delete":
        return probe.delete_json(
            document_path("/v1/documents", args.collection),
            headers,
            {"ids": list(args.id)},
        )
    raise AssertionError(f"unsupported command: {args.command}")


def ask_with_documents(
    args: argparse.Namespace,
    *,
    probe: DocumentsHttpProbe,
    headers: dict[str, str],
) -> DocumentCliHttpResult:
    search_result = probe.post_json(
        document_path("/v1/documents/search", args.collection),
        headers,
        {
            "query": args.query,
            "topK": args.top_k,
            "similarityThreshold": args.similarity_threshold,
        },
    )
    if not search_result.ok:
        return search_result
    if not isinstance(search_result.body, list):
        return DocumentCliHttpResult(
            ok=False,
            status_code=search_result.status_code,
            error="invalid_search_response",
        )
    if not search_result.body:
        failure = no_documents_found_failure(args)
        return DocumentCliHttpResult(
            ok=False,
            status_code=404,
            body=failure,
            error=no_documents_found_error(args),
        )
    if should_require_citation(args) and not has_stable_citation_labels(search_result.body):
        return DocumentCliHttpResult(
            ok=False,
            status_code=422,
            body=missing_citation_labels_failure(args),
            error="retrieved documents do not expose stable citation labels",
        )
    chat_result = probe.post_json(
        "/v1/chat",
        headers,
        {
            "message": ask_message(args.query, search_result.body),
            "metadata": ask_chat_metadata(args),
        },
    )
    if chat_result.ok and should_require_citation(args):
        citation_failure = required_citation_failure(
            search_result.body,
            chat_result.body,
            query=args.query,
            collection=args.collection,
            case_id=args.eval_case_id,
            case_file=args.eval_case_file,
            run_file=args.eval_run_file,
            apply_suite_file=args.apply_suite_file,
            apply_dataset_name=args.apply_dataset_name,
            feedback_workflow_tags=args.feedback_tag,
        )
        if citation_failure is not None:
            return DocumentCliHttpResult(
                ok=False,
                status_code=422,
                body=citation_failure,
                error=format_missing_citation_failure(citation_failure),
            )
    if chat_result.ok:
        write_ask_eval_files(args, search_result.body, chat_result.body)
        return DocumentCliHttpResult(
            ok=True,
            status_code=chat_result.status_code,
            body=ask_result_body(args, search_result.body, chat_result.body),
        )
    return chat_result


def no_documents_found_error(args: argparse.Namespace) -> str:
    failure = no_documents_found_failure(args)
    collection = str(failure["collection"])
    quoted_query = quote(str(failure["query"]))
    actions = {
        str(action["id"]): action
        for action in cast(Sequence[Mapping[str, object]], failure["nextActions"])
    }
    search_action = str(actions["search-documents"]["command"])
    ingest_action = str(actions["ingest-document"]["command"])
    retry_action = str(actions["retry-ask"]["command"])
    return (
        f"no_documents_found; collection={collection}; query={quoted_query}; "
        f"searchAction={search_action}; ingestAction={ingest_action}; "
        f"retryAction={retry_action}"
    )


def no_documents_found_failure(args: argparse.Namespace) -> dict[str, object]:
    collection = str(args.collection or "").strip() or "default"
    query = str(args.query)
    search_action = (
        "reactor-documents search "
        f"--collection {quote(collection)} --query {quote(query)} "
        f"--top-k {int(args.top_k)} --output table"
    )
    ingest_action = (
        "reactor-documents add "
        f"--collection {quote(collection)} --file <path> --title <title> "
        "--source-uri <uri> --acl-visibility tenant"
    )
    retry_action = documents_ask_retry_action(
        collection=collection,
        query=query,
        top_k=int(args.top_k),
        require_citation=False,
    )
    return {
        "error": "no_documents_found",
        "message": "no documents found for query",
        "collection": collection,
        "query": query,
        "topK": int(args.top_k),
        "nextActions": [
            {
                "id": "search-documents",
                "label": "Inspect the empty RAG search",
                "command": search_action,
                "collection": collection,
                "query": query,
                "topK": int(args.top_k),
            },
            {
                "id": "ingest-document",
                "label": "Ingest a document into the collection",
                "command": ingest_action,
                "collection": collection,
                "aclVisibility": "tenant",
            },
            {
                "id": "retry-ask",
                "label": "Retry the documents ask after ingest",
                "command": retry_action,
                "collection": collection,
                "query": query,
                "topK": int(args.top_k),
            },
        ],
    }


def documents_ask_retry_action(
    *,
    collection: str,
    query: str,
    top_k: int,
    require_citation: bool,
) -> str:
    citation_arg = " --require-citation" if require_citation else ""
    return (
        "reactor-documents ask "
        f"--collection {quote(collection)} --query {quote(query)} "
        f"--top-k {top_k}{citation_arg} --failure-output json"
    )


def ask_message(query: str, documents: Sequence[object]) -> str:
    lines = [
        "Answer the question using only the retrieved Reactor documents. "
        "Cite only the citation label shown at the start of each retrieved document header.",
        "",
        f"Question: {query}",
        "",
        "Retrieved documents:",
    ]
    lines.extend(format_retrieved_document(document) for document in documents)
    return "\n".join(lines)


def ask_chat_metadata(args: argparse.Namespace) -> dict[str, object]:
    metadata: dict[str, object] = {
        "sessionId": args.session_id or f"documents-ask:{args.collection or 'default'}",
    }
    if not ask_targets_rag_candidate_eval(args):
        return metadata
    eval_case_id = str(getattr(args, "eval_case_id", "") or "").strip()
    candidate_slug = rag_candidate_slug_from_case_id(eval_case_id)
    if candidate_slug is None:
        return metadata
    metadata["candidate_id"] = candidate_slug
    metadata["evalCaseId"] = eval_case_id
    collection = str(getattr(args, "collection", "") or "")
    workflow_tags = [
        *collection_tags(collection),
        *clean_string_values(getattr(args, "feedback_tag", ())),
        "rag",
        rag_candidate_workflow_tag(candidate_slug),
    ]
    workflow_tags = list(dict.fromkeys(workflow_tags))
    artifact_workflow_tags = eval_artifact_feedback_workflow_tags(
        collection=collection,
        case_id=eval_case_id,
        feedback_workflow_tags=getattr(args, "feedback_tag", ()),
    )
    workflow_tags = list(dict.fromkeys([*workflow_tags, *artifact_workflow_tags]))
    if workflow_tags:
        metadata["workflowTags"] = workflow_tags
    return metadata


def format_retrieved_document(document: object) -> str:
    if not isinstance(document, Mapping):
        return "[unknown] "
    document_mapping = cast(Mapping[str, object], document)
    metadata = document_mapping.get("metadata")
    metadata_mapping: Mapping[str, object]
    if isinstance(metadata, Mapping):
        metadata_mapping = cast(Mapping[str, object], metadata)
    else:
        metadata_mapping = {}
    content = document_mapping.get("content")
    safe_id = document_citation_label(document_mapping)
    safe_content = content if isinstance(content, str) else ""
    details: list[str] = []
    title = metadata_mapping.get("title")
    if isinstance(title, str) and title.strip():
        details.append(f"title={prompt_metadata_value(title)}")
    source = (
        metadata_mapping.get("source")
        or metadata_mapping.get("sourceUri")
        or metadata_mapping.get("source_uri")
    )
    if isinstance(source, str) and source.strip():
        details.append(f"source={prompt_metadata_value(source)}")
    quoted_content = quote_retrieved_content(safe_content)
    if details:
        return f"[{safe_id}] {' '.join(details)}\ncontent:\n{quoted_content}"
    return f"[{safe_id}]\ncontent:\n{quoted_content}"


def prompt_metadata_value(value: str) -> str:
    collapsed = " ".join(value.split())
    return collapsed.replace("[", "").replace("]", "")


def quote_retrieved_content(content: str) -> str:
    lines = content.splitlines() or [""]
    return "\n".join(f"> {line}" for line in lines)


def required_citation_error(
    documents: Sequence[object],
    chat_body: dict[str, object] | list[object] | None,
    *,
    query: str = "",
    collection: str = "",
    case_id: str = "",
    case_file: str = "",
    run_file: str = "",
    apply_suite_file: str = "",
    apply_dataset_name: str = "",
    feedback_workflow_tags: Sequence[str] = (),
) -> str | None:
    failure = required_citation_failure(
        documents,
        chat_body,
        query=query,
        collection=collection,
        case_id=case_id,
        case_file=case_file,
        run_file=run_file,
        apply_suite_file=apply_suite_file,
        apply_dataset_name=apply_dataset_name,
        feedback_workflow_tags=feedback_workflow_tags,
    )
    if failure is None:
        return None
    return format_missing_citation_failure(failure)


def required_citation_failure(
    documents: Sequence[object],
    chat_body: dict[str, object] | list[object] | None,
    *,
    query: str = "",
    collection: str = "",
    case_id: str = "",
    case_file: str = "",
    run_file: str = "",
    apply_suite_file: str = "",
    apply_dataset_name: str = "",
    feedback_workflow_tags: Sequence[str] = (),
) -> dict[str, object] | None:
    if not isinstance(chat_body, Mapping):
        return {
            "error": "missing_required_citation",
            "message": "missing required citation",
            "nextActions": [],
        }
    typed_chat_body = cast(Mapping[str, object], chat_body)
    answer = optional_text(typed_chat_body.get("content")) or ""
    labels = citation_labels(documents)
    citations = set(answer_citations(answer))
    if not any(label in citations for label in labels):
        return missing_citation_failure(
            labels[0],
            summary_run_id(typed_chat_body),
            query=query,
            answer=answer,
            collection=collection,
            case_id=case_id,
            case_file=case_file,
            run_file=run_file,
            apply_suite_file=apply_suite_file,
            apply_dataset_name=apply_dataset_name,
            feedback_workflow_tags=feedback_workflow_tags,
        )
    return None


def missing_citation_failure(
    label: str,
    run_id: str,
    *,
    query: str = "",
    answer: str = "",
    collection: str = "",
    case_id: str = "",
    case_file: str = "",
    run_file: str = "",
    apply_suite_file: str = "",
    apply_dataset_name: str = "",
    feedback_workflow_tags: Sequence[str] = (),
) -> dict[str, object]:
    if not run_id:
        return {
            "error": "missing_required_citation",
            "message": f"missing required citation: {label}",
            "citationLabel": label,
            "nextActions": [],
        }
    quoted_run_id = quote(run_id)
    resolved_case_id = case_id.strip() or f"case_missing_citation_{command_slug(run_id)}"
    resolved_case_file = case_file.strip() or "promoted-case.json"
    resolved_run_file = run_file.strip() or "promoted-run.json"
    eval_handoff = missing_citation_eval_handoff(
        collection,
        case_id=resolved_case_id,
        suite_file=apply_suite_file,
        dataset_name=apply_dataset_name,
    )
    workflow_tags = candidate_missing_citation_workflow_tags(
        collection=collection,
        case_id=resolved_case_id,
        suite_file=apply_suite_file,
        dataset_name=apply_dataset_name,
        feedback_workflow_tags=feedback_workflow_tags,
    )
    feedback_tags = [
        "rag",
        "documents-ask",
        "exported-from-cli",
        *workflow_tags,
        "citation-failure",
        f"expected-citation:{label}",
    ]
    promote_workflow_tags = [
        "rag",
        "documents-ask",
        "exported-from-cli",
        *workflow_tags,
        "citation-failure",
        "feedback-rating:thumbs_down",
        "feedback-source:documents_ask",
    ]
    tag_args = " ".join(f"--tag {quote(tag)}" for tag in promote_workflow_tags)
    feedback_tag_args = " ".join(f"--tag {quote(tag)}" for tag in feedback_tags)
    diagnose_command = f"reactor-runs diagnose {quoted_run_id} --output table"
    feedback_command = (
        "reactor-admin feedback-submit --rating thumbs_down "
        f"--run-id {quoted_run_id} --source documents_ask "
        f"--query {quote(query)} --response {quote(answer)} "
        f"--comment {quote(f'Missing required citation: [{label}]')} "
        f"{feedback_tag_args} --output table"
    )
    promote_command = (
        "reactor-runs promote-eval "
        f"{quoted_run_id} --case-id {quote(resolved_case_id)} "
        f"--case-file {quote(resolved_case_file)} --run-file {quote(resolved_run_file)} "
        f"{tag_args} "
        "--feedback-source documents_ask "
        f"--expected-answer {quote(f'[{label}]')} "
        f"--apply-suite-file {quote(eval_handoff['suite_file'])} "
        f"{eval_handoff['dataset_arg']}"
        f"{missing_citation_apply_dry_run_arg(eval_handoff)}"
        "--apply-require-source-run-id --apply-require-run-file "
        "--apply-require-context-diagnostics "
        "--apply-suite-summary "
        f"--langsmith-dry-run-report-file {quote(eval_handoff['report_file'])} "
        "--output table"
    )
    sync_command_base = missing_citation_sync_action(eval_handoff)
    sync_command = f"{sync_command_base} --output table"
    preflight_command = f"{sync_command_base} --preflight-only --output table"
    hardening_command = missing_citation_hardening_command(eval_handoff)
    readiness_command = missing_citation_readiness_action(eval_handoff)
    bulk_review_command = missing_citation_bulk_review_action(workflow_tags)
    next_actions: list[dict[str, object]] = [
        {
            "id": "diagnose-run",
            "label": "Diagnose source run",
            "command": diagnose_command,
            "runId": run_id,
            "sourceRunId": run_id,
        },
        {
            "id": "submit-feedback",
            "label": "Submit feedback for the missing citation",
            "command": feedback_command,
            "runId": run_id,
            "sourceRunId": run_id,
            "rating": "thumbs_down",
            "source": "documents_ask",
            "expectedCitation": f"[{label}]",
            "tags": feedback_tags,
        },
        {
            "id": "promote-eval",
            "label": "Promote missing citation to eval",
            "command": promote_command,
            "runId": run_id,
            "sourceRunId": run_id,
            "caseId": resolved_case_id,
            "evalCaseId": resolved_case_id,
            "caseFile": resolved_case_file,
            "runFile": resolved_run_file,
            "suiteFile": eval_handoff["suite_file"],
            "expectedAnswer": f"[{label}]",
            "source": "documents_ask",
            "rating": "thumbs_down",
            "workflowTags": promote_workflow_tags,
        },
        {
            "id": "preflight-langsmith",
            "label": "Preflight LangSmith eval sync credentials",
            "command": preflight_command,
            "sourceRunId": run_id,
            "evalCaseId": resolved_case_id,
            "reportFile": eval_handoff["report_file"],
            "datasetName": eval_handoff["dataset_name"],
            "preflightFile": RELEASE_SMOKE_PREFLIGHT_FILE,
            "preflightEnvTemplate": RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
            "releaseReadinessFile": RELEASE_READINESS_FILE,
            "releaseReadinessCommand": readiness_command,
            "remediationCommand": preflight_command,
            "readinessReportArg": readiness_report_args_for_reports(
                required_reports=missing_citation_required_readiness_reports(eval_handoff),
                report_files=missing_citation_readiness_reports(eval_handoff),
            ),
            "requiredReadinessReports": missing_citation_required_readiness_reports(eval_handoff),
            "readinessReports": missing_citation_readiness_reports(eval_handoff),
            "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
            "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
            "dependsOnActionIds": ["promote-eval"],
        },
        {
            "id": "sync-langsmith",
            "label": "Sync eval case to LangSmith",
            "command": sync_command,
            "sourceRunId": run_id,
            "evalCaseId": resolved_case_id,
            "reportFile": eval_handoff["report_file"],
            "datasetName": eval_handoff["dataset_name"],
            "preflightFile": RELEASE_SMOKE_PREFLIGHT_FILE,
            "preflightEnvTemplate": RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
            "releaseReadinessFile": RELEASE_READINESS_FILE,
            "releaseReadinessCommand": readiness_command,
            "remediationCommand": sync_command,
            "readinessReportArg": readiness_report_args_for_reports(
                required_reports=missing_citation_required_readiness_reports(eval_handoff),
                report_files=missing_citation_readiness_reports(eval_handoff),
            ),
            "requiredReadinessReports": missing_citation_required_readiness_reports(eval_handoff),
            "readinessReports": missing_citation_readiness_reports(eval_handoff),
            "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
            "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
            "dependsOnActionIds": ["preflight-langsmith"],
        },
    ]
    if bulk_review_command:
        next_actions.append(
            {
                "id": "bulk-review-feedback-queue",
                "label": "Close candidate feedback queue after eval and LangSmith review",
                "command": bulk_review_command,
                "sourceRunId": run_id,
                "evalCaseId": resolved_case_id,
                "candidateTag": missing_citation_candidate_tag(workflow_tags),
                "dependsOnActionIds": ["refresh-readiness"],
            }
        )
    if hardening_command:
        next_actions.append(
            {
                "id": "refresh-rag-hardening",
                "label": "Refresh RAG hardening evidence",
                "command": hardening_command,
                "sourceRunId": run_id,
                "dependsOnActionIds": ["promote-eval"],
            }
        )
    readiness_dependencies = ["sync-langsmith"]
    if hardening_command:
        readiness_dependencies.append("refresh-rag-hardening")
    next_actions.append(
        {
            "id": "refresh-readiness",
            "label": "Refresh release readiness",
            "command": readiness_command,
            "sourceRunId": run_id,
            "evalCaseId": resolved_case_id,
            "requiredReadinessReports": missing_citation_required_readiness_reports(eval_handoff),
            "readinessReports": missing_citation_readiness_reports(eval_handoff),
            "reportFile": eval_handoff["report_file"],
            "dependsOnActionIds": readiness_dependencies,
        }
    )
    failure: dict[str, object] = {
        "error": "missing_required_citation",
        "message": f"missing required citation: {label}",
        "citationLabel": label,
        "runId": run_id,
        "query": query,
        "collection": collection.strip() or "default",
        "nextActions": next_actions,
    }
    failure.update(next_action_state_fields(next_actions))
    return failure


def format_missing_citation_failure(failure: Mapping[str, object]) -> str:
    message = optional_text(failure.get("message")) or "missing required citation"
    actions: dict[str, Mapping[str, object]] = {}
    for action in cast(Sequence[object], failure.get("nextActions", [])):
        if not isinstance(action, Mapping):
            continue
        action_mapping = cast(Mapping[str, object], action)
        action_id = optional_text(action_mapping.get("id"))
        if action_id:
            actions[action_id] = action_mapping
    if not actions:
        return message
    parts = [
        message,
    ]
    ready_ids = string_list_value(failure.get("readyNextActionIds"))
    if ready_ids:
        parts.append(f"readyNextActionIds={','.join(ready_ids)}")
    blocked_ids = string_list_value(failure.get("blockedNextActionIds"))
    if blocked_ids:
        parts.append(f"blockedNextActionIds={','.join(blocked_ids)}")
    states = failure.get("nextActionStates")
    if isinstance(states, Mapping):
        state_parts = [
            f"{action_id.strip()}={state.strip()}"
            for action_id, state in cast(Mapping[object, object], states).items()
            if isinstance(action_id, str)
            and action_id.strip()
            and isinstance(state, str)
            and state.strip()
        ]
        if state_parts:
            parts.append(f"nextActionStates={','.join(state_parts)}")
    parts.extend(
        [
            f"diagnoseAction={actions['diagnose-run']['command']}",
            f"feedbackAction={actions['submit-feedback']['command']}",
            f"promoteAction={actions['promote-eval']['command']}",
            f"preflightAction={actions['preflight-langsmith']['command']}",
            f"syncAction={actions['sync-langsmith']['command']}",
        ]
    )
    bulk_review_action = actions.get("bulk-review-feedback-queue")
    if bulk_review_action is not None:
        parts.append(f"feedbackBulkReviewAction={bulk_review_action['command']}")
    hardening_action = actions.get("refresh-rag-hardening")
    if hardening_action is not None:
        parts.append(f"hardeningAction={hardening_action['command']}")
    parts.append(f"readinessAction={actions['refresh-readiness']['command']}")
    return "; ".join(parts)


def candidate_missing_citation_workflow_tags(
    *,
    collection: str,
    case_id: str,
    suite_file: str = "",
    dataset_name: str = "",
    feedback_workflow_tags: Sequence[str],
) -> list[str]:
    tags = [*collection_tags(collection), *clean_string_values(feedback_workflow_tags)]
    if missing_citation_targets_rag_candidate(
        collection,
        suite_file=suite_file,
        dataset_name=dataset_name,
    ):
        tags.append("collection:rag-ingestion-candidate")
        candidate_slug = rag_candidate_slug_from_case_id(case_id)
        if candidate_slug is not None:
            tags.append(rag_candidate_workflow_tag(candidate_slug))
    return list(dict.fromkeys(tags))


def missing_citation_eval_handoff(
    collection: str,
    *,
    case_id: str = "",
    suite_file: str = "",
    dataset_name: str = "",
) -> dict[str, str]:
    if missing_citation_targets_rag_candidate(
        collection,
        suite_file=suite_file,
        dataset_name=dataset_name,
    ):
        report_slug = command_slug(case_id) if case_id else "citation-failure"
        resolved_suite_file = suite_file.strip() or "evals/regression/rag-ingestion-candidate.json"
        requested_dataset_name = dataset_name.strip()
        resolved_dataset_name = (
            requested_dataset_name
            if requested_dataset_name and requested_dataset_name != DEFAULT_APPLY_DATASET_NAME
            else "reactor-rag-ingestion-candidate"
        )
        return {
            "suite_file": resolved_suite_file,
            "dataset_name": resolved_dataset_name,
            "dataset_arg": f"--apply-dataset-name {quote(resolved_dataset_name)} ",
            "report_file": f"artifacts/langsmith/rag-ingestion-candidate-{report_slug}.json",
        }
    resolved_suite_file = suite_file.strip() or "tests/fixtures/agent-eval/regression-suite.json"
    resolved_dataset_name = dataset_name.strip() or DEFAULT_APPLY_DATASET_NAME
    dataset_arg = (
        f"--apply-dataset-name {quote(resolved_dataset_name)} "
        if resolved_dataset_name != DEFAULT_APPLY_DATASET_NAME
        else ""
    )
    return {
        "suite_file": resolved_suite_file,
        "dataset_name": resolved_dataset_name,
        "dataset_arg": dataset_arg,
        "report_file": "reports/langsmith-eval-sync-dry-run.json",
    }


def missing_citation_targets_rag_candidate(
    collection: str,
    *,
    suite_file: str = "",
    dataset_name: str = "",
) -> bool:
    return (
        collection.strip() == "rag-ingestion-candidate"
        or dataset_name.strip() == "reactor-rag-ingestion-candidate"
        or "rag-ingestion-candidate" in suite_file
    )


def missing_citation_sync_action(eval_handoff: Mapping[str, str]) -> str:
    report_file = eval_handoff["report_file"]
    return (
        "uv run reactor-langsmith-eval-sync "
        f"--suite-file {eval_handoff['suite_file']} "
        f"--dataset-name {eval_handoff['dataset_name']} "
        f"--report-file {report_file}"
    )


def missing_citation_hardening_action(eval_handoff: Mapping[str, str]) -> str:
    command = missing_citation_hardening_command(eval_handoff)
    if not command:
        return ""
    return f"hardeningAction={command}; "


def missing_citation_hardening_command(eval_handoff: Mapping[str, str]) -> str:
    if not missing_citation_handoff_is_rag_candidate(eval_handoff):
        return ""
    return rag_ingestion_lifecycle_remediation_command()


def missing_citation_required_readiness_reports(eval_handoff: Mapping[str, str]) -> list[str]:
    return ["hardening_suite", "langsmith_eval_sync"]


def missing_citation_readiness_reports(eval_handoff: Mapping[str, str]) -> dict[str, str]:
    reports = {"langsmith_eval_sync": eval_handoff["report_file"]}
    return {"hardening_suite": HARDENING_SUITE_REPORT_FILE, **reports}


def missing_citation_readiness_action(eval_handoff: Mapping[str, str]) -> str:
    report_file = eval_handoff["report_file"]
    return release_readiness_command_for_reports(
        required_reports=("hardening_suite", "langsmith_eval_sync"),
        report_files={
            "hardening_suite": HARDENING_SUITE_REPORT_FILE,
            "langsmith_eval_sync": report_file,
        },
    )


def missing_citation_handoff_is_rag_candidate(eval_handoff: Mapping[str, str]) -> bool:
    return (
        eval_handoff.get("dataset_name") == "reactor-rag-ingestion-candidate"
        or "rag-ingestion-candidate" in eval_handoff.get("suite_file", "")
        or "rag-ingestion-candidate" in eval_handoff.get("report_file", "")
    )


def missing_citation_apply_dry_run_arg(eval_handoff: Mapping[str, str]) -> str:
    return "" if missing_citation_handoff_is_rag_candidate(eval_handoff) else "--apply-dry-run "


def missing_citation_candidate_tag(workflow_tags: Sequence[str]) -> str:
    for tag in workflow_tags:
        if tag.startswith("rag-candidate:"):
            return tag
    return ""


def missing_citation_bulk_review_action(workflow_tags: Sequence[str]) -> str:
    candidate_tag = missing_citation_candidate_tag(workflow_tags)
    if not candidate_tag:
        return ""
    return rag_candidate_feedback_bulk_review_action(candidate_tag, source="documents_ask")


def should_require_citation(args: argparse.Namespace) -> bool:
    return bool(args.require_citation or args.eval_case_file or args.eval_run_file)


def format_ask_summary(body: dict[str, object] | list[object] | None) -> str:
    answer = ""
    run_id = ""
    retrieved_documents: object = None
    suite_summary: object = None
    suite_apply: object = None
    eval_artifacts: object = None
    next_actions: object = None
    next_action_state_source: Mapping[str, object] | None = None
    if isinstance(body, Mapping):
        body_mapping = cast(Mapping[str, object], body)
        eval_artifacts = body_mapping.get("evalArtifacts")
        chat_body = body_mapping.get("chat")
        if isinstance(chat_body, Mapping):
            chat_mapping = cast(Mapping[str, object], chat_body)
            answer = optional_text(chat_mapping.get("content")) or ""
            run_id = summary_run_id(chat_mapping)
            retrieved_documents = chat_mapping.get("retrievedDocuments")
            suite_summary = body_mapping.get("suiteSummary")
            suite_apply = body_mapping.get("suiteApply")
            next_actions = chat_mapping.get("nextActions")
            next_action_state_source = chat_mapping
        else:
            answer = optional_text(body_mapping.get("content")) or ""
            run_id = summary_run_id(body_mapping)
            retrieved_documents = body_mapping.get("retrievedDocuments")
            next_actions = body_mapping.get("nextActions")
            next_action_state_source = body_mapping
    lines = ["Answer:", answer, "", "Citations:"]
    if run_id:
        quoted_run_id = quote(run_id)
        lines = [
            "Answer:",
            answer,
            "",
            "Run:",
            f"- {run_id}",
            f"- diagnose: reactor-runs diagnose {quoted_run_id} --output table",
            f"- replay: reactor-runs replay {quoted_run_id} --output table",
            f"- state-history: reactor-admin state-history {quoted_run_id} --output table",
            "",
            "Citations:",
        ]
    citations = answer_citations(answer)
    lines.extend(f"- {citation}" for citation in citations)
    grounding_line = grounding_summary_line(retrieved_documents, citations)
    if grounding_line:
        lines.extend(["", "Grounding:", grounding_line])
    retrieved_lines = retrieved_document_summary_lines(retrieved_documents)
    if retrieved_lines:
        lines.extend(["", "Retrieved documents:", *retrieved_lines])
    eval_artifacts_line = eval_artifacts_summary_line(eval_artifacts)
    if eval_artifacts_line:
        lines.extend(["", "Eval artifacts:", eval_artifacts_line])
    suite_line = eval_suite_summary_line(suite_summary)
    if suite_line:
        lines.extend(["", "Eval suite:", suite_line])
    langsmith_line = langsmith_dry_run_summary_line(suite_apply)
    if langsmith_line:
        lines.extend(["", "LangSmith dry run:", langsmith_line])
    next_action_lines = next_action_summary_lines(next_actions)
    if next_action_lines:
        state_lines = next_action_state_summary_lines(next_action_state_source)
        lines.extend(["", "Next actions:", *state_lines, *next_action_lines])
    return "\n".join(lines) + "\n"


def next_action_state_summary_lines(source: Mapping[str, object] | None) -> list[str]:
    if source is None:
        return []
    lines: list[str] = []
    ready_ids = string_list_value(source.get("readyNextActionIds"))
    if ready_ids:
        lines.append(f"- readyNextActionIds: {','.join(ready_ids)}")
    blocked_ids = string_list_value(source.get("blockedNextActionIds"))
    if blocked_ids:
        lines.append(f"- blockedNextActionIds: {','.join(blocked_ids)}")
    states = source.get("nextActionStates")
    if isinstance(states, Mapping):
        state_parts = [
            f"{action_id.strip()}={state.strip()}"
            for action_id, state in cast(Mapping[object, object], states).items()
            if isinstance(action_id, str)
            and action_id.strip()
            and isinstance(state, str)
            and state.strip()
        ]
        if state_parts:
            lines.append(f"- nextActionStates: {','.join(state_parts)}")
    return lines


def next_action_summary_lines(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    lines: list[str] = []
    for item in cast(Sequence[object], value):
        if not isinstance(item, Mapping):
            continue
        mapping = cast(Mapping[str, object], item)
        action_id = optional_text(mapping.get("id"))
        command = optional_text(mapping.get("command"))
        if action_id and command:
            lines.append(f"- {action_id}: {command}")
            lines.extend(next_action_metadata_summary_lines(action_id, mapping))
    return lines


def next_action_metadata_summary_lines(
    action_id: str,
    mapping: Mapping[str, object],
) -> list[str]:
    lines: list[str] = []
    for field_name in (
        "evalCaseId",
        "caseId",
        "caseFile",
        "runFile",
        "sourceRunId",
        "candidateTag",
        "source",
        "feedbackSource",
        "rating",
        "suiteFile",
        "datasetName",
        "reportFile",
        "expectedAnswer",
        "replatformReadinessFile",
        "smokePlanFile",
        "releaseEvidenceFile",
        "releaseReadinessFile",
        "releaseReadinessCommand",
        "latestTagCommand",
        "recommendedTagSource",
        "requiredReviewNote",
        "readinessReportArg",
    ):
        value = optional_text(mapping.get(field_name))
        if value:
            lines.append(f"- {action_id}.{field_name}: {value}")
        if field_name == "expectedAnswer":
            expected_answers = string_list_value(mapping.get("expectedAnswers"))
            if expected_answers:
                lines.append(f"- {action_id}.expectedAnswers: {','.join(expected_answers)}")
    required_reports = string_list_value(mapping.get("requiredReadinessReports"))
    if required_reports:
        lines.append(f"- {action_id}.requiredReadinessReports: {','.join(required_reports)}")
    minor_boundary_reports = string_list_value(mapping.get("minorBoundaryReports"))
    if minor_boundary_reports:
        lines.append(f"- {action_id}.minorBoundaryReports: {','.join(minor_boundary_reports)}")
    for index, env_group in enumerate(required_env_any_of_parts(mapping.get("requiredEnvAnyOf"))):
        lines.append(f"- {action_id}.requiredEnvAnyOf.{index}: {env_group}")
    missing_env_any_of = string_list_value(mapping.get("missingEnvAnyOf"))
    if missing_env_any_of:
        lines.append(f"- {action_id}.missingEnvAnyOf: {','.join(missing_env_any_of)}")
    recommended_env = string_list_value(mapping.get("recommendedEnv"))
    if recommended_env:
        lines.append(f"- {action_id}.recommendedEnv: {','.join(recommended_env)}")
    depends_on_action_ids = string_list_value(mapping.get("dependsOnActionIds"))
    if depends_on_action_ids:
        lines.append(f"- {action_id}.dependsOnActionIds: {','.join(depends_on_action_ids)}")
    readiness_reports = mapping.get("readinessReports")
    if isinstance(readiness_reports, Mapping):
        for report_name, report_file in sorted(
            cast(Mapping[object, object], readiness_reports).items(),
            key=lambda item: str(item[0]),
        ):
            if not isinstance(report_name, str) or not isinstance(report_file, str):
                continue
            report_name = report_name.strip()
            report_file = report_file.strip()
            if report_name and report_file:
                lines.append(f"- {action_id}.readinessReports.{report_name}: {report_file}")
    for field_name in ("workflowTags", "feedbackTags"):
        values = string_list_value(mapping.get(field_name))
        if values:
            lines.append(f"- {action_id}.{field_name}: {','.join(values)}")
    return lines


def summary_run_id(chat_body: Mapping[str, object]) -> str:
    metadata = document_mapping(chat_body.get("metadata"))
    return optional_text(metadata.get("runId")) or optional_text(metadata.get("run_id")) or ""


def eval_suite_summary_line(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    mapping = cast(Mapping[str, object], value)
    line = (
        f"- cases={mapping.get('caseCount')} "
        f"enabled={mapping.get('enabledCases')} "
        f"runs={mapping.get('runCount')} "
        f"covered={mapping.get('coveredCases')} "
        f"missingRuns={mapping.get('missingRuns')}"
    )
    missing_run_ids = comma_separated_sequence(mapping.get("missingRunIds"))
    if missing_run_ids:
        line = f"{line} missingRunIds={missing_run_ids}"
    return line


def comma_separated_sequence(value: object) -> str:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ""
    return ",".join(str(item) for item in cast(Sequence[object], value) if str(item))


def grounding_summary_line(retrieved_documents: object, citations: Sequence[str]) -> str:
    if not isinstance(retrieved_documents, Sequence) or isinstance(retrieved_documents, str):
        return ""
    retrieved_ids: list[str] = []
    for item in cast(Sequence[object], retrieved_documents):
        item_id = document_id(item)
        if item_id is not None:
            retrieved_ids.append(item_id)
    if not retrieved_ids:
        return ""
    cited_ids = {citation for citation in citations}
    cited_count = len(
        [document_id_value for document_id_value in retrieved_ids if document_id_value in cited_ids]
    )
    uncited_count = len(retrieved_ids) - cited_count
    return f"- retrieved={len(retrieved_ids)} cited={cited_count} uncited={uncited_count}"


def eval_artifact_summary(args: argparse.Namespace) -> dict[str, object]:
    artifacts: dict[str, object] = {}
    case_id = optional_text(args.eval_case_id)
    case_file = optional_text(args.eval_case_file)
    run_file = optional_text(args.eval_run_file)
    dataset_name = optional_text(args.apply_dataset_name)
    apply_suite_file = optional_text(args.apply_suite_file)
    langsmith_report_file = optional_text(args.langsmith_dry_run_report_file)
    collection = optional_text(args.collection)
    feedback_ids = clean_string_values(args.feedback_id)
    feedback_ratings = clean_string_values(args.feedback_rating)
    feedback_sources = [
        command_slug(source) for source in clean_string_values(args.feedback_source)
    ]
    feedback_workflow_tags = eval_artifact_feedback_workflow_tags(
        collection=collection or "",
        case_id=case_id or "",
        suite_file=apply_suite_file or "",
        dataset_name=dataset_name or "",
        feedback_workflow_tags=args.feedback_tag,
    )
    if case_id:
        artifacts["caseId"] = case_id
    if case_file:
        artifacts["caseFile"] = case_file
    if run_file:
        artifacts["runFile"] = run_file
    if dataset_name and dataset_name != DEFAULT_APPLY_DATASET_NAME:
        artifacts["datasetName"] = dataset_name
    if apply_suite_file:
        artifacts["applySuiteFile"] = apply_suite_file
    if langsmith_report_file:
        artifacts["langsmithDryRunReportFile"] = langsmith_report_file
    if collection:
        artifacts["collection"] = collection
    if feedback_ids:
        artifacts["feedbackIds"] = feedback_ids
    if feedback_ratings:
        artifacts["feedbackRatings"] = feedback_ratings
    if feedback_sources:
        artifacts["feedbackSources"] = feedback_sources
    if feedback_workflow_tags:
        artifacts["feedbackTags"] = feedback_workflow_tags
    return artifacts


def eval_artifacts_summary_line(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    mapping = cast(Mapping[str, object], value)
    parts: list[str] = []
    case_id = optional_text(mapping.get("caseId"))
    case_file = optional_text(mapping.get("caseFile"))
    run_file = optional_text(mapping.get("runFile"))
    dataset_name = optional_text(mapping.get("datasetName"))
    apply_suite_file = optional_text(mapping.get("applySuiteFile"))
    langsmith_report_file = optional_text(mapping.get("langsmithDryRunReportFile"))
    feedback_ids = string_list_value(mapping.get("feedbackIds"))
    feedback_ratings = string_list_value(mapping.get("feedbackRatings"))
    feedback_sources = string_list_value(mapping.get("feedbackSources"))
    feedback_workflow_tags = string_list_value(mapping.get("feedbackTags"))
    collection = optional_text(mapping.get("collection")) or ""
    if case_id:
        parts.append(f"caseId={case_id}")
    if case_file:
        parts.append(f"caseFile={case_file}")
    if run_file:
        parts.append(f"runFile={run_file}")
    if dataset_name:
        parts.append(f"datasetName={dataset_name}")
    if apply_suite_file:
        parts.append(f"applySuiteFile={apply_suite_file}")
    if langsmith_report_file:
        parts.append(f"langsmithDryRunReportFile={langsmith_report_file}")
    if feedback_ids:
        parts.append(f"feedbackIds={','.join(feedback_ids)}")
    if feedback_ratings:
        parts.append(f"feedbackRatings={','.join(feedback_ratings)}")
    if feedback_sources:
        parts.append(f"feedbackSources={','.join(feedback_sources)}")
    if feedback_workflow_tags:
        parts.append(f"feedbackTags={','.join(feedback_workflow_tags)}")
    if not parts:
        return ""
    lines = [f"- {' '.join(parts)}"]
    apply_command = eval_artifacts_apply_command(
        case_file=case_file,
        run_file=run_file,
        dataset_name=dataset_name,
        suite_file=apply_suite_file,
        langsmith_report_file=langsmith_report_file,
        dry_run=True,
    )
    if apply_command:
        lines.append(f"- apply: {apply_command}")
    persist_apply_command = eval_artifacts_apply_command(
        case_file=case_file,
        run_file=run_file,
        dataset_name=dataset_name,
        suite_file=apply_suite_file,
        langsmith_report_file=langsmith_report_file,
        dry_run=False,
    )
    if persist_apply_command:
        lines.append(f"- persistApply: {persist_apply_command}")
    review_action = eval_artifacts_feedback_review_action(
        feedback_ids=feedback_ids,
        feedback_ratings=feedback_ratings,
        feedback_sources=feedback_sources,
        workflow_tags=feedback_workflow_tags,
        collection=collection,
    )
    if review_action:
        lines.append(f"- feedbackReviewAction: {review_action}")
    review_actions = eval_artifacts_feedback_review_actions(feedback_ids=feedback_ids)
    if review_actions:
        lines.append(f"- feedbackReviewActions: {';'.join(review_actions)}")
    memory_lifecycle_action = eval_artifacts_memory_lifecycle_action(
        workflow_tags=feedback_workflow_tags
    )
    if memory_lifecycle_action:
        lines.append(f"- memoryLifecycleAction: {memory_lifecycle_action}")
    return "\n".join(lines)


def eval_artifacts_apply_command(
    *,
    case_file: str | None,
    run_file: str | None,
    dataset_name: str | None = None,
    suite_file: str | None = None,
    langsmith_report_file: str | None = None,
    dry_run: bool = True,
) -> str:
    if not case_file or not run_file:
        return ""
    dataset_arg = f"--dataset-name {quote(dataset_name)} " if dataset_name else ""
    suite_path = suite_file or "tests/fixtures/agent-eval/regression-suite.json"
    report_path = langsmith_report_file or "reports/langsmith-eval-sync-dry-run.json"
    dry_run_args = "--dry-run --summary " if dry_run else ""
    return (
        "reactor-agent-eval-apply "
        f"--case-file {quote(case_file)} "
        f"--run-file {quote(run_file)} "
        f"--suite-file {quote(suite_path)} "
        f"{dataset_arg}"
        f"{dry_run_args}"
        "--require-source-run-id --require-run-file --require-context-diagnostics "
        f"--langsmith-dry-run-report-file {quote(report_path)} "
        "--output table"
    )


def eval_artifacts_summary_command(
    *,
    dataset_name: str | None = None,
    suite_file: str | None = None,
    langsmith_report_file: str | None = None,
) -> str:
    dataset_arg = f"--dataset-name {quote(dataset_name)} " if dataset_name else ""
    suite_path = suite_file or "tests/fixtures/agent-eval/regression-suite.json"
    report_path = langsmith_report_file or "reports/langsmith-eval-sync-dry-run.json"
    return (
        "reactor-agent-eval-apply "
        f"--suite-file {quote(suite_path)} "
        f"{dataset_arg}"
        "--summary "
        f"--langsmith-dry-run-report-file {quote(report_path)} "
        "--output table"
    )


def eval_artifact_feedback_workflow_tags(
    *,
    collection: str,
    case_id: str,
    suite_file: str = "",
    dataset_name: str = "",
    feedback_workflow_tags: Sequence[str],
) -> list[str]:
    tags = clean_string_values(feedback_workflow_tags)
    if missing_citation_targets_rag_candidate(
        collection,
        suite_file=suite_file,
        dataset_name=dataset_name,
    ):
        tags.append("collection:rag-ingestion-candidate")
        candidate_slug = rag_candidate_slug_from_case_id(case_id)
        if candidate_slug is not None:
            tags.append(rag_candidate_workflow_tag(candidate_slug))
    return list(dict.fromkeys(tags))


def eval_artifacts_feedback_review_action(
    *,
    feedback_ids: Sequence[str],
    feedback_ratings: Sequence[str],
    feedback_sources: Sequence[str] = (),
    workflow_tags: Sequence[str] = (),
    collection: str = "",
) -> str:
    if len(feedback_ids) == 1:
        return f"reactor-admin feedback --feedback-id {quote(feedback_ids[0])} --output table"
    if len(feedback_ids) > 1:
        return ""
    workflow_tags_for_action = feedback_review_workflow_tags(
        workflow_tags=workflow_tags,
        collection=collection,
    )
    source_args = "".join(f" --source {quote(source)}" for source in sorted(feedback_sources))
    tag_args = "".join(f" --tag {quote(tag)}" for tag in workflow_tags_for_action)
    for rating in sorted(feedback_ratings):
        if rating:
            return " ".join(
                part.strip()
                for part in (
                    "reactor-admin feedback",
                    f"--rating {quote(rating)}",
                    source_args,
                    f"--review-status inbox{tag_args}",
                    "--limit 10 --output table",
                )
                if part.strip()
            )
    return " ".join(
        part.strip()
        for part in (
            "reactor-admin feedback",
            source_args,
            f"--review-status inbox{tag_args}",
            "--limit 10 --output table",
        )
        if part.strip()
    )


def eval_artifacts_feedback_review_actions(*, feedback_ids: Sequence[str]) -> list[str]:
    if len(feedback_ids) <= 1:
        return []
    return [
        f"reactor-admin feedback --feedback-id {quote(feedback_id)} --output table"
        for feedback_id in feedback_ids
    ]


def feedback_review_workflow_tag(*, workflow_tags: Sequence[str], collection: str = "") -> str:
    return feedback_review_workflow_tags(workflow_tags=workflow_tags, collection=collection)[0]


def feedback_review_workflow_tags(
    *, workflow_tags: Sequence[str], collection: str = ""
) -> list[str]:
    tags = [
        tag
        for tag in clean_string_values(workflow_tags)
        if not tag.startswith("expected-citation:")
    ]
    if "memory" in tags:
        return ["memory"]
    if tags:
        resolved_tags = list(tags)
    else:
        resolved_tags = [f"collection:{collection.strip()}" if collection.strip() else "rag"]
    collection_tag = f"collection:{collection.strip()}" if collection.strip() else ""
    if (
        collection_tag == "collection:rag-ingestion-candidate"
        and collection_tag not in resolved_tags
    ):
        resolved_tags.insert(0, collection_tag)
    return list(dict.fromkeys(resolved_tags))


def eval_artifacts_memory_lifecycle_action(*, workflow_tags: Sequence[str]) -> str:
    tags = clean_string_values(workflow_tags)
    workflow_counts = {tag: 1 for tag in tags}
    return feedback_review_queue_memory_lifecycle_action(workflow_counts)


def langsmith_dry_run_summary_line(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    suite_apply = cast(Mapping[str, object], value)
    dry_run = suite_apply.get("langsmithDryRun")
    if not isinstance(dry_run, Mapping):
        return ""
    mapping = cast(Mapping[str, object], dry_run)
    release_gate = mapping.get("releaseGate")
    release_gate_mapping: Mapping[str, object]
    release_gate_mapping = (
        cast(Mapping[str, object], release_gate) if isinstance(release_gate, Mapping) else {}
    )
    feedback_review_queue = mapping.get("feedbackReviewQueue")
    feedback_review_queue_mapping: Mapping[str, object]
    feedback_review_queue_mapping = (
        cast(Mapping[str, object], feedback_review_queue)
        if isinstance(feedback_review_queue, Mapping)
        else {}
    )
    queue_workflow_tag_counts = feedback_review_queue_mapping.get("workflowTagCounts")
    queue_candidate_tag = feedback_review_queue_mapping.get("candidateTag")
    if isinstance(queue_candidate_tag, str) and queue_candidate_tag.strip():
        merged_counts: dict[object, object] = {}
        if isinstance(queue_workflow_tag_counts, Mapping):
            merged_counts.update(cast(Mapping[object, object], queue_workflow_tag_counts))
        merged_counts.setdefault(queue_candidate_tag.strip(), 1)
        queue_workflow_tag_counts = merged_counts
    queue_candidate_action = feedback_review_queue_mapping.get("candidateReviewAction")
    if not isinstance(queue_candidate_action, str) or not queue_candidate_action.strip():
        queue_candidate_action = feedback_review_queue_candidate_review_action(
            queue_workflow_tag_counts,
            case_ids=feedback_review_queue_mapping.get("caseIds"),
        )
    queue_case_ids = string_list_value(feedback_review_queue_mapping.get("caseIds"))
    queue_review_action = feedback_review_queue_action(
        feedback_rating_counts=feedback_review_queue_mapping.get("feedbackRatingCounts"),
        feedback_source_counts=feedback_review_queue_mapping.get("feedbackSourceCounts"),
        workflow_tag_counts=feedback_review_queue_mapping.get("workflowTagCounts"),
        case_ids=queue_case_ids,
        case_count=len(queue_case_ids),
    ) or feedback_review_queue_mapping.get("reviewAction")
    queue_export_action = feedback_review_queue_export_action(
        feedback_rating_counts=feedback_review_queue_mapping.get("feedbackRatingCounts"),
        feedback_source_counts=feedback_review_queue_mapping.get("feedbackSourceCounts"),
        workflow_tag_counts=feedback_review_queue_mapping.get("workflowTagCounts"),
        case_ids=queue_case_ids,
        case_count=len(queue_case_ids),
    ) or feedback_review_queue_mapping.get("exportAction")
    queue_bulk_review_action = feedback_review_queue_mapping.get("bulkReviewAction")
    if not isinstance(queue_bulk_review_action, str) or not queue_bulk_review_action.strip():
        queue_bulk_review_candidate_tag = feedback_review_queue_candidate_tag(
            queue_workflow_tag_counts,
            case_ids=feedback_review_queue_mapping.get("caseIds"),
        )
        queue_bulk_review_action = feedback_review_queue_bulk_review_action(
            queue_bulk_review_candidate_tag,
            feedback_source_counts=feedback_review_queue_mapping.get("feedbackSourceCounts"),
        )
    queue_memory_action = feedback_review_queue_mapping.get("memoryLifecycleAction")
    if not isinstance(queue_memory_action, str) or not queue_memory_action.strip():
        queue_memory_action = feedback_review_queue_memory_lifecycle_action(
            feedback_review_queue_mapping.get("workflowTagCounts")
        )
    product_boundary = langsmith_product_boundary_summary_parts(
        mapping.get("productCapabilityBoundary")
    )
    parts = [
        langsmith_summary_part("status", mapping.get("status")),
        langsmith_summary_part("dataset", mapping.get("datasetName")),
        langsmith_summary_part("examples", mapping.get("examples")),
        langsmith_summary_part("caseIds", mapping.get("caseIds")),
        langsmith_summary_part("metadataCaseIds", mapping.get("metadataCaseIds")),
        langsmith_summary_part("sourceRunIds", string_sequence_count(mapping.get("sourceRunIds"))),
        langsmith_summary_part(
            "caseSourceRunMappings",
            string_mapping_count(mapping.get("caseSourceRunIds")),
        ),
        langsmith_summary_part("splitCounts", mapping.get("splitCounts")),
        langsmith_summary_part("sourceSuite", mapping.get("sourceSuite")),
        langsmith_summary_part("feedbackCases", mapping.get("feedbackCases")),
        langsmith_summary_part("feedbackIds", mapping.get("feedbackIds")),
        langsmith_summary_part("feedbackIdList", mapping.get("feedbackIdList")),
        langsmith_summary_part("feedbackReviewIds", mapping.get("feedbackReviewIds")),
        langsmith_summary_part("feedbackRatings", mapping.get("feedbackRatings")),
        langsmith_summary_part("feedbackSources", mapping.get("feedbackSources")),
        langsmith_summary_part(
            "feedbackExpectedCitations",
            mapping.get("feedbackExpectedCitations"),
        ),
        langsmith_summary_part(
            "feedbackReviewAction",
            ""
            if string_list_value(mapping.get("feedbackReviewActions"))
            else (langsmith_feedback_review_action(mapping)),
        ),
        langsmith_summary_part(
            "feedbackReviewActions",
            ";".join(string_list_value(mapping.get("feedbackReviewActions"))),
        ),
        langsmith_summary_part(
            "feedbackBulkReviewAction",
            mapping.get("bulkReviewAction"),
        ),
        langsmith_summary_part(
            "feedbackQueueCases",
            string_sequence_count(feedback_review_queue_mapping.get("caseIds")),
        ),
        langsmith_summary_part(
            "feedbackQueueRatings",
            feedback_review_queue_mapping.get("feedbackRatingCounts"),
        ),
        langsmith_summary_part(
            "feedbackQueueSources",
            feedback_review_queue_mapping.get("feedbackSourceCounts"),
        ),
        langsmith_summary_part(
            "feedbackQueueWorkflows",
            queue_workflow_tag_counts,
        ),
        langsmith_summary_part(
            "feedbackQueueReviewAction",
            queue_review_action,
        ),
        langsmith_summary_part(
            "feedbackQueueExportAction",
            queue_export_action,
        ),
        langsmith_summary_part(
            "feedbackQueueCandidateAction",
            queue_candidate_action,
        ),
        langsmith_summary_part(
            "feedbackQueueBulkReviewAction",
            queue_bulk_review_action,
        ),
        langsmith_summary_part(
            "feedbackQueueMemoryAction",
            queue_memory_action,
        ),
        langsmith_summary_part("groundingCases", mapping.get("groundingCitationCases")),
        langsmith_summary_part("groundingCited", mapping.get("groundingCitedChunks")),
        langsmith_summary_part("groundingUncited", mapping.get("groundingUncitedChunks")),
        langsmith_summary_part(
            "groundingDocuments",
            mapping.get("groundingCitationDocuments"),
        ),
        langsmith_summary_part("memoryStatusCounts", mapping.get("memoryStatusCounts")),
        langsmith_summary_part(
            "skippedMemoryStatusCounts",
            mapping.get("skippedMemoryStatusCounts"),
        ),
        langsmith_summary_part(
            "contextFindings",
            mapping.get("contextManifestDiagnosticsFindings"),
        ),
        langsmith_summary_part(
            "memoryLifecycleAction",
            memory_lifecycle_action_from_context_diagnostics(mapping),
        ),
        langsmith_summary_part("gradedRuns", mapping.get("gradedRuns")),
        langsmith_summary_part("missingRunCases", mapping.get("missingRunCases")),
        langsmith_summary_part("releaseGate", release_gate_mapping.get("status")),
        langsmith_summary_part("gateReason", release_gate_mapping.get("reason")),
        langsmith_summary_part("productCapability", product_boundary.get("productCapability")),
        langsmith_summary_part(
            "productBoundaryMinorEligible",
            product_boundary.get("productBoundaryMinorEligible"),
        ),
        langsmith_summary_part(
            "productBoundaryEvidence",
            product_boundary.get("productBoundaryEvidence"),
        ),
        langsmith_summary_part(
            "productBoundaryMissing",
            product_boundary.get("productBoundaryMissing"),
        ),
        langsmith_summary_part(
            "productBoundaryRemediationAction",
            product_boundary_remediation_action(product_boundary),
        ),
        langsmith_summary_part(
            "productBoundaryReadinessCommand",
            product_boundary_readiness_command(mapping, product_boundary),
        ),
        langsmith_summary_part(
            "releaseRequiredReport",
            release_gate_mapping.get("requiredReport"),
        ),
        langsmith_summary_part(
            "releaseNext",
            release_gate_next_action(release_gate_mapping),
        ),
        langsmith_summary_part(
            "releasePlan",
            release_gate_remediation_plan(release_gate_mapping),
        ),
        langsmith_summary_part(
            "releaseGateRemediationCommand",
            release_gate_remediation_command(release_gate_mapping),
        ),
        langsmith_summary_part("preflightFile", RELEASE_SMOKE_PREFLIGHT_FILE),
        langsmith_summary_part("preflightEnvTemplate", RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE),
        langsmith_summary_part("replatformReadinessFile", REPLATFORM_READINESS_FILE),
        langsmith_summary_part("smokePlanFile", RELEASE_SMOKE_PLAN_FILE),
        langsmith_summary_part("releaseEvidenceFile", RELEASE_EVIDENCE_FILE),
        langsmith_summary_part("releaseReadinessFile", RELEASE_READINESS_FILE),
        langsmith_summary_part("syncCommand", mapping.get("syncCommand")),
        langsmith_summary_part("liveSyncCommand", mapping.get("liveSyncCommand")),
        langsmith_summary_part("persistCommand", mapping.get("persistCommand")),
        langsmith_summary_part("summaryCommand", mapping.get("summaryCommand")),
        langsmith_summary_part(
            "readinessCommand",
            langsmith_readiness_command(mapping),
        ),
        langsmith_summary_part("nextActions", langsmith_next_action_ids(mapping)),
        *langsmith_next_action_summary_parts(mapping),
        langsmith_summary_part("reportFile", mapping.get("reportFile")),
    ]
    return f"- {' '.join(part for part in parts if part)}"


def product_boundary_remediation_action(product_boundary: Mapping[str, object]) -> str:
    missing = str(product_boundary.get("productBoundaryMissing") or "")
    missing_items = {item.strip() for item in missing.split(",") if item.strip()}
    if "rag_ingestion_lifecycle" not in missing_items:
        return ""
    return rag_ingestion_lifecycle_remediation_command()


def product_boundary_readiness_command(
    summary: Mapping[str, object],
    product_boundary: Mapping[str, object],
) -> str:
    missing = str(product_boundary.get("productBoundaryMissing") or "")
    missing_items = {item.strip() for item in missing.split(",") if item.strip()}
    report_file = optional_text(summary.get("reportFile"))
    if "rag_ingestion_lifecycle" not in missing_items or report_file is None:
        return ""
    return release_readiness_command_for_reports(
        required_reports=("hardening_suite", "langsmith_eval_sync"),
        report_files={
            "hardening_suite": HARDENING_SUITE_REPORT_FILE,
            "langsmith_eval_sync": report_file,
        },
    )


def langsmith_next_action_ids(summary: Mapping[str, object]) -> list[str]:
    next_actions = summary.get("nextActions")
    if not isinstance(next_actions, Sequence) or isinstance(next_actions, str | bytes | bytearray):
        return []
    action_ids: list[str] = []
    for item in cast(Sequence[object], next_actions):
        if not isinstance(item, Mapping):
            continue
        action_id = cast(Mapping[object, object], item).get("id")
        if isinstance(action_id, str) and action_id.strip():
            action_ids.append(action_id.strip())
    return action_ids


def langsmith_next_action_summary_parts(summary: Mapping[str, object]) -> list[str]:
    next_actions = summary.get("nextActions")
    if not isinstance(next_actions, Sequence) or isinstance(next_actions, str | bytes | bytearray):
        return []
    parts: list[str] = []
    for item in cast(Sequence[object], next_actions):
        if not isinstance(item, Mapping):
            continue
        action = cast(Mapping[object, object], item)
        action_id = action.get("id")
        if not isinstance(action_id, str) or not action_id.strip():
            continue
        normalized_id = action_id.strip()
        command = action.get("command")
        if isinstance(command, str) and command.strip():
            parts.append(f"nextAction.{normalized_id}={executable_next_action(command.strip())}")
        candidate_tag = action.get("candidateTag")
        if isinstance(candidate_tag, str) and candidate_tag.strip():
            parts.append(f"nextAction.{normalized_id}.candidateTag={candidate_tag.strip()}")
        workflow_tags = string_list_value(action.get("workflowTags"))
        if workflow_tags:
            parts.append(f"nextAction.{normalized_id}.workflowTags={','.join(workflow_tags)}")
        feedback_id = action.get("feedbackId")
        if isinstance(feedback_id, str) and feedback_id.strip():
            parts.append(f"nextAction.{normalized_id}.feedbackId={feedback_id.strip()}")
        for field_name in ("feedbackSource", "feedbackRating"):
            field_value = action.get(field_name)
            if isinstance(field_value, str) and field_value.strip():
                parts.append(f"nextAction.{normalized_id}.{field_name}={field_value.strip()}")
        remediation_command = action.get("remediationCommand")
        if isinstance(remediation_command, str) and remediation_command.strip():
            parts.append(
                f"nextAction.{normalized_id}.remediationCommand="
                f"{executable_next_action(remediation_command.strip())}"
            )
        readiness_report_arg = action.get("readinessReportArg")
        if isinstance(readiness_report_arg, str) and readiness_report_arg.strip():
            parts.append(
                f"nextAction.{normalized_id}.readinessReportArg={readiness_report_arg.strip()}"
            )
        for field_name in (
            "releaseReadinessCommand",
            "replatformReadinessFile",
            "smokePlanFile",
            "releaseEvidenceFile",
            "releaseReadinessFile",
            "latestTagCommand",
            "recommendedTagSource",
            "recommendedVersionBump",
            "recommendedTagPattern",
        ):
            field_value = action.get(field_name)
            if isinstance(field_value, str) and field_value.strip():
                parts.append(f"nextAction.{normalized_id}.{field_name}={field_value.strip()}")
        minor_boundary_reports = string_list_value(action.get("minorBoundaryReports"))
        if minor_boundary_reports:
            parts.append(
                f"nextAction.{normalized_id}.minorBoundaryReports="
                f"{','.join(minor_boundary_reports)}"
            )
        for field_name in ("minorBlockedReports", "minorBoundaryMissingEvidence"):
            values = string_list_value(action.get(field_name))
            if values:
                parts.append(f"nextAction.{normalized_id}.{field_name}={','.join(values)}")
        required_env_any_of = required_env_any_of_parts(action.get("requiredEnvAnyOf"))
        for index, env_group in enumerate(required_env_any_of):
            parts.append(f"nextAction.{normalized_id}.requiredEnvAnyOf.{index}={env_group}")
        missing_env_any_of = string_list_value(action.get("missingEnvAnyOf"))
        if missing_env_any_of:
            parts.append(
                f"nextAction.{normalized_id}.missingEnvAnyOf={','.join(missing_env_any_of)}"
            )
        recommended_env = string_list_value(action.get("recommendedEnv"))
        if recommended_env:
            parts.append(f"nextAction.{normalized_id}.recommendedEnv={','.join(recommended_env)}")
        required_reports = string_list_value(action.get("requiredReadinessReports"))
        if required_reports:
            parts.append(
                f"nextAction.{normalized_id}.requiredReadinessReports={','.join(required_reports)}"
            )
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
                        parts.append(
                            f"nextAction.{normalized_id}.readinessReports.{report_name}="
                            f"{report_file}"
                        )
    return parts


def executable_next_action(command: str) -> str:
    return command.replace("VERIFY_TIMESTAMP", "$(date -u +%Y-%m-%dT%H:%M:%SZ)")


def langsmith_readiness_command(summary: Mapping[str, object]) -> str:
    report_file = optional_text(summary.get("reportFile"))
    if report_file is None:
        return ""
    return langsmith_release_readiness_command(report_file)


def string_sequence_count(value: object) -> int | None:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return None
    count = sum(
        1 for item in cast(Sequence[object], value) if isinstance(item, str) and item.strip()
    )
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


def langsmith_summary_part(label: str, value: object) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, Mapping):
        text = ",".join(
            f"{key}={item}" for key, item in sorted(cast(Mapping[object, object], value).items())
        )
        return f"{label}={text}" if text else ""
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        text = ",".join(str(item) for item in cast(Sequence[object], value))
        return f"{label}={text}" if text else ""
    return f"{label}={value}"


def memory_lifecycle_action_from_context_diagnostics(summary: Mapping[str, object]) -> str:
    skipped_counts = positive_int_mapping(summary.get("skippedMemoryStatusCounts"))
    if skipped_counts:
        return feedback_review_queue_memory_lifecycle_action({"memory": 1})
    status_counts = positive_int_mapping(summary.get("memoryStatusCounts"))
    if any(status != "active" for status in status_counts):
        return feedback_review_queue_memory_lifecycle_action({"memory": 1})
    return ""


def positive_int_mapping(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    counts: dict[str, int] = {}
    for key, item in cast(Mapping[object, object], value).items():
        if (
            isinstance(key, str)
            and key.strip()
            and isinstance(item, int)
            and not isinstance(item, bool)
            and item > 0
        ):
            counts[key.strip()] = item
    return counts


def langsmith_feedback_review_action(summary: Mapping[str, object]) -> str:
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
    if len(feedback_ids) > 1:
        return ""
    return "reactor-admin feedback --limit 10 --output table"


def string_list_value(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [
        item.strip()
        for item in cast(Sequence[object], value)
        if isinstance(item, str) and item.strip()
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


def release_gate_next_action(release_gate: Mapping[str, object]) -> str:
    remediation = release_gate.get("remediation")
    if not isinstance(remediation, Sequence) or isinstance(remediation, str):
        return ""
    for item in cast(Sequence[object], remediation):
        if isinstance(item, str) and item.strip():
            return item.strip()
    return ""


def release_gate_remediation_plan(release_gate: Mapping[str, object]) -> list[str]:
    remediation = release_gate.get("remediation")
    if not isinstance(remediation, Sequence) or isinstance(remediation, str):
        return []
    return [
        item.strip()
        for item in cast(Sequence[object], remediation)
        if isinstance(item, str) and item.strip()
    ]


def release_gate_remediation_command(release_gate: Mapping[str, object]) -> str:
    command = release_gate.get("remediationCommand")
    return command.strip() if isinstance(command, str) else ""


def answer_citations(answer: str) -> list[str]:
    seen: set[str] = set()
    citations: list[str] = []
    for citation in re.findall(r"\[([A-Za-z0-9_.:-]+)\]", answer):
        if citation not in seen:
            citations.append(citation)
            seen.add(citation)
    return citations


def ask_result_body(
    args: argparse.Namespace,
    documents: Sequence[object],
    chat_body: dict[str, object] | list[object] | None,
) -> dict[str, object] | list[object] | None:
    if not isinstance(chat_body, Mapping):
        return chat_body
    result = dict(cast(Mapping[str, object], chat_body))
    result["retrievedDocuments"] = [retrieved_document_summary(document) for document in documents]
    next_actions = successful_ask_next_actions(args, result)
    if next_actions:
        result["nextActions"] = next_actions
        result.update(next_action_state_fields(next_actions))
    return result


def next_action_state_fields(actions: Sequence[object]) -> dict[str, object]:
    action_mappings = [
        cast(Mapping[str, object], item) for item in actions if isinstance(item, Mapping)
    ]
    states = next_action_states(action_mappings)
    if not states:
        return {}
    return {
        "readyNextActionIds": ready_next_action_ids(action_mappings),
        "blockedNextActionIds": blocked_next_action_ids(action_mappings),
        "nextActionStates": states,
    }


def successful_ask_next_actions(
    args: argparse.Namespace,
    result: Mapping[str, object],
) -> list[dict[str, object]]:
    run_id = summary_run_id(result)
    answer = optional_text(result.get("content")) or ""
    if not run_id or not answer:
        return []
    tags = dedupe_preserving_order(
        [
            "rag",
            "documents-ask",
            "grounding",
            *clean_string_values(list(args.feedback_tag)),
            *expected_citation_tags_from_output(result),
        ]
    )
    comment = "Grounded RAG answer needs review before eval promotion."
    tag_args = " ".join(f"--tag {quote(tag)}" for tag in tags)
    feedback_sources = clean_string_values(list(args.feedback_source))
    feedback_source = feedback_sources[0] if feedback_sources else "documents_ask"
    command = (
        "reactor-admin feedback-submit --rating thumbs_down "
        f"--run-id {quote(run_id)} --query {quote(str(args.query))} "
        f"--response {quote(answer)} --comment {quote(comment)} --source {quote(feedback_source)} "
        f"{tag_args} --output table"
    )
    action: dict[str, object] = {
        "id": "submit-feedback",
        "label": "Submit feedback if this grounded answer is weak",
        "command": command,
        "runId": run_id,
        "sourceRunId": run_id,
        "source": feedback_source,
        "feedbackSource": feedback_source,
        "rating": "thumbs_down",
        "comment": comment,
        "tags": tags,
        "workflowTags": tags,
        "feedbackTags": tags,
    }
    eval_case_id = str(args.eval_case_id or "").strip()
    if eval_case_id:
        action["evalCaseId"] = eval_case_id
    inspect_command = (
        f"reactor-admin feedback --rating thumbs_down --source {quote(feedback_source)} "
        f"--review-status inbox {tag_args} --limit 10 --output table"
    )
    inspect_action: dict[str, object] = {
        "id": "inspect-feedback",
        "label": "Inspect matching feedback after submission",
        "command": inspect_command,
        "runId": run_id,
        "sourceRunId": run_id,
        "source": feedback_source,
        "feedbackSource": feedback_source,
        "rating": "thumbs_down",
        "tags": tags,
        "workflowTags": tags,
        "feedbackTags": tags,
    }
    if eval_case_id:
        inspect_action["evalCaseId"] = eval_case_id
    actions = [action, inspect_action]
    promote_action = successful_ask_promote_eval_action(
        args,
        run_id=run_id,
        feedback_source=feedback_source,
        tags=tags,
    )
    if promote_action:
        actions.append(promote_action)
        actions.append(successful_ask_persist_eval_action(promote_action))
        actions.extend(successful_ask_langsmith_next_actions(promote_action))
        bulk_review_action = successful_ask_candidate_bulk_review_action(promote_action)
        if bulk_review_action:
            actions.append(bulk_review_action)
        review_done_action = successful_ask_review_done_action(promote_action)
        if review_done_action:
            actions.append(review_done_action)
    return actions


def successful_ask_review_done_action(promote_action: Mapping[str, object]) -> dict[str, object]:
    workflow_tags = string_list_value(promote_action.get("workflowTags"))
    if missing_citation_candidate_tag(workflow_tags):
        return {}
    case_id = optional_text(promote_action.get("caseId")) or ""
    feedback_source = optional_text(promote_action.get("feedbackSource")) or ""
    tag_args = " ".join(f"--tag {quote(tag)}" for tag in workflow_tags)
    command = (
        f"reactor-admin feedback-bulk-review --case-id {quote(case_id)} "
        f"--source {quote(feedback_source)} --status done --tag promoted --tag langsmith "
        f"{tag_args} "
        f"--note {quote(RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE)} "
        "--output table"
    )
    return {
        "id": "review-done",
        "label": "Mark matching feedback as promoted after eval and readiness are captured",
        "command": command,
        "sourceRunId": promote_action.get("sourceRunId"),
        "evalCaseId": case_id,
        "suiteFile": promote_action.get("suiteFile"),
        "datasetName": promote_action.get("datasetName") or DEFAULT_APPLY_DATASET_NAME,
        "reportFile": promote_action.get("reportFile"),
        "releaseReadinessFile": RELEASE_READINESS_FILE,
        "readinessReportArg": promote_action.get("readinessReportArg"),
        "requiredReadinessReports": promote_action.get("requiredReadinessReports"),
        "readinessReports": promote_action.get("readinessReports"),
        "feedbackSource": promote_action.get("feedbackSource"),
        "workflowTags": workflow_tags,
        "requiredReviewNote": RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
        "dependsOnActionIds": ["refresh-readiness"],
    }


def successful_ask_candidate_bulk_review_action(
    promote_action: Mapping[str, object],
) -> dict[str, object]:
    workflow_tags = string_list_value(promote_action.get("workflowTags"))
    candidate_tag = missing_citation_candidate_tag(workflow_tags)
    if not candidate_tag:
        return {}
    feedback_source = optional_text(promote_action.get("feedbackSource")) or ""
    filtered_feedback_tags = ["collection:rag-ingestion-candidate", candidate_tag]
    return {
        "id": "bulk-review-candidate-feedback",
        "label": "Close queued feedback for this RAG candidate after eval and LangSmith review",
        "command": rag_candidate_feedback_bulk_review_action(
            candidate_tag,
            source=feedback_source,
        ),
        "sourceRunId": promote_action.get("sourceRunId"),
        "evalCaseId": promote_action.get("caseId"),
        "candidateTag": candidate_tag,
        "reportFile": promote_action.get("reportFile"),
        "releaseReadinessFile": RELEASE_READINESS_FILE,
        "readinessReportArg": promote_action.get("readinessReportArg"),
        "requiredReadinessReports": promote_action.get("requiredReadinessReports"),
        "readinessReports": promote_action.get("readinessReports"),
        "feedbackSource": promote_action.get("feedbackSource"),
        "workflowTags": filtered_feedback_tags,
        "feedbackTags": filtered_feedback_tags,
        "requiredReviewNote": RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
        "dependsOnActionIds": ["refresh-readiness"],
    }


def successful_ask_langsmith_next_actions(
    promote_action: Mapping[str, object],
) -> list[dict[str, object]]:
    source_run_id = promote_action.get("sourceRunId")
    case_id = promote_action.get("caseId")
    suite_file = optional_text(promote_action.get("suiteFile")) or ""
    dataset_name = optional_text(promote_action.get("datasetName")) or DEFAULT_APPLY_DATASET_NAME
    report_file = optional_text(promote_action.get("reportFile")) or ""
    readiness_reports = promote_action.get("readinessReports")
    required_readiness_reports = promote_action.get("requiredReadinessReports")
    readiness_report_arg = optional_text(promote_action.get("readinessReportArg")) or ""
    feedback_source = promote_action.get("feedbackSource")
    preflight_command = (
        "uv run reactor-langsmith-eval-sync "
        f"--suite-file {quote(suite_file)} "
        f"--dataset-name {quote(dataset_name)} "
        f"--report-file {quote(report_file)} "
        "--preflight-only --output table"
    )
    sync_command = (
        "uv run reactor-langsmith-eval-sync "
        f"--suite-file {quote(suite_file)} "
        f"--dataset-name {quote(dataset_name)} "
        f"--report-file {quote(report_file)} "
        "--output table"
    )
    if required_readiness_reports and readiness_reports:
        readiness_command = release_readiness_command_for_reports(
            required_reports=cast(Sequence[str], required_readiness_reports or ()),
            report_files=cast(Mapping[str, str], readiness_reports or {}),
        )
    else:
        readiness_command = langsmith_release_readiness_command(report_file)
    common = {
        "sourceRunId": source_run_id,
        "evalCaseId": case_id,
        "reportFile": report_file,
        "releaseReadinessFile": RELEASE_READINESS_FILE,
        "readinessReportArg": readiness_report_arg,
        "requiredReadinessReports": required_readiness_reports,
        "readinessReports": readiness_reports,
        "feedbackSource": feedback_source,
    }
    return [
        {
            "id": "preflight-langsmith",
            "label": "Preflight LangSmith eval sync credentials",
            "command": preflight_command,
            "suiteFile": suite_file,
            "datasetName": dataset_name,
            "preflightFile": RELEASE_SMOKE_PREFLIGHT_FILE,
            "preflightEnvTemplate": RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
            "remediationCommand": preflight_command,
            "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
            "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
            "dependsOnActionIds": ["persist-eval-suite"],
            **common,
        },
        {
            "id": "sync-langsmith",
            "label": "Sync eval case to LangSmith",
            "command": sync_command,
            "suiteFile": suite_file,
            "datasetName": dataset_name,
            "preflightFile": RELEASE_SMOKE_PREFLIGHT_FILE,
            "preflightEnvTemplate": RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
            "remediationCommand": sync_command,
            "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
            "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
            "dependsOnActionIds": ["preflight-langsmith"],
            **common,
        },
        {
            "id": "refresh-readiness",
            "label": "Refresh release readiness",
            "command": readiness_command,
            "preflightFile": RELEASE_SMOKE_PREFLIGHT_FILE,
            "preflightEnvTemplate": RELEASE_SMOKE_PREFLIGHT_ENV_TEMPLATE,
            "replatformReadinessFile": REPLATFORM_READINESS_FILE,
            "smokePlanFile": RELEASE_SMOKE_PLAN_FILE,
            "releaseEvidenceFile": RELEASE_EVIDENCE_FILE,
            "latestTagCommand": LATEST_TAG_COMMAND,
            "recommendedTagSource": RECOMMENDED_TAG_SOURCE,
            "minorBoundaryReports": required_readiness_reports,
            "dependsOnActionIds": ["sync-langsmith"],
            **common,
        },
    ]


def successful_ask_persist_eval_action(promote_action: Mapping[str, object]) -> dict[str, object]:
    case_file = optional_text(promote_action.get("caseFile")) or ""
    run_file = optional_text(promote_action.get("runFile")) or ""
    suite_file = optional_text(promote_action.get("suiteFile")) or ""
    dataset_name = optional_text(promote_action.get("datasetName")) or DEFAULT_APPLY_DATASET_NAME
    report_file = optional_text(promote_action.get("reportFile")) or ""
    command = (
        "reactor-agent-eval-apply "
        f"--case-file {quote(case_file)} "
        f"--run-file {quote(run_file)} "
        f"--suite-file {quote(suite_file)} "
        f"--dataset-name {quote(dataset_name)} "
        "--require-source-run-id --require-run-file --require-context-diagnostics "
        f"--langsmith-dry-run-report-file {quote(report_file)} "
        "--output table"
    )
    return {
        "id": "persist-eval-suite",
        "label": "Persist promoted eval case after review",
        "command": command,
        "runId": promote_action.get("runId"),
        "sourceRunId": promote_action.get("sourceRunId"),
        "caseId": promote_action.get("caseId"),
        "evalCaseId": promote_action.get("caseId"),
        "caseFile": case_file,
        "runFile": run_file,
        "suiteFile": suite_file,
        "datasetName": dataset_name,
        "reportFile": report_file,
        "releaseReadinessFile": RELEASE_READINESS_FILE,
        "readinessReportArg": promote_action.get("readinessReportArg"),
        "requiredReadinessReports": promote_action.get("requiredReadinessReports"),
        "readinessReports": promote_action.get("readinessReports"),
        "dependsOnActionIds": ["promote-eval"],
        "workflowTags": promote_action.get("workflowTags"),
        "feedbackSource": promote_action.get("feedbackSource"),
        "feedbackTags": promote_action.get("feedbackTags"),
    }


def successful_ask_promote_eval_action(
    args: argparse.Namespace,
    *,
    run_id: str,
    feedback_source: str,
    tags: Sequence[str],
) -> dict[str, object]:
    citation_tags = [tag for tag in tags if tag.startswith("expected-citation:") and tag.strip()]
    expected_answers = [
        f"[{tag.removeprefix('expected-citation:')}]"
        for tag in citation_tags
        if is_citation_safe_id(tag.removeprefix("expected-citation:"))
    ]
    if not expected_answers:
        return {}
    case_id = str(args.eval_case_id or "").strip() or f"case_documents_ask_{command_slug(run_id)}"
    eval_handoff = missing_citation_eval_handoff(
        str(args.collection or ""),
        case_id=case_id,
        suite_file=str(args.apply_suite_file or ""),
        dataset_name=str(args.apply_dataset_name or ""),
    )
    candidate_handoff = missing_citation_handoff_is_rag_candidate(eval_handoff)
    default_case_file = f"evals/cases/{case_id}.json" if candidate_handoff else "promoted-case.json"
    default_run_file = (
        f"evals/runs/{command_slug(run_id)}.json" if candidate_handoff else "promoted-run.json"
    )
    case_file = str(args.eval_case_file or "").strip() or default_case_file
    run_file = str(args.eval_run_file or "").strip() or default_run_file
    suite_file = eval_handoff["suite_file"]
    report_file = (
        str(args.langsmith_dry_run_report_file or "").strip() or eval_handoff["report_file"]
    )
    readiness_reports = missing_citation_readiness_reports(eval_handoff)
    readiness_reports["langsmith_eval_sync"] = report_file
    required_readiness_reports = missing_citation_required_readiness_reports(eval_handoff)
    eval_tags = dedupe_preserving_order(
        [
            *tags,
            "feedback-rating:thumbs_down",
        ]
    )
    tag_args = " ".join(f"--tag {quote(tag)}" for tag in eval_tags)
    expected_answer_args = " ".join(
        f"--expected-answer {quote(expected_answer)}" for expected_answer in expected_answers
    )
    command = (
        f"reactor-runs promote-eval {quote(run_id)} --case-id {quote(case_id)} "
        f"--case-file {quote(case_file)} --run-file {quote(run_file)} "
        f"{tag_args} "
        f"--feedback-source {quote(feedback_source)} "
        f"{expected_answer_args} "
        f"--apply-suite-file {quote(suite_file)} "
        f"{eval_handoff['dataset_arg']}"
        f"{missing_citation_apply_dry_run_arg(eval_handoff)}"
        "--apply-require-source-run-id --apply-require-run-file "
        "--apply-require-context-diagnostics --apply-suite-summary "
        f"--langsmith-dry-run-report-file {quote(report_file)} "
        "--output table"
    )
    return {
        "id": "promote-eval",
        "label": "Promote weak grounded answer to eval",
        "command": command,
        "runId": run_id,
        "sourceRunId": run_id,
        "source": feedback_source,
        "feedbackSource": feedback_source,
        "rating": "thumbs_down",
        "caseId": case_id,
        "caseFile": case_file,
        "runFile": run_file,
        "suiteFile": suite_file,
        **({"datasetName": eval_handoff["dataset_name"]} if eval_handoff["dataset_arg"] else {}),
        "reportFile": report_file,
        "releaseReadinessFile": RELEASE_READINESS_FILE,
        "readinessReportArg": readiness_report_args_for_reports(
            required_reports=required_readiness_reports,
            report_files=readiness_reports,
        ),
        "requiredReadinessReports": required_readiness_reports,
        "readinessReports": readiness_reports,
        "expectedAnswer": expected_answers[0] if len(expected_answers) == 1 else expected_answers,
        "expectedAnswers": expected_answers,
        "tags": eval_tags,
        "workflowTags": tags,
        "feedbackTags": eval_tags,
    }


def retrieved_document_summary(document: object) -> dict[str, object]:
    mapping = document_mapping(document)
    metadata = document_mapping(mapping.get("metadata"))
    return {
        "id": document_citation_label(document),
        "title": optional_text(metadata.get("title")),
        "source": (
            optional_text(metadata.get("source"))
            or optional_text(metadata.get("sourceUri"))
            or optional_text(metadata.get("source_uri"))
        ),
        "score": optional_number(mapping.get("score")),
    }


def retrieved_document_summary_lines(retrieved_documents: object) -> list[str]:
    if not isinstance(retrieved_documents, Sequence) or isinstance(retrieved_documents, str):
        return []
    lines: list[str] = []
    for item in cast(Sequence[object], retrieved_documents):
        if not isinstance(item, Mapping):
            continue
        mapping = cast(Mapping[str, object], item)
        document_id = optional_text(mapping.get("id")) or "unknown"
        score = mapping.get("score")
        title = optional_text(mapping.get("title")) or ""
        source = optional_text(mapping.get("source")) or ""
        summary = f"- {document_id}"
        if score is not None:
            summary = f"{summary} score={score}"
        if title:
            summary = f"{summary} title={title}"
        if source:
            summary = f"{summary} source={source}"
        lines.append(summary)
    return lines


def write_ask_eval_files(
    args: argparse.Namespace,
    documents: Sequence[object],
    chat_body: dict[str, object] | list[object] | None,
) -> None:
    if not args.eval_case_file and not args.eval_run_file:
        return
    if not args.eval_case_id:
        raise ValueError("--eval-case-id is required with eval export files")
    if not isinstance(chat_body, Mapping):
        raise ValueError("chat response must be a JSON object for eval export")
    chat_mapping = cast(Mapping[str, object], chat_body)
    chat_metadata = document_mapping(chat_mapping.get("metadata"))
    run_id = chat_run_id(chat_mapping)
    final_answer = optional_text(chat_mapping.get("content")) or ""
    case_payload = ask_eval_case_payload(
        case_id=args.eval_case_id,
        query=args.query,
        collection=args.collection,
        source_run_id=run_id,
        documents=documents,
        final_answer=final_answer,
        feedback_ids=list(args.feedback_id),
        feedback_ratings=list(args.feedback_rating),
        feedback_sources=list(args.feedback_source),
        feedback_workflow_tags=list(args.feedback_tag),
    )
    run_payload = ask_eval_run_payload(
        case_id=args.eval_case_id,
        run_id=run_id,
        query=args.query,
        final_answer=final_answer,
        documents=documents,
        model=optional_text(chat_mapping.get("model")) or "unknown",
        context_manifest_diagnostics=document_mapping(
            chat_metadata.get("contextManifestDiagnostics")
            or chat_metadata.get("context_manifest_diagnostics")
        ),
    )
    if args.eval_case_file:
        write_json_file(Path(args.eval_case_file), case_payload)
    if args.eval_run_file:
        write_json_file(Path(args.eval_run_file), run_payload)


def ask_eval_case_payload(
    *,
    case_id: str,
    query: str,
    collection: str,
    source_run_id: str,
    documents: Sequence[object],
    final_answer: str,
    feedback_ids: Sequence[str] = (),
    feedback_ratings: Sequence[str] = (),
    feedback_sources: Sequence[str] = (),
    feedback_workflow_tags: Sequence[str] = (),
) -> dict[str, object]:
    return {
        "id": case_id,
        "name": f"Documents ask: {query}",
        "userInput": query,
        "expectedAnswerContains": cited_document_citation_markers(
            answer=final_answer,
            documents=documents,
        ),
        "forbiddenAnswerContains": [],
        "expectedToolNames": [],
        "forbiddenToolNames": [],
        "expectedExposedToolNames": [],
        "forbiddenExposedToolNames": [],
        "enabled": True,
        "tags": [
            "rag",
            "grounding",
            "documents-ask",
            "exported-from-cli",
            *collection_tags(collection),
            *expected_citation_tags(answer=final_answer, documents=documents),
            *feedback_tags(
                feedback_ids=feedback_ids,
                feedback_ratings=feedback_ratings,
                feedback_sources=feedback_sources,
                workflow_tags=feedback_workflow_tags,
            ),
        ],
        "minScore": 1.0,
        "sourceRunId": source_run_id,
    }


def collection_tags(collection: str) -> list[str]:
    normalized = collection.strip()
    return [f"collection:{normalized}"] if normalized else []


def expected_citation_tags(*, answer: str, documents: Sequence[object]) -> list[str]:
    return [
        f"expected-citation:{label}"
        for label in cited_document_labels(answer=answer, documents=documents)
        if label != "unknown" and is_citation_safe_id(label)
    ]


def feedback_tags(
    *,
    feedback_ids: Sequence[str],
    feedback_ratings: Sequence[str],
    feedback_sources: Sequence[str] = (),
    workflow_tags: Sequence[str] = (),
) -> list[str]:
    tags: list[str] = []
    tags.extend(f"feedback:{feedback_id}" for feedback_id in clean_string_values(feedback_ids))
    tags.extend(
        f"feedback-rating:{feedback_rating}"
        for feedback_rating in clean_string_values(feedback_ratings)
    )
    tags.extend(
        f"feedback-source:{command_slug(feedback_source)}"
        for feedback_source in clean_string_values(feedback_sources)
    )
    tags.extend(clean_string_values(workflow_tags))
    return tags


def clean_string_values(values: Sequence[str]) -> list[str]:
    return [value.strip() for value in values if value.strip()]


def dedupe_preserving_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in clean_string_values(values):
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def ask_eval_run_payload(
    *,
    case_id: str,
    run_id: str,
    query: str,
    final_answer: str,
    documents: Sequence[object],
    model: str,
    context_manifest_diagnostics: Mapping[str, object] | None = None,
) -> dict[str, object]:
    citations = set(answer_citations(final_answer))
    payload: dict[str, object] = {
        "runId": run_id,
        "evalCaseId": case_id,
        "userInput": query,
        "agentType": "documents-ask",
        "model": model,
        "finalAnswer": final_answer,
        "toolCalls": [],
        "toolExposure": {"count": 0, "names": []},
        "retrievedChunks": [
            retrieved_chunk_fixture(document, citations=citations) for document in documents
        ],
        "errors": [],
    }
    if context_manifest_diagnostics:
        payload["contextManifestDiagnostics"] = dict(context_manifest_diagnostics)
    return payload


def citation_labels(documents: Sequence[object]) -> list[str]:
    labels = [label for document in documents if (label := document_citation_label(document))]
    return labels or ["unknown"]


def has_stable_citation_labels(documents: Sequence[object]) -> bool:
    return all(document_citation_label(document) != "unknown" for document in documents)


def missing_citation_labels_failure(args: argparse.Namespace) -> dict[str, object]:
    collection = str(args.collection or "").strip() or "default"
    query = str(args.query)
    search_action = (
        "reactor-documents search "
        f"--collection {quote(collection)} --query {quote(query)} "
        f"--top-k {int(args.top_k)} --output table"
    )
    reingest_action = (
        "reactor-documents add "
        f"--collection {quote(collection)} --file <path> --title <title> "
        "--source-uri <stable-uri> --acl-visibility tenant"
    )
    retry_action = documents_ask_retry_action(
        collection=collection,
        query=query,
        top_k=int(args.top_k),
        require_citation=True,
    )
    return {
        "error": "missing_citation_labels",
        "message": "retrieved documents do not expose stable citation labels",
        "collection": collection,
        "query": query,
        "topK": int(args.top_k),
        "nextActions": [
            {
                "id": "search-documents",
                "label": "Inspect retrieved documents missing citation labels",
                "command": search_action,
                "collection": collection,
                "query": query,
                "topK": int(args.top_k),
            },
            {
                "id": "reingest-with-source",
                "label": "Reingest documents with stable source metadata",
                "command": reingest_action,
                "collection": collection,
                "aclVisibility": "tenant",
            },
            {
                "id": "retry-ask",
                "label": "Retry the citation-required documents ask after reingest",
                "command": retry_action,
                "collection": collection,
                "query": query,
                "topK": int(args.top_k),
                "requireCitation": True,
            },
        ],
    }


def cited_document_labels(*, answer: str, documents: Sequence[object]) -> list[str]:
    labels = citation_labels(documents)
    if labels == ["unknown"]:
        return labels
    citations = set(answer_citations(answer))
    cited_labels = [label for label in labels if label in citations]
    return cited_labels or labels


def cited_document_citation_markers(*, answer: str, documents: Sequence[object]) -> list[str]:
    return [f"[{label}]" for label in cited_document_labels(answer=answer, documents=documents)]


def retrieved_chunk_fixture(
    document: object,
    *,
    citations: set[str] | None = None,
) -> dict[str, object]:
    mapping = document_mapping(document)
    metadata = document_mapping(mapping.get("metadata"))
    citation_label = document_citation_label(document)
    document_id_value = document_id(document) or citation_label
    fixture: dict[str, object] = {
        "documentId": document_id_value,
        "source": (
            optional_text(metadata.get("source"))
            or optional_text(metadata.get("sourceUri"))
            or optional_text(metadata.get("source_uri"))
        ),
        "title": optional_text(metadata.get("title")),
        "score": optional_number(mapping.get("score")),
        "cited": bool(citations is not None and citation_label in citations),
    }
    if citation_label != document_id_value:
        fixture["citationId"] = citation_label
    return fixture


def document_id(document: object) -> str | None:
    return optional_text(document_mapping(document).get("id"))


def document_citation_label(document: object) -> str:
    mapping = document_mapping(document)
    metadata = document_mapping(mapping.get("metadata"))
    if (
        citation_id := optional_text(mapping.get("citationId"))
        or optional_text(mapping.get("citation_id"))
        or optional_text(metadata.get("citationId"))
        or optional_text(metadata.get("citation_id"))
    ):
        return citation_label_token(citation_id)
    if document_id_value := document_id(document):
        return citation_label_slug(document_id_value)
    source = (
        optional_text(metadata.get("source"))
        or optional_text(metadata.get("sourceUri"))
        or optional_text(metadata.get("source_uri"))
    )
    if source:
        return citation_label_slug(source)
    title = optional_text(metadata.get("title"))
    if title:
        return citation_label_slug(title)
    return "unknown"


def citation_label_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_") or "document"


def citation_label_token(value: str) -> str:
    normalized = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_.:-]+", normalized):
        return normalized
    return citation_label_slug(normalized)


def document_mapping(document: object) -> Mapping[str, object]:
    if not isinstance(document, Mapping):
        return {}
    return cast(Mapping[str, object], document)


def chat_run_id(chat_body: Mapping[str, object]) -> str:
    metadata = document_mapping(chat_body.get("metadata"))
    return optional_text(metadata.get("runId")) or "unknown"


def optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def optional_number(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def command_slug(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value.strip()).strip("_") or "item"


def write_json_file(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def document_content_from_args(args: argparse.Namespace) -> str:
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    return cast(str, args.content)


def document_path(path: str, collection: str, query: Mapping[str, object] | None = None) -> str:
    query_values: dict[str, object] = dict(query or {})
    if collection:
        query_values = {"collection": collection, **query_values}
    if not query_values:
        return path
    return f"{path}?{urlencode(query_values)}"


def metadata_from_json(raw: str) -> dict[str, object]:
    parsed = json.loads(raw or "{}")
    if not isinstance(parsed, dict):
        raise ValueError("--metadata-json must be a JSON object")
    return cast(dict[str, object], parsed)


def document_metadata_from_args(args: argparse.Namespace) -> dict[str, object]:
    metadata = metadata_from_json(args.metadata_json)
    if args.title:
        metadata["title"] = args.title
    if args.source_uri:
        metadata["sourceUri"] = args.source_uri
    elif getattr(args, "file", ""):
        metadata["sourceUri"] = Path(args.file).resolve().as_uri()
    return metadata


def batch_payload_from_file(path: str) -> dict[str, object]:
    parsed = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("--file must contain a JSON object")
    return cast(dict[str, object], parsed)


def batch_payload_from_directory(args: argparse.Namespace) -> dict[str, object]:
    root = Path(args.directory)
    documents: list[dict[str, object]] = []
    for document_file in sorted(path for path in root.glob(args.glob) if path.is_file()):
        relative_path = document_file.relative_to(root).as_posix()
        metadata: dict[str, object] = {"title": document_file.stem}
        if args.source_prefix:
            metadata["sourceUri"] = f"{args.source_prefix.rstrip('/')}/{relative_path}"
        else:
            metadata["sourceUri"] = document_file.resolve().as_uri()
        documents.append(
            {
                "content": document_file.read_text(encoding="utf-8"),
                "metadata": metadata,
                "acl": {
                    "visibility": args.acl_visibility,
                    "users": list(args.acl_user),
                    "groups": list(args.acl_group),
                },
            }
        )
    return {"documents": documents}


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv)
