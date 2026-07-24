from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from reactor.persistence.prompt_store import (
    PromptReleaseRecord,
    PromptTemplateRecord,
    PromptVersionRecord,
    build_prompt_release_upsert,
    build_prompt_template_upsert,
    build_prompt_version_upsert,
    build_released_prompt_find,
)

FIXED_TIME = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)


def test_prompt_template_upsert_is_tenant_and_name_scoped() -> None:
    statement = build_prompt_template_upsert(
        PromptTemplateRecord(
            id="prompt_template_1",
            tenant_id="tenant_1",
            name="support",
            graph_profile="rag",
            description="Support prompt",
            created_by="admin_1",
            created_at=FIXED_TIME,
            updated_at=FIXED_TIME,
        )
    )

    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "prompt_templates" in sql
    assert "ON CONFLICT ON CONSTRAINT uq_prompt_templates_name" in sql


def test_prompt_version_upsert_preserves_release_hash_contract() -> None:
    record = PromptVersionRecord(
        id="prompt_version_1",
        template_id="prompt_template_1",
        tenant_id="tenant_1",
        version="v1",
        system_policy="Follow policy.",
        developer_policy="Use safe tools.",
        examples=["hello"],
        metadata={"owner": "platform"},
        content_hash="sha256:abc",
        created_by="admin_1",
        created_at=FIXED_TIME,
    )

    statement = build_prompt_version_upsert(record)
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "prompt_versions" in sql
    assert "ON CONFLICT ON CONSTRAINT uq_prompt_versions_version" in sql
    assert statement.compile(dialect=postgresql.dialect()).params["content_hash"] == "sha256:abc"


def test_prompt_release_upsert_is_environment_scoped() -> None:
    statement = build_prompt_release_upsert(
        PromptReleaseRecord(
            id="prompt_release_1",
            tenant_id="tenant_1",
            template_id="prompt_template_1",
            version_id="prompt_version_1",
            environment="production",
            released_by="admin_1",
            released_at=FIXED_TIME,
            metadata={"ticket": "CUT-1"},
        )
    )

    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "prompt_releases" in sql
    assert "ON CONFLICT ON CONSTRAINT uq_prompt_releases_environment" in sql


def test_released_prompt_find_filters_tenant_template_and_environment() -> None:
    statement = build_released_prompt_find(
        tenant_id="tenant_1",
        template_name="support",
        environment="production",
    )
    compiled = statement.compile(dialect=postgresql.dialect())

    assert "prompt_templates" in str(compiled)
    assert "prompt_versions" in str(compiled)
    assert "prompt_releases" in str(compiled)
    assert "tenant_1" in compiled.params.values()
    assert "support" in compiled.params.values()
    assert "production" in compiled.params.values()
