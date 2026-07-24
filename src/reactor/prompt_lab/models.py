from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


class PromptLabExperimentStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class EvaluationTier(StrEnum):
    STRUCTURAL = "STRUCTURAL"
    RULES = "RULES"
    LLM_JUDGE = "LLM_JUDGE"


class RecommendationConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


def empty_str_list() -> list[str]:
    return []


def empty_test_query_list() -> list[TestQuery]:
    return []


def empty_prompt_weakness_list() -> list[PromptWeakness]:
    return []


def empty_evaluation_result_list() -> list[EvaluationResult]:
    return []


@dataclass(frozen=True)
class TestQuery:
    query: str
    intent: str | None = None
    domain: str | None = None
    expected_behavior: str | None = None
    tags: list[str] = field(default_factory=empty_str_list)

    def validate(self) -> None:
        if not self.query.strip():
            raise ValueError("query is required")


@dataclass(frozen=True)
class EvaluationConfig:
    structural_enabled: bool = True
    rules_enabled: bool = True
    llm_judge_enabled: bool = True
    llm_judge_budget_tokens: int = 100_000
    custom_rubric: str | None = None

    def validate(self) -> None:
        if self.llm_judge_budget_tokens < 0:
            raise ValueError("llm_judge_budget_tokens must be non-negative")


@dataclass(frozen=True)
class PromptLabExperimentRecord:
    id: str = field(default_factory=lambda: f"prompt_lab_exp_{uuid4().hex}")
    tenant_id: str = "local"
    name: str = ""
    description: str = ""
    template_id: str = ""
    baseline_version_id: str = ""
    candidate_version_ids: list[str] = field(default_factory=empty_str_list)
    test_queries: list[TestQuery] = field(default_factory=empty_test_query_list)
    evaluation_config: EvaluationConfig = field(default_factory=EvaluationConfig)
    model: str | None = None
    judge_model: str | None = None
    temperature: float = 0.3
    repetitions: int = 1
    auto_generated: bool = False
    status: PromptLabExperimentStatus = PromptLabExperimentStatus.PENDING
    created_by: str = "system"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None

    def validate(self) -> None:
        for field_name, value in (
            ("id", self.id),
            ("tenant_id", self.tenant_id),
            ("name", self.name),
            ("template_id", self.template_id),
            ("baseline_version_id", self.baseline_version_id),
            ("created_by", self.created_by),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} is required")
        if not self.candidate_version_ids:
            raise ValueError("candidate_version_ids must not be empty")
        if not self.test_queries:
            raise ValueError("test_queries must not be empty")
        if self.repetitions < 1:
            raise ValueError("repetitions must be positive")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        self.evaluation_config.validate()
        for query in self.test_queries:
            query.validate()


@dataclass(frozen=True)
class PromptWeakness:
    category: str
    description: str
    frequency: int
    example_queries: list[str] = field(default_factory=empty_str_list)


@dataclass(frozen=True)
class FeedbackAnalysis:
    total_feedback: int
    negative_count: int
    weaknesses: list[PromptWeakness] = field(default_factory=empty_prompt_weakness_list)
    sample_queries: list[TestQuery] = field(default_factory=empty_test_query_list)
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class EvaluationResult:
    tier: EvaluationTier
    passed: bool
    score: float
    reason: str
    evaluator_name: str | None = None


@dataclass(frozen=True)
class TokenUsageSummary:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class PromptLabTrialRecord:
    id: str = field(default_factory=lambda: f"prompt_lab_trial_{uuid4().hex}")
    tenant_id: str = "local"
    experiment_id: str = ""
    prompt_version_id: str = ""
    prompt_version_number: int = 0
    test_query: TestQuery = field(default_factory=lambda: TestQuery(query=""))
    repetition_index: int = 0
    response: str | None = None
    success: bool = False
    error_message: str | None = None
    tools_used: list[str] = field(default_factory=empty_str_list)
    token_usage: TokenUsageSummary | None = None
    duration_ms: int = 0
    evaluations: list[EvaluationResult] = field(default_factory=empty_evaluation_result_list)
    executed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class VersionSummary:
    version_id: str
    version_number: int
    is_baseline: bool
    total_trials: int
    pass_count: int
    pass_rate: float
    avg_score: float
    avg_duration_ms: float
    total_tokens: int
    tier_breakdown: dict[str, dict[str, float | int]]
    tool_usage_frequency: dict[str, int]
    error_rate: float


@dataclass(frozen=True)
class Recommendation:
    best_version_id: str
    best_version_number: int
    confidence: RecommendationConfidence
    reasoning: str
    improvements: list[str] = field(default_factory=empty_str_list)
    warnings: list[str] = field(default_factory=empty_str_list)


@dataclass(frozen=True)
class PromptLabReportRecord:
    experiment_id: str
    tenant_id: str
    experiment_name: str
    total_trials: int
    version_summaries: list[VersionSummary]
    recommendation: Recommendation
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def sanitize_prompt_lab_error(value: str | None, *, max_length: int = 200) -> str | None:
    if value is None or not value.strip():
        return None
    first_line = next((line.strip() for line in value.splitlines() if line.strip()), "")
    if not first_line:
        return None
    if len(first_line) <= max_length:
        return first_line
    return f"{first_line[:max_length]}..."
