from __future__ import annotations

import math
from collections.abc import Mapping, Sequence, Set
from shlex import quote
from shlex import split as shlex_split
from typing import cast

from reactor.agents.langchain_agent import LANGCHAIN_AGENT_INVOKE_VERSION
from reactor.agents.streaming import (
    LANGCHAIN_AGENT_STREAM_EVENTS_VERSION,
    LANGCHAIN_RAW_STREAM_EVENTS_VERSION,
    LANGGRAPH_INTERRUPT_STREAM_EVENTS_VERSION,
)
from reactor.context.diagnostics import (
    ALLOWED_MEMORY_STATUS_COUNT_LABELS,
    CONTEXT_MANIFEST_DIAGNOSTIC_CODES,
)
from reactor.evals.langsmith_dataset import deterministic_langsmith_example_id
from reactor.feedback.workflow import feedback_review_closed
from reactor.kernel.citations import is_citation_safe_id
from reactor.memory.lifecycle_actions import MEMORY_LIFECYCLE_GATE_ACTION
from reactor.rag.ingestion_candidate_actions import (
    RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE,
    RAG_CANDIDATE_REVIEW_ACTION,
    rag_candidate_feedback_bulk_review_action,
    rag_candidate_review_action,
)
from reactor.rag.ingestion_candidate_ids import (
    command_slug,
    is_command_slug,
    rag_candidate_slug_from_case_id,
)
from reactor.rag.poisoning import RAG_POISONING_REASONS
from reactor.release.readiness_actions import (
    HARDENING_SUITE_REPORT_FILE,
    LATEST_TAG_COMMAND,
    RECOMMENDED_TAG_SOURCE,
)
from reactor.tools.sanitizer import TOOL_OUTPUT_SANITIZER_FINDINGS

REQUIRED_LANGSMITH_EVAL_CASE_IDS = frozenset({"rag-poisoning-retrieval-is-labeled"})
REQUIRED_LANGSMITH_GROUNDED_CASE_IDS = frozenset({"rag-grounded-answer-cites-source"})
ALLOWED_LANGSMITH_EVAL_CASE_IDS = frozenset(
    {
        "tool-exposure-issue-readonly",
        "casual-prompt-exposes-no-tools",
        "rag-grounded-answer-cites-source",
        "rag-poisoning-retrieval-is-labeled",
        "rag-ungrounded-answer-fails-closed",
        "rag-weak-answer-feedback-promoted",
        "rag-acl-blocked-source-denied",
        "rag-unknown-citation-rejected",
        "eval-duplicate-promotion-idempotent",
        "langsmith-sync-retry-recovers",
        "langsmith-sync-failure-preserves-pending",
        "rag-weak-answer-repaired-with-citation",
    }
)
RAG_CANDIDATE_LANGSMITH_EVAL_CASE_IDS = frozenset({"case_rag_candidate_grounded_citation"})
RAG_CANDIDATE_SOURCE_SUITE = "evals/regression/rag-ingestion-candidate.json"
LANGSMITH_PROMOTION_COVERAGE_BASE_FIELDS = frozenset(
    {
        "sourceRunIdPresent",
        "runFixturePresent",
        "runFixtureMatchedCase",
        "runContextDiagnosticsPresent",
        "requiredSourceRunId",
        "requiredRunFile",
        "requiredContextDiagnostics",
    }
)
LANGSMITH_PROMOTION_COVERAGE_CITATION_FIELDS = frozenset(
    {
        "citationMarkersRequired",
        "citationMarkersPresent",
        "runCitationMarkersPresent",
        "citationFailureAllowsMissingRunCitation",
    }
)
LANGSMITH_PROMOTION_COVERAGE_CONTEXT_CITATION_FIELDS = frozenset(
    {
        "contextCitationEvalCaseIdMatched",
        "contextCitationWorkflowTagMatched",
    }
)
REQUIRED_PROMPT_RELEASE_EVAL_CASE_IDS = frozenset(
    {
        "tool-exposure-issue-readonly",
        "casual-prompt-exposes-no-tools",
        "rag-grounded-answer-cites-source",
        "rag-poisoning-retrieval-is-labeled",
    }
)
REQUIRED_OBSERVABILITY_REDACTION_COVERAGE = frozenset(
    {
        "reactor.api_key",
        "reactor.payload.password",
        "reactor.payload.query",
        "reactor.payload.actor_email",
        "reactor.metadata.user_email",
        "reactor.metadata.nested.authorization",
    }
)
SENSITIVE_OBSERVABILITY_TARGET_MARKERS = (
    "api_key=",
    "apikey=",
    "access_token=",
    "authorization=",
    "bearer ",
    "password=",
    "secret=",
    "sk-",
    "token=",
    "xapp-",
    "xoxb-",
)


def readiness_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    for check in (
        hardening_suite_identity_contract_failure,
        hardening_suite_partial_contract_failure,
        observability_smoke_identity_contract_failure,
        langsmith_eval_sync_identity_contract_failure,
        release_evidence_identity_contract_failure,
        observability_contract_failure,
        backend_provider_observability_contract_failure,
        live_provider_runtime_contract_failure,
        live_slack_gateway_contract_failure,
        api_boundary_contract_failure,
        graph_topology_contract_failure,
        langsmith_eval_sync_contract_failure,
        checkpoint_provenance_contract_failure,
        langchain_middleware_policy_contract_failure,
        langchain_middleware_chain_contract_failure,
        langchain_serialization_boundary_contract_failure,
        context_management_lifecycle_contract_failure,
        usage_cost_lifecycle_contract_failure,
        tool_profile_budget_contract_failure,
        context_manifest_diagnostics_contract_failure,
        tool_output_guard_contract_failure,
        guard_block_contract_failure,
        structured_output_contract_failure,
        research_answer_contract_failure,
        tool_invocation_lifecycle_contract_failure,
        durable_run_queue_contract_failure,
        outbox_inbox_lifecycle_contract_failure,
        redis_coordination_contract_failure,
        mcp_preflight_contract_failure,
        slack_mcp_surface_policy_contract_failure,
        memory_maintenance_lifecycle_contract_failure,
        rag_ingestion_lifecycle_contract_failure,
        artifact_lifecycle_contract_failure,
        prompt_release_lifecycle_contract_failure,
        approval_lifecycle_contract_failure,
        provider_fallback_policy_contract_failure,
        langgraph_fault_tolerance_contract_failure,
        checkpoint_retention_policy_contract_failure,
        streaming_event_contract_failure,
        a2a_protocol_contract_failure,
        release_evidence_contract_failure,
    ):
        failure = check(name=name, item=item)
        if failure is not None:
            return failure
    return None


def report_identity_contract_failure(
    *,
    item: Mapping[str, object],
    expected_scope: str,
    expected_owner: str,
    expected_mode: str,
) -> bool:
    return (
        item.get("scope") != expected_scope
        or item.get("owner") != expected_owner
        or item.get("mode") != expected_mode
        or not non_empty_string(item.get("artifact"))
    )


def hardening_suite_identity_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    if report_identity_contract_failure(
        item=item,
        expected_scope="agent_release_gate",
        expected_owner="reactor.evals",
        expected_mode="local_agent_hardening_release_gate",
    ):
        return "hardening suite identity contract missing"
    return None


def hardening_suite_partial_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    selected_tags = item.get("selectedTags")
    if not isinstance(selected_tags, Mapping):
        return None
    selected_tags_mapping = cast(Mapping[str, object], selected_tags)
    if selected_tags_mapping.get("partial") is True:
        return "hardening suite partial report cannot pass release readiness"
    return None


def observability_smoke_identity_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    if name != "observability_smoke":
        return None
    if item.get("status") != "passed":
        return None
    if report_identity_contract_failure(
        item=item,
        expected_scope="local_contract",
        expected_owner="reactor.observability",
        expected_mode="langsmith_online_observability_contract",
    ):
        return "observability smoke identity contract missing"
    return None


def langsmith_eval_sync_identity_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    if name != "langsmith_eval_sync":
        return None
    if item.get("status") != "passed":
        return None
    if report_identity_contract_failure(
        item=item,
        expected_scope="langsmith_eval_dataset_sync",
        expected_owner="reactor.evals",
        expected_mode="langsmith_dataset_sync",
    ):
        return "langsmith eval sync identity contract missing"
    return None


def release_evidence_identity_contract_failure(
    *,
    name: str,
    item: Mapping[str, object],
) -> str | None:
    if name != "release_evidence":
        return None
    if report_identity_contract_failure(
        item=item,
        expected_scope="release_evidence",
        expected_owner="reactor.release",
        expected_mode="release_evidence",
    ):
        return "release evidence identity contract missing"
    return None


def api_boundary_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "dress_api_smoke":
        return None
    if item.get("status") != "passed":
        return None
    boundary = item.get("apiBoundary")
    if not isinstance(boundary, Mapping):
        return "api boundary contract missing"
    boundary_mapping = cast(Mapping[str, object], boundary)
    required_text_fields = {
        "status": "verified",
        "framework": "FastAPI",
        "schema": "OpenAPI",
        "validation": "Pydantic",
        "openapiPath": "/openapi.json",
    }
    required_boolean_fields = {
        "requestResponseModels",
        "publicMetadataAllowlist",
        "secretFree",
    }
    if set(boundary_mapping) != (
        set(required_text_fields)
        | required_boolean_fields
        | {
            "openapiVersion",
            "routeCount",
            "schemaCount",
            "requiredPaths",
            "nextActionSchemas",
            "nextActionSchemaFields",
            "runOperatorNextActionSchemaFields",
            "nextActionFieldsNonEmpty",
            "chatPolicyBoundary",
        }
    ):
        return "api boundary contract missing"
    for field_name, expected_value in required_text_fields.items():
        if boundary_mapping.get(field_name) != expected_value:
            return "api boundary contract missing"
    openapi_version = boundary_mapping.get("openapiVersion")
    if not isinstance(openapi_version, str) or not openapi_version.startswith("3."):
        return "api boundary contract missing"
    for field_name in ("routeCount", "schemaCount"):
        if not positive_int(boundary_mapping.get(field_name)):
            return "api boundary contract missing"
    if not exact_string_set(
        boundary_mapping.get("requiredPaths"),
        {
            "/api/admin/capabilities",
            "/api/chat",
        },
    ):
        return "api boundary contract missing"
    if not exact_string_set(
        boundary_mapping.get("nextActionSchemas"),
        {
            "FeedbackNextAction",
            "RagIngestionCandidateNextAction",
            "MemoryNextAction",
            "RunOperatorNextAction",
        },
    ):
        return "api boundary contract missing"
    if not exact_string_set(
        boundary_mapping.get("nextActionSchemaFields"),
        {
            "candidateTag",
            "caseFile",
            "command",
            "datasetName",
            "envFileCommand",
            "id",
            "label",
            "preflightEnvTemplate",
            "preflightFile",
            "releaseEvidenceFile",
            "releaseReadinessFile",
            "recommendedEnv",
            "readinessReportArg",
            "readinessReports",
            "remediationCommand",
            "replatformReadinessFile",
            "reportFile",
            "requiredEnvAnyOf",
            "requiredReadinessReports",
            "runFile",
            "smokePlanFile",
            "suiteFile",
        },
    ):
        return "api boundary contract missing"
    if not exact_string_set(
        boundary_mapping.get("runOperatorNextActionSchemaFields"),
        {
            "approvalId",
            "checkpointId",
            "checkpointNs",
            "command",
            "id",
            "label",
            "sourceRunId",
            "threadId",
        },
    ):
        return "api boundary contract missing"
    if boundary_mapping.get("nextActionFieldsNonEmpty") is not True:
        return "api boundary contract missing"
    if chat_policy_boundary_failure(boundary_mapping.get("chatPolicyBoundary")):
        return "api boundary contract missing"
    for field_name in required_boolean_fields:
        if boundary_mapping.get(field_name) is not True:
            return "api boundary contract missing"
    return None


def chat_policy_boundary_failure(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    boundary = cast(Mapping[str, object], value)
    if set(boundary) != {
        "invokeAndStreamSharedRunService",
        "sharedRunServiceComponents",
        "verificationSensors",
        "covers",
    }:
        return True
    if boundary.get("invokeAndStreamSharedRunService") is not True:
        return True
    if not exact_string_set(
        boundary.get("sharedRunServiceComponents"),
        {
            "tool_provider",
            "tool_handler",
            "tool_invocation_store",
            "builtin_tool_specs",
        },
    ):
        return True
    if boundary.get("verificationSensors") != [
        "uv run pytest tests/integration/test_chat_api.py -q "
        "-k 'chat_request_uses_reactor_tool_policy_components or "
        "chat_stream_uses_reactor_tool_policy_components'"
    ]:
        return True
    return not exact_string_set(
        boundary.get("covers"),
        {
            "chat_invoke_shares_reactor_tool_policy_components",
            "chat_stream_shares_reactor_tool_policy_components",
        },
    )


def live_slack_gateway_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "live_slack_workspace_smoke":
        return None
    if item.get("status") != "passed":
        return None
    gateway = item.get("slackGatewaySmoke")
    if not isinstance(gateway, Mapping):
        return "live slack gateway contract missing"
    gateway_mapping = cast(Mapping[str, object], gateway)
    allowed_gateway_fields = {
        "status",
        "gateway",
        "ingress",
        "currentThreadReplyRoute",
        "signatureVerificationRequired",
        "responseUrlRouteSupported",
        "mcpWriteOverlapForbidden",
        "requiredChecks",
    }
    if set(gateway_mapping) != allowed_gateway_fields:
        return "live slack gateway contract missing"
    expected_text_fields = {
        "status": "verified",
        "gateway": "native_slack_gateway",
        "ingress": "slash_command_or_socket_mode",
        "currentThreadReplyRoute": "native_gateway",
    }
    for field_name, expected_value in expected_text_fields.items():
        if gateway_mapping.get(field_name) != expected_value:
            return "live slack gateway contract missing"
    if not exact_string_set(
        gateway_mapping.get("requiredChecks"),
        {
            "required_env",
            "signed_request",
            "auth_test",
            "approval_block_contract",
        },
    ):
        return "live slack gateway contract missing"
    for field_name in (
        "signatureVerificationRequired",
        "responseUrlRouteSupported",
        "mcpWriteOverlapForbidden",
    ):
        if gateway_mapping.get(field_name) is not True:
            return "live slack gateway contract missing"
    return None


def live_provider_runtime_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name not in {"live_provider_runtime_smoke", "live_provider_smoke"}:
        return None
    if item.get("status") != "passed":
        return None
    runtime = item.get("providerRuntimeSmoke")
    if not isinstance(runtime, Mapping):
        return "live provider runtime contract missing"
    runtime_mapping = cast(Mapping[str, object], runtime)
    if set(runtime_mapping) != {
        "status",
        "invocationApi",
        "framework",
        "interface",
        "provider",
        "model",
        "requiredChecks",
    }:
        return "live provider runtime contract missing"
    if (
        runtime_mapping.get("status") != "verified"
        or runtime_mapping.get("invocationApi") != "ainvoke"
    ):
        return "live provider runtime contract missing"
    if runtime_mapping.get("framework") != "langchain":
        return "live provider runtime contract missing"
    if runtime_mapping.get("interface") != "ChatModelFactory":
        return "live provider runtime contract missing"
    for field_name in ("provider", "model"):
        field_value = runtime_mapping.get(field_name)
        if not isinstance(field_value, str) or not field_value.strip():
            return "live provider runtime contract missing"
    if not exact_string_set(
        runtime_mapping.get("requiredChecks"),
        {
            "required_env",
            "chat_model_invoke",
        },
    ):
        return "live provider runtime contract missing"
    return None


def backend_provider_observability_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    if name != "live_backend_provider_integration":
        return None
    if item.get("status") != "passed":
        return None
    target = item.get("observabilityTarget")
    if not isinstance(target, Mapping) or target.get("secretFree") is not True:
        return "backend provider observability contract missing"
    target_mapping = cast(Mapping[str, object], target)
    if set(target_mapping) != {
        "traceProvider",
        "project",
        "endpoint",
        "spanName",
        "secretFree",
    }:
        return "backend provider observability contract missing"
    if observability_target_has_secret(target_mapping):
        return "backend provider observability contract missing"
    required_target = {
        "traceProvider": "langsmith",
        "spanName": "reactor.release.backend_provider_smoke",
    }
    for field_name, expected_value in required_target.items():
        if target_mapping.get(field_name) != expected_value:
            return "backend provider observability contract missing"
    for field_name in ("project", "endpoint"):
        field_value = target_mapping.get(field_name)
        if not isinstance(field_value, str) or not field_value.strip():
            return "backend provider observability contract missing"

    privacy = item.get("privacy")
    if not isinstance(privacy, Mapping):
        return "backend provider observability contract missing"
    privacy_mapping = cast(Mapping[str, object], privacy)
    if set(privacy_mapping) != {
        "traceProvider",
        "hideInputs",
        "hideOutputs",
        "hideMetadata",
        "redactionCheck",
    }:
        return "backend provider observability contract missing"
    if (
        privacy_mapping.get("traceProvider") != "langsmith"
        or privacy_mapping.get("hideInputs") is not True
        or privacy_mapping.get("hideOutputs") is not True
        or privacy_mapping.get("hideMetadata") is not True
        or privacy_mapping.get("redactionCheck") != "required"
    ):
        return "backend provider observability contract missing"

    integration = item.get("backendProviderIntegration")
    if not isinstance(integration, Mapping):
        return "backend provider observability contract missing"
    integration_mapping = cast(Mapping[str, object], integration)
    if set(integration_mapping) != {
        "status",
        "invocationApi",
        "provider",
        "model",
        "usageMetadata",
        "requiredChecks",
    }:
        return "backend provider observability contract missing"
    if (
        integration_mapping.get("status") != "verified"
        or integration_mapping.get("invocationApi") != "ainvoke"
    ):
        return "backend provider observability contract missing"
    for field_name in ("provider", "model"):
        field_value = integration_mapping.get(field_name)
        if not isinstance(field_value, str) or not field_value.strip():
            return "backend provider observability contract missing"
    checks = integration_mapping.get("requiredChecks")
    if not exact_string_set(
        checks,
        {
            "required_env",
            "tracing_config",
            "chat_model_invoke",
            "usage_metadata",
        },
    ):
        return "backend provider observability contract missing"
    usage = integration_mapping.get("usageMetadata")
    if not isinstance(usage, Mapping):
        return "backend provider observability contract missing"
    usage_mapping = cast(Mapping[str, object], usage)
    if set(usage_mapping) != {
        "source",
        "present",
        "inputTokens",
        "outputTokens",
        "totalTokens",
        "totalMatchesBreakdown",
    }:
        return "backend provider observability contract missing"
    if (
        usage_mapping.get("source") != "LangChain AIMessage.usage_metadata"
        or usage_mapping.get("present") is not True
        or usage_mapping.get("totalMatchesBreakdown") is not True
    ):
        return "backend provider observability contract missing"
    input_tokens = usage_mapping.get("inputTokens")
    output_tokens = usage_mapping.get("outputTokens")
    total_tokens = usage_mapping.get("totalTokens")
    if (
        not non_negative_int(input_tokens)
        or not non_negative_int(output_tokens)
        or not non_negative_int(total_tokens)
    ):
        return "backend provider observability contract missing"
    input_token_count = cast(int, input_tokens)
    output_token_count = cast(int, output_tokens)
    total_token_count = cast(int, total_tokens)
    if total_token_count != input_token_count + output_token_count:
        return "backend provider observability contract missing"
    return None


def mcp_preflight_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    preflight = item.get("mcpPreflight")
    if not isinstance(preflight, Mapping):
        return "mcp preflight contract missing"
    preflight_mapping = cast(Mapping[str, object], preflight)
    required_preflight_boolean_fields = {
        "privateAddressBlocked",
        "tokenPassthroughForbidden",
        "unsupportedProtocolRejected",
        "credentialBindingRequired",
        "authWithoutCredentialBindingRejected",
    }
    allowed_preflight_fields = {
        "status",
        "protocolVersion",
        "adapter",
        "sdk",
        "toolNameFormat",
        "adapterToolLoading",
        "supportedTransports",
        "authorizationSecurity",
    } | required_preflight_boolean_fields
    if set(preflight_mapping) != allowed_preflight_fields:
        return "mcp preflight contract missing"
    if preflight_mapping.get("status") != "verified":
        return "mcp preflight contract missing"
    if preflight_mapping.get("protocolVersion") != "2025-11-25":
        return "mcp preflight contract missing"
    if preflight_mapping.get("adapter") != "langchain-mcp-adapters":
        return "mcp preflight contract missing"
    if preflight_mapping.get("sdk") != "mcp":
        return "mcp preflight contract missing"
    if preflight_mapping.get("toolNameFormat") != "ServerName:tool_name":
        return "mcp preflight contract missing"
    adapter_tool_loading = preflight_mapping.get("adapterToolLoading")
    if not isinstance(adapter_tool_loading, Mapping):
        return "mcp preflight contract missing"
    adapter_tool_loading_mapping = cast(Mapping[str, object], adapter_tool_loading)
    required_adapter_fields = {
        "client": "MultiServerMCPClient",
        "primaryMethod": "get_tools",
        "sessionLoader": "load_mcp_tools",
        "streamableHttpProtocolHeader": "MCP-Protocol-Version",
    }
    required_adapter_boolean_fields = {
        "structuredContentArtifactsSupported",
        "toolErrorsReturnToolMessage",
        "toolExceptionPropagationConfigurable",
    }
    if set(adapter_tool_loading_mapping) != (
        set(required_adapter_fields)
        | required_adapter_boolean_fields
        | {"connectionDictionaryTransports"}
    ):
        return "mcp preflight contract missing"
    for field_name, expected_value in required_adapter_fields.items():
        if adapter_tool_loading_mapping.get(field_name) != expected_value:
            return "mcp preflight contract missing"
    connection_transports = adapter_tool_loading_mapping.get("connectionDictionaryTransports")
    if not exact_string_set(connection_transports, {"stdio", "streamable_http"}):
        return "mcp preflight contract missing"
    for field_name in required_adapter_boolean_fields:
        if adapter_tool_loading_mapping.get(field_name) is not True:
            return "mcp preflight contract missing"
    supported_transports = preflight_mapping.get("supportedTransports")
    if not exact_string_set(supported_transports, {"stdio", "streamable_http"}):
        return "mcp preflight contract missing"
    for field_name in required_preflight_boolean_fields:
        if preflight_mapping.get(field_name) is not True:
            return "mcp preflight contract missing"
    authorization_security = preflight_mapping.get("authorizationSecurity")
    if not isinstance(authorization_security, Mapping):
        return "mcp preflight contract missing"
    authorization_security_mapping = cast(Mapping[str, object], authorization_security)
    required_authorization_security_fields = {
        "oauth21Required",
        "pkceRequired",
        "tlsRequired",
        "protectedResourceMetadataRequired",
        "authorizationServerMetadataRequired",
        "tokensStoredServerSide",
        "scopesValidated",
        "resourceIndicatorsRequired",
        "tokenAudienceValidated",
        "leastPrivilegeScopesRequired",
    }
    if set(authorization_security_mapping) != required_authorization_security_fields:
        return "mcp preflight contract missing"
    for field_name in required_authorization_security_fields:
        if authorization_security_mapping.get(field_name) is not True:
            return "mcp preflight contract missing"
    return None


def a2a_protocol_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "live_peer_network_interoperability_smoke":
        return None
    if item.get("status") != "passed":
        return None
    protocol = item.get("a2aProtocol")
    if not isinstance(protocol, Mapping):
        return "a2a protocol contract missing"
    protocol_mapping = cast(Mapping[str, object], protocol)
    if set(protocol_mapping) != {
        "status",
        "agentCard",
        "diagnostics",
        "protocolNegotiation",
        "taskApi",
        "operationalEvidence",
        "executionPolicyBoundary",
        "secretFree",
        "tlsRequired",
    }:
        return "a2a protocol contract missing"
    if (
        protocol_mapping.get("status") != "verified"
        or protocol_mapping.get("secretFree") is not True
        or protocol_mapping.get("tlsRequired") is not True
    ):
        return "a2a protocol contract missing"
    agent_card = protocol_mapping.get("agentCard")
    if not isinstance(agent_card, Mapping):
        return "a2a protocol contract missing"
    agent_card_mapping = cast(Mapping[str, object], agent_card)
    if set(agent_card_mapping) != {
        "name",
        "interfaceCount",
        "interfaceProtocolBindings",
        "interfaceProtocolVersions",
        "interfaceUrls",
        "wellKnownPath",
    }:
        return "a2a protocol contract missing"
    if not non_empty_string(agent_card_mapping.get("name")):
        return "a2a protocol contract missing"
    if not positive_int(agent_card_mapping.get("interfaceCount")):
        return "a2a protocol contract missing"
    interface_protocol_bindings = agent_card_mapping.get("interfaceProtocolBindings")
    if not exact_string_set(interface_protocol_bindings, {"JSONRPC"}):
        return "a2a protocol contract missing"
    interface_protocol_versions = agent_card_mapping.get("interfaceProtocolVersions")
    if not exact_string_set(interface_protocol_versions, {"1.0"}):
        return "a2a protocol contract missing"
    interface_urls = agent_card_mapping.get("interfaceUrls")
    if not non_empty_string_sequence(interface_urls):
        return "a2a protocol contract missing"
    if any(contains_sensitive_target_marker(url) for url in cast(Sequence[str], interface_urls)):
        return "a2a protocol contract missing"
    if agent_card_mapping.get("wellKnownPath") != "/.well-known/agent-card.json":
        return "a2a protocol contract missing"
    diagnostics = protocol_mapping.get("diagnostics")
    if not isinstance(diagnostics, Mapping):
        return "a2a protocol contract missing"
    diagnostics_mapping = cast(Mapping[str, object], diagnostics)
    if set(diagnostics_mapping) != {"sdkAvailable", "protocolVersion", "endpoint", "path"}:
        return "a2a protocol contract missing"
    if diagnostics_mapping.get("sdkAvailable") is not True:
        return "a2a protocol contract missing"
    if diagnostics_mapping.get("protocolVersion") != "1.0":
        return "a2a protocol contract missing"
    endpoint = diagnostics_mapping.get("endpoint")
    if not non_empty_string(endpoint):
        return "a2a protocol contract missing"
    if contains_sensitive_target_marker(cast(str, endpoint)):
        return "a2a protocol contract missing"
    if cast(str, endpoint) not in cast(Sequence[str], interface_urls):
        return "a2a protocol contract missing"
    if diagnostics_mapping.get("path") != "/v1/a2a/diagnostics":
        return "a2a protocol contract missing"
    protocol_negotiation = protocol_mapping.get("protocolNegotiation")
    if not isinstance(protocol_negotiation, Mapping):
        return "a2a protocol contract missing"
    protocol_negotiation_mapping = cast(Mapping[str, object], protocol_negotiation)
    required_protocol_fields = {
        "requestHeader": "A2A-Version",
        "requestedVersion": "1.0",
        "responseVersion": "1.0",
        "telemetryInstrumentation": "a2a-sdk[telemetry]",
    }
    required_protocol_boolean_fields = {
        "majorMinorOnly",
        "agentCardVersionsChecked",
        "serverGeneratedTaskIds",
        "sdkFastApiSurface",
    }
    if set(protocol_negotiation_mapping) != (
        set(required_protocol_fields) | required_protocol_boolean_fields
    ):
        return "a2a protocol contract missing"
    for field_name, expected_value in required_protocol_fields.items():
        if protocol_negotiation_mapping.get(field_name) != expected_value:
            return "a2a protocol contract missing"
    for field_name in required_protocol_boolean_fields:
        if protocol_negotiation_mapping.get(field_name) is not True:
            return "a2a protocol contract missing"
    task_api = protocol_mapping.get("taskApi")
    if not isinstance(task_api, Mapping):
        return "a2a protocol contract missing"
    task_api_mapping = cast(Mapping[str, object], task_api)
    if set(task_api_mapping) != {"status", "taskStatus", "path"}:
        return "a2a protocol contract missing"
    if task_api_mapping.get("status") != "passed":
        return "a2a protocol contract missing"
    if not non_empty_string(task_api_mapping.get("taskStatus")):
        return "a2a protocol contract missing"
    if task_api_mapping.get("path") != "/v1/a2a/tasks":
        return "a2a protocol contract missing"
    operational_evidence = protocol_mapping.get("operationalEvidence")
    if not isinstance(operational_evidence, Mapping):
        return "a2a protocol contract missing"
    operational_evidence_mapping = cast(Mapping[str, object], operational_evidence)
    required_operational_evidence_fields = {
        "auditRecorded",
        "idempotencyEnforced",
        "telemetryEnabled",
        "pushOutboxRouted",
    }
    if set(operational_evidence_mapping) != required_operational_evidence_fields:
        return "a2a protocol contract missing"
    for field_name in required_operational_evidence_fields:
        if operational_evidence_mapping.get(field_name) is not True:
            return "a2a protocol contract missing"
    if a2a_execution_policy_boundary_failure(protocol_mapping.get("executionPolicyBoundary")):
        return "a2a protocol contract missing"
    return None


def a2a_execution_policy_boundary_failure(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    boundary = cast(Mapping[str, object], value)
    for field_name in (
        "requiresReactorAppContext",
        "runServiceRequired",
        "directRunnerFallbackForbidden",
    ):
        if boundary.get(field_name) is not True:
            return True
    if not exact_string_set(
        boundary.get("sharedRunServiceComponents"),
        {
            "tool_provider",
            "tool_handler",
            "tool_invocation_store",
            "builtin_tool_specs",
        },
    ):
        return True
    if boundary.get("verificationSensors") != [
        "uv run pytest tests/unit/test_a2a_server.py -q "
        "-k 'execution_fails_closed_without_reactor_app_context or "
        "execution_uses_reactor_tool_policy_components'"
    ]:
        return True
    if not exact_string_set(
        boundary.get("covers"),
        {
            "a2a_execution_requires_reactor_policy_runtime",
            "a2a_execution_shares_reactor_tool_policy_components",
        },
    ):
        return True
    return False


def contains_sensitive_target_marker(value: str) -> bool:
    normalized = value.lower()
    return any(marker in normalized for marker in SENSITIVE_OBSERVABILITY_TARGET_MARKERS)


def slack_mcp_surface_policy_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    policy = item.get("slackMcpSurfacePolicy")
    if not isinstance(policy, Mapping):
        return "slack mcp surface policy missing"
    policy_mapping = cast(Mapping[str, object], policy)
    required_true_fields = {
        "nativeGatewayOwnsIngress",
        "nativeGatewayOwnsCurrentThreadReplies",
        "slackMcpModelFacingOnly",
        "overlappingWriteSurfacesRequireRouteSelection",
        "promptContextDeclaresToolAvailability",
        "unavailableToolClaimsForbidden",
    }
    allowed_policy_fields = required_true_fields | {
        "status",
        "currentThreadReplyRoute",
        "workspaceActionRoute",
        "auditSurfaces",
        "faqIngestionFailureBoundary",
        "feedbackReviewHandoff",
    }
    if set(policy_mapping) != allowed_policy_fields:
        return "slack mcp surface policy missing"
    if policy_mapping.get("status") != "verified":
        return "slack mcp surface policy missing"
    for field_name in required_true_fields:
        if policy_mapping.get(field_name) is not True:
            return "slack mcp surface policy missing"
    if policy_mapping.get("currentThreadReplyRoute") != "native_gateway":
        return "slack mcp surface policy missing"
    if policy_mapping.get("workspaceActionRoute") != "slack_mcp_tools":
        return "slack mcp surface policy missing"
    if not exact_string_set(
        policy_mapping.get("auditSurfaces"),
        {"native_slack_gateway", "slack_mcp_tools"},
    ):
        return "slack mcp surface policy missing"
    if slack_faq_failure_boundary_failure(policy_mapping.get("faqIngestionFailureBoundary")):
        return "slack mcp surface policy missing"
    feedback_handoff = policy_mapping.get("feedbackReviewHandoff")
    if not isinstance(feedback_handoff, Mapping):
        return "slack mcp surface policy missing"
    feedback_handoff_mapping = cast(Mapping[str, object], feedback_handoff)
    if set(feedback_handoff_mapping) != {
        "status",
        "responseSurfaces",
        "reviewCommand",
        "feedbackNextActionIds",
        "feedbackNextActionIdentityFields",
        "feedbackNextActionReadinessFields",
        "verificationSensors",
        "rawSlackPayloadExcluded",
    }:
        return "slack mcp surface policy missing"
    if feedback_handoff_mapping.get("status") != "verified":
        return "slack mcp surface policy missing"
    if not exact_string_set(
        feedback_handoff_mapping.get("responseSurfaces"),
        {"slack_run_response", "slack_approval_resume_ack"},
    ):
        return "slack mcp surface policy missing"
    if feedback_handoff_mapping.get("reviewCommand") != (
        "reactor-admin feedback --rating thumbs_down "
        "--review-status inbox --limit 10 --output table"
    ):
        return "slack mcp surface policy missing"
    if not exact_string_set(
        feedback_handoff_mapping.get("feedbackNextActionIds"),
        {
            "promote-eval",
            "sync-langsmith",
            "refresh-readiness",
            "export-candidate-feedback",
            "review-done",
        },
    ):
        return "slack mcp surface policy missing"
    if not exact_string_set(
        feedback_handoff_mapping.get("feedbackNextActionIdentityFields"),
        {"feedbackId", "evalCaseId", "sourceRunId"},
    ):
        return "slack mcp surface policy missing"
    if not exact_string_set(
        feedback_handoff_mapping.get("feedbackNextActionReadinessFields"),
        {
            "releaseReadinessFile",
            "readinessReportArg",
            "requiredReadinessReports",
            "readinessReports",
        },
    ):
        return "slack mcp surface policy missing"
    verification_sensors = feedback_handoff_mapping.get("verificationSensors")
    if not isinstance(verification_sensors, Mapping):
        return "slack mcp surface policy missing"
    verification_sensors_mapping = cast(Mapping[str, object], verification_sensors)
    if set(verification_sensors_mapping) != {"focusedTests", "covers"}:
        return "slack mcp surface policy missing"
    if not same_string_sequence(
        verification_sensors_mapping.get("focusedTests"),
        [
            "uv run pytest tests/unit/test_admin_cli.py -q "
            "-k 'structured_recovery_actions or structured_error_body'",
            "uv run pytest tests/unit/test_feedback_router.py -q "
            "-k 'feedback_id or readiness_handoff'",
            "uv run pytest tests/integration/test_feedback_api.py -q -k feedback",
        ],
    ):
        return "slack mcp surface policy missing"
    if not same_string_sequence(
        verification_sensors_mapping.get("covers"),
        [
            "admin_feedback_review_surfaces_recovery_actions",
            "admin_feedback_review_preserves_structured_error_body",
            "feedback_api_review_handoff_exercised",
            "feedback_next_actions_preserve_feedback_identity",
            "feedback_next_actions_preserve_readiness_handoff_fields",
        ],
    ):
        return "slack mcp surface policy missing"
    if feedback_handoff_mapping.get("rawSlackPayloadExcluded") is not True:
        return "slack mcp surface policy missing"
    return None


def slack_faq_failure_boundary_failure(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    boundary = cast(Mapping[str, object], value)
    required_text_fields = {
        "status": "verified",
        "worker": "ChannelFaqIngestWorker",
        "safeFailureCode": "slack_faq_ingestion_failed",
    }
    for field_name, expected_value in required_text_fields.items():
        if boundary.get(field_name) != expected_value:
            return True
    if not exact_string_set(
        boundary.get("exceptionDetailsExcludedFrom"),
        {
            "worker.result.error",
            "registration.last_error",
            "admin.registration.lastError",
        },
    ):
        return True
    if boundary.get("failOpenResultPreserved") is not True:
        return True
    if boundary.get("verificationSensors") != [
        "uv run pytest tests/unit/test_slack_worker.py -q "
        "-k channel_faq_ingest_worker_records_failure_without_raising"
    ]:
        return True
    if boundary.get("covers") != ["slack_faq_ingestion_failure_uses_safe_error_code"]:
        return True
    return False


def memory_maintenance_lifecycle_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    lifecycle = item.get("memoryMaintenanceLifecycle")
    if not isinstance(lifecycle, Mapping):
        return "memory maintenance lifecycle contract missing"
    lifecycle_mapping = cast(Mapping[str, object], lifecycle)
    required_text_fields = {
        "status": "verified",
        "framework": "langmem",
        "extractor": "LangMemMemoryExtractor",
        "proposalJob": "LangMemProposalJob",
        "proposalService": "MemoryProposalService",
        "store": "SqlAlchemyMemoryStore",
    }
    required_boolean_fields = {
        "extractionCreatesProposalsOnly",
        "extractedMemoryIdRequired",
        "extractedMemoryContentRequired",
        "promotionRequiresReviewer",
        "sensitivePromotionBlocked",
        "tombstoneDeletesEmbedding",
        "activeQueryFiltersStatus",
        "applicationOwnsLifecycle",
        "checkpointMemorySeparated",
    }
    allowed_lifecycle_fields = (
        set(required_text_fields)
        | required_boolean_fields
        | {
            "managerContract",
            "proposalStatuses",
            "itemStatuses",
            "consolidationPolicy",
            "verificationSensors",
            "reviewSurface",
            "dependencyWarnings",
        }
    )
    if set(lifecycle_mapping) != allowed_lifecycle_fields:
        return "memory maintenance lifecycle contract missing"
    for field_name, expected_value in required_text_fields.items():
        if lifecycle_mapping.get(field_name) != expected_value:
            return "memory maintenance lifecycle contract missing"
    manager_contract = lifecycle_mapping.get("managerContract")
    if not isinstance(manager_contract, Mapping):
        return "memory maintenance lifecycle contract missing"
    manager_contract_mapping = cast(Mapping[str, object], manager_contract)
    expected_manager_fields = {
        "factory": "langmem.create_memory_manager",
        "storeFactory": "langmem.create_memory_store_manager",
        "invokeApi": "ainvoke",
        "inputMessagesKey": "messages",
        "maxSteps": 1,
        "maxCandidates": 20,
        "candidateOverflowPolicy": "reject_all",
    }
    allowed_manager_fields = set(expected_manager_fields) | {
        "enableInserts",
        "enableUpdates",
        "enableDeletes",
        "applicationOwnsDeletes",
    }
    if set(manager_contract_mapping) != allowed_manager_fields:
        return "memory maintenance lifecycle contract missing"
    for manager_field_name, manager_expected_value in expected_manager_fields.items():
        if manager_contract_mapping.get(manager_field_name) != manager_expected_value:
            return "memory maintenance lifecycle contract missing"
    for field_name in (
        "enableInserts",
        "enableUpdates",
        "applicationOwnsDeletes",
    ):
        if manager_contract_mapping.get(field_name) is not True:
            return "memory maintenance lifecycle contract missing"
    if manager_contract_mapping.get("enableDeletes") is not False:
        return "memory maintenance lifecycle contract missing"
    required_proposal_statuses = {"proposed", "approved", "rejected", "expired"}
    if not exact_string_set(
        lifecycle_mapping.get("proposalStatuses"),
        required_proposal_statuses,
    ):
        return "memory maintenance lifecycle contract missing"
    required_item_statuses = {"active", "superseded", "tombstoned"}
    if not exact_string_set(
        lifecycle_mapping.get("itemStatuses"),
        required_item_statuses,
    ):
        return "memory maintenance lifecycle contract missing"
    for field_name in required_boolean_fields:
        if lifecycle_mapping.get(field_name) is not True:
            return "memory maintenance lifecycle contract missing"
    consolidation_policy = lifecycle_mapping.get("consolidationPolicy")
    if not isinstance(consolidation_policy, Mapping):
        return "memory maintenance lifecycle contract missing"
    consolidation_policy_mapping = cast(Mapping[str, object], consolidation_policy)
    allowed_consolidation_policy_fields = {
        "supersedesPriorActiveMemory",
        "reviewedPromotionCanSupersedePriorActiveMemory",
        "dedupeOrConflictRequiresReviewer",
        "supersededItemsExcludedFromActiveContext",
    }
    if set(consolidation_policy_mapping) != allowed_consolidation_policy_fields:
        return "memory maintenance lifecycle contract missing"
    for field_name in allowed_consolidation_policy_fields:
        if consolidation_policy_mapping.get(field_name) is not True:
            return "memory maintenance lifecycle contract missing"
    verification_sensors = lifecycle_mapping.get("verificationSensors")
    if memory_verification_sensors_contract_failure(verification_sensors):
        return "memory maintenance lifecycle contract missing"
    review_surface = lifecycle_mapping.get("reviewSurface")
    dependency_warnings = lifecycle_mapping.get("dependencyWarnings")
    if memory_review_surface_contract_failure(review_surface, dependency_warnings):
        return "memory maintenance lifecycle contract missing"
    if memory_dependency_warnings_contract_failure(dependency_warnings):
        return "memory maintenance lifecycle contract missing"
    return None


def memory_verification_sensors_contract_failure(verification_sensors: object) -> bool:
    if not isinstance(verification_sensors, Mapping):
        return True
    mapping = cast(Mapping[str, object], verification_sensors)
    if set(mapping) != {
        "focusedTests",
        "releaseReadinessContracts",
        "artifactOutputs",
        "covers",
    }:
        return True
    if not same_string_sequence(
        mapping.get("focusedTests"),
        [
            "uv run pytest tests/unit/test_rag_memory.py -q",
            "uv run pytest tests/unit/test_prompt_assembler.py -q -k memory",
            "uv run pytest tests/unit/test_context_manifest.py -q -k memory",
            "uv run pytest tests/unit/test_memory_cli.py "
            "tests/unit/test_memory_lifecycle_actions.py "
            "-q -k 'memory_lifecycle or sensitive_recovery_actions or structured_error_body'",
            "REACTOR_TEST_POSTGRES=1 uv run pytest "
            "tests/integration/test_memory_postgres_lifecycle.py -q",
            "uv run pytest tests/integration/test_admin_api.py -q -k memory",
            "uv run pytest tests/integration/test_feedback_api.py -q -k memory",
            "uv run pytest tests/unit/test_slack_worker.py "
            "-q -k 'reaction_feedback_memory_handoff'",
            "uv run pytest tests/unit/test_slack_feedback.py "
            "-q -k 'negative_ack_preserves_memory_review_tag'",
        ],
    ):
        return True
    if not same_string_sequence(
        mapping.get("releaseReadinessContracts"),
        [
            "memoryMaintenanceLifecycle",
            "contextManifestDiagnostics.memoryAdmissionPolicy",
        ],
    ):
        return True
    if not same_string_sequence(
        mapping.get("artifactOutputs"),
        [
            "reports/hardening-suite.json",
            "reports/release/replatform-readiness.local.json",
            "reports/release/release-smoke-plan.local.json",
            "reports/release/release-smoke-preflight.local.json",
            "reports/release/release-smoke-preflight.local.env",
            "reports/release-smoke-run.json",
            "reports/release-evidence.json",
            "reports/release-readiness.json",
        ],
    ):
        return True
    return not same_string_sequence(
        mapping.get("covers"),
        [
            "langmem_manager_shape_exercised",
            "langmem_manager_lifecycle_policy_explicitly_configured",
            "langmem_extracted_memory_id_required",
            "langmem_extracted_memory_content_required",
            "langmem_extraction_candidate_budget_enforced",
            "proposal_promotion_requires_reviewer",
            "sensitive_memory_proposals_blocked",
            "memory_source_payload_secret_markers_flagged",
            "source_payload_sensitive_memory_proposals_blocked",
            "supersession_marks_prior_active_memory",
            "self_supersession_rejected",
            "tombstone_deletes_embedding",
            "active_namespace_memory_retrieval_boundary_exercised",
            "superseded_and_tombstoned_memory_excluded_from_model_context",
            "memory_review_api_and_cli_surface_exercised",
            "memory_feedback_review_handoff_exercised",
            "slack_reaction_feedback_enters_memory_review_handoff",
            "slack_button_feedback_preserves_memory_review_tags",
        ],
    )


def memory_dependency_warnings_contract_failure(dependency_warnings: object) -> bool:
    if not isinstance(dependency_warnings, Mapping):
        return True
    mapping = cast(Mapping[str, object], dependency_warnings)
    if set(mapping) != {
        "status",
        "checkedPackages",
        "installedVersions",
        "directPins",
        "pinSource",
        "reviewCommand",
        "resolverCheck",
        "remediationCommand",
        "findings",
    }:
        return True
    if mapping.get("status") not in {"verified", "review_required"}:
        return True
    if not same_string_sequence(
        mapping.get("checkedPackages"),
        ["langmem", "trustcall", "langgraph"],
    ):
        return True
    if memory_dependency_versions_contract_failure(mapping.get("installedVersions")):
        return True
    if memory_dependency_direct_pins_contract_failure(mapping.get("directPins")):
        return True
    if mapping.get("pinSource") != "pyproject.toml":
        return True
    if mapping.get("reviewCommand") != "uv pip show langmem trustcall langgraph":
        return True
    resolver_check = mapping.get("resolverCheck")
    if not isinstance(resolver_check, Mapping):
        return True
    resolver_mapping = cast(Mapping[object, object], resolver_check)
    if set(resolver_mapping) != {"command", "status", "latestKnownFrom"}:
        return True
    if (
        resolver_mapping.get("command")
        != "uv lock --upgrade-package langmem --upgrade-package trustcall "
        "--upgrade-package langgraph --dry-run"
        or resolver_mapping.get("status") != "no_lockfile_changes"
        or resolver_mapping.get("latestKnownFrom") != "resolver"
    ):
        return True
    if (
        mapping.get("remediationCommand")
        != "monitor upstream trustcall/langmem compatibility; keep "
        "dependency warning visible until "
        "trustcall stops importing langgraph.constants.Send or "
        "Reactor replaces the dependency path"
    ):
        return True
    findings = mapping.get("findings")
    if not isinstance(findings, Sequence) or isinstance(findings, str | bytes | bytearray):
        return True
    if mapping.get("status") == "verified":
        return len(cast(Sequence[object], findings)) != 0
    typed_findings = cast(Sequence[object], findings)
    if len(typed_findings) == 0:
        return True
    for finding in typed_findings:
        if not isinstance(finding, Mapping):
            return True
        finding_mapping = cast(Mapping[object, object], finding)
        if (
            finding_mapping.get("package") != "trustcall"
            or finding_mapping.get("module") != "trustcall._base"
            or finding_mapping.get("deprecatedImport") != "langgraph.constants.Send"
            or finding_mapping.get("replacement") != "langgraph.types.Send"
            or finding_mapping.get("severity") != "warning"
        ):
            return True
    return False


def memory_dependency_versions_contract_failure(installed_versions: object) -> bool:
    if not isinstance(installed_versions, Mapping):
        return True
    mapping = cast(Mapping[object, object], installed_versions)
    if set(mapping) != {"langmem", "trustcall", "langgraph"}:
        return True
    return any(not isinstance(version, str) or not version.strip() for version in mapping.values())


def memory_dependency_direct_pins_contract_failure(direct_pins: object) -> bool:
    if not isinstance(direct_pins, Mapping):
        return True
    mapping = cast(Mapping[object, object], direct_pins)
    if set(mapping) != {"langmem", "langgraph"}:
        return True
    return mapping.get("langmem") != "==0.0.30" or mapping.get("langgraph") != "==1.2.7"


def memory_review_surface_contract_failure(
    review_surface: object,
    dependency_warnings: object,
) -> bool:
    if not isinstance(review_surface, Mapping):
        return True
    mapping = cast(Mapping[str, object], review_surface)
    if set(mapping) != {
        "approvalApi",
        "cliApprovalTable",
        "lifecycleGateAction",
        "dependencyReviewCommand",
        "dependencyRemediationCommand",
        "proposalNextActionIds",
        "lifecycleGateReportBinding",
        "feedbackNextActionSubjectField",
        "responseProjection",
        "rawSourcePayloadExposed",
        "sourcePayloadPrivacy",
        "sensitivityProjection",
        "maintenanceSummaryFields",
    }:
        return True
    dependency_mapping = (
        cast(Mapping[str, object], dependency_warnings)
        if isinstance(dependency_warnings, Mapping)
        else cast(Mapping[str, object], {})
    )
    if (
        mapping.get("approvalApi") != "/api/admin/memory/proposals/{proposal_id}/approve"
        or mapping.get("cliApprovalTable")
        != (
            "reactor-memory approve PROPOSAL_ID "
            "--reason 'reviewed and approved memory' --output table"
        )
        or mapping.get("lifecycleGateAction") != MEMORY_LIFECYCLE_GATE_ACTION
        or mapping.get("dependencyReviewCommand") != dependency_mapping.get("reviewCommand")
        or mapping.get("dependencyRemediationCommand")
        != dependency_mapping.get("remediationCommand")
        or mapping.get("feedbackNextActionSubjectField") != "subjectUserId"
        or mapping.get("responseProjection") != "maintenance"
        or mapping.get("rawSourcePayloadExposed") is not False
    ):
        return True
    if not same_string_sequence(
        mapping.get("proposalNextActionIds"),
        [
            "approve-memory",
            "reject-memory",
            "review-memory-dependencies",
            "verify-memory-lifecycle",
        ],
    ):
        return True
    if memory_lifecycle_gate_report_binding_contract_failure(
        mapping.get("lifecycleGateReportBinding")
    ):
        return True
    if memory_source_payload_privacy_contract_failure(mapping.get("sourcePayloadPrivacy")):
        return True
    if memory_sensitivity_projection_contract_failure(mapping.get("sensitivityProjection")):
        return True
    return not same_string_sequence(
        mapping.get("maintenanceSummaryFields"),
        [
            "manager",
            "storeManager",
            "operation",
            "maxSteps",
            "deletePolicy",
            "dependencyReviewCommand",
            "dependencyRemediationCommand",
            "sensitivity",
        ],
    )


def memory_lifecycle_gate_report_binding_contract_failure(binding: object) -> bool:
    if not isinstance(binding, Mapping):
        return True
    mapping = cast(Mapping[object, object], binding)
    readiness_reports = mapping.get("readinessReports")
    if not isinstance(readiness_reports, Mapping):
        return True
    report_mapping = cast(Mapping[object, object], readiness_reports)
    return (
        mapping.get("readinessReportArg")
        != f"--readiness-report hardening_suite={HARDENING_SUITE_REPORT_FILE}"
        or not same_string_sequence(mapping.get("requiredReadinessReports"), ["hardening_suite"])
        or set(report_mapping) != {"hardening_suite"}
        or report_mapping.get("hardening_suite") != HARDENING_SUITE_REPORT_FILE
    )


def memory_sensitivity_projection_contract_failure(projection: object) -> bool:
    if not isinstance(projection, Mapping):
        return True
    mapping = cast(Mapping[str, object], projection)
    if set(mapping) != {
        "apiProjection",
        "cliProjection",
        "rawSourcePayloadExposed",
        "fields",
    }:
        return True
    return (
        mapping.get("apiProjection") != "maintenance.sensitivity"
        or mapping.get("cliProjection") != "SENSITIVITY"
        or mapping.get("rawSourcePayloadExposed") is not False
        or not same_string_sequence(
            mapping.get("fields"),
            ["status", "policy", "markers", "source"],
        )
    )


def memory_source_payload_privacy_contract_failure(privacy: object) -> bool:
    if not isinstance(privacy, Mapping):
        return True
    mapping = cast(Mapping[str, object], privacy)
    if set(mapping) != {
        "apiProjection",
        "cliProjection",
        "readinessProjection",
        "rawSourcePayloadExposed",
        "sourcePayloadKeysExposed",
        "secretScanRequired",
    }:
        return True
    return (
        mapping.get("apiProjection") != "maintenance"
        or mapping.get("cliProjection") != "maintenance"
        or mapping.get("readinessProjection") != "contract_metadata_only"
        or mapping.get("rawSourcePayloadExposed") is not False
        or mapping.get("sourcePayloadKeysExposed") is not False
        or mapping.get("secretScanRequired") is not True
    )


def provider_fallback_policy_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    policy = item.get("providerFallbackPolicy")
    if not isinstance(policy, Mapping):
        return "provider fallback policy contract missing"
    policy_mapping = cast(Mapping[str, object], policy)
    required_text_fields = {
        "status": "verified",
        "middleware": "ModelFallbackMiddleware",
        "router": "ProviderRouter",
        "tenantPolicyBoundary": "provider_routing_policy",
    }
    required_boolean_fields = {
        "disabledProfilesSkipped",
        "sameModelFallbackRejected",
        "fallbackRequiresAlternateEnabledProfile",
        "regionRetentionBoundaryRequired",
        "postToolFallbackRequiresPersistedState",
    }
    allowed_policy_fields = (
        set(required_text_fields)
        | required_boolean_fields
        | {
            "fallbackMetadata",
            "retryComposition",
        }
    )
    if set(policy_mapping) != allowed_policy_fields:
        return "provider fallback policy contract missing"
    for field_name, expected_value in required_text_fields.items():
        if policy_mapping.get(field_name) != expected_value:
            return "provider fallback policy contract missing"
    required_metadata = {
        "from_provider",
        "from_model",
        "to_provider",
        "to_model",
        "reason",
        "latency_ms",
        "cost_usd",
    }
    if not exact_string_set(policy_mapping.get("fallbackMetadata"), required_metadata):
        return "provider fallback policy contract missing"
    for field_name in required_boolean_fields:
        if policy_mapping.get(field_name) is not True:
            return "provider fallback policy contract missing"
    retry_composition = policy_mapping.get("retryComposition")
    if not isinstance(retry_composition, Mapping):
        return "provider fallback policy contract missing"
    retry_composition_mapping = cast(Mapping[str, object], retry_composition)
    if set(retry_composition_mapping) != {
        "middlewareOrder",
        "firstMiddlewareOutermost",
        "retryScope",
        "primaryExcludedFromFallbackModels",
        "verificationSensors",
    }:
        return "provider fallback policy contract missing"
    if retry_composition_mapping.get("middlewareOrder") != [
        "ModelFallbackMiddleware",
        "ModelRetryMiddleware",
    ]:
        return "provider fallback policy contract missing"
    if retry_composition_mapping.get("firstMiddlewareOutermost") is not True:
        return "provider fallback policy contract missing"
    if retry_composition_mapping.get("retryScope") != "per_model_before_fallback":
        return "provider fallback policy contract missing"
    if retry_composition_mapping.get("primaryExcludedFromFallbackModels") is not True:
        return "provider fallback policy contract missing"
    if retry_composition_mapping.get("verificationSensors") != [
        "tests/unit/test_langchain_middleware.py::"
        "test_model_retry_is_exhausted_per_model_before_fallback",
        "tests/unit/test_langchain_agent.py::"
        "test_resolve_langchain_agent_models_rejects_primary_as_fallback",
    ]:
        return "provider fallback policy contract missing"
    return None


def langgraph_fault_tolerance_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    policy = item.get("langgraphFaultTolerance")
    if not isinstance(policy, Mapping):
        return "langgraph fault tolerance contract missing"
    policy_mapping = cast(Mapping[str, object], policy)
    allowed_policy_fields = {
        "status",
        "runtime",
        "loopExitBudget",
        "runnableConfigTraceIdentity",
        "nodeDefaults",
        "cacheSerialization",
        "errorHandling",
        "resumeSemantics",
    }
    if set(policy_mapping) != allowed_policy_fields:
        return "langgraph fault tolerance contract missing"
    if policy_mapping.get("status") != "verified":
        return "langgraph fault tolerance contract missing"
    if policy_mapping.get("runtime") != "langgraph":
        return "langgraph fault tolerance contract missing"

    loop_exit_budget = policy_mapping.get("loopExitBudget")
    if not isinstance(loop_exit_budget, Mapping):
        return "langgraph fault tolerance contract missing"
    loop_exit_budget_mapping = cast(Mapping[str, object], loop_exit_budget)
    if set(loop_exit_budget_mapping) != {
        "configKey",
        "defaultLimit",
        "configuredOnDurableInvocations",
        "configuredOnLangChainAgentInvocations",
        "releaseEvidenceRequired",
    }:
        return "langgraph fault tolerance contract missing"
    if loop_exit_budget_mapping.get("configKey") != "recursion_limit":
        return "langgraph fault tolerance contract missing"
    default_limit = loop_exit_budget_mapping.get("defaultLimit")
    if not isinstance(default_limit, int) or isinstance(default_limit, bool) or default_limit <= 0:
        return "langgraph fault tolerance contract missing"
    for field_name in (
        "configuredOnDurableInvocations",
        "configuredOnLangChainAgentInvocations",
        "releaseEvidenceRequired",
    ):
        if loop_exit_budget_mapping.get(field_name) is not True:
            return "langgraph fault tolerance contract missing"

    trace_identity = policy_mapping.get("runnableConfigTraceIdentity")
    if not isinstance(trace_identity, Mapping):
        return "langgraph fault tolerance contract missing"
    trace_identity_mapping = cast(Mapping[str, object], trace_identity)
    if set(trace_identity_mapping) != {
        "runNames",
        "tags",
        "metadata",
        "configuredOnInvokeResumeStream",
        "secretFree",
        "verificationSensors",
    }:
        return "langgraph fault tolerance contract missing"
    if trace_identity_mapping.get("runNames") != {
        "invoke": "reactor.langgraph.invoke",
        "resume": "reactor.langgraph.resume",
        "stream": "reactor.langgraph.stream",
    }:
        return "langgraph fault tolerance contract missing"
    if not same_string_sequence(
        trace_identity_mapping.get("tags"),
        ["reactor", "runtime:langgraph"],
    ):
        return "langgraph fault tolerance contract missing"
    if trace_identity_mapping.get("metadata") != {"reactor.runtime": "langgraph"}:
        return "langgraph fault tolerance contract missing"
    if trace_identity_mapping.get("configuredOnInvokeResumeStream") is not True:
        return "langgraph fault tolerance contract missing"
    if trace_identity_mapping.get("secretFree") is not True:
        return "langgraph fault tolerance contract missing"
    if not same_string_sequence(
        trace_identity_mapping.get("verificationSensors"),
        [
            (
                "uv run pytest tests/unit/test_langchain_agent.py -q "
                "-k runner_invokes_langgraph_with_versioned_state_and_durable_config"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k 'publishes_resume_lifecycle_event_after_durable_event or "
                "streams_langgraph_events_and_records_them'"
            ),
        ],
    ):
        return "langgraph fault tolerance contract missing"

    node_defaults = policy_mapping.get("nodeDefaults")
    if not isinstance(node_defaults, Mapping):
        return "langgraph fault tolerance contract missing"
    node_defaults_mapping = cast(Mapping[str, object], node_defaults)
    if set(node_defaults_mapping) != {"retryPolicy", "cachePolicy", "timeoutSeconds"}:
        return "langgraph fault tolerance contract missing"
    required_node_defaults = {
        "retryPolicy": "graph_node_retry_policy",
        "cachePolicy": "disabled_for_side_effect_nodes",
    }
    for field_name, expected_value in required_node_defaults.items():
        if node_defaults_mapping.get(field_name) != expected_value:
            return "langgraph fault tolerance contract missing"
    timeout_seconds = node_defaults_mapping.get("timeoutSeconds")
    if (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or timeout_seconds <= 0
    ):
        return "langgraph fault tolerance contract missing"

    cache_serialization = policy_mapping.get("cacheSerialization")
    if not isinstance(cache_serialization, Mapping):
        return "langgraph fault tolerance contract missing"
    cache_serialization_mapping = cast(Mapping[str, object], cache_serialization)
    if set(cache_serialization_mapping) != {
        "langgraphDefaultKeyFuncUsesPickle",
        "customKeyFuncRequired",
        "pickleFallbackEnabled",
        "sideEffectNodeCacheEnabled",
    }:
        return "langgraph fault tolerance contract missing"
    if cache_serialization_mapping.get("langgraphDefaultKeyFuncUsesPickle") is not True:
        return "langgraph fault tolerance contract missing"
    if cache_serialization_mapping.get("customKeyFuncRequired") is not True:
        return "langgraph fault tolerance contract missing"
    if cache_serialization_mapping.get("pickleFallbackEnabled") is not False:
        return "langgraph fault tolerance contract missing"
    if cache_serialization_mapping.get("sideEffectNodeCacheEnabled") is not False:
        return "langgraph fault tolerance contract missing"

    error_handling = policy_mapping.get("errorHandling")
    if not isinstance(error_handling, Mapping):
        return "langgraph fault tolerance contract missing"
    error_handling_mapping = cast(Mapping[str, object], error_handling)
    if set(error_handling_mapping) != {
        "guardFailuresFailClosed",
        "toolFailuresBecomeToolMessages",
        "nonIdempotentEffectsBehindOutbox",
        "interruptsBypassErrorHandlers",
        "externalCancellationPropagates",
        "invokeStartCommitCancellationPersistsTerminalState",
        "streamStartCommitCancellationPersistsTerminalState",
        "langgraphResumeRuntimeCancellationPersistsTerminalState",
        "langchainResumeRuntimeCancellationPersistsTerminalState",
        "langgraphResumeClaimCommitCancellationPersistsTerminalState",
        "langchainResumeClaimCommitCancellationPersistsTerminalState",
        "langgraphResumeApprovalCancellationPersistsTerminalState",
        "langchainResumeApprovalCancellationPersistsTerminalState",
        "langgraphResumeResponseFilteringCancellationPersistsTerminalState",
        "langgraphResumeResponseFilteringFailureFailsOpenSafely",
        "langchainResumeResponseFilteringCancellationPersistsTerminalState",
        "langgraphResumeCompletionPersistenceCancellationResolvesTerminalState",
        "langchainResumeCompletionPersistenceCancellationResolvesTerminalState",
        "resumeCompletionCommitCancellationPreservesTerminalState",
        "runtimeExecutionCancellationPersistsTerminalState",
        "invokeRuntimeExecutionCancellationPersistsTerminalState",
        "invokeToolPreflightCancellationPersistsTerminalState",
        "invokeCheckpointReplayCancellationPersistsTerminalState",
        "invokeMiddlewarePreflightCancellationPersistsTerminalState",
        "checkpointReadCancellationPersistsTerminalState",
        "invokeCheckpointReadCancellationPersistsTerminalState",
        "resumeCheckpointReadCancellationPersistsTerminalState",
        "approvalPersistenceCancellationPersistsTerminalState",
        "invokeApprovalPersistenceCancellationPersistsTerminalState",
        "responseFilteringCancellationPersistsTerminalState",
        "invokeResponseFilteringCancellationPersistsTerminalState",
        "cancellationPersistencePreservesTerminalState",
        "completionPersistenceCancellationResolvesTerminalState",
        "invokeCompletionPersistenceCancellationResolvesTerminalState",
        "tokenEventPersistenceCancellationPersistsTerminalState",
        "approvalEventPersistenceCancellationPersistsTerminalState",
        "streamCloseAfterStartedPersistsTerminalState",
        "streamCloseAfterFinalTokenPersistsTerminalState",
        "streamCloseAfterApprovalPersistsTerminalState",
        "explicitRunCancellationUsesAtomicTransition",
        "explicitRunCancellationAllowsInterrupted",
        "timeoutCancelsUnderlyingExecution",
        "invokeRuntimeParity",
        "streamRuntimeParity",
        "verificationSensors",
    }:
        return "langgraph fault tolerance contract missing"
    for field_name in (
        "guardFailuresFailClosed",
        "toolFailuresBecomeToolMessages",
        "nonIdempotentEffectsBehindOutbox",
        "interruptsBypassErrorHandlers",
        "externalCancellationPropagates",
        "invokeStartCommitCancellationPersistsTerminalState",
        "streamStartCommitCancellationPersistsTerminalState",
        "langgraphResumeRuntimeCancellationPersistsTerminalState",
        "langchainResumeRuntimeCancellationPersistsTerminalState",
        "langgraphResumeClaimCommitCancellationPersistsTerminalState",
        "langchainResumeClaimCommitCancellationPersistsTerminalState",
        "langgraphResumeApprovalCancellationPersistsTerminalState",
        "langchainResumeApprovalCancellationPersistsTerminalState",
        "langgraphResumeResponseFilteringCancellationPersistsTerminalState",
        "langgraphResumeResponseFilteringFailureFailsOpenSafely",
        "langchainResumeResponseFilteringCancellationPersistsTerminalState",
        "langgraphResumeCompletionPersistenceCancellationResolvesTerminalState",
        "langchainResumeCompletionPersistenceCancellationResolvesTerminalState",
        "resumeCompletionCommitCancellationPreservesTerminalState",
        "runtimeExecutionCancellationPersistsTerminalState",
        "invokeRuntimeExecutionCancellationPersistsTerminalState",
        "invokeToolPreflightCancellationPersistsTerminalState",
        "invokeCheckpointReplayCancellationPersistsTerminalState",
        "invokeMiddlewarePreflightCancellationPersistsTerminalState",
        "checkpointReadCancellationPersistsTerminalState",
        "invokeCheckpointReadCancellationPersistsTerminalState",
        "resumeCheckpointReadCancellationPersistsTerminalState",
        "approvalPersistenceCancellationPersistsTerminalState",
        "invokeApprovalPersistenceCancellationPersistsTerminalState",
        "responseFilteringCancellationPersistsTerminalState",
        "invokeResponseFilteringCancellationPersistsTerminalState",
        "cancellationPersistencePreservesTerminalState",
        "completionPersistenceCancellationResolvesTerminalState",
        "invokeCompletionPersistenceCancellationResolvesTerminalState",
        "tokenEventPersistenceCancellationPersistsTerminalState",
        "approvalEventPersistenceCancellationPersistsTerminalState",
        "streamCloseAfterStartedPersistsTerminalState",
        "streamCloseAfterFinalTokenPersistsTerminalState",
        "streamCloseAfterApprovalPersistsTerminalState",
        "explicitRunCancellationUsesAtomicTransition",
        "explicitRunCancellationAllowsInterrupted",
        "timeoutCancelsUnderlyingExecution",
        "invokeRuntimeParity",
        "streamRuntimeParity",
    ):
        if error_handling_mapping.get(field_name) is not True:
            return "langgraph fault tolerance contract missing"
    if not same_string_sequence(
        error_handling_mapping.get("verificationSensors"),
        [
            (
                "uv run pytest tests/unit/test_langchain_agent.py -q "
                "-k propagates_external_cancellation_to_native_and_langchain_invocations"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k stream_timeout_cancels_native_and_langchain_generators"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k start_commit_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k resume_runtime_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k resume_claim_commit_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k resume_approval_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k resume_response_filter_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k langgraph_resume_response_filter_failure_logs_safely_and_completes"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k resume_completion_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k resume_completion_commit_cancellation_preserves_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k runtime_execution_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k create_run_runtime_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k create_run_tool_preflight_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k create_run_checkpoint_replay_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k create_run_middleware_preflight_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k checkpoint_read_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k create_run_checkpoint_read_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k resume_checkpoint_read_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k stream_approval_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k response_filter_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k create_run_response_filter_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_store.py -q "
                "-k 'cancel_running_run_query_is_tenant_scoped_and_atomic or "
                "record_cancelled_if_running or "
                "complete_running_run_query_is_tenant_scoped_and_atomic or "
                "record_completed_preserves_existing_terminal_state'"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k external_cancellation_does_not_overwrite_terminal_result"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k 'completion_persistence_cancellation_records_cancelled or "
                "completion_commit_cancellation_preserves_completed or "
                "late_completion_rejection_suppresses_phantom_completion or "
                "late_completion_rejection_returns_cancelled_result or "
                "run_service_resume_completion_rejection_returns_cancelled_without_events or "
                "langchain_resume_completion_rejection_returns_cancelled_without_events or "
                "unknown_runtime_rejection_losing_to_cancellation_returns_cancelled or "
                "checkpoint_preflight_failure_losing_to_cancellation_returns_cancelled or "
                "stream_runtime_rejection_losing_to_cancellation_suppresses_completion or "
                "streaming_capability_rejection_losing_to_cancellation_"
                "suppresses_completion or "
                "research_preflight_rejection_losing_to_cancellation_returns_cancelled or "
                "stream_research_rejection_losing_to_cancellation_suppresses_completion'"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k 'create_run_completion_persistence_cancellation_records_cancelled or "
                "create_run_completion_commit_cancellation_preserves_completed'"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k token_event_persistence_cancellation_records_cancelled"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k approval_event_persistence_cancellation_records_cancelled"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k close_after_started_event_records_cancelled"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k close_after_final_token_records_cancelled"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q "
                "-k close_after_approval_event_records_cancelled"
            ),
            (
                "uv run pytest tests/integration/test_api.py -q "
                "-k 'run_cancel_endpoint_marks_run_cancelled or "
                "run_cancel_endpoint_rejects_existing_terminal_run'"
            ),
        ],
    ):
        return "langgraph fault tolerance contract missing"

    resume_semantics = policy_mapping.get("resumeSemantics")
    if not isinstance(resume_semantics, Mapping):
        return "langgraph fault tolerance contract missing"
    resume_semantics_mapping = cast(Mapping[str, object], resume_semantics)
    if set(resume_semantics_mapping) != {
        "threadIdRequired",
        "checkpointNsRequired",
        "trustedCheckpointIdOnly",
        "stateHistoryAuditable",
        "interruptedNodeRerunsFromStart",
        "preInterruptSideEffectsForbidden",
        "preInterruptSideEffectsRequireIdempotency",
    }:
        return "langgraph fault tolerance contract missing"
    for field_name in (
        "threadIdRequired",
        "checkpointNsRequired",
        "trustedCheckpointIdOnly",
        "stateHistoryAuditable",
        "interruptedNodeRerunsFromStart",
        "preInterruptSideEffectsForbidden",
        "preInterruptSideEffectsRequireIdempotency",
    ):
        if resume_semantics_mapping.get(field_name) is not True:
            return "langgraph fault tolerance contract missing"
    return None


def checkpoint_retention_policy_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    policy = item.get("checkpointRetentionPolicy")
    if not isinstance(policy, Mapping):
        return "checkpoint retention policy contract missing"
    policy_mapping = cast(Mapping[str, object], policy)
    required_text_fields = {
        "status": "verified",
        "runtime": "langgraph",
        "store": "AsyncPostgresSaver",
        "policyOwner": "reactor.persistence",
        "auditSurface": "retention_policy_api",
    }
    required_boolean_fields = {
        "missingDatabaseFailsClosed",
        "tenantScopedDeletion",
        "exportBeforeDeleteSupported",
        "stateHistoryRetentionAligned",
        "forkProvenanceRetained",
        "checkpointMetadataRedacted",
    }
    allowed_policy_fields = (
        set(required_text_fields)
        | required_boolean_fields
        | {"graphStoreRuntime", "retentionSettings", "verificationSensors"}
    )
    if set(policy_mapping) != allowed_policy_fields:
        return "checkpoint retention policy contract missing"
    for field_name, expected_value in required_text_fields.items():
        if policy_mapping.get(field_name) != expected_value:
            return "checkpoint retention policy contract missing"

    graph_store_runtime = policy_mapping.get("graphStoreRuntime")
    if not isinstance(graph_store_runtime, Mapping):
        return "checkpoint retention policy contract missing"
    graph_store_runtime_mapping = cast(Mapping[str, object], graph_store_runtime)
    required_graph_store_fields = {
        "durableStore": "AsyncPostgresStore",
        "localStore": "InMemoryStore",
        "schemaOwner": "alembic",
        "checkpointMigrationRevision": "202606260001",
        "graphStoreMigrationRevision": "202607230002",
    }
    required_graph_store_boolean_fields = {
        "durableDeploymentsRequirePostgres",
        "localStoreNonDurableOnly",
        "sameStorePassedToLangChainCreateAgent",
        "runtimeSchemaSetupForbidden",
        "existingSchemaAdoptionIdempotent",
        "frameworkMigrationVersionSensor",
        "startupFailureClosesDurableResources",
        "blankDatabaseUrlFailsBeforeEngineCreation",
        "runCheckpointIdentityPersisted",
        "durableCompletedStreamsRequireCheckpointProvenance",
        "durableCompletedInvocationsRequireCheckpointProvenance",
        "durableCompletedResumesRequireCheckpointProvenance",
        "resumePinsPersistedCheckpoint",
        "missingCheckpointIdentityBlocksResume",
        "checkpointVerifiedBeforeApproval",
    }
    if set(graph_store_runtime_mapping) != (
        set(required_graph_store_fields) | required_graph_store_boolean_fields
    ):
        return "checkpoint retention policy contract missing"
    for field_name, expected_value in required_graph_store_fields.items():
        if graph_store_runtime_mapping.get(field_name) != expected_value:
            return "checkpoint retention policy contract missing"
    for field_name in required_graph_store_boolean_fields:
        if graph_store_runtime_mapping.get(field_name) is not True:
            return "checkpoint retention policy contract missing"

    required_settings = {
        "retention.session.days",
        "retention.conversation.days",
        "retention.audit.days",
        "retention.metric.days",
        "retention.checkpoint.days",
    }
    if not exact_string_set(policy_mapping.get("retentionSettings"), required_settings):
        return "checkpoint retention policy contract missing"
    if not same_string_sequence(
        policy_mapping.get("verificationSensors"),
        [
            "uv run pytest tests/unit/test_container.py -q -k open_container",
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "'checkpoint_namespace or persisted_checkpoint_id or "
                "persisted_runtime_owner or durable_approval or "
                "durable_checkpoint'"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "resume_fails_closed_without_required_completed_checkpoint"
            ),
        ],
    ):
        return "checkpoint retention policy contract missing"

    for field_name in required_boolean_fields:
        if policy_mapping.get(field_name) is not True:
            return "checkpoint retention policy contract missing"
    return None


def streaming_event_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    contract = item.get("streamingEventContract")
    if not isinstance(contract, Mapping):
        return "streaming event contract missing"
    contract_mapping = cast(Mapping[str, object], contract)
    required_text_fields = {
        "status": "verified",
        "runtime": "langgraph",
        "api": "astream_events",
        "version": LANGCHAIN_RAW_STREAM_EVENTS_VERSION,
        "replayFilter": "run.stream.",
    }
    required_boolean_fields = {
        "sequenceMonotonic",
        "persistedReplay",
        "graphNodeRequired",
        "traceIdRequired",
        "tenantScopedPersistence",
    }
    allowed_contract_fields = (
        set(required_text_fields)
        | required_boolean_fields
        | {
            "eventTypes",
            "upstreamEventFields",
            "requiredPayloadFields",
            "langchainAgentInvoke",
            "langchainAgentStreaming",
            "interruptLineage",
            "publicPayloadRedaction",
            "terminalNextActions",
            "recommendedInterruptStreaming",
        }
    )
    if set(contract_mapping) != allowed_contract_fields:
        return "streaming event contract missing"
    for field_name, expected_value in required_text_fields.items():
        if contract_mapping.get(field_name) != expected_value:
            return "streaming event contract missing"

    if not exact_string_set(
        contract_mapping.get("eventTypes"),
        {
            "run.stream.started",
            "run.stream.token",
            "run.stream.tool",
            "run.stream.approval",
            "run.stream.completed",
        },
    ):
        return "streaming event contract missing"

    if not exact_string_set(
        contract_mapping.get("upstreamEventFields"),
        {"event", "name", "run_id", "parent_ids", "tags", "metadata", "data"},
    ):
        return "streaming event contract missing"

    if not exact_string_set(
        contract_mapping.get("requiredPayloadFields"),
        {"run_id", "sequence", "graph_node", "trace_id"},
    ):
        return "streaming event contract missing"

    for field_name in required_boolean_fields:
        if contract_mapping.get(field_name) is not True:
            return "streaming event contract missing"

    langchain_agent_invoke = contract_mapping.get("langchainAgentInvoke")
    if not isinstance(langchain_agent_invoke, Mapping):
        return "streaming event contract missing"
    invoke_mapping = cast(Mapping[str, object], langchain_agent_invoke)
    expected_invoke_fields = {
        "api": "ainvoke",
        "version": LANGCHAIN_AGENT_INVOKE_VERSION,
        "output": "GraphOutput",
        "interruptStatus": "interrupted",
    }
    if set(invoke_mapping) != (
        set(expected_invoke_fields) | {"rawInterruptPayloadExcluded", "publicMetadata"}
    ):
        return "streaming event contract missing"
    for invoke_field_name, invoke_expected_value in expected_invoke_fields.items():
        if invoke_mapping.get(invoke_field_name) != invoke_expected_value:
            return "streaming event contract missing"
    if invoke_mapping.get("rawInterruptPayloadExcluded") is not True:
        return "streaming event contract missing"
    if not exact_string_set(
        invoke_mapping.get("publicMetadata"),
        {"approval_status", "stop_reason"},
    ):
        return "streaming event contract missing"

    langchain_agent_streaming = contract_mapping.get("langchainAgentStreaming")
    if not isinstance(langchain_agent_streaming, Mapping):
        return "streaming event contract missing"
    agent_streaming_mapping = cast(Mapping[str, object], langchain_agent_streaming)
    expected_agent_streaming_fields = {
        "api": "astream_events",
        "version": LANGCHAIN_AGENT_STREAM_EVENTS_VERSION,
        "surface": "async_iterator",
        "interruptStatus": "interrupted",
        "publicEventType": "run.stream.approval",
    }
    expected_agent_streaming_boolean_fields = {
        "rawInterruptPayloadExcluded",
        "durableApprovalPersisted",
        "toolInputStoredOnlyInApprovalRow",
        "persistedApprovalIdReplayable",
        "approvalToolInputExcludedFromReplay",
    }
    if set(agent_streaming_mapping) != (
        set(expected_agent_streaming_fields)
        | expected_agent_streaming_boolean_fields
        | {"publicPayloadFields"}
    ):
        return "streaming event contract missing"
    for field_name, expected_value in expected_agent_streaming_fields.items():
        if agent_streaming_mapping.get(field_name) != expected_value:
            return "streaming event contract missing"
    if not exact_string_set(
        agent_streaming_mapping.get("publicPayloadFields"),
        {"approval_status", "action_count", "approval_id"},
    ):
        return "streaming event contract missing"
    for field_name in expected_agent_streaming_boolean_fields:
        if agent_streaming_mapping.get(field_name) is not True:
            return "streaming event contract missing"

    interrupt_lineage = contract_mapping.get("interruptLineage")
    if not isinstance(interrupt_lineage, Mapping):
        return "streaming event contract missing"
    interrupt_lineage_mapping = cast(Mapping[str, object], interrupt_lineage)
    expected_interrupt_lineage_fields = {
        "status": "enforced",
        "event": "on_chain_stream",
        "version": LANGGRAPH_INTERRUPT_STREAM_EVENTS_VERSION,
        "requiredParentIds": "empty",
    }
    expected_interrupt_lineage_boolean_fields = {
        "rootFramesOnly",
        "missingMalformedNestedFailClosed",
        "malformedRootPayloadFailsClosed",
        "invalidPayloadCannotEmitTokens",
        "singleApprovalActionRequired",
        "invalidActionsFailBeforeApprovalPersistence",
        "invalidActionsCannotEmitTokens",
        "invokeInvalidActionsFailClosed",
        "invokeInvalidActionStatusFailed",
        "invokeStreamInvalidActionParity",
        "invalidInvokeActionSkipsCheckpointRead",
        "nonRecoverableStreamsSkipCheckpointRead",
        "nonRecoverableInvocationsSkipCheckpointRead",
        "nestedInterruptCannotPersistApproval",
        "interruptPayloadOnlyApprovalSource",
        "pendingStateChunksIgnored",
        "verifiedInterruptCannotBeOverridden",
        "identicalInterruptFramesIdempotent",
        "conflictingInterruptFramesFailClosed",
        "conflictingInterruptApprovalPersistenceBlocked",
    }
    if set(interrupt_lineage_mapping) != (
        set(expected_interrupt_lineage_fields)
        | expected_interrupt_lineage_boolean_fields
        | {
            "runtimes",
            "verificationSensors",
            "conflictStopReason",
            "invalidLineageStopReason",
            "invalidPayloadStopReason",
            "invalidActionStopReason",
        }
    ):
        return "streaming event contract missing"
    for field_name, expected_value in expected_interrupt_lineage_fields.items():
        if interrupt_lineage_mapping.get(field_name) != expected_value:
            return "streaming event contract missing"
    for field_name in expected_interrupt_lineage_boolean_fields:
        if interrupt_lineage_mapping.get(field_name) is not True:
            return "streaming event contract missing"
    if interrupt_lineage_mapping.get("conflictStopReason") != "interrupt_stream_conflict":
        return "streaming event contract missing"
    if (
        interrupt_lineage_mapping.get("invalidLineageStopReason")
        != "interrupt_stream_lineage_invalid"
    ):
        return "streaming event contract missing"
    if (
        interrupt_lineage_mapping.get("invalidPayloadStopReason")
        != "interrupt_stream_payload_invalid"
    ):
        return "streaming event contract missing"
    if (
        interrupt_lineage_mapping.get("invalidActionStopReason")
        != "interrupt_stream_action_invalid"
    ):
        return "streaming event contract missing"
    if not exact_string_set(
        interrupt_lineage_mapping.get("runtimes"),
        {"langgraph", "langchain_agent"},
    ):
        return "streaming event contract missing"
    if not same_string_sequence(
        interrupt_lineage_mapping.get("verificationSensors"),
        [
            (
                "uv run pytest tests/unit/test_langchain_agent.py "
                "tests/unit/test_run_service.py "
                "tests/integration/test_agent_streaming.py -q -k "
                "'real_create_agent_v2_stream_exposes_interrupt_without_executing_tool or "
                "run_langchain_agent_once_fails_closed_on_invalid_interrupt_actions or "
                "stream_interrupts_requires_root_stream_lineage or "
                "stream_fails_closed_on_invalid_langchain_v2_interrupt_lineage or "
                "stream_fails_closed_on_malformed_root_interrupt_payload or "
                "stream_fails_closed_on_invalid_interrupt_actions or "
                "stream_persists_redacted_langchain_v2_interrupt or "
                "stream_projection_ignores_pending_approval_without_interrupt or "
                "stream_persists_redacted_native_langgraph_interrupt or "
                "stream_fails_closed_on_conflicting_root_interrupts or "
                "native_stream_fails_closed_on_conflicting_root_interrupts'"
            )
        ],
    ):
        return "streaming event contract missing"

    public_payload_redaction = contract_mapping.get("publicPayloadRedaction")
    if not isinstance(public_payload_redaction, Mapping):
        return "streaming event contract missing"
    redaction_mapping = cast(Mapping[str, object], public_payload_redaction)
    expected_redaction_text_fields = {
        "apiBoundary": "public_run_event_payload",
        "cliBoundary": "stream_event_summary",
        "redactionFunction": "redact_trace_payload",
    }
    expected_redaction_boolean_fields = {
        "secretShapedValuesRedacted",
        "sensitiveKeysDropped",
        "toolResultsSanitized",
        "rawPayloadsExcluded",
    }
    if set(redaction_mapping) != (
        set(expected_redaction_text_fields) | expected_redaction_boolean_fields | {"apiEndpoints"}
    ):
        return "streaming event contract missing"
    for field_name, expected_value in expected_redaction_text_fields.items():
        if redaction_mapping.get(field_name) != expected_value:
            return "streaming event contract missing"
    if not exact_string_set(
        redaction_mapping.get("apiEndpoints"),
        {"GET /v1/runs/{run_id}/events", "GET /v1/runs/{run_id}/stream-events"},
    ):
        return "streaming event contract missing"
    for field_name in expected_redaction_boolean_fields:
        if redaction_mapping.get(field_name) is not True:
            return "streaming event contract missing"

    terminal_next_actions = contract_mapping.get("terminalNextActions")
    if not isinstance(terminal_next_actions, Mapping):
        return "streaming event contract missing"
    terminal_actions_mapping = cast(Mapping[str, object], terminal_next_actions)
    if set(terminal_actions_mapping) != {
        "includedInCompletedPayload",
        "actionIds",
        "commands",
        "identityFields",
        "runtimePayloadVerified",
    }:
        return "streaming event contract missing"
    if terminal_actions_mapping.get("includedInCompletedPayload") is not True:
        return "streaming event contract missing"
    if terminal_actions_mapping.get("runtimePayloadVerified") is not True:
        return "streaming event contract missing"
    if not exact_string_set(
        terminal_actions_mapping.get("actionIds"),
        {"diagnose-run", "inspect-state-history", "replay-stream", "fork-checkpoint"},
    ):
        return "streaming event contract missing"
    if not exact_string_set(
        terminal_actions_mapping.get("commands"),
        {
            "reactor-runs diagnose '{run_id}' --output table",
            "reactor-admin state-history '{run_id}' --output table",
            "reactor-runs replay '{run_id}' --output table",
            (
                "reactor-runs fork {run_id} --checkpoint-ns {checkpoint_ns} "
                "--checkpoint-id {checkpoint_id} --output table"
            ),
        },
    ):
        return "streaming event contract missing"
    if not exact_string_set(
        terminal_actions_mapping.get("identityFields"),
        {"sourceRunId", "threadId", "checkpointNs"},
    ):
        return "streaming event contract missing"

    recommended_interrupt_streaming = contract_mapping.get("recommendedInterruptStreaming")
    if not isinstance(recommended_interrupt_streaming, Mapping):
        return "streaming event contract missing"
    recommended_mapping = cast(Mapping[str, object], recommended_interrupt_streaming)
    expected_interrupt_fields = {
        "recommendedApi": "stream_events",
        "recommendedAsyncApi": "astream_events",
        "version": LANGGRAPH_INTERRUPT_STREAM_EVENTS_VERSION,
        "resumeCommand": "Command(resume=...)",
    }
    expected_interrupt_boolean_fields = {
        "threadIdRequired",
        "persistentCheckpointerRequired",
        "interruptPayloadsJsonSerializable",
    }
    if set(recommended_mapping) != (
        set(expected_interrupt_fields) | expected_interrupt_boolean_fields | {"projectionFields"}
    ):
        return "streaming event contract missing"
    for field_name, expected_value in expected_interrupt_fields.items():
        if recommended_mapping.get(field_name) != expected_value:
            return "streaming event contract missing"
    if not exact_string_set(
        recommended_mapping.get("projectionFields"),
        {"approval_status", "action_count"},
    ):
        return "streaming event contract missing"
    for field_name in expected_interrupt_boolean_fields:
        if recommended_mapping.get(field_name) is not True:
            return "streaming event contract missing"
    return None


def redis_coordination_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    contract = item.get("redisCoordination")
    if not isinstance(contract, Mapping):
        return "redis coordination contract missing"
    contract_mapping = cast(Mapping[str, object], contract)
    required_text_fields = {
        "status": "verified",
        "client": "redis.asyncio.Redis",
        "healthCheck": "check_redis",
        "primaryCheckpointStoreForbidden": "langgraph-checkpoint-redis",
        "pubsubDelivery": "at_most_once",
        "rateLimitFailureMode": "fail_closed_by_default",
    }
    required_boolean_fields = {
        "productionMultiReplicaRequired",
        "ephemeralOnly",
        "durableStateForbidden",
        "clientClosedAfterPing",
        "runLifecyclePublisherClosedOnContainerClose",
        "slackUserRateLimiterClosedOnContainerClose",
    }
    allowed_contract_fields = set(required_text_fields) | required_boolean_fields | {"allowedUses"}
    if set(contract_mapping) != allowed_contract_fields:
        return "redis coordination contract missing"
    for field_name, expected_value in required_text_fields.items():
        if contract_mapping.get(field_name) != expected_value:
            return "redis coordination contract missing"

    allowed_uses = contract_mapping.get("allowedUses")
    if not exact_string_set(
        allowed_uses,
        {
            "rate_limit_counters",
            "lock_tokens",
            "pubsub_wakeups",
            "ttl_cache_entries",
        },
    ):
        return "redis coordination contract missing"

    for field_name in required_boolean_fields:
        if contract_mapping.get(field_name) is not True:
            return "redis coordination contract missing"
    return None


def observability_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "observability_smoke":
        return None
    sdk_contract = item.get("observabilitySdk")
    if not isinstance(sdk_contract, Mapping):
        return "observability sdk contract missing"
    sdk_contract_mapping = cast(Mapping[str, object], sdk_contract)
    if sdk_contract_mapping.get("status") != "verified":
        return "observability sdk contract missing"
    langsmith = sdk_contract_mapping.get("langsmith")
    if not isinstance(langsmith, Mapping):
        return "observability sdk contract missing"
    langsmith_mapping = cast(Mapping[str, object], langsmith)
    expected_langsmith_fields = {
        "sdk": "langsmith",
        "traceProvider": "langsmith",
        "tracingEnv": "LANGSMITH_TRACING",
        "projectEnv": "LANGSMITH_PROJECT",
    }
    for field_name, expected_value in expected_langsmith_fields.items():
        if langsmith_mapping.get(field_name) != expected_value:
            return "observability sdk contract missing"
    privacy_env = langsmith_mapping.get("privacyEnv")
    if not exact_string_set(
        privacy_env,
        {
            "LANGSMITH_HIDE_INPUTS",
            "LANGSMITH_HIDE_OUTPUTS",
            "LANGSMITH_HIDE_METADATA",
        },
    ):
        return "observability sdk contract missing"
    opentelemetry = sdk_contract_mapping.get("opentelemetry")
    if not isinstance(opentelemetry, Mapping):
        return "observability sdk contract missing"
    opentelemetry_mapping = cast(Mapping[str, object], opentelemetry)
    expected_otel_fields = {
        "sdk": "opentelemetry-sdk",
        "tracerProvider": "TracerProvider",
        "spanProcessor": "BatchSpanProcessor",
        "otlpProtocol": "http/protobuf",
        "sampler": "TraceIdRatioBased",
    }
    for field_name, expected_value in expected_otel_fields.items():
        if opentelemetry_mapping.get(field_name) != expected_value:
            return "observability sdk contract missing"
    for field_name in ("providerShutdownOnLifespanExit", "forceFlushBeforeShutdown"):
        if opentelemetry_mapping.get(field_name) is not True:
            return "observability sdk contract missing"
    exporters = opentelemetry_mapping.get("exporters")
    if not exact_string_set(exporters, {"ConsoleSpanExporter", "OTLPSpanExporter"}):
        return "observability sdk contract missing"
    resource_attributes = opentelemetry_mapping.get("resourceAttributes")
    if not exact_string_set(resource_attributes, {"service.name", "deployment.environment"}):
        return "observability sdk contract missing"
    target = item.get("observabilityTarget")
    if not isinstance(target, Mapping) or target.get("secretFree") is not True:
        return "observability target contract missing"
    target_mapping = cast(Mapping[str, object], target)
    if observability_target_has_secret(target_mapping):
        return "observability target contract missing"
    for field_name in ("traceProvider", "project", "endpoint", "spanName"):
        field_value = target_mapping.get(field_name)
        if not isinstance(field_value, str) or not field_value.strip():
            return "observability target contract missing"
    privacy = item.get("privacy")
    if not isinstance(privacy, Mapping):
        return "observability privacy contract missing"
    if (
        privacy.get("hideInputs") is not True
        or privacy.get("hideOutputs") is not True
        or privacy.get("hideMetadata") is not True
        or privacy.get("redactionCheck") != "required"
    ):
        return "observability privacy contract missing"
    redaction_coverage = cast(object, privacy.get("redactionCoverage"))
    if not isinstance(redaction_coverage, Sequence) or isinstance(
        redaction_coverage, str | bytes | bytearray
    ):
        return "observability privacy contract missing"
    if not redaction_coverage:
        return "observability privacy contract missing"
    for coverage_item in cast(Sequence[object], redaction_coverage):
        if not isinstance(coverage_item, str) or not coverage_item.strip():
            return "observability privacy contract missing"
    if not exact_string_set(
        cast(object, redaction_coverage), set(REQUIRED_OBSERVABILITY_REDACTION_COVERAGE)
    ):
        return "observability privacy contract missing"
    failure_log_coverage = cast(object, privacy.get("failureLogCoverage"))
    if failure_log_coverage is not None:
        if not isinstance(failure_log_coverage, Mapping):
            return "observability privacy contract missing"
        failure_log_mapping = cast(Mapping[str, object], failure_log_coverage)
        if (
            failure_log_mapping.get("alertDispatchFailureFailsOpen") is not True
            or failure_log_mapping.get("exceptionDetailsExcluded") is not True
            or not exact_string_set(
                failure_log_mapping.get("safeIdentityFields"),
                {"alert_id", "rule_id"},
            )
            or failure_log_mapping.get("verificationSensor")
            != (
                "uv run pytest tests/unit/test_slo_alerts.py -q -k "
                "keeps_alert_and_logs_safely_when_dispatch_fails"
            )
        ):
            return "observability privacy contract missing"
    feedback_loop = item.get("feedbackLoop")
    if not isinstance(feedback_loop, Mapping):
        return "observability feedback loop contract missing"
    feedback_loop_mapping = cast(Mapping[str, object], feedback_loop)
    required_feedback_loop = {
        "onlineSignal": "langsmith_traces_and_feedback",
        "offlineGate": "langsmith_eval_dataset_sync",
        "sourceSuite": "evals/agent-hardening.json",
        "promotionRule": "online_findings_become_offline_eval_cases",
    }
    for field_name, expected_value in required_feedback_loop.items():
        if feedback_loop_mapping.get(field_name) != expected_value:
            return "observability feedback loop contract missing"
    promoted_case_ids = feedback_loop_mapping.get("promotedCaseIds")
    if not non_empty_string_sequence(promoted_case_ids):
        return "observability feedback loop contract missing"
    typed_promoted_case_ids = cast(Sequence[str], promoted_case_ids)
    if len(set(typed_promoted_case_ids)) != len(typed_promoted_case_ids):
        return "observability feedback loop contract missing"
    return None


def observability_target_has_secret(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    target = cast(Mapping[str, object], value)
    for field_name in ("traceProvider", "project", "endpoint", "spanName"):
        field_value = target.get(field_name)
        if not isinstance(field_value, str):
            continue
        normalized = field_value.lower()
        if any(marker in normalized for marker in SENSITIVE_OBSERVABILITY_TARGET_MARKERS):
            return True
    return False


def graph_topology_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "hardening_suite":
        return None
    topology = item.get("graphTopology")
    if not isinstance(topology, Mapping):
        return "graph topology contract missing"
    topology_mapping = cast(Mapping[str, object], topology)
    if topology_mapping.get("composition") != "stage_subgraphs":
        return "graph topology contract missing"
    stage_order: object = topology_mapping.get("stageOrder")
    node_order: object = topology_mapping.get("nodeOrder")
    subgraph_order: object = topology_mapping.get("subgraphOrder")
    subgraph_edges: object = topology_mapping.get("subgraphEdges")
    subgraphs: object = topology_mapping.get("subgraphs")
    if (
        not non_empty_string_sequence(stage_order)
        or not non_empty_string_sequence(node_order)
        or not non_empty_string_sequence(subgraph_order)
        or not non_empty_mapping_sequence(subgraph_edges)
        or not non_empty_mapping_sequence(subgraphs)
    ):
        return "graph topology contract missing"
    subgraph_mappings = cast(Sequence[Mapping[str, object]], subgraphs)
    for subgraph in subgraph_mappings:
        if graph_subgraph_contract_failure(subgraph):
            return "graph topology contract missing"
    subgraph_names = {cast(str, subgraph["name"]) for subgraph in subgraph_mappings}
    ordered_subgraphs = cast(Sequence[str], subgraph_order)
    if len(ordered_subgraphs) != len(subgraph_names) or subgraph_names != set(ordered_subgraphs):
        return "graph topology contract missing"
    known_edge_endpoints = {"__start__", "__end__", *subgraph_names}
    for edge in cast(Sequence[Mapping[str, object]], subgraph_edges):
        source = edge.get("source")
        target = edge.get("target")
        if (
            not isinstance(source, str)
            or not source.strip()
            or not isinstance(target, str)
            or not target.strip()
            or source not in known_edge_endpoints
            or target not in known_edge_endpoints
        ):
            return "graph topology contract missing"
    if graph_execution_boundary_failure(topology_mapping.get("executionBoundary")):
        return "graph topology contract missing"
    return None


def graph_execution_boundary_failure(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    boundary = cast(Mapping[str, object], value)
    if boundary.get("wrapper") != "JsonSafeReactorGraph":
        return True
    if boundary.get("productionAsyncOnly") is not True:
        return True
    if not exact_string_set(
        boundary.get("allowedApis"),
        {"ainvoke", "astream", "astream_events"},
    ):
        return True
    if not exact_string_set(boundary.get("forbiddenApis"), {"invoke", "stream"}):
        return True
    if boundary.get("verificationSensors") != [
        "uv run pytest tests/unit/test_agent_tool_state.py -q "
        "-k 'rejects_synchronous_invoke or rejects_synchronous_stream'"
    ]:
        return True
    if boundary.get("covers") != ["langgraph_sync_execution_is_blocked_at_graph_boundary"]:
        return True
    return False


def graph_subgraph_contract_failure(subgraph: Mapping[str, object]) -> bool:
    for field_name in ("name", "entryNode", "exitNode", "checkpointMode"):
        field_value = subgraph.get(field_name)
        if not isinstance(field_value, str) or not field_value.strip():
            return True
    nodes_value = subgraph.get("nodes")
    node_count = subgraph.get("nodeCount")
    if not non_empty_string_sequence(nodes_value):
        return True
    nodes = cast(Sequence[object], nodes_value)
    node_names = set(cast(Sequence[str], nodes))
    entry_node = cast(str, subgraph["entryNode"])
    exit_node = cast(str, subgraph["exitNode"])
    return (
        not isinstance(node_count, int)
        or isinstance(node_count, bool)
        or node_count != len(nodes)
        or len(node_names) != len(nodes)
        or entry_node not in node_names
        or exit_node not in node_names
    )


def langsmith_eval_sync_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "langsmith_eval_sync":
        return None
    if item.get("status") != "passed":
        return None
    for field_name in ("datasetName", "sourceSuite"):
        field_value = item.get(field_name)
        if not isinstance(field_value, str) or not field_value.strip():
            return "langsmith eval sync contract missing"
    if item.get("dataType") != "kv":
        return "langsmith eval sync contract missing"
    dataset_metadata = item.get("datasetMetadata")
    if not isinstance(dataset_metadata, Mapping):
        return "langsmith eval sync contract missing"
    dataset_metadata_mapping = cast(Mapping[str, object], dataset_metadata)
    allowed_dataset_metadata_fields = {"source", "kind", "dataType", "sourceSuite"}
    if set(dataset_metadata_mapping) != allowed_dataset_metadata_fields:
        return "langsmith eval sync contract missing"
    if (
        dataset_metadata_mapping.get("source") != "reactor"
        or dataset_metadata_mapping.get("kind") != "agent_eval"
        or dataset_metadata_mapping.get("dataType") != "kv"
        or dataset_metadata_mapping.get("sourceSuite") != item.get("sourceSuite")
    ):
        return "langsmith eval sync contract missing"
    if langsmith_dataset_name_contract_failure(
        dataset_name=cast(str, item["datasetName"]),
        source_suite=cast(str, item["sourceSuite"]),
    ):
        return "langsmith eval sync contract missing"
    if langsmith_readiness_preflight_command_failure(item):
        return "langsmith eval sync contract missing"
    if langsmith_readiness_report_arg_failure(item):
        return "langsmith next action handoff metadata is incomplete"
    if langsmith_readiness_metadata_failure(item):
        return "langsmith eval sync contract missing"
    if langsmith_next_action_handoff_failure(item):
        return "langsmith eval sync contract missing"
    if cast(
        str, item["sourceSuite"]
    ).strip() != RAG_CANDIDATE_SOURCE_SUITE and langsmith_readiness_report_path_failure(item):
        return "langsmith eval sync contract missing"
    example_contract = item.get("exampleContract")
    if not isinstance(example_contract, Mapping):
        return "langsmith eval sync contract missing"
    example_contract_mapping = cast(Mapping[str, object], example_contract)
    allowed_example_contract_fields = {
        "dataType",
        "requiredExampleFields",
        "inputFields",
        "metadataCaseIdField",
        "metadataFields",
        "rawExampleValuesIncluded",
        "citationMarkerContract",
        "secretScan",
    }
    if set(example_contract_mapping) != allowed_example_contract_fields:
        return "langsmith eval sync contract missing"
    if example_contract_mapping.get("dataType") != "kv":
        return "langsmith eval sync contract missing"
    if not exact_string_set(
        example_contract_mapping.get("requiredExampleFields"),
        {
            "id",
            "inputs",
            "outputs",
            "metadata",
            "split",
        },
    ):
        return "langsmith eval sync contract missing"
    if not exact_string_set(example_contract_mapping.get("inputFields"), {"user_input"}):
        return "langsmith eval sync contract missing"
    if example_contract_mapping.get("metadataCaseIdField") != "reactorCaseId":
        return "langsmith eval sync contract missing"
    if not exact_string_set(
        example_contract_mapping.get("metadataFields"),
        {
            "reactorCaseId",
            "tenantId",
            "name",
            "tags",
            "agentType",
            "model",
            "sourceRunId",
            "enabled",
        },
    ):
        return "langsmith eval sync contract missing"
    if example_contract_mapping.get("rawExampleValuesIncluded") is not False:
        return "langsmith eval sync contract missing"
    citation_marker_contract = example_contract_mapping.get("citationMarkerContract")
    if not isinstance(citation_marker_contract, Mapping):
        return "langsmith eval sync contract missing"
    citation_marker_mapping = cast(Mapping[str, object], citation_marker_contract)
    if set(citation_marker_mapping) != {
        "ragExpectedAnswersRequireBracketedMarkers",
        "markerPattern",
        "rawExampleValuesIncluded",
    }:
        return "langsmith eval sync contract missing"
    if (
        citation_marker_mapping.get("ragExpectedAnswersRequireBracketedMarkers") is not True
        or citation_marker_mapping.get("markerPattern") != "[source-label]"
        or citation_marker_mapping.get("rawExampleValuesIncluded") is not False
    ):
        return "langsmith eval sync contract missing"
    secret_scan = example_contract_mapping.get("secretScan")
    if not isinstance(secret_scan, Mapping):
        return "langsmith eval sync contract missing"
    secret_scan_mapping = cast(Mapping[str, object], secret_scan)
    secret_scan_fields = {"enabled", "scansKeys", "scansValues", "beforeCreateExamples"}
    if set(secret_scan_mapping) != secret_scan_fields:
        return "langsmith eval sync contract missing"
    for field_name in secret_scan_fields:
        if secret_scan_mapping.get(field_name) is not True:
            return "langsmith eval sync contract missing"
    sdk_contract = item.get("sdkContract")
    if not isinstance(sdk_contract, Mapping):
        return "langsmith eval sync contract missing"
    sdk_contract_mapping = cast(Mapping[str, object], sdk_contract)
    allowed_sdk_contract_fields = {
        "sdk",
        "client",
        "datasetApi",
        "exampleApi",
        "lookupApi",
        "dataType",
        "maxConcurrency",
        "deterministicExampleIds",
        "sourceControlledCases",
    }
    if set(sdk_contract_mapping) != allowed_sdk_contract_fields:
        return "langsmith eval sync contract missing"
    expected_sdk_fields = {
        "sdk": "langsmith",
        "client": "langsmith.Client",
        "datasetApi": "create_dataset",
        "exampleApi": "create_examples",
        "lookupApi": "has_dataset",
        "dataType": "kv",
    }
    for field_name, expected_value in expected_sdk_fields.items():
        if sdk_contract_mapping.get(field_name) != expected_value:
            return "langsmith eval sync contract missing"
    max_concurrency = sdk_contract_mapping.get("maxConcurrency")
    if not isinstance(max_concurrency, int) or isinstance(max_concurrency, bool):
        return "langsmith eval sync contract missing"
    if max_concurrency != 1:
        return "langsmith eval sync contract missing"
    for field_name in ("deterministicExampleIds", "sourceControlledCases"):
        if sdk_contract_mapping.get(field_name) is not True:
            return "langsmith eval sync contract missing"
    enabled_cases = item.get("enabledCases")
    if not isinstance(enabled_cases, int) or isinstance(enabled_cases, bool) or enabled_cases <= 0:
        return "langsmith eval sync contract missing"
    example_ids = item.get("exampleIds")
    if not non_empty_string_sequence(example_ids):
        return "langsmith eval sync contract missing"
    case_ids = item.get("caseIds")
    if not non_empty_string_sequence(case_ids):
        return "langsmith eval sync contract missing"
    if (
        len(cast(Sequence[str], example_ids)) != enabled_cases
        or len(cast(Sequence[str], case_ids)) != enabled_cases
    ):
        return "langsmith eval sync contract missing"
    if len(set(cast(Sequence[str], example_ids))) != enabled_cases:
        return "langsmith eval sync contract missing"
    case_id_set = set(cast(Sequence[str], case_ids))
    if len(case_id_set) != enabled_cases:
        return "langsmith eval sync contract missing"
    dataset_name = cast(str, item["datasetName"])
    deterministic_example_ids = [
        str(deterministic_langsmith_example_id(dataset_name=dataset_name, case_id=case_id))
        for case_id in cast(Sequence[str], case_ids)
    ]
    if list(cast(Sequence[str], example_ids)) != deterministic_example_ids:
        return "langsmith eval sync contract missing"
    metadata_case_ids = item.get("metadataCaseIds")
    if (
        not non_empty_string_sequence(metadata_case_ids)
        or len(cast(Sequence[str], metadata_case_ids)) != enabled_cases
        or len(set(cast(Sequence[str], metadata_case_ids))) != enabled_cases
        or set(cast(Sequence[str], metadata_case_ids)) != case_id_set
    ):
        return "langsmith eval sync contract missing"
    source_run_ids = item.get("sourceRunIds")
    if (
        not non_empty_string_sequence(source_run_ids)
        or len(cast(Sequence[str], source_run_ids)) != enabled_cases
        or len(set(cast(Sequence[str], source_run_ids))) != enabled_cases
    ):
        return "langsmith eval sync contract missing"
    case_source_run_ids = item.get("caseSourceRunIds")
    if not isinstance(case_source_run_ids, Mapping):
        return "langsmith eval sync contract missing"
    case_source_run_ids_mapping = cast(Mapping[object, object], case_source_run_ids)
    if set(case_source_run_ids_mapping) != case_id_set:
        return "langsmith eval sync contract missing"
    mapped_source_run_ids = {
        source_run_id
        for source_run_id in case_source_run_ids_mapping.values()
        if isinstance(source_run_id, str) and source_run_id.strip()
    }
    if mapped_source_run_ids != set(cast(Sequence[str], source_run_ids)):
        return "langsmith eval sync contract missing"
    split_counts = item.get("splitCounts")
    if not isinstance(split_counts, Mapping):
        return "langsmith eval sync contract missing"
    split_counts_mapping = cast(Mapping[str, object], split_counts)
    if set(split_counts_mapping) != {"regression"}:
        return "langsmith eval sync contract missing"
    regression_count = split_counts_mapping.get("regression")
    if not isinstance(regression_count, int) or isinstance(regression_count, bool):
        return "langsmith eval sync contract missing"
    if regression_count != enabled_cases:
        return "langsmith eval sync contract missing"
    source_suite = cast(str, item["sourceSuite"])
    case_policy = langsmith_case_policy(source_suite=source_suite, case_ids=case_id_set)
    if not case_policy["required"].issubset(case_id_set) or not case_id_set.issubset(
        case_policy["allowed"]
    ):
        return "langsmith eval sync contract missing"
    if source_suite == RAG_CANDIDATE_SOURCE_SUITE and langsmith_rag_candidate_handoff_failure(item):
        return "langsmith eval sync contract missing"
    feedback_promotion = item.get("feedbackPromotion")
    promotion_coverage = item.get("promotionCoverage")
    if feedback_promotion is not None and langsmith_feedback_promotion_contract_failure(
        feedback_promotion=feedback_promotion,
        case_id_set=case_id_set,
        promotion_coverage=promotion_coverage,
    ):
        return "langsmith eval sync contract missing"
    feedback_review_queue = item.get("feedbackReviewQueue")
    reviewed_feedback_promotion = isinstance(
        feedback_promotion, Mapping
    ) and feedback_promotion_review_closed(cast(Mapping[str, object], feedback_promotion))
    if (
        case_policy["feedback_queue"]
        and feedback_review_queue is None
        and not reviewed_feedback_promotion
    ):
        return "langsmith eval sync contract missing"
    if feedback_review_queue is not None and langsmith_feedback_review_queue_contract_failure(
        feedback_review_queue=feedback_review_queue,
        case_id_set=case_id_set,
    ):
        return "langsmith eval sync contract missing"
    if feedback_promotion is not None and promotion_coverage is None:
        return "langsmith eval sync contract missing"
    if promotion_coverage is not None and langsmith_promotion_coverage_contract_failure(
        promotion_coverage=promotion_coverage,
    ):
        return "langsmith eval sync contract missing"
    trace_grading = item.get("traceGrading")
    if not isinstance(trace_grading, Mapping):
        return "langsmith eval sync contract missing"
    trace_grading_mapping = cast(Mapping[str, object], trace_grading)
    allowed_trace_grading_fields = {
        "enabledCases",
        "gradedRuns",
        "passed",
        "failed",
        "caseIds",
        "grades",
    }
    if case_policy["poisoning"]:
        allowed_trace_grading_fields.add("poisoningSafety")
    if set(trace_grading_mapping) != allowed_trace_grading_fields:
        return "langsmith eval sync contract missing"
    trace_enabled_cases = trace_grading_mapping.get("enabledCases")
    if not isinstance(trace_enabled_cases, int) or isinstance(trace_enabled_cases, bool):
        return "langsmith eval sync contract missing"
    if trace_enabled_cases != enabled_cases:
        return "langsmith eval sync contract missing"
    graded_runs = trace_grading_mapping.get("gradedRuns")
    passed = trace_grading_mapping.get("passed")
    failed = trace_grading_mapping.get("failed")
    if (
        not isinstance(graded_runs, int)
        or isinstance(graded_runs, bool)
        or graded_runs <= 0
        or graded_runs != enabled_cases
        or not isinstance(passed, int)
        or isinstance(passed, bool)
        or passed != graded_runs
        or not isinstance(failed, int)
        or isinstance(failed, bool)
        or failed != 0
    ):
        return "langsmith eval sync contract missing"
    trace_case_ids = trace_grading_mapping.get("caseIds")
    if not non_empty_string_sequence(trace_case_ids):
        return "langsmith eval sync contract missing"
    if (
        len(cast(Sequence[str], trace_case_ids)) != enabled_cases
        or len(set(cast(Sequence[str], trace_case_ids))) != enabled_cases
    ):
        return "langsmith eval sync contract missing"
    if set(cast(Sequence[str], trace_case_ids)) != case_id_set:
        return "langsmith eval sync contract missing"
    grades = trace_grading_mapping.get("grades")
    if not non_empty_mapping_sequence(grades):
        return "langsmith eval sync contract missing"
    grade_mappings = cast(Sequence[Mapping[str, object]], grades)
    if len(grade_mappings) != graded_runs:
        return "langsmith eval sync contract missing"
    if langsmith_trace_grade_contract_failure(
        grades=grade_mappings,
        case_id_set=case_id_set,
        required_grounded_case_ids=case_policy["grounded"],
        required_poisoning_case_ids=case_policy["poisoning"],
    ):
        return "langsmith eval sync contract missing"
    poisoning_safety = trace_grading_mapping.get("poisoningSafety")
    if not case_policy["poisoning"]:
        if poisoning_safety is not None:
            return "langsmith eval sync contract missing"
        return None
    if not isinstance(poisoning_safety, Mapping):
        return "langsmith eval sync contract missing"
    poisoning_safety_mapping = cast(Mapping[str, object], poisoning_safety)
    allowed_poisoning_safety_fields = {
        "caseId",
        "runId",
        "poisonedChunks",
        "poisoningReasons",
        "poisonedChunkDocuments",
    }
    if set(poisoning_safety_mapping) != allowed_poisoning_safety_fields:
        return "langsmith eval sync contract missing"
    if poisoning_safety_mapping.get("caseId") not in case_policy["poisoning"]:
        return "langsmith eval sync contract missing"
    poisoning_case_id = cast(str, poisoning_safety_mapping["caseId"])
    run_id = poisoning_safety_mapping.get("runId")
    if not isinstance(run_id, str) or not run_id.strip():
        return "langsmith eval sync contract missing"
    if run_id != langsmith_trace_grade_run_id(
        grades=grade_mappings,
        case_id=poisoning_case_id,
    ):
        return "langsmith eval sync contract missing"
    poisoned_chunks = poisoning_safety_mapping.get("poisonedChunks")
    if (
        not isinstance(poisoned_chunks, int)
        or isinstance(poisoned_chunks, bool)
        or poisoned_chunks <= 0
    ):
        return "langsmith eval sync contract missing"
    poisoning_reasons = poisoning_safety_mapping.get("poisoningReasons")
    if not non_empty_string_sequence(poisoning_reasons):
        return "langsmith eval sync contract missing"
    if any(
        cast(str, reason) not in RAG_POISONING_REASONS
        for reason in cast(Sequence[object], poisoning_reasons)
    ):
        return "langsmith eval sync contract missing"
    poisoned_documents = poisoning_safety_mapping.get("poisonedChunkDocuments")
    if not non_empty_string_sequence(poisoned_documents):
        return "langsmith eval sync contract missing"
    poisoned_document_values = cast(Sequence[str], poisoned_documents)
    if any(not is_citation_safe_id(document) for document in poisoned_document_values):
        return "langsmith eval sync contract missing"
    grade_safety_evidence = langsmith_trace_grade_safety_evidence(
        grades=grade_mappings,
        case_id=poisoning_case_id,
    )
    if grade_safety_evidence is None:
        return "langsmith eval sync contract missing"
    if (
        poisoned_chunks != grade_safety_evidence.get("poisonedChunks")
        or not same_string_sequence(
            poisoning_reasons,
            grade_safety_evidence.get("poisoningReasons"),
        )
        or not same_string_sequence(
            poisoned_documents,
            grade_safety_evidence.get("poisonedChunkDocuments"),
        )
    ):
        return "langsmith eval sync contract missing"
    return None


def langsmith_dataset_name_contract_failure(*, dataset_name: str, source_suite: str) -> bool:
    required_by_source_suite = {
        RAG_CANDIDATE_SOURCE_SUITE: "reactor-rag-ingestion-candidate",
    }
    required_dataset = required_by_source_suite.get(source_suite.strip())
    return required_dataset is not None and dataset_name.strip() != required_dataset


def langsmith_rag_candidate_handoff_failure(item: Mapping[str, object]) -> bool:
    live_sync_command = item.get("liveSyncCommand") or item.get("syncCommand")
    readiness_command = item.get("readinessCommand")
    if not isinstance(live_sync_command, str) or not isinstance(readiness_command, str):
        return True
    live_sync_command = live_sync_command.strip()
    readiness_command = readiness_command.strip()
    if (
        "uv run reactor-langsmith-eval-sync" not in live_sync_command
        or f"--suite-file {RAG_CANDIDATE_SOURCE_SUITE}" not in live_sync_command
        or "--dataset-name reactor-rag-ingestion-candidate" not in live_sync_command
        or langsmith_readiness_preflight_command_failure(item)
    ):
        return True
    report_path = command_value_after(live_sync_command, "--report-file")
    readiness_path = command_value_after(readiness_command, "langsmith_eval_sync=")
    return (
        not report_path
        or not readiness_path
        or report_path != readiness_path
        or langsmith_rag_candidate_next_action_identity_failure(item)
    )


def langsmith_rag_candidate_next_action_identity_failure(item: Mapping[str, object]) -> bool:
    case_ids = item.get("caseIds")
    case_source_run_ids = item.get("caseSourceRunIds")
    next_actions = item.get("nextActions")
    feedback_queue = item.get("feedbackReviewQueue")
    if isinstance(feedback_queue, Mapping) and feedback_queue.get("reviewStatus") == "done":
        return False
    if (
        not non_empty_string_sequence(case_ids)
        or not isinstance(case_source_run_ids, Mapping)
        or not isinstance(next_actions, Sequence)
        or isinstance(next_actions, str | bytes | bytearray)
    ):
        return True
    source_mapping = cast(Mapping[object, object], case_source_run_ids)
    expected_actions: dict[str, dict[str, str]] = {}
    for case_id in cast(Sequence[str], case_ids):
        candidate_id = rag_candidate_slug_from_case_id(case_id)
        source_run_id = source_mapping.get(case_id)
        if candidate_id is None or not isinstance(source_run_id, str) or not source_run_id.strip():
            return True
        candidate_tag = f"rag-candidate:{candidate_id}"
        expected_actions[f"review-rag-candidate-{candidate_id}"] = {
            "candidateTag": candidate_tag,
            "command": rag_candidate_review_action(candidate_tag),
            "evalCaseId": case_id,
            "sourceRunId": source_run_id,
        }
    found_actions: dict[str, Mapping[object, object]] = {}
    for action in cast(Sequence[object], next_actions):
        if not isinstance(action, Mapping):
            continue
        action_mapping = cast(Mapping[object, object], action)
        action_id = action_mapping.get("id")
        if isinstance(action_id, str) and action_id in expected_actions:
            found_actions[action_id] = action_mapping
    if set(found_actions) != set(expected_actions):
        return True
    return any(
        action.get(field_name) != expected_value
        for action_id, expected in expected_actions.items()
        for field_name, expected_value in expected.items()
        for action in (found_actions[action_id],)
    )


def langsmith_readiness_preflight_command_failure(item: Mapping[str, object]) -> bool:
    readiness_command = item.get("readinessCommand")
    if not isinstance(readiness_command, str):
        return True
    readiness_command = readiness_command.strip()
    preflight_file = item.get("preflightFile")
    preflight_env_template = item.get("preflightEnvTemplate")
    if (
        isinstance(preflight_file, str)
        and preflight_file.strip() != "reports/release/release-smoke-preflight.local.json"
    ):
        return True
    if (
        isinstance(preflight_env_template, str)
        and preflight_env_template.strip() != "reports/release/release-smoke-preflight.local.env"
    ):
        return True
    return (
        "uv run reactor-release-smoke-run" not in readiness_command
        or "--preflight-file reports/release/release-smoke-preflight.local.json"
        not in readiness_command
        or "--env-file reports/release/release-smoke-preflight.local.env" not in readiness_command
        or "--required-readiness-report langsmith_eval_sync" not in readiness_command
    )


def langsmith_readiness_report_path_failure(item: Mapping[str, object]) -> bool:
    artifact = item.get("artifact")
    readiness_command = item.get("readinessCommand")
    if not isinstance(artifact, str) or not artifact.strip():
        return True
    if not isinstance(readiness_command, str):
        return True
    readiness_path = command_value_after(readiness_command, "langsmith_eval_sync=")
    return not readiness_path or readiness_path != artifact.strip()


def langsmith_readiness_metadata_failure(item: Mapping[str, object]) -> bool:
    readiness_command = item.get("readinessCommand")
    if not isinstance(readiness_command, str):
        return True
    readiness_path = command_value_after(readiness_command, "langsmith_eval_sync=")
    required_reports = item.get("requiredReadinessReports")
    if not isinstance(required_reports, Sequence) or isinstance(
        required_reports, str | bytes | bytearray
    ):
        return True
    reports = [
        report.strip()
        for report in cast(Sequence[object], required_reports)
        if isinstance(report, str) and report.strip()
    ]
    readiness_reports = item.get("readinessReports")
    if not isinstance(readiness_reports, Mapping):
        return True
    readiness_report_mapping = cast(Mapping[object, object], readiness_reports)
    report_file = readiness_report_mapping.get("langsmith_eval_sync")
    if (
        not readiness_path
        or not isinstance(report_file, str)
        or report_file.strip() != readiness_path
    ):
        return True
    if reports == ["langsmith_eval_sync"]:
        return False
    hardening_path = command_value_after(readiness_command, "hardening_suite=")
    hardening_file = readiness_report_mapping.get("hardening_suite")
    if (
        reports != ["hardening_suite", "langsmith_eval_sync"]
        or hardening_path != "reports/hardening-suite.json"
        or not isinstance(hardening_file, str)
        or hardening_file.strip() != hardening_path
    ):
        return True
    product_boundary = item.get("productCapabilityBoundary")
    if not isinstance(product_boundary, Mapping):
        return False
    missing_evidence = cast(Mapping[object, object], product_boundary).get("missingEvidence")
    missing_sequence = (
        cast(Sequence[object], missing_evidence)
        if isinstance(missing_evidence, Sequence)
        and not isinstance(missing_evidence, str | bytes | bytearray)
        else ()
    )
    missing_items = {
        evidence.strip()
        for evidence in missing_sequence
        if isinstance(evidence, str) and evidence.strip()
    }
    resolved_by = item.get("productBoundaryResolvedByReports")
    if not isinstance(resolved_by, Mapping):
        resolved_by = item.get("productBoundaryExpectedResolvedByReports")
    if isinstance(resolved_by, Mapping):
        resolved_by_mapping = cast(Mapping[object, object], resolved_by)
        if resolved_by_mapping.get("rag_ingestion_lifecycle") == "hardening_suite":
            return False
    return "rag_ingestion_lifecycle" not in missing_items


def langsmith_readiness_report_arg_failure(item: Mapping[str, object]) -> bool:
    required_reports = item.get("requiredReadinessReports")
    if not isinstance(required_reports, Sequence) or isinstance(
        required_reports, str | bytes | bytearray
    ):
        return False
    reports = {
        report.strip()
        for report in cast(Sequence[object], required_reports)
        if isinstance(report, str) and report.strip()
    }
    if "hardening_suite" not in reports:
        return False
    readiness_report_arg = item.get("readinessReportArg")
    readiness_reports = item.get("readinessReports")
    if not isinstance(readiness_report_arg, str) or not isinstance(readiness_reports, Mapping):
        return True
    readiness_report_mapping = cast(Mapping[object, object], readiness_reports)
    hardening_file = readiness_report_mapping.get("hardening_suite")
    langsmith_file = readiness_report_mapping.get("langsmith_eval_sync")
    hardening_arg = command_value_after(readiness_report_arg, "hardening_suite=")
    langsmith_arg = command_value_after(readiness_report_arg, "langsmith_eval_sync=")
    return (
        not isinstance(hardening_file, str)
        or not isinstance(langsmith_file, str)
        or hardening_file.strip() != hardening_arg
        or langsmith_file.strip() != langsmith_arg
    )


def command_value_after(command: str, marker: str) -> str:
    marker_index = command.find(marker)
    if marker_index < 0:
        return ""
    value = command[marker_index + len(marker) :].strip()
    if not value:
        return ""
    return value.split()[0].strip()


def langsmith_case_policy(
    source_suite: str,
    *,
    case_ids: Set[str],
) -> dict[str, frozenset[str]]:
    if source_suite.strip() == RAG_CANDIDATE_SOURCE_SUITE:
        if not case_ids or any(not valid_rag_candidate_case_id(case_id) for case_id in case_ids):
            return {
                "required": RAG_CANDIDATE_LANGSMITH_EVAL_CASE_IDS,
                "allowed": RAG_CANDIDATE_LANGSMITH_EVAL_CASE_IDS,
                "grounded": RAG_CANDIDATE_LANGSMITH_EVAL_CASE_IDS,
                "poisoning": frozenset(),
                "feedback_queue": RAG_CANDIDATE_LANGSMITH_EVAL_CASE_IDS,
            }
        candidate_case_ids = frozenset(case_ids)
        return {
            "required": candidate_case_ids,
            "allowed": candidate_case_ids,
            "grounded": candidate_case_ids,
            "poisoning": frozenset(),
            "feedback_queue": candidate_case_ids,
        }
    return {
        "required": REQUIRED_LANGSMITH_EVAL_CASE_IDS,
        "allowed": ALLOWED_LANGSMITH_EVAL_CASE_IDS,
        "grounded": REQUIRED_LANGSMITH_GROUNDED_CASE_IDS,
        "poisoning": REQUIRED_LANGSMITH_EVAL_CASE_IDS,
        "feedback_queue": frozenset(),
    }


def langsmith_trace_grade_safety_evidence(
    *,
    grades: Sequence[Mapping[str, object]],
    case_id: str,
) -> Mapping[str, object] | None:
    for grade in grades:
        if grade.get("caseId") != case_id:
            continue
        dimensions = grade.get("dimensions")
        if non_empty_mapping_sequence(dimensions):
            return safety_dimension_evidence(cast(Sequence[Mapping[str, object]], dimensions))
    return None


def langsmith_trace_grade_run_id(
    *,
    grades: Sequence[Mapping[str, object]],
    case_id: str,
) -> str | None:
    for grade in grades:
        if grade.get("caseId") == case_id and isinstance(run_id := grade.get("runId"), str):
            return run_id
    return None


def langsmith_trace_grade_contract_failure(
    *,
    grades: Sequence[Mapping[str, object]],
    case_id_set: set[str],
    required_grounded_case_ids: frozenset[str],
    required_poisoning_case_ids: frozenset[str],
) -> bool:
    allowed_dimension_names = {
        "deterministic_eval",
        "safety",
        "tool_exposure",
        "tool_efficiency",
        "grounding",
        "reliability",
    }
    seen_case_ids: set[str] = set()
    poisoning_safety_verified = False
    grounded_case_ids: set[str] = set()
    for grade in grades:
        allowed_grade_fields = {"caseId", "runId", "passed", "score", "dimensions"}
        if set(grade) != allowed_grade_fields:
            return True
        case_id = grade.get("caseId")
        run_id = grade.get("runId")
        score = grade.get("score")
        if (
            not isinstance(case_id, str)
            or case_id not in case_id_set
            or not isinstance(run_id, str)
            or not run_id.strip()
            or grade.get("passed") is not True
            or not normalized_score(score)
        ):
            return True
        seen_case_ids.add(case_id)
        dimensions = grade.get("dimensions")
        if not non_empty_mapping_sequence(dimensions):
            return True
        dimension_mappings = cast(Sequence[Mapping[str, object]], dimensions)
        for dimension in dimension_mappings:
            dimension_name = dimension.get("name")
            if not isinstance(dimension_name, str) or dimension_name not in allowed_dimension_names:
                return True
            dimension_score = dimension.get("score")
            dimension_evidence = dimension.get("evidence")
            if not normalized_score(dimension_score) or not isinstance(dimension_evidence, Mapping):
                return True
            dimension_evidence_mapping = cast(Mapping[str, object], dimension_evidence)
            if dimension_name == "grounding":
                has_grounding_evidence = bool(set(dimension_evidence_mapping))
                if has_grounding_evidence and grounding_dimension_evidence_contract_failure(
                    dimension_evidence_mapping
                ):
                    return True
                if has_grounding_evidence:
                    grounded_case_ids.add(case_id)
            elif dimension_name == "deterministic_eval":
                if deterministic_eval_dimension_evidence_contract_failure(
                    dimension_evidence_mapping
                ):
                    return True
            elif dimension_name != "safety" and set(dimension_evidence_mapping):
                return True
        safety_dimension = safety_dimension_evidence(dimension_mappings)
        if safety_dimension is None:
            return True
        if case_id in required_poisoning_case_ids:
            poisoned_chunks = safety_dimension.get("poisonedChunks")
            poisoning_reasons = safety_dimension.get("poisoningReasons")
            poisoned_documents = safety_dimension.get("poisonedChunkDocuments")
            if (
                not isinstance(poisoned_chunks, int)
                or isinstance(poisoned_chunks, bool)
                or poisoned_chunks <= 0
                or not non_empty_string_sequence(poisoning_reasons)
                or not non_empty_string_sequence(poisoned_documents)
            ):
                return True
            if any(
                cast(str, reason) not in RAG_POISONING_REASONS
                for reason in cast(Sequence[object], poisoning_reasons)
            ):
                return True
            poisoning_safety_verified = True
    return (
        seen_case_ids != case_id_set
        or (bool(required_poisoning_case_ids) and not poisoning_safety_verified)
        or not required_grounded_case_ids.intersection(case_id_set).issubset(grounded_case_ids)
    )


def deterministic_eval_dimension_evidence_contract_failure(
    evidence: Mapping[str, object],
) -> bool:
    if set(evidence) != {"missingExpectedAnswerContains", "reasons"}:
        return True
    missing_expected = evidence.get("missingExpectedAnswerContains")
    reasons = evidence.get("reasons")
    return not string_sequence(missing_expected) or not string_sequence(reasons)


def grounding_dimension_evidence_contract_failure(evidence: Mapping[str, object]) -> bool:
    if set(evidence) != {"retrieved", "cited", "uncited", "citedDocuments"}:
        return True
    retrieved = evidence.get("retrieved")
    cited = evidence.get("cited")
    uncited = evidence.get("uncited")
    if (
        not isinstance(retrieved, int)
        or isinstance(retrieved, bool)
        or retrieved <= 0
        or not isinstance(cited, int)
        or isinstance(cited, bool)
        or cited <= 0
        or not isinstance(uncited, int)
        or isinstance(uncited, bool)
        or uncited < 0
        or retrieved != cited + uncited
    ):
        return True
    cited_documents = evidence.get("citedDocuments")
    if not non_empty_string_sequence(cited_documents):
        return True
    cited_document_values = cast(Sequence[str], cited_documents)
    return (
        len(set(cited_document_values)) != len(cited_document_values)
        or len(cited_document_values) > cited
        or any(not is_citation_safe_id(document) for document in cited_document_values)
    )


def safety_dimension_evidence(
    dimensions: Sequence[Mapping[str, object]],
) -> Mapping[str, object] | None:
    for dimension in dimensions:
        if set(dimension) != {"name", "score", "evidence"}:
            return None
        if dimension.get("name") != "safety":
            continue
        score = dimension.get("score")
        evidence = dimension.get("evidence")
        if not normalized_score(score) or not isinstance(evidence, Mapping):
            return None
        evidence_mapping = cast(Mapping[str, object], evidence)
        allowed_fields = {
            "forbiddenUsed",
            "forbiddenExposed",
            "poisonedChunks",
            "poisoningReasons",
            "poisonedChunkDocuments",
        }
        if set(evidence_mapping) != allowed_fields:
            return None
        forbidden_used = evidence_mapping.get("forbiddenUsed")
        forbidden_exposed = evidence_mapping.get("forbiddenExposed")
        if not string_sequence(forbidden_used) or not string_sequence(forbidden_exposed):
            return None
        if any(not non_empty_string(item) for item in cast(Sequence[object], forbidden_used)):
            return None
        if any(not non_empty_string(item) for item in cast(Sequence[object], forbidden_exposed)):
            return None
        return evidence_mapping
    return None


def checkpoint_provenance_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if item.get("status") != "passed":
        return None
    provenance = item.get("checkpointProvenance")
    if provenance is None:
        if name == "hardening_suite":
            return "checkpoint provenance contract missing"
        return None
    if not isinstance(provenance, Mapping):
        return "checkpoint provenance contract missing"
    provenance_mapping = cast(Mapping[str, object], provenance)
    if provenance_mapping.get("source") != "checkpoint_fork":
        return "checkpoint provenance contract missing"
    for field_name in (
        "forkedFromRunId",
        "forkedFromThreadId",
        "forkedFromCheckpointNs",
        "forkTargetThreadId",
        "forkTargetCheckpointNs",
    ):
        field_value = provenance_mapping.get(field_name)
        if not isinstance(field_value, str) or not field_value.strip():
            return "checkpoint provenance contract missing"
    checkpoint_id = provenance_mapping.get("forkedFromCheckpointId")
    if checkpoint_id is not None and (not isinstance(checkpoint_id, str) or not checkpoint_id):
        return "checkpoint provenance contract missing"
    replay_coverage = provenance_mapping.get("replayCoverage")
    if not isinstance(replay_coverage, Mapping):
        return "checkpoint provenance contract missing"
    replay_coverage_mapping = cast(Mapping[str, object], replay_coverage)
    if replay_coverage_mapping.get("status") != "verified":
        return "checkpoint provenance contract missing"
    required_runtimes = {
        "langgraph",
        "langchain_agent",
        "langgraph_stream",
        "langchain_agent_stream",
    }
    if not exact_string_set(replay_coverage_mapping.get("runtimes"), required_runtimes):
        return "checkpoint provenance contract missing"
    required_configurable_keys = {"thread_id", "checkpoint_ns", "checkpoint_id"}
    if not exact_string_set(
        replay_coverage_mapping.get("configurableKeys"),
        required_configurable_keys,
    ):
        return "checkpoint provenance contract missing"
    required_ignored_reasons = {"missing_checkpoint_id", "fork_target_mismatch"}
    if not exact_string_set(
        replay_coverage_mapping.get("ignoredReasons"),
        required_ignored_reasons,
    ):
        return "checkpoint provenance contract missing"
    required_applied_metadata_fields = {
        "status",
        "source",
        "requestedCheckpointId",
        "checkpointId",
        "materialization",
        "targetThreadId",
        "targetCheckpointNs",
    }
    if not exact_string_set(
        replay_coverage_mapping.get("appliedMetadataFields"),
        required_applied_metadata_fields,
    ):
        return "checkpoint provenance contract missing"
    if checkpoint_storage_semantics_failure(provenance_mapping.get("storageSemantics")):
        return "checkpoint provenance contract missing"
    if checkpoint_diagnostics_surface_failure(provenance_mapping.get("diagnosticsSurface")):
        return "checkpoint provenance contract missing"
    return None


def checkpoint_storage_semantics_failure(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    semantics = cast(Mapping[str, object], value)
    if semantics.get("status") != "verified":
        return True
    if semantics.get("physicalThreadKey") != "sha256_v1":
        return True
    if semantics.get("rootCheckpointNs") != "":
        return True
    if semantics.get("sourceRead") != "BaseCheckpointSaver.aget_tuple":
        return True
    if semantics.get("targetWrite") != "BaseCheckpointSaver.aput":
        return True
    if semantics.get("trustedCapability") != "TrustedCheckpointFork":
        return True
    if semantics.get("profileNamespaceStateField") != "profile_checkpoint_ns":
        return True
    if semantics.get("profileNamespaceSource") != "resolved_durable_checkpoint_ns":
        return True
    for field_name in (
        "tenantScoped",
        "targetMustBeEmpty",
        "pendingWritesRejected",
        "sourceReadIdentityVerified",
        "sourcePayloadIdentityVerified",
        "targetWriteScopeVerified",
        "userMetadataCannotAuthorizeReplay",
        "typedChatNamespaceAccepted",
        "userMetadataCannotOverrideNamespace",
        "profileMetadataUsesDurableNamespace",
        "profileCannotOverrideDurableNamespace",
        "executionContractMatchRequired",
    ):
        if semantics.get(field_name) is not True:
            return True
    if not exact_string_set(
        semantics.get("logicalIdentity"),
        {"tenant_id", "thread_id", "checkpoint_ns"},
    ):
        return True
    if not exact_string_set(
        semantics.get("streamingNamespaceTargets"),
        {
            "run_store",
            "checkpoint_fork",
            "langgraph_config",
            "langchain_agent",
            "run_result",
            "terminal_actions",
        },
    ):
        return True
    if not exact_string_set(
        semantics.get("materializationModes"),
        {"pinned_source_scope", "copied_to_target_scope"},
    ):
        return True
    if not exact_string_set(
        semantics.get("executionContractFields"),
        {"runtime", "graphProfile"},
    ):
        return True
    return not exact_string_set(
        semantics.get("failClosedReasons"),
        {
            "invalid_fork_provenance",
            "checkpointer_unavailable",
            "source_checkpoint_not_found",
            "source_checkpoint_scope_mismatch",
            "source_checkpoint_id_mismatch",
            "source_checkpoint_payload_id_mismatch",
            "invalid_source_checkpoint",
            "source_checkpoint_has_pending_writes",
            "target_checkpoint_scope_not_empty",
            "target_checkpoint_write_scope_mismatch",
            "target_checkpoint_write_failed",
            "checkpoint_store_error",
            "fork_execution_contract_mismatch",
        },
    )


def checkpoint_diagnostics_surface_failure(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    diagnostics_surface = cast(Mapping[str, object], value)
    if diagnostics_surface.get("status") != "verified":
        return True
    if diagnostics_surface.get("permission") != "settings:read":
        return True
    if not exact_string_set(
        diagnostics_surface.get("forkApiPaths"),
        {"/v1/runs/{run_id}/fork"},
    ):
        return True
    if not exact_string_set(
        diagnostics_surface.get("stateHistoryApiPaths"),
        {
            "/api/admin/debug/state-history/{run_id}",
            "/v1/admin/debug/state-history/{run_id}",
        },
    ):
        return True
    if not exact_string_set(
        diagnostics_surface.get("diagnosticsApiPaths"),
        {
            "/api/admin/checkpoints/diagnostics",
            "/v1/admin/checkpoints/diagnostics",
        },
    ):
        return True
    trusted_keys = diagnostics_surface.get("trustedMetadataKeys")
    required_trusted_keys = {
        "source",
        "forkedFromRunId",
        "forkedFromThreadId",
        "forkedFromCheckpointNs",
        "forkedFromCheckpointId",
        "forkTargetThreadId",
        "forkTargetCheckpointNs",
        "forkedFromExecutionContract",
    }
    if not exact_string_set(trusted_keys, required_trusted_keys):
        return True
    required_stripped_keys = {
        "source",
        "checkpointId",
        "checkpoint_id",
        *required_trusted_keys,
    }
    return not exact_string_set(
        diagnostics_surface.get("userMetadataStrippedKeys"),
        required_stripped_keys,
    )


def langchain_middleware_policy_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    if item.get("status") != "passed":
        return None
    middleware_policy = item.get("langchainMiddlewarePolicy")
    if middleware_policy is None:
        if name == "hardening_suite":
            return "langchain middleware policy contract missing"
        return None
    if not isinstance(middleware_policy, Mapping):
        return "langchain middleware policy contract missing"
    policy_mapping = cast(Mapping[str, object], middleware_policy)
    status = policy_mapping.get("status")
    if status not in {"applied", "ignored"}:
        return "langchain middleware policy contract missing"
    source = policy_mapping.get("source")
    if not isinstance(source, str) or not source.strip():
        return "langchain middleware policy contract missing"
    if status == "applied":
        policy = policy_mapping.get("policy")
        if not isinstance(policy, Mapping):
            return "langchain middleware policy contract missing"
        policy_body = cast(Mapping[str, object], policy)
        for field_name in (
            "modelCallRunLimit",
            "toolCallRunLimit",
            "modelRetryMaxRetries",
            "toolRetryMaxRetries",
        ):
            if field_name not in policy_body:
                return "langchain middleware policy contract missing"
        pii_rules = policy_body.get("piiRules")
        if pii_rules is None or langchain_middleware_policy_pii_rule_failure(pii_rules):
            return "langchain middleware policy contract missing"
        if source == "default_code_policy" and langchain_middleware_default_pii_coverage_failure(
            pii_rules
        ):
            return "langchain middleware policy contract missing"
        if name == "hardening_suite":
            if policy_mapping.get("policyFieldValidation") != {
                "unknownPolicyFieldsRejected": True,
                "unknownPiiRuleFieldsRejected": True,
                "metadataFailureReason": "invalid_metadata_policy",
                "runtimeSettingFailureReason": "invalid_runtime_setting",
                "invokeStreamSharedResolver": True,
                "invokeRuntimeSettingsSnapshotShared": True,
                "preflightRuntimeSettingsSnapshotShared": True,
                "streamRuntimeSettingsSnapshotShared": True,
                "resumePolicyReevaluated": True,
                "resumeStaleEvidenceRemoved": True,
                "resumeRuntimeSettingsSnapshotShared": True,
                "resumeSettingsSnapshotCancellationPersisted": True,
                "resumeSettingsSnapshotFailureFailsClosed": True,
                "resumeMiddlewareLookupCancellationPersisted": True,
                "verificationSensors": [
                    "tests/unit/test_langchain_middleware.py::"
                    "test_langchain_middleware_policy_from_mapping_rejects_invalid_values",
                    "tests/unit/test_run_service.py::"
                    "test_run_service_ignores_invalid_metadata_langchain_middleware_policy",
                    "tests/unit/test_run_service.py::"
                    "test_run_service_ignores_invalid_langchain_middleware_runtime_setting",
                    "tests/unit/test_run_service.py::"
                    "test_langchain_invoke_uses_one_runtime_settings_snapshot",
                    "tests/unit/test_run_service.py::"
                    "test_langchain_preflight_uses_one_runtime_settings_snapshot",
                    "tests/unit/test_run_service.py::"
                    "test_langchain_stream_uses_one_runtime_settings_snapshot",
                    "tests/unit/test_run_service.py::"
                    "test_langchain_resume_removes_stale_middleware_policy_evidence",
                    "tests/unit/test_run_service.py::"
                    "test_langchain_resume_refreshes_middleware_policy_from_tenant_setting",
                    "tests/unit/test_run_service.py::"
                    "test_langchain_resume_uses_one_runtime_settings_snapshot",
                    "tests/unit/test_run_service.py::"
                    "test_langchain_resume_settings_snapshot_cancellation_persists_terminal_state",
                    "tests/unit/test_run_service.py::"
                    "test_langchain_resume_settings_snapshot_failure_fails_closed",
                    "tests/unit/test_run_service.py::"
                    "test_langchain_resume_middleware_lookup_cancellation_persists_terminal_state",
                ],
            }:
                return "langchain middleware policy contract missing"
            retry_exception_policy = policy_mapping.get("retryExceptionPolicy")
            if not isinstance(retry_exception_policy, Mapping):
                return "langchain middleware policy contract missing"
            retry_exception_policy_mapping = cast(
                Mapping[str, object],
                retry_exception_policy,
            )
            if retry_exception_policy_mapping != {
                "predicate": "is_transient_retry_exception",
                "appliesTo": [
                    "ModelRetryMiddleware",
                    "ToolRetryMiddleware",
                    "invoke_chat_model_with_retry",
                ],
                "transientFamilies": [
                    "timeout",
                    "connection",
                    "rate_limit",
                    "server_error",
                ],
                "httpStatusPolicy": {
                    "explicit": [408, 409, 425, 429],
                    "serverRange": "500-599",
                },
                "permanentFailuresNotRetried": True,
                "sdkCoverage": [
                    "openai",
                    "anthropic",
                    "google-genai",
                ],
                "verificationSensors": [
                    "tests/unit/test_langchain_middleware.py::"
                    "test_retry_exception_policy_uses_transient_failures_only",
                    "tests/unit/test_langchain_middleware.py::"
                    "test_model_retry_does_not_repeat_permanent_validation_error",
                    "tests/unit/test_langchain_middleware.py::"
                    "test_model_retry_is_exhausted_per_model_before_fallback",
                    "tests/unit/test_langchain_middleware.py::"
                    "test_tool_retry_retries_allowlisted_read_tool",
                    "tests/unit/test_agent_graph_policy.py::"
                    "test_graph_model_node_does_not_retry_permanent_chat_model_failure",
                ],
            }:
                return "langchain middleware policy contract missing"
            retry_budget_ownership = policy_mapping.get("retryBudgetOwnership")
            if not isinstance(retry_budget_ownership, Mapping):
                return "langchain middleware policy contract missing"
            retry_budget_ownership_mapping = cast(
                Mapping[str, object],
                retry_budget_ownership,
            )
            if retry_budget_ownership_mapping != {
                "owner": "reactor_policy",
                "providerInternalMaxRetries": 0,
                "langchainAgentMiddleware": "ModelRetryMiddleware",
                "appliesTo": [
                    "primary_model",
                    "fallback_models",
                    "explicit_langgraph_model",
                ],
                "nestedProviderRetriesDisabled": True,
                "middlewareEvidencePlanning": "side_effect_free",
                "providerInitializationOwner": "agent_runtime",
                "verificationSensors": [
                    "tests/unit/test_provider_chat_models.py::"
                    "test_langchain_chat_model_factory_delegates_to_init_chat_model",
                    "tests/unit/test_langchain_agent.py::"
                    "test_resolve_langchain_agent_models_uses_one_factory_for_primary_and_fallbacks",
                    "tests/unit/test_langchain_agent.py::"
                    "test_build_langchain_agent_passes_fallback_models_to_middleware",
                    "tests/unit/test_agent_graph_policy.py::"
                    "test_graph_model_node_retries_transient_chat_model_failure",
                    "tests/unit/test_langchain_agent.py::"
                    "test_planned_langchain_middleware_metadata_matches_actual_chain",
                    "tests/unit/test_run_service.py::"
                    "test_run_service_stream_delegates_fallback_model_initialization_to_runtime",
                ],
            }:
                return "langchain middleware policy contract missing"
            tool_retry_boundary = policy_mapping.get("toolRetryFailureBoundary")
            if not isinstance(tool_retry_boundary, Mapping):
                return "langchain middleware policy contract missing"
            tool_retry_boundary_mapping = cast(Mapping[str, object], tool_retry_boundary)
            if tool_retry_boundary_mapping != {
                "middleware": "ToolRetryMiddleware",
                "onFailure": "fixed_labeled_message",
                "modelVisiblePrefix": "[tool_output:data]",
                "rawExceptionVisible": False,
                "retryableRiskLevels": ["read"],
                "approvalRequiredToolsRetryable": False,
                "sideEffectExceptionStatus": "requires_reconciliation",
                "sideEffectTimeoutStatus": "requires_reconciliation",
                "verificationSensors": [
                    "tests/unit/test_langchain_middleware.py::"
                    "test_tool_retry_failure_hides_raw_exception_from_model",
                    "tests/unit/test_langchain_middleware.py::"
                    "test_tool_retry_does_not_repeat_external_side_effect_without_durable_store",
                    "tests/unit/test_langchain_middleware.py::"
                    "test_tool_retry_retries_allowlisted_read_tool",
                    "tests/unit/test_langchain_tool_adapter.py::"
                    "test_langchain_external_side_effect_timeout_requires_reconciliation",
                ],
            }:
                return "langchain middleware policy contract missing"
        return None
    reason = policy_mapping.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return "langchain middleware policy contract missing"
    return None


def langchain_middleware_policy_pii_rule_failure(value: object) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return True
    rules = cast(Sequence[object], value)
    if not rules:
        return True
    supported_strategies = {"block", "redact", "mask", "hash"}
    for rule in rules:
        if not isinstance(rule, Mapping):
            return True
        rule_mapping = cast(Mapping[str, object], rule)
        if (
            not isinstance(rule_mapping.get("type"), str)
            or not cast(str, rule_mapping.get("type")).strip()
        ):
            return True
        if rule_mapping.get("strategy") not in supported_strategies:
            return True
        for field_name in (
            "applyToInput",
            "applyToOutput",
            "applyToToolResults",
            "applyToStreamOutput",
        ):
            if rule_mapping.get(field_name) is not True:
                return True
    return False


def langsmith_next_action_handoff_failure(item: Mapping[str, object]) -> bool:
    next_actions = item.get("nextActions")
    if not isinstance(next_actions, Sequence) or isinstance(next_actions, str | bytes | bytearray):
        return langsmith_has_next_action_handoff_metadata(item)
    if not next_actions:
        return langsmith_has_next_action_handoff_metadata(item)
    saw_sync_action = False
    saw_refresh_action = False
    saw_hardening_action = False
    for action in cast(Sequence[object], next_actions):
        if not isinstance(action, Mapping):
            continue
        action_mapping = cast(Mapping[object, object], action)
        action_id = action_mapping.get("id")
        if action_id == "sync-langsmith":
            saw_sync_action = True
            command = action_mapping.get("command")
            if (
                not isinstance(command, str)
                or not command.strip()
                or "--dry-run" in command.split()
                or "--preflight-only" in command.split()
                or "reactor-langsmith-eval-sync" not in command
                or "--report-file" not in command.split()
                or action_mapping.get("remediationCommand") == command
                or action_mapping.get("preflightFile")
                != "reports/release/release-smoke-preflight.local.json"
                or action_mapping.get("preflightEnvTemplate")
                != "reports/release/release-smoke-preflight.local.env"
                or action_mapping.get("releaseReadinessFile") != "reports/release-readiness.json"
                or langsmith_action_readiness_handoff_failure(action_mapping, item)
            ):
                return True
            continue
        if action_id == "refresh-release-readiness":
            saw_refresh_action = True
            command = action_mapping.get("command")
            if (
                not isinstance(command, str)
                or not command.strip()
                or action_mapping.get("remediationCommand") != command
                or langsmith_refresh_action_tag_handoff_failure(action_mapping)
                or langsmith_action_readiness_handoff_failure(action_mapping, item)
            ):
                return True
            continue
        if action_id in {"generate-hardening-suite", "verify-memory-lifecycle"}:
            saw_hardening_action = True
            if (
                langsmith_memory_lifecycle_action_failure(action_mapping)
                if action_id == "verify-memory-lifecycle"
                else langsmith_hardening_generation_action_failure(action_mapping, item)
            ):
                return True
    return (
        (saw_sync_action and not saw_refresh_action)
        or (langsmith_requires_sync_action(item) and saw_refresh_action and not saw_sync_action)
        or (langsmith_requires_hardening_report(item) and not saw_hardening_action)
    )


def langsmith_refresh_action_tag_handoff_failure(action: Mapping[object, object]) -> bool:
    minor_boundary_reports = action.get("minorBoundaryReports")
    tag_recommendation_handoff = (
        action.get("recommendedVersionBump") == "minor"
        or action.get("recommendedTagPattern") == "v1.2.0"
    )
    minor_handoff_failure = (
        action.get("recommendedVersionBump") != "minor"
        or action.get("recommendedTagPattern") != "v1.2.0"
        or not (
            isinstance(minor_boundary_reports, Sequence)
            and not isinstance(minor_boundary_reports, str | bytes | bytearray)
            and "langsmith_eval_sync" in minor_boundary_reports
        )
    )
    return (
        action.get("latestTagCommand") != LATEST_TAG_COMMAND
        or action.get("recommendedTagSource") != RECOMMENDED_TAG_SOURCE
        or (tag_recommendation_handoff and minor_handoff_failure)
    )


def langsmith_requires_sync_action(item: Mapping[str, object]) -> bool:
    live_sync_command = item.get("liveSyncCommand")
    return isinstance(live_sync_command, str) and bool(live_sync_command.strip())


def langsmith_has_next_action_handoff_metadata(item: Mapping[str, object]) -> bool:
    return any(
        isinstance(item.get(field_name), str) and cast(str, item.get(field_name)).strip()
        for field_name in ("liveSyncCommand", "syncCommand", "readinessReportArg")
    )


def langsmith_requires_hardening_report(item: Mapping[str, object]) -> bool:
    required_reports = item.get("requiredReadinessReports")
    if not isinstance(required_reports, Sequence) or isinstance(
        required_reports, str | bytes | bytearray
    ):
        return False
    resolved_by = item.get("productBoundaryResolvedByReports")
    if not isinstance(resolved_by, Mapping):
        resolved_by = item.get("productBoundaryExpectedResolvedByReports")
    if isinstance(resolved_by, Mapping):
        resolved_by_mapping = cast(Mapping[object, object], resolved_by)
        if resolved_by_mapping.get("rag_ingestion_lifecycle") == "hardening_suite":
            return False
    return any(
        isinstance(report, str) and report.strip() == "hardening_suite"
        for report in cast(Sequence[object], required_reports)
    )


def langsmith_hardening_generation_action_failure(
    action_mapping: Mapping[object, object],
    item: Mapping[str, object],
) -> bool:
    return (
        action_mapping.get("command")
        != "uv run reactor-hardening-suite --report-file reports/hardening-suite.json"
        or action_mapping.get("readinessReportArg")
        != "--readiness-report hardening_suite=reports/hardening-suite.json"
        or not same_string_sequence(
            action_mapping.get("requiredReadinessReports"), item.get("requiredReadinessReports")
        )
        or not same_string_mapping(
            action_mapping.get("readinessReports"),
            item.get("readinessReports"),
        )
    )


def langsmith_memory_lifecycle_action_failure(action_mapping: Mapping[object, object]) -> bool:
    return (
        action_mapping.get("command") != MEMORY_LIFECYCLE_GATE_ACTION
        or action_mapping.get("preflightFile")
        != "reports/release/release-smoke-preflight.local.json"
        or action_mapping.get("preflightEnvTemplate")
        != "reports/release/release-smoke-preflight.local.env"
        or action_mapping.get("replatformReadinessFile")
        != "reports/release/replatform-readiness.local.json"
        or action_mapping.get("smokePlanFile") != "reports/release/release-smoke-plan.local.json"
        or action_mapping.get("releaseEvidenceFile") != "reports/release-evidence.json"
        or action_mapping.get("releaseReadinessFile") != "reports/release-readiness.json"
        or action_mapping.get("readinessReportArg")
        != "--readiness-report hardening_suite=reports/hardening-suite.json"
        or not same_string_sequence(
            action_mapping.get("requiredReadinessReports"),
            ["hardening_suite"],
        )
        or not same_string_mapping(
            action_mapping.get("readinessReports"),
            {"hardening_suite": HARDENING_SUITE_REPORT_FILE},
        )
    )


def langsmith_action_readiness_handoff_failure(
    action_mapping: Mapping[object, object],
    item: Mapping[str, object],
) -> bool:
    return (
        action_mapping.get("readinessReportArg") != item.get("readinessReportArg")
        or not same_string_sequence(
            action_mapping.get("requiredReadinessReports"), item.get("requiredReadinessReports")
        )
        or not same_string_mapping(
            action_mapping.get("readinessReports"),
            item.get("readinessReports"),
        )
    )


def langchain_middleware_default_pii_coverage_failure(value: object) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return True
    rules = cast(Sequence[object], value)
    rule_types = {
        cast(Mapping[str, object], rule).get("type") for rule in rules if isinstance(rule, Mapping)
    }
    return rule_types != {"email", "url", "ip", "mac_address", "credit_card"}


def langchain_middleware_chain_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    chain = item.get("langchainMiddlewareChain")
    if chain is None:
        if name == "hardening_suite":
            return "langchain middleware chain contract missing"
        return None
    if not isinstance(chain, Mapping):
        return "langchain middleware chain contract missing"
    chain_mapping = cast(Mapping[str, object], chain)
    if chain_mapping.get("status") != "applied":
        return "langchain middleware chain contract missing"
    middleware = chain_mapping.get("middleware")
    if not non_empty_string_sequence(middleware):
        return "langchain middleware chain contract missing"
    middleware_names = cast(Sequence[str], middleware)
    allowed_middleware = {
        "ModelCallLimitMiddleware",
        "ToolCallLimitMiddleware",
        "ModelRetryMiddleware",
        "ToolRetryMiddleware",
        "PIIMiddleware",
        "HumanInTheLoopMiddleware",
        "ModelFallbackMiddleware",
    }
    if any(name not in allowed_middleware for name in middleware_names):
        return "langchain middleware chain contract missing"
    count = chain_mapping.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count != len(middleware_names):
        return "langchain middleware chain contract missing"
    for field_name in ("piiRuleCount", "hitlToolCount", "fallbackModelCount"):
        field_value = chain_mapping.get(field_name)
        if not isinstance(field_value, int) or isinstance(field_value, bool) or field_value < 0:
            return "langchain middleware chain contract missing"
    pii_rule_count = cast(int, chain_mapping["piiRuleCount"])
    if pii_rule_count != middleware_names.count("PIIMiddleware"):
        return "langchain middleware chain contract missing"
    hitl_tool_count = cast(int, chain_mapping["hitlToolCount"])
    if hitl_tool_count != middleware_names.count("HumanInTheLoopMiddleware"):
        return "langchain middleware chain contract missing"
    fallback_model_count = cast(int, chain_mapping["fallbackModelCount"])
    fallback_middleware_count = middleware_names.count("ModelFallbackMiddleware")
    if fallback_model_count == 0 and fallback_middleware_count != 0:
        return "langchain middleware chain contract missing"
    if fallback_model_count > 0 and fallback_middleware_count != 1:
        return "langchain middleware chain contract missing"
    expected_pii_rule_count = langchain_middleware_policy_pii_rule_count(item)
    if expected_pii_rule_count is not None and pii_rule_count != expected_pii_rule_count:
        return "langchain middleware chain contract missing"
    if "PIIMiddleware" not in middleware_names:
        return "langchain middleware chain contract missing"
    return None


def langchain_middleware_policy_pii_rule_count(item: Mapping[str, object]) -> int | None:
    middleware_policy = item.get("langchainMiddlewarePolicy")
    if not isinstance(middleware_policy, Mapping):
        return None
    policy_mapping = cast(Mapping[str, object], middleware_policy)
    if policy_mapping.get("status") != "applied":
        return None
    policy = policy_mapping.get("policy")
    if not isinstance(policy, Mapping):
        return None
    policy_body = cast(Mapping[str, object], policy)
    pii_rules = policy_body.get("piiRules")
    if pii_rules is None:
        return None
    if not isinstance(pii_rules, Sequence) or isinstance(pii_rules, str | bytes | bytearray):
        return None
    return len(cast(Sequence[object], pii_rules))


def langchain_serialization_boundary_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    boundary = item.get("langchainSerializationBoundary")
    if not isinstance(boundary, Mapping):
        return "langchain serialization boundary contract missing"
    boundary_mapping = cast(Mapping[str, object], boundary)
    if boundary_mapping.get("status") != "verified":
        return "langchain serialization boundary contract missing"
    if boundary_mapping.get("sdk") != "langchain-core":
        return "langchain serialization boundary contract missing"

    unsafe_apis = boundary_mapping.get("unsafeLoadApisForbidden")
    if not non_empty_string_sequence(unsafe_apis):
        return "langchain serialization boundary contract missing"
    required_apis = {
        "langchain_core.load.load",
        "langchain_core.load.loads",
        "langchain_core.prompts.load_prompt",
        "langchain.chains.loading.load_chain",
        "langchain.agents.loading.load_agent",
    }
    if not exact_string_set(unsafe_apis, required_apis):
        return "langchain serialization boundary contract missing"

    for field_name in (
        "secretsFromEnvForbidden",
        "userConfigDeserializationForbidden",
        "trustedJsonOnly",
    ):
        if boundary_mapping.get(field_name) is not True:
            return "langchain serialization boundary contract missing"
    checkpoint_state = boundary_mapping.get("checkpointState")
    if not isinstance(checkpoint_state, Mapping):
        return "langchain serialization boundary contract missing"
    checkpoint_mapping = cast(Mapping[str, object], checkpoint_state)
    if set(checkpoint_mapping) != {
        "runtime",
        "strictMsgpackEnvironment",
        "strictMsgpackEnabledBeforeImports",
        "stateSchema",
        "pendingToolSchema",
        "approvalResumeSchema",
        "newInputVersionInjected",
        "incompatibleNewInputRejected",
        "everyNodeVersionGuarded",
        "staleReplayRejected",
        "graphInputNormalizedBeforeCheckpoint",
        "resumeCommandNormalizedBeforeCheckpoint",
        "resumeControlFieldsForbidden",
        "unexpectedResumeFieldsRejected",
        "reducersNormalizeUpdates",
        "customObjectsForbidden",
        "unknownSchemaVersionsRejected",
        "catalogIdentityPreserved",
        "verificationSensors",
    }:
        return "langchain serialization boundary contract missing"
    if checkpoint_mapping.get("runtime") != "langgraph":
        return "langchain serialization boundary contract missing"
    if checkpoint_mapping.get("strictMsgpackEnvironment") != "LANGGRAPH_" + "STRICT_MSGPACK":
        return "langchain serialization boundary contract missing"
    if checkpoint_mapping.get("stateSchema") != "reactor.agent.state.v1":
        return "langchain serialization boundary contract missing"
    if checkpoint_mapping.get("pendingToolSchema") != "reactor.pending_tool_request.v1":
        return "langchain serialization boundary contract missing"
    if checkpoint_mapping.get("approvalResumeSchema") != "reactor.approval_resume.v1":
        return "langchain serialization boundary contract missing"
    for field_name in (
        "strictMsgpackEnabledBeforeImports",
        "newInputVersionInjected",
        "incompatibleNewInputRejected",
        "everyNodeVersionGuarded",
        "staleReplayRejected",
        "graphInputNormalizedBeforeCheckpoint",
        "resumeCommandNormalizedBeforeCheckpoint",
        "resumeControlFieldsForbidden",
        "unexpectedResumeFieldsRejected",
        "reducersNormalizeUpdates",
        "customObjectsForbidden",
        "unknownSchemaVersionsRejected",
        "catalogIdentityPreserved",
    ):
        if checkpoint_mapping.get(field_name) is not True:
            return "langchain serialization boundary contract missing"
    if not exact_string_set(
        checkpoint_mapping.get("verificationSensors"),
        {
            "tests/unit/test_agent_tool_state.py",
            "tests/unit/test_agent_graph_policy.py::test_graph_checkpoint_normalizes_pending_tool_to_strict_msgpack_state",
            "tests/unit/test_agent_graph_policy.py::test_graph_replay_rejects_stale_checkpoint_state_version",
        },
    ):
        return "langchain serialization boundary contract missing"
    return None


def context_management_lifecycle_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    lifecycle = item.get("contextManagementLifecycle")
    if not isinstance(lifecycle, Mapping):
        return "context management lifecycle contract missing"
    lifecycle_mapping = cast(Mapping[str, object], lifecycle)
    required_text_fields = {
        "status": "verified",
        "framework": "langchain_middleware",
        "summarizationMiddleware": "SummarizationMiddleware",
        "contextEditingMiddleware": "ContextEditingMiddleware",
        "toolSelectionMiddleware": "LLMToolSelectorMiddleware",
        "providerToolSearchMiddleware": "ProviderToolSearchMiddleware",
    }
    required_boolean_fields = {
        "contextManifestRequired",
        "contentChecksumsRequired",
        "toolCallPairPreservationRequired",
        "tenantPolicyBeforeContextMutation",
        "auditRecordsContextMutations",
        "rawContextNotInReleaseEvidence",
        "activeToolBudgetEnforced",
        "selectionReasonsAudited",
    }
    if set(lifecycle_mapping) != set(required_text_fields) | required_boolean_fields:
        return "context management lifecycle contract missing"
    for field_name, expected_value in required_text_fields.items():
        if lifecycle_mapping.get(field_name) != expected_value:
            return "context management lifecycle contract missing"
    for field_name in required_boolean_fields:
        if lifecycle_mapping.get(field_name) is not True:
            return "context management lifecycle contract missing"
    return None


def usage_cost_lifecycle_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    lifecycle = item.get("usageCostLifecycle")
    if not isinstance(lifecycle, Mapping):
        return "usage cost lifecycle contract missing"
    lifecycle_mapping = cast(Mapping[str, object], lifecycle)
    required_text_fields = {
        "status": "verified",
        "ledger": "UsageLedgerRecord",
        "store": "SqlAlchemyUsageLedgerStore",
        "frameworkUsageSource": "LangChain usage_metadata",
        "streamUsageSource": "LangChain v2 data.chunk usage_metadata",
        "traceUsageSource": "LangSmith token_and_cost_tracking",
        "metricsSurface": "reactor_model_cost_usd_total",
    }
    for field_name, expected_value in required_text_fields.items():
        if lifecycle_mapping.get(field_name) != expected_value:
            return "usage cost lifecycle contract missing"
    required_record_fields = {
        "tenant_id",
        "run_id",
        "provider",
        "model",
        "step_type",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "estimated_cost_usd",
    }
    if not exact_string_set(
        lifecycle_mapping.get("requiredRecordFields"),
        required_record_fields,
    ):
        return "usage cost lifecycle contract missing"
    required_admin_surfaces = {
        "/api/admin/token-cost/by-session",
        "/v1/admin/token-cost/by-session",
        "/api/admin/token-cost/daily",
        "/v1/admin/token-cost/daily",
        "/api/admin/token-cost/top-expensive",
        "/v1/admin/token-cost/top-expensive",
        "/api/admin/tenant/cost",
        "/v1/admin/tenant/cost",
    }
    if not exact_string_set(
        lifecycle_mapping.get("adminReviewSurfaces"),
        required_admin_surfaces,
    ):
        return "usage cost lifecycle contract missing"
    for field_name in (
        "tenantScoped",
        "runScoped",
        "sessionScoped",
        "modelBreakdownRequired",
        "negativeCostRejected",
        "tokenTotalsValidated",
        "totalTokensMatchesBreakdown",
        "zeroCostRecorded",
        "estimatedCostQuantized",
        "metricsRecorded",
        "providerUsagePreferred",
        "estimatedUsageFallbackOnly",
        "cacheAndReasoningTokensPreserved",
    ):
        if lifecycle_mapping.get(field_name) is not True:
            return "usage cost lifecycle contract missing"
    if agent_eval_replay_boundary_failure(lifecycle_mapping.get("agentEvalReplayBoundary")):
        return "usage cost lifecycle contract missing"
    if runs_api_usage_boundary_failure(lifecycle_mapping.get("runsApiBoundary")):
        return "usage cost lifecycle contract missing"
    return None


def agent_eval_replay_boundary_failure(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    boundary = cast(Mapping[str, object], value)
    if set(boundary) != {
        "runtime",
        "usageLedgerAttached",
        "toolPolicyAttached",
        "components",
        "verificationSensors",
    }:
        return True
    if boundary.get("runtime") != "RunService":
        return True
    if (
        boundary.get("usageLedgerAttached") is not True
        or boundary.get("toolPolicyAttached") is not True
    ):
        return True
    if not exact_string_set(
        boundary.get("components"),
        {
            "usage_ledger",
            "tool_provider",
            "tool_handler",
            "tool_invocation_store",
            "builtin_tool_specs",
        },
    ):
        return True
    return boundary.get("verificationSensors") != [
        "tests/integration/test_eval_api.py::"
        "test_eval_replay_uses_reactor_policy_and_usage_components"
    ]


def runs_api_usage_boundary_failure(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    boundary = cast(Mapping[str, object], value)
    if set(boundary) != {
        "factory",
        "usageLedgerAttached",
        "verificationSensors",
    }:
        return True
    if (
        boundary.get("factory") != "build_run_service"
        or boundary.get("usageLedgerAttached") is not True
    ):
        return True
    return boundary.get("verificationSensors") != [
        "tests/integration/test_runs_api.py::test_create_run_api_uses_configured_usage_ledger"
    ]


def tool_profile_budget_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if item.get("status") != "passed":
        return None
    budget = item.get("toolProfileBudget")
    if budget is None:
        return None
    if not isinstance(budget, Mapping):
        return "tool profile budget contract missing"
    budget_mapping = cast(Mapping[str, object], budget)
    allowed_budget_fields = {
        "recommendedActiveToolRange",
        "defaultSource",
        "budgetFieldValidation",
        "researchForcedTool",
        "resolvedMetadataFields",
        "resumePolicyLifecycle",
        "invokePolicyLifecycle",
        "preflightPolicyLifecycle",
        "streamPolicyLifecycle",
        "sampleDroppedTools",
    }
    if set(budget_mapping) != allowed_budget_fields:
        return "tool profile budget contract missing"
    active_range = budget_mapping.get("recommendedActiveToolRange")
    if not isinstance(active_range, Mapping):
        return "tool profile budget contract missing"
    active_range_mapping = cast(Mapping[str, object], active_range)
    minimum = active_range_mapping.get("min")
    maximum = active_range_mapping.get("max")
    if (
        not isinstance(minimum, int)
        or isinstance(minimum, bool)
        or not isinstance(maximum, int)
        or isinstance(maximum, bool)
        or minimum <= 0
        or maximum < minimum
    ):
        return "tool profile budget contract missing"
    default_source = budget_mapping.get("defaultSource")
    if not isinstance(default_source, str) or not default_source.strip():
        return "tool profile budget contract missing"
    field_validation = budget_mapping.get("budgetFieldValidation")
    if not isinstance(field_validation, Mapping):
        return "tool profile budget contract missing"
    field_validation_mapping = cast(Mapping[str, object], field_validation)
    if set(field_validation_mapping) != {
        "allowedFields",
        "unknownFieldsRejected",
        "metadataFailureReason",
        "runtimeSettingFailureReason",
        "metadataAndRuntimeSettingsSharedParser",
    }:
        return "tool profile budget contract missing"
    if (
        not exact_string_set(
            field_validation_mapping.get("allowedFields"),
            {"maxTools", "allowedRiskLevels", "allowedTools", "deniedTools"},
        )
        or field_validation_mapping.get("unknownFieldsRejected") is not True
        or field_validation_mapping.get("metadataFailureReason") != "invalid_metadata_budget"
        or field_validation_mapping.get("runtimeSettingFailureReason") != "invalid_runtime_setting"
        or field_validation_mapping.get("metadataAndRuntimeSettingsSharedParser") is not True
    ):
        return "tool profile budget contract missing"
    required_fields = {
        "source",
        "budget",
        "configuredToolCount",
        "activeToolCount",
        "activeTools",
        "droppedToolCount",
        "droppedTools",
    }
    if not exact_string_set(budget_mapping.get("resolvedMetadataFields"), required_fields):
        return "tool profile budget contract missing"
    if budget_mapping.get("resumePolicyLifecycle") != {
        "budgetReevaluated": True,
        "staleResolvedMetadataRemoved": True,
        "currentResolvedMetadataPersisted": True,
        "runtimeSettingsSnapshotSharedWithMiddleware": True,
        "settingsSnapshotCancellationPersisted": True,
        "verificationSensors": [
            "tests/unit/test_run_service.py::"
            "test_langchain_resume_replaces_stale_tool_profile_budget_evidence",
            "tests/unit/test_run_service.py::"
            "test_langchain_resume_uses_one_runtime_settings_snapshot",
            "tests/unit/test_run_service.py::"
            "test_langchain_resume_settings_snapshot_cancellation_persists_terminal_state",
        ],
    }:
        return "tool profile budget contract missing"
    if budget_mapping.get("invokePolicyLifecycle") != {
        "runtimeSettingsSnapshotSharedWithMiddleware": True,
        "verificationSensors": [
            "tests/unit/test_run_service.py::"
            "test_langchain_invoke_uses_one_runtime_settings_snapshot",
        ],
    }:
        return "tool profile budget contract missing"
    if budget_mapping.get("preflightPolicyLifecycle") != {
        "runtimeSettingsSnapshotSharedWithMiddleware": True,
        "verificationSensors": [
            "tests/unit/test_run_service.py::"
            "test_langchain_preflight_uses_one_runtime_settings_snapshot",
        ],
    }:
        return "tool profile budget contract missing"
    if budget_mapping.get("streamPolicyLifecycle") != {
        "runtimeSettingsSnapshotSharedWithMiddleware": True,
        "verificationSensors": [
            "tests/unit/test_run_service.py::"
            "test_langchain_stream_uses_one_runtime_settings_snapshot",
        ],
    }:
        return "tool profile budget contract missing"
    forced_tool = budget_mapping.get("researchForcedTool")
    if not isinstance(forced_tool, Mapping):
        return "tool profile budget contract missing"
    forced_tool_mapping = cast(Mapping[str, object], forced_tool)
    allowed_forced_tool_fields = {
        "profile",
        "tool",
        "preflightBlocksWhenUnavailable",
        "runBlocksWhenUnavailable",
        "streamBlocksWhenUnavailable",
        "operatorAction",
    }
    if set(forced_tool_mapping) != allowed_forced_tool_fields:
        return "tool profile budget contract missing"
    if (
        forced_tool_mapping.get("profile") != "research"
        or forced_tool_mapping.get("tool") != "Rag:hybrid_search"
        or forced_tool_mapping.get("preflightBlocksWhenUnavailable") is not True
        or forced_tool_mapping.get("runBlocksWhenUnavailable") is not True
        or forced_tool_mapping.get("streamBlocksWhenUnavailable") is not True
        or forced_tool_mapping.get("operatorAction") != "allow_required_research_tool"
    ):
        return "tool profile budget contract missing"
    if tool_profile_budget_drop_reason_failure(budget_mapping.get("sampleDroppedTools")):
        return "tool profile budget contract missing"
    return None


def tool_profile_budget_drop_reason_failure(value: object) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return True
    if len(cast(Sequence[object], value)) == 0:
        return True
    allowed_reasons = {
        "denied_tool",
        "tool_not_allowed",
        "risk_level_not_allowed",
        "max_tools_exceeded",
    }
    seen_reasons: set[str] = set()
    for item in cast(Sequence[object], value):
        if not isinstance(item, Mapping):
            return True
        item_mapping = cast(Mapping[str, object], item)
        if set(item_mapping) != {"tool", "reason", "riskLevel"}:
            return True
        reason = item_mapping.get("reason")
        if reason not in allowed_reasons:
            return True
        seen_reasons.add(cast(str, reason))
        for field_name in ("tool", "riskLevel"):
            field_value = item_mapping.get(field_name)
            if not isinstance(field_value, str) or not field_value.strip():
                return True
    if seen_reasons != allowed_reasons:
        return True
    return False


def research_answer_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    contract = item.get("researchAnswerContract")
    if not isinstance(contract, Mapping):
        return "research answer contract missing"
    contract_mapping = cast(Mapping[str, object], contract)
    allowed_fields = {
        "profile",
        "requiresCitationIds",
        "requiresSourceLabels",
        "citationStyle",
        "uncitedClaimsAllowed",
        "publicMetadataField",
        "extractionMetadataField",
        "tracksContentHashMismatches",
        "tracksMissingChunks",
        "fallbackResponseIncludesSources",
    }
    if set(contract_mapping) != allowed_fields:
        return "research answer contract missing"
    if (
        contract_mapping.get("profile") != "research"
        or contract_mapping.get("requiresCitationIds") is not True
        or contract_mapping.get("requiresSourceLabels") is not True
        or contract_mapping.get("citationStyle") != "manifest_ids"
        or contract_mapping.get("uncitedClaimsAllowed") is not False
        or contract_mapping.get("publicMetadataField") != "research_plan.answerContract"
        or contract_mapping.get("extractionMetadataField") != "research_plan.answerExtraction"
        or contract_mapping.get("tracksContentHashMismatches") is not True
        or contract_mapping.get("tracksMissingChunks") is not True
        or contract_mapping.get("fallbackResponseIncludesSources") is not True
    ):
        return "research answer contract missing"
    return None


def tool_invocation_lifecycle_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    lifecycle = item.get("toolInvocationLifecycle")
    if not isinstance(lifecycle, Mapping):
        return "tool invocation lifecycle contract missing"
    lifecycle_mapping = cast(Mapping[str, object], lifecycle)
    if lifecycle_mapping.get("status") != "verified":
        return "tool invocation lifecycle contract missing"
    required_text_fields = {
        "store": "SqlAlchemyToolInvocationStore",
        "model": "ToolInvocationRecord",
        "idempotencyConstraint": "uq_tool_invocations_idempotency",
        "langchainClaimOperation": "insert_on_conflict_do_nothing",
        "langchainReplayPolicy": "reuse_succeeded_else_fail_closed",
        "nativeClaimOperation": "insert_on_conflict_do_nothing",
        "sharedExecutionPrimitive": "execute_tools_parallel",
        "pendingApprovalClaimTransition": "started_unbound_to_started_approved",
        "langchainCallIdentity": "InjectedToolCallId",
        "toolIdentityField": "catalog_id",
        "staleClaimTransition": "started_to_requires_reconciliation",
        "staleClaimOperatorEndpoint": "/v1/admin/tool-calls/reconcile-stale",
        "pendingApprovalStatus": "started",
    }
    required_collection_fields = {
        "allowedStatuses",
        "requiredRecordFields",
        "auditSurfaces",
        "terminalStatuses",
        "verificationSensors",
        "covers",
    }
    required_boolean_fields = {
        "publicPayloadRedaction",
        "terminalPayloadsValidated",
        "langchainPreExecutionClaimRequired",
        "langchainConcurrentDuplicateBlocked",
        "langchainClaimFailureFailsClosed",
        "idempotencyClaimFailureLogsSafe",
        "langchainApprovalAuditFailureFailsClosed",
        "langchainSucceededResultReused",
        "nativePreExecutionClaimRequired",
        "nativeClaimFailureFailsClosed",
        "nativeUnresolvedClaimFailsClosed",
        "nativeSucceededResultReused",
        "sharedLangGraphLangChainClaimContract",
        "pendingApprovalClaimAtomic",
        "pendingApprovalAuditFailureFailsClosed",
        "rejectedApprovalAuditFailureFailsClosed",
        "pendingApprovalClaimApprovalBound",
        "pendingApprovalClaimChecksumBound",
        "pendingApprovalClaimMarkerRequired",
        "pendingApprovalReplayKeepsInvocationId",
        "runCancellationCancelsUnexecutedApprovalClaims",
        "requestChecksumStableAcrossLifecycle",
        "langchainCallIdentityHiddenFromModelSchema",
        "langchainDistinctCallsPreserved",
        "langchainSameCallReplayStable",
        "completionAuditFailureRequiresReconciliation",
        "completionAuditFailureSkipsSuccessCache",
        "staleClaimAutoReplayForbidden",
        "staleClaimTenantScoped",
        "staleClaimTransitionAudited",
        "staleClaimResponseRawFree",
    }
    allowed_fields = {
        "status",
        *required_text_fields,
        *required_collection_fields,
        *required_boolean_fields,
    }
    if set(lifecycle_mapping) != allowed_fields:
        return "tool invocation lifecycle contract missing"
    for field_name, expected_value in required_text_fields.items():
        if lifecycle_mapping.get(field_name) != expected_value:
            return "tool invocation lifecycle contract missing"
    required_statuses = {
        "started",
        "succeeded",
        "failed",
        "requires_reconciliation",
        "cancelled",
    }
    if not exact_string_set(lifecycle_mapping.get("allowedStatuses"), required_statuses):
        return "tool invocation lifecycle contract missing"
    required_record_fields = {
        "tenant_id",
        "run_id",
        "tool_id",
        "status",
        "idempotency_key",
        "request_checksum",
        "input_payload",
    }
    if not exact_string_set(
        lifecycle_mapping.get("requiredRecordFields"),
        required_record_fields,
    ):
        return "tool invocation lifecycle contract missing"
    required_surfaces = {
        "langgraph_tool_executor",
        "langchain_tool_adapter",
        "approval_pending",
        "approval_rejected",
        "run_tool_invocations_api",
        "admin_tool_calls_api",
        "admin_tool_reconciliation_api",
    }
    if not exact_string_set(lifecycle_mapping.get("auditSurfaces"), required_surfaces):
        return "tool invocation lifecycle contract missing"
    if not same_string_sequence(
        lifecycle_mapping.get("verificationSensors"),
        [
            (
                "uv run pytest tests/unit/test_agent_graph_policy.py -q -k "
                "'fails_closed_when_pending_approval_audit_cannot_be_persisted or "
                "fails_closed_when_rejected_approval_audit_cannot_be_persisted or "
                "rebinds_pending_approval_audit_row_before_resumed_execution or "
                "reuses_durable_idempotent_tool_result_before_handler_execution or "
                "fails_closed_when_durable_idempotency_claim_is_unavailable or "
                "fails_closed_for_unresolved_durable_idempotency_claim'"
            ),
            (
                "uv run pytest tests/unit/test_tool_execution.py -q -k "
                "'idempotency_claim_failure_logs_safely_and_skips_execution or "
                "external_side_effect_requires_reconciliation_when_completion_audit_fails'"
            ),
            (
                "uv run pytest tests/unit/test_tool_invocation_store.py -q -k "
                "'approved_pending_tool_invocation_claim or "
                "tool_invocation_claim_insert_is_conflict_safe'"
            ),
            (
                "uv run pytest tests/unit/test_langchain_tool_adapter.py -q -k "
                "'reuses_succeeded_idempotent_result or "
                "fails_closed_when_approval_audit_cannot_be_persisted or "
                "fails_closed_for_unresolved_idempotency_claim or "
                "fails_closed_when_idempotency_store_is_unavailable'"
            ),
            (
                "uv run pytest tests/unit/test_run_store.py tests/unit/test_run_service.py -q "
                "-k 'cancel_pending_approval_tool_invocations_query_excludes_executing_claims "
                "or approval_event_persistence_cancellation_records_cancelled'"
            ),
        ],
    ):
        return "tool invocation lifecycle contract missing"
    if not same_string_sequence(
        lifecycle_mapping.get("covers"),
        [
            "native_tool_claim_precedes_handler_execution",
            "native_claim_failure_skips_handler",
            "native_unresolved_claim_skips_handler",
            "native_succeeded_result_reused_without_handler",
            "langgraph_and_langchain_share_durable_execution_primitive",
            "langchain_approval_audit_failure_blocks_model_result",
            "idempotency_claim_failure_logs_exclude_exception_details",
            "completion_audit_failure_requires_reconciliation",
            "completion_audit_failure_skips_success_cache",
            "pending_approval_audit_failure_blocks_interrupt",
            "rejected_approval_audit_failure_blocks_completion",
            "pending_approval_claim_is_atomic_and_approval_bound",
            "pending_approval_claim_requires_request_checksum_and_marker",
            "pending_approval_replay_preserves_invocation_identity",
            "run_cancellation_cancels_only_unexecuted_approval_claims",
        ],
    ):
        return "tool invocation lifecycle contract missing"
    terminal_statuses = lifecycle_mapping.get("terminalStatuses")
    if not exact_string_set(terminal_statuses, {"succeeded", "failed", "cancelled"}):
        return "tool invocation lifecycle contract missing"
    for field_name in required_boolean_fields:
        if lifecycle_mapping.get(field_name) is not True:
            return "tool invocation lifecycle contract missing"
    return None


def durable_run_queue_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    durable_queue = item.get("durableRunQueue")
    if not isinstance(durable_queue, Mapping):
        return "durable run queue contract missing"
    durable_queue_mapping = cast(Mapping[str, object], durable_queue)
    required_text_fields = {
        "status": "verified",
        "store": "SqlAlchemyDurableStore",
        "queueModel": "RunQueue",
        "deadLetterModel": "DeadLetterJob",
        "expiredLeaseAction": "retry_or_dead_letter",
        "deadLetterReason": "run_queue_lease_attempts_exhausted",
    }
    for field_name, expected_value in required_text_fields.items():
        if durable_queue_mapping.get(field_name) != expected_value:
            return "durable run queue contract missing"
    if not exact_string_set(
        durable_queue_mapping.get("leasedStatuses"),
        {"queued", "retryable_failed"},
    ):
        return "durable run queue contract missing"
    if not exact_string_set(
        durable_queue_mapping.get("deadLetterPayloadFields"),
        {
            "attempt",
            "maxAttempts",
            "leaseOwner",
            "fencingToken",
            "queuePayload",
        },
    ):
        return "durable run queue contract missing"
    if durable_queue_mapping.get("fencingTokenRequired") is not True:
        return "durable run queue contract missing"
    diagnostics_surface = durable_queue_mapping.get("diagnosticsSurface")
    if durable_queue_diagnostics_surface_failure(diagnostics_surface):
        return "durable run queue contract missing"
    if scheduler_failure_boundary_failure(durable_queue_mapping.get("scheduledJobFailureBoundary")):
        return "durable run queue contract missing"
    return None


def outbox_inbox_lifecycle_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    lifecycle = item.get("outboxInboxLifecycle")
    if not isinstance(lifecycle, Mapping):
        return "outbox inbox lifecycle contract missing"
    lifecycle_mapping = cast(Mapping[str, object], lifecycle)
    required_text_fields = {
        "status": "verified",
        "store": "SqlAlchemyDurableStore",
        "outboxModel": "OutboxEvent",
        "inboxModel": "InboxEvent",
        "idempotencyModel": "IdempotencyRecord",
        "dispatcher": "OutboxDispatcher",
        "claimStrategy": "postgres_for_update_skip_locked",
        "idempotencyConstraint": "uq_outbox_events_idempotency",
        "inboxDeduplicationConstraint": "uq_inbox_events_source_event",
    }
    for field_name, expected_value in required_text_fields.items():
        if lifecycle_mapping.get(field_name) != expected_value:
            return "outbox inbox lifecycle contract missing"
    if not exact_string_set(
        lifecycle_mapping.get("outboxStatuses"),
        {"pending", "dispatching", "dispatched", "retryable_failed", "dead_lettered"},
    ):
        return "outbox inbox lifecycle contract missing"
    if not exact_string_set(
        lifecycle_mapping.get("inboxStatuses"),
        {"received", "processing", "processed", "ignored", "failed"},
    ):
        return "outbox inbox lifecycle contract missing"
    required_destinations = {
        "a2a.task.created",
        "a2a.task.updated",
        "slack.event_callback",
        "slack.slash_command",
        "slack.block_action",
    }
    if not exact_string_set(lifecycle_mapping.get("replayableDestinations"), required_destinations):
        return "outbox inbox lifecycle contract missing"
    required_lease_fields = {
        "lease_owner",
        "lease_expires_at",
        "attempt",
        "max_attempts",
    }
    if not exact_string_set(lifecycle_mapping.get("leaseFields"), required_lease_fields):
        return "outbox inbox lifecycle contract missing"
    for field_name in (
        "sideEffectsBeforeOutboxForbidden",
        "incomingEventsPersistedBeforeProcessing",
        "atLeastOnceDeliveryAssumed",
        "dispatcherDeadLettersUnsupportedRoutes",
        "retryableFailuresReclaimable",
        "staleLeaseOwnerCannotDispatch",
        "workerFailureErrorDetailsExcluded",
        "payloadReplayable",
    ):
        if lifecycle_mapping.get(field_name) is not True:
            return "outbox inbox lifecycle contract missing"
    if lifecycle_mapping.get("verificationSensors") != [
        "uv run pytest tests/unit/test_outbox_dispatcher.py -q "
        "-k 'marks_retryable_then_dead_letter or preserves_worker_retry_after_seconds'"
    ]:
        return "outbox inbox lifecycle contract missing"
    if lifecycle_mapping.get("covers") != ["outbox_worker_failure_uses_safe_durable_error_code"]:
        return "outbox inbox lifecycle contract missing"
    return None


def scheduler_failure_boundary_failure(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    boundary_mapping = cast(Mapping[str, object], value)
    required_text_fields = {
        "status": "verified",
        "worker": "SchedulerWorker",
        "executionRecord": "ScheduledJobExecutionRecord",
        "deadLetterRecord": "ScheduledJobDeadLetterRecord",
        "safeFailureCode": "scheduled_job_execution_failed",
    }
    for field_name, expected_value in required_text_fields.items():
        if boundary_mapping.get(field_name) != expected_value:
            return True
    if not exact_string_set(
        boundary_mapping.get("exceptionDetailsExcludedFrom"),
        {
            "execution.result",
            "job.last_result",
            "dead_letter.reason",
            "dead_letter.result",
        },
    ):
        return True
    if boundary_mapping.get("retrySemanticsPreserved") is not True:
        return True
    if boundary_mapping.get("verificationSensors") != [
        "uv run pytest tests/unit/test_scheduler_worker.py -q "
        "-k dead_letters_after_retry_exhaustion"
    ]:
        return True
    if boundary_mapping.get("covers") != ["scheduler_failure_uses_safe_durable_error_code"]:
        return True
    return False


def durable_queue_diagnostics_surface_failure(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    diagnostics_surface = cast(Mapping[str, object], value)
    if diagnostics_surface.get("status") != "verified":
        return True
    if diagnostics_surface.get("dashboardFacet") != "ops.dashboard.durableQueue":
        return True
    if diagnostics_surface.get("tenantScoped") is not True:
        return True
    if diagnostics_surface.get("missingStoreStatus") != "unavailable":
        return True
    if not exact_string_set(
        diagnostics_surface.get("apiPaths"),
        {
            "/api/admin/durable-queue/diagnostics",
            "/v1/admin/durable-queue/diagnostics",
        },
    ):
        return True
    if not exact_string_set(
        diagnostics_surface.get("requiredCountFields"),
        {
            "queueStatusCounts",
            "queueBacklog",
            "leasedCount",
            "deadLetterCount",
        },
    ):
        return True
    if not exact_string_set(
        diagnostics_surface.get("releaseReviewFields"),
        {
            "leaseRecovery",
            "deadLetterReason",
            "fencingTokenRequired",
        },
    ):
        return True
    return durable_queue_remediation_actions_failure(diagnostics_surface.get("remediationActions"))


def durable_queue_remediation_actions_failure(value: object) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray) or not value:
        return True
    for action in cast(Sequence[object], value):
        if not isinstance(action, Mapping):
            continue
        action_mapping = cast(Mapping[str, object], action)
        if action_mapping.get("name") != "release_expired_leases":
            continue
        if action_mapping.get("permission") != "settings:write":
            return True
        if action_mapping.get("auditCategory") != "durable_queue":
            return True
        if action_mapping.get("auditAction") != "UPDATE":
            return True
        if action_mapping.get("resourceType") != "run_queue":
            return True
        if action_mapping.get("resourceId") != "release_expired":
            return True
        return not exact_string_set(
            action_mapping.get("apiPaths"),
            {
                "/api/admin/durable-queue/release-expired",
                "/v1/admin/durable-queue/release-expired",
            },
        )
    return True


def rag_ingestion_lifecycle_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    if item.get("status") != "passed":
        return None
    lifecycle = item.get("ragIngestionLifecycle")
    if not isinstance(lifecycle, Mapping):
        return "rag ingestion lifecycle contract missing" if name == "hardening_suite" else None
    lifecycle_mapping = cast(Mapping[str, object], lifecycle)
    expected_text_fields = {
        "status": "verified",
        "framework": "langchain-postgres",
        "vectorStore": "PGVector",
        "embeddingBoundary": "LangChainEmbeddings",
    }
    for field_name, expected_value in expected_text_fields.items():
        if lifecycle_mapping.get(field_name) != expected_value:
            return "rag ingestion lifecycle contract missing"
    for field_name in (
        "sourceAllowlistRequired",
        "mimeAllowlistRequired",
        "sizeLimitRequired",
        "checksumIdempotency",
        "backgroundRetries",
        "quarantineBeforeIndex",
        "humanReviewRequiredForCapturedCandidates",
        "aclMetadataRequired",
        "aclBeforeRanking",
        "retrievalResultsReauthorized",
        "retrievalResultLimitEnforced",
        "rawAclRedactedFromModelContext",
        "reindexAuditRequired",
    ):
        if lifecycle_mapping.get(field_name) is not True:
            return "rag ingestion lifecycle contract missing"
    allowed_lifecycle_fields = set(expected_text_fields) | {
        "sourceAllowlistRequired",
        "mimeAllowlistRequired",
        "sizeLimitRequired",
        "checksumIdempotency",
        "backgroundRetries",
        "quarantineBeforeIndex",
        "humanReviewRequiredForCapturedCandidates",
        "aclMetadataRequired",
        "aclBeforeRanking",
        "retrievalResultsReauthorized",
        "retrievalResultLimitEnforced",
        "rawAclRedactedFromModelContext",
        "toolOutputBoundary",
        "reindexAuditRequired",
        "poisoningEvalCaseIds",
        "verificationSensors",
        "diagnosticsSurface",
    }
    if set(lifecycle_mapping) != allowed_lifecycle_fields:
        return "rag ingestion lifecycle contract missing"
    eval_case_ids = lifecycle_mapping.get("poisoningEvalCaseIds")
    if not non_empty_string_sequence(eval_case_ids) or set(
        cast(Sequence[str], eval_case_ids)
    ) != set(REQUIRED_LANGSMITH_EVAL_CASE_IDS):
        return "rag ingestion lifecycle contract missing"
    verification_sensors = lifecycle_mapping.get("verificationSensors")
    if rag_verification_sensors_contract_failure(verification_sensors):
        return "rag ingestion lifecycle contract missing"
    diagnostics_surface = lifecycle_mapping.get("diagnosticsSurface")
    if rag_ingestion_diagnostics_surface_failure(diagnostics_surface):
        return "rag ingestion lifecycle contract missing"
    if rag_tool_output_boundary_contract_failure(lifecycle_mapping.get("toolOutputBoundary")):
        return "rag ingestion lifecycle contract missing"
    return None


def rag_tool_output_boundary_contract_failure(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    mapping = cast(Mapping[str, object], value)
    required_fields = {
        "auditPayloadPreserved",
        "contextManifestAclHashPreserved",
        "nativeToolMessageAclEvidenceExcluded",
        "langchainToolNodeAclEvidenceExcluded",
        "responseFilterInsightsAclEvidenceExcluded",
        "recursiveCaseInsensitiveAclKeyFiltering",
        "citationLabelsPreserved",
        "langchainContentAndArtifactMode",
        "langchainOutputLabeled",
        "langchainSecretRedaction",
        "langchainTruncationSafe",
        "langchainArtifactSanitized",
        "langchainGuardFindingsPersisted",
        "langchainGuardManifestChecksummed",
        "langchainInvokeAndStreamGuardParity",
        "toolArtifactContentBoundToToolMessage",
        "toolArtifactContentMismatchFailsClosed",
        "toolArtifactContentMismatchInvokeStreamParity",
        "toolMessageLabelRequired",
        "unlabeledToolOutputFailsClosed",
        "unlabeledToolOutputInvokeStreamParity",
        "mappingWrappedToolMessagesGuarded",
        "commandWrappedToolMessagesGuarded",
        "rawSanitizedOutputExcludedFromManifest",
        "boundedRuntimeRagCitationArtifact",
        "runtimeRagCitationPromotionBeforeStructuredBoundary",
        "langchainInvokeAndStreamCitationParity",
        "runtimeRagCitationFieldsAllowlisted",
        "runtimeRagCitationLengthsBounded",
        "invalidRuntimeRagCitationIdsFailClosed",
        "invalidRuntimeRagCitationValuesExcluded",
        "invalidRuntimeRagCitationInvokeStreamParity",
        "invalidRuntimeRagCitationCountProjected",
        "invalidCitationIdsExcludedFromGroundingCounts",
        "nativeRagCitationBoundarySharedWithLangChain",
        "nativeRagCitationFieldsAndLengthsBounded",
        "invalidNativeRagCitationIdsCountOnly",
        "invalidNativeRagCitationValuesExcluded",
        "citationChunkIdentityRequired",
        "orphanCitationIdsExcludedFromGroundingCounts",
        "duplicateCitationIdsExcludedFromGroundingCounts",
        "orphanAndDuplicateCitationClaimsFailClosed",
        "citationProvenanceFieldsMatchReturnedChunk",
        "mismatchedCitationProvenanceExcluded",
        "mismatchedCitationProvenanceFailClosed",
        "mismatchedCitationProvenanceInvokeStreamParity",
        "duplicateChunkCitationIdsExcludedFromGroundingCounts",
        "duplicateChunkCitationIdsDoNotUseLastWriteWins",
        "duplicateChunkCitationIdsFailClosed",
        "duplicateChunkCitationIdInvokeStreamParity",
        "nativeExplicitCitationIdentityAuthoritative",
        "legacyDocumentKeyFallbackCannotOverrideExplicitId",
        "conflictingExplicitCitationIdsExcluded",
        "conflictingExplicitCitationIdsFailClosed",
        "missingOrInvalidChunkCitationIdsCountOnly",
        "noncanonicalCitationIdsRejected",
        "noncanonicalManifestCitationIdsRejected",
        "chunksWithoutSafeCitationIdsRemainUncited",
        "partialRagGroundingFailsClosed",
        "invalidChunkCitationIdInvokeStreamParity",
        "runtimeRagCitationCardinalityBounded",
        "runtimeRagCitationLimitAlignedWithSearch",
        "omittedRuntimeRagCitationValuesExcluded",
        "omittedRuntimeRagCitationsFailClosed",
        "omittedRuntimeRagCitationInvokeStreamParity",
        "versionedReactorToolArtifactContract",
        "runtimeRagArtifactContractValidated",
        "runtimeRagArtifactManifestBoundToDurableEnvelope",
        "mismatchedRagArtifactManifestRejected",
        "failedRagArtifactCitationClaimsRejected",
        "foreignSchemaRagArtifactCitationClaimsRejected",
        "invalidRagArtifactValuesExcluded",
        "invalidRagArtifactInvokeStreamParity",
        "durableToolEnvelopeVersioned",
        "langchainInterruptReadsCheckpointMessages",
        "langchainInterruptRagEvidencePersisted",
        "artifactlessCheckpointToolOutputChecksummed",
        "hitlResumeRuntimeEvidenceSnapshotStable",
        "hitlResumeNoRagDoubleCount",
        "streamRuntimeEvidenceDeltaMode",
        "rawDurableToolOutputExcludedFromManifest",
        "pinnedReplayInvocationCheckpointPreserved",
        "postInterruptCheckpointPinRemovedFromReadCopy",
        "postInterruptLatestChildCheckpointRead",
        "postInterruptReadDoesNotMutateInvocationConfig",
        "checkpointReadFailurePreservesInterrupt",
        "checkpointReadFailureMetadataSecretFree",
        "checkpointReadCancellationPropagated",
        "repeatedHitlLatestPendingAction",
        "repeatedHitlApprovedToolExactlyOnce",
        "repeatedHitlFinalApprovalCompletes",
    }
    return set(mapping) != required_fields or any(
        mapping.get(field_name) is not True for field_name in required_fields
    )


def rag_verification_sensors_contract_failure(verification_sensors: object) -> bool:
    if not isinstance(verification_sensors, Mapping):
        return True
    mapping = cast(Mapping[str, object], verification_sensors)
    if set(mapping) != {"focusedTests", "releaseReadinessContracts", "covers"}:
        return True
    if not same_string_sequence(
        mapping.get("focusedTests"),
        [
            (
                "uv run pytest tests/unit/test_rag_document_management.py "
                "tests/unit/test_rag_retriever.py tests/unit/test_rag_vector_store.py "
                "tests/unit/test_rag_tool.py -q"
            ),
            "uv run pytest tests/unit/test_prompt_assembler.py -q -k rag",
            "uv run pytest tests/unit/test_structured_output.py -q -k 'rag and citation'",
            (
                "uv run pytest tests/unit/test_agent_graph_policy.py "
                "-q -k 'research_profile_marks_plan or "
                "removes_rag_acl_evidence_from_model_visible_tool_message'"
            ),
            (
                "uv run pytest tests/unit/test_langchain_tool_adapter.py "
                "-q -k 'executes_through_reactor_tool_handler or "
                "hides_acl_evidence_but_preserves_audit_payload or "
                "bounded_citation_evidence_drops_unbounded_and_private_fields or "
                "bounded_citation_evidence_rejects_noncanonical_citation_ids or "
                "records_oversized_citation_id or "
                "excludes_orphan_citations_from_grounding_counts or "
                "deduplicates_citations_in_grounding_counts or "
                "rejects_mismatched_citation_provenance or "
                "rejects_duplicate_chunk_citation_ids or "
                "counts_chunks_without_safe_citation_ids or "
                "bounds_citation_evidence_cardinality or "
                "labels_and_redacts_model_visible_result or "
                "keeps_truncated_result_as_safe_artifact'"
            ),
            (
                "uv run pytest tests/unit/test_langchain_agent.py "
                "-q -k 'records_tool_output_guard_manifest or "
                "blocks_tool_artifact_content_mismatch or "
                "blocks_unlabeled_tool_output or "
                "promotes_runtime_rag_citations_before_boundary or "
                "blocks_oversized_runtime_rag_citation_id or "
                "blocks_orphan_runtime_rag_citation_claims or "
                "blocks_omitted_runtime_rag_citations or "
                "blocks_rag_artifact_manifest_mismatch or "
                "blocks_failed_rag_artifact_citation_claims or "
                "hitl_resume_does_not_double_count_checkpoint_rag or "
                "durable_rag_context_metadata_rejects_foreign_schema_claim or "
                "durable_interrupt_messages_reads_latest_after_pinned_replay or "
                "preserves_interrupt_when_checkpoint_read_fails or "
                "propagates_checkpoint_read_cancellation or "
                "repeated_hitl_resumes_latest_pending_action'"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py "
                "-q -k 'langchain_stream_records_tool_output_guard_manifest or "
                "langchain_stream_blocks_tool_artifact_content_mismatch or "
                "stream_promotes_runtime_rag_citations_before_boundary or "
                "stream_blocks_oversized_runtime_rag_citation_id or "
                "stream_blocks_orphan_runtime_rag_citation_claims or "
                "stream_blocks_omitted_runtime_rag_citations or "
                "stream_blocks_rag_artifact_manifest_mismatch or "
                "stream_blocks_failed_rag_artifact_citation_claims'"
            ),
            ("uv run pytest tests/unit/test_documents_cli.py -q -k 'ask and citation'"),
            ("uv run pytest tests/unit/test_eval_regression_suite_apply.py -q -k documents_ask"),
            (
                "uv run pytest tests/unit/test_rag_ingestion_candidate_ids.py "
                "tests/unit/test_runs_cli.py -q -k candidate"
            ),
            (
                "uv run pytest tests/unit/test_rag_candidate_actions.py "
                "tests/unit/test_dress_api_smoke.py -q"
            ),
            (
                "uv run pytest tests/unit/test_feedback_router.py "
                "tests/unit/test_documents_cli.py -q -k "
                "'preserve_feedback_id_on_rag_candidate_handoff or "
                "candidate_ask_missing_citation_uses_candidate_eval_handoff or "
                "langsmith_report_preserves_rating_only_feedback_queue'"
            ),
            (
                "uv run pytest tests/unit/test_release_readiness_evidence.py "
                "-q -k 'eval_apply_boundary or without_eval_apply_coverage'"
            ),
            "uv run pytest tests/integration/test_rag_ingestion_candidates_api.py -q",
            "uv run pytest tests/integration/test_feedback_api.py -q -k rag_candidate",
            (
                "uv run pytest tests/integration/test_feedback_api.py -q "
                "-k 'admin_submit_returns_review_next_actions or stats_export'"
            ),
            (
                "uv run pytest tests/integration/test_feedback_api.py -q "
                "-k 'citation_marker and memory'"
            ),
        ],
    ):
        return True
    if not same_string_sequence(
        mapping.get("releaseReadinessContracts"),
        [
            "ragIngestionLifecycle",
            "contextManifestDiagnostics.ragGroundingPolicy",
            "researchAnswerContract",
            "ragIngestionLifecycle.toolOutputBoundary",
        ],
    ):
        return True
    return not same_string_sequence(
        mapping.get("covers"),
        [
            "managed_document_ingest_requires_acl",
            "retrieval_filters_acl_before_ranking",
            "rag_tool_revalidates_retriever_results_before_model_output",
            "rag_tool_caps_retriever_results_to_requested_limit",
            "rag_tool_results_promote_citations_to_context",
            "native_and_langchain_tool_outputs_exclude_acl_evidence",
            "audit_and_context_manifest_preserve_acl_hash_evidence",
            "langchain_tool_node_labels_and_redacts_model_visible_results",
            "langchain_tool_node_truncation_preserves_safe_artifact",
            "langchain_invoke_and_stream_guard_findings_persisted",
            "langchain_tool_artifact_content_mismatch_fails_closed",
            "unlabeled_langchain_tool_output_fails_closed",
            "mapping_wrapped_langchain_tool_messages_are_guarded",
            "command_wrapped_langgraph_tool_messages_are_guarded",
            "tool_output_manifest_excludes_sanitized_content",
            "runtime_rag_citations_promoted_before_structured_output_validation",
            "runtime_rag_citation_artifacts_are_bounded_and_allowlisted",
            "langchain_invoke_and_stream_runtime_citation_parity",
            "invalid_runtime_rag_citation_ids_fail_closed",
            "invalid_runtime_rag_citation_values_excluded_from_manifest",
            "langchain_invoke_and_stream_invalid_citation_parity",
            "public_run_metadata_preserves_invalid_citation_count",
            "native_rag_citations_share_bounded_normalization",
            "invalid_native_rag_citations_are_count_only",
            "invalid_native_rag_citation_values_are_not_persisted",
            "rag_citations_require_returned_chunk_identity",
            "orphan_and_duplicate_citations_do_not_inflate_grounding_counts",
            "orphan_and_duplicate_citation_claims_fail_closed",
            "citation_provenance_fields_match_returned_chunks",
            "mismatched_citation_provenance_is_not_persisted",
            "mismatched_citation_provenance_fails_closed_with_invoke_stream_parity",
            "duplicate_chunk_citation_ids_do_not_inflate_grounding_counts",
            "duplicate_chunk_citation_ids_do_not_use_last_write_wins",
            "duplicate_chunk_citation_ids_fail_closed_with_invoke_stream_parity",
            "native_explicit_citation_identity_is_authoritative",
            "legacy_document_key_fallback_cannot_alias_explicit_citation_ids",
            "conflicting_explicit_citation_ids_are_excluded_and_fail_closed",
            "missing_or_invalid_chunk_citation_ids_are_count_only",
            "noncanonical_citation_ids_are_not_normalized",
            "noncanonical_manifest_citation_ids_fail_closed",
            "chunks_without_safe_citation_ids_remain_uncited",
            "partial_rag_grounding_fails_closed_with_invoke_stream_parity",
            "runtime_rag_citation_evidence_is_limited_to_search_maximum",
            "omitted_runtime_rag_citation_values_are_not_persisted",
            "omitted_runtime_rag_citations_fail_closed",
            "langchain_invoke_and_stream_omitted_citation_parity",
            "reactor_tool_artifacts_are_versioned",
            "runtime_rag_artifacts_require_successful_reactor_contract",
            "runtime_rag_artifact_manifest_is_bound_to_durable_envelope",
            "mismatched_runtime_rag_artifact_manifest_fails_closed_with_invoke_stream_parity",
            "failed_and_foreign_schema_citation_claims_fail_closed",
            "invalid_runtime_rag_artifact_values_are_not_persisted",
            "langchain_invoke_and_stream_invalid_artifact_parity",
            "durable_tool_content_envelopes_are_versioned",
            "langchain_interrupt_reads_messages_from_checkpoint_saver",
            "interrupt_rag_and_tool_guard_evidence_is_persisted",
            "artifactless_checkpoint_tool_output_is_checksum_only",
            "hitl_resume_replaces_runtime_snapshot_counts",
            "hitl_resume_does_not_double_count_rag_evidence",
            "stream_runtime_evidence_remains_delta_merged",
            "raw_durable_tool_output_is_excluded_from_manifest",
            "pinned_checkpoint_id_remains_on_graph_invocation",
            "post_interrupt_read_drops_pin_from_config_copy_only",
            "post_interrupt_read_uses_latest_child_checkpoint",
            "trusted_invocation_config_is_not_mutated",
            "checkpoint_read_failure_preserves_interrupt_result",
            "checkpoint_read_failure_metadata_excludes_error_details",
            "checkpoint_read_cancellation_is_not_swallowed",
            "repeated_hitl_exposes_only_latest_pending_action",
            "each_approved_tool_executes_exactly_once",
            "repeated_hitl_completes_after_final_approval",
            "weak_documents_ask_answers_promote_to_eval_with_citation_markers",
            "documents_ask_review_done_action_closes_feedback_queue",
            "rag_candidate_eval_handoff_uses_canonical_candidate_ids",
            "rag_candidate_hardening_report_action_exposed_before_readiness",
            "api_smoke_requires_readiness_action_fields",
            "rag_candidate_feedback_review_handoff_exercised",
            "rag_candidate_feedback_actions_scope_inferred_candidate_tag",
            "rag_candidate_feedback_bulk_review_action_closes_candidate_queue",
            "rag_candidate_ask_action_preserves_feedback_tags",
            "rag_candidate_minor_boundary_requires_eval_apply_coverage",
            "rag_candidate_eval_apply_boundary_remediation_exposed",
            "memory_feedback_review_handoff_preserved_while_citation_marker_is_required",
        ],
    )


def rag_ingestion_diagnostics_surface_failure(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    diagnostics_surface = cast(Mapping[str, object], value)
    if diagnostics_surface.get("status") != "verified":
        return True
    if not exact_string_set(
        diagnostics_surface.get("apiPaths"),
        {
            "/api/admin/rag/ingestion-jobs/{job_id}",
            "/v1/rag/ingestion-jobs/{job_id}",
        },
    ):
        return True
    return not exact_string_set(
        diagnostics_surface.get("releaseReviewFields"),
        {
            "sourceAllowlist",
            "mimeAllowlist",
            "sizeLimitBytes",
            "checksum",
            "chunkCount",
            "aclHash",
            "quarantineStatus",
            "retryCount",
            "poisoningFindings",
        },
    )


def artifact_lifecycle_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    lifecycle = item.get("artifactLifecycle")
    if not isinstance(lifecycle, Mapping):
        return "artifact lifecycle contract missing"
    lifecycle_mapping = cast(Mapping[str, object], lifecycle)
    allowed_lifecycle_fields = {
        "status",
        "storage",
        "referenceBoundary",
        "graphStateStoresReferencesOnly",
        "blobBodiesExcludedFromGraphState",
        "metadataRequired",
        "accessPolicy",
        "ingestionPolicy",
        "retentionPolicy",
    }
    if set(lifecycle_mapping) != allowed_lifecycle_fields:
        return "artifact lifecycle contract missing"
    if lifecycle_mapping.get("status") != "verified":
        return "artifact lifecycle contract missing"
    if lifecycle_mapping.get("referenceBoundary") != "ArtifactReference":
        return "artifact lifecycle contract missing"
    for field_name in ("graphStateStoresReferencesOnly", "blobBodiesExcludedFromGraphState"):
        if lifecycle_mapping.get(field_name) is not True:
            return "artifact lifecycle contract missing"

    storage = lifecycle_mapping.get("storage")
    if not isinstance(storage, Mapping):
        return "artifact lifecycle contract missing"
    storage_mapping = cast(Mapping[str, object], storage)
    if set(storage_mapping) != {"production", "local", "metadataStore"}:
        return "artifact lifecycle contract missing"
    if (
        storage_mapping.get("production") != "s3-compatible"
        or storage_mapping.get("local") != "filesystem"
        or storage_mapping.get("metadataStore") != "postgres"
    ):
        return "artifact lifecycle contract missing"

    if not exact_string_set(
        lifecycle_mapping.get("metadataRequired"),
        {
            "artifact_id",
            "tenant_id",
            "owner_user_id",
            "mime_type",
            "size_bytes",
            "sha256",
            "acl",
            "retention_days",
            "source_run_id",
        },
    ):
        return "artifact lifecycle contract missing"

    access_policy = lifecycle_mapping.get("accessPolicy")
    if artifact_lifecycle_mapping_missing_true_fields(
        access_policy,
        (
            "shortLivedSignedUrls",
            "authenticatedStreamingEndpointSupported",
            "tenantAclEnforcedBeforeDownload",
            "signedUrlExpiryTested",
        ),
    ):
        return "artifact lifecycle contract missing"

    ingestion_policy = lifecycle_mapping.get("ingestionPolicy")
    if artifact_lifecycle_mapping_missing_true_fields(
        ingestion_policy,
        (
            "mimeSniffingRequired",
            "mimeAllowlistRequired",
            "sizeLimitRequired",
            "checksumIdempotency",
            "parserAllowlistRequired",
            "parserSandboxingRequired",
            "spoofingRegressionTested",
            "parserFailureQuarantinesArtifact",
        ),
    ):
        return "artifact lifecycle contract missing"

    retention_policy = lifecycle_mapping.get("retentionPolicy")
    if artifact_lifecycle_mapping_missing_true_fields(
        retention_policy,
        (
            "tenantRetentionApplied",
            "deleteOrTombstoneDerivedEmbeddings",
            "tombstoneAuditRequired",
        ),
    ):
        return "artifact lifecycle contract missing"
    return None


def artifact_lifecycle_mapping_missing_true_fields(
    value: object,
    fields: Sequence[str],
) -> bool:
    if not isinstance(value, Mapping):
        return True
    mapping = cast(Mapping[str, object], value)
    if set(mapping) != set(fields):
        return True
    return any(mapping.get(field_name) is not True for field_name in fields)


def prompt_release_lifecycle_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    lifecycle = item.get("promptReleaseLifecycle")
    if not isinstance(lifecycle, Mapping):
        return "prompt release lifecycle contract missing"
    lifecycle_mapping = cast(Mapping[str, object], lifecycle)
    expected_text_fields = {
        "status": "verified",
        "store": "SqlAlchemyPromptStore",
        "versionModel": "PromptVersionRecord",
        "releaseModel": "PromptReleaseRecord",
        "templateBoundary": "ChatPromptTemplate",
    }
    expected_boolean_fields = {
        "contentHashRequired",
        "renderedChecksumRequired",
        "evalGateRequired",
        "langsmithDatasetRequired",
        "baselineComparisonRequired",
        "promptWritePermissionRequired",
        "releaseAuditRequired",
        "rollbackTargetRequired",
        "noDynamicPromptDeserialization",
    }
    expected_collection_fields = {"metadataFields", "diagnosticsSurface", "evalGate"}
    allowed_lifecycle_fields = (
        set(expected_text_fields) | expected_boolean_fields | expected_collection_fields
    )
    if set(lifecycle_mapping) != allowed_lifecycle_fields:
        return "prompt release lifecycle contract missing"
    for field_name, expected_value in expected_text_fields.items():
        if lifecycle_mapping.get(field_name) != expected_value:
            return "prompt release lifecycle contract missing"
    for field_name in expected_boolean_fields:
        if lifecycle_mapping.get(field_name) is not True:
            return "prompt release lifecycle contract missing"
    if not exact_string_set(
        lifecycle_mapping.get("metadataFields"),
        {
            "promptReleaseId",
            "templateId",
            "versionId",
            "environment",
            "contentHash",
            "renderedChecksum",
            "evalDatasetName",
            "evalExperimentId",
            "baselineVersionId",
            "candidateVersionId",
            "releasedBy",
        },
    ):
        return "prompt release lifecycle contract missing"
    diagnostics_surface = lifecycle_mapping.get("diagnosticsSurface")
    if prompt_release_diagnostics_surface_failure(diagnostics_surface):
        return "prompt release lifecycle contract missing"
    eval_gate = lifecycle_mapping.get("evalGate")
    if prompt_release_eval_gate_failure(eval_gate):
        return "prompt release lifecycle contract missing"
    return None


def prompt_release_eval_gate_failure(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    eval_gate = cast(Mapping[str, object], value)
    expected_text_fields = {
        "sourceSuite": "tests/fixtures/agent-eval/regression-suite.json",
        "datasetName": "reactor-regression",
        "requiredSplit": "regression",
        "langsmithReportName": "langsmith_eval_sync",
    }
    if set(eval_gate) != set(expected_text_fields) | {"caseIds", "splitCounts"}:
        return True
    for field_name, expected_value in expected_text_fields.items():
        if eval_gate.get(field_name) != expected_value:
            return True
    case_ids = eval_gate.get("caseIds")
    if not exact_string_set(case_ids, set(REQUIRED_PROMPT_RELEASE_EVAL_CASE_IDS)):
        return True
    split_counts = eval_gate.get("splitCounts")
    if not isinstance(split_counts, Mapping):
        return True
    split_counts_mapping = cast(Mapping[str, object], split_counts)
    if set(split_counts_mapping) != {"regression"}:
        return True
    regression_count = split_counts_mapping.get("regression")
    return (
        not isinstance(regression_count, int)
        or isinstance(regression_count, bool)
        or regression_count != len(REQUIRED_PROMPT_RELEASE_EVAL_CASE_IDS)
    )


def prompt_release_diagnostics_surface_failure(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    diagnostics_surface = cast(Mapping[str, object], value)
    if set(diagnostics_surface) != {"status", "apiPaths", "releaseReviewFields"}:
        return True
    if diagnostics_surface.get("status") != "verified":
        return True
    if not exact_string_set(
        diagnostics_surface.get("apiPaths"),
        {
            "/api/admin/prompts/templates/{template_id}/releases",
            "/v1/admin/prompts/templates/{template_id}/releases",
        },
    ):
        return True
    return not exact_string_set(
        diagnostics_surface.get("releaseReviewFields"),
        {
            "promptReleaseId",
            "contentHash",
            "renderedChecksum",
            "evalDatasetName",
            "evalExperimentId",
            "recommendation",
            "rollbackTarget",
        },
    )


def approval_lifecycle_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    lifecycle = item.get("approvalLifecycle")
    if not isinstance(lifecycle, Mapping):
        return "approval lifecycle contract missing"
    lifecycle_mapping = cast(Mapping[str, object], lifecycle)
    expected_text_fields = {
        "status": "verified",
        "runtimePause": "langgraph_interrupts_or_langchain_hitl",
        "store": "SqlAlchemyApprovalStore",
        "requestModel": "ApprovalRequest",
        "decisionModel": "ApprovalDecision",
        "rowModel": "PendingApproval",
        "pendingStatus": "pending",
        "resumeClaimStore": "SqlAlchemyRunStore",
        "resumeClaimTransition": "interrupted_to_running",
        "resumeClaimAuditEvent": "run.resume_claimed",
    }
    expected_boolean_fields = {
        "rbacRequired",
        "tenantScoped",
        "runAccessChecked",
        "decisionReasonRequiredOnReject",
        "rejectionReasonValidatedAtApiBoundary",
        "resumeProvenanceRequired",
        "checkpointProvenanceRequiredBeforeApproval",
        "resumeFollowupCheckpointProvenanceRequiredBeforeApproval",
        "langgraphResumeCheckpointProvenanceRefreshed",
        "langchainResumeCheckpointProvenanceRefreshed",
        "auditRequired",
        "expirySupported",
        "sideEffectsBeforeApprovalForbidden",
        "slackDecisionRouteSupported",
        "atomicResumeClaim",
        "duplicateResumeFailsClosed",
        "tenantScopedResumeClaim",
        "rawToolInputExcludedFromResumeClaimAudit",
        "resumeClaimRuntimeAccurate",
        "resumeRuntimeUnavailablePreservesInterruptedRun",
        "nativeLangGraphInterruptsEnabledInDatabaseRuntime",
        "nativeLangGraphDirectInterruptPersisted",
        "nativeLangGraphStreamingInterruptPersisted",
        "nativeLangGraphFollowupInterruptPersisted",
        "runtimeResumeApprovalStateMatched",
        "resumeDecisionUsesDurableProvenance",
        "resumeApprovalBooleanStrict",
        "langchainHitlSingleDecisionRequired",
        "langchainHitlEditDecisionForbidden",
        "langchainHitlControlFieldsForbidden",
        "langchainHitlResumeValidatedBeforeInvoke",
        "persistedRunResumeIdentityAuthoritative",
        "resumeCheckpointIdentityMismatchFailsClosed",
        "persistedRunRuntimeOwnerStatusAuthoritative",
        "resumeIdentityCheckedBeforeClaim",
        "approvalRequestRuntimeAuthoritative",
        "approvalRequestThreadIdentityRequired",
        "approvalRequestCheckpointNamespaceRequired",
        "approvalResumeProvenanceMismatchFailsClosed",
        "approvalResumeProvenanceCheckedBeforeClaim",
        "langchainResumeApprovalLookupCancellationPersisted",
        "langchainResumeApprovalLookupFailureFailsClosed",
        "langgraphResumeApprovalLookupCancellationPersisted",
        "langgraphResumeApprovalLookupFailureFailsClosed",
        "langgraphResumeToolPolicyCancellationPersisted",
        "langgraphResumeToolPolicyFailureFailsClosed",
        "unsupportedPersistedResumeRuntimeFailsClosed",
        "resumeRuntimeValidatedBeforeDispatch",
        "approvedToolRevalidatedBeforeResume",
        "currentToolCatalogIdentityRequired",
        "currentToolPolicyBudgetApplied",
        "missingToolProviderFailsClosed",
        "inactiveApprovedToolFailsClosed",
        "rejectedResumeAllowsInactiveTool",
        "approvalToolCheckedBeforeClaim",
        "missingDecisionActorFailsClosed",
        "resumeAuditActorsSeparated",
        "resumeTerminalAuditAtomic",
        "failedResumeExcludesSuccessAudit",
        "nativeResumeTimeoutEnforced",
        "nativeResumeGuardFailClosed",
        "nativeResumeProviderUsageRecorded",
        "nativeResumeResponseMetadataPreserved",
        "nativeResumeRunMetadataPreserved",
        "nativeResumeRuntimeFailurePersisted",
        "langchainResumeRuntimeFailurePersisted",
        "approvalPersistenceFailureFailClosed",
        "approvalPersistenceFailureRecorded",
        "streamApprovalPersistenceFailureCompletes",
        "streamApprovalEventAfterPersistence",
        "failedApprovalPersistenceSuppressesPendingEvent",
        "streamApprovalEventIncludesPersistedId",
        "persistedApprovalIdReplayable",
        "approvalToolInputExcludedFromReplay",
        "approvalPersistenceErrorDetailsExcluded",
        "approvalPersistenceCancellationPropagated",
        "approvalPersistenceIdValidated",
        "runCancellationCancelsPendingApprovalsAtomically",
    }
    expected_collection_fields = {
        "terminalStatuses",
        "metadataFields",
        "apiPaths",
        "resumeClaimPayloadFields",
        "resumeRuntimes",
        "verificationSensors",
        "covers",
    }
    allowed_lifecycle_fields = (
        set(expected_text_fields) | expected_boolean_fields | expected_collection_fields
    )
    if set(lifecycle_mapping) != allowed_lifecycle_fields:
        return "approval lifecycle contract missing"
    for field_name, expected_value in expected_text_fields.items():
        if lifecycle_mapping.get(field_name) != expected_value:
            return "approval lifecycle contract missing"
    if not exact_string_set(
        lifecycle_mapping.get("terminalStatuses"),
        {"approved", "rejected", "expired", "cancelled"},
    ):
        return "approval lifecycle contract missing"
    for field_name in expected_boolean_fields:
        if lifecycle_mapping.get(field_name) is not True:
            return "approval lifecycle contract missing"
    if not exact_string_set(
        lifecycle_mapping.get("resumeRuntimes"),
        {"langgraph", "langchain_agent"},
    ):
        return "approval lifecycle contract missing"
    if not same_string_sequence(
        lifecycle_mapping.get("verificationSensors"),
        [
            (
                "uv run pytest tests/unit/test_runs_router.py -q -k "
                "resume_run_request_requires_strict_boolean_approval"
            ),
            (
                "uv run pytest tests/integration/test_api.py -q -k "
                "approval_reject_requires_nonblank_reason"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "'fails_closed_when_approval_storage_raises or "
                "stream_completes_failed_when_approval_storage_raises or "
                "propagates_approval_storage_cancellation or "
                "approval_storage_returns_blank_id or "
                "stream_persists_redacted_langchain_v2_interrupt or "
                "stream_persists_redacted_native_langgraph_interrupt'"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "'resume_fails_closed_when_checkpoint_identity_differs_from_persisted_run or "
                "resume_uses_persisted_runtime_owner_and_status or "
                "resume_fails_closed_when_approval_request_provenance_differs or "
                "resume_fails_closed_for_unsupported_persisted_runtime or "
                "resume_without_graph_preserves_unclaimed_interrupted_run or "
                "resume_fails_closed_when_approved_tool_is_no_longer_active or "
                "rejected_resume_does_not_require_tool_to_remain_active'"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "'resume_does_not_request_followup_approval_without_checkpoint or "
                "native_langgraph_resume_persists_a_followup_interrupt or "
                "langchain_resume_persists_followup_interrupt_checkpoint'"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "langchain_resume_approval_lookup_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "langchain_resume_approval_lookup_failure_fails_closed"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "langgraph_resume_approval_lookup_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "langgraph_resume_approval_lookup_failure_fails_closed"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "langgraph_resume_tool_policy_cancellation_persists_terminal_state"
            ),
            (
                "uv run pytest tests/unit/test_run_service.py -q -k "
                "langgraph_resume_tool_policy_failure_fails_closed"
            ),
            (
                "uv run pytest tests/integration/test_api.py -q -k "
                "stream_events_endpoint_preserves_approval_id_without_tool_input"
            ),
            (
                "uv run pytest tests/unit/test_run_store.py tests/unit/test_run_service.py -q "
                "-k 'cancel_pending_run_approvals_query_is_tenant_and_run_scoped or "
                "approval_event_persistence_cancellation_records_cancelled'"
            ),
        ],
    ):
        return "approval lifecycle contract missing"
    if not same_string_sequence(
        lifecycle_mapping.get("covers"),
        [
            "approval_persistence_failure_returns_failed_run",
            "approval_persistence_failure_is_recorded",
            "stream_approval_persistence_failure_emits_completion",
            "stream_approval_event_requires_persisted_approval",
            "failed_approval_persistence_suppresses_pending_event",
            "stream_approval_event_includes_persisted_approval_id",
            "persisted_stream_replay_preserves_approval_id",
            "persisted_stream_replay_excludes_tool_input",
            "approval_persistence_error_details_are_not_exposed",
            "approval_persistence_cancellation_is_not_swallowed",
            "blank_persisted_approval_id_fails_closed",
            "persisted_run_identity_drives_resume_configuration",
            "resume_checkpoint_identity_mismatch_fails_before_claim",
            "caller_runtime_owner_and_status_cannot_override_persisted_run",
            "approval_request_runtime_matches_selected_resume_runtime",
            "approval_request_thread_matches_persisted_run_thread",
            "approval_request_checkpoint_namespace_matches_persisted_run_namespace",
            "missing_or_mismatched_approval_request_provenance_fails_before_claim",
            "langchain_resume_approval_lookup_cancellation_persisted",
            "langchain_resume_approval_lookup_failure_fails_closed",
            "langgraph_resume_approval_lookup_cancellation_persisted",
            "langgraph_resume_approval_lookup_failure_fails_closed",
            "langgraph_resume_tool_policy_cancellation_persisted",
            "langgraph_resume_tool_policy_failure_fails_closed",
            "unsupported_persisted_resume_runtime_fails_before_dispatch",
            "unavailable_resume_runtime_preserves_unclaimed_interrupted_run",
            "approved_tool_is_revalidated_against_current_catalog_identity",
            "approved_tool_obeys_current_enabled_approval_and_profile_budget_policy",
            "missing_tool_provider_fails_approved_resume_before_claim",
            "inactive_approved_tool_fails_before_claim",
            "rejected_resume_can_finalize_after_tool_deactivation",
            "run_cancellation_atomically_cancels_pending_approvals",
        ],
    ):
        return "approval lifecycle contract missing"
    if not exact_string_set(
        lifecycle_mapping.get("resumeClaimPayloadFields"),
        {"approval_id", "claimed_by", "runtime"},
    ):
        return "approval lifecycle contract missing"
    if not exact_string_set(
        lifecycle_mapping.get("metadataFields"),
        {
            "approval_id",
            "tenant_id",
            "run_id",
            "tool_id",
            "requested_by",
            "decided_by",
            "decision_reason",
            "thread_id",
            "checkpoint_ns",
        },
    ):
        return "approval lifecycle contract missing"
    if not exact_string_set(
        lifecycle_mapping.get("apiPaths"),
        {
            "/api/approvals",
            "/v1/approvals",
            "/api/approvals/{approval_id}/approve",
            "/v1/approvals/{approval_id}/approve",
            "/api/approvals/{approval_id}/reject",
            "/v1/approvals/{approval_id}/reject",
        },
    ):
        return "approval lifecycle contract missing"
    return None


def context_manifest_diagnostics_contract_failure(
    *, name: str, item: Mapping[str, object]
) -> str | None:
    diagnostics = item.get("contextManifestDiagnostics")
    if diagnostics is None:
        if name == "hardening_suite":
            return "context manifest diagnostics contract missing"
        if name == "langsmith_eval_sync" and item.get("status") == "passed":
            return "context manifest diagnostics missing"
        return None
    if not isinstance(diagnostics, Mapping):
        return "context manifest diagnostics contract missing"
    diagnostics_mapping = cast(Mapping[str, object], diagnostics)
    status = diagnostics_mapping.get("status")
    ok = diagnostics_mapping.get("ok")
    if not isinstance(ok, bool) or status not in {"passed", "failed"}:
        return "context manifest diagnostics contract missing"
    if ok != (status == "passed"):
        return "context manifest diagnostics contract missing"
    if status == "failed":
        findings = diagnostics_mapping.get("findings")
        if not non_empty_mapping_sequence(findings):
            return "context manifest diagnostics contract missing"
        if not context_manifest_diagnostic_findings_have_known_codes(findings):
            return "context manifest diagnostics contract missing"
        return "context manifest diagnostics failed"
    if name == "langsmith_eval_sync":
        required_langsmith_diagnostics_fields = {
            "ok",
            "status",
            "ragGroundingPolicy",
            "citationCount",
            "chunkCount",
            "citedChunkCount",
            "uncitedChunkCount",
            "memoryStatusCounts",
            "skippedMemoryStatusCounts",
        }
        optional_langsmith_diagnostics_fields = {
            "citationWorkflowEvalCaseIds",
            "citationWorkflowTags",
        }
        if (
            not required_langsmith_diagnostics_fields.issubset(diagnostics_mapping)
            or set(diagnostics_mapping)
            - required_langsmith_diagnostics_fields
            - optional_langsmith_diagnostics_fields
        ):
            return "context manifest diagnostics contract missing"
        for field_name in ("citationWorkflowEvalCaseIds", "citationWorkflowTags"):
            values = diagnostics_mapping.get(field_name)
            if values is None:
                continue
            if not isinstance(values, Sequence) or isinstance(values, str | bytes):
                return "context manifest diagnostics contract missing"
            if not all(
                isinstance(value, str) and value for value in cast(Sequence[object], values)
            ):
                return "context manifest diagnostics contract missing"
        for field_name in ("memoryStatusCounts", "skippedMemoryStatusCounts"):
            counts = diagnostics_mapping.get(field_name)
            if not isinstance(counts, Mapping):
                return "context manifest diagnostics contract missing"
            counts_mapping = cast(Mapping[str, object], counts)
            if set(counts_mapping) - ALLOWED_MEMORY_STATUS_COUNT_LABELS:
                return "context manifest diagnostics contract missing"
            for value in counts_mapping.values():
                if not non_negative_int(value):
                    return "context manifest diagnostics contract missing"
        skipped_memory_status_counts = cast(
            Mapping[str, object],
            diagnostics_mapping["skippedMemoryStatusCounts"],
        )
        if skipped_memory_status_counts.get("active", 0) != 0:
            return "context manifest diagnostics contract missing"
        if context_manifest_rag_grounding_contract_failure(diagnostics_mapping):
            return "context manifest diagnostics contract missing"
    if name == "hardening_suite":
        allowed_diagnostics_fields = {
            "ok",
            "status",
            "sectionCount",
            "memoryAdmissionPolicy",
            "ragGroundingPolicy",
            "citationCount",
            "chunkCount",
            "citedChunkCount",
            "uncitedChunkCount",
            "memoryCount",
            "skippedMemoryCount",
            "skippedMemoryStatusCounts",
            "memoryStatusCounts",
            "poisoningCoverage",
            "rawAclMetadataVisible",
            "findings",
        }
        if set(diagnostics_mapping) != allowed_diagnostics_fields:
            return "context manifest diagnostics contract missing"
        memory_policy = diagnostics_mapping.get("memoryAdmissionPolicy")
        if not isinstance(memory_policy, Mapping):
            return "context manifest diagnostics contract missing"
        memory_policy_mapping = cast(Mapping[str, object], memory_policy)
        allowed_memory_policy_fields = {
            "activeOnly",
            "missingStatusExcluded",
            "tombstonedExcluded",
            "supersededExcluded",
        }
        if set(memory_policy_mapping) != allowed_memory_policy_fields:
            return "context manifest diagnostics contract missing"
        if (
            memory_policy_mapping.get("activeOnly") is not True
            or memory_policy_mapping.get("missingStatusExcluded") is not True
            or memory_policy_mapping.get("tombstonedExcluded") is not True
            or memory_policy_mapping.get("supersededExcluded") is not True
        ):
            return "context manifest diagnostics contract missing"
        if not non_negative_int(diagnostics_mapping.get("memoryCount")):
            return "context manifest diagnostics contract missing"
        if not non_negative_int(diagnostics_mapping.get("skippedMemoryCount")):
            return "context manifest diagnostics contract missing"
        if not isinstance(diagnostics_mapping.get("memoryStatusCounts"), Mapping):
            return "context manifest diagnostics contract missing"
        if not isinstance(diagnostics_mapping.get("skippedMemoryStatusCounts"), Mapping):
            return "context manifest diagnostics contract missing"
        memory_count = cast(int, diagnostics_mapping["memoryCount"])
        skipped_memory_count = cast(int, diagnostics_mapping["skippedMemoryCount"])
        memory_status_counts = cast(Mapping[str, object], diagnostics_mapping["memoryStatusCounts"])
        skipped_memory_status_counts = cast(
            Mapping[str, object],
            diagnostics_mapping["skippedMemoryStatusCounts"],
        )
        if set(memory_status_counts) - ALLOWED_MEMORY_STATUS_COUNT_LABELS:
            return "context manifest diagnostics contract missing"
        if set(skipped_memory_status_counts) - ALLOWED_MEMORY_STATUS_COUNT_LABELS:
            return "context manifest diagnostics contract missing"
        for value in memory_status_counts.values():
            if not non_negative_int(value):
                return "context manifest diagnostics contract missing"
        for value in skipped_memory_status_counts.values():
            if not non_negative_int(value):
                return "context manifest diagnostics contract missing"
        if sum(cast(int, value) for value in memory_status_counts.values()) != (
            memory_count + skipped_memory_count
        ):
            return "context manifest diagnostics contract missing"
        if memory_status_counts.get("active", 0) != memory_count:
            return "context manifest diagnostics contract missing"
        if skipped_memory_status_counts.get("active", 0) != 0:
            return "context manifest diagnostics contract missing"
        if (
            sum(cast(int, value) for value in skipped_memory_status_counts.values())
            != skipped_memory_count
        ):
            return "context manifest diagnostics contract missing"
        if context_manifest_rag_grounding_contract_failure(diagnostics_mapping):
            return "context manifest diagnostics contract missing"
        poisoning_coverage = diagnostics_mapping.get("poisoningCoverage")
        if not isinstance(poisoning_coverage, Mapping):
            return "context manifest diagnostics contract missing"
        poisoning_mapping = cast(Mapping[str, object], poisoning_coverage)
        allowed_poisoning_fields = {
            "status",
            "poisonedChunkCount",
            "poisoningReasons",
            "source",
        }
        if set(poisoning_mapping) != allowed_poisoning_fields:
            return "context manifest diagnostics contract missing"
        if poisoning_mapping.get("status") != "verified":
            return "context manifest diagnostics contract missing"
        poisoned_chunk_count = poisoning_mapping.get("poisonedChunkCount")
        if (
            not isinstance(poisoned_chunk_count, int)
            or isinstance(poisoned_chunk_count, bool)
            or poisoned_chunk_count <= 0
        ):
            return "context manifest diagnostics contract missing"
        if poisoning_mapping.get("source") != "rag_tool_context_manifest":
            return "context manifest diagnostics contract missing"
        reasons = poisoning_mapping.get("poisoningReasons")
        if not non_empty_string_sequence(reasons):
            return "context manifest diagnostics contract missing"
        if any(
            cast(str, reason) not in RAG_POISONING_REASONS
            for reason in cast(Sequence[object], reasons)
        ):
            return "context manifest diagnostics contract missing"
    return None


def tool_output_guard_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "hardening_suite":
        return None
    if item.get("status") != "passed":
        return None
    guard = item.get("toolOutputGuard")
    if not isinstance(guard, Mapping):
        return "tool output guard contract missing"
    guard_mapping = cast(Mapping[str, object], guard)
    if set(guard_mapping) != {"output_count", "sanitized_count", "findings"}:
        return "tool output guard contract missing"
    output_count = guard_mapping.get("output_count")
    sanitized_count = guard_mapping.get("sanitized_count")
    if not non_negative_int(output_count) or not non_negative_int(sanitized_count):
        return "tool output guard contract missing"
    if cast(int, sanitized_count) < cast(int, output_count):
        return "tool output guard contract missing"
    findings = guard_mapping.get("findings")
    if findings is not None and not string_sequence(findings):
        return "tool output guard contract missing"
    if findings is not None and any(
        not non_empty_string(finding) for finding in cast(Sequence[object], findings)
    ):
        return "tool output guard contract missing"
    if findings is not None and any(
        cast(str, finding) not in TOOL_OUTPUT_SANITIZER_FINDINGS
        for finding in cast(Sequence[object], findings)
    ):
        return "tool output guard contract missing"
    return None


def guard_block_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if item.get("status") != "passed":
        return None
    guard_block = item.get("guardBlock")
    if guard_block is None:
        return None
    if not isinstance(guard_block, Mapping):
        return "guard block contract missing"
    block_mapping = cast(Mapping[str, object], guard_block)
    allowed_fields = {"stage", "reason", "run_id", "tenant_id", "graph_node"}
    if set(block_mapping) != allowed_fields:
        return "guard block contract missing"
    for field_name in allowed_fields:
        if not non_empty_string(block_mapping.get(field_name)):
            return "guard block contract missing"
    return None


def context_manifest_rag_grounding_contract_failure(
    diagnostics_mapping: Mapping[str, object],
) -> bool:
    rag_policy = diagnostics_mapping.get("ragGroundingPolicy")
    if not isinstance(rag_policy, Mapping):
        return True
    rag_policy_mapping = cast(Mapping[str, object], rag_policy)
    allowed_rag_policy_fields = {
        "citationTracking",
        "uncitedChunksTracked",
        "aclEvidence",
        "rawAclMetadataVisible",
    }
    if set(rag_policy_mapping) != allowed_rag_policy_fields:
        return True
    if (
        rag_policy_mapping.get("citationTracking") != "required"
        or rag_policy_mapping.get("uncitedChunksTracked") is not True
        or rag_policy_mapping.get("aclEvidence") != "acl_hash_only"
        or rag_policy_mapping.get("rawAclMetadataVisible") is not False
    ):
        return True
    citation_count = diagnostics_mapping.get("citationCount")
    chunk_count = diagnostics_mapping.get("chunkCount")
    cited_chunk_count = diagnostics_mapping.get("citedChunkCount")
    uncited_chunk_count = diagnostics_mapping.get("uncitedChunkCount")
    if (
        not positive_int(citation_count)
        or not positive_int(chunk_count)
        or not positive_int(cited_chunk_count)
        or not non_negative_int(uncited_chunk_count)
    ):
        return True
    return cast(int, cited_chunk_count) + cast(int, uncited_chunk_count) != cast(
        int,
        chunk_count,
    )


def context_manifest_diagnostic_findings_have_known_codes(findings: object) -> bool:
    if not isinstance(findings, Sequence) or isinstance(findings, str | bytes | bytearray):
        return False
    for finding in cast(Sequence[object], findings):
        if not isinstance(finding, Mapping):
            return False
        code = cast(Mapping[str, object], finding).get("code")
        if not isinstance(code, str) or code not in CONTEXT_MANIFEST_DIAGNOSTIC_CODES:
            return False
    return True


def structured_output_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if item.get("status") != "passed":
        return None
    structured_output = item.get("structuredOutput")
    if structured_output is None:
        if name == "hardening_suite":
            return "structured output contract missing"
        return None
    if not isinstance(structured_output, Mapping):
        return "structured output contract missing"
    output_mapping = cast(Mapping[str, object], structured_output)
    allowed_output_fields = {
        "format",
        "strategy",
        "langchainStrategies",
        "reactorStrategies",
        "enforcement",
        "policyFailureStatus",
        "blockedResponseEmittedAsSuccessToken",
        "nativeStreamFinalPolicyOutputHonored",
        "nativeStreamRootFinalOutputOnly",
        "nativeStreamInvalidLineageFailClosed",
        "conflictingRootNativeGraphResultsFailClosed",
        "identicalRootNativeGraphResultReplayAllowed",
        "nativeGraphResultConflictStopReason",
        "nativeStructuredStreamResponseHonored",
        "invokeStreamStructuredResponseParity",
        "nativeStructuredResponseAuthoritativeWhenPresent",
        "emptyStructuredResponseFailsClosed",
        "unserializableStructuredResponseFailsClosed",
        "serializationFailureErrorCode",
        "rootStructuredStreamResponseOnly",
        "nestedStructuredStreamResponsesIgnored",
        "missingStructuredStreamParentIdsFailClosed",
        "conflictingRootStructuredResponsesFailClosed",
        "identicalRootStructuredResponseReplayAllowed",
        "structuredResponseConflictStopReason",
        "applicationOwnedContextManifest",
        "schemaImpliesJsonFormat",
        "verificationSensors",
        "covers",
        "repairBoundary",
        "schema",
        "schemaSource",
        "citationBoundary",
        "ignoredSchema",
        "ignoredFormat",
    }
    if set(output_mapping) - allowed_output_fields:
        return "structured output contract missing"
    output_format = output_mapping.get("format")
    if not isinstance(output_format, str) or output_format not in {"JSON", "YAML", "TEXT"}:
        return "structured output contract missing"
    strategy = output_mapping.get("strategy")
    if not isinstance(strategy, str) or strategy not in {
        "schema_passthrough",
        "json_object_schema",
        "reactor_boundary",
    }:
        return "structured output contract missing"
    if strategy == "json_object_schema" and output_format != "JSON":
        return "structured output contract missing"
    if output_format == "TEXT" and strategy != "reactor_boundary":
        return "structured output contract missing"
    ignored_format = output_mapping.get("ignoredFormat")
    ignored_schema = output_mapping.get("ignoredSchema")
    schema_source = output_mapping.get("schemaSource")
    if strategy != "reactor_boundary" and ignored_schema is None:
        if not isinstance(schema_source, str) or not schema_source.strip():
            return "structured output contract missing"
    elif schema_source is not None and not non_empty_string(schema_source):
        return "structured output contract missing"
    langchain_strategies = output_mapping.get("langchainStrategies")
    if not exact_string_set(
        langchain_strategies,
        {"ProviderStrategy", "ToolStrategy", "schema_type", "none"},
    ):
        return "structured output contract missing"
    reactor_strategies = output_mapping.get("reactorStrategies")
    if not exact_string_set(
        reactor_strategies,
        {"schema_passthrough", "json_object_schema", "reactor_boundary"},
    ):
        return "structured output contract missing"
    if output_mapping.get("enforcement") != "langchain_response_format_and_reactor_boundary":
        return "structured output contract missing"
    if (
        output_mapping.get("policyFailureStatus") != "rejected"
        or output_mapping.get("blockedResponseEmittedAsSuccessToken") is not False
        or output_mapping.get("nativeStreamFinalPolicyOutputHonored") is not True
    ):
        return "structured output contract missing"
    if name == "hardening_suite":
        if any(
            output_mapping.get(field_name) is not True
            for field_name in (
                "nativeStreamRootFinalOutputOnly",
                "nativeStreamInvalidLineageFailClosed",
                "conflictingRootNativeGraphResultsFailClosed",
                "identicalRootNativeGraphResultReplayAllowed",
                "nativeStructuredStreamResponseHonored",
                "invokeStreamStructuredResponseParity",
                "nativeStructuredResponseAuthoritativeWhenPresent",
                "emptyStructuredResponseFailsClosed",
                "unserializableStructuredResponseFailsClosed",
                "rootStructuredStreamResponseOnly",
                "nestedStructuredStreamResponsesIgnored",
                "missingStructuredStreamParentIdsFailClosed",
                "conflictingRootStructuredResponsesFailClosed",
                "identicalRootStructuredResponseReplayAllowed",
                "applicationOwnedContextManifest",
                "schemaImpliesJsonFormat",
            )
        ):
            return "structured output contract missing"
        if (
            output_mapping.get("nativeGraphResultConflictStopReason")
            != "native_graph_result_stream_conflict"
        ):
            return "structured output contract missing"
        if (
            output_mapping.get("structuredResponseConflictStopReason")
            != "structured_response_stream_conflict"
        ):
            return "structured output contract missing"
        if (
            output_mapping.get("serializationFailureErrorCode")
            != "STRUCTURED_RESPONSE_SERIALIZATION_FAILED"
        ):
            return "structured output contract missing"
        if not same_string_sequence(
            output_mapping.get("verificationSensors"),
            [
                (
                    "uv run pytest tests/unit/test_run_service.py -q -k "
                    "'native_stream_uses_final_graph_policy_output or "
                    "native_stream_fails_closed_on_conflicting_root_graph_results or "
                    "native_stream_ignores_nested_final_policy_output or "
                    "native_graph_stream_result_requires_v2_root_lineage'"
                ),
                (
                    "uv run pytest tests/unit/test_run_service.py -q -k "
                    "'stream_uses_langchain_native_structured_response or "
                    "stream_fails_closed_on_conflicting_root_structured_responses or "
                    "stream_rejects_empty_native_structured_response or "
                    "stream_ignores_nested_structured_response or "
                    "stream_ignores_structured_response_without_parent_ids'"
                ),
                (
                    "uv run pytest tests/integration/test_api.py "
                    "tests/integration/test_chat_api.py -q -k context_manifest"
                ),
                (
                    "uv run pytest tests/integration/test_api.py -q "
                    "-k structured_output_diagnostics_treats_schema_only_contract_as_json"
                ),
            ],
        ):
            return "structured output contract missing"
        if not same_string_sequence(
            output_mapping.get("covers"),
            [
                "native_langgraph_final_result_requires_root_event",
                "native_langgraph_invalid_lineage_fails_closed",
                "nested_native_stream_result_cannot_override_root_output",
                "conflicting_root_native_graph_results_fail_closed",
                "identical_root_native_graph_result_replay_allowed",
                "langchain_native_structured_response_drives_stream_result",
                "langchain_invoke_and_stream_structured_response_precedence_match",
                "empty_native_structured_response_uses_token_fallback",
                "langchain_structured_stream_response_requires_root_event",
                "nested_structured_stream_response_cannot_override_root_output",
                "missing_structured_stream_parent_ids_fail_closed",
                "conflicting_root_structured_responses_fail_closed",
                "identical_root_structured_response_replay_allowed",
                "public_request_context_manifest_cannot_authorize_citations",
                "explicit_schema_implies_json_format_without_response_format",
            ],
        ):
            return "structured output contract missing"
    citation_boundary = output_mapping.get("citationBoundary")
    if citation_boundary is None and not (
        strategy == "reactor_boundary"
        and ignored_format is not None
        or strategy == "json_object_schema"
        and ignored_schema is not None
    ):
        return "structured output contract missing"
    if citation_boundary is not None:
        if not isinstance(citation_boundary, Mapping):
            return "structured output contract missing"
        citation_boundary_mapping = cast(Mapping[str, object], citation_boundary)
        allowed_citation_boundary_fields = {"status", "source", "runtimes", "requiredMetadata"}
        if set(citation_boundary_mapping) != allowed_citation_boundary_fields:
            return "structured output contract missing"
        if (
            citation_boundary_mapping.get("status") != "enforced"
            or citation_boundary_mapping.get("source") != "context_manifest"
        ):
            return "structured output contract missing"
        required_runtimes = {"langgraph", "langchain_agent", "langchain_agent_stream"}
        runtimes = citation_boundary_mapping.get("runtimes")
        if not exact_string_set(runtimes, required_runtimes):
            return "structured output contract missing"
        required_metadata = {
            "structured_output_allowed_citation_ids",
            "structured_output_citation_policy",
            "structured_output_citation_count",
        }
        if not exact_string_set(
            citation_boundary_mapping.get("requiredMetadata"), required_metadata
        ):
            return "structured output contract missing"
    repair_boundary = output_mapping.get("repairBoundary")
    if not isinstance(repair_boundary, Mapping):
        return "structured output contract missing"
    repair_boundary_mapping = cast(Mapping[str, object], repair_boundary)
    allowed_repair_boundary_fields = {
        "status",
        "maxInvalidInputChars",
        "rawInvalidInputIncluded",
    }
    if set(repair_boundary_mapping) != allowed_repair_boundary_fields:
        return "structured output contract missing"
    max_invalid_input_chars = repair_boundary_mapping.get("maxInvalidInputChars")
    if (
        repair_boundary_mapping.get("status") != "enforced"
        or not isinstance(max_invalid_input_chars, int)
        or isinstance(max_invalid_input_chars, bool)
        or max_invalid_input_chars != 8192
        or repair_boundary_mapping.get("rawInvalidInputIncluded") is not False
    ):
        return "structured output contract missing"
    if ignored_schema is not None:
        if ignored_format is None and (output_format != "JSON" or strategy != "json_object_schema"):
            return "structured output contract missing"
        if ignored_format is not None and (
            output_format != "TEXT" or strategy != "reactor_boundary"
        ):
            return "structured output contract missing"
        if schema_source is not None or output_mapping.get("schema") is not None:
            return "structured output contract missing"
        if not isinstance(ignored_schema, Mapping):
            return "structured output contract missing"
        ignored_schema_mapping = cast(Mapping[str, object], ignored_schema)
        if set(ignored_schema_mapping) != {"status", "reason", "source"}:
            return "structured output contract missing"
        if ignored_schema_mapping.get("status") != "ignored":
            return "structured output contract missing"
        if (
            ignored_schema_mapping.get("reason") != "invalid_response_schema"
            or ignored_schema_mapping.get("source") != "metadata.responseSchema"
        ):
            return "structured output contract missing"
    if ignored_format is not None:
        if output_format != "TEXT" or strategy != "reactor_boundary":
            return "structured output contract missing"
        if not isinstance(ignored_format, Mapping):
            return "structured output contract missing"
        ignored_format_mapping = cast(Mapping[str, object], ignored_format)
        if set(ignored_format_mapping) != {"status", "reason", "source", "value"}:
            return "structured output contract missing"
        if (
            ignored_format_mapping.get("status") != "ignored"
            or ignored_format_mapping.get("reason") != "invalid_response_format"
            or ignored_format_mapping.get("source") != "metadata.responseFormat"
            or not non_empty_string(ignored_format_mapping.get("value"))
        ):
            return "structured output contract missing"
    return None


def non_empty_string_sequence(value: object) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return False
    items = cast(Sequence[object], value)
    return all(isinstance(item, str) and item.strip() for item in items) and len(items) > 0


def non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def exact_string_set(value: object, expected: set[str]) -> bool:
    if not non_empty_string_sequence(value):
        return False
    items = cast(Sequence[str], value)
    return len(items) == len(expected) and set(items) == expected


def same_string_sequence(left: object, right: object) -> bool:
    if not non_empty_string_sequence(left) or not non_empty_string_sequence(right):
        return False
    return list(cast(Sequence[str], left)) == list(cast(Sequence[str], right))


def same_string_mapping(left: object, right: object) -> bool:
    if not isinstance(left, Mapping) or not isinstance(right, Mapping) or not right:
        return False
    mapping = cast(Mapping[object, object], left)
    expected = cast(Mapping[object, object], right)
    if set(mapping) != set(expected):
        return False
    return all(
        isinstance(key, str)
        and key.strip()
        and isinstance(value, str)
        and value.strip()
        and mapping.get(key) == value
        for key, value in expected.items()
    )


def normalized_score(value: object) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= 1
    )


def positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def positive_int_mapping(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    mapping = cast(Mapping[object, object], value)
    if not mapping:
        return False
    return all(
        isinstance(key, str)
        and key.strip()
        and isinstance(item, int)
        and not isinstance(item, bool)
        and item > 0
        for key, item in mapping.items()
    )


def count_mapping_total_matches(value: object, *, expected: int) -> bool:
    if not positive_int_mapping(value):
        return False
    mapping = cast(Mapping[object, object], value)
    return sum(cast(int, item) for item in mapping.values()) == expected


def langsmith_feedback_workflow_counts_valid(
    value: object, *, max_count: int | None = None
) -> bool:
    if not positive_int_mapping(value):
        return False
    mapping = cast(Mapping[object, object], value)
    forbidden_tags = {"exported-from-cli", "regression"}
    return not any(key in forbidden_tags for key in mapping) and (
        max_count is None or all(cast(int, item) <= max_count for item in mapping.values())
    )


def langsmith_feedback_promotion_contract_failure(
    *,
    feedback_promotion: object,
    case_id_set: set[str],
    promotion_coverage: object = None,
) -> bool:
    if not isinstance(feedback_promotion, Mapping):
        return True
    mapping = cast(Mapping[str, object], feedback_promotion)
    base_required_fields = {
        "caseIds",
        "feedbackIds",
        "feedbackReviewIds",
        "feedbackRatingCounts",
        "feedbackSourceCounts",
        "workflowTagCounts",
    }
    optional_field_sets = (
        frozenset[str](),
        frozenset({"expectedCitationCounts"}),
        frozenset({"releaseReadinessCommand"}),
        frozenset({"expectedCitationCounts", "releaseReadinessCommand"}),
    )
    open_required_fields = {*base_required_fields, "bulkReviewAction"}
    closed_required_fields = {*base_required_fields, "reviewStatus", "reviewTags", "reviewNote"}
    allowed_sets = {
        frozenset(open_required_fields | set(optional_fields) | {review_field})
        for optional_fields in optional_field_sets
        for review_field in ("reviewAction", "reviewActions")
    } | {
        frozenset(closed_required_fields | set(optional_fields))
        for optional_fields in optional_field_sets
    }
    if frozenset(mapping) not in allowed_sets:
        return True
    release_readiness_command = mapping.get("releaseReadinessCommand")
    if release_readiness_command is not None and (
        not isinstance(release_readiness_command, str)
        or "uv run reactor-release-smoke-run" not in release_readiness_command
        or "--readiness-output" not in release_readiness_command
    ):
        return True
    case_ids = mapping.get("caseIds")
    if not non_empty_string_sequence(case_ids):
        return True
    promoted_case_ids = cast(Sequence[str], case_ids)
    if len(set(promoted_case_ids)) != len(promoted_case_ids):
        return True
    if not set(promoted_case_ids).issubset(case_id_set):
        return True
    feedback_ids = mapping.get("feedbackIds")
    if not non_empty_string_sequence(feedback_ids):
        return True
    typed_feedback_ids = cast(Sequence[str], feedback_ids)
    if len(set(typed_feedback_ids)) != len(typed_feedback_ids):
        return True
    feedback_review_ids = mapping.get("feedbackReviewIds")
    if not non_empty_string_sequence(feedback_review_ids):
        return True
    if list(cast(Sequence[str], feedback_review_ids)) != list(typed_feedback_ids):
        return True
    if feedback_promotion_review_closed(mapping):
        if mapping.get("reviewAction") is not None or mapping.get("reviewActions") is not None:
            return True
        if mapping.get("bulkReviewAction") is not None:
            return True
    else:
        if not feedback_review_actions_match_ids(
            review_action=mapping.get("reviewAction"),
            review_actions=mapping.get("reviewActions"),
            feedback_review_ids=cast(Sequence[str], feedback_review_ids),
            feedback_rating_counts=mapping.get("feedbackRatingCounts"),
            feedback_source_counts=mapping.get("feedbackSourceCounts"),
            workflow_tag_counts=mapping.get("workflowTagCounts"),
        ):
            return True
        bulk_review_action = mapping.get("bulkReviewAction")
        if not feedback_bulk_review_action_valid(
            action=bulk_review_action,
            feedback_review_ids=cast(Sequence[str], feedback_review_ids),
            case_ids=promoted_case_ids,
            workflow_tag_counts=mapping.get("workflowTagCounts"),
            feedback_source_counts=mapping.get("feedbackSourceCounts"),
        ):
            return True
    expected_feedback_count = (
        len(promoted_case_ids)
        if feedback_promotion_review_closed(mapping)
        else len(cast(Sequence[str], feedback_review_ids))
    )
    if not count_mapping_total_matches(
        mapping.get("feedbackRatingCounts"),
        expected=expected_feedback_count,
    ):
        return True
    if not count_mapping_total_matches(
        mapping.get("feedbackSourceCounts"),
        expected=expected_feedback_count,
    ):
        return True
    return (
        not positive_int_mapping(mapping.get("feedbackRatingCounts"))
        or not positive_int_mapping(mapping.get("feedbackSourceCounts"))
        or not langsmith_feedback_workflow_counts_valid(
            mapping.get("workflowTagCounts"),
            max_count=expected_feedback_count,
        )
        or langsmith_expected_citation_counts_invalid(
            workflow_tag_counts=mapping.get("workflowTagCounts"),
            expected_citation_counts=mapping.get("expectedCitationCounts"),
            max_count=expected_feedback_count,
            citation_markers_required=promotion_coverage_requires_citation_markers(
                promotion_coverage
            ),
        )
    )


def langsmith_expected_citation_counts_invalid(
    *,
    workflow_tag_counts: object,
    expected_citation_counts: object,
    max_count: int,
    citation_markers_required: bool = False,
) -> bool:
    if not isinstance(workflow_tag_counts, Mapping):
        return citation_markers_required and not positive_safe_citation_count_mapping(
            expected_citation_counts
        )
    workflow_mapping = cast(Mapping[object, object], workflow_tag_counts)
    expected_ids = {
        citation_id
        for key in workflow_mapping
        if isinstance(key, str) and key.startswith("expected-citation:")
        if (citation_id := key.removeprefix("expected-citation:").strip())
    }
    if any(not is_citation_safe_id(citation_id) for citation_id in expected_ids):
        return True
    if citation_markers_required and not positive_int_mapping(expected_citation_counts):
        return True
    if not expected_ids:
        if not positive_safe_citation_count_mapping(expected_citation_counts):
            return False
        expected_mapping_without_tags = cast(Mapping[object, object], expected_citation_counts)
        return any(cast(int, item) > max_count for item in expected_mapping_without_tags.values())
    if not positive_safe_citation_count_mapping(expected_citation_counts):
        return True
    expected_mapping = cast(Mapping[object, object], expected_citation_counts)
    return set(expected_mapping) != expected_ids or any(
        cast(int, item) > max_count for item in expected_mapping.values()
    )


def positive_safe_citation_count_mapping(value: object) -> bool:
    if not positive_int_mapping(value):
        return False
    return all(
        isinstance(key, str) and is_citation_safe_id(key)
        for key in cast(Mapping[object, object], value)
    )


def promotion_coverage_requires_citation_markers(promotion_coverage: object) -> bool:
    if not isinstance(promotion_coverage, Mapping):
        return False
    return cast(Mapping[object, object], promotion_coverage).get("citationMarkersRequired") is True


def langsmith_promotion_coverage_contract_failure(*, promotion_coverage: object) -> bool:
    if not isinstance(promotion_coverage, Mapping):
        return True
    mapping = cast(Mapping[object, object], promotion_coverage)
    keys = set(mapping)
    if not all(isinstance(key, str) for key in keys):
        return True
    typed_keys = cast(set[str], keys)
    if not LANGSMITH_PROMOTION_COVERAGE_BASE_FIELDS.issubset(typed_keys):
        return True
    optional_fields = frozenset(typed_keys - LANGSMITH_PROMOTION_COVERAGE_BASE_FIELDS)
    remaining_optional_fields = set(optional_fields)
    if LANGSMITH_PROMOTION_COVERAGE_CITATION_FIELDS <= remaining_optional_fields:
        remaining_optional_fields -= LANGSMITH_PROMOTION_COVERAGE_CITATION_FIELDS
    if LANGSMITH_PROMOTION_COVERAGE_CONTEXT_CITATION_FIELDS <= remaining_optional_fields:
        remaining_optional_fields -= LANGSMITH_PROMOTION_COVERAGE_CONTEXT_CITATION_FIELDS
    if remaining_optional_fields:
        return True
    if not all(isinstance(mapping.get(key), bool) for key in typed_keys):
        return True
    if any(mapping.get(key) is not True for key in LANGSMITH_PROMOTION_COVERAGE_BASE_FIELDS):
        return True
    if "citationMarkersRequired" in typed_keys:
        if mapping.get("citationMarkersRequired") is not True:
            return True
        if mapping.get("citationMarkersPresent") is not True:
            return True
        if (
            mapping.get("runCitationMarkersPresent") is not True
            and mapping.get("citationFailureAllowsMissingRunCitation") is not True
        ):
            return True
    return False


def feedback_promotion_review_closed(mapping: Mapping[str, object]) -> bool:
    return feedback_review_closed(mapping)


def langsmith_feedback_review_queue_contract_failure(
    *,
    feedback_review_queue: object,
    case_id_set: set[str],
) -> bool:
    if not isinstance(feedback_review_queue, Mapping):
        return True
    mapping = cast(Mapping[str, object], feedback_review_queue)
    reviewed_done = mapping.get("reviewStatus") == "done"
    required_fields = {
        "caseIds",
        "feedbackRatingCounts",
        "workflowTagCounts",
    }
    if not reviewed_done:
        required_fields.add("reviewAction")
    allowed_fields = required_fields | {
        "expectedCitationCounts",
        "exportAction",
        "feedbackSourceCounts",
        "reviewNote",
        "reviewStatus",
        "reviewTags",
    }
    expected_candidate_action = feedback_review_queue_candidate_review_action(
        workflow_tag_counts=mapping.get("workflowTagCounts"),
        case_ids=mapping.get("caseIds"),
    )
    expected_memory_action = feedback_review_queue_memory_lifecycle_action(
        mapping.get("workflowTagCounts")
    )
    if expected_candidate_action:
        allowed_fields.add("candidateReviewAction")
        allowed_fields.add("candidateTag")
        allowed_fields.add("bulkReviewAction")
    if expected_memory_action:
        allowed_fields.add("memoryLifecycleAction")
    if not required_fields.issubset(set(mapping)) or not set(mapping).issubset(allowed_fields):
        return True
    case_ids = mapping.get("caseIds")
    if not non_empty_string_sequence(case_ids):
        return True
    queue_case_ids = cast(Sequence[str], case_ids)
    if len(set(queue_case_ids)) != len(queue_case_ids):
        return True
    if not set(queue_case_ids).issubset(case_id_set):
        return True
    if not positive_int_mapping(mapping.get("feedbackRatingCounts")):
        return True
    if "reviewStatus" in mapping and mapping.get("reviewStatus") != "done":
        return True
    if "reviewTags" in mapping and not non_empty_string_sequence(mapping.get("reviewTags")):
        return True
    if "reviewNote" in mapping and (
        not isinstance(mapping.get("reviewNote"), str)
        or not cast(str, mapping.get("reviewNote")).strip()
    ):
        return True
    if not count_mapping_total_matches(
        mapping.get("feedbackRatingCounts"),
        expected=len(queue_case_ids),
    ):
        return True
    if "feedbackSourceCounts" in mapping and not positive_int_mapping(
        mapping.get("feedbackSourceCounts")
    ):
        return True
    if "feedbackSourceCounts" in mapping and not count_mapping_total_matches(
        mapping.get("feedbackSourceCounts"),
        expected=len(queue_case_ids),
    ):
        return True
    if expected_candidate_action and not positive_int_mapping(mapping.get("feedbackSourceCounts")):
        return True
    if not langsmith_feedback_workflow_counts_valid(
        mapping.get("workflowTagCounts"),
        max_count=len(queue_case_ids),
    ):
        return True
    if langsmith_expected_citation_counts_invalid(
        workflow_tag_counts=mapping.get("workflowTagCounts"),
        expected_citation_counts=mapping.get("expectedCitationCounts"),
        max_count=len(queue_case_ids),
    ):
        return True
    if not reviewed_done:
        if mapping.get("reviewAction") != feedback_review_queue_action(
            feedback_rating_counts=mapping.get("feedbackRatingCounts"),
            feedback_source_counts=mapping.get("feedbackSourceCounts"),
            workflow_tag_counts=mapping.get("workflowTagCounts"),
            case_ids=queue_case_ids,
            case_count=len(queue_case_ids),
        ):
            return True
    if "exportAction" in mapping:
        if mapping.get("exportAction") != feedback_review_queue_export_action(
            feedback_rating_counts=mapping.get("feedbackRatingCounts"),
            feedback_source_counts=mapping.get("feedbackSourceCounts"),
            workflow_tag_counts=mapping.get("workflowTagCounts"),
            case_ids=queue_case_ids,
            case_count=len(queue_case_ids),
        ):
            return True
    if expected_candidate_action and not reviewed_done:
        if mapping.get("candidateReviewAction") != expected_candidate_action:
            return True
        expected_candidate_tag = feedback_review_queue_candidate_tag(
            mapping.get("workflowTagCounts"),
            case_ids=queue_case_ids,
        )
        if not expected_candidate_tag:
            return True
        if mapping.get("candidateTag") != expected_candidate_tag:
            return True
        if mapping.get("bulkReviewAction") != feedback_review_queue_bulk_review_action(
            expected_candidate_tag,
            feedback_source_counts=mapping.get("feedbackSourceCounts"),
        ):
            return True
    if expected_memory_action:
        return mapping.get("memoryLifecycleAction") != expected_memory_action
    return False


def feedback_review_actions_match_ids(
    *,
    review_action: object,
    review_actions: object,
    feedback_review_ids: Sequence[str],
    feedback_rating_counts: object,
    workflow_tag_counts: object,
    feedback_source_counts: object = None,
) -> bool:
    expected_actions = [
        f"reactor-admin feedback --feedback-id {quote(feedback_id)} --output table"
        for feedback_id in feedback_review_ids
    ]
    if len(expected_actions) == 1:
        return review_action == expected_actions[0] and review_actions is None
    workflow_action = feedback_workflow_review_action(
        feedback_review_ids=feedback_review_ids,
        feedback_rating_counts=feedback_rating_counts,
        feedback_source_counts=feedback_source_counts,
        workflow_tag_counts=workflow_tag_counts,
    )
    if workflow_action and review_action == workflow_action and review_actions is None:
        return True
    if not non_empty_string_sequence(review_actions):
        return False
    return list(cast(Sequence[str], review_actions)) == expected_actions and review_action is None


def feedback_bulk_review_action_valid(
    *,
    action: object,
    feedback_review_ids: Sequence[str],
    case_ids: Sequence[str],
    workflow_tag_counts: object = None,
    feedback_source_counts: object = None,
) -> bool:
    if not isinstance(action, str) or not action.strip():
        return False
    try:
        parts = shlex_split(action)
    except ValueError:
        return False
    if parts[:2] != ["reactor-admin", "feedback-bulk-review"]:
        return False
    positional_ids: list[str] = []
    case_id_values: list[str] = []
    candidate_tag_values: list[str] = []
    source_values: list[str] = []
    status_value = ""
    output_value = ""
    note_value = ""
    tag_values: list[str] = []
    index = 2
    options_with_values = {
        "--candidate-tag",
        "--case-id",
        "--note",
        "--output",
        "--source",
        "--status",
        "--tag",
    }
    while index < len(parts):
        part = parts[index]
        if part in options_with_values:
            if index + 1 >= len(parts):
                return False
            value = parts[index + 1]
            if part == "--case-id":
                case_id_values.append(value)
            elif part == "--candidate-tag":
                candidate_tag_values.append(value)
            elif part == "--source":
                source_values.append(value)
            elif part == "--status":
                status_value = value
            elif part == "--output":
                output_value = value
            elif part == "--note":
                note_value = value
            elif part == "--tag":
                tag_values.append(value)
            index += 2
            continue
        if part.startswith("--"):
            return False
        positional_ids.append(part)
        index += 1
    if status_value != "done" or output_value != "table":
        return False
    if note_value != RAG_CANDIDATE_FEEDBACK_BULK_REVIEW_NOTE:
        return False
    base_tags = {"promoted", "langsmith"}
    if not base_tags.issubset(set(tag_values)):
        return False
    if len(candidate_tag_values) > 1 or len(source_values) > 1:
        return False
    if source_values:
        source_arg = feedback_source_filter_arg(feedback_source_counts)
        if source_arg != f"--source {quote(source_values[0])} ":
            return False
    expected_candidate_tag = candidate_workflow_tag_from_case_ids(case_ids)
    if candidate_tag_values:
        candidate_tag = candidate_tag_values[0]
        if not expected_candidate_tag or candidate_tag != expected_candidate_tag:
            return False
        if candidate_tag not in tag_values:
            return False
    if positional_ids:
        expected_tags = set(base_tags)
        if isinstance(workflow_tag_counts, Mapping):
            workflow_mapping = cast(Mapping[object, object], workflow_tag_counts)
            required_workflow_count = max(len(case_ids), len(feedback_review_ids))
            expected_tags.update(
                str(tag)
                for tag, count in workflow_mapping.items()
                if isinstance(tag, str)
                and tag.strip()
                and isinstance(count, int)
                and not isinstance(count, bool)
                and count == required_workflow_count
            )
        if set(tag_values) != expected_tags:
            return False
    if positional_ids and sorted(positional_ids) == sorted(feedback_review_ids):
        return True
    if candidate_tag_values:
        return True
    return bool(case_id_values) and set(case_id_values).issubset(set(case_ids))


def feedback_workflow_review_action(
    *,
    feedback_review_ids: Sequence[str],
    feedback_rating_counts: object,
    workflow_tag_counts: object,
    feedback_source_counts: object = None,
) -> str:
    if len(feedback_review_ids) <= 1:
        return ""
    if not isinstance(workflow_tag_counts, Mapping) or not isinstance(
        feedback_rating_counts, Mapping
    ):
        return ""
    workflow_mapping = cast(Mapping[object, object], workflow_tag_counts)
    workflow_tag = preferred_feedback_workflow_tag(
        workflow_mapping,
        required_count=len(feedback_review_ids),
    )
    if not workflow_tag:
        return ""
    rating_mapping = cast(Mapping[object, object], feedback_rating_counts)
    rating = next(
        (
            str(rating).strip()
            for rating, count in sorted(rating_mapping.items(), key=lambda item: str(item[0]))
            if str(rating).strip()
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count > 0
        ),
        "",
    )
    if not rating:
        return ""
    source_arg = feedback_source_filter_arg(feedback_source_counts)
    collection_tag_arg = (
        "--tag collection:rag-ingestion-candidate "
        if workflow_tag.startswith("rag-candidate:")
        else ""
    )
    return (
        f"reactor-admin feedback --rating {quote(rating)} "
        f"{source_arg}"
        f"--review-status inbox {collection_tag_arg}"
        f"--tag {quote(workflow_tag)} "
        "--limit 10 --output table"
    )


def feedback_review_queue_action(
    *,
    feedback_rating_counts: object,
    workflow_tag_counts: object,
    feedback_source_counts: object = None,
    case_ids: Sequence[str] = (),
    case_count: int,
) -> str:
    if case_count <= 0:
        return ""
    if not isinstance(workflow_tag_counts, Mapping) or not isinstance(
        feedback_rating_counts, Mapping
    ):
        return ""
    workflow_mapping = cast(Mapping[object, object], workflow_tag_counts)
    workflow_tag = preferred_feedback_workflow_tag(
        workflow_mapping,
        required_count=case_count,
    )
    if not workflow_tag.startswith("rag-candidate:"):
        workflow_tag = candidate_workflow_tag_from_case_ids(case_ids) or workflow_tag
    if not workflow_tag:
        return ""
    rating_mapping = cast(Mapping[object, object], feedback_rating_counts)
    rating = next(
        (
            str(rating).strip()
            for rating, count in sorted(rating_mapping.items(), key=lambda item: str(item[0]))
            if str(rating).strip()
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count > 0
        ),
        "",
    )
    if not rating:
        return ""
    source_arg = feedback_source_filter_arg(feedback_source_counts)
    case_id_arg = f"--case-id {quote(case_ids[0])} " if len(case_ids) == 1 else ""
    collection_tag_arg = (
        "--tag collection:rag-ingestion-candidate "
        if workflow_tag.startswith("rag-candidate:")
        else ""
    )
    return (
        f"reactor-admin feedback --rating {quote(rating)} "
        f"{source_arg}"
        f"--review-status inbox {case_id_arg}{collection_tag_arg}"
        f"--tag {quote(workflow_tag)} "
        "--limit 10 --output table"
    )


def feedback_review_queue_export_action(
    *,
    feedback_rating_counts: object,
    workflow_tag_counts: object,
    feedback_source_counts: object = None,
    case_ids: Sequence[str] = (),
    case_count: int,
) -> str:
    review_action = feedback_review_queue_action(
        feedback_rating_counts=feedback_rating_counts,
        feedback_source_counts=feedback_source_counts,
        workflow_tag_counts=workflow_tag_counts,
        case_ids=case_ids,
        case_count=case_count,
    )
    if not review_action:
        return ""
    export_action = review_action.replace(
        "reactor-admin feedback ",
        "reactor-admin feedback-export ",
        1,
    ).replace("--output table", "--output json")
    return export_action


def feedback_review_queue_memory_lifecycle_action(workflow_tag_counts: object) -> str:
    if not isinstance(workflow_tag_counts, Mapping):
        return ""
    workflow_mapping = cast(Mapping[object, object], workflow_tag_counts)
    memory_count = workflow_mapping.get("memory")
    if not isinstance(memory_count, int) or isinstance(memory_count, bool) or memory_count <= 0:
        return ""
    return MEMORY_LIFECYCLE_GATE_ACTION


def feedback_review_queue_candidate_review_action(
    workflow_tag_counts: object,
    *,
    case_ids: object = (),
) -> str:
    candidate_tag = feedback_review_queue_candidate_tag(workflow_tag_counts, case_ids=case_ids)
    if candidate_tag:
        return rag_candidate_review_action(candidate_tag)
    if not isinstance(workflow_tag_counts, Mapping):
        return ""
    workflow_mapping = cast(Mapping[object, object], workflow_tag_counts)
    candidate_count = workflow_mapping.get("collection:rag-ingestion-candidate")
    if (
        not isinstance(candidate_count, int)
        or isinstance(candidate_count, bool)
        or candidate_count <= 0
    ):
        return ""
    return RAG_CANDIDATE_REVIEW_ACTION


def feedback_review_queue_candidate_tag(
    workflow_tag_counts: object,
    *,
    case_ids: object = (),
) -> str:
    if non_empty_string_sequence(case_ids):
        candidate_tag = candidate_workflow_tag_from_case_ids(cast(Sequence[str], case_ids))
        if candidate_tag:
            return candidate_tag
    if not isinstance(workflow_tag_counts, Mapping):
        return ""
    workflow_mapping = cast(Mapping[object, object], workflow_tag_counts)
    candidate_tags = sorted(
        tag
        for tag, count in workflow_mapping.items()
        if isinstance(tag, str)
        and tag.startswith("rag-candidate:")
        and valid_candidate_workflow_tag(tag)
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count > 0
    )
    if len(candidate_tags) == 1:
        return candidate_tags[0]
    return ""


def feedback_review_queue_bulk_review_action(
    candidate_tag: str,
    *,
    feedback_source_counts: object = None,
    expected_citation_counts: object = None,
) -> str:
    source_arg = feedback_source_filter_arg(feedback_source_counts)
    source = source_arg.removeprefix("--source ").strip() if source_arg else ""
    citation_counts: Mapping[object, object] = (
        cast(Mapping[object, object], expected_citation_counts)
        if isinstance(expected_citation_counts, Mapping)
        else {}
    )
    expected_citation_tags = [
        f"expected-citation:{citation_id}"
        for citation_id, count in sorted(citation_counts.items())
        if isinstance(citation_id, str)
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count > 0
        and is_citation_safe_id(citation_id)
    ]
    return rag_candidate_feedback_bulk_review_action(
        candidate_tag,
        source=source,
        extra_review_tags=expected_citation_tags,
    )


def candidate_workflow_tag_from_case_ids(case_ids: Sequence[str]) -> str:
    candidate_ids: list[str] = []
    for case_id in case_ids:
        stripped = case_id.strip()
        candidate_id = ""
        for prefix in ("case-rag-candidate-", "case_rag_candidate_"):
            if stripped.startswith(prefix):
                candidate_id = stripped.removeprefix(prefix).strip()
                break
        if not candidate_id or command_slug(candidate_id) != candidate_id:
            return ""
        candidate_ids.append(candidate_id)
    if not candidate_ids or len(set(candidate_ids)) != 1:
        return ""
    return f"rag-candidate:{candidate_ids[0]}"


def valid_rag_candidate_case_id(case_id: str) -> bool:
    return rag_candidate_slug_from_case_id(case_id) is not None


def preferred_feedback_workflow_tag(
    workflow_mapping: Mapping[object, object],
    *,
    required_count: int,
) -> str:
    eligible = sorted(
        str(tag).strip()
        for tag, count in workflow_mapping.items()
        if str(tag).strip()
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count >= required_count
    )
    for prefix in ("rag-candidate:",):
        for tag in eligible:
            if tag.startswith(prefix) and valid_candidate_workflow_tag(tag):
                return tag
    if "memory" in eligible:
        return "memory"
    for tag in eligible:
        if tag.startswith("collection:"):
            return tag
    if "grounding" in eligible:
        return "grounding"
    if "rag" in eligible:
        return "rag"
    return eligible[0] if eligible else ""


def feedback_source_filter_arg(source_counts: object) -> str:
    if not isinstance(source_counts, Mapping):
        return ""
    source_mapping = cast(Mapping[object, object], source_counts)
    sources = [
        str(source).strip()
        for source, count in source_mapping.items()
        if str(source).strip()
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count > 0
    ]
    return f"--source {quote(sources[0])} " if len(sources) == 1 else ""


def valid_candidate_workflow_tag(tag: str) -> bool:
    prefix = "rag-candidate:"
    if not tag.startswith(prefix):
        return False
    candidate_slug = tag.removeprefix(prefix).strip()
    return is_command_slug(candidate_slug)


def release_evidence_contract_failure(*, name: str, item: Mapping[str, object]) -> str | None:
    if name != "release_evidence":
        return None
    if item.get("status") != "passed":
        return None
    release_evidence = item.get("releaseEvidence")
    if release_evidence_summary_failure(release_evidence):
        return "release evidence contract missing"
    return None


def release_evidence_summary_failure(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    mapping = cast(Mapping[str, object], value)
    if set(mapping) != {"gateCount", "gateCodes", "scopes", "statusCounts"}:
        return True
    gate_count = mapping.get("gateCount")
    if not isinstance(gate_count, int) or isinstance(gate_count, bool) or gate_count <= 0:
        return True
    gate_codes = mapping.get("gateCodes")
    if not non_empty_string_sequence(gate_codes):
        return True
    typed_gate_codes = cast(Sequence[str], gate_codes)
    if len(typed_gate_codes) != gate_count or len(set(typed_gate_codes)) != len(typed_gate_codes):
        return True
    if not positive_int_mapping(mapping.get("scopes")):
        return True
    status_counts = mapping.get("statusCounts")
    if not positive_int_mapping(status_counts):
        return True
    return sum(cast(Mapping[str, int], status_counts).values()) != gate_count


def non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def string_sequence(value: object) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return False
    return all(isinstance(item, str) for item in cast(Sequence[object], value))


def non_empty_mapping_sequence(value: object) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return False
    items = cast(Sequence[object], value)
    if len(items) == 0:
        return False
    for item in items:
        if not isinstance(item, Mapping):
            return False
        mapping = cast(Mapping[object, object], item)
        if len(mapping) == 0:
            return False
    return True
