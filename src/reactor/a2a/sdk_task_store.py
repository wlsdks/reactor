from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from a2a.server.context import ServerCallContext
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.tasks.task_store import TaskStore
from a2a.types.a2a_pb2 import ListTasksRequest, ListTasksResponse, Task, TaskState
from google.protobuf.json_format import MessageToDict, ParseDict


class A2ASdkTaskPersistence(Protocol):
    async def save_sdk_task(
        self,
        *,
        tenant_id: str,
        task_id: str,
        context_id: str,
        status: str,
        payload: dict[str, object],
    ) -> None: ...

    async def get_sdk_task(self, *, tenant_id: str, task_id: str) -> dict[str, object] | None: ...

    async def list_sdk_tasks(
        self,
        *,
        tenant_id: str,
        context_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, object]]: ...

    async def delete_sdk_task(self, *, tenant_id: str, task_id: str) -> None: ...


@dataclass(frozen=True)
class ReactorA2ASdkTaskStore(TaskStore):
    persistence: A2ASdkTaskPersistence

    async def save(self, task: Task, context: ServerCallContext) -> None:
        await self.persistence.save_sdk_task(
            tenant_id=tenant_from_context(context),
            task_id=task.id,
            context_id=task.context_id,
            status=status_from_task(task),
            payload=task_to_payload(task),
        )

    async def get(self, task_id: str, context: ServerCallContext) -> Task | None:
        payload = await self.persistence.get_sdk_task(
            tenant_id=tenant_from_context(context),
            task_id=task_id,
        )
        if payload is None:
            return None
        return task_from_payload(payload)

    async def list(
        self,
        params: ListTasksRequest,
        context: ServerCallContext,
    ) -> ListTasksResponse:
        page_size = page_size_from_params(params)
        offset = offset_from_page_token(params.page_token)
        payloads = await self.persistence.list_sdk_tasks(
            tenant_id=tenant_from_context(context),
            context_id=params.context_id or None,
            limit=page_size + 1,
            offset=offset,
        )
        page_payloads = payloads[:page_size]
        tasks = [task_from_payload(payload) for payload in page_payloads]
        next_page_token = str(offset + page_size) if len(payloads) > page_size else ""
        return ListTasksResponse(
            tasks=tasks,
            total_size=len(tasks),
            page_size=page_size,
            next_page_token=next_page_token,
        )

    async def delete(self, task_id: str, context: ServerCallContext) -> None:
        await self.persistence.delete_sdk_task(
            tenant_id=tenant_from_context(context),
            task_id=task_id,
        )


@dataclass(frozen=True)
class LazyReactorA2ASdkTaskStore(TaskStore):
    fallback: TaskStore

    @classmethod
    def with_in_memory_fallback(cls) -> LazyReactorA2ASdkTaskStore:
        return cls(fallback=InMemoryTaskStore())

    async def save(self, task: Task, context: ServerCallContext) -> None:
        store = self._store_from_context(context)
        await store.save(task, context)

    async def get(self, task_id: str, context: ServerCallContext) -> Task | None:
        store = self._store_from_context(context)
        return await store.get(task_id, context)

    async def list(
        self,
        params: ListTasksRequest,
        context: ServerCallContext,
    ) -> ListTasksResponse:
        store = self._store_from_context(context)
        return await store.list(params, context)

    async def delete(self, task_id: str, context: ServerCallContext) -> None:
        store = self._store_from_context(context)
        await store.delete(task_id, context)

    def _store_from_context(self, context: ServerCallContext) -> TaskStore:
        app = context.state.get("reactor_app")
        reactor = getattr(getattr(app, "state", None), "reactor", None)
        persistence = reactor.a2a_task_store() if reactor is not None else None
        if persistence is None:
            return self.fallback
        return ReactorA2ASdkTaskStore(persistence=persistence)


def tenant_from_context(context: ServerCallContext) -> str:
    return context.tenant or "local"


def offset_from_page_token(page_token: str) -> int:
    if not page_token:
        return 0
    if not page_token.isdecimal():
        raise ValueError("invalid A2A task page token")
    return int(page_token)


def page_size_from_params(params: ListTasksRequest) -> int:
    if params.page_size < 0:
        raise ValueError("invalid A2A task page size")
    return params.page_size or 100


def task_to_payload(task: Task) -> dict[str, object]:
    return MessageToDict(task, preserving_proto_field_name=True)


def task_from_payload(payload: dict[str, object]) -> Task:
    task = Task()
    ParseDict(payload, task)
    return task


def status_from_task(task: Task) -> str:
    if not task.HasField("status"):
        return "submitted"
    state_name = TaskState.Name(task.status.state).lower()
    return {
        "task_state_submitted": "submitted",
        "task_state_working": "working",
        "task_state_input_required": "input_required",
        "task_state_auth_required": "input_required",
        "task_state_completed": "completed",
        "task_state_failed": "failed",
        "task_state_rejected": "failed",
        "task_state_canceled": "cancelled",
        "task_state_cancelled": "cancelled",
    }.get(state_name, "submitted")
