# Scenario Matrix Validation

`scripts/dev/validate-scenario-matrix.py` runs API validation by scenario definitions and matrix expansion.

## Scenario Pack

- File: `scripts/dev/scenarios/user-activity-matrix.json`
- Case groups:
  - `contract`: auth/permission/validation contracts
  - `stable`: tool-invocation matrix expected to pass consistently
  - `known-limited`: tools that typically require more input (or are environment-limited)

Current size (full expansion):

- `contract`: 6
- `stable`: 13 tools x 3 channels x 6 activities = 234
- `known-limited`: 7 tools x 3 channels x 6 activities = 126
- Total: 366

### Golden Pack

- File: `scripts/dev/scenarios/integration-golden-scenarios.json`
- Purpose: deterministic regression for external MCP skill routing and response safety.
- Expansion:
  - 48 tools x 3 channels x 6 activities x 4 personas = 3456
  - + contract checks 2
  - Total: 3458
- Golden expectations per tool case:
  - HTTP `200`
  - `success=true`
  - `toolsUsed` must include the exact target tool
  - response must NOT include unknown-error / rate-limit patterns

### Agent Effect Canary

- File: `scripts/dev/scenarios/agent-effect-canary.json`
- Purpose: live canary for the agent hardening work: casual no-tool behavior, workspace read-only routing,
  grounding, latency, rate-limit noise, and max tool calls per case.
- The pack includes `qualityGates`; the validator fails the run if pass rate, latency, rate-limit, or tool count
  thresholds are exceeded.

## Quick Start

1. Contract-only check:

```bash
ADMIN_TOKEN="<admin-jwt>"
python3 scripts/dev/validate-scenario-matrix.py \
  --base-url http://localhost:8080 \
  --scenario-file scripts/dev/scenarios/user-activity-matrix.json \
  --admin-token "$ADMIN_TOKEN" \
  --include-tags contract \
  --report-file /tmp/reactor-scenario-contract.json
```

2. Stable tool sample (fast):

```bash
python3 scripts/dev/validate-scenario-matrix.py \
  --base-url http://localhost:8080 \
  --scenario-file scripts/dev/scenarios/user-activity-matrix.json \
  --admin-token "$ADMIN_TOKEN" \
  --include-tags stable \
  --max-cases 20 \
  --seed 11 \
  --report-file /tmp/reactor-scenario-stable-sample.json
```

3. Full stable matrix (rate-limit aware):

```bash
python3 scripts/dev/validate-scenario-matrix.py \
  --base-url http://localhost:8080 \
  --scenario-file scripts/dev/scenarios/user-activity-matrix.json \
  --admin-token "$ADMIN_TOKEN" \
  --include-tags stable \
  --case-delay-ms 3100 \
  --rate-limit-backoff-sec 65 \
  --report-file /tmp/reactor-scenario-stable-full.json
```

4. Golden sample (recommended first run):

```bash
python3 scripts/dev/validate-scenario-matrix.py \
  --base-url http://localhost:8080 \
  --scenario-file scripts/dev/scenarios/integration-golden-scenarios.json \
  --admin-token "$ADMIN_TOKEN" \
  --include-tags golden \
  --max-cases 40 \
  --seed 26 \
  --case-delay-ms 600 \
  --report-file /tmp/reactor-scenario-golden-sample.json
```

5. Golden full run:

```bash
python3 scripts/dev/validate-scenario-matrix.py \
  --base-url http://localhost:8080 \
  --scenario-file scripts/dev/scenarios/integration-golden-scenarios.json \
  --admin-token "$ADMIN_TOKEN" \
  --include-tags golden \
  --case-delay-ms 900 \
  --rate-limit-backoff-sec 65 \
  --report-file /tmp/reactor-scenario-golden-full.json
```

6. Agent effect canary:

```bash
python3 scripts/dev/validate-scenario-matrix.py \
  --base-url http://localhost:8080 \
  --scenario-file scripts/dev/scenarios/agent-effect-canary.json \
  --case-delay-ms 1000 \
  --strict \
  --report-file /tmp/reactor-agent-effect-canary.json
```

## Useful Flags

- `--include-tags <csv>`: run only matching tags
- `--exclude-tags <csv>`: exclude tags
- `--max-cases <n>`: random sample from expanded matrix
- `--seed <n>`: deterministic sampling
- `--case-delay-ms <n>`: delay between cases
- `--rate-limit-backoff-sec <n>`: sleep when rate limit is detected
- `--strict`: fail if any case is skipped
- `--stop-on-fail`: stop at first failure

## Output

The script prints per-case PASS/FAIL and writes JSON report:

- summary (`total`, `passed`, `failed`, `skipped`, `rateLimited`, `passRate`, `averageDurationMs`,
  `p95DurationMs`, `maxToolsUsedCount`)
- per-case observations (`toolsUsed`, `toolsUsedCount`, `contentLength`, `tokenUsage`)
- per-case attempt details (`httpStatus`, `durationMs`, failures, body snippet)
- `qualityGateFailures` when the scenario file defines `qualityGates`

Use the report to compare expected behavior across user activity patterns and environment changes.
