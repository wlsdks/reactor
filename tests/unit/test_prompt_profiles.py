from __future__ import annotations

import pytest

from reactor.prompts.profiles import (
    PromptDriftReport,
    PromptProfile,
    PromptRelease,
    ToolForcingMode,
    ToolForcingPolicy,
    prompt_cache_key,
    resolve_tool_exposure,
)


def test_prompt_release_hash_is_stable_for_equivalent_content() -> None:
    left = PromptRelease(
        profile=PromptProfile(
            name="standard",
            system_policy="Follow Reactor policy.",
            graph_profile="standard",
            version="v1",
        ),
        developer_policy="Use tools only after policy checks.",
        examples=["short", "long"],
        metadata={"b": 2, "a": 1},
    )
    right = PromptRelease(
        profile=PromptProfile(
            name="standard",
            system_policy="Follow Reactor policy.",
            graph_profile="standard",
            version="v1",
        ),
        developer_policy="Use tools only after policy checks.",
        examples=["short", "long"],
        metadata={"a": 1, "b": 2},
    )

    assert left.content_hash == right.content_hash
    assert left.content_hash.startswith("sha256:")


def test_prompt_cache_key_includes_release_hash_model_and_tenant() -> None:
    release = PromptRelease(
        profile=PromptProfile(
            name="support",
            system_policy="Answer with citations.",
            graph_profile="rag",
            version="2026-06-26",
        )
    )

    key = prompt_cache_key(
        tenant_id="tenant_1",
        release=release,
        model_provider="openai",
        model="gpt-5-mini",
    )

    assert key == (
        f"prompt:tenant_1:support:rag:2026-06-26:openai:gpt-5-mini:{release.content_hash}"
    )


def test_prompt_drift_report_detects_changed_release_content() -> None:
    original = PromptRelease(
        profile=PromptProfile(
            name="standard",
            system_policy="Follow Reactor policy.",
            graph_profile="standard",
            version="v1",
        )
    )
    changed = PromptRelease(
        profile=PromptProfile(
            name="standard",
            system_policy="Ignore Reactor policy.",
            graph_profile="standard",
            version="v1",
        )
    )

    report = PromptDriftReport.from_expected_hash(
        release=changed,
        expected_hash=original.content_hash,
    )

    assert report.drifted is True
    assert report.profile_name == "standard"
    assert report.version == "v1"
    assert report.expected_hash == original.content_hash
    assert report.actual_hash == changed.content_hash


def test_prompt_release_rejects_mismatched_profile_and_example_values() -> None:
    with pytest.raises(ValueError, match="example prompt must not be blank"):
        PromptRelease(
            profile=PromptProfile(
                name="standard",
                system_policy="Policy",
                graph_profile="standard",
                version="v1",
            ),
            examples=[""],
        ).validate()


def test_tool_forcing_policy_forces_single_allowed_tool() -> None:
    decision = resolve_tool_exposure(
        profile_tools=["SearchServer:search_docs", "Rag:hybrid_search"],
        request_tools=None,
        policy=ToolForcingPolicy(
            mode=ToolForcingMode.FORCE_ONE,
            forced_tool="Rag:hybrid_search",
        ),
    )

    assert decision.active_tools == ["Rag:hybrid_search"]
    assert decision.tool_choice == {"type": "tool", "name": "Rag:hybrid_search"}


def test_tool_forcing_policy_none_removes_all_tools() -> None:
    decision = resolve_tool_exposure(
        profile_tools=["SearchServer:search_docs"],
        request_tools=["TenantTool:lookup"],
        policy=ToolForcingPolicy(mode=ToolForcingMode.NONE),
    )

    assert decision.active_tools == []
    assert decision.tool_choice == "none"


def test_tool_forcing_policy_rejects_forced_tool_outside_active_set() -> None:
    with pytest.raises(ValueError, match="forced_tool must be in active tool set"):
        resolve_tool_exposure(
            profile_tools=["SearchServer:search_docs"],
            request_tools=None,
            policy=ToolForcingPolicy(
                mode=ToolForcingMode.FORCE_ONE,
                forced_tool="Rag:hybrid_search",
            ),
        )
