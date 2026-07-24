from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.evals.models import AgentEvalCaseRecord, AgentEvalStoredResultRecord
from reactor.persistence.models import AgentEvalCase, AgentEvalResult


class SqlAlchemyEvalCaseStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, record: AgentEvalCaseRecord) -> AgentEvalCaseRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    insert(AgentEvalCase)
                    .values(eval_case_values(record))
                    .on_conflict_do_update(
                        index_elements=[AgentEvalCase.id],
                        set_=eval_case_values(record, include_id=False, include_created_at=False),
                    )
                    .returning(AgentEvalCase)
                )
                if row is None:
                    raise RuntimeError("agent eval case upsert did not return a row")
                return eval_case_from_model(row)

    async def find_by_id(self, *, tenant_id: str, case_id: str) -> AgentEvalCaseRecord | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(AgentEvalCase).where(
                    AgentEvalCase.tenant_id == tenant_id,
                    AgentEvalCase.id == case_id,
                )
            )
            return eval_case_from_model(row) if row is not None else None

    async def list(
        self,
        *,
        tenant_id: str,
        enabled_only: bool = True,
        tags: set[str] | None = None,
        limit: int = 100,
    ) -> list[AgentEvalCaseRecord]:
        conditions = [AgentEvalCase.tenant_id == tenant_id]
        if enabled_only:
            conditions.append(AgentEvalCase.enabled.is_(True))
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(AgentEvalCase)
                .where(*conditions)
                .order_by(AgentEvalCase.updated_at.desc())
                .limit(max(0, min(limit, 500)))
            )
            records = [eval_case_from_model(row) for row in rows]
        if tags:
            records = [record for record in records if set(record.tags).issuperset(tags)]
        return records

    async def delete(self, *, tenant_id: str, case_id: str) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.scalar(
                    delete(AgentEvalCase)
                    .where(
                        AgentEvalCase.tenant_id == tenant_id,
                        AgentEvalCase.id == case_id,
                    )
                    .returning(AgentEvalCase.id)
                )
                return result is not None


class SqlAlchemyEvalResultStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, record: AgentEvalStoredResultRecord) -> AgentEvalStoredResultRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    insert(AgentEvalResult)
                    .values(eval_result_values(record))
                    .on_conflict_do_update(
                        index_elements=[AgentEvalResult.id],
                        set_=eval_result_values(record, include_id=False),
                    )
                    .returning(AgentEvalResult)
                )
                if row is None:
                    raise RuntimeError("agent eval result upsert did not return a row")
                return eval_result_from_model(row)

    async def list(
        self,
        *,
        tenant_id: str,
        case_id: str | None = None,
        tier: str | None = None,
        limit: int = 100,
    ) -> list[AgentEvalStoredResultRecord]:
        conditions = [AgentEvalResult.tenant_id == tenant_id]
        if case_id:
            conditions.append(AgentEvalResult.case_id == case_id)
        if tier:
            conditions.append(AgentEvalResult.tier == tier)
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(AgentEvalResult)
                .where(*conditions)
                .order_by(AgentEvalResult.evaluated_at.desc())
                .limit(max(0, min(limit, 500)))
            )
            return [eval_result_from_model(row) for row in rows]

    async def delete_by_case_id(self, *, tenant_id: str, case_id: str) -> int:
        async with self._session_factory() as session:
            async with session.begin():
                ids = await session.scalars(
                    delete(AgentEvalResult)
                    .where(
                        AgentEvalResult.tenant_id == tenant_id,
                        AgentEvalResult.case_id == case_id,
                    )
                    .returning(AgentEvalResult.id)
                )
                return len(list(ids))

    async def analytics_runs(
        self, *, tenant_id: str, from_time: datetime
    ) -> list[dict[str, object]]:
        async with self._session_factory() as session:
            rows = await session.execute(
                select(
                    AgentEvalResult.run_id.label("eval_run_id"),
                    func.count(AgentEvalResult.id).label("total_cases"),
                    func.sum(case((AgentEvalResult.passed.is_(True), 1), else_=0)).label(
                        "pass_count"
                    ),
                    func.avg(AgentEvalResult.score).label("avg_score"),
                    func.min(AgentEvalResult.evaluated_at).label("started_at"),
                    func.max(AgentEvalResult.evaluated_at).label("ended_at"),
                )
                .where(
                    AgentEvalResult.tenant_id == tenant_id,
                    AgentEvalResult.evaluated_at >= from_time,
                    AgentEvalResult.run_id.is_not(None),
                )
                .group_by(AgentEvalResult.run_id)
                .order_by(func.max(AgentEvalResult.evaluated_at).desc())
            )
            return [
                {
                    "eval_run_id": row.eval_run_id,
                    "total_cases": int(row.total_cases or 0),
                    "pass_count": int(row.pass_count or 0),
                    "avg_score": round(float(row.avg_score or 0), 6),
                    "avg_latency_ms": 0,
                    "total_tokens": 0,
                    "total_cost": 0,
                    "started_at": datetime_iso(row.started_at),
                    "ended_at": datetime_iso(row.ended_at),
                }
                for row in rows
            ]

    async def analytics_pass_rate(
        self, *, tenant_id: str, from_time: datetime
    ) -> list[dict[str, object]]:
        day = func.date(AgentEvalResult.evaluated_at)
        async with self._session_factory() as session:
            rows = await session.execute(
                select(
                    day.label("day"),
                    func.count(AgentEvalResult.id).label("total"),
                    func.sum(case((AgentEvalResult.passed.is_(True), 1), else_=0)).label("passed"),
                    func.avg(AgentEvalResult.score).label("avg_score"),
                )
                .where(
                    AgentEvalResult.tenant_id == tenant_id,
                    AgentEvalResult.evaluated_at >= from_time,
                )
                .group_by(day)
                .order_by(day.desc())
            )
            return [
                {
                    "day": str(row.day),
                    "total": int(row.total or 0),
                    "passed": int(row.passed or 0),
                    "avg_score": round(float(row.avg_score or 0), 6),
                }
                for row in rows
            ]


def eval_case_values(
    record: AgentEvalCaseRecord,
    *,
    include_id: bool = True,
    include_created_at: bool = True,
) -> dict[str, object]:
    values: dict[str, object] = {
        "tenant_id": record.tenant_id,
        "name": record.name,
        "user_input": record.user_input,
        "expected_answer_contains": list(record.expected_answer_contains),
        "forbidden_answer_contains": list(record.forbidden_answer_contains),
        "expected_tool_names": list(record.expected_tool_names),
        "forbidden_tool_names": list(record.forbidden_tool_names),
        "expected_exposed_tool_names": list(record.expected_exposed_tool_names),
        "forbidden_exposed_tool_names": list(record.forbidden_exposed_tool_names),
        "max_tool_exposure_count": record.max_tool_exposure_count,
        "agent_type": record.agent_type,
        "model": record.model,
        "enabled": record.enabled,
        "tags": list(record.tags),
        "min_score": record.min_score,
        "source_run_id": record.source_run_id,
        "updated_at": record.updated_at,
    }
    if include_id:
        values["id"] = record.id
    if include_created_at:
        values["created_at"] = record.created_at
    return values


def eval_result_values(
    record: AgentEvalStoredResultRecord,
    *,
    include_id: bool = True,
) -> dict[str, object]:
    values: dict[str, object] = {
        "tenant_id": record.tenant_id,
        "case_id": record.case_id,
        "run_id": record.run_id,
        "tier": record.tier,
        "passed": record.passed,
        "score": record.score,
        "reasons": list(record.reasons),
        "evaluated_at": record.evaluated_at,
    }
    if include_id:
        values["id"] = record.id
    return values


def datetime_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def eval_case_from_model(row: AgentEvalCase) -> AgentEvalCaseRecord:
    return AgentEvalCaseRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        user_input=row.user_input,
        expected_answer_contains=tuple(row.expected_answer_contains),
        forbidden_answer_contains=tuple(row.forbidden_answer_contains),
        expected_tool_names=tuple(row.expected_tool_names),
        forbidden_tool_names=tuple(row.forbidden_tool_names),
        expected_exposed_tool_names=tuple(row.expected_exposed_tool_names),
        forbidden_exposed_tool_names=tuple(row.forbidden_exposed_tool_names),
        max_tool_exposure_count=row.max_tool_exposure_count,
        agent_type=row.agent_type,
        model=row.model,
        enabled=row.enabled,
        tags=tuple(row.tags),
        min_score=row.min_score,
        source_run_id=row.source_run_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def eval_result_from_model(row: AgentEvalResult) -> AgentEvalStoredResultRecord:
    return AgentEvalStoredResultRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        case_id=row.case_id,
        run_id=row.run_id,
        tier=row.tier,
        passed=row.passed,
        score=row.score,
        reasons=tuple(row.reasons),
        evaluated_at=row.evaluated_at,
    )
