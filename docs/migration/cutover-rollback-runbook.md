# Reactor Python/LangGraph Cutover And Rollback Runbook

This runbook is the production gate for switching retained Reactor data from the
backup Kotlin/Spring system into the Python 3.13/FastAPI/LangGraph runtime.

## Required Inputs

- Frozen legacy PostgreSQL connection string with write traffic stopped.
- Python target PostgreSQL connection string on the final Alembic schema.
- Exported retained-data NDJSON.
- Imported retained-data NDJSON or migration import ledger export.
- Rollback snapshot NDJSON captured from the Python target before import.
- JSON parity report from `reactor-migration-report`.
- JSON cutover readiness report from `reactor-migration-cutover`.
- File-backed dress rehearsal output from `reactor-migration-dress-rehearsal` before
  using the same exported artifact against staging or production target stores.

## No-Go Gates

Do not cut over when any of these are true:

- Legacy writes are still active.
- Alembic migrations have not been applied to the target database.
- Export contains skipped rows that have not been reviewed and explicitly accepted.
- Count/checksum parity fails for any retained table.
- Rollback snapshot is missing for an imported table, unless the migration owner has
  explicitly accepted that the table had no target pre-state to restore.
- Full Python verification gate fails:

```bash
uv lock --check
uv run ruff format --check
uv run ruff check
uv run pyright
uv run pytest -q
```

## Cutover Procedure

1. Freeze legacy writes.
   - Stop scheduled workers, Slack event consumers, A2A/MCP background sync, and any
     write-capable admin jobs in the Kotlin/Spring deployment.
   - Keep read-only diagnostics available until Python health checks pass.

2. Apply the Python schema.
   - Run Alembic migrations against the target database.
   - Confirm `pgvector` is available for RAG and memory embeddings.

3. Capture rollback snapshot.
   - Snapshot every target table that will receive imported retained data.
   - Store the snapshot as immutable NDJSON and retain it through burn-in.

4. Export legacy retained data.
   - Use the configured source readers in deterministic order.
   - Preserve source table, source primary key, payload checksum, and export timestamp.
   - Review any `record_type="skipped"` entries before continuing.

5. Import into staging first.
   - Import the exported NDJSON into a staging target using the same schema and target
     writers as production.
   - Export the migration import ledger for the staging batch.

6. Generate parity report.

```bash
reactor-migration-report \
  --exported /path/to/exported.ndjson \
  --imported /path/to/imported.ndjson \
  --output /path/to/parity-report.json
```

7. Generate cutover readiness report.

```bash
reactor-migration-cutover \
  --exported /path/to/exported.ndjson \
  --imported /path/to/imported.ndjson \
  --rollback /path/to/rollback-snapshot.ndjson \
  --output /path/to/cutover-readiness.json \
  --required-table-file docs/migration/retained-table-manifest.txt
```

Only use `--allow-skipped` or `--allow-missing-rollback` when the migration owner
has reviewed the specific rows/tables and recorded the reason in the cutover ticket.
For production cutover, use `docs/migration/retained-table-manifest.txt` or another
reviewed manifest containing every retained table in the approved migration inventory.
A readiness report generated without the full retained table manifest is smoke
evidence only; it is not full backup DB dress rehearsal evidence.

8. Run the file-backed dress rehearsal command.

```bash
reactor-migration-dress-rehearsal \
  --exported /path/to/exported.ndjson \
  --rollback /path/to/rollback-snapshot.ndjson \
  --imported-output /path/to/dress-rehearsal-imported.ndjson \
  --readiness-output /path/to/dress-rehearsal-readiness.json \
  --batch-id staging-dress-rehearsal \
  --required-table-file docs/migration/retained-table-manifest.txt
```

The command must exit `0` and its readiness report must contain `ok=true`. This
does not replace the staging database import; it proves the exact exported and
rollback artifacts can pass the shared rehearsal/readiness path before target-store
execution. Use the same complete `--required-table` list here as the production
readiness command.

9. Import into production.
   - Reuse the exact exported NDJSON that passed staging readiness.
   - Use a new production batch id.
   - Keep the import ledger and rollback snapshot immutable.

10. Switch runtime traffic.
   - Enable Python FastAPI ingress, LangGraph workers, Slack consumers, scheduler,
     MCP sync, A2A endpoint, and outbox dispatchers.
   - Keep Kotlin/Spring write paths disabled.

11. Burn in.
    - Watch API errors, agent run completion, stream replay, Slack delivery,
      scheduler leases, outbox/dead-letter counts, RAG retrieval, memory proposal
      queues, token/cost ledger writes, and guard denials.

## Rollback Procedure

1. Stop Python write traffic immediately.
2. Disable Python workers and external event consumers.
3. Restore rows from the rollback snapshot for every imported target table.
4. Re-enable the Kotlin/Spring deployment only after confirming restored counts and
   checksums against the pre-import snapshot.
5. Preserve failed production import ledgers and readiness reports for incident review.

## Completion Evidence

Cutover is not complete until these artifacts are attached to the release record:

- Exported retained-data NDJSON checksum.
- Rollback snapshot NDJSON checksum.
- Staging parity report with `ok=true`.
- Cutover readiness report with `ok=true`.
- File-backed dress rehearsal imported NDJSON and readiness report with `ok=true`.
- Full Python verification gate output.
- Production smoke evidence for API, LangGraph agent run, streaming replay, Slack,
  scheduler, MCP, A2A, RAG, memory, admin, and observability surfaces.
