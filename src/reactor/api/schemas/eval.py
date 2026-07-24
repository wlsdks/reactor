from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class AgentEvalCaseRequest(CamelModel):
    id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    userInput: str = Field(min_length=1)
    expectedAnswerContains: tuple[str, ...] = ()
    forbiddenAnswerContains: tuple[str, ...] = ()
    expectedToolNames: tuple[str, ...] = ()
    forbiddenToolNames: tuple[str, ...] = ()
    expectedExposedToolNames: tuple[str, ...] = ()
    forbiddenExposedToolNames: tuple[str, ...] = ()
    maxToolExposureCount: int | None = Field(default=None, ge=0)
    agentType: str | None = None
    model: str | None = None
    enabled: bool = True
    tags: tuple[str, ...] = ()
    minScore: float = Field(default=1.0, ge=0, le=1)
    sourceRunId: str | None = None


class EvaluateRunRequest(CamelModel):
    runId: str = Field(min_length=1, max_length=128)
    finalAnswer: str = ""
    toolNames: tuple[str, ...] = ()
    exposedToolNames: tuple[str, ...] = ()
    agentType: str | None = None
    model: str | None = None


class PromoteEvalCaseRequest(CamelModel):
    runId: str = Field(min_length=1, max_length=128)
    id: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=255)
    expectedAnswerContains: tuple[str, ...] = ()
    forbiddenAnswerContains: tuple[str, ...] = ()
    expectedToolNames: tuple[str, ...] = ()
    forbiddenToolNames: tuple[str, ...] = ()
    expectedExposedToolNames: tuple[str, ...] = ()
    forbiddenExposedToolNames: tuple[str, ...] = ()
    maxToolExposureCount: int | None = Field(default=None, ge=0)
    tags: tuple[str, ...] = ()
    minScore: float = Field(default=1.0, ge=0, le=1)
    enabled: bool = True


class LangSmithEvalSyncRequest(CamelModel):
    datasetName: str = Field(min_length=1, max_length=255)
    caseIds: tuple[str, ...] = Field(default=(), max_length=100)
    description: str | None = Field(default=None, max_length=1000)


class LangSmithEvalSyncResponse(CamelModel):
    ok: bool
    status: str
    scope: str
    mode: str
    datasetName: str
    created: bool
    examples: int
    exampleIds: tuple[str, ...]
    caseIds: tuple[str, ...]
    metadataCaseIds: tuple[str, ...]
    sourceRunIds: tuple[str, ...]
    caseSourceRunIds: dict[str, str]
    splitCounts: dict[str, int]
    secretFree: bool
    exampleContract: dict[str, Any]
    sdkContract: dict[str, Any]


class AgentEvalNextAction(CamelModel):
    id: str
    label: str
    command: str


class AgentEvalCaseResponse(CamelModel):
    id: str
    name: str
    userInput: str
    expectedAnswerContains: tuple[str, ...]
    forbiddenAnswerContains: tuple[str, ...]
    expectedToolNames: tuple[str, ...]
    forbiddenToolNames: tuple[str, ...]
    expectedExposedToolNames: tuple[str, ...]
    forbiddenExposedToolNames: tuple[str, ...]
    maxToolExposureCount: int | None
    agentType: str | None
    model: str | None
    enabled: bool
    tags: tuple[str, ...]
    minScore: float
    sourceRunId: str | None
    assertionCount: int
    createdAt: str
    updatedAt: str
    nextActions: tuple[AgentEvalNextAction, ...] = ()


class AgentEvalResultResponse(CamelModel):
    id: str | None = None
    caseId: str
    runId: str | None
    tier: str
    passed: bool
    score: float
    reasons: tuple[str, ...]
    evaluatedAt: str


class AgentEvalRunLogResponse(CamelModel):
    runId: str
    evalCaseId: str | None
    agentType: str
    model: str
    toolExposureCount: int
    toolExposureNames: tuple[str, ...]
    toolCallCount: int
    retrievedChunkCount: int
    errorCount: int
    finalAnswerPreview: str


class ReplayEvalCaseResponse(CamelModel):
    case: AgentEvalCaseResponse
    deterministic: AgentEvalResultResponse
    storedResults: tuple[AgentEvalResultResponse, ...]
