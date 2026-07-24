# Security Policy

## Supported Versions

The Python/LangGraph replatform is the supported development line. Security fixes
target the current mainline and actively maintained release branches.

## Reporting a Vulnerability

Do not open a public issue for security vulnerabilities.

Use GitHub private vulnerability reporting from the repository's **Security** tab
when it is available. Otherwise, contact the repository owner without posting
sensitive details publicly.

Report privately with:

- affected commit or release
- reproduction steps
- impact and affected boundary
- relevant logs or traces with secrets redacted
- whether credentials, tenant data, tools, artifacts, or external side effects are
  involved

Expected response:

- acknowledgment within 48 hours
- initial assessment within 1 week
- fix or mitigation plan within 2 weeks for confirmed vulnerabilities

## In Scope

- Guard, approval, sandbox, or tool-policy bypasses
- Prompt injection that reaches model-visible trusted context
- MCP or A2A trust-boundary failures
- Tenant, ACL, RAG, memory, checkpoint, or artifact isolation failures
- Secret exposure in config, logs, traces, prompts, model context, or agent cards
- Unsafe deserialization or user-controlled dynamic imports
- Durable work idempotency, outbox, inbox, or replay flaws
- Direct dependency vulnerabilities with a reachable exploit path

## Out of Scope

- Issues requiring physical access to the server
- Social engineering against operators
- Denial of service through authorized high-volume usage where documented limits are
  configured by the operator
- Vulnerabilities introduced only by downstream private modifications

## Credential Exposure Response

If an API key, model credential, signing secret, webhook URL, database password, or
storage credential is exposed:

1. Revoke and rotate the credential immediately.
2. Invalidate affected sessions, tokens, and webhooks.
3. Review Reactor audit logs, provider logs, and infrastructure logs.
4. Remove exposed values from code, docs, CI logs, traces, and model-visible context.
5. Add a post-incident note with impact, timeline, and remediation.

Treat exposure as a security incident even if no abuse is confirmed.

## Production Security Baseline

- Set `LANGGRAPH_STRICT_MSGPACK=true` before LangGraph imports.
- Keep API keys and secrets out of default config files.
- Disable untrusted LangChain object deserialization.
- Validate checkpoint metadata and retrieval filter keys against allowlists.
- Store durable agent state in PostgreSQL, not Redis.
- Filter tenant and ACL predicates before ranking or limiting RAG results.
- Redact secrets, credentials, PII, and private tool payloads in logs, traces, and
  model-visible context.
- Require approval or sandbox policy for write, destructive, shell, browser,
  file-write, and external-side-effect tools.
- Use outbox/idempotency records before dispatching external side effects.
