from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class SubmitFeedbackRequest(CamelModel):
    rating: str = Field(min_length=1)
    query: str | None = Field(default=None, max_length=10000)
    response: str | None = Field(default=None, max_length=50000)
    comment: str | None = Field(default=None, max_length=5000)
    sessionId: str | None = Field(default=None, max_length=120)
    runId: str | None = Field(default=None, max_length=120)
    intent: str | None = Field(default=None, max_length=120)
    domain: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    promptVersion: int | None = None
    toolsUsed: list[str] | None = Field(default=None, max_length=50)
    durationMs: int | None = Field(default=None, ge=0)
    source: str | None = Field(default=None, max_length=120)
    tags: list[str] | None = Field(default=None, max_length=20)
    templateId: str | None = Field(default=None, max_length=120)


class ReviewUpdateRequest(CamelModel):
    status: str | None = Field(default=None, max_length=32)
    tags: list[str] | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=5000)


class BulkFeedbackReviewUpdateRequest(CamelModel):
    ids: list[str] = Field(min_length=1, max_length=100)
    status: str | None = Field(default=None, max_length=32)
    tags: list[str] | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=5000)


class FeedbackReviewHandoffDetail(CamelModel):
    feedbackId: str = Field(min_length=1)
    evalCaseId: str | None = Field(default=None, min_length=1)
    sourceRunId: str | None = Field(default=None, min_length=1)
    feedbackSource: str | None = Field(default=None, min_length=1)
    reviewTags: list[str] | None = Field(default=None, min_length=1)
    reviewNote: str | None = Field(default=None, min_length=1)
    nextAction: str | None = Field(default=None, min_length=1)
    bulkReviewAction: str | None = Field(default=None, min_length=1)
    readinessReportArg: str | None = Field(default=None, min_length=1)
    requiredReadinessReports: list[str] | None = Field(default=None, min_length=1)
    readinessReports: dict[str, str] | None = Field(default=None, min_length=1)
    requiredEnvAnyOf: list[list[str]] | None = Field(default=None, min_length=1)
    missingEnvAnyOf: list[str] | None = Field(default=None, min_length=1)
    recommendedEnv: list[str] | None = Field(default=None, min_length=1)
    releaseReadinessCommand: str | None = Field(default=None, min_length=1)


class BulkFeedbackReviewFailure(CamelModel):
    id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evalCaseId: str | None = Field(default=None, min_length=1)
    sourceRunId: str | None = Field(default=None, min_length=1)
    feedbackSource: str | None = Field(default=None, min_length=1)
    requiredReviewNote: str | None = Field(default=None, min_length=1)
    nextAction: str | None = Field(default=None, min_length=1)
    bulkReviewAction: str | None = Field(default=None, min_length=1)
    readinessReportArg: str | None = Field(default=None, min_length=1)
    requiredReadinessReports: list[str] | None = Field(default=None, min_length=1)
    readinessReports: dict[str, str] | None = Field(default=None, min_length=1)
    requiredEnvAnyOf: list[list[str]] | None = Field(default=None, min_length=1)
    missingEnvAnyOf: list[str] | None = Field(default=None, min_length=1)
    recommendedEnv: list[str] | None = Field(default=None, min_length=1)
    releaseReadinessCommand: str | None = Field(default=None, min_length=1)
    readyNextActionIds: list[str] | None = None
    blockedNextActionIds: list[str] | None = None
    nextActionStates: dict[str, str] | None = None
    nextActions: list[FeedbackNextAction] | None = None


class BulkFeedbackReviewUpdateResponse(CamelModel):
    updated: list[str]
    failed: list[BulkFeedbackReviewFailure]
    updatedDetails: list[FeedbackReviewHandoffDetail] | None = None
    alreadyDone: list[str] | None = None
    alreadyDoneDetails: list[FeedbackReviewHandoffDetail] | None = None


class FeedbackNextAction(CamelModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    command: str = Field(min_length=1)
    feedbackId: str | None = Field(default=None, min_length=1)
    evalCaseId: str | None = Field(default=None, min_length=1)
    sourceRunId: str | None = Field(default=None, min_length=1)
    candidateTag: str | None = Field(default=None, min_length=1)
    subjectUserId: str | None = Field(default=None, min_length=1)
    reportFile: str | None = Field(default=None, min_length=1)
    caseFile: str | None = Field(default=None, min_length=1)
    runFile: str | None = Field(default=None, min_length=1)
    suiteFile: str | None = Field(default=None, min_length=1)
    datasetName: str | None = Field(default=None, min_length=1)
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
    dependsOnActionIds: list[str] | None = Field(default=None, min_length=1)
    missingEnvAnyOf: list[str] | None = Field(default=None, min_length=1)
    recommendedEnv: list[str] | None = Field(default=None, min_length=1)
    recommendedVersionBump: str | None = Field(default=None, min_length=1)
    recommendedTagPattern: str | None = Field(default=None, min_length=1)
    latestTagCommand: str | None = Field(default=None, min_length=1)
    recommendedTagSource: str | None = Field(default=None, min_length=1)
    minorBoundaryReports: list[str] | None = Field(default=None, min_length=1)
    feedbackTags: list[str] | None = Field(default=None, min_length=1)
    feedbackSource: str | None = Field(default=None, min_length=1)
    workflowTags: list[str] | None = Field(default=None, min_length=1)
    expectedAnswers: list[str] | None = Field(default=None, min_length=1)
    requiredReviewNote: str | None = Field(default=None, min_length=1)


class FeedbackResponse(CamelModel):
    feedbackId: str
    query: str
    response: str
    rating: str
    source: str
    timestamp: str
    comment: str | None
    sessionId: str | None
    runId: str | None
    userId: str | None
    intent: str | None
    domain: str | None
    model: str | None
    promptVersion: int | None
    toolsUsed: list[str] | None
    durationMs: int | None
    tags: list[str] | None
    templateId: str | None
    reviewStatus: str
    reviewTags: list[str]
    reviewedBy: str | None
    reviewedAt: str | None
    reviewNote: str | None
    version: int
    updatedAt: str
    readyNextActionIds: list[str] | None = None
    blockedNextActionIds: list[str] | None = None
    nextActionStates: dict[str, str] | None = None
    nextActions: list[FeedbackNextAction] | None = None


class FeedbackPageResponse(CamelModel):
    items: list[FeedbackResponse]
    nextCursor: str | None = None
    prevCursor: str | None = None
    approximateTotal: int


class FeedbackExportWorkflow(CamelModel):
    type: str = Field(min_length=1)
    candidateId: str = Field(min_length=1)
    collection: str = Field(min_length=1)
    sourceUri: str = Field(min_length=1)
    evalCaseId: str = Field(min_length=1)
    runId: str | None = Field(min_length=1)
    sourceRunId: str | None = Field(min_length=1)
    feedbackSource: str = Field(min_length=1)
    feedbackTag: str = Field(min_length=1)


class FeedbackExportItem(CamelModel):
    feedbackId: str
    query: str
    response: str
    rating: str
    source: str
    timestamp: str
    comment: str | None
    runId: str | None
    sessionId: str | None
    userId: str | None
    intent: str | None
    domain: str | None
    model: str | None
    promptVersion: int | None
    toolsUsed: list[str] | None
    durationMs: int | None
    tags: list[str] | None
    templateId: str | None
    reviewStatus: str
    reviewTags: list[str]
    reviewedBy: str | None
    reviewedAt: str | None
    reviewNote: str | None
    version: int
    updatedAt: str
    workflow: FeedbackExportWorkflow | None = None
    nextActions: list[FeedbackNextAction]


class FeedbackExportResponse(CamelModel):
    version: int
    source: str
    items: list[FeedbackExportItem]
