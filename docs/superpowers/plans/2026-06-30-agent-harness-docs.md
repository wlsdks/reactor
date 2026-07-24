# Agent Harness Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh Reactor's agent harness documentation so AGENTS.md, CLAUDE.md, and the canonical architecture docs encode current LangChain, LangGraph, LangSmith, and public agent-harness practice without weakening Reactor's focused verification strategy.

**Architecture:** Keep instruction files short and put durable operational detail in `docs/architecture/agent-harness-operating-model.md` and `docs/architecture/python-langgraph-replatform-spec.md`. Treat external references as source basis, while Reactor-owned policy remains tenancy, approvals, audit, idempotency, ACLs, redaction, and release evidence.

**Tech Stack:** Markdown docs, uv static gates, existing Reactor verification commands.

---

### Task 1: Source Basis And Harness Rules

**Files:**
- Modify: `docs/architecture/agent-harness-operating-model.md`
- Modify: `docs/architecture/python-langgraph-replatform-spec.md`
- Test: `tests/unit/test_agent_harness_docs.py`

- [x] **Step 1: Write the failing document contract test**

Add `tests/unit/test_agent_harness_docs.py` to pin:

- public source basis as of 2026-06-29
- Component layer, Experience layer, and Decision layer harness loop
- LangGraph durable execution, interrupts, and streaming contracts
- LangChain middleware ownership of generic controls
- LangSmith offline evals and online observability split
- compact AGENTS/CLAUDE instruction-map alignment

Run: `uv run pytest tests/unit/test_agent_harness_docs.py -q`

Expected: FAIL before the docs are updated.

- [x] **Step 2: Update source basis**

Add a dated source-basis section that separates official framework docs from public agent-harness operating guidance and keeps Reactor-specific decisions explicit.

- [x] **Step 3: Add operating rules**

Add concise sections for source-of-truth hierarchy, Component/Experience/Decision harness loops, context/tool budget, structured output/citation expectations, eval/observability gates, and feedback-loop escalation.

- [x] **Step 4: Verify focused docs text**

Run: `uv run pytest tests/unit/test_agent_harness_docs.py -q`

Expected: focused document contract test passes.

### Task 2: Instruction File Alignment

**Files:**
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`

- [x] **Step 1: Add CodeGraph and source-of-truth navigation**

Ensure both instruction files tell agents to use CodeGraph for structural questions and canonical docs for durable rules.

- [x] **Step 2: Preserve partial-test strategy**

Ensure both files keep focused-first verification and full-gate escalation criteria instead of implying CI or full pytest after every edit.

- [x] **Step 3: Add compact harness-source guidance**

Ensure both files point to the harness source basis and the Component/Experience/Decision loop without turning session files into manuals.

### Task 3: Commit-Ready Verification

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/reactor/__init__.py`
- Modify: `docs/superpowers/plans/2026-06-30-agent-harness-docs.md`

- [x] **Step 1: Bump release metadata**

Update `pyproject.toml` and `src/reactor/__init__.py` from `1.0.13` to `1.0.14`.

- [x] **Step 2: Run static gates**

Run:

```bash
uv lock --check
uv run ruff check
uv run ruff format --check
uv run pyright
```

Expected: all static gates pass.

- [x] **Step 3: Run focused affected lane**

Run: `uv run pytest tests/unit/test_agent_harness_docs.py -q`

Expected: document contract passes.

- [ ] **Step 4: Prepare the separate docs commit**

Run:

```bash
git add AGENTS.md CLAUDE.md docs/architecture/agent-harness-operating-model.md docs/architecture/python-langgraph-replatform-spec.md docs/superpowers/plans/2026-06-30-agent-harness-docs.md tests/unit/test_agent_harness_docs.py pyproject.toml src/reactor/__init__.py
git commit -m "docs: harden agent harness operating model"
git tag v1.0.14
git push origin main
git push origin v1.0.14
```

Expected: release metadata, commit, branch, and tag are published.
