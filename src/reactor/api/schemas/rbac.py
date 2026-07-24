from __future__ import annotations

from pydantic import BaseModel, Field


class RoleDefinitionResponse(BaseModel):
    role: str
    scope: str | None
    permissions: list[str]


class UpdateRoleRequest(BaseModel):
    role: str


class UpdateRoleResponse(BaseModel):
    user_id: str = Field(alias="userId")
    role: str
