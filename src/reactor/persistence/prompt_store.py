from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reactor.persistence.models import PromptRelease, PromptTemplate, PromptVersion

LEGACY_PROMPT_STATUS_KEY = "legacyStatus"
LEGACY_PROMPT_CHANGE_LOG_KEY = "changeLog"
LEGACY_PROMPT_STATUS_DRAFT = "DRAFT"
LEGACY_PROMPT_STATUS_ACTIVE = "ACTIVE"
LEGACY_PROMPT_STATUS_ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class PromptTemplateRecord:
    id: str
    tenant_id: str
    name: str
    graph_profile: str
    description: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime

    def validate(self) -> None:
        for field_name, value in (
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("name", self.name),
            ("graph_profile", self.graph_profile),
            ("created_by", self.created_by),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")


@dataclass(frozen=True)
class PromptVersionRecord:
    id: str
    template_id: str
    tenant_id: str
    version: str
    system_policy: str
    developer_policy: str
    examples: list[str]
    metadata: dict[str, Any]
    content_hash: str
    created_by: str
    created_at: datetime

    def validate(self) -> None:
        for field_name, value in (
            ("id", self.id),
            ("template_id", self.template_id),
            ("tenant_id", self.tenant_id),
            ("version", self.version),
            ("system_policy", self.system_policy),
            ("content_hash", self.content_hash),
            ("created_by", self.created_by),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")
        if not self.content_hash.startswith("sha256:"):
            raise ValueError("content_hash must be a sha256 digest")


@dataclass(frozen=True)
class PromptReleaseRecord:
    id: str
    tenant_id: str
    template_id: str
    version_id: str
    environment: str
    released_by: str
    released_at: datetime
    metadata: dict[str, Any]

    def validate(self) -> None:
        for field_name, value in (
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("template_id", self.template_id),
            ("version_id", self.version_id),
            ("environment", self.environment),
            ("released_by", self.released_by),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")


@dataclass(frozen=True)
class ReleasedPromptRecord:
    template: PromptTemplateRecord
    version: PromptVersionRecord
    release: PromptReleaseRecord


class SqlAlchemyPromptStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_template(self, record: PromptTemplateRecord) -> PromptTemplateRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_prompt_template_upsert(record))
        return record

    async def list_templates(self, *, tenant_id: str) -> list[PromptTemplateRecord]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(PromptTemplate)
                .where(PromptTemplate.tenant_id == tenant_id)
                .order_by(PromptTemplate.created_at.asc())
            )
            templates = result.scalars().all()
        return [prompt_template_record(template) for template in templates]

    async def find_template_by_id(
        self,
        *,
        tenant_id: str,
        template_id: str,
    ) -> PromptTemplateRecord | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(PromptTemplate).where(
                    PromptTemplate.tenant_id == tenant_id,
                    PromptTemplate.id == template_id,
                )
            )
            template = result.scalar_one_or_none()
        if template is None:
            return None
        return prompt_template_record(template)

    async def update_template(
        self,
        *,
        tenant_id: str,
        template_id: str,
        name: str | None,
        description: str | None,
        updated_at: datetime,
    ) -> PromptTemplateRecord | None:
        values: dict[str, Any] = {"updated_at": updated_at}
        if name is not None:
            values["name"] = name
        if description is not None:
            values["description"] = description
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(PromptTemplate)
                    .where(
                        PromptTemplate.tenant_id == tenant_id,
                        PromptTemplate.id == template_id,
                    )
                    .values(**values)
                    .returning(PromptTemplate)
                )
                template = result.scalar_one_or_none()
        if template is None:
            return None
        return prompt_template_record(template)

    async def delete_template(self, *, tenant_id: str, template_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    delete(PromptTemplate).where(
                        PromptTemplate.tenant_id == tenant_id,
                        PromptTemplate.id == template_id,
                    )
                )

    async def save_version(self, record: PromptVersionRecord) -> PromptVersionRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_prompt_version_upsert(record))
        return record

    async def list_versions(
        self,
        *,
        tenant_id: str,
        template_id: str,
    ) -> list[PromptVersionRecord]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(PromptVersion)
                .where(
                    PromptVersion.tenant_id == tenant_id,
                    PromptVersion.template_id == template_id,
                )
                .order_by(PromptVersion.version.asc(), PromptVersion.created_at.asc())
            )
            versions = result.scalars().all()
        return [prompt_version_record(version) for version in versions]

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
        next_version = max((legacy_version_number(version) for version in versions), default=0) + 1
        metadata = {
            LEGACY_PROMPT_STATUS_KEY: LEGACY_PROMPT_STATUS_DRAFT,
            LEGACY_PROMPT_CHANGE_LOG_KEY: change_log,
        }
        record = PromptVersionRecord(
            id=version_id,
            template_id=template_id,
            tenant_id=tenant_id,
            version=str(next_version),
            system_policy=content,
            developer_policy="",
            examples=[],
            metadata=metadata,
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
        return await self.save_version(record)

    async def activate_legacy_version(
        self,
        *,
        tenant_id: str,
        template_id: str,
        version_id: str,
    ) -> PromptVersionRecord | None:
        versions = await self.list_versions(tenant_id=tenant_id, template_id=template_id)
        target = next((version for version in versions if version.id == version_id), None)
        if target is None:
            return None
        async with self._session_factory() as session:
            async with session.begin():
                for version in versions:
                    if legacy_status(version) == LEGACY_PROMPT_STATUS_ACTIVE:
                        await session.execute(
                            update(PromptVersion)
                            .where(PromptVersion.id == version.id)
                            .values(
                                prompt_metadata=legacy_metadata_with_status(
                                    version, LEGACY_PROMPT_STATUS_ARCHIVED
                                )
                            )
                        )
                await session.execute(
                    update(PromptVersion)
                    .where(
                        PromptVersion.tenant_id == tenant_id,
                        PromptVersion.template_id == template_id,
                        PromptVersion.id == version_id,
                    )
                    .values(
                        prompt_metadata=legacy_metadata_with_status(
                            target, LEGACY_PROMPT_STATUS_ACTIVE
                        )
                    )
                )
        return replace_legacy_status(target, LEGACY_PROMPT_STATUS_ACTIVE)

    async def archive_legacy_version(
        self,
        *,
        tenant_id: str,
        template_id: str,
        version_id: str,
    ) -> PromptVersionRecord | None:
        versions = await self.list_versions(tenant_id=tenant_id, template_id=template_id)
        target = next((version for version in versions if version.id == version_id), None)
        if target is None:
            return None
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(PromptVersion)
                    .where(
                        PromptVersion.tenant_id == tenant_id,
                        PromptVersion.template_id == template_id,
                        PromptVersion.id == version_id,
                    )
                    .values(
                        prompt_metadata=legacy_metadata_with_status(
                            target, LEGACY_PROMPT_STATUS_ARCHIVED
                        )
                    )
                )
        return replace_legacy_status(target, LEGACY_PROMPT_STATUS_ARCHIVED)

    async def save_release(self, record: PromptReleaseRecord) -> PromptReleaseRecord:
        record.validate()
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(build_prompt_release_upsert(record))
        return record

    async def find_released(
        self,
        *,
        tenant_id: str,
        template_name: str,
        environment: str,
    ) -> ReleasedPromptRecord | None:
        async with self._session_factory() as session:
            result = await session.execute(
                build_released_prompt_find(
                    tenant_id=tenant_id,
                    template_name=template_name,
                    environment=environment,
                )
            )
            row = result.first()
        if row is None:
            return None
        template, version, release = row.t
        return ReleasedPromptRecord(
            template=prompt_template_record(template),
            version=prompt_version_record(version),
            release=PromptReleaseRecord(
                id=release.id,
                tenant_id=release.tenant_id,
                template_id=release.template_id,
                version_id=release.version_id,
                environment=release.environment,
                released_by=release.released_by,
                released_at=release.released_at,
                metadata=dict(release.release_metadata),
            ),
        )


def prompt_template_record(template: PromptTemplate) -> PromptTemplateRecord:
    return PromptTemplateRecord(
        id=template.id,
        tenant_id=template.tenant_id,
        name=template.name,
        graph_profile=template.graph_profile,
        description=template.description,
        created_by=template.created_by,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def prompt_version_record(version: PromptVersion) -> PromptVersionRecord:
    return PromptVersionRecord(
        id=version.id,
        template_id=version.template_id,
        tenant_id=version.tenant_id,
        version=version.version,
        system_policy=version.system_policy,
        developer_policy=version.developer_policy,
        examples=list(version.examples),
        metadata=dict(version.prompt_metadata),
        content_hash=version.content_hash,
        created_by=version.created_by,
        created_at=version.created_at,
    )


def legacy_version_number(record: PromptVersionRecord) -> int:
    try:
        return int(record.version)
    except ValueError:
        return 0


def legacy_status(record: PromptVersionRecord) -> str:
    status = record.metadata.get(LEGACY_PROMPT_STATUS_KEY)
    return status if isinstance(status, str) and status else LEGACY_PROMPT_STATUS_DRAFT


def legacy_change_log(record: PromptVersionRecord) -> str:
    change_log = record.metadata.get(LEGACY_PROMPT_CHANGE_LOG_KEY)
    return change_log if isinstance(change_log, str) else ""


def legacy_metadata_with_status(record: PromptVersionRecord, status: str) -> dict[str, Any]:
    metadata = dict(record.metadata)
    metadata[LEGACY_PROMPT_STATUS_KEY] = status
    return metadata


def replace_legacy_status(record: PromptVersionRecord, status: str) -> PromptVersionRecord:
    return PromptVersionRecord(
        id=record.id,
        template_id=record.template_id,
        tenant_id=record.tenant_id,
        version=record.version,
        system_policy=record.system_policy,
        developer_policy=record.developer_policy,
        examples=record.examples,
        metadata=legacy_metadata_with_status(record, status),
        content_hash=record.content_hash,
        created_by=record.created_by,
        created_at=record.created_at,
    )


def legacy_content_hash(
    *,
    template_name: str,
    graph_profile: str,
    version: str,
    content: str,
    change_log: str,
) -> str:
    payload = {
        "templateName": template_name,
        "graphProfile": graph_profile,
        "version": version,
        "content": content,
        "changeLog": change_log,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{sha256(encoded).hexdigest()}"


def build_prompt_template_upsert(record: PromptTemplateRecord):
    record.validate()
    return (
        insert(PromptTemplate)
        .values(
            id=record.id,
            tenant_id=record.tenant_id,
            name=record.name,
            graph_profile=record.graph_profile,
            description=record.description,
            created_by=record.created_by,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        .on_conflict_do_update(
            constraint="uq_prompt_templates_name",
            set_={
                "graph_profile": record.graph_profile,
                "description": record.description,
                "updated_at": record.updated_at,
            },
        )
    )


def build_prompt_version_upsert(record: PromptVersionRecord):
    record.validate()
    return (
        insert(PromptVersion)
        .values(
            id=record.id,
            template_id=record.template_id,
            tenant_id=record.tenant_id,
            version=record.version,
            system_policy=record.system_policy,
            developer_policy=record.developer_policy,
            examples=record.examples,
            prompt_metadata=record.metadata,
            content_hash=record.content_hash,
            created_by=record.created_by,
            created_at=record.created_at,
        )
        .on_conflict_do_update(
            constraint="uq_prompt_versions_version",
            set_={
                "system_policy": record.system_policy,
                "developer_policy": record.developer_policy,
                "examples": record.examples,
                "metadata": record.metadata,
                "content_hash": record.content_hash,
            },
        )
    )


def build_prompt_release_upsert(record: PromptReleaseRecord):
    record.validate()
    return (
        insert(PromptRelease)
        .values(
            id=record.id,
            tenant_id=record.tenant_id,
            template_id=record.template_id,
            version_id=record.version_id,
            environment=record.environment,
            released_by=record.released_by,
            released_at=record.released_at,
            release_metadata=record.metadata,
        )
        .on_conflict_do_update(
            constraint="uq_prompt_releases_environment",
            set_={
                "version_id": record.version_id,
                "released_by": record.released_by,
                "released_at": record.released_at,
                "metadata": record.metadata,
            },
        )
    )


def build_released_prompt_find(*, tenant_id: str, template_name: str, environment: str):
    for field_name, value in (
        ("tenant_id", tenant_id),
        ("template_name", template_name),
        ("environment", environment),
    ):
        if not value.strip():
            raise ValueError(f"{field_name} is required")
    return (
        select(PromptTemplate, PromptVersion, PromptRelease)
        .join(PromptRelease, PromptRelease.template_id == PromptTemplate.id)
        .join(PromptVersion, PromptVersion.id == PromptRelease.version_id)
        .where(
            PromptTemplate.tenant_id == tenant_id,
            PromptTemplate.name == template_name,
            PromptRelease.environment == environment,
        )
    )
