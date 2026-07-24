from __future__ import annotations

import argparse
import itertools
import json
import random
import re
import secrets
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import gettempdir
from typing import Final, cast

MISSING: Final = object()


@dataclass(frozen=True)
class ScenarioDocument:
    path: Path
    defaults: dict[str, object]
    scenarios: tuple[dict[str, object], ...]
    quality_gates: dict[str, object]


@dataclass(frozen=True)
class ScenarioCase:
    id: str
    method: str
    path: str
    auth: str
    timeout_sec: float
    max_attempts: int
    headers: dict[str, str]
    request_json: object | None
    expect: dict[str, object]
    raw: dict[str, object]


@dataclass(frozen=True)
class ScenarioMatrixReport:
    generated_at_ms: int
    scenario_file: str
    base_url: str
    tenant_id: str
    run_id: str
    summary: dict[str, object]
    results: list[dict[str, object]]
    quality_gate_failures: list[str]

    @classmethod
    def from_results(
        cls,
        *,
        scenario_file: str,
        base_url: str,
        tenant_id: str,
        run_id: str,
        strict: bool,
        results: list[dict[str, object]],
        rate_limited: int,
    ) -> ScenarioMatrixReport:
        passed = sum(1 for item in results if item.get("status") == "passed")
        failed = sum(1 for item in results if item.get("status") == "failed")
        skipped = sum(1 for item in results if item.get("status") == "skipped")
        durations = [
            as_int(item.get("durationMs", 0)) for item in results if item.get("status") != "skipped"
        ]
        tools_counts = [
            as_int(
                require_dict(item.get("observations", {}), "observations").get("toolsUsedCount", 0)
            )
            for item in results
            if item.get("status") != "skipped"
        ]
        total = len(results)
        summary: dict[str, object] = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "rateLimited": rate_limited,
            "strict": strict,
            "passRate": passed / max(total, 1),
            "averageDurationMs": int(sum(durations) / max(len(durations), 1)),
            "p95DurationMs": percentile(durations, 0.95),
            "maxToolsUsedCount": max(tools_counts) if tools_counts else 0,
        }
        return cls(
            generated_at_ms=now_ms(),
            scenario_file=scenario_file,
            base_url=base_url,
            tenant_id=tenant_id,
            run_id=run_id,
            summary=summary,
            results=results,
            quality_gate_failures=[],
        )

    def with_quality_gate_failures(self, failures: Sequence[str]) -> ScenarioMatrixReport:
        return ScenarioMatrixReport(
            generated_at_ms=self.generated_at_ms,
            scenario_file=self.scenario_file,
            base_url=self.base_url,
            tenant_id=self.tenant_id,
            run_id=self.run_id,
            summary=self.summary,
            results=self.results,
            quality_gate_failures=list(failures),
        )

    def to_json_dict(self) -> dict[str, object]:
        return {
            "generatedAtMs": self.generated_at_ms,
            "scenarioFile": self.scenario_file,
            "baseUrl": self.base_url,
            "tenantId": self.tenant_id,
            "runId": self.run_id,
            "summary": self.summary,
            "results": self.results,
            "qualityGateFailures": self.quality_gate_failures,
        }


def now_ms() -> int:
    return int(time.time() * 1000)


def load_scenario_document(path: Path) -> ScenarioDocument:
    if not path.exists():
        raise FileNotFoundError(f"scenario file not found: {path}")
    raw = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(raw, dict):
        raise ValueError("scenario file root must be an object")
    raw_dict = cast(dict[object, object], raw)
    defaults = require_dict(raw_dict.get("defaults", {}), "defaults")
    raw_scenarios = require_list(raw_dict.get("scenarios"), "scenarios")
    scenarios = tuple(
        require_dict(item, f"scenarios[{idx}]") for idx, item in enumerate(raw_scenarios)
    )
    if not scenarios:
        raise ValueError("scenarios must contain at least one case")
    quality_gates = require_dict(raw_dict.get("qualityGates", {}), "qualityGates")
    return ScenarioDocument(
        path=path,
        defaults=defaults,
        scenarios=scenarios,
        quality_gates=quality_gates,
    )


def build_cases(
    scenario_doc: ScenarioDocument,
    runtime_vars: dict[str, object],
    include_tags: set[str],
    exclude_tags: set[str],
) -> list[ScenarioCase]:
    built: list[ScenarioCase] = []
    seen_ids: set[str] = set()

    for raw_case in scenario_doc.scenarios:
        if raw_case.get("enabled", True) is False:
            continue
        tags = case_tags(raw_case)
        if include_tags and not (tags & include_tags):
            continue
        if exclude_tags and (tags & exclude_tags):
            continue

        merged_case = require_dict(deep_merge(scenario_doc.defaults, raw_case), "merged scenario")
        matrix = require_dict(merged_case.pop("matrix", {}), "matrix")
        expanded = expand_case_matrix(merged_case, matrix, runtime_vars)
        for rendered in expanded:
            case = scenario_case_from_dict(rendered)
            if case.id in seen_ids:
                raise ValueError(f"duplicate scenario id: {case.id}")
            seen_ids.add(case.id)
            built.append(case)
    return built


def expand_case_matrix(
    merged_case: dict[str, object],
    matrix: dict[str, object],
    runtime_vars: dict[str, object],
) -> list[dict[str, object]]:
    if not matrix:
        return [require_dict(render_templates(merged_case, runtime_vars), "rendered scenario")]

    keys = list(matrix.keys())
    values: list[list[object]] = []
    for key in keys:
        dimension_values = matrix.get(key, [])
        if not isinstance(dimension_values, list) or not dimension_values:
            raise ValueError(f"matrix dimension '{key}' must be a non-empty list")
        values.append(cast(list[object], dimension_values))

    expanded: list[dict[str, object]] = []
    for combo in itertools.product(*values):
        combo_vars = dict(runtime_vars)
        combo_vars.update(dict(zip(keys, combo, strict=True)))
        rendered = require_dict(render_templates(merged_case, combo_vars), "rendered scenario")
        combo_suffix = ",".join(f"{key}={value}" for key, value in zip(keys, combo, strict=True))
        rendered["id"] = f"{rendered.get('id', 'case')}[{combo_suffix}]"
        expanded.append(rendered)
    return expanded


def scenario_case_from_dict(data: dict[str, object]) -> ScenarioCase:
    case_id = str(data.get("id", "case")).strip()
    if not case_id:
        raise ValueError("scenario id is required")
    return ScenarioCase(
        id=case_id,
        method=str(data.get("method", "POST")).upper(),
        path=str(data.get("path", "/api/chat")),
        auth=str(data.get("auth", "user")).lower(),
        timeout_sec=as_float(data.get("timeoutSec", 30)),
        max_attempts=as_int(data.get("maxAttempts", 1)),
        headers={
            str(key): str(value)
            for key, value in require_dict(data.get("headers", {}), f"{case_id}.headers").items()
        },
        request_json=data.get("json"),
        expect=require_dict(data.get("expect", {}), f"{case_id}.expect"),
        raw=data,
    )


def deep_merge(base: object, override: object) -> object:
    if isinstance(base, dict) and isinstance(override, dict):
        base_dict = cast(dict[object, object], base)
        override_dict = cast(dict[object, object], override)
        merged: dict[str, object] = {str(key): value for key, value in base_dict.items()}
        for key, value in override_dict.items():
            str_key = str(key)
            merged[str_key] = deep_merge(merged[str_key], value) if str_key in merged else value
        return merged
    return override


def render_templates(value: object, variables: dict[str, object]) -> object:
    if isinstance(value, dict):
        value_dict = cast(dict[object, object], value)
        return {str(key): render_templates(item, variables) for key, item in value_dict.items()}
    if isinstance(value, list):
        return [render_templates(item, variables) for item in cast(list[object], value)]
    if isinstance(value, str):
        rendered = value
        for key, item in variables.items():
            rendered = rendered.replace("{{" + key + "}}", str(item))
            rendered = rendered.replace("{{ " + key + " }}", str(item))
            rendered = rendered.replace("{" + key + "}", str(item))
        return rendered
    return value


def get_path(data: object, dotted_path: str) -> object:
    cursor = data
    if dotted_path == "":
        return cursor
    for raw_part in dotted_path.split("."):
        part = raw_part.strip()
        if not part:
            continue
        if isinstance(cursor, list):
            if not part.isdigit():
                return MISSING
            idx = int(part)
            list_cursor = cast(list[object], cursor)
            if idx < 0 or idx >= len(list_cursor):
                return MISSING
            cursor = list_cursor[idx]
        elif isinstance(cursor, dict):
            dict_cursor = cast(dict[object, object], cursor)
            if part not in dict_cursor:
                return MISSING
            cursor = dict_cursor[part]
        else:
            return MISSING
    return cursor


def evaluate_expectations(
    expect: dict[str, object],
    *,
    status: int,
    body_text: str,
    body_json: object,
) -> list[str]:
    failures: list[str] = []
    content, tools_used = response_content_and_tools(body_text, body_json)

    expected_status = expect.get("status")
    if expected_status is not None and status != as_int(expected_status):
        failures.append(f"status expected={expected_status} actual={status}")

    status_in = expect.get("statusIn")
    if isinstance(status_in, list):
        expected_statuses = [as_int(value) for value in cast(list[object], status_in)]
        if status not in expected_statuses:
            failures.append(f"status expected in {status_in}, actual={status}")

    expected_success = expect.get("success")
    if expected_success is not None:
        actual_success = get_path(body_json, "success")
        if actual_success is MISSING:
            failures.append("json path 'success' missing")
        elif bool(actual_success) != bool(expected_success):
            failures.append(f"success expected={expected_success} actual={actual_success}")

    failures.extend(tool_expectation_failures(expect, tools_used))
    failures.extend(content_expectation_failures(expect, content))
    failures.extend(json_expectation_failures(expect, body_json))
    return failures


def response_content_and_tools(body_text: str, body_json: object) -> tuple[str, list[str]]:
    content = body_text
    tools_used: list[str] = []
    if isinstance(body_json, dict):
        body = cast(dict[object, object], body_json)
        raw_content = body.get("content")
        if raw_content is not None and str(raw_content).strip():
            content = str(raw_content)
        raw_tools = body.get("toolsUsed", [])
        if isinstance(raw_tools, list):
            tools_used = [str(tool) for tool in cast(list[object], raw_tools)]
    return content, tools_used


def tool_expectation_failures(expect: dict[str, object], tools_used: Sequence[str]) -> list[str]:
    failures: list[str] = []
    for tool in string_list(expect.get("toolsUsedAll")):
        if tool not in tools_used:
            failures.append(f"toolsUsed missing required '{tool}'")

    tools_any = string_list(expect.get("toolsUsedAny"))
    if tools_any and not any(tool in tools_used for tool in tools_any):
        failures.append(f"toolsUsed must contain one of {tools_any}, actual={list(tools_used)}")

    for tool in string_list(expect.get("toolsUsedNone")):
        if tool in tools_used:
            failures.append(f"toolsUsed must not contain '{tool}'")

    min_count = expect.get("toolsUsedMinCount")
    if min_count is not None and len(tools_used) < as_int(min_count):
        failures.append(f"toolsUsed count expected>={min_count}, actual={len(tools_used)}")

    max_count = expect.get("toolsUsedMaxCount")
    if max_count is not None and len(tools_used) > as_int(max_count):
        failures.append(f"toolsUsed count expected<={max_count}, actual={len(tools_used)}")
    return failures


def content_expectation_failures(expect: dict[str, object], content: str) -> list[str]:
    failures: list[str] = []
    for needle in string_list(expect.get("contentContainsAll")):
        if needle not in content:
            failures.append(f"content missing substring '{needle}'")

    contains_any = string_list(expect.get("contentContainsAny"))
    if contains_any and not any(needle in content for needle in contains_any):
        failures.append(f"content must contain one of {contains_any}")

    for pattern in string_list(expect.get("contentRegexAll")):
        if re.search(pattern, content, flags=re.MULTILINE) is None:
            failures.append(f"content missing regex /{pattern}/")

    regex_any = string_list(expect.get("contentRegexAny"))
    if regex_any and not any(
        re.search(pattern, content, flags=re.MULTILINE) for pattern in regex_any
    ):
        failures.append(f"content must match one of {regex_any}")

    for pattern in string_list(expect.get("contentNotRegex")):
        if re.search(pattern, content, flags=re.MULTILINE):
            failures.append(f"content must not match regex /{pattern}/")
    return failures


def json_expectation_failures(expect: dict[str, object], body_json: object) -> list[str]:
    failures: list[str] = []
    error_contains = expect.get("errorContains")
    if error_contains is not None:
        actual_error = get_path(body_json, "errorMessage")
        if actual_error is MISSING:
            failures.append("json path 'errorMessage' missing")
        elif str(error_contains) not in str(actual_error):
            failures.append(f"errorMessage missing '{error_contains}'")

    json_equals = expect.get("jsonEquals", {})
    if isinstance(json_equals, dict):
        for path, expected_value in cast(dict[object, object], json_equals).items():
            actual_value = get_path(body_json, str(path))
            if actual_value is MISSING:
                failures.append(f"json path missing for equals check: {path}")
            elif actual_value != expected_value:
                failures.append(
                    "json equals mismatch "
                    f"path={path} expected={expected_value!r} actual={actual_value!r}"
                )

    json_exists = expect.get("jsonExists", [])
    if isinstance(json_exists, list):
        for path in cast(list[object], json_exists):
            if get_path(body_json, str(path)) is MISSING:
                failures.append(f"json path missing: {path}")

    json_regex = expect.get("jsonRegex", {})
    if isinstance(json_regex, dict):
        for path, pattern in cast(dict[object, object], json_regex).items():
            actual_value = get_path(body_json, str(path))
            if actual_value is MISSING:
                failures.append(f"json path missing for regex check: {path}")
                continue
            if re.search(str(pattern), str(actual_value), flags=re.MULTILINE) is None:
                failures.append(
                    f"json regex mismatch path={path} pattern=/{pattern}/ actual={actual_value!r}"
                )
    return failures


def response_observations(body_text: str, body_json: object) -> dict[str, object]:
    content, tools_used = response_content_and_tools(body_text, body_json)
    token_usage: dict[str, object] = {}
    if isinstance(body_json, dict):
        body = cast(dict[object, object], body_json)
        raw_token_usage = body.get("tokenUsage")
        if isinstance(raw_token_usage, dict):
            token_usage = {
                str(key): value
                for key, value in cast(dict[object, object], raw_token_usage).items()
            }
    return {
        "contentLength": len(content),
        "toolsUsed": tools_used,
        "toolsUsedCount": len(tools_used),
        "tokenUsage": token_usage,
    }


def http_json_request(
    method: str,
    url: str,
    headers: dict[str, str],
    json_body: object | None,
    timeout_sec: float,
) -> tuple[int, str, object]:
    payload = None
    req_headers = dict(headers)
    if json_body is not None:
        payload = json.dumps(json_body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(  # noqa: S310
        url=url,
        method=method.upper(),
        data=payload,
        headers=req_headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:  # noqa: S310
            status = int(response.getcode())
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        status = int(error.code)
        body = error.read().decode("utf-8", errors="replace")
    parsed: object = None
    try:
        parsed = cast(object, json.loads(body)) if body.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return status, body, parsed


def execute_case(
    *,
    base_url: str,
    tenant_id: str,
    case: ScenarioCase,
    user_token: str,
    admin_token: str,
    verbose: bool,
    request_fn: Callable[
        [str, str, dict[str, str], object | None, float],
        tuple[int, str, object],
    ] = http_json_request,
) -> dict[str, object]:
    token = token_for_auth_mode(case.auth, user_token, admin_token)
    if token is None:
        return {
            "id": case.id,
            "status": "skipped",
            "reason": "admin token is required but unavailable",
        }

    headers = dict(case.headers)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers.setdefault("X-Tenant-Id", tenant_id)

    attempt_results: list[dict[str, object]] = []
    for attempt in range(1, case.max_attempts + 1):
        started = now_ms()
        status_code, body_text, body_json = request_fn(
            case.method,
            f"{base_url}{case.path}",
            headers,
            case.request_json,
            case.timeout_sec,
        )
        duration_ms = now_ms() - started
        failures = evaluate_expectations(
            case.expect,
            status=status_code,
            body_text=body_text,
            body_json=body_json,
        )
        observations = response_observations(body_text, body_json)
        attempt_result: dict[str, object] = {
            "attempt": attempt,
            "httpStatus": status_code,
            "durationMs": duration_ms,
            "failures": failures,
            "observations": observations,
            "bodySnippet": body_text[:1200],
        }
        attempt_results.append(attempt_result)
        if not failures:
            return {
                "id": case.id,
                "status": "passed",
                "attempts": attempt,
                "httpStatus": status_code,
                "durationMs": duration_ms,
                "observations": observations,
                "bodySnippet": body_text[:1200],
            }
        if verbose:
            print(f"      attempt={attempt} failed: {failures}")

    final = attempt_results[-1] if attempt_results else {}
    return {
        "id": case.id,
        "status": "failed",
        "attempts": case.max_attempts,
        "httpStatus": final.get("httpStatus", 0),
        "durationMs": final.get("durationMs", 0),
        "observations": final.get("observations", {}),
        "failures": final.get("failures", ["unknown failure"]),
        "attemptDetails": attempt_results,
    }


def token_for_auth_mode(auth_mode: str, user_token: str, admin_token: str) -> str | None:
    if auth_mode == "user":
        return user_token
    if auth_mode == "admin":
        return admin_token or None
    if auth_mode == "none":
        return ""
    raise ValueError(f"unsupported auth mode: {auth_mode}")


def is_rate_limited_result(result: dict[str, object]) -> bool:
    for attempt in cast(list[dict[str, object]], result.get("attemptDetails", [])):
        if "Rate limit exceeded" in str(attempt.get("bodySnippet", "")):
            return True
    return False


def percentile(values: Sequence[int], ratio: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * ratio))
    return ordered[max(0, min(idx, len(ordered) - 1))]


def evaluate_quality_gates(report: ScenarioMatrixReport, gates: dict[str, object]) -> list[str]:
    if not gates:
        return []
    summary = report.summary
    total = max(as_int(summary["total"]), 1)
    pass_rate = as_float(summary["passed"]) / total
    checks: list[tuple[str, Callable[[object], bool], str]] = [
        (
            "minPassRate",
            lambda value: pass_rate >= as_float(value),
            f"passRate={pass_rate:.3f}",
        ),
        (
            "maxFailed",
            lambda value: as_int(summary["failed"]) <= as_int(value),
            f"failed={summary['failed']}",
        ),
        (
            "maxSkipped",
            lambda value: as_int(summary["skipped"]) <= as_int(value),
            f"skipped={summary['skipped']}",
        ),
        (
            "maxRateLimited",
            lambda value: as_int(summary["rateLimited"]) <= as_int(value),
            f"rateLimited={summary['rateLimited']}",
        ),
        (
            "maxAverageDurationMs",
            lambda value: as_int(summary["averageDurationMs"]) <= as_int(value),
            f"avgMs={summary['averageDurationMs']}",
        ),
        (
            "maxP95DurationMs",
            lambda value: as_int(summary["p95DurationMs"]) <= as_int(value),
            f"p95Ms={summary['p95DurationMs']}",
        ),
        (
            "maxToolsUsedPerCase",
            lambda value: as_int(summary["maxToolsUsedCount"]) <= as_int(value),
            f"maxTools={summary['maxToolsUsedCount']}",
        ),
    ]
    failures: list[str] = []
    for key, predicate, actual in checks:
        if key in gates and not predicate(gates[key]):
            failures.append(f"quality gate failed: {key} expected={gates[key]} actual={actual}")
    return failures


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run scenario matrix validation against Reactor.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--scenario-file", required=True)
    parser.add_argument("--report-file", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="passw0rd!")
    parser.add_argument("--name", default="Scenario Matrix QA")
    parser.add_argument("--admin-token", default="")
    parser.add_argument("--admin-email", default="")
    parser.add_argument("--admin-password", default="")
    parser.add_argument("--max-cases", type=int, default=0, help="0 means unlimited")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--include-tags", default="")
    parser.add_argument("--exclude-tags", default="")
    parser.add_argument("--case-delay-ms", type=int, default=0)
    parser.add_argument("--rate-limit-backoff-sec", type=int, default=0)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--stop-on-fail", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    random.seed(args.seed)

    try:
        scenario_doc = load_scenario_document(Path(args.scenario_file))
        run_id = f"smx-{int(time.time())}-{secrets.randbelow(9000) + 1000}"
        runtime_vars: dict[str, object] = {
            "run_id": run_id,
            "tenant_id": args.tenant_id,
            "base_url": args.base_url,
            "user_email": args.email or f"qa-scenario-{int(time.time())}@example.com",
        }
        cases = build_cases(
            scenario_doc,
            runtime_vars=runtime_vars,
            include_tags=split_tags(args.include_tags),
            exclude_tags=split_tags(args.exclude_tags),
        )
        if args.max_cases > 0 and len(cases) > args.max_cases:
            cases = random.sample(cases, args.max_cases)
    except Exception as error:
        print(f"Error: {error}", flush=True)
        return 1

    if not cases:
        print("No scenarios selected after filters.")
        return 1

    if args.validate_only:
        results: list[dict[str, object]] = [
            {"id": case.id, "status": "skipped", "reason": "validate-only"} for case in cases
        ]
        report = ScenarioMatrixReport.from_results(
            scenario_file=str(scenario_doc.path),
            base_url=args.base_url,
            tenant_id=args.tenant_id,
            run_id=run_id,
            strict=args.strict,
            results=results,
            rate_limited=0,
        )
        write_report(args.report_file, report)
        print(f"Validated {len(cases)} scenario cases")
        return 0

    try:
        user_token = resolve_user_token(args)
        admin_token = resolve_admin_token(args)
    except Exception as error:
        print(f"Error: failed to resolve auth token: {error}", flush=True)
        return 1

    report, failed, skipped = run_cases(args, scenario_doc, cases, run_id, user_token, admin_token)
    gate_failures = evaluate_quality_gates(report, scenario_doc.quality_gates)
    report = report.with_quality_gate_failures(gate_failures)
    report_path = write_report(args.report_file, report)
    print_summary(report, report_path)
    if failed > 0 or gate_failures or (args.strict and skipped > 0):
        return 1
    return 0


def run_cases(
    args: argparse.Namespace,
    scenario_doc: ScenarioDocument,
    cases: Sequence[ScenarioCase],
    run_id: str,
    user_token: str,
    admin_token: str,
) -> tuple[ScenarioMatrixReport, int, int]:
    print(f"Running {len(cases)} scenario cases")
    print(f"Base URL: {args.base_url}")
    print(f"Tenant ID: {args.tenant_id}")
    print(f"Run ID: {run_id}")
    print(f"Admin token available: {'yes' if admin_token else 'no'}")
    results: list[dict[str, object]] = []
    rate_limited = 0

    for idx, case in enumerate(cases, start=1):
        print(f"[{idx}/{len(cases)}] {case.id}")
        result = execute_case(
            base_url=args.base_url,
            tenant_id=args.tenant_id,
            case=case,
            user_token=user_token,
            admin_token=admin_token,
            verbose=args.verbose,
        )
        results.append(result)
        status = result.get("status")
        if status == "passed":
            print("      PASS")
        elif status == "skipped":
            print(f"      SKIP: {result.get('reason', 'no reason')}")
        else:
            reason = result.get("reason") or "; ".join(string_list(result.get("failures")))
            print(f"      FAIL: {reason}")
            if is_rate_limited_result(result):
                rate_limited += 1
            if args.stop_on_fail:
                break
        sleep_between_cases(args, status, result, idx == len(cases))

    failed = sum(1 for item in results if item.get("status") == "failed")
    skipped = sum(1 for item in results if item.get("status") == "skipped")
    return (
        ScenarioMatrixReport.from_results(
            scenario_file=str(scenario_doc.path),
            base_url=args.base_url,
            tenant_id=args.tenant_id,
            run_id=run_id,
            strict=args.strict,
            results=results,
            rate_limited=rate_limited,
        ),
        failed,
        skipped,
    )


def sleep_between_cases(
    args: argparse.Namespace,
    status: object,
    result: dict[str, object],
    is_last: bool,
) -> None:
    if is_last:
        return
    if args.case_delay_ms > 0:
        time.sleep(args.case_delay_ms / 1000.0)
    if args.rate_limit_backoff_sec > 0 and status == "failed" and is_rate_limited_result(result):
        print(f"      INFO: rate limit detected, sleeping {args.rate_limit_backoff_sec}s")
        time.sleep(args.rate_limit_backoff_sec)


def resolve_user_token(args: argparse.Namespace) -> str:
    email = (
        args.email or f"qa-scenario-{int(time.time())}-{secrets.randbelow(9000) + 1000}@example.com"
    )
    login_status, login_body, login_json = http_json_request(
        "POST",
        f"{args.base_url}/api/auth/login",
        {},
        {"email": email, "password": args.password},
        20,
    )
    if login_status == 200:
        return token_from_response(login_json, login_body)
    register_status, register_body, register_json = http_json_request(
        "POST",
        f"{args.base_url}/api/auth/register",
        {},
        {"email": email, "password": args.password, "name": args.name},
        20,
    )
    if register_status in {200, 201}:
        return token_from_response(register_json, register_body)
    raise RuntimeError(
        f"login status={login_status}; register status={register_status} body={register_body}"
    )


def resolve_admin_token(args: argparse.Namespace) -> str:
    if args.admin_token:
        return str(args.admin_token)
    if not args.admin_email or not args.admin_password:
        return ""
    status, body, body_json = http_json_request(
        "POST",
        f"{args.base_url}/api/auth/login",
        {},
        {"email": args.admin_email, "password": args.admin_password},
        20,
    )
    if status != 200:
        print(f"Warning: admin login failed status={status} body={body}")
        return ""
    return token_from_response(body_json, body)


def token_from_response(body_json: object, body_text: str) -> str:
    if not isinstance(body_json, dict):
        raise RuntimeError(f"token response was not JSON: {body_text}")
    token = str(cast(dict[object, object], body_json).get("token", "")).strip()
    if not token:
        raise RuntimeError(f"token missing: {body_text}")
    return token


def write_report(report_file: str, report: ScenarioMatrixReport) -> Path:
    path = (
        Path(report_file.strip())
        if report_file.strip()
        else Path(gettempdir()) / f"reactor-scenario-report-{int(time.time())}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_json_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def print_summary(report: ScenarioMatrixReport, report_path: Path) -> None:
    summary = report.summary
    print("Summary:")
    print(
        f"  total={summary['total']} passed={summary['passed']} "
        f"failed={summary['failed']} skipped={summary['skipped']}"
    )
    print(
        f"  passRate={as_float(summary['passRate']):.3f} avgMs={summary['averageDurationMs']} "
        f"p95Ms={summary['p95DurationMs']} maxTools={summary['maxToolsUsedCount']}"
    )
    for failure in report.quality_gate_failures:
        print(f"  {failure}")
    print(f"  report={report_path}")


def split_tags(value: str) -> set[str]:
    return {tag.strip() for tag in value.split(",") if tag.strip()}


def case_tags(case: dict[str, object]) -> set[str]:
    raw = case.get("tags", [])
    if isinstance(raw, str):
        return {raw.strip()} if raw.strip() else set()
    if isinstance(raw, list):
        return {str(item).strip() for item in cast(list[object], raw) if str(item).strip()}
    return set()


def string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in cast(list[object], value)]
    return []


def require_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def require_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return cast(list[object], value)


def as_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    raise ValueError(f"value must be int-compatible: {value!r}")


def as_float(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise ValueError(f"value must be float-compatible: {value!r}")
