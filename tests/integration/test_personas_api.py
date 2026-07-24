from __future__ import annotations

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.core.settings import Settings
from reactor.prompts.personas import PersonaRecord

ADMIN_HEADERS = {"X-Reactor-Role": "ADMIN", "X-Reactor-User-Id": "admin_1"}
USER_HEADERS = {"X-Reactor-Role": "USER", "X-Reactor-User-Id": "user_1"}


async def test_personas_require_admin_for_collection_and_writes() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden_list = await client.get("/api/personas", headers=USER_HEADERS)
        forbidden_create = await client.post(
            "/api/personas",
            headers=USER_HEADERS,
            json={"name": "Helper", "systemPrompt": "Help users."},
        )
        unavailable_get = await client.get("/api/personas/default")
        unavailable_list = await client.get("/api/personas", headers=ADMIN_HEADERS)

    assert forbidden_list.status_code == 403
    assert forbidden_list.json()["error"] == "관리자 권한이 필요합니다"
    assert forbidden_create.status_code == 403
    assert forbidden_create.json()["error"] == "관리자 권한이 필요합니다"
    assert unavailable_get.status_code == 503
    assert unavailable_get.json()["error"] == "PersonaStore 미등록 — DB 미구성"
    assert unavailable_list.status_code == 503
    assert unavailable_list.json()["error"] == "PersonaStore 미등록 — DB 미구성"


async def test_personas_crud_ports_legacy_contract() -> None:
    store = FakePersonaStore()
    app = create_app()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        created = await client.post(
            "/api/personas",
            headers=ADMIN_HEADERS,
            json={
                "name": "Customer Support",
                "systemPrompt": "Answer support questions.",
                "isDefault": True,
                "description": "Support persona",
                "responseGuideline": "Be concise.",
                "welcomeMessage": "How can I help?",
                "promptTemplateId": "template-1",
                "icon": "CS",
            },
        )
        persona_id = created.json()["id"]
        hidden = await client.post(
            "/v1/personas",
            headers=ADMIN_HEADERS,
            json={
                "name": "Inactive",
                "systemPrompt": "Hidden",
                "isActive": False,
            },
        )
        listed = await client.get("/api/personas", headers=ADMIN_HEADERS)
        active = await client.get("/v1/personas?activeOnly=true", headers=ADMIN_HEADERS)
        fetched_public = await client.get(f"/api/personas/{persona_id}")
        updated = await client.put(
            f"/api/personas/{persona_id}",
            headers=ADMIN_HEADERS,
            json={
                "name": "Customer Support Plus",
                "responseGuideline": "",
                "promptTemplateId": "",
                "isActive": False,
            },
        )
        missing = await client.get("/api/personas/missing")
        deleted = await client.delete(f"/v1/personas/{persona_id}", headers=ADMIN_HEADERS)
        deleted_again = await client.delete("/v1/personas/missing", headers=ADMIN_HEADERS)

    assert created.status_code == 201
    created_body = created.json()
    assert created_body["name"] == "Customer Support"
    assert created_body["systemPrompt"] == "Answer support questions."
    assert created_body["isDefault"] is True
    assert created_body["isActive"] is True
    assert created_body["description"] == "Support persona"
    assert created_body["responseGuideline"] == "Be concise."
    assert created_body["welcomeMessage"] == "How can I help?"
    assert created_body["promptTemplateId"] == "template-1"
    assert created_body["icon"] == "CS"
    assert isinstance(created_body["createdAt"], int)
    assert isinstance(created_body["updatedAt"], int)
    assert hidden.status_code == 201
    assert listed.status_code == 200
    assert [record["name"] for record in listed.json()] == ["Customer Support", "Inactive"]
    assert active.status_code == 200
    assert [record["name"] for record in active.json()] == ["Customer Support"]
    assert fetched_public.status_code == 200
    assert fetched_public.json()["id"] == persona_id
    assert updated.status_code == 200
    assert updated.json()["name"] == "Customer Support Plus"
    assert updated.json()["responseGuideline"] is None
    assert updated.json()["promptTemplateId"] is None
    assert updated.json()["isActive"] is False
    assert missing.status_code == 404
    assert missing.json()["error"] == "Persona not found: missing"
    assert deleted.status_code == 204
    assert deleted_again.status_code == 204
    assert await store.get(persona_id) is None


async def test_personas_default_is_unique_on_save_and_update() -> None:
    store = FakePersonaStore()
    first = await store.save(
        PersonaRecord(
            id="persona_1",
            name="First",
            system_prompt="First prompt",
            is_default=True,
        )
    )
    second = await store.save(
        PersonaRecord(
            id="persona_2",
            name="Second",
            system_prompt="Second prompt",
            is_default=True,
        )
    )
    third = await store.save(
        PersonaRecord(
            id="persona_3",
            name="Third",
            system_prompt="Third prompt",
        )
    )

    assert (await store.get(first.id)).is_default is False  # type: ignore[union-attr]
    assert (await store.get(second.id)).is_default is True  # type: ignore[union-attr]

    await store.update(third.id, is_default=True)

    assert (await store.get(second.id)).is_default is False  # type: ignore[union-attr]
    assert (await store.get(third.id)).is_default is True  # type: ignore[union-attr]
    default = await store.get_default()
    assert default is not None
    assert default.id == third.id


class FakeContainer:
    def __init__(self, persona_store: FakePersonaStore | None) -> None:
        self.settings = Settings()
        self._persona_store = persona_store

    def persona_store(self) -> FakePersonaStore | None:
        return self._persona_store


class FakePersonaStore:
    def __init__(self) -> None:
        self.records: dict[str, PersonaRecord] = {}

    async def list(self) -> list[PersonaRecord]:
        return sorted(self.records.values(), key=lambda record: record.created_at)

    async def list_active(self) -> list[PersonaRecord]:
        return [record for record in await self.list() if record.is_active]

    async def get(self, persona_id: str) -> PersonaRecord | None:
        return self.records.get(persona_id)

    async def get_default(self) -> PersonaRecord | None:
        return next((record for record in self.records.values() if record.is_default), None)

    async def save(self, record: PersonaRecord) -> PersonaRecord:
        record.validate()
        if record.is_default:
            self.records = {
                key: existing.with_updates(is_default=False)
                if existing.is_default and key != record.id
                else existing
                for key, existing in self.records.items()
            }
        if record.created_at.tzinfo is None:
            record = PersonaRecord(
                id=record.id,
                name=record.name,
                system_prompt=record.system_prompt,
                is_default=record.is_default,
                description=record.description,
                response_guideline=record.response_guideline,
                welcome_message=record.welcome_message,
                icon=record.icon,
                is_active=record.is_active,
                prompt_template_id=record.prompt_template_id,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        self.records[record.id] = record
        return record

    async def update(
        self,
        persona_id: str,
        *,
        name: str | None = None,
        system_prompt: str | None = None,
        is_default: bool | None = None,
        description: str | None = None,
        response_guideline: str | None = None,
        welcome_message: str | None = None,
        icon: str | None = None,
        prompt_template_id: str | None = None,
        is_active: bool | None = None,
    ) -> PersonaRecord | None:
        existing = self.records.get(persona_id)
        if existing is None:
            return None
        updated = existing.with_updates(
            name=name,
            system_prompt=system_prompt,
            is_default=is_default,
            description=description,
            response_guideline=response_guideline,
            welcome_message=welcome_message,
            icon=icon,
            prompt_template_id=prompt_template_id,
            is_active=is_active,
        )
        if is_default is True:
            self.records = {
                key: record.with_updates(is_default=False)
                if record.is_default and key != persona_id
                else record
                for key, record in self.records.items()
            }
        self.records[persona_id] = updated
        return updated

    async def delete(self, persona_id: str) -> None:
        self.records.pop(persona_id, None)
