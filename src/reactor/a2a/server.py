from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from a2a.auth.user import User
from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.common import DefaultServerCallContextBuilder
from a2a.server.routes.fastapi_routes import add_a2a_routes_to_fastapi
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.routes.rest_routes import create_rest_routes
from a2a.types.a2a_pb2 import Message, Role, TaskState, TaskStatus, TaskStatusUpdateEvent
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from reactor.a2a.agent_card import build_sdk_agent_card, canonical_a2a_endpoint
from reactor.a2a.sdk_task_store import LazyReactorA2ASdkTaskStore
from reactor.agents.runner import RunResult
from reactor.auth.api_keys import api_key_principal_from_header
from reactor.auth.rbac import AuthPrincipal, UserRole, local_identity_headers_allowed, parse_role
from reactor.core.settings import Settings, get_settings
from reactor.kernel.ids import new_id
from reactor.runs.service import RunService


class ReactorA2AExecutor(AgentExecutor):
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def execute(self, context: Any, event_queue: Any) -> None:
        user_input = str(context.get_user_input()).strip()
        result = await run_a2a_message(context, user_input, self._settings)
        response = Message(
            message_id=new_id("a2amsg"),
            context_id=result.thread_id,
            task_id=str(getattr(context, "task_id", "") or ""),
            role=Role.ROLE_AGENT,
        )
        part = response.parts.add()
        part.text = result.response
        await event_queue.enqueue_event(response)

    async def cancel(self, context: Any, event_queue: Any) -> None:
        await cancel_a2a_task(context)
        response = TaskStatusUpdateEvent(
            context_id=str(getattr(context, "context_id", "") or ""),
            task_id=str(getattr(context, "task_id", "") or ""),
            status=TaskStatus(state=TaskState.TASK_STATE_CANCELED),
        )
        await event_queue.enqueue_event(response)


class ReactorA2AContextBuilder(DefaultServerCallContextBuilder):
    def __init__(self, app: Any) -> None:
        self._app = app

    def build(self, request: Any) -> Any:
        context = super().build(request)
        context.state["reactor_app"] = self._app
        request_principal = a2a_request_principal_from_request(
            request,
            settings_from_app(self._app),
        )
        context.state["reactor_principal"] = request_principal.auth
        context.state["reactor_a2a_peer_agent_id"] = request_principal.peer_agent_id
        context.state["reactor_a2a_skill_id"] = request_principal.skill_id
        context.tenant = request_principal.auth.tenant_id
        context.user = ReactorA2AUser(request_principal.auth)
        return context


class ReactorA2AUser(User):
    def __init__(self, principal: AuthPrincipal) -> None:
        self.principal = principal

    @property
    def is_authenticated(self) -> bool:
        return self.principal.user_id != "anonymous"

    @property
    def user_name(self) -> str:
        return self.principal.user_id

    @property
    def id(self) -> str:
        return self.principal.user_id


@dataclass(frozen=True)
class ReactorA2APrincipal:
    auth: AuthPrincipal
    peer_agent_id: str | None = None
    skill_id: str | None = None


@dataclass(frozen=True)
class A2AServerStatus:
    protocol_version: str
    sdk_available: bool
    endpoint: str
    detail: str


def a2a_server_status(settings: Settings | None = None) -> A2AServerStatus:
    sdk_available = True
    detail = "A2A SDK protocol routes are mounted"
    return A2AServerStatus(
        protocol_version="1.0",
        sdk_available=sdk_available,
        endpoint=canonical_a2a_endpoint(settings) or "/a2a",
        detail=detail,
    )


def mount_a2a_sdk_routes(app: Any) -> bool:
    app.middleware("http")(a2a_api_key_fail_closed_middleware)
    settings = getattr(app.state.reactor, "settings", None)
    agent_card = build_sdk_agent_card(settings if isinstance(settings, Settings) else None)
    context_builder = ReactorA2AContextBuilder(app)
    request_handler = DefaultRequestHandler(
        agent_executor=ReactorA2AExecutor(
            settings=settings if isinstance(settings, Settings) else None
        ),
        task_store=LazyReactorA2ASdkTaskStore.with_in_memory_fallback(),
        agent_card=agent_card,
    )
    add_a2a_routes_to_fastapi(
        app,
        jsonrpc_routes=create_jsonrpc_routes(
            request_handler,
            rpc_url="/a2a",
            context_builder=context_builder,
        ),
        rest_routes=create_rest_routes(
            request_handler,
            context_builder=context_builder,
            path_prefix="/a2a",
        ),
    )
    return True


async def a2a_api_key_fail_closed_middleware(request: Any, call_next: Any) -> Any:
    if not str(request.url.path).startswith("/a2a"):
        return await call_next(request)
    settings = settings_from_app(request.app)
    try:
        request_principal = a2a_request_principal_from_request(request, settings)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    if not await a2a_inbound_allowed(request.app, request_principal):
        return JSONResponse(status_code=403, content={"detail": "A2A inbound access is denied"})
    if not await a2a_inbound_skill_allowed(request.app, request_principal):
        return JSONResponse(status_code=403, content={"detail": "A2A skill is not allowed"})
    return await call_next(request)


async def a2a_inbound_allowed(app: Any, principal: ReactorA2APrincipal) -> bool:
    reactor = getattr(app.state, "reactor", None)
    store_accessor = getattr(reactor, "a2a_task_store", None)
    if store_accessor is None:
        return not a2a_access_policy_required(app)
    store = store_accessor()
    if store is None:
        return not a2a_access_policy_required(app)
    policy_check = getattr(store, "is_inbound_allowed", None)
    if policy_check is None:
        return not a2a_access_policy_required(app)
    allowed = await policy_check(
        tenant_id=principal.auth.tenant_id,
        peer_agent_id=principal.peer_agent_id,
    )
    return bool(allowed)


async def a2a_inbound_skill_allowed(app: Any, principal: ReactorA2APrincipal) -> bool:
    reactor = getattr(app.state, "reactor", None)
    store_accessor = getattr(reactor, "a2a_task_store", None)
    if store_accessor is None:
        return not a2a_access_policy_required(app)
    store = store_accessor()
    if store is None:
        return not a2a_access_policy_required(app)
    policy_check = getattr(store, "is_skill_allowed", None)
    if policy_check is None:
        return not a2a_access_policy_required(app)
    allowed = await policy_check(
        tenant_id=principal.auth.tenant_id,
        peer_agent_id=principal.peer_agent_id,
        skill_id=principal.skill_id,
    )
    return bool(allowed)


def a2a_access_policy_required(app: Any) -> bool:
    settings = settings_from_app(app)
    if settings.database_required:
        return True
    return settings.environment.strip().lower() in {"prod", "production"}


async def run_a2a_message(context: Any, user_input: str, settings: Settings) -> RunResult:
    del settings
    app = reactor_app_from_context(context)
    if app is None:
        raise RuntimeError("Reactor application context is required for A2A execution")
    reactor = getattr(app.state, "reactor", None)
    if reactor is None:
        raise RuntimeError("Reactor application context is required for A2A execution")

    run_lifecycle_publisher_factory = getattr(reactor, "run_lifecycle_publisher", None)
    runtime_settings_store_factory = getattr(reactor, "runtime_settings_store", None)
    service = RunService(
        reactor.settings,
        reactor.run_store(),
        reactor.graph,
        usage_ledger(reactor),
        checkpointer=getattr(reactor, "checkpointer", None),
        graph_store=getattr(reactor, "graph_store", None),
        tool_provider=getattr(reactor, "tool_store", lambda: None)(),
        tool_handler=getattr(reactor, "agent_tool_handler", lambda: None)(),
        tool_invocation_store=getattr(reactor, "tool_invocation_store", lambda: None)(),
        builtin_tool_specs=getattr(reactor, "builtin_tool_specs", None),
        run_lifecycle_publisher=run_lifecycle_publisher_factory()
        if run_lifecycle_publisher_factory is not None
        else None,
        runtime_settings_store=runtime_settings_store_factory()
        if runtime_settings_store_factory is not None
        else None,
        approval_store=getattr(reactor, "approval_store", lambda: None)(),
    )
    return await service.create_run(
        user_input,
        tenant_id=tenant_id_from_context(context),
        user_id=user_id_from_context(context),
        trusted_user_groups=trusted_user_groups_from_context(context),
        thread_id=context_id_from_context(context) or reactor.settings.default_thread_id,
        metadata=a2a_run_metadata(context),
    )


async def cancel_a2a_task(context: Any) -> None:
    app = reactor_app_from_context(context)
    if app is None:
        return
    reactor = getattr(app.state, "reactor", None)
    store_accessor = getattr(reactor, "a2a_task_store", None)
    if store_accessor is None:
        return
    store = store_accessor()
    cancel_task = getattr(store, "cancel_task", None)
    task_id = str(getattr(context, "task_id", "") or "").strip()
    if store is None or cancel_task is None or not task_id:
        return
    await cancel_task(
        tenant_id=tenant_id_from_context(context),
        task_id=task_id,
        cancelled_by=user_id_from_context(context),
        reason="A2A SDK cancel request",
    )


def reactor_app_from_context(context: Any) -> Any | None:
    call_context = getattr(context, "call_context", None)
    state = getattr(call_context, "state", None)
    if not isinstance(state, dict):
        return None
    return cast(Any | None, state.get("reactor_app"))


def usage_ledger(reactor: Any) -> Any | None:
    accessor = getattr(reactor, "usage_ledger", None)
    if accessor is None:
        return None
    return accessor()


def tenant_id_from_context(context: Any) -> str:
    principal = principal_from_context(context)
    if principal is not None:
        return principal.tenant_id
    tenant = str(getattr(context, "tenant", "") or "").strip()
    return tenant or "local"


def user_id_from_context(context: Any) -> str:
    principal = principal_from_context(context)
    if principal is not None:
        return principal.user_id
    call_context = getattr(context, "call_context", None)
    user = getattr(call_context, "user", None)
    user_id = str(getattr(user, "id", "") or "").strip()
    return user_id or "a2a_peer"


def trusted_user_groups_from_context(context: Any) -> tuple[str, ...]:
    principal = principal_from_context(context)
    return principal.groups if principal is not None else ()


def principal_from_context(context: Any) -> AuthPrincipal | None:
    call_context = getattr(context, "call_context", None)
    state = getattr(call_context, "state", None)
    if not isinstance(state, dict):
        return None
    principal = cast(object | None, state.get("reactor_principal"))
    return principal if isinstance(principal, AuthPrincipal) else None


def context_id_from_context(context: Any) -> str | None:
    context_id = str(getattr(context, "context_id", "") or "").strip()
    return context_id or None


def a2a_run_metadata(context: Any) -> dict[str, object]:
    message = getattr(context, "message", None)
    metadata: dict[str, object] = {
        "channel": "a2a",
        "a2aTaskId": str(getattr(context, "task_id", "") or ""),
        "a2aContextId": str(getattr(context, "context_id", "") or ""),
        "a2aMessageId": str(getattr(message, "message_id", "") or ""),
    }
    peer_agent_id = peer_agent_id_from_context(context)
    if peer_agent_id is not None:
        metadata["a2aPeerAgentId"] = peer_agent_id
    skill_id = skill_id_from_context(context)
    if skill_id is not None:
        metadata["a2aSkillId"] = skill_id
    return metadata


def peer_agent_id_from_context(context: Any) -> str | None:
    call_context = getattr(context, "call_context", None)
    state = getattr(call_context, "state", None)
    if not isinstance(state, dict):
        return None
    peer_agent_id = cast(object | None, state.get("reactor_a2a_peer_agent_id"))
    if not isinstance(peer_agent_id, str):
        return None
    peer_agent_id = peer_agent_id.strip()
    return peer_agent_id or None


def skill_id_from_context(context: Any) -> str | None:
    call_context = getattr(context, "call_context", None)
    state = getattr(call_context, "state", None)
    if not isinstance(state, dict):
        return None
    skill_id = cast(object | None, state.get("reactor_a2a_skill_id"))
    if not isinstance(skill_id, str):
        return None
    skill_id = skill_id.strip()
    return skill_id or None


def settings_from_app(app: Any) -> Settings:
    reactor = getattr(app.state, "reactor", None)
    settings = getattr(reactor, "settings", None)
    return settings if isinstance(settings, Settings) else get_settings()


def a2a_principal_from_request(request: Any, settings: Settings) -> AuthPrincipal:
    api_key = request.headers.get("X-Reactor-API-Key")
    api_key_principal = api_key_principal_from_header(api_key, settings=settings)
    if api_key_principal is not None:
        return api_key_principal
    if api_key is not None and str(api_key).strip():
        raise HTTPException(status_code=401, detail="invalid API key")
    if not local_identity_headers_allowed(settings.environment):
        return AuthPrincipal(
            user_id="a2a_peer",
            tenant_id=settings.auth_default_tenant_id,
            role=UserRole.USER,
        )
    role = parse_role(request.headers.get("X-Reactor-Role"))
    if role == UserRole.USER and truthy(request.headers.get("X-Reactor-Admin")):
        role = UserRole.ADMIN
    return AuthPrincipal(
        user_id=(request.headers.get("X-Reactor-User-Id") or "a2a_peer").strip() or "a2a_peer",
        tenant_id=(request.headers.get("X-Reactor-Tenant-Id") or "local").strip() or "local",
        role=role,
        groups=(),
    )


def a2a_request_principal_from_request(request: Any, settings: Settings) -> ReactorA2APrincipal:
    return ReactorA2APrincipal(
        auth=a2a_principal_from_request(request, settings),
        peer_agent_id=optional_peer_agent_id(request),
        skill_id=optional_skill_id(request),
    )


def optional_peer_agent_id(request: Any) -> str | None:
    value = request.headers.get("X-Reactor-A2A-Peer-Id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def optional_skill_id(request: Any) -> str | None:
    value = request.headers.get("X-Reactor-A2A-Skill-Id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "on"}
