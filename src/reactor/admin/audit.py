from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from reactor.kernel.ids import new_id


class AdminAuditAction(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    READ = "READ"
    UPSERT = "UPSERT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ACTIVATE = "ACTIVATE"
    SUSPEND = "SUSPEND"
    CONNECT = "CONNECT"
    DISCONNECT = "DISCONNECT"
    ADD = "ADD"
    REMOVE = "REMOVE"
    UPDATE_ROLE = "UPDATE_ROLE"
    ROLE_UPDATE = "ROLE_UPDATE"
    RULE_CREATE = "RULE_CREATE"
    RULE_UPDATE = "RULE_UPDATE"
    RULE_DELETE = "RULE_DELETE"
    RULE_UPSERT = "RULE_UPSERT"
    UPDATE_SETTINGS = "UPDATE_SETTINGS"
    SIMULATE = "SIMULATE"
    STAGE_CONFIG_UPDATE = "STAGE_CONFIG_UPDATE"
    PIPELINE_REORDER = "PIPELINE_REORDER"
    REVIEW_UPDATE = "REVIEW_UPDATE"
    REVIEW_BULK_UPDATE = "REVIEW_BULK_UPDATE"
    INVALIDATE_ALL = "INVALIDATE_ALL"
    INVALIDATE_KEY = "INVALIDATE_KEY"
    INVALIDATE_PATTERN = "INVALIDATE_PATTERN"
    ALERT_RESOLVE = "ALERT_RESOLVE"
    ALERT_EVALUATE = "ALERT_EVALUATE"
    EXPORT = "EXPORT"
    LIST_SOURCES = "LIST_SOURCES"
    GET_SOURCE = "GET_SOURCE"
    CREATE_SOURCE = "CREATE_SOURCE"
    UPDATE_SOURCE = "UPDATE_SOURCE"
    SYNC_SOURCE = "SYNC_SOURCE"
    LIST_REVISIONS = "LIST_REVISIONS"
    GET_DIFF = "GET_DIFF"
    PUBLISH_REVISION = "PUBLISH_REVISION"


@dataclass(frozen=True)
class AdminAuditLog:
    category: str
    action: AdminAuditAction
    actor: str
    id: str = field(default_factory=lambda: new_id("admin_audit"))
    resource_type: str | None = None
    resource_id: str | None = None
    detail: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
