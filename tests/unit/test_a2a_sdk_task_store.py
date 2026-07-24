from __future__ import annotations

from dataclasses import dataclass, field

from a2a.server.context import ServerCallContext
from a2a.types.a2a_pb2 import ListTasksRequest, Task, TaskState

from reactor.a2a.sdk_task_store import (
    ReactorA2ASdkTaskStore,
    status_from_task,
    task_from_payload,
    task_to_payload,
)


@dataclass
class FakeSdkPersistence:
    saved: dict[str, object] | None = None
    deleted: tuple[str, str] | None = None
    payloads: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    list_calls: list[dict[str, object]] = field(default_factory=list[dict[str, object]])

    async def save_sdk_task(
        self,
        *,
        tenant_id: str,
        task_id: str,
        context_id: str,
        status: str,
        payload: dict[str, object],
    ) -> None:
        self.saved = {
            "tenant_id": tenant_id,
            "task_id": task_id,
            "context_id": context_id,
            "status": status,
            "payload": payload,
        }
        self.payloads = [payload]

    async def get_sdk_task(self, *, tenant_id: str, task_id: str) -> dict[str, object] | None:
        if tenant_id == "tenant_1" and task_id == "task_1" and self.payloads:
            return self.payloads[0]
        return None

    async def list_sdk_tasks(
        self,
        *,
        tenant_id: str,
        context_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, object]]:
        self.list_calls.append(
            {
                "tenant_id": tenant_id,
                "context_id": context_id,
                "limit": limit,
                "offset": offset,
            }
        )
        return self.payloads[offset : offset + limit]

    async def delete_sdk_task(self, *, tenant_id: str, task_id: str) -> None:
        self.deleted = (tenant_id, task_id)


async def test_reactor_a2a_sdk_task_store_round_trips_proto_task() -> None:
    persistence = FakeSdkPersistence()
    store = ReactorA2ASdkTaskStore(persistence=persistence)
    task = Task(id="task_1", context_id="ctx_1")
    task.status.state = TaskState.TASK_STATE_COMPLETED
    context = ServerCallContext(tenant="tenant_1")

    await store.save(task, context)
    loaded = await store.get("task_1", context)
    listed = await store.list(ListTasksRequest(page_size=10), context)

    assert persistence.saved is not None
    assert persistence.saved["tenant_id"] == "tenant_1"
    assert persistence.saved["status"] == "completed"
    assert loaded is not None
    assert loaded.id == "task_1"
    assert loaded.status.state == TaskState.TASK_STATE_COMPLETED
    assert listed.total_size == 1
    assert listed.tasks[0].id == "task_1"


async def test_reactor_a2a_sdk_task_store_deletes_by_tenant_and_task() -> None:
    persistence = FakeSdkPersistence()
    store = ReactorA2ASdkTaskStore(persistence=persistence)

    await store.delete("task_1", ServerCallContext(tenant="tenant_1"))

    assert persistence.deleted == ("tenant_1", "task_1")


def test_a2a_sdk_task_payload_conversion_preserves_status() -> None:
    task = Task(id="task_1", context_id="ctx_1")
    task.status.state = TaskState.TASK_STATE_WORKING

    payload = task_to_payload(task)
    restored = task_from_payload(payload)

    assert restored.id == "task_1"
    assert restored.context_id == "ctx_1"
    assert restored.status.state == TaskState.TASK_STATE_WORKING
    assert status_from_task(restored) == "working"


async def test_reactor_a2a_sdk_task_store_returns_next_page_token() -> None:
    persistence = FakeSdkPersistence(
        payloads=[
            task_to_payload(Task(id="task_1", context_id="ctx_1")),
            task_to_payload(Task(id="task_2", context_id="ctx_1")),
            task_to_payload(Task(id="task_3", context_id="ctx_1")),
        ]
    )
    store = ReactorA2ASdkTaskStore(persistence=persistence)
    context = ServerCallContext(tenant="tenant_1")

    first_page = await store.list(ListTasksRequest(context_id="ctx_1", page_size=2), context)
    second_page = await store.list(
        ListTasksRequest(context_id="ctx_1", page_size=2, page_token=first_page.next_page_token),
        context,
    )

    assert [task.id for task in first_page.tasks] == ["task_1", "task_2"]
    expected_second_page_offset = str(2)
    assert first_page.next_page_token == expected_second_page_offset
    assert [task.id for task in second_page.tasks] == ["task_3"]
    assert second_page.next_page_token == ""
    assert persistence.list_calls == [
        {"tenant_id": "tenant_1", "context_id": "ctx_1", "limit": 3, "offset": 0},
        {"tenant_id": "tenant_1", "context_id": "ctx_1", "limit": 3, "offset": 2},
    ]


async def test_reactor_a2a_sdk_task_store_rejects_invalid_page_token() -> None:
    persistence = FakeSdkPersistence()
    store = ReactorA2ASdkTaskStore(persistence=persistence)
    request = ListTasksRequest(page_size=2)
    bad_cursor = "not-an-offset"
    request.page_token = bad_cursor

    try:
        await store.list(
            request,
            ServerCallContext(tenant="tenant_1"),
        )
    except ValueError as exc:
        assert str(exc) == "invalid A2A task page token"
    else:
        raise AssertionError("expected invalid page token to fail closed")


async def test_reactor_a2a_sdk_task_store_rejects_invalid_page_size() -> None:
    persistence = FakeSdkPersistence()
    store = ReactorA2ASdkTaskStore(persistence=persistence)

    try:
        await store.list(
            ListTasksRequest(page_size=-1),
            ServerCallContext(tenant="tenant_1"),
        )
    except ValueError as exc:
        assert str(exc) == "invalid A2A task page size"
    else:
        raise AssertionError("expected invalid page size to fail closed")
