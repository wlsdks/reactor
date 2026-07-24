from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class RagIngestionCandidateNextAction(CamelModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    command: str = Field(min_length=1)
    evalCaseId: str | None = Field(default=None, min_length=1)
    sourceRunId: str | None = Field(default=None, min_length=1)
    candidateTag: str | None = Field(default=None, min_length=1)
    workflowTags: list[str] | None = None
    reportFile: str | None = Field(default=None, min_length=1)
    caseFile: str | None = Field(default=None, min_length=1)
    runFile: str | None = Field(default=None, min_length=1)
    suiteFile: str | None = Field(default=None, min_length=1)
    datasetName: str | None = Field(default=None, min_length=1)
    feedbackRating: str | None = Field(default=None, min_length=1)
    feedbackSource: str | None = Field(default=None, min_length=1)
    feedbackTags: list[str] | None = None
    preflightFile: str | None = Field(default=None, min_length=1)
    preflightEnvTemplate: str | None = Field(default=None, min_length=1)
    replatformReadinessFile: str | None = Field(default=None, min_length=1)
    smokePlanFile: str | None = Field(default=None, min_length=1)
    releaseEvidenceFile: str | None = Field(default=None, min_length=1)
    releaseReadinessFile: str | None = Field(default=None, min_length=1)
    releaseReadinessCommand: str | None = Field(default=None, min_length=1)
    remediationCommand: str | None = Field(default=None, min_length=1)
    envFileCommand: str | None = Field(default=None, min_length=1)
    readinessReportArg: str | None = Field(default=None, min_length=1)
    requiredReadinessReports: list[str] | None = Field(default=None, min_length=1)
    readinessReports: dict[str, str] | None = Field(default=None, min_length=1)
    requiredEnvAnyOf: list[list[str]] | None = Field(default=None, min_length=1)
    missingEnvAnyOf: list[str] | None = Field(default=None, min_length=1)
    recommendedEnv: list[str] | None = Field(default=None, min_length=1)
    recommendedVersionBump: str | None = Field(default=None, min_length=1)
    recommendedTagPattern: str | None = Field(default=None, min_length=1)
    latestTagCommand: str | None = Field(default=None, min_length=1)
    recommendedTagSource: str | None = Field(default=None, min_length=1)
    minorBoundaryReports: list[str] | None = Field(default=None, min_length=1)
    dependsOnActionIds: list[str] | None = Field(default=None, min_length=1)


def empty_next_actions() -> list[RagIngestionCandidateNextAction]:
    return []


class RagIngestionCandidateResponse(CamelModel):
    id: str
    runId: str
    channel: str | None
    query: str
    response: str
    status: str
    capturedAt: int
    reviewedAt: int | None
    reviewedBy: str | None
    reviewComment: str | None
    ingestedDocumentId: str | None
    nextAction: str | None = None
    readyNextActionIds: list[str] = Field(default_factory=list)
    blockedNextActionIds: list[str] = Field(default_factory=list)
    nextActionStates: dict[str, str] = Field(default_factory=dict)
    nextActions: list[RagIngestionCandidateNextAction] = Field(default_factory=empty_next_actions)


class ReviewRagIngestionCandidateRequest(CamelModel):
    comment: str | None = Field(default=None, max_length=500)
