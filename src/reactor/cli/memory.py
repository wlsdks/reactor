from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from shlex import quote
from typing import Protocol, TextIO, cast
from urllib.parse import quote as url_quote
from urllib.parse import urlencode

import httpx

MEMORY_CONTRACT_AREAS = (
    "manager",
    "statuses",
    "consolidation",
    "review",
    "privacy",
    "dependencies",
)


@dataclass(frozen=True)
class MemoryCliHttpResult:
    ok: bool
    status_code: int
    body: dict[str, object] | list[object] | None = None
    error: str | None = None


class MemoryHttpProbe(Protocol):
    def get_json(self, path: str, headers: dict[str, str]) -> MemoryCliHttpResult: ...

    def post_json(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> MemoryCliHttpResult: ...

    def put_json(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> MemoryCliHttpResult: ...

    def delete_json(self, path: str, headers: dict[str, str]) -> MemoryCliHttpResult: ...


def path_segment(value: str) -> str:
    return url_quote(value, safe="")


class HttpMemoryProbe:
    def __init__(self, *, base_url: str, timeout_seconds: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def get_json(self, path: str, headers: dict[str, str]) -> MemoryCliHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.get(f"{self._base_url}{path}", headers=headers)
            return result_from_response(response)
        except httpx.HTTPError as error:
            return MemoryCliHttpResult(ok=False, status_code=0, error=str(error))

    def post_json(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> MemoryCliHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{self._base_url}{path}",
                    headers=headers,
                    json=payload,
                )
            return result_from_response(response)
        except httpx.HTTPError as error:
            return MemoryCliHttpResult(ok=False, status_code=0, error=str(error))

    def put_json(
        self,
        path: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> MemoryCliHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.put(
                    f"{self._base_url}{path}",
                    headers=headers,
                    json=payload,
                )
            return result_from_response(response)
        except httpx.HTTPError as error:
            return MemoryCliHttpResult(ok=False, status_code=0, error=str(error))

    def delete_json(self, path: str, headers: dict[str, str]) -> MemoryCliHttpResult:
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.delete(f"{self._base_url}{path}", headers=headers)
            if response.status_code == 204:
                return MemoryCliHttpResult(ok=True, status_code=204, body={"deleted": True})
            return result_from_response(response)
        except httpx.HTTPError as error:
            return MemoryCliHttpResult(ok=False, status_code=0, error=str(error))


def result_from_response(response: httpx.Response) -> MemoryCliHttpResult:
    if response.status_code >= 400:
        error_body: dict[str, object] | list[object] | None = None
        try:
            parsed_error_body = response.json()
        except ValueError:
            parsed_error_body = None
        if isinstance(parsed_error_body, dict | list):
            error_body = cast(dict[str, object] | list[object], parsed_error_body)
        return MemoryCliHttpResult(
            ok=False,
            status_code=response.status_code,
            body=error_body,
            error=response.text,
        )
    try:
        body = response.json()
    except ValueError:
        return MemoryCliHttpResult(
            ok=False,
            status_code=response.status_code,
            error="invalid_response",
        )
    if not isinstance(body, dict | list):
        return MemoryCliHttpResult(
            ok=False,
            status_code=response.status_code,
            error="invalid_response",
        )
    return MemoryCliHttpResult(
        ok=True,
        status_code=response.status_code,
        body=cast(dict[str, object] | list[object], body),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reactor-memory",
        description="Inspect and update Reactor user memory through the public API.",
    )
    parser.add_argument("--base-url", default="", help="Reactor API base URL")
    parser.add_argument("--tenant-id", default="", help="Tenant id header")
    parser.add_argument("--user-id", default="", help="User id header")
    parser.add_argument("--role", default="", help="Optional Reactor role header")
    parser.add_argument("--token", default="", help="Optional bearer token")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    subparsers = parser.add_subparsers(dest="command", required=True)

    get = subparsers.add_parser("get", help="Fetch the current user's memory")
    get.add_argument("--target-user-id", default="", help="Optional explicit user id")
    get.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    set_fact = subparsers.add_parser("set-fact", help="Set a current-user memory fact")
    set_fact.add_argument("--target-user-id", default="", help="Optional explicit user id")
    set_fact.add_argument("--key", required=True, help="Memory fact key")
    set_fact.add_argument("--value", required=True, help="Memory fact value")

    set_preference = subparsers.add_parser(
        "set-preference",
        help="Set a current-user memory preference",
    )
    set_preference.add_argument("--target-user-id", default="", help="Optional explicit user id")
    set_preference.add_argument("--key", required=True, help="Memory preference key")
    set_preference.add_argument("--value", required=True, help="Memory preference value")

    delete = subparsers.add_parser("delete", help="Delete the current user's memory")
    delete.add_argument("--target-user-id", default="", help="Optional explicit user id")

    proposals = subparsers.add_parser("proposals", help="List memory proposals for review")
    proposals.add_argument("--status", default="proposed", help="Proposal status filter")
    proposals.add_argument("--limit", type=int, default=50, help="Maximum proposals")
    proposals.add_argument("--subject-id", default="", help="Optional subject id filter")
    proposals.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    approve = subparsers.add_parser("approve", help="Approve a memory proposal")
    approve.add_argument("proposal_id")
    approve.add_argument("--reason", default="", help="Optional review reason")
    approve.add_argument(
        "--supersedes-memory-id",
        default="",
        help="Active memory item id that this approval supersedes",
    )
    approve.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )

    reject = subparsers.add_parser("reject", help="Reject a memory proposal")
    reject.add_argument("proposal_id")
    reject.add_argument("--reason", default="", help="Optional review reason")
    reject.add_argument(
        "--output",
        choices=("json", "table"),
        default="json",
        help="Output format",
    )
    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    http_probe: MemoryHttpProbe | None = None,
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
    probe = http_probe or HttpMemoryProbe(base_url=base_url, timeout_seconds=args.timeout)
    headers = request_headers(args, environ, tenant_id=tenant_id, user_id=user_id)

    result = dispatch_command(args, probe, headers, user_id=user_id)
    if not result.ok:
        stderr.write(memory_request_failure_message(result))
        return 1

    if getattr(args, "output", "json") == "table":
        if args.command == "proposals":
            stdout.write(format_memory_proposals_table(result.body))
        elif args.command in {"approve", "reject"}:
            stdout.write(format_memory_approval_table(result.body))
        else:
            stdout.write(format_memory_table(result.body))
    else:
        stdout.write(json.dumps(result.body, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


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
    probe: MemoryHttpProbe,
    headers: dict[str, str],
    *,
    user_id: str,
) -> MemoryCliHttpResult:
    if args.command == "get":
        target_user_id = args.target_user_id or user_id
        return probe.get_json(f"/api/user-memory/{path_segment(target_user_id)}", headers=headers)
    if args.command == "set-fact":
        target_user_id = args.target_user_id or user_id
        return probe.put_json(
            f"/api/user-memory/{path_segment(target_user_id)}/facts",
            headers=headers,
            payload={"key": args.key, "value": args.value},
        )
    if args.command == "set-preference":
        target_user_id = args.target_user_id or user_id
        return probe.put_json(
            f"/api/user-memory/{path_segment(target_user_id)}/preferences",
            headers=headers,
            payload={"key": args.key, "value": args.value},
        )
    if args.command == "delete":
        target_user_id = args.target_user_id or user_id
        return probe.delete_json(
            f"/api/user-memory/{path_segment(target_user_id)}", headers=headers
        )
    if args.command == "proposals":
        query_args: dict[str, object] = {"status": args.status, "limit": args.limit}
        if args.subject_id:
            query_args["subject_id"] = args.subject_id
        query = urlencode(query_args)
        return probe.get_json(f"/api/admin/memory/proposals?{query}", headers=headers)
    if args.command == "approve":
        return probe.post_json(
            f"/api/admin/memory/proposals/{path_segment(args.proposal_id)}/approve",
            headers=headers,
            payload=memory_decision_payload(args),
        )
    if args.command == "reject":
        return probe.post_json(
            f"/api/admin/memory/proposals/{path_segment(args.proposal_id)}/reject",
            headers=headers,
            payload=memory_decision_payload(args),
        )
    raise AssertionError(f"unsupported command: {args.command}")


def memory_decision_payload(args: argparse.Namespace) -> dict[str, object]:
    payload: dict[str, object] = {}
    if args.reason:
        payload["reason"] = args.reason
    supersedes_memory_id = getattr(args, "supersedes_memory_id", "")
    if supersedes_memory_id:
        payload["supersedesMemoryId"] = supersedes_memory_id
    return payload


def memory_request_failure_message(result: MemoryCliHttpResult) -> str:
    detail = error_detail_mapping(result.body)
    parts = [f"reactor-memory request failed ({result.status_code}): {result.error or ''}".rstrip()]
    for key in ("reason", "proposalId"):
        value = detail.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(f"{key}: {value.strip()}")
    message = detail.get("message")
    if isinstance(message, str) and message.strip():
        parts.append(f"message: {message.strip()}")
    sensitivity = object_mapping(detail.get("sensitivity"))
    if sensitivity:
        for key in ("status", "policy", "source"):
            value = sensitivity.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(f"sensitivity.{key}: {value.strip()}")
        markers_value = sensitivity.get("markers")
        markers = (
            [
                marker.strip()
                for marker in cast(Sequence[object], markers_value)
                if isinstance(marker, str) and marker.strip()
            ]
            if isinstance(markers_value, Sequence)
            and not isinstance(markers_value, str | bytes | bytearray)
            else []
        )
        if markers:
            parts.append(f"sensitivity.markers: {','.join(markers)}")
    reject_action = detail.get("rejectAction")
    if isinstance(reject_action, str) and reject_action.strip():
        parts.append(f"rejectAction: {reject_action.strip()}")
    review_queue_action = detail.get("reviewQueueAction")
    if isinstance(review_queue_action, str) and review_queue_action.strip():
        parts.append(f"reviewQueueAction: {review_queue_action.strip()}")
    next_action_ids = memory_next_action_ids(detail.get("nextActions"))
    if next_action_ids:
        parts.append(f"nextActionIds: {next_action_ids}")
    next_actions = detail.get("nextActions")
    if isinstance(next_actions, Sequence) and not isinstance(next_actions, str | bytes | bytearray):
        for index, action in enumerate(cast(Sequence[object], next_actions), start=1):
            if not isinstance(action, Mapping):
                continue
            action_mapping = cast(Mapping[object, object], action)
            command = action_mapping.get("command")
            if not isinstance(command, str) or not command.strip():
                continue
            action_id = action_mapping.get("id")
            normalized_id = (
                safe_next_action_id(action_id.strip())
                if isinstance(action_id, str) and action_id.strip()
                else str(index)
            )
            label = action_mapping.get("label")
            label_prefix = f"{label.strip()}  " if isinstance(label, str) and label.strip() else ""
            parts.append(
                f"nextAction.{normalized_id}: {label_prefix}"
                f"{executable_next_action(command.strip())}"
            )
    return "\n".join(parts) + "\n"


def error_detail_mapping(body: object) -> Mapping[object, object]:
    if not isinstance(body, Mapping):
        return {}
    detail = cast(Mapping[object, object], body).get("detail")
    if not isinstance(detail, Mapping):
        return {}
    return cast(Mapping[object, object], detail)


def format_memory_table(body: dict[str, object] | list[object] | None) -> str:
    if not isinstance(body, Mapping):
        return "SECTION  KEY  VALUE\n"
    rows: list[tuple[str, str, str]] = []
    rows.extend(mapping_rows("facts", body.get("facts")))
    rows.extend(mapping_rows("preferences", body.get("preferences")))
    rows.extend(sequence_rows("recentTopics", body.get("recentTopics")))
    updated_at = body.get("updatedAt")
    if updated_at is not None:
        rows.append(("updatedAt", "-", str(updated_at)))
    widths = (
        max([len("SECTION"), *(len(section) for section, _, _ in rows)]),
        max([len("KEY"), *(len(key) for _, key, _ in rows)]),
    )
    lines = [f"{'SECTION':<{widths[0]}}  {'KEY':<{widths[1]}}  VALUE"]
    lines.extend(
        f"{section:<{widths[0]}}  {key:<{widths[1]}}  {value}" for section, key, value in rows
    )
    return "\n".join(lines) + "\n"


def mapping_rows(section: str, value: object) -> list[tuple[str, str, str]]:
    if not isinstance(value, Mapping):
        return []
    mapping = cast(Mapping[object, object], value)
    return [(section, str(key), str(item)) for key, item in sorted(mapping.items(), key=sort_key)]


def sequence_rows(section: str, value: object) -> list[tuple[str, str, str]]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [
        (section, str(index), str(item)) for index, item in enumerate(cast(Sequence[object], value))
    ]


def sort_key(item: tuple[object, object]) -> str:
    return str(item[0])


def format_memory_proposals_table(body: dict[str, object] | list[object] | None) -> str:
    if not isinstance(body, Mapping):
        return "ID  STATUS  SUBJECT_TYPE  SUBJECT  TYPE  VISIBILITY  CONFIDENCE  CONTENT\n"
    items = body.get("items")
    if not isinstance(items, Sequence) or isinstance(items, str):
        return "ID  STATUS  SUBJECT_TYPE  SUBJECT  TYPE  VISIBILITY  CONFIDENCE  CONTENT\n"
    rows = [
        memory_proposal_row(cast(Mapping[object, object], item))
        for item in cast(Sequence[object], items)
        if isinstance(item, Mapping)
    ]
    show_extraction = any(row[9] or row[10] for row in rows)
    show_maintenance = any(
        row[11] or row[12] or row[13] or row[14] or row[15] or row[16] for row in rows
    )
    widths = (
        max([len("ID"), *(len(row[0]) for row in rows)]),
        max([len("STATUS"), *(len(row[1]) for row in rows)]),
        max([len("SUBJECT_TYPE"), *(len(row[2]) for row in rows)]),
        max([len("SUBJECT"), *(len(row[3]) for row in rows)]),
        max([len("TYPE"), *(len(row[4]) for row in rows)]),
        max([len("VISIBILITY"), *(len(row[5]) for row in rows)]),
        max([len("CONFIDENCE"), *(len(row[6]) for row in rows)]),
        max([len("CREATED"), *(len(row[7]) for row in rows)]),
        max([len("EXTRACTOR"), *(len(row[9]) for row in rows)]),
        max([len("PROMPT"), *(len(row[10]) for row in rows)]),
        max([len("LANGMEM_MANAGER"), *(len(row[11]) for row in rows)]),
        max([len("DELETE_POLICY"), *(len(row[12]) for row in rows)]),
        max([len("DEPENDENCY_REVIEW"), *(len(row[13]) for row in rows)]),
        max([len("DEPENDENCY_REMEDIATION"), *(len(row[14]) for row in rows)]),
        max([len("LANGMEM_AREAS"), *(len(row[15]) for row in rows)]),
        max([len("SENSITIVITY"), *(len(row[16]) for row in rows)]),
    )
    header = (
        f"{'ID':<{widths[0]}}  {'STATUS':<{widths[1]}}  "
        f"{'SUBJECT_TYPE':<{widths[2]}}  {'SUBJECT':<{widths[3]}}  "
        f"{'TYPE':<{widths[4]}}  {'VISIBILITY':<{widths[5]}}  "
        f"{'CONFIDENCE':<{widths[6]}}  {'CREATED':<{widths[7]}}"
    )
    if show_extraction:
        header = f"{header}  {'EXTRACTOR':<{widths[8]}}  {'PROMPT':<{widths[9]}}"
    if show_maintenance:
        header = (
            f"{header}  {'LANGMEM_MANAGER':<{widths[10]}}  "
            f"{'DELETE_POLICY':<{widths[11]}}  "
            f"{'DEPENDENCY_REVIEW':<{widths[12]}}  "
            f"{'DEPENDENCY_REMEDIATION':<{widths[13]}}  "
            f"{'LANGMEM_AREAS':<{widths[14]}}  "
            f"{'SENSITIVITY':<{widths[15]}}"
        )
    lines = [f"{header}  CONTENT"]
    for row in rows:
        (
            proposal_id,
            status,
            subject_type,
            subject,
            memory_type,
            visibility,
            confidence,
            created_at,
        ) = row[:8]
        content = row[8]
        line = (
            f"{proposal_id:<{widths[0]}}  {status:<{widths[1]}}  "
            f"{subject_type:<{widths[2]}}  {subject:<{widths[3]}}  "
            f"{memory_type:<{widths[4]}}  {visibility:<{widths[5]}}  "
            f"{confidence:<{widths[6]}}  {created_at:<{widths[7]}}"
        )
        if show_extraction:
            line = f"{line}  {row[9]:<{widths[8]}}  {row[10]:<{widths[9]}}"
        if show_maintenance:
            line = (
                f"{line}  {row[11]:<{widths[10]}}  {row[12]:<{widths[11]}}  "
                f"{row[13]:<{widths[12]}}  {row[14]:<{widths[13]}}  "
                f"{row[15]:<{widths[14]}}  {row[16]:<{widths[15]}}"
            )
        lines.append(f"{line}  {content}")
    raw_items = [
        cast(Mapping[object, object], item)
        for item in cast(Sequence[object], items)
        if isinstance(item, Mapping)
    ]
    lines.extend(memory_proposal_next_action_rows(rows))
    lines.extend(memory_proposal_structured_next_action_rows(raw_items))
    return "\n".join(lines) + "\n"


def memory_proposal_row(
    item: Mapping[object, object],
) -> tuple[
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
]:
    maintenance = object_mapping(item.get("maintenance")) or object_mapping(
        item.get("memoryMaintenance")
    )
    return (
        str(item.get("id") or ""),
        str(item.get("status") or ""),
        str(item.get("subjectType") or item.get("subject_type") or ""),
        str(item.get("subjectId") or ""),
        str(item.get("memoryType") or ""),
        str(item.get("visibility") or ""),
        str(item.get("confidence") or ""),
        str(item.get("createdAt") or ""),
        str(item.get("proposedContent") or ""),
        str(item.get("extractionModel") or ""),
        str(item.get("extractionPromptVersion") or ""),
        str(table_value(maintenance, "manager") or ""),
        str(table_value(maintenance, "deletePolicy", "delete_policy") or ""),
        str(table_value(maintenance, "dependencyReviewCommand", "dependency_review_command") or ""),
        str(
            table_value(
                maintenance,
                "dependencyRemediationCommand",
                "dependency_remediation_command",
            )
            or ""
        ),
        memory_contract_areas_value(maintenance) or "",
        memory_sensitivity_value(maintenance) or "",
    )


def memory_proposal_next_action_rows(
    rows: Sequence[Sequence[str]],
) -> list[str]:
    actions = [
        memory_review_inspection_action(subject_id)
        for proposal_id, status, _, subject_id, *_ in rows
        if proposal_id and status == "proposed" and subject_id.strip()
    ]
    if not actions:
        return []
    return [f"nextAction  {action}" for action in actions]


def memory_proposal_structured_next_action_rows(
    items: Sequence[Mapping[object, object]],
) -> list[str]:
    rows: list[str] = []
    for item in items:
        proposal_id = item.get("id")
        if not isinstance(proposal_id, str) or not proposal_id.strip():
            continue
        next_actions = item.get("nextActions")
        if not isinstance(next_actions, Sequence) or isinstance(next_actions, str):
            continue
        for action in cast(Sequence[object], next_actions):
            if not isinstance(action, Mapping):
                continue
            action_mapping = cast(Mapping[object, object], action)
            action_id = action_mapping.get("id")
            command = action_mapping.get("command")
            if (
                not isinstance(action_id, str)
                or not action_id.strip()
                or not isinstance(command, str)
                or not command.strip()
            ):
                continue
            label = action_mapping.get("label")
            label_prefix = f"{label.strip()}  " if isinstance(label, str) and label.strip() else ""
            rows.append(
                f"nextAction.{proposal_id.strip()}.{action_id.strip()}  "
                f"{label_prefix}{command.strip()}"
            )
            rows.extend(
                memory_next_action_artifact_rows(
                    proposal_id=proposal_id,
                    action_id=action_id,
                    action_mapping=action_mapping,
                )
            )
    return rows


def memory_next_action_artifact_rows(
    *,
    proposal_id: str,
    action_id: str,
    action_mapping: Mapping[object, object],
) -> list[str]:
    rows: list[str] = []
    for field_name in (
        "preflightFile",
        "preflightEnvTemplate",
        "replatformReadinessFile",
        "smokePlanFile",
        "releaseEvidenceFile",
        "releaseReadinessFile",
        "readinessReportArg",
    ):
        value = action_mapping.get(field_name)
        if isinstance(value, str) and value.strip():
            rows.append(
                "nextAction."
                f"{proposal_id.strip()}.{action_id.strip()}.{field_name}  {value.strip()}"
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
                "nextAction."
                f"{proposal_id.strip()}.{action_id.strip()}.requiredReadinessReports  "
                f"{','.join(reports)}"
            )
    readiness_reports = action_mapping.get("readinessReports")
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
                rows.append(
                    "nextAction."
                    f"{proposal_id.strip()}.{action_id.strip()}.readinessReports."
                    f"{report_name}  {report_file}"
                )
    return rows


def memory_review_inspection_action(subject_id: str) -> str:
    if not subject_id.strip():
        return ""
    normalized_subject_id = subject_id.strip()
    return f"reactor-memory get --target-user-id {quote(normalized_subject_id)} --output table"


def format_memory_approval_table(body: dict[str, object] | list[object] | None) -> str:
    if not isinstance(body, Mapping):
        return "FIELD  VALUE\n"
    mapping = cast(Mapping[object, object], body)
    proposal = object_mapping(mapping.get("proposal")) or mapping
    item = object_mapping(mapping.get("item"))
    superseded_ids = superseded_memory_ids(mapping.get("supersededItems"))
    maintenance = object_mapping(mapping.get("maintenance")) or object_mapping(
        mapping.get("memoryMaintenance")
    )
    rows = [
        ("proposal.id", proposal.get("id")),
        ("proposal.status", proposal.get("status")),
        ("proposal.subjectId", table_value(proposal, "subjectId", "subject_id")),
        ("proposal.confidence", table_value(proposal, "confidence")),
        ("proposal.decisionReason", table_value(proposal, "decisionReason", "decision_reason")),
        ("proposal.extractionModel", table_value(proposal, "extractionModel")),
        (
            "proposal.extractionPromptVersion",
            table_value(proposal, "extractionPromptVersion"),
        ),
        ("item.id", item.get("id")),
        ("item.status", item.get("status")),
        ("superseded.count", len(superseded_ids) if superseded_ids else None),
        ("superseded.ids", ", ".join(superseded_ids) if superseded_ids else None),
        ("langmem.manager", table_value(maintenance, "manager")),
        ("langmem.storeManager", table_value(maintenance, "storeManager", "store_manager")),
        ("langmem.operation", table_value(maintenance, "operation")),
        ("langmem.maxSteps", table_value(maintenance, "maxSteps", "max_steps")),
        ("langmem.deletePolicy", table_value(maintenance, "deletePolicy", "delete_policy")),
        (
            "langmem.dependencyReview",
            table_value(maintenance, "dependencyReviewCommand", "dependency_review_command"),
        ),
        (
            "langmem.dependencyRemediation",
            table_value(
                maintenance,
                "dependencyRemediationCommand",
                "dependency_remediation_command",
            ),
        ),
        ("langmem.contractAreas", memory_contract_areas_value(maintenance)),
        ("nextAction", memory_review_next_action(proposal, superseded_ids=superseded_ids)),
        ("nextActionIds", memory_next_action_ids(mapping.get("nextActions"))),
    ]
    rows.extend(memory_next_action_rows(mapping.get("nextActions")))
    present_rows = [(field, str(value)) for field, value in rows if value is not None]
    width = max([len("FIELD"), *(len(field) for field, _ in present_rows)])
    lines = [f"{'FIELD':<{width}}  VALUE"]
    lines.extend(f"{field:<{width}}  {value}" for field, value in present_rows)
    return "\n".join(lines) + "\n"


def memory_review_next_action(
    proposal: Mapping[object, object],
    *,
    superseded_ids: Sequence[str] = (),
) -> str | None:
    status = proposal.get("status")
    if status == "rejected":
        subject_id = proposal.get("subjectId") or proposal.get("subject_id")
        if isinstance(subject_id, str) and subject_id.strip():
            normalized_subject_id = subject_id.strip()
            return (
                "reactor-memory proposals --status proposed "
                f"--subject-id {quote(normalized_subject_id)} --output table"
            )
        return "reactor-memory proposals --status proposed --output table"
    if status != "approved":
        return None
    subject_id = proposal.get("subjectId") or proposal.get("subject_id")
    if not isinstance(subject_id, str) or not subject_id.strip():
        return None
    normalized_subject_id = subject_id.strip()
    return f"reactor-memory get --target-user-id {quote(normalized_subject_id)} --output table"


def memory_contract_areas_value(maintenance: Mapping[object, object]) -> str | None:
    if not maintenance:
        return None
    return ",".join(MEMORY_CONTRACT_AREAS)


def memory_next_action_ids(value: object) -> str | None:
    actions = memory_next_action_mappings(value)
    ids = [action_id for action_id, _ in actions]
    return ",".join(ids) if ids else None


def memory_next_action_rows(value: object) -> list[tuple[str, str]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    rows: list[tuple[str, str]] = []
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
        rows.append((f"nextAction.{normalized_id}", executable_next_action(command.strip())))
        for field_name in (
            "preflightFile",
            "preflightEnvTemplate",
            "replatformReadinessFile",
            "smokePlanFile",
            "releaseEvidenceFile",
            "releaseReadinessFile",
            "readinessReportArg",
        ):
            value = mapping.get(field_name)
            if isinstance(value, str) and value.strip():
                rows.append((f"nextAction.{normalized_id}.{field_name}", value.strip()))
        required_reports = mapping.get("requiredReadinessReports")
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
                    (
                        f"nextAction.{normalized_id}.requiredReadinessReports",
                        ",".join(reports),
                    )
                )
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
                    rows.append(
                        (
                            f"nextAction.{normalized_id}.readinessReports.{report_name}",
                            report_file,
                        )
                    )
    return rows


def memory_next_action_mappings(value: object) -> list[tuple[str, str]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    actions: list[tuple[str, str]] = []
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
        actions.append((normalized_id, command.strip()))
    return actions


def executable_next_action(command: str) -> str:
    return command.replace("VERIFY_TIMESTAMP", "$(date -u +%Y-%m-%dT%H:%M:%SZ)")


def safe_next_action_id(value: str) -> str:
    return (
        "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_")
        or "action"
    )


def memory_sensitivity_value(maintenance: Mapping[object, object]) -> str | None:
    sensitivity = object_mapping(maintenance.get("sensitivity"))
    status = table_value(sensitivity, "status")
    if not isinstance(status, str) or not status.strip():
        return None
    markers_value = sensitivity.get("markers")
    markers = (
        [
            marker.strip()
            for marker in cast(Sequence[object], markers_value)
            if isinstance(marker, str) and marker.strip()
        ]
        if isinstance(markers_value, Sequence) and not isinstance(markers_value, str | bytes)
        else []
    )
    source = table_value(sensitivity, "source")
    parts = [status.strip()]
    if markers:
        parts.append(",".join(markers))
    if isinstance(source, str) and source.strip():
        parts.append(source.strip())
    return ":".join(parts)


def object_mapping(value: object) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        return {}
    return cast(Mapping[object, object], value)


def table_value(body: Mapping[object, object], *keys: str) -> object | None:
    for key in keys:
        value = body.get(key)
        if value is not None:
            return value
    return None


def superseded_memory_ids(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    ids: list[str] = []
    for item in cast(Sequence[object], value):
        item_mapping = object_mapping(item)
        item_id = item_mapping.get("id")
        if isinstance(item_id, str) and item_id.strip():
            ids.append(item_id.strip())
    return ids


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
