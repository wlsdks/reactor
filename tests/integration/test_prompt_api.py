from __future__ import annotations

from datetime import datetime

from httpx import ASGITransport, AsyncClient

from reactor.api.app import create_app
from reactor.persistence.prompt_store import (
    LEGACY_PROMPT_CHANGE_LOG_KEY,
    LEGACY_PROMPT_STATUS_ACTIVE,
    LEGACY_PROMPT_STATUS_ARCHIVED,
    LEGACY_PROMPT_STATUS_DRAFT,
    LEGACY_PROMPT_STATUS_KEY,
    PromptReleaseRecord,
    PromptTemplateRecord,
    PromptVersionRecord,
    ReleasedPromptRecord,
    legacy_content_hash,
)
from reactor.prompts.profiles import PromptProfile, PromptRelease

ADMIN_HEADERS = {
    "X-Reactor-User-Id": "admin_1",
    "X-Reactor-Tenant-Id": "tenant_1",
    "X-Reactor-Role": "ADMIN",
}


async def test_prompt_release_api_requires_prompt_permission_and_persistence() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.get("/v1/admin/prompts/support/releases/production")
        unavailable = await client.get(
            "/v1/admin/prompts/support/releases/production",
            headers=ADMIN_HEADERS,
        )

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "permission required: prompt:read"
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"] == "prompt persistence is not configured"


async def test_prompt_release_admin_flow_with_store() -> None:
    store = FakePromptStore()
    app = create_app()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        template_response = await client.post(
            "/v1/admin/prompts/templates",
            headers=ADMIN_HEADERS,
            json={
                "name": "support",
                "graphProfile": "rag",
                "description": "Support RAG prompt",
            },
        )
        template_id = template_response.json()["id"]
        version_response = await client.post(
            f"/v1/admin/prompts/templates/{template_id}/versions",
            headers=ADMIN_HEADERS,
            json={
                "version": "2026-06-26",
                "systemPolicy": "Follow Reactor policy.",
                "developerPolicy": "Answer with citations.",
                "examples": ["Use source labels."],
                "metadata": {"owner": "platform"},
            },
        )
        version_id = version_response.json()["id"]
        release_response = await client.post(
            f"/v1/admin/prompts/templates/{template_id}/releases",
            headers=ADMIN_HEADERS,
            json={
                "versionId": version_id,
                "environment": "production",
                "metadata": {"ticket": "PROMPT-1"},
            },
        )
        fetched_response = await client.get(
            "/v1/admin/prompts/support/releases/production",
            headers=ADMIN_HEADERS,
        )

    assert template_response.status_code == 200
    assert template_response.json()["tenantId"] == "tenant_1"
    assert version_response.status_code == 200
    assert (
        version_response.json()["contentHash"]
        == PromptRelease(
            profile=PromptProfile(
                name="support",
                system_policy="Follow Reactor policy.",
                graph_profile="rag",
                version="2026-06-26",
            ),
            developer_policy="Answer with citations.",
            examples=["Use source labels."],
            metadata={"owner": "platform"},
        ).content_hash
    )
    assert release_response.status_code == 200
    assert release_response.json()["environment"] == "production"
    assert fetched_response.status_code == 200
    body = fetched_response.json()
    assert body["template"]["name"] == "support"
    assert body["version"]["version"] == "2026-06-26"
    assert body["release"]["releasedBy"] == "admin_1"
    assert body["promptRelease"]["contentHash"] == version_response.json()["contentHash"]


async def test_legacy_prompt_template_flow_with_store() -> None:
    store = FakePromptStore()
    app = create_app()
    app.state.reactor = FakeContainer(store)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        forbidden = await client.post(
            "/api/prompt-templates",
            json={"name": "support", "description": "Support prompt"},
        )
        created = await client.post(
            "/api/prompt-templates",
            headers=ADMIN_HEADERS,
            json={"name": "support", "description": "Support prompt"},
        )
        template_id = created.json()["id"]
        first_version = await client.post(
            f"/api/prompt-templates/{template_id}/versions",
            headers=ADMIN_HEADERS,
            json={"content": "You are helpful.", "changeLog": "initial"},
        )
        second_version = await client.post(
            f"/api/prompt-templates/{template_id}/versions",
            headers=ADMIN_HEADERS,
            json={"content": "You are careful.", "changeLog": "safer"},
        )
        activated_first = await client.put(
            f"/api/prompt-templates/{template_id}/versions/{first_version.json()['id']}/activate",
            headers=ADMIN_HEADERS,
        )
        activated_second = await client.put(
            f"/api/prompt-templates/{template_id}/versions/{second_version.json()['id']}/activate",
            headers=ADMIN_HEADERS,
        )
        fetched = await client.get(
            f"/api/prompt-templates/{template_id}",
            headers=ADMIN_HEADERS,
        )
        listed = await client.get("/api/prompt-templates", headers=ADMIN_HEADERS)
        archived = await client.put(
            f"/api/prompt-templates/{template_id}/versions/{second_version.json()['id']}/archive",
            headers=ADMIN_HEADERS,
        )
        deleted = await client.delete(f"/api/prompt-templates/{template_id}", headers=ADMIN_HEADERS)
        missing = await client.get(f"/api/prompt-templates/{template_id}", headers=ADMIN_HEADERS)

    assert forbidden.status_code == 403
    assert created.status_code == 201
    assert created.json()["name"] == "support"
    assert first_version.status_code == 201
    assert first_version.json()["version"] == 1
    assert first_version.json()["status"] == "DRAFT"
    assert first_version.json()["changeLog"] == "initial"
    assert second_version.json()["version"] == 2
    assert activated_first.json()["status"] == "ACTIVE"
    assert activated_second.json()["status"] == "ACTIVE"
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["activeVersion"]["id"] == second_version.json()["id"]
    assert [version["status"] for version in body["versions"]] == ["ARCHIVED", "ACTIVE"]
    assert listed.json()[0]["id"] == template_id
    assert archived.json()["status"] == "ARCHIVED"
    assert deleted.status_code == 204
    assert missing.status_code == 404


class FakeContainer:
    def __init__(self, store: FakePromptStore | None) -> None:
        self._store = store

    def prompt_store(self) -> FakePromptStore | None:
        return self._store


class FakePromptStore:
    def __init__(self) -> None:
        self.templates: dict[str, PromptTemplateRecord] = {}
        self.versions: dict[str, PromptVersionRecord] = {}
        self.releases: dict[tuple[str, str], PromptReleaseRecord] = {}

    async def list_templates(self, *, tenant_id: str) -> list[PromptTemplateRecord]:
        return sorted(
            [record for record in self.templates.values() if record.tenant_id == tenant_id],
            key=lambda record: record.created_at,
        )

    async def save_template(self, record: PromptTemplateRecord) -> PromptTemplateRecord:
        record.validate()
        self.templates[record.id] = record
        return record

    async def find_template_by_id(
        self,
        *,
        tenant_id: str,
        template_id: str,
    ) -> PromptTemplateRecord | None:
        record = self.templates.get(template_id)
        return record if record is not None and record.tenant_id == tenant_id else None

    async def update_template(
        self,
        *,
        tenant_id: str,
        template_id: str,
        name: str | None,
        description: str | None,
        updated_at: datetime,
    ) -> PromptTemplateRecord | None:
        record = await self.find_template_by_id(tenant_id=tenant_id, template_id=template_id)
        if record is None:
            return None
        updated = PromptTemplateRecord(
            id=record.id,
            tenant_id=record.tenant_id,
            name=name if name is not None else record.name,
            graph_profile=record.graph_profile,
            description=description if description is not None else record.description,
            created_by=record.created_by,
            created_at=record.created_at,
            updated_at=updated_at,
        )
        self.templates[record.id] = updated
        return updated

    async def delete_template(self, *, tenant_id: str, template_id: str) -> None:
        record = await self.find_template_by_id(tenant_id=tenant_id, template_id=template_id)
        if record is None:
            return
        self.templates.pop(template_id, None)
        self.versions = {
            version_id: version
            for version_id, version in self.versions.items()
            if version.template_id != template_id
        }

    async def save_version(self, record: PromptVersionRecord) -> PromptVersionRecord:
        record.validate()
        self.versions[record.id] = record
        return record

    async def list_versions(
        self,
        *,
        tenant_id: str,
        template_id: str,
    ) -> list[PromptVersionRecord]:
        return sorted(
            [
                record
                for record in self.versions.values()
                if record.tenant_id == tenant_id and record.template_id == template_id
            ],
            key=lambda record: int(record.version) if record.version.isdigit() else 0,
        )

    async def create_legacy_version(
        self,
        *,
        tenant_id: str,
        template_id: str,
        content: str,
        change_log: str,
        created_by: str,
        created_at: datetime,
        version_id: str,
    ) -> PromptVersionRecord | None:
        template = await self.find_template_by_id(tenant_id=tenant_id, template_id=template_id)
        if template is None:
            return None
        versions = await self.list_versions(tenant_id=tenant_id, template_id=template_id)
        next_version = max((int(record.version) for record in versions), default=0) + 1
        record = PromptVersionRecord(
            id=version_id,
            template_id=template_id,
            tenant_id=tenant_id,
            version=str(next_version),
            system_policy=content,
            developer_policy="",
            examples=[],
            metadata={
                LEGACY_PROMPT_STATUS_KEY: LEGACY_PROMPT_STATUS_DRAFT,
                LEGACY_PROMPT_CHANGE_LOG_KEY: change_log,
            },
            content_hash=legacy_content_hash(
                template_name=template.name,
                graph_profile=template.graph_profile,
                version=str(next_version),
                content=content,
                change_log=change_log,
            ),
            created_by=created_by,
            created_at=created_at,
        )
        self.versions[record.id] = record
        return record

    async def activate_legacy_version(
        self,
        *,
        tenant_id: str,
        template_id: str,
        version_id: str,
    ) -> PromptVersionRecord | None:
        versions = await self.list_versions(tenant_id=tenant_id, template_id=template_id)
        target = next((record for record in versions if record.id == version_id), None)
        if target is None:
            return None
        for record in versions:
            if record.metadata.get(LEGACY_PROMPT_STATUS_KEY) == LEGACY_PROMPT_STATUS_ACTIVE:
                self.versions[record.id] = replace_fake_legacy_status(
                    record, LEGACY_PROMPT_STATUS_ARCHIVED
                )
        updated = replace_fake_legacy_status(target, LEGACY_PROMPT_STATUS_ACTIVE)
        self.versions[updated.id] = updated
        return updated

    async def archive_legacy_version(
        self,
        *,
        tenant_id: str,
        template_id: str,
        version_id: str,
    ) -> PromptVersionRecord | None:
        versions = await self.list_versions(tenant_id=tenant_id, template_id=template_id)
        target = next((record for record in versions if record.id == version_id), None)
        if target is None:
            return None
        updated = replace_fake_legacy_status(target, LEGACY_PROMPT_STATUS_ARCHIVED)
        self.versions[updated.id] = updated
        return updated

    async def save_release(self, record: PromptReleaseRecord) -> PromptReleaseRecord:
        record.validate()
        self.releases[(record.template_id, record.environment)] = record
        return record

    async def find_released(
        self,
        *,
        tenant_id: str,
        template_name: str,
        environment: str,
    ) -> ReleasedPromptRecord | None:
        for template in self.templates.values():
            release = self.releases.get((template.id, environment))
            if (
                template.tenant_id == tenant_id
                and template.name == template_name
                and release is not None
            ):
                return ReleasedPromptRecord(
                    template=template,
                    version=self.versions[release.version_id],
                    release=release,
                )
        return None


def replace_fake_legacy_status(record: PromptVersionRecord, status: str) -> PromptVersionRecord:
    metadata = dict(record.metadata)
    metadata[LEGACY_PROMPT_STATUS_KEY] = status
    return PromptVersionRecord(
        id=record.id,
        template_id=record.template_id,
        tenant_id=record.tenant_id,
        version=record.version,
        system_policy=record.system_policy,
        developer_policy=record.developer_policy,
        examples=record.examples,
        metadata=metadata,
        content_hash=record.content_hash,
        created_by=record.created_by,
        created_at=record.created_at,
    )
