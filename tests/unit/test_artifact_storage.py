from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from reactor.artifacts.storage import (
    ArtifactAcl,
    ArtifactBlobRef,
    ArtifactDownloadPrincipal,
    ArtifactSource,
    authorize_artifact_download,
    create_artifact_reference,
    tombstone_artifact,
)


def test_create_artifact_reference_preserves_metadata_without_blob_body() -> None:
    reference = create_artifact_reference(
        tenant_id="tenant_1",
        owner_user_id="user_1",
        filename="report.csv",
        mime_type="text/csv",
        size_bytes=1024,
        sha256="a" * 64,
        source=ArtifactSource(run_id="run_1", thread_id="thread_1", tool_call_id="tool_1"),
        acl=ArtifactAcl(visibility="private", users=frozenset({"user_1"})),
        retention_days=30,
        created_at=datetime(2026, 6, 28, tzinfo=UTC),
    )

    assert reference.artifact_id.startswith("artifact_")
    assert reference.tenant_id == "tenant_1"
    assert reference.owner_user_id == "user_1"
    assert reference.filename == "report.csv"
    assert reference.mime_type == "text/csv"
    assert reference.size_bytes == 1024
    assert reference.sha256 == "a" * 64
    assert reference.blob == ArtifactBlobRef(
        storage="s3",
        key=(f"tenants/tenant_1/artifacts/2026/06/28/{reference.artifact_id}-aaaaaaaaaaaaaaaa.csv"),
    )
    assert reference.expires_at == datetime(2026, 7, 28, tzinfo=UTC)
    assert reference.to_graph_state() == {
        "artifactId": reference.artifact_id,
        "filename": "report.csv",
        "mimeType": "text/csv",
        "sizeBytes": 1024,
        "sha256": "a" * 64,
        "sourceRunId": "run_1",
    }


def test_create_artifact_reference_rejects_untrusted_metadata() -> None:
    with pytest.raises(ValueError, match="artifact sha256 must be 64 lowercase hex characters"):
        create_artifact_reference(
            tenant_id="tenant_1",
            owner_user_id="user_1",
            filename="report.csv",
            mime_type="text/csv",
            size_bytes=1024,
            sha256="not-a-sha",
            source=ArtifactSource(run_id="run_1"),
            acl=ArtifactAcl(visibility="private", users=frozenset({"user_1"})),
            retention_days=30,
            created_at=datetime(2026, 6, 28, tzinfo=UTC),
        )

    with pytest.raises(ValueError, match="private artifacts require at least one ACL"):
        create_artifact_reference(
            tenant_id="tenant_1",
            owner_user_id="user_1",
            filename="report.csv",
            mime_type="text/csv",
            size_bytes=1024,
            sha256="b" * 64,
            source=ArtifactSource(run_id="run_1"),
            acl=ArtifactAcl(visibility="private"),
            retention_days=30,
            created_at=datetime(2026, 6, 28, tzinfo=UTC),
        )


def test_create_artifact_reference_rejects_non_canonical_mime_type() -> None:
    for mime_type in ("text/html; charset=utf-8", "text /csv", "application/"):
        with pytest.raises(ValueError, match="artifact mime_type must be a canonical media type"):
            create_artifact_reference(
                tenant_id="tenant_1",
                owner_user_id="user_1",
                filename="report.csv",
                mime_type=mime_type,
                size_bytes=1024,
                sha256="c" * 64,
                source=ArtifactSource(run_id="run_1"),
                acl=ArtifactAcl(visibility="tenant"),
                retention_days=30,
                created_at=datetime(2026, 6, 28, tzinfo=UTC),
            )


def test_create_artifact_reference_rejects_control_character_filename() -> None:
    with pytest.raises(ValueError, match="artifact filename is invalid"):
        create_artifact_reference(
            tenant_id="tenant_1",
            owner_user_id="user_1",
            filename='report.csv"\r\nX-Injected: yes',
            mime_type="text/csv",
            size_bytes=1024,
            sha256="d" * 64,
            source=ArtifactSource(run_id="run_1"),
            acl=ArtifactAcl(visibility="tenant"),
            retention_days=30,
            created_at=datetime(2026, 6, 28, tzinfo=UTC),
        )


def test_authorize_artifact_download_enforces_acl_expiry_tombstone_and_ttl() -> None:
    now = datetime(2026, 6, 28, 12, tzinfo=UTC)
    reference = create_artifact_reference(
        tenant_id="tenant_1",
        owner_user_id="user_1",
        filename="report.csv",
        mime_type="text/csv",
        size_bytes=1024,
        sha256="d" * 64,
        source=ArtifactSource(run_id="run_1"),
        acl=ArtifactAcl(visibility="private", groups=frozenset({"finance"})),
        retention_days=1,
        created_at=datetime(2026, 6, 28, tzinfo=UTC),
        artifact_id="artifact_report",
    )

    grant = authorize_artifact_download(
        reference,
        principal=ArtifactDownloadPrincipal(
            tenant_id="tenant_1",
            user_id="user_2",
            groups=frozenset({"finance"}),
        ),
        requested_ttl_seconds=900,
        max_ttl_seconds=3600,
        now=now,
    )

    assert grant.artifact_id == "artifact_report"
    assert grant.blob == reference.blob
    assert grant.expires_at == datetime(2026, 6, 28, 12, 15, tzinfo=UTC)
    assert grant.content_type == "text/csv"
    assert grant.response_filename == "report.csv"

    with pytest.raises(ValueError, match="artifact download denied"):
        authorize_artifact_download(
            reference,
            principal=ArtifactDownloadPrincipal(tenant_id="tenant_2", user_id="user_2"),
            requested_ttl_seconds=900,
            max_ttl_seconds=3600,
            now=now,
        )

    with pytest.raises(ValueError, match="artifact download denied"):
        authorize_artifact_download(
            reference,
            principal=ArtifactDownloadPrincipal(tenant_id="tenant_1", user_id="user_3"),
            requested_ttl_seconds=900,
            max_ttl_seconds=3600,
            now=now,
        )

    with pytest.raises(ValueError, match="artifact signed URL ttl exceeds policy"):
        authorize_artifact_download(
            reference,
            principal=ArtifactDownloadPrincipal(
                tenant_id="tenant_1",
                user_id="user_2",
                groups=frozenset({"finance"}),
            ),
            requested_ttl_seconds=7200,
            max_ttl_seconds=3600,
            now=now,
        )

    with pytest.raises(ValueError, match="artifact signed URL ttl exceeds artifact retention"):
        authorize_artifact_download(
            reference,
            principal=ArtifactDownloadPrincipal(
                tenant_id="tenant_1",
                user_id="user_2",
                groups=frozenset({"finance"}),
            ),
            requested_ttl_seconds=900,
            max_ttl_seconds=3600,
            now=datetime(2026, 6, 28, 23, 50, tzinfo=UTC),
        )

    with pytest.raises(ValueError, match="artifact is no longer available"):
        authorize_artifact_download(
            reference,
            principal=ArtifactDownloadPrincipal(
                tenant_id="tenant_1",
                user_id="user_2",
                groups=frozenset({"finance"}),
            ),
            requested_ttl_seconds=900,
            max_ttl_seconds=3600,
            now=datetime(2026, 6, 29, tzinfo=UTC),
        )

    with pytest.raises(ValueError, match="artifact is no longer available"):
        authorize_artifact_download(
            replace(reference, tombstoned=True),
            principal=ArtifactDownloadPrincipal(
                tenant_id="tenant_1",
                user_id="user_2",
                groups=frozenset({"finance"}),
            ),
            requested_ttl_seconds=900,
            max_ttl_seconds=3600,
            now=now,
        )


def test_tombstone_artifact_records_audit_and_deletes_derived_embeddings() -> None:
    reference = create_artifact_reference(
        tenant_id="tenant_1",
        owner_user_id="user_1",
        filename="report.csv",
        mime_type="text/csv",
        size_bytes=1024,
        sha256="e" * 64,
        source=ArtifactSource(run_id="run_1"),
        acl=ArtifactAcl(visibility="tenant"),
        retention_days=30,
        created_at=datetime(2026, 6, 28, tzinfo=UTC),
        artifact_id="artifact_report",
    )
    tombstoned_at = datetime(2026, 6, 29, tzinfo=UTC)

    result = tombstone_artifact(
        reference,
        actor_id="admin_1",
        reason="tenant retention expired",
        tombstoned_at=tombstoned_at,
    )

    assert result.reference == replace(reference, tombstoned=True)
    assert result.delete_blob is True
    assert result.delete_derived_embeddings is True
    assert result.audit_metadata == {
        "artifact_id": "artifact_report",
        "tenant_id": "tenant_1",
        "actor_id": "admin_1",
        "reason": "tenant retention expired",
        "tombstoned_at": "2026-06-29T00:00:00+00:00",
        "blob_storage": "s3",
        "blob_key": reference.blob.key,
    }

    with pytest.raises(ValueError, match="only active artifacts can be tombstoned"):
        tombstone_artifact(
            replace(reference, tombstoned=True),
            actor_id="admin_1",
            reason="tenant retention expired",
            tombstoned_at=tombstoned_at,
        )

    with pytest.raises(ValueError, match="actor_id is required"):
        tombstone_artifact(
            reference,
            actor_id=" ",
            reason="tenant retention expired",
            tombstoned_at=tombstoned_at,
        )

    with pytest.raises(ValueError, match="reason is required"):
        tombstone_artifact(
            reference,
            actor_id="admin_1",
            reason=" ",
            tombstoned_at=tombstoned_at,
        )
