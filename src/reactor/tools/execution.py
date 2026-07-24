from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Protocol

from reactor.kernel.ids import new_id
from reactor.persistence.tool_invocation_store import ToolInvocationClaim, ToolInvocationRecord
from reactor.sandbox.policy import SandboxPolicy
from reactor.tools.catalog import ToolSpec
from reactor.tools.idempotency import build_tool_idempotency_key

logger = logging.getLogger(__name__)


def empty_approved_approval_ids() -> set[str]:
    return set()


def empty_sandboxed_tool_names() -> set[str]:
    return set()


@dataclass(frozen=True)
class ToolPolicy:
    allow_write_without_approval: bool = False
    approved_approval_ids: set[str] = field(default_factory=empty_approved_approval_ids)
    sandboxed_tool_names: set[str] = field(default_factory=empty_sandboxed_tool_names)


@dataclass(frozen=True)
class ToolExecutionRequest:
    run_id: str
    tenant_id: str
    user_id: str
    tool: ToolSpec
    input_payload: Mapping[str, Any]
    trusted_user_groups: tuple[str, ...] = ()
    approval_id: str | None = None
    tool_call_id: str | None = None

    def validate(self) -> None:
        for field_name, value in (
            ("run_id", self.run_id),
            ("tenant_id", self.tenant_id),
            ("user_id", self.user_id),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")
        self.tool.validate()
        if not self.tool.enabled:
            raise ValueError("tool is disabled")
        if self.tool.tenant_id != self.tenant_id:
            raise ValueError("tool tenant_id does not match request tenant_id")
        if self.tool_call_id is not None and not self.tool_call_id.strip():
            raise ValueError("tool_call_id must be non-blank when provided")

    @property
    def idempotency_key(self) -> str:
        return build_tool_idempotency_key(
            tenant_id=self.tenant_id,
            run_id=self.run_id,
            qualified_name=self.tool.qualified_name,
            input_payload=self.input_payload,
            trusted_user_groups=self.trusted_user_groups,
            tool_call_id=self.tool_call_id,
        )


@dataclass(frozen=True)
class ToolAdmissionDecision:
    allowed: bool
    requires_approval: bool
    reason: str
    idempotency_key: str
    approval_id: str | None = None


@dataclass(frozen=True)
class ToolExecutionResult:
    status: str
    payload: Mapping[str, Any]

    @classmethod
    def success(cls, payload: Mapping[str, Any]) -> ToolExecutionResult:
        return cls(status="succeeded", payload=dict(payload))

    @classmethod
    def error(cls, code: str, message: str) -> ToolExecutionResult:
        return cls(
            status="failed",
            payload={"error": {"code": code, "message": message}},
        )

    @classmethod
    def requires_reconciliation(cls) -> ToolExecutionResult:
        return cls(
            status="requires_reconciliation",
            payload={
                "error": {
                    "code": "execution_outcome_unknown",
                    "message": "tool execution outcome requires reconciliation",
                }
            },
        )


class ToolResultCache:
    def __init__(self) -> None:
        self._results: dict[str, ToolExecutionResult] = {}

    def get(self, request: ToolExecutionRequest) -> ToolExecutionResult | None:
        return self._results.get(request.idempotency_key)

    def store(
        self,
        request: ToolExecutionRequest,
        result: ToolExecutionResult,
    ) -> ToolExecutionResult:
        self._results[request.idempotency_key] = result
        return result


ToolHandler = Callable[[ToolExecutionRequest], Awaitable[ToolExecutionResult]]


class ToolInvocationIdempotencyStore(Protocol):
    async def claim(self, record: ToolInvocationRecord) -> ToolInvocationClaim: ...

    async def save(self, record: ToolInvocationRecord) -> ToolInvocationRecord: ...


@dataclass(frozen=True)
class ToolExecutionOutcome:
    request: ToolExecutionRequest
    result: ToolExecutionResult
    cache_status: str | None = None
    executed: bool = True


async def run_tool_with_timeout(
    request: ToolExecutionRequest,
    handler: Callable[[], Awaitable[ToolExecutionResult]],
) -> ToolExecutionResult:
    request.validate()
    try:
        return await asyncio.wait_for(handler(), timeout=request.tool.timeout_ms / 1000)
    except TimeoutError:
        if request.tool.risk_level != "read":
            return ToolExecutionResult.requires_reconciliation()
        return ToolExecutionResult.error(
            "timeout",
            f"tool timed out after {request.tool.timeout_ms}ms",
        )
    except Exception:
        if request.tool.risk_level == "read":
            raise
        return ToolExecutionResult.requires_reconciliation()


async def execute_tools_parallel(
    requests: Sequence[ToolExecutionRequest],
    handler: ToolHandler,
    *,
    cache: ToolResultCache | None = None,
    idempotency_store: ToolInvocationIdempotencyStore | None = None,
) -> list[ToolExecutionOutcome]:
    async def execute_one(request: ToolExecutionRequest) -> ToolExecutionOutcome:
        cached = cache.get(request) if cache is not None else None
        if cached is not None:
            return ToolExecutionOutcome(
                request=request,
                result=cached,
                cache_status="hit",
                executed=False,
            )
        started_at = datetime.now(UTC)
        claimed_invocation_id: str | None = None
        if idempotency_store is not None:
            try:
                claim = await idempotency_store.claim(
                    tool_invocation_started_record(
                        request,
                        invocation_id=new_id("tool_invocation"),
                        started_at=started_at,
                    )
                )
            except Exception:
                logger.warning(
                    "tool invocation idempotency claim failed",
                    extra={
                        "tenant_id": request.tenant_id,
                        "run_id": request.run_id,
                        "tool_id": request.tool.qualified_name,
                    },
                )
                return ToolExecutionOutcome(
                    request=request,
                    result=ToolExecutionResult.error(
                        "idempotency_unavailable",
                        "tool execution could not acquire its idempotency claim",
                    ),
                    cache_status="claim_error",
                    executed=False,
                )
            if not claim.claimed:
                result = tool_idempotency_result(claim.record)
                return ToolExecutionOutcome(
                    request=request,
                    result=result,
                    cache_status=(
                        "durable_hit" if result.status == "succeeded" else "durable_conflict"
                    ),
                    executed=False,
                )
            claimed_invocation_id = claim.record.id
        result = await run_tool_with_timeout(request, lambda: handler(request))
        outcome = ToolExecutionOutcome(
            request=request,
            result=result,
            cache_status="miss" if cache is not None else None,
            executed=True,
        )
        if idempotency_store is not None:
            completed_at = datetime.now(UTC)
            try:
                await idempotency_store.save(
                    tool_invocation_record_from_outcome(
                        outcome,
                        invocation_id=claimed_invocation_id or new_id("tool_invocation"),
                        started_at=started_at,
                        completed_at=completed_at,
                    )
                )
            except Exception:
                logger.warning(
                    "tool invocation completion save failed",
                    extra={
                        "tenant_id": request.tenant_id,
                        "run_id": request.run_id,
                        "tool_id": request.tool.qualified_name,
                    },
                )
                return ToolExecutionOutcome(
                    request=request,
                    result=(
                        ToolExecutionResult.error(
                            "audit_persistence_unavailable",
                            "tool execution audit could not be persisted",
                        )
                        if request.tool.risk_level == "read"
                        else ToolExecutionResult.requires_reconciliation()
                    ),
                    cache_status="completion_save_error",
                    executed=True,
                )
        if cache is not None:
            cache.store(request, result)
        return outcome

    return list(await asyncio.gather(*(execute_one(request) for request in requests)))


def tool_idempotency_result(record: ToolInvocationRecord) -> ToolExecutionResult:
    if record.status == "succeeded" and record.output_payload is not None:
        return ToolExecutionResult.success(record.output_payload)
    return ToolExecutionResult.error(
        "idempotency_conflict",
        "tool execution with this idempotency key is already in progress or unresolved",
    )


def tool_invocation_record_from_outcome(
    outcome: ToolExecutionOutcome,
    *,
    invocation_id: str,
    started_at: datetime,
    completed_at: datetime | None,
) -> ToolInvocationRecord:
    request = outcome.request
    result = outcome.result
    input_payload = {
        **tool_invocation_request_payload(request),
        "cacheStatus": outcome.cache_status,
        "executed": outcome.executed,
    }
    return ToolInvocationRecord(
        id=invocation_id,
        tenant_id=request.tenant_id,
        run_id=request.run_id,
        tool_id=request.tool.catalog_id or request.tool.qualified_name,
        approval_id=request.approval_id,
        status=result.status,
        idempotency_key=request.idempotency_key,
        request_checksum=payload_checksum(tool_invocation_request_payload(request)),
        result_checksum=payload_checksum(result.payload),
        input_payload=input_payload,
        output_payload=dict(result.payload) if result.status == "succeeded" else None,
        error_payload=dict(result.payload) if result.status != "succeeded" else None,
        started_at=started_at,
        completed_at=completed_at,
    )


def tool_invocation_started_record(
    request: ToolExecutionRequest,
    *,
    invocation_id: str,
    started_at: datetime,
) -> ToolInvocationRecord:
    input_payload = {
        **tool_invocation_request_payload(request),
        "cacheStatus": None,
        "executed": False,
    }
    return ToolInvocationRecord(
        id=invocation_id,
        tenant_id=request.tenant_id,
        run_id=request.run_id,
        tool_id=request.tool.catalog_id or request.tool.qualified_name,
        approval_id=request.approval_id,
        status="started",
        idempotency_key=request.idempotency_key,
        request_checksum=payload_checksum(tool_invocation_request_payload(request)),
        result_checksum=None,
        input_payload=input_payload,
        output_payload=None,
        error_payload=None,
        started_at=started_at,
        completed_at=None,
    )


def tool_invocation_request_payload(request: ToolExecutionRequest) -> dict[str, object]:
    payload: dict[str, object] = {
        "tool": request.tool.qualified_name,
        "riskLevel": request.tool.risk_level,
        "approvalRequired": request.tool.approval_required,
        "payload": dict(request.input_payload),
    }
    if request.tool_call_id is not None:
        payload["toolCallId"] = request.tool_call_id
    return payload


def payload_checksum(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def admit_tool_execution(
    request: ToolExecutionRequest,
    policy: ToolPolicy,
) -> ToolAdmissionDecision:
    request.validate()
    sandbox_policy = SandboxPolicy.from_names(policy.sandboxed_tool_names)
    sandbox_failure_reason = sandbox_policy.admission_failure_reason(request.tool)
    if sandbox_failure_reason is not None:
        return ToolAdmissionDecision(
            allowed=False,
            requires_approval=False,
            reason=sandbox_failure_reason,
            idempotency_key=request.idempotency_key,
            approval_id=request.approval_id,
        )
    if request.tool.approval_required and not policy.allow_write_without_approval:
        if request.approval_id not in policy.approved_approval_ids:
            return ToolAdmissionDecision(
                allowed=False,
                requires_approval=True,
                reason="approval_required",
                idempotency_key=request.idempotency_key,
                approval_id=request.approval_id,
            )
    return ToolAdmissionDecision(
        allowed=True,
        requires_approval=False,
        reason="allowed",
        idempotency_key=request.idempotency_key,
        approval_id=request.approval_id,
    )
