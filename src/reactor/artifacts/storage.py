from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import PurePosixPath

from reactor.kernel.ids import new_id

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MEDIA_TYPE_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9!#$&^_.+-]{0,126}/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}$"
)


@dataclass(frozen=True)
class ArtifactAcl:
    visibility: str
    users: frozenset[str] = field(default_factory=lambda: frozenset[str]())
    groups: frozenset[str] = field(default_factory=lambda: frozenset[str]())

    def validate(self) -> None:
        if self.visibility not in {"tenant", "private"}:
            raise ValueError("artifact visibility must be tenant or private")
        if self.visibility == "private" and not self.users and not self.groups:
            raise ValueError("private artifacts require at least one ACL")
        if any(not value.strip() for value in self.users | self.groups):
            raise ValueError("artifact ACL entries must be non-empty")


@dataclass(frozen=True)
class ArtifactSource:
    run_id: str | None = None
    thread_id: str | None = None
    tool_call_id: str | None = None
    source_uri: str | None = None


@dataclass(frozen=True)
class ArtifactBlobRef:
    storage: str
    key: str

    def validate(self) -> None:
        if self.storage not in {"s3", "local"}:
            raise ValueError("artifact blob storage must be s3 or local")
        if (
            not self.key.strip()
            or self.key.startswith("/")
            or ".." in PurePosixPath(self.key).parts
        ):
            raise ValueError("artifact blob key must be relative and normalized")


@dataclass(frozen=True)
class ArtifactReference:
    artifact_id: str
    tenant_id: str
    owner_user_id: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    blob: ArtifactBlobRef
    acl: ArtifactAcl
    source: ArtifactSource
    created_at: datetime
    expires_at: datetime | None = None
    encryption_policy: str = "managed"
    tombstoned: bool = False

    def to_graph_state(self) -> dict[str, object]:
        state: dict[str, object] = {
            "artifactId": self.artifact_id,
            "filename": self.filename,
            "mimeType": self.mime_type,
            "sizeBytes": self.size_bytes,
            "sha256": self.sha256,
        }
        if self.source.run_id is not None:
            state["sourceRunId"] = self.source.run_id
        return state


@dataclass(frozen=True)
class ArtifactDownloadPrincipal:
    tenant_id: str
    user_id: str
    groups: frozenset[str] = field(default_factory=lambda: frozenset[str]())

    def validate(self) -> None:
        required_text(self.tenant_id, "tenant_id")
        required_text(self.user_id, "user_id")
        if any(not value.strip() for value in self.groups):
            raise ValueError("artifact principal groups must be non-empty")


@dataclass(frozen=True)
class ArtifactDownloadGrant:
    artifact_id: str
    blob: ArtifactBlobRef
    expires_at: datetime
    content_type: str
    response_filename: str


@dataclass(frozen=True)
class ArtifactTombstoneResult:
    reference: ArtifactReference
    delete_blob: bool
    delete_derived_embeddings: bool
    audit_metadata: dict[str, str]


def tombstone_artifact(
    reference: ArtifactReference,
    *,
    actor_id: str,
    reason: str,
    tombstoned_at: datetime,
) -> ArtifactTombstoneResult:
    normalized_actor_id = required_text(actor_id, "actor_id")
    normalized_reason = required_text(reason, "reason")
    if reference.tombstoned:
        raise ValueError("only active artifacts can be tombstoned")
    return ArtifactTombstoneResult(
        reference=replace(reference, tombstoned=True),
        delete_blob=True,
        delete_derived_embeddings=True,
        audit_metadata={
            "artifact_id": reference.artifact_id,
            "tenant_id": reference.tenant_id,
            "actor_id": normalized_actor_id,
            "reason": normalized_reason,
            "tombstoned_at": tombstoned_at.isoformat(),
            "blob_storage": reference.blob.storage,
            "blob_key": reference.blob.key,
        },
    )


def authorize_artifact_download(
    reference: ArtifactReference,
    *,
    principal: ArtifactDownloadPrincipal,
    requested_ttl_seconds: int,
    max_ttl_seconds: int,
    now: datetime,
) -> ArtifactDownloadGrant:
    principal.validate()
    if reference.tombstoned or (reference.expires_at is not None and now >= reference.expires_at):
        raise ValueError("artifact is no longer available")
    if requested_ttl_seconds <= 0:
        raise ValueError("artifact signed URL ttl must be positive")
    if max_ttl_seconds <= 0:
        raise ValueError("artifact signed URL max ttl must be positive")
    if requested_ttl_seconds > max_ttl_seconds:
        raise ValueError("artifact signed URL ttl exceeds policy")
    if not artifact_acl_allows(reference, principal):
        raise ValueError("artifact download denied")
    grant_expires_at = now + timedelta(seconds=requested_ttl_seconds)
    if reference.expires_at is not None and grant_expires_at > reference.expires_at:
        raise ValueError("artifact signed URL ttl exceeds artifact retention")
    return ArtifactDownloadGrant(
        artifact_id=reference.artifact_id,
        blob=reference.blob,
        expires_at=grant_expires_at,
        content_type=reference.mime_type,
        response_filename=reference.filename,
    )


def artifact_acl_allows(
    reference: ArtifactReference,
    principal: ArtifactDownloadPrincipal,
) -> bool:
    if principal.tenant_id.strip() != reference.tenant_id:
        return False
    if reference.acl.visibility == "tenant":
        return True
    if reference.acl.visibility != "private":
        return False
    return principal.user_id.strip() in reference.acl.users or bool(
        principal.groups & reference.acl.groups
    )


def create_artifact_reference(
    *,
    tenant_id: str,
    owner_user_id: str,
    filename: str,
    mime_type: str,
    size_bytes: int,
    sha256: str,
    source: ArtifactSource,
    acl: ArtifactAcl,
    retention_days: int | None,
    created_at: datetime,
    storage: str = "s3",
    artifact_id: str | None = None,
) -> ArtifactReference:
    normalized_tenant_id = required_text(tenant_id, "tenant_id")
    normalized_owner_user_id = required_text(owner_user_id, "owner_user_id")
    normalized_filename = safe_filename(required_text(filename, "filename"))
    normalized_mime_type = required_mime_type(mime_type)
    normalized_sha256 = required_sha256(sha256)
    if size_bytes < 0:
        raise ValueError("artifact size_bytes must be non-negative")
    if retention_days is not None and retention_days <= 0:
        raise ValueError("artifact retention_days must be positive")
    acl.validate()
    resolved_artifact_id = artifact_id or new_id("artifact")
    blob = ArtifactBlobRef(
        storage=storage,
        key=artifact_blob_key(
            tenant_id=normalized_tenant_id,
            artifact_id=resolved_artifact_id,
            filename=normalized_filename,
            sha256=normalized_sha256,
            created_at=created_at,
        ),
    )
    blob.validate()
    return ArtifactReference(
        artifact_id=resolved_artifact_id,
        tenant_id=normalized_tenant_id,
        owner_user_id=normalized_owner_user_id,
        filename=normalized_filename,
        mime_type=normalized_mime_type,
        size_bytes=size_bytes,
        sha256=normalized_sha256,
        blob=blob,
        acl=acl,
        source=source,
        created_at=created_at,
        expires_at=created_at + timedelta(days=retention_days)
        if retention_days is not None
        else None,
    )


def artifact_blob_key(
    *,
    tenant_id: str,
    artifact_id: str,
    filename: str,
    sha256: str,
    created_at: datetime,
) -> str:
    suffix = PurePosixPath(filename).suffix
    return (
        f"tenants/{tenant_id}/artifacts/{created_at:%Y/%m/%d}/{artifact_id}-{sha256[:16]}{suffix}"
    )


def required_text(value: str, label: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{label} is required")
    return stripped


def required_mime_type(value: str) -> str:
    stripped = required_text(value, "mime_type").lower()
    if MEDIA_TYPE_PATTERN.fullmatch(stripped) is None:
        raise ValueError("artifact mime_type must be a canonical media type")
    return stripped


def required_sha256(value: str) -> str:
    stripped = value.strip()
    if SHA256_PATTERN.fullmatch(stripped) is None:
        raise ValueError("artifact sha256 must be 64 lowercase hex characters")
    return stripped


def safe_filename(value: str) -> str:
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("artifact filename is invalid")
    name = PurePosixPath(value.replace("\\", "/")).name.strip()
    if not name or name in {".", ".."}:
        raise ValueError("artifact filename is invalid")
    return name
