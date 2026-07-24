from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from shlex import quote
from shlex import split as shlex_split
from typing import Protocol, TextIO, cast
from urllib.parse import quote as url_quote
from urllib.parse import urlencode

import httpx

from reactor.rag.ingestion_candidate_actions import RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE
from reactor.release.readiness_actions import (
    HARDENING_SUITE_REPORT_FILE,
    LANGSMITH_SYNC_RECOMMENDED_ENV,
    LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
    readiness_report_args_for_reports,
    release_readiness_command_for_reports,
)


@dataclass(frozen=True)
class AdminCliHttpResult:
    ok: bool
    status_code: int
    body: dict[str, object] | list[object] | None = None
    error: str | None = None


class AdminHttpProbe(Protocol):
    def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult: ...

    def post_json(
        self,
        path: str,
        *,
        headers: dict[str, str],
        body: dict[str, object],
    ) -> AdminCliHttpResult: ...

    def patch_json(
        self,
        path: str,
        *,
        headers: dict[str, str],
        body: dict[str, object],
    ) -> AdminCliHttpResult: ...


def path_segment(value: str) -> str:
    return url_quote(value, safe="")


class HttpAdminProbe:
    def __init__(self, *, base_url: str, timeout_seconds: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def get_json(self, path: str, headers: dict[str, str]) -> AdminCliHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.get(f"{self._base_url}{path}", headers=headers)
            return result_from_response(response)
        except httpx.HTTPError as error:
            return AdminCliHttpResult(ok=False, status_code=0, error=str(error))

    def post_json(
        self,
        path: str,
        *,
        headers: dict[str, str],
        body: dict[str, object],
    ) -> AdminCliHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(f"{self._base_url}{path}", headers=headers, json=body)
            return result_from_response(response)
        except httpx.HTTPError as error:
            return AdminCliHttpResult(ok=False, status_code=0, error=str(error))

    def patch_json(
        self,
        path: str,
        *,
        headers: dict[str, str],
        body: dict[str, object],
    ) -> AdminCliHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.patch(f"{self._base_url}{path}", headers=headers, json=body)
            return result_from_response(response)
        except httpx.HTTPError as error:
            return AdminCliHttpResult(ok=False, status_code=0, error=str(error))


def result_from_response(response: httpx.Response) -> AdminCliHttpResult:
    if response.status_code >= 400:
        error_body: dict[str, object] | list[object] | None = None
        try:
            parsed_error_body = response.json()
        except ValueError:
            parsed_error_body = None
        if isinstance(parsed_error_body, dict | list):
            error_body = cast(dict[str, object] | list[object], parsed_error_body)
        return AdminCliHttpResult(
            ok=False,
            status_code=response.status_code,
            body=error_body,
            error=response.text,
        )
    try:
        body = response.json()
    except ValueError:
        return AdminCliHttpResult(
            ok=False,
            status_code=response.status_code,
            error="invalid_response",
        )
    if not isinstance(body, dict | list):
        return AdminCliHttpResult(
            ok=False,
            status_code=response.status_code,
            error="invalid_response",
        )
    return AdminCliHttpResult(
        ok=True,
        status_code=response.status_code,
        body=cast(dict[str, object] | list[object], body),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reactor-admin",
        description="Inspect Reactor admin/operator diagnostics through the public API.",
    )
    parser.add_argument("--base-url", default="", help="Reactor API base URL")
    parser.add_argument("--tenant-id", default="", help="Tenant id header")
    parser.add_argument("--user-id", default="", help="User id header")
    parser.add_argument("--role", default="", help="Optional Reactor role header")
    parser.add_argument("--token", default="", help="Optional bearer token")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    subparsers = parser.add_subparsers(dest="command", required=True)

    diagnostics = subparsers.add_parser(
        "diagnostics",
        help="Fetch platform health and admin capabilities in one operator report",
    )
    diagnostics.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )
    diagnostics.add_argument(
        "--include-evals",
        action="store_true",
        help="Include eval run and pass-rate dashboard diagnostics.",
    )
    diagnostics.add_argument(
        "--include-tenant-dashboard",
        action="store_true",
        help="Include tenant run, usage, quality, tool, and cost dashboard diagnostics.",
    )
    diagnostics.add_argument(
        "--include-slack-activity",
        action="store_true",
        help="Include Slack channel and daily activity diagnostics.",
    )
    diagnostics.add_argument("--eval-days", type=int, default=30, help="Eval dashboard window")
    diagnostics.add_argument("--eval-limit", type=int, default=5, help="Maximum eval runs")
    diagnostics.add_argument("--slack-days", type=int, default=30, help="Slack activity window")

    state_history = subparsers.add_parser(
        "state-history",
        help="Fetch LangGraph checkpoint state history for a persisted run",
    )
    state_history.add_argument("run_id")
    state_history.add_argument("--limit", type=int, default=25, help="Maximum checkpoints")
    state_history.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    feedback = subparsers.add_parser(
        "feedback",
        help="List feedback review inbox items and eval promotion next actions",
    )
    feedback.add_argument("--feedback-id", default="", help="Fetch one feedback record by id")
    feedback.add_argument("--rating", default="", help="Optional rating filter")
    feedback.add_argument("--source", default="", help="Optional feedback source filter")
    feedback.add_argument("--case-id", default="", help="Optional eval case id filter")
    feedback.add_argument(
        "--review-status",
        choices=("inbox", "done", "all"),
        default="inbox",
        help="Feedback review status filter; use all to include closed records",
    )
    feedback.add_argument(
        "--tag",
        action="append",
        dest="tags",
        default=None,
        help="Feedback or review tag filter; may be repeated.",
    )
    feedback.add_argument("--limit", type=int, default=50, help="Maximum feedback records")
    feedback.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    feedback_export = subparsers.add_parser(
        "feedback-export",
        help="Export filtered feedback records with review/eval handoff actions",
    )
    feedback_export.add_argument("--rating", default="", help="Optional rating filter")
    feedback_export.add_argument("--source", default="", help="Optional feedback source filter")
    feedback_export.add_argument("--case-id", default="", help="Optional eval case id filter")
    feedback_export.add_argument(
        "--review-status",
        choices=("inbox", "done", "all"),
        default="inbox",
        help="Feedback review status filter; use all to include closed records",
    )
    feedback_export.add_argument(
        "--tag",
        action="append",
        dest="tags",
        default=None,
        help="Feedback or review tag filter; may be repeated.",
    )
    feedback_export.add_argument("--limit", type=int, default=100, help="Maximum feedback records")
    feedback_export.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    feedback_submit = subparsers.add_parser(
        "feedback-submit",
        help="Submit a feedback record through the public API for review and eval promotion",
    )
    feedback_submit.add_argument("--rating", required=True, help="Feedback rating")
    feedback_submit.add_argument("--query", default="", help="Prompt or query text")
    feedback_submit.add_argument("--response", default="", help="Answer text")
    feedback_submit.add_argument("--comment", default="", help="Optional reviewer comment")
    feedback_submit.add_argument("--source", default="", help="Optional feedback source")
    feedback_submit.add_argument("--run-id", default="", help="Optional source run id")
    feedback_submit.add_argument("--session-id", default="", help="Optional source session id")
    feedback_submit.add_argument("--intent", default="", help="Optional intent")
    feedback_submit.add_argument("--domain", default="", help="Optional domain")
    feedback_submit.add_argument("--model", default="", help="Optional model")
    feedback_submit.add_argument(
        "--tag",
        action="append",
        dest="tags",
        default=None,
        help="Feedback tag to attach; may be repeated.",
    )
    feedback_submit.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    rag_candidates = subparsers.add_parser(
        "rag-candidates",
        help="List RAG ingestion review candidates and follow-up next actions",
    )
    rag_candidates.add_argument("--status", default="", help="Optional candidate status filter")
    rag_candidates.add_argument("--channel", default="", help="Optional source channel filter")
    rag_candidates.add_argument("--limit", type=int, default=50, help="Maximum candidates")
    rag_candidates.add_argument(
        "--tag",
        action="append",
        dest="tags",
        help="Candidate workflow tag filter; may be repeated.",
    )
    rag_candidates.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    rag_candidate_approve = subparsers.add_parser(
        "rag-candidate-approve",
        help="Approve one RAG ingestion candidate and show eval follow-up next action",
    )
    rag_candidate_approve.add_argument("candidate_id")
    rag_candidate_approve.add_argument("--comment", default="", help="Optional review comment")
    rag_candidate_approve.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    rag_candidate_reject = subparsers.add_parser(
        "rag-candidate-reject",
        help="Reject one RAG ingestion candidate after review",
    )
    rag_candidate_reject.add_argument("candidate_id")
    rag_candidate_reject.add_argument("--comment", default="", help="Optional review comment")
    rag_candidate_reject.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    feedback_review = subparsers.add_parser(
        "feedback-review",
        help="Update feedback review status through the admin API",
    )
    feedback_review.add_argument("feedback_id")
    feedback_review.add_argument(
        "--if-match",
        required=True,
        help="Expected feedback version for optimistic review updates.",
    )
    feedback_review.add_argument("--status", default="", help="Review status to apply")
    feedback_review.add_argument(
        "--tag",
        action="append",
        dest="tags",
        default=None,
        help="Review tag to apply; may be repeated.",
    )
    feedback_review.add_argument("--note", default="", help="Optional review note")
    feedback_review.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )
    feedback_bulk_review = subparsers.add_parser(
        "feedback-bulk-review",
        help="Bulk update feedback review status through the admin API",
    )
    feedback_bulk_review.add_argument("feedback_ids", nargs="*")
    feedback_bulk_review.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        default=None,
        help="Resolve feedback records whose eval promotion next action targets this case id.",
    )
    feedback_bulk_review.add_argument(
        "--candidate-tag",
        action="append",
        dest="candidate_tags",
        default=None,
        help="Resolve inbox feedback records tagged for this RAG ingestion candidate.",
    )
    feedback_bulk_review.add_argument(
        "--source",
        default="",
        help="Optional feedback source filter when resolving --case-id or --candidate-tag.",
    )
    feedback_bulk_review.add_argument("--status", default="", help="Review status to apply")
    feedback_bulk_review.add_argument(
        "--tag",
        action="append",
        dest="tags",
        default=None,
        help="Review tag to apply; may be repeated.",
    )
    feedback_bulk_review.add_argument("--note", default="", help="Optional review note")
    feedback_bulk_review.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )
    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    http_probe: AdminHttpProbe | None = None,
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
    probe = http_probe or HttpAdminProbe(base_url=base_url, timeout_seconds=args.timeout)
    headers = request_headers(args, environ, tenant_id=tenant_id, user_id=user_id)

    result = dispatch_command(args, probe, headers, base_url=base_url.rstrip("/"))
    if not result.ok:
        stderr.write(admin_request_failure_message(result))
        return 1

    output_body = public_command_body(args.command, result.body)
    if getattr(args, "output", "json") == "table":
        stdout.write(format_table(args.command, output_body))
    else:
        stdout.write(json.dumps(output_body, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


def format_table(command: str, body: dict[str, object] | list[object] | None) -> str:
    if command == "state-history":
        return format_state_history_table(body)
    if command == "feedback":
        return format_feedback_table(body)
    if command == "feedback-submit":
        return format_feedback_table(body)
    if command == "feedback-export":
        return format_feedback_table(body)
    if command == "rag-candidates":
        return format_rag_candidates_table(body)
    if command == "rag-candidate-approve":
        return format_rag_candidates_table(body)
    if command == "rag-candidate-reject":
        return format_rag_candidates_table(body)
    if command == "feedback-review":
        return format_feedback_review_table(body)
    if command == "feedback-bulk-review":
        return format_feedback_bulk_review_table(body)
    return format_diagnostics_table(body)


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
    probe: AdminHttpProbe,
    headers: dict[str, str],
    *,
    base_url: str,
) -> AdminCliHttpResult:
    if args.command == "diagnostics":
        return diagnostics_report(
            probe=probe,
            headers=headers,
            base_url=base_url,
            include_evals=bool(args.include_evals),
            eval_days=args.eval_days,
            eval_limit=args.eval_limit,
            include_tenant_dashboard=bool(args.include_tenant_dashboard),
            include_slack_activity=bool(args.include_slack_activity),
            slack_days=args.slack_days,
        )
    if args.command == "state-history":
        query = urlencode({"limit": args.limit})
        return probe.get_json(
            f"/v1/admin/debug/state-history/{path_segment(args.run_id)}?{query}",
            headers=headers,
        )
    if args.command == "feedback":
        if args.feedback_id:
            return probe.get_json(
                f"/v1/feedback/{path_segment(args.feedback_id)}",
                headers=headers,
            )
        query_args: dict[str, object] = {}
        if args.rating:
            query_args["rating"] = args.rating
        if args.source:
            query_args["source"] = args.source
        if args.review_status and args.review_status != "all":
            query_args["reviewStatus"] = args.review_status
        if args.case_id:
            query_args["caseId"] = args.case_id
        query_args["limit"] = args.limit
        if args.tags is not None:
            query_args["tag"] = list(args.tags)
        return probe.get_json(f"/v1/feedback?{urlencode(query_args, doseq=True)}", headers=headers)
    if args.command == "feedback-export":
        query_args: dict[str, object] = {}
        if args.rating:
            query_args["rating"] = args.rating
        if args.source:
            query_args["source"] = args.source
        if args.review_status and args.review_status != "all":
            query_args["reviewStatus"] = args.review_status
        if args.case_id:
            query_args["caseId"] = args.case_id
        query_args["limit"] = args.limit
        if args.tags is not None:
            query_args["tag"] = list(args.tags)
        return probe.get_json(
            f"/v1/feedback/export?{urlencode(query_args, doseq=True)}",
            headers=headers,
        )
    if args.command == "feedback-submit":
        return probe.post_json(
            "/v1/feedback",
            headers=headers,
            body=feedback_submission_body(args),
        )
    if args.command == "rag-candidates":
        query_args: dict[str, object] = {"status": args.status or "PENDING"}
        if args.channel:
            query_args["channel"] = args.channel
        query_args["limit"] = args.limit
        if args.tags is not None:
            query_args["tag"] = list(args.tags)
        query = urlencode(query_args, doseq=True)
        return probe.get_json(f"/v1/rag-ingestion/candidates?{query}", headers=headers)
    if args.command == "rag-candidate-approve":
        body = {"comment": args.comment} if args.comment else {}
        return probe.post_json(
            f"/v1/rag-ingestion/candidates/{path_segment(args.candidate_id)}/approve",
            headers=headers,
            body=body,
        )
    if args.command == "rag-candidate-reject":
        body = {"comment": args.comment} if args.comment else {}
        return probe.post_json(
            f"/v1/rag-ingestion/candidates/{path_segment(args.candidate_id)}/reject",
            headers=headers,
            body=body,
        )
    if args.command == "feedback-review":
        request_body: dict[str, object] = {}
        if args.status:
            request_body["status"] = args.status
        if args.tags is not None:
            request_body["tags"] = list(args.tags)
        if args.note:
            request_body["note"] = args.note
        current = probe.get_json(f"/v1/feedback/{path_segment(args.feedback_id)}", headers=headers)
        if current_feedback_matches_review_resolution(
            current,
            feedback_id=args.feedback_id,
            status=args.status,
            tags=args.tags,
            note=args.note,
        ):
            return current
        return probe.patch_json(
            f"/v1/feedback/{path_segment(args.feedback_id)}",
            headers={**headers, "If-Match": args.if_match},
            body=request_body,
        )
    if args.command == "feedback-bulk-review":
        feedback_ids = list(args.feedback_ids)
        explicit_feedback_ids = dedupe_strings(feedback_ids)
        case_ids = list(args.case_ids or [])
        candidate_tags = list(args.candidate_tags or [])
        effective_note = args.note or (
            RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE
            if feedback_bulk_review_requires_langsmith_note(
                status=args.status,
                tags=args.tags,
            )
            else ""
        )
        already_done_ids: list[str] = []
        already_done_details: list[dict[str, object]] = []
        if case_ids:
            resolved = resolve_feedback_ids_for_case_ids(
                probe=probe,
                headers=headers,
                case_ids=case_ids,
                source=args.source,
                review_status="inbox",
            )
            if not resolved.ok:
                return resolved
            resolved_feedback_ids = feedback_ids_from_result(resolved)
            if not resolved_feedback_ids:
                resolved = resolve_feedback_ids_for_case_ids(
                    probe=probe,
                    headers=headers,
                    case_ids=case_ids,
                    source=args.source,
                    review_status="done",
                )
                if not resolved.ok and resolved.status_code != 404:
                    return resolved
                if resolved.ok:
                    resolved_feedback_ids = feedback_ids_from_result(resolved)
                    matching_done = feedback_review_details_matching_review_resolution(
                        resolved,
                        status=args.status,
                        tags=args.tags,
                        note=effective_note,
                    )
                    already_done_ids.extend(
                        str(item["feedbackId"])
                        for item in matching_done
                        if isinstance(item.get("feedbackId"), str)
                    )
                    already_done_details.extend(matching_done)
            if not resolved_feedback_ids:
                return AdminCliHttpResult(
                    ok=False,
                    status_code=404,
                    body={
                        "detail": {
                            "message": "no inbox feedback matched case id: "
                            f"{','.join(dedupe_strings(case_ids))}",
                            "reviewQueueAction": feedback_case_review_queue_action(
                                case_ids,
                                source=args.source,
                            ),
                        }
                    },
                )
            feedback_ids.extend(resolved_feedback_ids)
        if candidate_tags:
            resolved = resolve_feedback_ids_for_candidate_tags(
                probe=probe,
                headers=headers,
                candidate_tags=candidate_tags,
                source=args.source,
                review_status="inbox",
            )
            if not resolved.ok:
                return resolved
            resolved_feedback_ids = feedback_ids_from_result(resolved)
            if not resolved_feedback_ids:
                resolved = resolve_feedback_ids_for_candidate_tags(
                    probe=probe,
                    headers=headers,
                    candidate_tags=candidate_tags,
                    source=args.source,
                    review_status="done",
                )
                if not resolved.ok and resolved.status_code != 404:
                    return resolved
                if resolved.ok:
                    resolved_feedback_ids = feedback_ids_from_result(resolved)
                    matching_done = feedback_review_details_matching_review_resolution(
                        resolved,
                        status=args.status,
                        tags=args.tags,
                        note=effective_note,
                    )
                    already_done_ids.extend(
                        str(item["feedbackId"])
                        for item in matching_done
                        if isinstance(item.get("feedbackId"), str)
                    )
                    already_done_details.extend(matching_done)
            if not resolved_feedback_ids:
                return AdminCliHttpResult(
                    ok=False,
                    status_code=404,
                    body={
                        "detail": {
                            "message": "no inbox feedback matched candidate tag: "
                            f"{','.join(dedupe_strings(candidate_tags))}",
                            "reviewQueueAction": feedback_candidate_review_queue_action(
                                candidate_tags,
                                source=args.source,
                            ),
                        }
                    },
                )
            feedback_ids.extend(resolved_feedback_ids)
        if explicit_feedback_ids:
            matching_done = resolve_matching_done_feedback_details(
                probe=probe,
                headers=headers,
                feedback_ids=explicit_feedback_ids,
                status=args.status,
                tags=args.tags,
                note=effective_note,
            )
            already_done_ids.extend(
                str(item["feedbackId"])
                for item in matching_done
                if isinstance(item.get("feedbackId"), str)
            )
            already_done_details.extend(matching_done)
        feedback_ids = dedupe_strings(feedback_ids)
        if not feedback_ids:
            return AdminCliHttpResult(
                ok=False,
                status_code=400,
                body={
                    "detail": {
                        "message": (
                            "feedback-bulk-review requires feedback ids, --case-id, "
                            "or --candidate-tag"
                        )
                    }
                },
            )
        already_done_ids = dedupe_strings(already_done_ids)
        already_done_id_set = set(already_done_ids)
        pending_feedback_ids = [
            feedback_id for feedback_id in feedback_ids if feedback_id not in already_done_id_set
        ]
        request_body: dict[str, object] = {"ids": pending_feedback_ids}
        if args.status:
            request_body["status"] = args.status
        if args.tags is not None:
            request_body["tags"] = list(args.tags)
        if effective_note:
            request_body["note"] = effective_note
        if feedback_ids and not pending_feedback_ids:
            body: dict[str, object] = {
                "updated": [],
                "alreadyDone": feedback_ids,
                "failed": [],
            }
            if already_done_details:
                details = feedback_bulk_review_already_done_details_for_output(
                    already_done_details,
                    include_all=getattr(args, "output", "json") == "table",
                )
                if details:
                    body["alreadyDoneDetails"] = details
            return AdminCliHttpResult(
                ok=True,
                status_code=200,
                body=body,
            )
        result = probe.post_json(
            "/v1/feedback/bulk-update",
            headers=headers,
            body=request_body,
        )
        result = result_with_already_done_ids(result, already_done_ids)
        if already_done_details:
            return result_with_already_done_details(
                result,
                already_done_details,
                include_all=getattr(args, "output", "json") == "table",
            )
        return result
    raise AssertionError(f"unsupported command: {args.command}")


def resolve_feedback_ids_for_case_ids(
    *,
    probe: AdminHttpProbe,
    headers: dict[str, str],
    case_ids: Sequence[str],
    source: str = "",
    review_status: str = "inbox",
) -> AdminCliHttpResult:
    clean_case_ids = dedupe_strings(case_ids)
    if not clean_case_ids:
        return AdminCliHttpResult(ok=True, status_code=200, body={"ids": []})
    ids: list[str] = []
    matched_items: list[object] = []
    for case_id in clean_case_ids:
        query_args: dict[str, object] = {"reviewStatus": review_status}
        if source.strip():
            query_args["source"] = source.strip()
        query_args["caseId"] = case_id
        query_args["limit"] = 100
        query = urlencode(query_args)
        result = probe.get_json(f"/v1/feedback?{query}", headers=headers)
        if not result.ok:
            return result
        body = result.body
        items = body.get("items") if isinstance(body, Mapping) else None
        if not isinstance(items, Sequence) or isinstance(items, str | bytes | bytearray):
            continue
        for item in cast(Sequence[object], items):
            if not isinstance(item, Mapping):
                continue
            item_mapping = cast(Mapping[object, object], item)
            if not feedback_item_matches_case_id(item_mapping, [case_id]):
                continue
            feedback_id = item_mapping.get("feedbackId") or item_mapping.get("feedback_id")
            if isinstance(feedback_id, str) and feedback_id.strip():
                ids.append(feedback_id.strip())
                matched_items.append(item_mapping)
    return AdminCliHttpResult(
        ok=True,
        status_code=200,
        body={"ids": dedupe_strings(ids), "items": matched_items},
    )


def resolve_feedback_ids_for_candidate_tags(
    *,
    probe: AdminHttpProbe,
    headers: dict[str, str],
    candidate_tags: Sequence[str],
    source: str = "",
    review_status: str = "inbox",
) -> AdminCliHttpResult:
    clean_candidate_tags = dedupe_strings(candidate_tags)
    if not clean_candidate_tags:
        return AdminCliHttpResult(ok=True, status_code=200, body={"ids": []})
    ids: list[str] = []
    matched_items: list[object] = []
    for candidate_tag in clean_candidate_tags:
        query_args: dict[str, object] = {
            "reviewStatus": review_status,
        }
        if source.strip():
            query_args["source"] = source.strip()
        query_args["limit"] = 100
        query_args["tag"] = ["collection:rag-ingestion-candidate", candidate_tag]
        query = urlencode(
            query_args,
            doseq=True,
        )
        result = probe.get_json(f"/v1/feedback?{query}", headers=headers)
        if not result.ok:
            return result
        body = result.body
        items = body.get("items") if isinstance(body, Mapping) else None
        if not isinstance(items, Sequence) or isinstance(items, str | bytes | bytearray):
            continue
        for item in cast(Sequence[object], items):
            if not isinstance(item, Mapping):
                continue
            item_mapping = cast(Mapping[object, object], item)
            if not feedback_item_matches_candidate_tag(item_mapping, candidate_tag):
                continue
            feedback_id = item_mapping.get("feedbackId") or item_mapping.get("feedback_id")
            if isinstance(feedback_id, str) and feedback_id.strip():
                ids.append(feedback_id.strip())
                matched_items.append(item_mapping)
    return AdminCliHttpResult(
        ok=True,
        status_code=200,
        body={"ids": dedupe_strings(ids), "items": matched_items},
    )


def feedback_candidate_review_queue_action(
    candidate_tags: Sequence[str],
    *,
    source: str = "",
) -> str:
    tags = ["collection:rag-ingestion-candidate", *dedupe_strings(candidate_tags)]
    tag_args = " ".join(f"--tag {quote(tag)}" for tag in tags if tag.strip())
    source_arg = f"--source {quote(source.strip())} " if source.strip() else ""
    return (
        f"reactor-admin feedback --review-status all {source_arg}"
        f"{tag_args} --limit 10 --output table"
    )


def feedback_case_review_queue_action(case_ids: Sequence[str], *, source: str = "") -> str:
    source_arg = f"--source {quote(source.strip())} " if source.strip() else ""
    case_id = next((item for item in dedupe_strings(case_ids) if item.strip()), "")
    if not case_id:
        return f"reactor-admin feedback --review-status all {source_arg}--limit 10 --output table"
    return (
        f"reactor-admin feedback --review-status all {source_arg}"
        f"--case-id {quote(case_id)} "
        "--limit 10 --output table"
    )


def resolve_matching_done_feedback_details(
    *,
    probe: AdminHttpProbe,
    headers: dict[str, str],
    feedback_ids: Sequence[str],
    status: str,
    tags: Sequence[str] | None,
    note: str,
) -> list[dict[str, object]]:
    items: list[Mapping[object, object]] = []
    for feedback_id in dedupe_strings(feedback_ids):
        result = probe.get_json(f"/v1/feedback/{path_segment(feedback_id)}", headers=headers)
        if not result.ok or not isinstance(result.body, Mapping):
            continue
        items.append(cast(Mapping[object, object], result.body))
    if not items:
        return []
    return feedback_review_details_matching_review_resolution(
        AdminCliHttpResult(ok=True, status_code=200, body={"items": items}),
        status=status,
        tags=tags,
        note=note,
    )


def feedback_ids_from_result(result: AdminCliHttpResult) -> list[str]:
    body = result.body
    if not isinstance(body, Mapping):
        return []
    ids = body.get("ids")
    if not isinstance(ids, Sequence) or isinstance(ids, str | bytes | bytearray):
        return []
    return [item.strip() for item in cast(Sequence[object], ids) if isinstance(item, str)]


def feedback_ids_matching_review_resolution(
    result: AdminCliHttpResult,
    *,
    status: str,
    tags: Sequence[str] | None,
    note: str,
) -> list[str]:
    return [
        str(item["feedbackId"])
        for item in feedback_review_details_matching_review_resolution(
            result,
            status=status,
            tags=tags,
            note=note,
        )
        if isinstance(item.get("feedbackId"), str)
    ]


def feedback_review_details_matching_review_resolution(
    result: AdminCliHttpResult,
    *,
    status: str,
    tags: Sequence[str] | None,
    note: str,
) -> list[dict[str, object]]:
    body = result.body
    if not isinstance(body, Mapping):
        return []
    items = body.get("items")
    if not isinstance(items, Sequence) or isinstance(items, str | bytes | bytearray):
        return []
    expected_status = status.strip().lower()
    expected_tags = {tag.strip() for tag in tags or () if tag.strip()}
    matching: list[dict[str, object]] = []
    for item in cast(Sequence[object], items):
        if not isinstance(item, Mapping):
            continue
        item_mapping = cast(Mapping[object, object], item)
        feedback_id = item_mapping.get("feedbackId") or item_mapping.get("feedback_id")
        if not isinstance(feedback_id, str) or not feedback_id.strip():
            continue
        review_status = item_mapping.get("reviewStatus") or item_mapping.get("review_status")
        if not isinstance(review_status, str) or review_status.strip().lower() != expected_status:
            continue
        review_tags = item_mapping.get("reviewTags") or item_mapping.get("review_tags")
        if expected_tags:
            if not isinstance(review_tags, Sequence) or isinstance(
                review_tags,
                str | bytes | bytearray,
            ):
                continue
            actual_tags = {
                tag.strip()
                for tag in cast(Sequence[object], review_tags)
                if isinstance(tag, str) and tag.strip()
            }
            if not expected_tags.issubset(actual_tags):
                continue
        review_note = item_mapping.get("reviewNote") or item_mapping.get("review_note")
        if note and (
            not isinstance(review_note, str)
            or not feedback_review_note_matches(review_note.strip(), note)
        ):
            continue
        matching.append(feedback_review_detail_from_item(item_mapping))
    return matching


def feedback_review_detail_from_item(item: Mapping[object, object]) -> dict[str, object]:
    detail: dict[str, object] = {}
    feedback_id = item.get("feedbackId") or item.get("feedback_id")
    if isinstance(feedback_id, str) and feedback_id.strip():
        detail["feedbackId"] = feedback_id.strip()
    review_status = item.get("reviewStatus") or item.get("review_status")
    if isinstance(review_status, str) and review_status.strip():
        detail["reviewStatus"] = review_status.strip()
    review_tags = item.get("reviewTags") or item.get("review_tags")
    if isinstance(review_tags, Sequence) and not isinstance(
        review_tags,
        str | bytes | bytearray,
    ):
        tags = [
            tag.strip()
            for tag in cast(Sequence[object], review_tags)
            if isinstance(tag, str) and tag.strip()
        ]
        if tags:
            detail["reviewTags"] = tags
    review_note = item.get("reviewNote") or item.get("review_note")
    if isinstance(review_note, str) and review_note.strip():
        detail["reviewNote"] = review_note.strip()
    source = item.get("source") or item.get("feedbackSource") or item.get("feedback_source")
    if isinstance(source, str) and source.strip():
        detail["feedbackSource"] = source.strip()
    readiness_report_arg = item.get("readinessReportArg")
    if isinstance(readiness_report_arg, str) and readiness_report_arg.strip():
        detail["readinessReportArg"] = readiness_report_arg.strip()
    required_readiness_reports = item.get("requiredReadinessReports")
    if isinstance(required_readiness_reports, Sequence) and not isinstance(
        required_readiness_reports,
        str | bytes | bytearray,
    ):
        reports = [
            report.strip()
            for report in cast(Sequence[object], required_readiness_reports)
            if isinstance(report, str) and report.strip()
        ]
        if reports:
            detail["requiredReadinessReports"] = reports
    readiness_reports = item.get("readinessReports")
    if isinstance(readiness_reports, Mapping):
        report_paths = {
            report_name.strip(): report_file.strip()
            for report_name, report_file in cast(Mapping[object, object], readiness_reports).items()
            if isinstance(report_name, str)
            and report_name.strip()
            and isinstance(report_file, str)
            and report_file.strip()
        }
        if report_paths:
            detail["readinessReports"] = report_paths
    next_action_fields = feedback_detail_next_action_fields(item.get("nextActions"))
    detail.update(next_action_fields)
    if feedback_review_detail_uses_langsmith_review(detail):
        review_note = detail.get("reviewNote")
        if isinstance(review_note, str) and feedback_review_note_matches(
            review_note,
            RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
        ):
            detail["reviewNote"] = RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE
    langsmith_review_args = feedback_langsmith_review_args(detail)
    if langsmith_review_args:
        detail["langsmithReviewArgs"] = langsmith_review_args
        langsmith_review_command = feedback_langsmith_review_command(
            detail,
            review_args=langsmith_review_args,
        )
        if langsmith_review_command:
            detail["langsmithReviewCommand"] = langsmith_review_command
        for key, value in feedback_langsmith_readiness_metadata(detail).items():
            if key not in detail:
                detail[key] = value
    return detail


def feedback_review_note_matches(actual_note: str, expected_note: str) -> bool:
    actual = actual_note.strip()
    expected = expected_note.strip()
    if actual == expected:
        return True
    legacy_prefix = RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE.partition(
        " Required readiness reports:"
    )[0]
    return expected == RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE and actual == legacy_prefix


def feedback_review_detail_uses_langsmith_review(detail: Mapping[str, object]) -> bool:
    review_status = detail.get("reviewStatus")
    if not isinstance(review_status, str) or review_status.strip().lower() != "done":
        return False
    review_tags = detail.get("reviewTags")
    if not isinstance(review_tags, Sequence) or isinstance(
        review_tags,
        str | bytes | bytearray,
    ):
        return False
    normalized_tags = {
        tag.strip().lower()
        for tag in cast(Sequence[object], review_tags)
        if isinstance(tag, str) and tag.strip()
    }
    return {"promoted", "langsmith"}.issubset(normalized_tags)


def feedback_langsmith_report_file(detail: Mapping[str, object]) -> str:
    eval_case_id = detail.get("evalCaseId")
    if not isinstance(eval_case_id, str) or not eval_case_id.startswith("case_rag_candidate_"):
        return ""
    return f"artifacts/langsmith/rag-ingestion-candidate-{eval_case_id}.json"


def feedback_langsmith_readiness_metadata(detail: Mapping[str, object]) -> dict[str, object]:
    report_file = feedback_langsmith_report_file(detail)
    if not report_file:
        return {}
    required_reports = ["hardening_suite", "langsmith_eval_sync"]
    readiness_reports = {
        "hardening_suite": HARDENING_SUITE_REPORT_FILE,
        "langsmith_eval_sync": report_file,
    }
    return {
        "readinessReportArg": readiness_report_args_for_reports(
            required_reports=required_reports,
            report_files=readiness_reports,
        ),
        "requiredReadinessReports": required_reports,
        "requiredEnvAnyOf": LANGSMITH_SYNC_REQUIRED_ENV_ANY_OF,
        "recommendedEnv": LANGSMITH_SYNC_RECOMMENDED_ENV,
        "readinessReports": readiness_reports,
        "releaseReadinessCommand": release_readiness_command_for_reports(
            required_reports=required_reports,
            report_files=readiness_reports,
        ),
    }


def feedback_langsmith_review_command(
    detail: Mapping[str, object],
    *,
    review_args: str,
) -> str:
    report_file = feedback_langsmith_report_file(detail)
    if not report_file:
        return ""
    return (
        "uv run reactor-langsmith-eval-sync "
        "--suite-file evals/regression/rag-ingestion-candidate.json "
        "--dataset-name reactor-rag-ingestion-candidate --dry-run "
        f"--report-file {quote(report_file)} "
        f"{review_args} --output table"
    )


def feedback_langsmith_review_args(detail: Mapping[str, object]) -> str:
    review_status = detail.get("reviewStatus")
    if not isinstance(review_status, str) or review_status.strip().lower() != "done":
        return ""
    review_tags = detail.get("reviewTags")
    if not isinstance(review_tags, Sequence) or isinstance(
        review_tags,
        str | bytes | bytearray,
    ):
        return ""
    tags = [
        tag.strip()
        for tag in cast(Sequence[object], review_tags)
        if isinstance(tag, str) and tag.strip()
    ]
    normalized_tags = {tag.lower() for tag in tags}
    if not {"promoted", "langsmith"}.issubset(normalized_tags):
        return ""
    review_note = detail.get("reviewNote")
    if (
        not isinstance(review_note, str)
        or review_note.strip() != RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE
    ):
        return ""
    tag_args = " ".join(f"--feedback-review-tag {quote(tag)}" for tag in tags)
    return (
        f"--feedback-review-status {quote(review_status.strip())} "
        f"{tag_args} "
        f"--feedback-review-note {quote(review_note.strip())}"
    )


def feedback_detail_next_action_fields(value: object) -> dict[str, str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return {}
    for item in cast(Sequence[object], value):
        if not isinstance(item, Mapping):
            continue
        mapping = cast(Mapping[object, object], item)
        fields: dict[str, str] = {}
        for source_key, target_key in (
            ("command", "nextAction"),
            ("evalCaseId", "evalCaseId"),
            ("sourceRunId", "sourceRunId"),
            ("feedbackSource", "feedbackSource"),
        ):
            field_value = mapping.get(source_key)
            if isinstance(field_value, str) and field_value.strip():
                fields[target_key] = field_value.strip()
        if fields:
            return fields
    return {}


def dedupe_feedback_review_details(
    details: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    seen: set[str] = set()
    deduped: list[dict[str, object]] = []
    for detail in details:
        feedback_id = detail.get("feedbackId")
        if not isinstance(feedback_id, str) or not feedback_id.strip():
            continue
        if feedback_id in seen:
            continue
        seen.add(feedback_id)
        deduped.append(dict(detail))
    return deduped


def result_with_already_done_ids(
    result: AdminCliHttpResult,
    already_done_ids: Sequence[str],
) -> AdminCliHttpResult:
    clean_already_done_ids = dedupe_strings(already_done_ids)
    if not clean_already_done_ids or not isinstance(result.body, Mapping):
        return result
    body = dict(result.body)
    existing = body.get("alreadyDone")
    merged = list(clean_already_done_ids)
    if isinstance(existing, Sequence) and not isinstance(existing, str | bytes | bytearray):
        merged.extend(item for item in cast(Sequence[object], existing) if isinstance(item, str))
    body["alreadyDone"] = dedupe_strings(merged)
    return AdminCliHttpResult(
        ok=result.ok,
        status_code=result.status_code,
        body=body,
        error=result.error,
    )


def result_with_already_done_details(
    result: AdminCliHttpResult,
    already_done_details: Sequence[Mapping[str, object]],
    *,
    include_all: bool,
) -> AdminCliHttpResult:
    details = feedback_bulk_review_already_done_details_for_output(
        already_done_details,
        include_all=include_all,
    )
    if not details or not isinstance(result.body, Mapping):
        return result
    body = dict(result.body)
    body["alreadyDoneDetails"] = details
    return AdminCliHttpResult(
        ok=result.ok,
        status_code=result.status_code,
        body=body,
        error=result.error,
    )


def feedback_bulk_review_already_done_details_for_output(
    details: Sequence[Mapping[str, object]],
    *,
    include_all: bool,
) -> list[dict[str, object]]:
    deduped = dedupe_feedback_review_details(details)
    if include_all:
        return deduped
    return [detail for detail in deduped if feedback_bulk_review_detail_has_release_handoff(detail)]


def feedback_bulk_review_detail_has_release_handoff(detail: Mapping[str, object]) -> bool:
    eval_case_id = detail.get("evalCaseId")
    if not isinstance(eval_case_id, str) or not eval_case_id.strip():
        return False
    review_tags = detail.get("reviewTags")
    if not isinstance(review_tags, Sequence) or isinstance(
        review_tags,
        str | bytes | bytearray,
    ):
        return False
    normalized_tags = {
        tag.strip().lower()
        for tag in cast(Sequence[object], review_tags)
        if isinstance(tag, str) and tag.strip()
    }
    return {"promoted", "langsmith"}.issubset(normalized_tags)


def current_feedback_matches_review_resolution(
    result: AdminCliHttpResult,
    *,
    feedback_id: str,
    status: str,
    tags: Sequence[str] | None,
    note: str,
) -> bool:
    if not result.ok or not isinstance(result.body, Mapping):
        return False
    matching_ids = feedback_ids_matching_review_resolution(
        AdminCliHttpResult(ok=True, status_code=200, body={"items": [result.body]}),
        status=status,
        tags=tags,
        note=note,
    )
    return feedback_id.strip() in set(matching_ids)


def feedback_item_matches_case_id(
    item: Mapping[object, object],
    case_ids: Sequence[str],
) -> bool:
    next_actions = item.get("nextActions") or item.get("next_actions")
    if not isinstance(next_actions, Sequence) or isinstance(next_actions, str | bytes | bytearray):
        return False
    for action in cast(Sequence[object], next_actions):
        if not isinstance(action, Mapping):
            continue
        action_mapping = cast(Mapping[object, object], action)
        eval_case_id = action_mapping.get("evalCaseId") or action_mapping.get("eval_case_id")
        if isinstance(eval_case_id, str) and eval_case_id.strip() in case_ids:
            return True
        command = action_mapping.get("command")
        if isinstance(command, str) and command_targets_case_id(command, case_ids):
            return True
    return False


def feedback_item_matches_candidate_tag(item: Mapping[object, object], candidate_tag: str) -> bool:
    clean_candidate_tag = candidate_tag.strip()
    if not clean_candidate_tag:
        return False
    tags = item.get("tags")
    review_tags = item.get("reviewTags") or item.get("review_tags")
    for value in (tags, review_tags):
        if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
            continue
        clean_tags = {tag.strip() for tag in cast(Sequence[object], value) if isinstance(tag, str)}
        if "collection:rag-ingestion-candidate" in clean_tags and clean_candidate_tag in clean_tags:
            return True
    next_actions = item.get("nextActions") or item.get("next_actions")
    if isinstance(next_actions, Sequence) and not isinstance(next_actions, str | bytes | bytearray):
        for action in cast(Sequence[object], next_actions):
            if not isinstance(action, Mapping):
                continue
            action_mapping = cast(Mapping[object, object], action)
            action_candidate_tag = action_mapping.get("candidateTag") or action_mapping.get(
                "candidate_tag"
            )
            if (
                isinstance(action_candidate_tag, str)
                and action_candidate_tag.strip() == clean_candidate_tag
            ):
                return True
            command = action_mapping.get("command")
            if isinstance(command, str) and command_targets_candidate_tag(
                command,
                clean_candidate_tag,
            ):
                return True
    return False


def command_targets_case_id(command: str, case_ids: Sequence[str]) -> bool:
    try:
        parts = shlex_split(command)
    except ValueError:
        return False
    for index, part in enumerate(parts[:-1]):
        if part == "--case-id" and parts[index + 1] in case_ids:
            return True
    return False


def command_targets_candidate_tag(command: str, candidate_tag: str) -> bool:
    try:
        parts = shlex_split(command)
    except ValueError:
        return False
    for index, part in enumerate(parts[:-1]):
        if part == "--candidate-tag" and parts[index + 1] == candidate_tag:
            return True
    return False


def feedback_bulk_review_requires_langsmith_note(
    *,
    status: str,
    tags: Sequence[str] | None,
) -> bool:
    if status.strip().lower() != "done":
        return False
    tag_set = {tag.strip() for tag in tags or () if tag.strip()}
    return {"promoted", "langsmith"}.issubset(tag_set)


def dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = value.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def diagnostics_report(
    *,
    probe: AdminHttpProbe,
    headers: dict[str, str],
    base_url: str,
    include_evals: bool = False,
    eval_days: int = 30,
    eval_limit: int = 5,
    include_tenant_dashboard: bool = False,
    include_slack_activity: bool = False,
    slack_days: int = 30,
) -> AdminCliHttpResult:
    healthz = probe.get_json("/healthz", headers=headers)
    readyz = probe.get_json("/readyz", headers=headers)
    platform_health = probe.get_json("/api/admin/platform/health", headers=headers)
    capabilities = probe.get_json("/api/admin/capabilities", headers=headers)
    body: dict[str, object] = {
        "status": (
            "passed"
            if healthz.ok and readyz.ok and platform_health.ok and capabilities.ok
            else "failed"
        ),
        "baseUrl": base_url,
        "healthz": diagnostic_section(healthz),
        "readyz": diagnostic_section(readyz),
        "platformHealth": diagnostic_section(platform_health),
        "capabilities": capabilities_section(capabilities),
    }
    if include_evals:
        body["evals"] = eval_dashboard_section(
            probe=probe,
            headers=headers,
            days=eval_days,
            limit=eval_limit,
        )
    if include_tenant_dashboard:
        body["tenantDashboard"] = tenant_dashboard_section(probe=probe, headers=headers)
    if include_slack_activity:
        body["slackActivity"] = slack_activity_section(
            probe=probe,
            headers=headers,
            days=slack_days,
        )
    return AdminCliHttpResult(
        ok=True,
        status_code=200,
        body=body,
    )


def admin_request_failure_message(result: AdminCliHttpResult) -> str:
    detail = error_detail_mapping(result.body)
    parts = [f"reactor-admin request failed ({result.status_code}): {result.error or ''}".rstrip()]
    message = detail.get("message")
    if isinstance(message, str) and message.strip():
        parts.append(f"message: {message.strip()}")
    for key in (
        "feedbackId",
        "expectedVersion",
        "currentVersion",
        "evalCaseId",
        "sourceRunId",
        "feedbackSource",
    ):
        value = detail.get(key)
        if isinstance(value, str | int) and not isinstance(value, bool):
            parts.append(f"{key}: {value}")
    for key in ("requiredAnyReviewTag", "requiredAllReviewTags", "resolutionTagsRequiringNote"):
        tags = string_sequence_detail(detail.get(key))
        if tags:
            parts.append(f"{key}: {','.join(tags)}")
    for key in ("readyNextActionIds", "blockedNextActionIds"):
        action_ids = string_sequence_detail(detail.get(key))
        if action_ids:
            parts.append(f"{key}: {','.join(action_ids)}")
    action_states = next_action_states_detail(detail.get("nextActionStates"))
    if action_states:
        parts.append(f"nextActionStates: {action_states}")
    readiness_report_arg = detail.get("readinessReportArg")
    if isinstance(readiness_report_arg, str) and readiness_report_arg.strip():
        parts.append(f"readinessReportArg: {readiness_report_arg.strip()}")
    required_readiness_reports = string_sequence_detail(detail.get("requiredReadinessReports"))
    if required_readiness_reports:
        parts.append(f"requiredReadinessReports: {','.join(required_readiness_reports)}")
    required_review_note = detail.get("requiredReviewNote")
    if isinstance(required_review_note, str) and required_review_note.strip():
        parts.append(f"requiredReviewNote: {required_review_note.strip()}")
    readiness_reports = detail.get("readinessReports")
    if isinstance(readiness_reports, Mapping):
        for report_name, report_file in sorted(
            cast(Mapping[object, object], readiness_reports).items(),
            key=lambda item: str(item[0]),
        ):
            if isinstance(report_name, str) and isinstance(report_file, str):
                report_name = report_name.strip()
                report_file = report_file.strip()
                if report_name and report_file:
                    parts.append(f"readinessReports.{report_name}: {report_file}")
    next_action = detail.get("nextAction")
    if isinstance(next_action, str) and next_action.strip():
        parts.append(f"nextAction: {next_action.strip()}")
    review_queue_action = detail.get("reviewQueueAction")
    if isinstance(review_queue_action, str) and review_queue_action.strip():
        parts.append(f"reviewQueueAction: {review_queue_action.strip()}")
    bulk_review_action = detail.get("bulkReviewAction")
    if isinstance(bulk_review_action, str) and bulk_review_action.strip():
        parts.append(f"bulkReviewAction: {bulk_review_action.strip()}")
    next_action_rows = feedback_next_action_rows([detail])
    if next_action_rows:
        parts.extend(next_action_rows)
    return "\n".join(parts) + "\n"


def error_detail_mapping(body: object) -> Mapping[object, object]:
    if not isinstance(body, Mapping):
        return {}
    detail = cast(Mapping[object, object], body).get("detail")
    if not isinstance(detail, Mapping):
        return {}
    return cast(Mapping[object, object], detail)


def string_sequence_detail(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [
        item.strip()
        for item in cast(Sequence[object], value)
        if isinstance(item, str) and item.strip()
    ]


def public_command_body(
    command: str,
    body: dict[str, object] | list[object] | None,
) -> dict[str, object] | list[object] | None:
    if command in {"feedback", "feedback-submit"}:
        return feedback_page_projection(body)
    if command == "feedback-export":
        return feedback_export_projection(body)
    if command == "feedback-review":
        return feedback_review_projection(body)
    return body


def feedback_submission_body(args: argparse.Namespace) -> dict[str, object]:
    body: dict[str, object] = {"rating": args.rating}
    optional_fields = (
        ("query", args.query),
        ("response", args.response),
        ("comment", args.comment),
        ("source", args.source),
        ("runId", args.run_id),
        ("sessionId", args.session_id),
        ("intent", args.intent),
        ("domain", args.domain),
        ("model", args.model),
    )
    for key, value in optional_fields:
        if value:
            body[key] = value
    if args.tags is not None:
        body["tags"] = list(args.tags)
    return body


def feedback_page_projection(
    body: dict[str, object] | list[object] | None,
) -> dict[str, object]:
    if not isinstance(body, Mapping):
        return {}
    typed_body = cast(Mapping[str, object], body)
    if table_value(typed_body, "feedbackId", "feedback_id") is not None:
        return feedback_record_projection(typed_body)
    projected: dict[str, object] = {}
    items = typed_body.get("items")
    if isinstance(items, Sequence) and not isinstance(items, str):
        projected_items: list[dict[str, object]] = []
        for item in cast(Sequence[object], items):
            if isinstance(item, Mapping):
                projected_items.append(feedback_record_projection(cast(Mapping[str, object], item)))
        projected["items"] = projected_items
    for key in ("nextCursor", "prevCursor", "approximateTotal"):
        if key in typed_body:
            projected[key] = typed_body[key]
    return projected


def feedback_export_projection(
    body: dict[str, object] | list[object] | None,
) -> dict[str, object]:
    if not isinstance(body, Mapping):
        return {}
    typed_body = cast(Mapping[str, object], body)
    projected = feedback_page_projection(body)
    for key in ("version", "source"):
        if key in typed_body:
            projected[key] = typed_body[key]
    return projected


def feedback_review_projection(
    body: dict[str, object] | list[object] | None,
) -> dict[str, object]:
    if not isinstance(body, Mapping):
        return {}
    return feedback_record_projection(cast(Mapping[str, object], body))


def feedback_record_projection(typed_body: Mapping[str, object]) -> dict[str, object]:
    projected: dict[str, object] = {}
    for key in (
        "feedbackId",
        "rating",
        "source",
        "tags",
        "reviewStatus",
        "reviewTags",
        "reviewedBy",
        "reviewNote",
        "version",
        "runId",
        "model",
        "promptVersion",
        "toolsUsed",
        "comment",
        "readyNextActionIds",
        "blockedNextActionIds",
        "nextActions",
    ):
        if key in typed_body:
            projected[key] = typed_body[key]
    return projected


def eval_dashboard_section(
    *,
    probe: AdminHttpProbe,
    headers: dict[str, str],
    days: int,
    limit: int,
) -> dict[str, object]:
    runs_query = urlencode({"days": days, "limit": limit})
    pass_rate_query = urlencode({"days": days})
    runs = probe.get_json(f"/api/admin/evals/runs?{runs_query}", headers=headers)
    pass_rate = probe.get_json(f"/api/admin/evals/pass-rate?{pass_rate_query}", headers=headers)
    return {
        "ok": runs.ok and pass_rate.ok,
        "statusCode": 200
        if runs.ok and pass_rate.ok
        else first_failed_status_code(runs, pass_rate),
        "runs": eval_runs_section(runs),
        "passRate": diagnostic_section(pass_rate),
    }


def tenant_dashboard_section(
    *,
    probe: AdminHttpProbe,
    headers: dict[str, str],
) -> dict[str, object]:
    overview = probe.get_json("/api/admin/tenant/overview", headers=headers)
    usage = probe.get_json("/api/admin/tenant/usage", headers=headers)
    quality = probe.get_json("/api/admin/tenant/quality", headers=headers)
    tools = probe.get_json("/api/admin/tenant/tools", headers=headers)
    cost = probe.get_json("/api/admin/tenant/cost", headers=headers)
    ok = overview.ok and usage.ok and quality.ok and tools.ok and cost.ok
    return {
        "ok": ok,
        "statusCode": 200
        if ok
        else first_failed_status_code(overview, usage, quality, tools, cost),
        "overview": diagnostic_section(overview),
        "usage": diagnostic_section(usage),
        "quality": diagnostic_section(quality),
        "tools": diagnostic_section(tools),
        "cost": diagnostic_section(cost),
    }


def slack_activity_section(
    *,
    probe: AdminHttpProbe,
    headers: dict[str, str],
    days: int,
) -> dict[str, object]:
    query = urlencode({"days": days})
    channels = probe.get_json(f"/api/admin/slack-activity/channels?{query}", headers=headers)
    daily = probe.get_json(f"/api/admin/slack-activity/daily?{query}", headers=headers)
    ok = channels.ok and daily.ok
    return {
        "ok": ok,
        "statusCode": 200 if ok else first_failed_status_code(channels, daily),
        "days": days,
        "channels": slack_channels_section(channels),
        "daily": slack_daily_section(daily),
    }


def first_failed_status_code(*results: AdminCliHttpResult) -> int:
    for result in results:
        if not result.ok:
            return result.status_code
    return 200


def eval_runs_section(result: AdminCliHttpResult) -> dict[str, object]:
    section = diagnostic_section(result)
    if result.ok and isinstance(result.body, Sequence) and not isinstance(result.body, str):
        section["runCount"] = len(cast(Sequence[object], result.body))
    return section


def slack_channels_section(result: AdminCliHttpResult) -> dict[str, object]:
    section = diagnostic_section(result)
    if result.ok and isinstance(result.body, Sequence) and not isinstance(result.body, str):
        section["channelCount"] = len(cast(Sequence[object], result.body))
    return section


def slack_daily_section(result: AdminCliHttpResult) -> dict[str, object]:
    section = diagnostic_section(result)
    if result.ok and isinstance(result.body, Sequence) and not isinstance(result.body, str):
        section["dayCount"] = len(cast(Sequence[object], result.body))
    return section


def diagnostic_section(result: AdminCliHttpResult) -> dict[str, object]:
    section: dict[str, object] = {
        "ok": result.ok,
        "statusCode": result.status_code,
    }
    if result.ok:
        section["body"] = result.body
    else:
        section["error"] = result.error
    return section


def capabilities_section(result: AdminCliHttpResult) -> dict[str, object]:
    section = diagnostic_section(result)
    if result.ok and isinstance(result.body, Mapping):
        paths = result.body.get("paths")
        if isinstance(paths, Sequence) and not isinstance(paths, str):
            path_values = cast(Sequence[object], paths)
            section["pathCount"] = sum(1 for path in path_values if isinstance(path, str))
    return section


def format_diagnostics_table(body: dict[str, object] | list[object] | None) -> str:
    if not isinstance(body, Mapping):
        return "SECTION  OK  STATUS  SUMMARY\n"
    rows: list[tuple[str, str, str, str]] = []
    for section_name in (
        "healthz",
        "readyz",
        "platformHealth",
        "capabilities",
        "evals",
        "tenantDashboard",
        "slackActivity",
    ):
        section = body.get(section_name)
        if not isinstance(section, Mapping):
            continue
        typed_section = cast(Mapping[object, object], section)
        rows.append(
            (
                section_name,
                section_ok(typed_section),
                section_status_code(typed_section),
                admin_diagnostic_summary(section_name, typed_section),
            )
        )
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


def format_state_history_table(body: dict[str, object] | list[object] | None) -> str:
    if not isinstance(body, Mapping):
        return "FIELD  VALUE\n"
    typed_body = cast(Mapping[str, object], body)
    entries = body.get("entries")
    raw_entries: Sequence[object] = (
        cast(Sequence[object], entries)
        if isinstance(entries, Sequence) and not isinstance(entries, str)
        else ()
    )
    entry_rows = [
        cast(Mapping[str, object], entry) for entry in raw_entries if isinstance(entry, Mapping)
    ]
    summary_rows = [
        ("run_id", table_value(typed_body, "runId", "run_id")),
        ("thread_id", table_value(typed_body, "threadId", "thread_id")),
        ("checkpoint_ns", table_value(typed_body, "checkpointNs", "checkpoint_ns")),
        (
            "resolved_checkpoint_ns",
            table_value(typed_body, "resolvedCheckpointNs", "resolved_checkpoint_ns"),
        ),
        ("namespace_fallback", bool_table_value(table_value(typed_body, "namespaceFallbackUsed"))),
        ("checkpoint_count", len(entry_rows)),
        ("latest_checkpoint_id", latest_checkpoint_id(entry_rows)),
        ("diagnoseAction", state_history_diagnose_next_action(typed_body)),
        ("nextAction", state_history_fork_next_action(typed_body, entry_rows)),
        ("replayAction", state_history_replay_next_action(typed_body)),
    ]
    summary_rows = [(field, value) for field, value in summary_rows if value is not None]
    summary_width = max([len("FIELD"), *(len(field) for field, _ in summary_rows)])
    lines = [f"{'FIELD':<{summary_width}}  VALUE"]
    lines.extend(f"{field:<{summary_width}}  {value}" for field, value in summary_rows)
    lines.extend(state_history_next_action_rows(typed_body))
    if not entry_rows:
        return "\n".join(lines) + "\n"

    rows = [
        (
            str(table_value(entry, "checkpointId", "checkpoint_id") or ""),
            str(table_value(entry, "parentCheckpointId", "parent_checkpoint_id") or ""),
            str(table_value(entry, "createdAt", "created_at") or ""),
            str(table_value(entry, "step") or ""),
            str(table_value(entry, "source") or ""),
            comma_separated_table_value(entry, "stateKeys", "state_keys") or "",
            comma_separated_table_value(entry, "updatedChannels", "updated_channels") or "",
            string_table_value(table_value(entry, "pendingWriteCount", "pending_write_count")),
            state_history_checkpoint_fork_action(
                typed_body,
                table_value(entry, "checkpointId", "checkpoint_id"),
            )
            or "",
        )
        for entry in entry_rows
    ]
    widths = (
        max([len("CHECKPOINT"), *(len(row[0]) for row in rows)]),
        max([len("PARENT"), *(len(row[1]) for row in rows)]),
        max([len("CREATED_AT"), *(len(row[2]) for row in rows)]),
        max([len("STEP"), *(len(row[3]) for row in rows)]),
        max([len("SOURCE"), *(len(row[4]) for row in rows)]),
        max([len("STATE_KEYS"), *(len(row[5]) for row in rows)]),
        max([len("UPDATED_CHANNELS"), *(len(row[6]) for row in rows)]),
        max([len("PENDING"), *(len(row[7]) for row in rows)]),
        max([len("FORK_ACTION"), *(len(row[8]) for row in rows)]),
    )
    lines.append("")
    lines.append(
        f"{'CHECKPOINT':<{widths[0]}}  {'PARENT':<{widths[1]}}  "
        f"{'CREATED_AT':<{widths[2]}}  {'STEP':<{widths[3]}}  "
        f"{'SOURCE':<{widths[4]}}  {'STATE_KEYS':<{widths[5]}}  "
        f"{'UPDATED_CHANNELS':<{widths[6]}}  {'PENDING':<{widths[7]}}  FORK_ACTION"
    )
    lines.extend(
        f"{checkpoint:<{widths[0]}}  {parent:<{widths[1]}}  "
        f"{created_at:<{widths[2]}}  {step:<{widths[3]}}  "
        f"{source:<{widths[4]}}  {state_keys:<{widths[5]}}  "
        f"{updated_channels:<{widths[6]}}  {pending:<{widths[7]}}  {fork_action}"
        for (
            checkpoint,
            parent,
            created_at,
            step,
            source,
            state_keys,
            updated_channels,
            pending,
            fork_action,
        ) in rows
    )
    return "\n".join(lines) + "\n"


def format_feedback_table(body: dict[str, object] | list[object] | None) -> str:
    if not isinstance(body, Mapping):
        return (
            "ID  RATING  SOURCE  REVIEW  REVIEW_TAGS  VERSION  RUN  MODEL  PROMPT  TOOLS  "
            "COMMENT  REVIEW_NOTE  NEXT_ACTION\n"
        )
    items = body.get("items")
    raw_items: Sequence[object] = (
        cast(Sequence[object], items)
        if isinstance(items, Sequence) and not isinstance(items, str)
        else ()
    )
    if not raw_items and table_value(body, "feedbackId", "feedback_id") is not None:
        raw_items = (body,)
    rows: list[tuple[str, str, str, str, str, str, str, str, str, str, str, str, str]] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        typed_item = {str(key): value for key, value in cast(Mapping[object, object], item).items()}
        rows.append(
            (
                str(table_value(typed_item, "feedbackId", "feedback_id") or ""),
                str(table_value(typed_item, "rating") or ""),
                str(table_value(typed_item, "source") or ""),
                str(table_value(typed_item, "reviewStatus", "review_status") or ""),
                str(comma_separated_table_value(typed_item, "reviewTags", "review_tags") or ""),
                str(table_value(typed_item, "version") or ""),
                str(table_value(typed_item, "runId", "run_id") or ""),
                str(table_value(typed_item, "model") or ""),
                feedback_prompt_version_summary(typed_item),
                str(comma_separated_table_value(typed_item, "toolsUsed", "tools_used") or ""),
                str(table_value(typed_item, "comment") or ""),
                str(table_value(typed_item, "reviewNote", "review_note") or ""),
                feedback_next_action_summary(typed_item),
            )
        )
    widths = (
        max([len("ID"), *(len(row[0]) for row in rows)]),
        max([len("RATING"), *(len(row[1]) for row in rows)]),
        max([len("SOURCE"), *(len(row[2]) for row in rows)]),
        max([len("REVIEW"), *(len(row[3]) for row in rows)]),
        max([len("REVIEW_TAGS"), *(len(row[4]) for row in rows)]),
        max([len("VERSION"), *(len(row[5]) for row in rows)]),
        max([len("RUN"), *(len(row[6]) for row in rows)]),
        max([len("MODEL"), *(len(row[7]) for row in rows)]),
        max([len("PROMPT"), *(len(row[8]) for row in rows)]),
        max([len("TOOLS"), *(len(row[9]) for row in rows)]),
        max([len("COMMENT"), *(len(row[10]) for row in rows)]),
        max([len("REVIEW_NOTE"), *(len(row[11]) for row in rows)]),
    )
    lines = [
        f"{'ID':<{widths[0]}}  {'RATING':<{widths[1]}}  {'SOURCE':<{widths[2]}}  "
        f"{'REVIEW':<{widths[3]}}  {'REVIEW_TAGS':<{widths[4]}}  "
        f"{'VERSION':<{widths[5]}}  {'RUN':<{widths[6]}}  "
        f"{'MODEL':<{widths[7]}}  {'PROMPT':<{widths[8]}}  {'TOOLS':<{widths[9]}}  "
        f"{'COMMENT':<{widths[10]}}  {'REVIEW_NOTE':<{widths[11]}}  NEXT_ACTION"
    ]
    lines.extend(
        f"{feedback_id:<{widths[0]}}  {rating:<{widths[1]}}  {source:<{widths[2]}}  "
        f"{review:<{widths[3]}}  {review_tags:<{widths[4]}}  "
        f"{version:<{widths[5]}}  {run_id:<{widths[6]}}  "
        f"{model:<{widths[7]}}  {prompt:<{widths[8]}}  {tools:<{widths[9]}}  "
        f"{comment:<{widths[10]}}  {review_note:<{widths[11]}}  {next_action}"
        for (
            feedback_id,
            rating,
            source,
            review,
            review_tags,
            version,
            run_id,
            model,
            prompt,
            tools,
            comment,
            review_note,
            next_action,
        ) in rows
    )
    action_rows = feedback_next_action_rows(raw_items)
    if action_rows:
        lines.extend(action_rows)
    return "\n".join(lines) + "\n"


def feedback_prompt_version_summary(item: Mapping[str, object]) -> str:
    value = table_value(item, "promptVersion", "prompt_version")
    if value is None:
        return ""
    return f"prompt={value}"


def format_rag_candidates_table(body: dict[str, object] | list[object] | None) -> str:
    raw_items: Sequence[object]
    if isinstance(body, list):
        raw_items = cast(Sequence[object], body)
    elif isinstance(body, Mapping):
        raw_items = (body,)
    else:
        raw_items = ()
    rows: list[tuple[str, str, str, str, str, str]] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        typed_item = {str(key): value for key, value in cast(Mapping[object, object], item).items()}
        rows.append(
            (
                str(table_value(typed_item, "id") or ""),
                str(table_value(typed_item, "status") or ""),
                str(table_value(typed_item, "channel") or ""),
                str(table_value(typed_item, "runId", "run_id") or ""),
                str(table_value(typed_item, "ingestedDocumentId", "ingested_document_id") or ""),
                executable_next_action(
                    str(table_value(typed_item, "nextAction", "next_action") or "")
                ),
            )
        )
    widths = (
        max([len("ID"), *(len(row[0]) for row in rows)]),
        max([len("STATUS"), *(len(row[1]) for row in rows)]),
        max([len("CHANNEL"), *(len(row[2]) for row in rows)]),
        max([len("RUN"), *(len(row[3]) for row in rows)]),
        max([len("DOCUMENT"), *(len(row[4]) for row in rows)]),
    )
    lines = [
        f"{'ID':<{widths[0]}}  {'STATUS':<{widths[1]}}  {'CHANNEL':<{widths[2]}}  "
        f"{'RUN':<{widths[3]}}  {'DOCUMENT':<{widths[4]}}  NEXT_ACTION"
    ]
    lines.extend(
        f"{candidate_id:<{widths[0]}}  {status:<{widths[1]}}  {channel:<{widths[2]}}  "
        f"{run_id:<{widths[3]}}  {document_id:<{widths[4]}}  {next_action}"
        for candidate_id, status, channel, run_id, document_id, next_action in rows
    )
    action_rows = rag_candidate_next_action_rows(raw_items)
    if action_rows:
        lines.extend(action_rows)
    return "\n".join(lines) + "\n"


def rag_candidate_next_action_rows(raw_items: Sequence[object]) -> list[str]:
    rows: list[str] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        item_mapping = cast(Mapping[object, object], item)
        candidate_id = item_mapping.get("id")
        candidate_prefix = (
            f"{candidate_id.strip()}."
            if isinstance(candidate_id, str) and candidate_id.strip()
            else ""
        )
        rows.extend(next_action_state_rows(candidate_prefix, item_mapping))
        next_actions = item_mapping.get("nextActions")
        if not isinstance(next_actions, Sequence) or isinstance(
            next_actions, str | bytes | bytearray
        ):
            continue
        ready_action_ids = ready_next_action_id_set(item_mapping)
        for action in cast(Sequence[object], next_actions):
            if not isinstance(action, Mapping):
                continue
            action_mapping = cast(Mapping[object, object], action)
            action_id = action_mapping.get("id")
            command = action_mapping.get("command")
            if not isinstance(action_id, str) or not action_id.strip():
                continue
            stripped_action_id = action_id.strip()
            if ready_action_ids is not None and stripped_action_id not in ready_action_ids:
                continue
            if not isinstance(command, str) or not command.strip():
                continue
            label = action_mapping.get("label")
            label_segment = f"{label.strip()}  " if isinstance(label, str) and label.strip() else ""
            rows.append(
                f"nextAction.{candidate_prefix}{stripped_action_id}  "
                f"{label_segment}{executable_next_action(command.strip())}"
            )
            rows.extend(
                next_action_artifact_rows(candidate_prefix, stripped_action_id, action_mapping)
            )
    return rows


def ready_next_action_id_set(item_mapping: Mapping[object, object]) -> set[str] | None:
    ready_ids = item_mapping.get("readyNextActionIds") or item_mapping.get("ready_next_action_ids")
    if not isinstance(ready_ids, Sequence) or isinstance(ready_ids, str | bytes | bytearray):
        return None
    normalized = {
        item.strip()
        for item in cast(Sequence[object], ready_ids)
        if isinstance(item, str) and item.strip()
    }
    return normalized


def action_has_dependencies(action_mapping: Mapping[object, object]) -> bool:
    dependencies = action_mapping.get("dependsOnActionIds") or action_mapping.get(
        "depends_on_action_ids"
    )
    return isinstance(dependencies, Sequence) and not isinstance(
        dependencies,
        str | bytes | bytearray,
    )


def next_action_state_rows(prefix: str, item_mapping: Mapping[object, object]) -> list[str]:
    rows: list[str] = []
    for source_key, output_key in (
        ("readyNextActionIds", "readyNextActionIds"),
        ("blockedNextActionIds", "blockedNextActionIds"),
    ):
        action_ids = string_sequence_detail(item_mapping.get(source_key))
        if action_ids:
            rows.append(f"nextAction.{prefix}{output_key}  {','.join(action_ids)}")
    action_states = next_action_states_detail(item_mapping.get("nextActionStates"))
    if action_states:
        rows.append(f"nextAction.{prefix}nextActionStates  {action_states}")
    return rows


def next_action_states_detail(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    parts: list[str] = []
    for action_id, state in cast(Mapping[object, object], value).items():
        if not isinstance(action_id, str) or not action_id.strip():
            continue
        if not isinstance(state, str) or not state.strip():
            continue
        parts.append(f"{action_id.strip()}={state.strip()}")
    return ",".join(parts)


def feedback_next_action_rows(raw_items: Sequence[object]) -> list[str]:
    rows: list[str] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        item_mapping = cast(Mapping[object, object], item)
        feedback_id = (
            item_mapping.get("feedbackId")
            or item_mapping.get("feedback_id")
            or item_mapping.get("id")
        )
        feedback_prefix = (
            f"{feedback_id.strip()}."
            if isinstance(feedback_id, str) and feedback_id.strip()
            else ""
        )
        ready_action_ids = ready_next_action_id_set(item_mapping)
        rows.extend(next_action_state_rows(feedback_prefix, item_mapping))
        next_actions = item_mapping.get("nextActions")
        if not isinstance(next_actions, Sequence) or isinstance(
            next_actions, str | bytes | bytearray
        ):
            continue
        for action in cast(Sequence[object], next_actions):
            if not isinstance(action, Mapping):
                continue
            action_mapping = cast(Mapping[object, object], action)
            action_id = action_mapping.get("id")
            command = action_mapping.get("command")
            if not isinstance(action_id, str) or not action_id.strip():
                continue
            stripped_action_id = action_id.strip()
            if ready_action_ids is not None and stripped_action_id not in ready_action_ids:
                rows.extend(
                    blocked_next_action_artifact_rows(
                        feedback_prefix,
                        stripped_action_id,
                        action_mapping,
                    )
                )
                continue
            if ready_action_ids is None and action_has_dependencies(action_mapping):
                rows.extend(
                    blocked_next_action_artifact_rows(
                        feedback_prefix,
                        stripped_action_id,
                        action_mapping,
                    )
                )
                continue
            if not isinstance(command, str) or not command.strip():
                continue
            label = action_mapping.get("label")
            label_segment = f"{label.strip()}  " if isinstance(label, str) and label.strip() else ""
            rows.append(
                f"nextAction.{feedback_prefix}{stripped_action_id}  "
                f"{label_segment}{executable_next_action(command.strip())}"
            )
            rows.extend(
                next_action_artifact_rows(feedback_prefix, stripped_action_id, action_mapping)
            )
    return rows


def blocked_next_action_artifact_rows(
    item_prefix: str,
    action_id: str,
    action_mapping: Mapping[object, object],
) -> list[str]:
    required_review_note = action_mapping.get("requiredReviewNote")
    if not isinstance(required_review_note, str) or not required_review_note.strip():
        return []
    return [
        f"nextAction.{item_prefix}{action_id.strip()}.requiredReviewNote  "
        f"{required_review_note.strip()}"
    ]


def state_history_next_action_rows(body: Mapping[str, object]) -> list[str]:
    next_actions = body.get("nextActions") or body.get("next_actions")
    if not isinstance(next_actions, Sequence) or isinstance(next_actions, str | bytes | bytearray):
        return []
    rows: list[str] = []
    for action in cast(Sequence[object], next_actions):
        if not isinstance(action, Mapping):
            continue
        action_mapping = cast(Mapping[object, object], action)
        action_id = action_mapping.get("id")
        command = action_mapping.get("command")
        if not isinstance(action_id, str) or not action_id.strip():
            continue
        if not isinstance(command, str) or not command.strip():
            continue
        label = action_mapping.get("label")
        label_segment = f"{label.strip()}  " if isinstance(label, str) and label.strip() else ""
        rows.append(
            f"nextAction.{action_id.strip()}  "
            f"{label_segment}{executable_next_action(command.strip())}"
        )
        rows.extend(next_action_artifact_rows("", action_id, action_mapping))
    return rows


def next_action_artifact_rows(
    item_prefix: str,
    action_id: str,
    action_mapping: Mapping[object, object],
) -> list[str]:
    rows: list[str] = []
    for field_name in (
        "evalCaseId",
        "sourceRunId",
        "candidateTag",
        "subjectUserId",
        "reportFile",
        "caseFile",
        "runFile",
        "suiteFile",
        "datasetName",
        "feedbackId",
        "feedbackRating",
        "feedbackSource",
        "preflightFile",
        "preflightEnvTemplate",
        "replatformReadinessFile",
        "smokePlanFile",
        "releaseEvidenceFile",
        "releaseReadinessFile",
        "releaseReadinessCommand",
        "remediationCommand",
        "envFileCommand",
        "readinessReportArg",
        "recommendedVersionBump",
        "recommendedTagPattern",
        "latestTagCommand",
        "recommendedTagSource",
        "requiredReviewNote",
    ):
        value = action_mapping.get(field_name)
        if isinstance(value, str) and value.strip():
            rows.append(
                f"nextAction.{item_prefix}{action_id.strip()}.{field_name}  {value.strip()}"
            )
    required_reports = action_mapping.get("requiredReadinessReports")
    if isinstance(required_reports, Sequence) and not isinstance(
        required_reports, str | bytes | bytearray
    ):
        reports = [
            report.strip()
            for report in cast(Sequence[object], required_reports)
            if isinstance(report, str) and report.strip()
        ]
        if reports:
            rows.append(
                f"nextAction.{item_prefix}{action_id.strip()}.requiredReadinessReports  "
                f"{','.join(reports)}"
            )
    required_env_any_of = action_mapping.get("requiredEnvAnyOf")
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
                    f"nextAction.{item_prefix}{action_id.strip()}.requiredEnvAnyOf.{index}  "
                    f"{'|'.join(env_names)}"
                )
    depends_on_action_ids = action_mapping.get("dependsOnActionIds")
    if isinstance(depends_on_action_ids, Sequence) and not isinstance(
        depends_on_action_ids, str | bytes | bytearray
    ):
        action_ids = [
            action_id_item.strip()
            for action_id_item in cast(Sequence[object], depends_on_action_ids)
            if isinstance(action_id_item, str) and action_id_item.strip()
        ]
        if action_ids:
            rows.append(
                f"nextAction.{item_prefix}{action_id.strip()}.dependsOnActionIds  "
                f"{','.join(action_ids)}"
            )
    missing_env_any_of = action_mapping.get("missingEnvAnyOf")
    if isinstance(missing_env_any_of, Sequence) and not isinstance(
        missing_env_any_of, str | bytes | bytearray
    ):
        env_groups = [
            env_group.strip()
            for env_group in cast(Sequence[object], missing_env_any_of)
            if isinstance(env_group, str) and env_group.strip()
        ]
        if env_groups:
            rows.append(
                f"nextAction.{item_prefix}{action_id.strip()}.missingEnvAnyOf  "
                f"{','.join(env_groups)}"
            )
    recommended_env = action_mapping.get("recommendedEnv")
    if isinstance(recommended_env, Sequence) and not isinstance(
        recommended_env, str | bytes | bytearray
    ):
        env_names = [
            env_name.strip()
            for env_name in cast(Sequence[object], recommended_env)
            if isinstance(env_name, str) and env_name.strip()
        ]
        if env_names:
            rows.append(
                f"nextAction.{item_prefix}{action_id.strip()}.recommendedEnv  {','.join(env_names)}"
            )
    readiness_reports = action_mapping.get("readinessReports")
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
                        f"nextAction.{item_prefix}{action_id.strip()}.readinessReports."
                        f"{report_name}  {report_file}"
                    )
    workflow_tags = action_mapping.get("workflowTags")
    if isinstance(workflow_tags, Sequence) and not isinstance(
        workflow_tags, str | bytes | bytearray
    ):
        tags = [
            tag.strip()
            for tag in cast(Sequence[object], workflow_tags)
            if isinstance(tag, str) and tag.strip()
        ]
        if tags:
            rows.append(
                f"nextAction.{item_prefix}{action_id.strip()}.workflowTags  {','.join(tags)}"
            )
    feedback_tags = action_mapping.get("feedbackTags")
    if isinstance(feedback_tags, Sequence) and not isinstance(
        feedback_tags, str | bytes | bytearray
    ):
        tags = [
            tag.strip()
            for tag in cast(Sequence[object], feedback_tags)
            if isinstance(tag, str) and tag.strip()
        ]
        if tags:
            rows.append(
                f"nextAction.{item_prefix}{action_id.strip()}.feedbackTags  {','.join(tags)}"
            )
    expected_answers = action_mapping.get("expectedAnswers")
    if isinstance(expected_answers, Sequence) and not isinstance(
        expected_answers, str | bytes | bytearray
    ):
        answers = [
            answer.strip()
            for answer in cast(Sequence[object], expected_answers)
            if isinstance(answer, str) and answer.strip()
        ]
        if answers:
            rows.append(
                f"nextAction.{item_prefix}{action_id.strip()}.expectedAnswers  {','.join(answers)}"
            )
    for field_name in (
        "minorBoundaryReports",
        "minorBlockedReports",
        "minorBoundaryMissingEvidence",
    ):
        values = action_mapping.get(field_name)
        if not isinstance(values, Sequence) or isinstance(values, str | bytes | bytearray):
            continue
        normalized_values = [
            value.strip()
            for value in cast(Sequence[object], values)
            if isinstance(value, str) and value.strip()
        ]
        if normalized_values:
            rows.append(
                f"nextAction.{item_prefix}{action_id.strip()}.{field_name}  "
                f"{','.join(normalized_values)}"
            )
    return rows


def format_feedback_review_table(body: dict[str, object] | list[object] | None) -> str:
    if not isinstance(body, Mapping):
        return "FIELD  VALUE\n"
    typed_body = cast(Mapping[str, object], body)
    rows = [
        ("feedback_id", table_value(typed_body, "feedbackId", "feedback_id")),
        ("rating", table_value(typed_body, "rating")),
        ("review_status", table_value(typed_body, "reviewStatus", "review_status")),
        ("review_tags", comma_separated_table_value(typed_body, "reviewTags", "review_tags")),
        ("reviewed_by", table_value(typed_body, "reviewedBy", "reviewed_by")),
        ("review_note", table_value(typed_body, "reviewNote", "review_note")),
        ("version", table_value(typed_body, "version")),
        ("run_id", table_value(typed_body, "runId", "run_id")),
        ("model", table_value(typed_body, "model")),
        ("nextAction", feedback_review_next_action(typed_body)),
    ]
    rows = [(field, value) for field, value in rows if value is not None]
    width = max([len("FIELD"), *(len(field) for field, _ in rows)])
    lines = [f"{'FIELD':<{width}}  VALUE"]
    lines.extend(f"{field:<{width}}  {value}" for field, value in rows)
    action_rows = feedback_next_action_rows((typed_body,))
    if action_rows:
        lines.extend(action_rows)
    return "\n".join(lines) + "\n"


def format_feedback_bulk_review_table(body: dict[str, object] | list[object] | None) -> str:
    if not isinstance(body, Mapping):
        return (
            "STATUS  ID  REASON  EVAL_CASE_ID  SOURCE_RUN_ID  FEEDBACK_SOURCE  "
            "NEXT_ACTION  BULK_REVIEW_ACTION  READINESS_REPORT_ARG  "
            "REQUIRED_READINESS_REPORTS  REQUIRED_ENV_ANY_OF  RECOMMENDED_ENV  "
            "REVIEW_TAGS  REVIEW_NOTE  REQUIRED_REVIEW_NOTE  LANGSMITH_REVIEW_ARGS  "
            "LANGSMITH_REVIEW_COMMAND  RELEASE_READINESS_COMMAND  READINESS_REPORTS\n"
        )
    rows: list[
        tuple[
            str,
            str,
            str,
            str,
            str,
            str,
            str,
            str,
            str,
            str,
            str,
            str,
            str,
            str,
            str,
            str,
            str,
            str,
            str,
        ]
    ] = []
    updated_details = feedback_bulk_review_updated_details(body)
    updated_detail_ids = {
        detail["feedbackId"]
        for detail in updated_details
        if isinstance(detail.get("feedbackId"), str)
    }
    rows.extend(
        (
            "updated",
            str(detail.get("feedbackId") or ""),
            "",
            str(detail.get("evalCaseId") or ""),
            str(detail.get("sourceRunId") or ""),
            str(detail.get("feedbackSource") or ""),
            executable_next_action(str(detail.get("nextAction") or "")),
            "",
            str(detail.get("readinessReportArg") or ""),
            compact_string_sequence(detail.get("requiredReadinessReports")),
            compact_env_any_of(detail.get("requiredEnvAnyOf")),
            compact_string_sequence(detail.get("recommendedEnv")),
            compact_string_sequence(detail.get("reviewTags")),
            str(detail.get("reviewNote") or ""),
            "",
            str(detail.get("langsmithReviewArgs") or ""),
            executable_next_action(str(detail.get("langsmithReviewCommand") or "")),
            executable_next_action(str(detail.get("releaseReadinessCommand") or "")),
            compact_string_mapping(detail.get("readinessReports")),
        )
        for detail in updated_details
    )
    updated = body.get("updated")
    if isinstance(updated, Sequence) and not isinstance(updated, str | bytes | bytearray):
        rows.extend(
            (
                "updated",
                str(feedback_id),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            )
            for feedback_id in cast(Sequence[object], updated)
            if str(feedback_id) not in updated_detail_ids
        )
    already_done_details = feedback_bulk_review_already_done_details(body)
    already_done_detail_ids = {
        detail["feedbackId"]
        for detail in already_done_details
        if isinstance(detail.get("feedbackId"), str)
    }
    rows.extend(
        (
            "already_done",
            str(detail.get("feedbackId") or ""),
            "",
            str(detail.get("evalCaseId") or ""),
            str(detail.get("sourceRunId") or ""),
            str(detail.get("feedbackSource") or ""),
            executable_next_action(str(detail.get("nextAction") or "")),
            "",
            str(detail.get("readinessReportArg") or ""),
            compact_string_sequence(detail.get("requiredReadinessReports")),
            compact_env_any_of(detail.get("requiredEnvAnyOf")),
            compact_string_sequence(detail.get("recommendedEnv")),
            compact_string_sequence(detail.get("reviewTags")),
            str(detail.get("reviewNote") or ""),
            "",
            str(detail.get("langsmithReviewArgs") or ""),
            executable_next_action(str(detail.get("langsmithReviewCommand") or "")),
            executable_next_action(str(detail.get("releaseReadinessCommand") or "")),
            compact_string_mapping(detail.get("readinessReports")),
        )
        for detail in already_done_details
    )
    already_done = body.get("alreadyDone")
    if isinstance(already_done, Sequence) and not isinstance(
        already_done,
        str | bytes | bytearray,
    ):
        rows.extend(
            (
                "already_done",
                str(feedback_id),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            )
            for feedback_id in cast(Sequence[object], already_done)
            if str(feedback_id) not in already_done_detail_ids
        )
    failed = body.get("failed")
    failed_action_items: list[Mapping[object, object]] = []
    if isinstance(failed, Sequence) and not isinstance(failed, str | bytes | bytearray):
        for item in cast(Sequence[object], failed):
            if not isinstance(item, Mapping):
                continue
            item_mapping = cast(Mapping[object, object], item)
            failed_action_items.append(item_mapping)
            rows.append(
                (
                    "failed",
                    str(item_mapping.get("id") or ""),
                    str(item_mapping.get("reason") or ""),
                    str(item_mapping.get("evalCaseId") or ""),
                    str(item_mapping.get("sourceRunId") or ""),
                    str(item_mapping.get("feedbackSource") or ""),
                    executable_next_action(str(item_mapping.get("nextAction") or "")),
                    executable_next_action(str(item_mapping.get("bulkReviewAction") or "")),
                    str(item_mapping.get("readinessReportArg") or ""),
                    compact_string_sequence(item_mapping.get("requiredReadinessReports")),
                    compact_env_any_of(item_mapping.get("requiredEnvAnyOf")),
                    compact_string_sequence(item_mapping.get("recommendedEnv")),
                    "",
                    "",
                    str(item_mapping.get("requiredReviewNote") or ""),
                    "",
                    "",
                    executable_next_action(str(item_mapping.get("releaseReadinessCommand") or "")),
                    compact_string_mapping(item_mapping.get("readinessReports")),
                )
            )
    widths = (
        max([len("STATUS"), *(len(row[0]) for row in rows)]),
        max([len("ID"), *(len(row[1]) for row in rows)]),
        max([len("REASON"), *(len(row[2]) for row in rows)]),
        max([len("EVAL_CASE_ID"), *(len(row[3]) for row in rows)]),
        max([len("SOURCE_RUN_ID"), *(len(row[4]) for row in rows)]),
        max([len("FEEDBACK_SOURCE"), *(len(row[5]) for row in rows)]),
        max([len("NEXT_ACTION"), *(len(row[6]) for row in rows)]),
        max([len("BULK_REVIEW_ACTION"), *(len(row[7]) for row in rows)]),
        max([len("READINESS_REPORT_ARG"), *(len(row[8]) for row in rows)]),
        max([len("REQUIRED_READINESS_REPORTS"), *(len(row[9]) for row in rows)]),
        max([len("REQUIRED_ENV_ANY_OF"), *(len(row[10]) for row in rows)]),
        max([len("RECOMMENDED_ENV"), *(len(row[11]) for row in rows)]),
        max([len("REVIEW_TAGS"), *(len(row[12]) for row in rows)]),
        max([len("REVIEW_NOTE"), *(len(row[13]) for row in rows)]),
        max([len("REQUIRED_REVIEW_NOTE"), *(len(row[14]) for row in rows)]),
        max([len("LANGSMITH_REVIEW_ARGS"), *(len(row[15]) for row in rows)]),
        max([len("LANGSMITH_REVIEW_COMMAND"), *(len(row[16]) for row in rows)]),
        max([len("RELEASE_READINESS_COMMAND"), *(len(row[17]) for row in rows)]),
    )
    lines = [
        f"{'STATUS':<{widths[0]}}  {'ID':<{widths[1]}}  {'REASON':<{widths[2]}}  "
        f"{'EVAL_CASE_ID':<{widths[3]}}  {'SOURCE_RUN_ID':<{widths[4]}}  "
        f"{'FEEDBACK_SOURCE':<{widths[5]}}  {'NEXT_ACTION':<{widths[6]}}  "
        f"{'BULK_REVIEW_ACTION':<{widths[7]}}  "
        f"{'READINESS_REPORT_ARG':<{widths[8]}}  "
        f"{'REQUIRED_READINESS_REPORTS':<{widths[9]}}  "
        f"{'REQUIRED_ENV_ANY_OF':<{widths[10]}}  "
        f"{'RECOMMENDED_ENV':<{widths[11]}}  "
        f"{'REVIEW_TAGS':<{widths[12]}}  {'REVIEW_NOTE':<{widths[13]}}  "
        f"{'REQUIRED_REVIEW_NOTE':<{widths[14]}}  "
        f"{'LANGSMITH_REVIEW_ARGS':<{widths[15]}}  "
        f"{'LANGSMITH_REVIEW_COMMAND':<{widths[16]}}  "
        f"{'RELEASE_READINESS_COMMAND':<{widths[17]}}  "
        "READINESS_REPORTS"
    ]
    lines.extend(
        f"{status:<{widths[0]}}  {feedback_id:<{widths[1]}}  {reason:<{widths[2]}}  "
        f"{eval_case_id:<{widths[3]}}  {source_run_id:<{widths[4]}}  "
        f"{feedback_source:<{widths[5]}}  {action:<{widths[6]}}  "
        f"{bulk_action:<{widths[7]}}  {readiness_report_arg:<{widths[8]}}  "
        f"{required_readiness_reports:<{widths[9]}}  "
        f"{required_env_any_of:<{widths[10]}}  "
        f"{recommended_env:<{widths[11]}}  "
        f"{review_tags:<{widths[12]}}  {review_note:<{widths[13]}}  "
        f"{required_review_note:<{widths[14]}}  "
        f"{langsmith_review_args:<{widths[15]}}  "
        f"{langsmith_review_command:<{widths[16]}}  "
        f"{release_readiness_command:<{widths[17]}}  "
        f"{readiness_reports}"
        for (
            status,
            feedback_id,
            reason,
            eval_case_id,
            source_run_id,
            feedback_source,
            action,
            bulk_action,
            readiness_report_arg,
            required_readiness_reports,
            required_env_any_of,
            recommended_env,
            review_tags,
            review_note,
            required_review_note,
            langsmith_review_args,
            langsmith_review_command,
            release_readiness_command,
            readiness_reports,
        ) in rows
    )
    action_rows = feedback_next_action_rows(failed_action_items)
    if action_rows:
        lines.extend(action_rows)
    return "\n".join(lines) + "\n"


def feedback_bulk_review_already_done_details(
    body: Mapping[str, object],
) -> list[Mapping[object, object]]:
    details = body.get("alreadyDoneDetails")
    if not isinstance(details, Sequence) or isinstance(details, str | bytes | bytearray):
        return []
    return [
        cast(Mapping[object, object], item)
        for item in cast(Sequence[object], details)
        if isinstance(item, Mapping)
    ]


def feedback_bulk_review_updated_details(
    body: Mapping[str, object],
) -> list[Mapping[object, object]]:
    details = body.get("updatedDetails")
    if not isinstance(details, Sequence) or isinstance(details, str | bytes | bytearray):
        return []
    return [
        cast(Mapping[object, object], item)
        for item in cast(Sequence[object], details)
        if isinstance(item, Mapping)
    ]


def compact_string_sequence(value: object) -> str:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return ""
    return ",".join(
        item.strip()
        for item in cast(Sequence[object], value)
        if isinstance(item, str) and item.strip()
    )


def compact_env_any_of(value: object) -> str:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return ""
    groups: list[str] = []
    for group in cast(Sequence[object], value):
        env_names = compact_string_sequence(group)
        if env_names:
            groups.append(env_names.replace(",", "|"))
    return ",".join(groups)


def compact_string_mapping(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    pairs: list[str] = []
    for key, item in sorted(
        cast(Mapping[object, object], value).items(), key=lambda pair: str(pair[0])
    ):
        if not isinstance(key, str) or not isinstance(item, str):
            continue
        key = key.strip()
        item = item.strip()
        if key and item:
            pairs.append(f"{key}={item}")
    return ";".join(pairs)


def feedback_next_action_summary(item: Mapping[str, object]) -> str:
    next_actions = item.get("nextActions")
    if not isinstance(next_actions, Sequence) or isinstance(next_actions, str):
        return ""
    ready_action_ids = ready_next_action_id_set(cast(Mapping[object, object], item))
    commands: list[str] = []
    for action in cast(Sequence[object], next_actions):
        if not isinstance(action, Mapping):
            continue
        action_mapping = cast(Mapping[object, object], action)
        action_id = action_mapping.get("id")
        if ready_action_ids is not None:
            if not isinstance(action_id, str) or action_id.strip() not in ready_action_ids:
                continue
        elif action_has_dependencies(action_mapping):
            continue
        command = action_mapping.get("command")
        if isinstance(command, str) and command.strip():
            commands.append(executable_next_action(command.strip()))
    return "; ".join(commands)


def executable_next_action(command: str) -> str:
    return command.replace("VERIFY_TIMESTAMP", "$(date -u +%Y-%m-%dT%H:%M:%SZ)")


def feedback_review_next_action(item: Mapping[str, object]) -> str:
    next_action = feedback_next_action_summary(item)
    if next_action:
        return next_action
    review_status = table_value(item, "reviewStatus", "review_status")
    if review_status == "inbox":
        return ""
    rating = table_value(item, "rating")
    source_args = feedback_review_next_action_source_args(item)
    tag_args = feedback_review_next_action_tag_args(item)
    if isinstance(rating, str) and rating.strip():
        return (
            f"reactor-admin feedback --rating {quote(rating.strip())}"
            " --review-status inbox"
            f"{source_args}{tag_args} --limit 10 --output table"
        )
    return (
        f"reactor-admin feedback --review-status inbox"
        f"{source_args}{tag_args} --limit 10 --output table"
    )


def feedback_review_next_action_source_args(item: Mapping[str, object]) -> str:
    source = table_value(item, "source")
    if not isinstance(source, str) or not source.strip():
        return ""
    return f" --source {quote(source.strip())}"


def feedback_review_next_action_tag_args(item: Mapping[str, object]) -> str:
    tags = comma_separated_table_value(item, "tags")
    if not tags:
        tags = comma_separated_table_value(item, "reviewTags", "review_tags")
    if not isinstance(tags, str) or not tags.strip():
        return ""
    workflow_tags = [
        tag.strip()
        for tag in tags.split(",")
        if tag.strip() and tag.strip() not in {"promoted", "langsmith"}
    ]
    if not workflow_tags:
        return ""
    return "".join(f" --tag {quote(tag)}" for tag in workflow_tags)


def table_value(body: Mapping[str, object], *keys: str) -> object | None:
    for key in keys:
        value = body.get(key)
        if value is not None:
            return value
    return None


def latest_checkpoint_id(entries: Sequence[Mapping[str, object]]) -> str | None:
    if not entries:
        return None
    value = table_value(entries[0], "checkpointId", "checkpoint_id")
    return value if isinstance(value, str) and value.strip() else None


def state_history_fork_next_action(
    body: Mapping[str, object],
    entries: Sequence[Mapping[str, object]],
) -> str | None:
    checkpoint_id = latest_checkpoint_id(entries)
    return state_history_checkpoint_fork_action(body, checkpoint_id)


def state_history_checkpoint_fork_action(
    body: Mapping[str, object],
    checkpoint_id: object | None,
) -> str | None:
    run_id = table_value(body, "runId", "run_id")
    checkpoint_ns = state_history_replay_checkpoint_ns(body)
    if not (
        isinstance(run_id, str)
        and run_id.strip()
        and isinstance(checkpoint_ns, str)
        and isinstance(checkpoint_id, str)
        and checkpoint_id.strip()
    ):
        return None
    return (
        f"reactor-runs fork {quote(run_id.strip())} --checkpoint-ns {quote(checkpoint_ns)} "
        f"--checkpoint-id {quote(checkpoint_id.strip())} --output table"
    )


def state_history_diagnose_next_action(body: Mapping[str, object]) -> str | None:
    run_id = table_value(body, "runId", "run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        return None
    return f"reactor-runs diagnose {quote(run_id.strip())} --output table"


def state_history_replay_next_action(body: Mapping[str, object]) -> str | None:
    run_id = table_value(body, "runId", "run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        return None
    return f"reactor-runs replay {quote(run_id.strip())} --output table"


def state_history_replay_checkpoint_ns(body: Mapping[str, object]) -> object | None:
    if body.get("namespaceFallbackUsed") is True:
        resolved = table_value(body, "resolvedCheckpointNs", "resolved_checkpoint_ns")
        if isinstance(resolved, str):
            return resolved
    return table_value(body, "checkpointNs", "checkpoint_ns")


def bool_table_value(value: object) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    return None


def string_table_value(value: object | None) -> str:
    return "" if value is None else str(value)


def comma_separated_table_value(body: Mapping[str, object], *keys: str) -> str | None:
    value = table_value(body, *keys)
    if not isinstance(value, Sequence) or isinstance(value, str):
        return None
    sequence_value = cast(Sequence[object], value)
    return ", ".join(str(item) for item in sequence_value)


def section_ok(section: Mapping[object, object]) -> str:
    return "true" if section.get("ok") is True else "false"


def section_status_code(section: Mapping[object, object]) -> str:
    status_code = section.get("statusCode")
    return str(status_code) if status_code is not None else ""


def admin_diagnostic_summary(section_name: str, section: Mapping[object, object]) -> str:
    if section.get("ok") is not True:
        return str(section.get("error") or "")
    body = section.get("body")
    if section_name == "healthz" and isinstance(body, Mapping):
        typed_body = cast(Mapping[object, object], body)
        return str(typed_body.get("status") or "")
    if section_name == "readyz" and isinstance(body, Mapping):
        typed_body = cast(Mapping[object, object], body)
        checks = typed_body.get("checks")
        check_count = (
            len(cast(Mapping[object, object], checks)) if isinstance(checks, Mapping) else 0
        )
        return f"{typed_body.get('status')} checks={check_count}"
    if section_name == "platformHealth" and isinstance(body, Mapping):
        typed_body = cast(Mapping[object, object], body)
        cache_hits = numeric_value(typed_body.get("cacheExactHits")) + numeric_value(
            typed_body.get("cacheSemanticHits")
        )
        return (
            f"alerts={typed_body.get('activeAlerts')}"
            f" buffer={typed_body.get('pipelineBufferUsage')}"
            f" drops={typed_body.get('pipelineDropRate')}"
            f" latencyMs={typed_body.get('pipelineWriteLatencyMs')}"
            f" cacheHits={format_number(cache_hits)}"
            f" cacheMisses={typed_body.get('cacheMisses')}"
        )
    if section_name == "capabilities":
        path_count = section.get("pathCount")
        return f"paths={path_count}" if path_count is not None else ""
    if section_name == "evals":
        return eval_dashboard_summary(section)
    if section_name == "tenantDashboard":
        return tenant_dashboard_summary(section)
    if section_name == "slackActivity":
        return slack_activity_summary(section)
    return ""


def eval_dashboard_summary(section: Mapping[object, object]) -> str:
    runs = section.get("runs")
    pass_rate = section.get("passRate")
    if not isinstance(runs, Mapping) or not isinstance(pass_rate, Mapping):
        return ""
    typed_runs = cast(Mapping[object, object], runs)
    typed_pass_rate = cast(Mapping[object, object], pass_rate)
    pass_rate_body = typed_pass_rate.get("body")
    body_mapping: Mapping[object, object] = (
        cast(Mapping[object, object], pass_rate_body) if isinstance(pass_rate_body, Mapping) else {}
    )
    total_cases = body_mapping.get("total_cases")
    pass_count = body_mapping.get("pass_count")
    return (
        f"runs={typed_runs.get('runCount')}"
        f"{eval_latest_run_summary(typed_runs)}"
        f" passRate={body_mapping.get('pass_rate')}"
        f" cases={total_cases}"
        f"{eval_pass_fail_summary(total_cases, pass_count)}"
    )


def eval_latest_run_summary(runs: Mapping[object, object]) -> str:
    body = runs.get("body")
    if not isinstance(body, Sequence) or isinstance(body, str | bytes):
        return ""
    for item in cast(Sequence[object], body):
        if not isinstance(item, Mapping):
            continue
        typed_item = cast(Mapping[object, object], item)
        run_id = typed_item.get("eval_run_id") or typed_item.get("evalRunId")
        avg_score = typed_item.get("avg_score") or typed_item.get("avgScore")
        parts: list[str] = []
        if isinstance(run_id, str) and run_id.strip():
            parts.append(f"latestRun={run_id.strip()}")
        if isinstance(avg_score, int | float) and not isinstance(avg_score, bool):
            parts.append(f"avgScore={avg_score}")
        return f" {' '.join(parts)}" if parts else ""
    return ""


def eval_pass_fail_summary(total_cases: object, pass_count: object) -> str:
    if not isinstance(total_cases, int) or isinstance(total_cases, bool):
        return ""
    if not isinstance(pass_count, int) or isinstance(pass_count, bool):
        return ""
    failed_count = max(total_cases - pass_count, 0)
    summary = f" passed={pass_count} failed={failed_count}"
    if failed_count:
        summary = (
            f"{summary} nextAction="
            "'reactor-admin feedback --rating thumbs_down "
            "--review-status inbox --limit 10 --output table'"
        )
    return summary


def tenant_dashboard_summary(section: Mapping[object, object]) -> str:
    overview_body = dashboard_body(section, "overview")
    quality_body = dashboard_body(section, "quality")
    tools_body = dashboard_body(section, "tools")
    cost_body = dashboard_body(section, "cost")
    tool_ranking = tools_body.get("toolRanking")
    tool_count = (
        len(cast(Sequence[object], tool_ranking))
        if isinstance(tool_ranking, Sequence) and not isinstance(tool_ranking, str)
        else 0
    )
    return (
        f"requests={overview_body.get('totalRequests')}"
        f" successRate={overview_body.get('successRate')}"
        f" latencyP95={quality_body.get('latencyP95')}"
        f" alerts={overview_body.get('activeAlerts')}"
        f" tools={tool_count}"
        f" monthlyCost={cost_body.get('monthlyCost')}"
    )


def slack_activity_summary(section: Mapping[object, object]) -> str:
    channels = section.get("channels")
    daily = section.get("daily")
    if not isinstance(channels, Mapping) or not isinstance(daily, Mapping):
        return ""
    typed_channels = cast(Mapping[object, object], channels)
    typed_daily = cast(Mapping[object, object], daily)
    channel_rows = body_rows(typed_channels)
    daily_rows = body_rows(typed_daily)
    sessions = sum_numeric_field(channel_rows, "session_count")
    messages = sum_numeric_field(daily_rows, "message_count")
    failures = sum_numeric_field(daily_rows, "failure_count")
    cost = sum_decimal_string_field(channel_rows, "total_cost_usd")
    summary = (
        f"channels={typed_channels.get('channelCount')}"
        f" sessions={format_number(sessions)}"
        f" messages={format_number(messages)}"
        f" failures={format_number(failures)}"
        f" cost={cost}"
    )
    top_channel = top_slack_channel(channel_rows)
    if top_channel:
        summary = f"{summary} topChannel={top_channel}"
        days = section.get("days")
        if isinstance(days, int) and not isinstance(days, bool) and days > 0:
            summary = (
                f"{summary} slackChannelAction='curl "
                f"/api/admin/slack-activity/channels?days={days}'"
            )
    return summary


def top_slack_channel(rows: Sequence[Mapping[object, object]]) -> str:
    top_channel = ""
    top_sessions = -1.0
    for row in rows:
        channel = row.get("channel")
        if not isinstance(channel, str) or not channel.strip():
            continue
        sessions = numeric_value(row.get("session_count"))
        if sessions > top_sessions:
            top_channel = channel.strip()
            top_sessions = sessions
    return top_channel


def dashboard_body(section: Mapping[object, object], key: str) -> Mapping[object, object]:
    child = section.get(key)
    if not isinstance(child, Mapping):
        return {}
    body = cast(Mapping[object, object], child).get("body")
    return cast(Mapping[object, object], body) if isinstance(body, Mapping) else {}


def body_rows(section: Mapping[object, object]) -> list[Mapping[object, object]]:
    body = section.get("body")
    if not isinstance(body, Sequence) or isinstance(body, str):
        return []
    return [
        cast(Mapping[object, object], item)
        for item in cast(Sequence[object], body)
        if isinstance(item, Mapping)
    ]


def sum_numeric_field(rows: Sequence[Mapping[object, object]], key: str) -> float:
    return sum(numeric_value(row.get(key)) for row in rows)


def sum_decimal_string_field(rows: Sequence[Mapping[object, object]], key: str) -> str:
    total = sum(numeric_value(row.get(key)) for row in rows)
    return f"{total:.4f}"


def numeric_value(value: object) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
