from __future__ import annotations

from reactor.response.boundary import (
    OutputBoundaryEnforcer,
    OutputBoundarySettings,
    OutputBoundaryViolation,
    OutputBoundaryViolationRecorder,
    OutputMinViolationMode,
)


async def test_output_boundary_truncates_over_max_and_records_violation() -> None:
    recorder = RecordingBoundaryViolationRecorder()
    enforcer = OutputBoundaryEnforcer(
        settings=OutputBoundarySettings(output_max_chars=5),
        violation_recorder=recorder,
    )

    result = await enforcer.enforce("1234567", metadata={"run_id": "run_1"})

    assert result == "12345\n\n[Response truncated]"
    assert recorder.violations == [
        OutputBoundaryViolation(
            violation_type="output_too_long",
            policy="truncate",
            limit=5,
            actual=7,
            metadata={"run_id": "run_1"},
        )
    ]


async def test_output_boundary_fail_mode_returns_none_for_short_output() -> None:
    recorder = RecordingBoundaryViolationRecorder()
    enforcer = OutputBoundaryEnforcer(
        settings=OutputBoundarySettings(
            output_min_chars=10,
            output_min_violation_mode=OutputMinViolationMode.FAIL,
        ),
        violation_recorder=recorder,
    )

    result = await enforcer.enforce("short", metadata={})

    assert result is None
    assert recorder.violations[0].violation_type == "output_too_short"
    assert recorder.violations[0].policy == "fail"
    assert recorder.violations[0].limit == 10
    assert recorder.violations[0].actual == 5


async def test_output_boundary_warn_mode_preserves_short_output() -> None:
    recorder = RecordingBoundaryViolationRecorder()
    enforcer = OutputBoundaryEnforcer(
        settings=OutputBoundarySettings(
            output_min_chars=10,
            output_min_violation_mode=OutputMinViolationMode.WARN,
        ),
        violation_recorder=recorder,
    )

    result = await enforcer.enforce("short", metadata={})

    assert result == "short"
    assert recorder.violations[0].policy == "warn"


async def test_output_boundary_retry_once_uses_longer_retry_result() -> None:
    recorder = RecordingBoundaryViolationRecorder()
    enforcer = OutputBoundaryEnforcer(
        settings=OutputBoundarySettings(
            output_min_chars=10,
            output_min_violation_mode=OutputMinViolationMode.RETRY_ONCE,
        ),
        violation_recorder=recorder,
    )

    result = await enforcer.enforce(
        "short",
        metadata={},
        attempt_longer_response=lambda content, required_min: f"{content} plus details",
    )

    assert result == "short plus details"
    assert recorder.violations[0].policy == "retry_once"


class RecordingBoundaryViolationRecorder(OutputBoundaryViolationRecorder):
    def __init__(self) -> None:
        self.violations: list[OutputBoundaryViolation] = []

    def record(self, violation: OutputBoundaryViolation) -> None:
        self.violations.append(violation)
