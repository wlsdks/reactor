# Reactor Admin Full-Surface Redesign Audit

Date: 2026-07-11
Status: active long-running redesign program

## Objective

Audit and redesign every user-visible Reactor Admin route so the application reads as one mature operations product. This is not a theme pass. Each page must translate backend evidence into intentional operator UI instead of exposing debug text, raw keys, or generic dashboard patterns.

## Global failure classes

These are release-blocking design defects when they appear in a primary workflow:

1. Raw implementation language: `snake_case`, report IDs, internal enum values, raw commands, or English contract keys shown as primary copy.
2. Browser-default presentation: blue/purple links, unstyled lists, default code blocks, or controls inheriting browser typography.
3. AI dashboard patterns: equal metric tiles, repeated PASS pills, card grids used as a feature inventory, decorative vertical rails, nested rounded containers, and status color repeated without information value.
4. Broken density: large empty metric boxes for small values, or dense multi-column content that collapses into one-character/vertical text.
5. Workflow duplication: the same release step links repeated in page header, panel header, cards, and footer without a clear next action.
6. Weak hierarchy: labels, values, evidence, actions, and remediation copy presented at nearly the same weight.
7. Responsive failure: any supported width that clips controls, creates horizontal overflow, or makes Korean/English words stack vertically.

## Required page grammar

- One page title and one concise purpose sentence.
- One primary operator action at most; secondary actions are contextual.
- Use rows, tables, definition lists, inspectors, and disclosure for operational data before cards.
- Cards are reserved for independent objects, not labels or scalar values.
- Status appears once per decision level as a dot + plain word unless a blocking alert needs stronger treatment.
- Internal evidence IDs must have a human label; raw IDs belong in secondary monospace detail.
- Links always use product tokens and descriptive labels.
- At 989px and 1440px, body copy must remain horizontally readable; no one-character columns.
- Empty states explain what is absent and what action is available; they do not render tall empty metric containers.

## Route census

### Shell and access

- `/login`
- `*` not-found state
- shared header, LNB expanded/collapsed, footer, loading/error/forbidden states

### Today and AI settings

- `/`
- `/health`
- `/issues`
- `/approvals`
- `/personas`
- `/prompt-studio`
- `/reactor-universe`

### Release workflow

- `/release`
- `/documents`
- `/rag-cache`
- `/feedback`
- `/evals`
- `/integrations`
- `/models`

### Safety, monitoring, and analysis

- `/safety-rules`
- `/sessions`
- `/sessions/feed`
- `/sessions/users`
- `/sessions/users/:userId`
- `/sessions/:sessionId`
- `/traces`
- `/audit`
- `/performance`
- `/usage`

### Management and developer tools

- `/tenants`
- `/settings`
- `/access-control`
- `/mcp-servers`
- `/mcp-servers/:name`
- `/chat-inspector`
- `/scheduler`
- `/metrics-ingestion`
- `/debug-replay`

Redirect-only legacy routes are excluded from visual redesign but must resolve to the correct target surface.

## Milestone 1 evidence: release workflow capture

Capture folder: `.playwright-mcp/admin-audit-2026-07-11/`
Viewport: 989 x 812 CSS pixels
Backend: live local Reactor backend

| Step | Route | Health | Evidence-backed finding | Required direction |
| --- | --- | --- | --- | --- |
| 1 | `/release#release-cockpit` | Poor | Long raw shell command dominates; scalar cards and nested panels repeat status; English operator instructions leak into Korean UI. | Decision summary + prioritized blockers + command disclosure. |
| 2 | `/documents?tab=ingestion` | Poor | Four tall boxes contain only `0`; repeated workflow buttons compete with the page task. | Ingestion queue/table + compact empty state + one next action. |
| 3 | `/rag-cache?tab=rag` | Poor | Multiple tabs, status strip, accordion, pills, and follow-up buttons compete; evidence is prose-heavy. | Lifecycle checklist/table with one selected-stage detail. |
| 4 | `/feedback#feedback-promotion` | Broken | At 989px, title and body text collapse into one-character vertical columns. Primary task is unusable. | Responsive list-detail promotion queue; P0 layout fix first. |
| 5 | `/evals#eval-regression` | Broken | Card grids collapse into narrow columns; raw evidence IDs wrap vertically; repeated PASS/EVIDENCE pills obscure meaning. | Evaluation run table + selected suite inspector; P0 layout fix first. |
| 6 | `/integrations#release-smoke` | Poor | Four equal PASS metrics repeat one summary; reports and env are disconnected from the action queue. | Selected concept: prioritized smoke queue + inspector + recent runs. |
| 7 | `/models#provider-smoke` | Poor | Large scalar cards, blue callout, nested smoke panel, and mixed Korean/English copy create a prototype feel. | Provider registry table + selected provider smoke inspector. |

## Immediate priority

1. ~~Fix P0 responsive collapse in Feedback and Evals.~~ Completed in the first primitive pass.
2. Replace shared scalar-card and release-link inventories with table/list/inspector primitives.
3. Redesign the seven release workflow pages using one navigation and evidence vocabulary.
4. Continue capture and scoring for every remaining route before declaring any page family complete.

## Verification contract per page

- Current-state screenshot accepted and inspected.
- Page-specific information hierarchy documented.
- Focused test for the new semantic structure or responsive contract.
- Nearest affected test lane passes.
- ESLint and production build pass at milestone boundary.
- Browser QA at 1440px target and current/narrow viewport.
- No raw-key, browser-default-link, vertical-text, nested-card, or repeated-status regression.

## Milestone 1 iteration: PageHeader and narrow evidence layouts

Before evidence:

- `.playwright-mcp/admin-audit-2026-07-11/04.png`
- `.playwright-mcp/admin-audit-2026-07-11/05.png`

After evidence:

- `.playwright-mcp/admin-audit-2026-07-11/04-feedback-after.png`
- `.playwright-mcp/admin-audit-2026-07-11/05-evals-after.png`

Measured at 989 x 812:

- Feedback `h1` width changed from `0px` to `693px` after the shared PageHeader action row began stacking before the mobile breakpoint.
- Feedback and Evals both report zero visible long-text nodes narrower than 24px.
- Evals has no document-level horizontal overflow.
- Release workflow inventories switch from fixed 3-5 column grids to readable rows at compact-laptop widths.

This iteration restores usability but does not close the page redesign. Scalar stat cards, repeated status pills, and raw evidence IDs remain tracked P1 design debt for the next release-workflow milestone.

## Milestone 3 iteration: integration release smoke overview

Before evidence: `.playwright-mcp/admin-audit-2026-07-11/06.png`

After evidence: `.playwright-mcp/admin-audit-2026-07-11/38-integrations-release-smoke-after.png`

The release-smoke overview now expresses the aggregate decision once as a status dot and sentence. The four 120px KPI boxes became a 64px evidence row, duplicated PASS/complete captions were removed, and the four workflow cards use a two-column readable list with plain step numbers and dot statuses instead of circular indices and pills. Report IDs such as `smoke_run` and `langsmith_eval_sync` are translated into operator labels while retaining the source ID in secondary metadata. The page header now has one purpose sentence and no floating help icon.

At 1280 x 720, the overview has no horizontal overflow, no narrow vertical-text nodes, two 478px workflow columns, and no status badge in the decision header. Overview → 실행 anchor navigation was exercised and changed the URL to `#external-smoke-operations`. A clean reload produced no new console warnings or errors; earlier `useAuth` errors were limited to the hot-module replacement window and did not recur after reload. Detailed Slack/A2A/provider evidence sections remain open for the later evidence-inspector pass.

## Milestone 3 iteration: provider release smoke entry

Before evidence: `.playwright-mcp/admin-audit-2026-07-11/07.png`

After evidence: `.playwright-mcp/admin-audit-2026-07-11/39-model-provider-after.png`

The two large model KPI cards became a 66px definition row and the blue nested handoff alert became a flat release-condition section. The provider evidence header now uses a status dot and text rather than a badge, while visible mixed-language contract copy was rewritten into operator-oriented Korean. At 1280 x 720, the first viewport has zero StatCards, zero top-level provider badges, zero alert-styled handoff containers, no overflow, no narrow vertical text, and no fresh console warnings or errors. The live-operation section, workflow list, and deep evidence grid remain open for the selected-inspector redesign.

## Milestone 3 iteration: release cockpit decision entry

Before evidence: `.playwright-mcp/admin-audit-2026-07-11/01.png`

After evidence: `.playwright-mcp/admin-audit-2026-07-11/40-release-cockpit-top-after.png`

The cockpit entry no longer presents the entire release decision inside a raised rounded card. Its outer shadow, radius, and filled surface were removed; recommended tag, version bump, and minor eligibility now occupy a 66px definition row. The aggregate status appears once as a dot and word, and the repeated decision-summary badge was removed. At 1280 x 720 the entry has no header badges, metric-card borders, shadow, radius, overflow, narrow vertical text, or fresh console errors. Thirty-five badges still exist deeper in gate/evidence sections, so the cockpit is not complete until those sections become prioritized rows and a selected evidence inspector.

## Milestone 1 evidence: Today and AI settings capture

Capture files: `.playwright-mcp/admin-audit-2026-07-11/08.png` through `14.png`

| Route | Health | Evidence-backed finding | Required direction |
| --- | --- | --- | --- |
| `/` | Poor | Dashboard exposes untranslated/internal signal keys such as MCP/runtime policy identifiers; multiple stat surfaces and dim cards compete with the primary work queue. | Operator work queue first, human labels, release summary as a compact row. |
| `/health` | Broken | The route renders a generic section error and the browser title falls back to `Reactor Admin`; the intended status content cannot be audited. | Diagnose the route failure before visual redesign; then use service rows with explicit remediation. |
| `/issues` | Poor | Topology labels expose i18n keys (`issuesPage.topology.*`); decorative graph consumes the first viewport before the actionable issue list. | Default to prioritized issue list; topology becomes an optional secondary view with human labels. |
| `/approvals` | Poor | Empty state uses a large readiness container and two scalar `0` cards, leaving most of the viewport blank. | Compact readiness sentence + empty queue state; details disclosed only when checks fail. |
| `/personas` | Poor | Two large `0` stat cards duplicate the empty state and both the header and empty state offer creation actions. | One creation action and a concise empty collection state with an optional example disclosure. |
| `/prompt-studio` | Poor | Two vertically separated empty states and tutorial copy create excessive blank space and duplicate the absent-data message. | One template collection empty state; detail pane appears only after selection. |
| `/reactor-universe` | Poor | Empty state is followed by a boxed three-card explainer and example panel, reproducing the card-in-card onboarding pattern. | One concise empty state with a short expandable explanation or documentation link. |

Cross-route findings:

- No horizontal overflow or vertical-text collapse was detected in this group after the PageHeader primitive fix.
- Empty collection pages repeatedly combine scalar stat cards, a central empty state, duplicate CTA buttons, and tutorial cards. A shared `CollectionEmptyState` contract should replace this pattern.
- Raw i18n or backend keys are visible on Dashboard and Issues and must be treated as product defects, not cosmetic copy polish.

## Milestone 1 evidence: safety, monitoring, and analysis capture

Capture files: `.playwright-mcp/admin-audit-2026-07-11/15.png` through `22.png`

| Route | Health | Evidence-backed finding | Required direction |
| --- | --- | --- | --- |
| `/safety-rules` | Fair | The policy editor is usable, but release-step chrome, two levels of tabs, and each stage as a bordered card make a simple ordered pipeline feel heavier than it is. | Compact policy navigation + ordered rule table; reserve a side inspector for the selected rule. |
| `/sessions` | Broken | The entire route is replaced by a generic section error with no diagnostic context or alternate path. | Repair the data contract and provide a recoverable error state that names the failed resource. |
| `/sessions/feed` | Poor | Search and five pill-like filters dominate a two-row result list; actor IDs and English prompts are truncated before useful session evidence. | Dense session table with explicit columns, search/filter toolbar, and selected-session inspector. |
| `/sessions/users` | Poor | Mixed Korean/English metadata (`Last active.`), truncated user identity, and separated filter/export controls weaken scanability. | User activity table with human identity fallback, localized metadata, and contextual export. |
| `/traces` | Broken | Raw translation keys and enum labels are visible; latency renders as `NaNm NaNs`; four large scalar cards amplify invalid data. | Fail closed on invalid duration, humanize status, and use a trace table with selected-span waterfall. |
| `/audit` | Poor | Four large readiness metrics repeat counts inside a nested panel; filters lack a clear query hierarchy and warning status competes with page content. | Query toolbar + audit event table + selected-event inspector; readiness becomes one compact precondition row. |
| `/performance` | Broken | P50/P95/P99 values render as `NaNs` while an empty chart occupies most of the viewport. | Treat absent samples as an explicit empty state; render percentile summary only with valid samples. |
| `/usage` | Poor | Seven equal cost/token cards and a blank chart create a generic dashboard with no operator decision or anomaly context. | Cost trend first, compact totals row, breakdown table, and explicit no-cost-data state. |

Cross-route findings:

- Invalid numeric values (`NaN`) and untranslated keys must be blocked at the view-model boundary; CSS cannot repair these product defects.
- Monitoring pages need a consistent list-detail grammar: filter toolbar, operational table, selected-record inspector, and a compact empty/error state.
- Release-step backlinks should not occupy first-view content on every operational page; retain one contextual route affordance in the page metadata layer.

## Milestone 1 evidence: management and developer tools capture

Capture files: `.playwright-mcp/admin-audit-2026-07-11/23.png` through `30.png`

| Route | Health | Evidence-backed finding | Required direction |
| --- | --- | --- | --- |
| `/tenants` | Poor | A tall empty tenant panel is followed immediately by a full creation form and another analytics empty state, producing three competing modes in one scroll. | Tenant table first; creation in a dedicated drawer/page; analytics only after a tenant is selected. |
| `/settings` | Poor | An absent settings result leaves most of the page blank while release links and cache/Slack actions remain visually prominent. | Settings category list + selected setting inspector; global refresh actions move to contextual utilities. |
| `/access-control` | Broken | Role names, descriptions, group keys, and action keys expose raw `rbacPage.*` identifiers throughout the primary UI. | Add a typed human-label boundary and use a role-permission comparison matrix with detail disclosure. |
| `/mcp-servers` | Poor | Four large zero cards, global actions, search, status filter, and empty state all compete before any server exists. | Server registry table + concise empty state; destructive global controls live in a guarded overflow area. |
| `/chat-inspector` | Fair | The form is readable, but independent bordered containers and always-visible setup fields make the single request workflow feel fragmented. | One task form with progressive options and a persistent response inspector, not stacked cards. |
| `/scheduler` | Poor | Empty readiness metrics, warning pills, saved-view controls, and a long explanatory panel overwhelm the absent job list. | Job table/empty state first; readiness problems become actionable rows with remediation. |
| `/metrics-ingestion` | Poor | Raw endpoint and JSON payload are the primary interface; tab inventory and an empty response panel present a developer harness rather than an operator tool. | Guided request form + payload preview disclosure + structured response/result history. |
| `/debug-replay` | Fair | The empty state is clean, but the page still exposes English product naming and a release backlink without explaining the capture/replay boundary. | Localized failure queue with capture criteria and selected replay timeline when data exists. |

Cross-route findings:

- Empty management pages repeatedly render large zero metrics before the collection they summarize. Totals belong in table metadata, not separate cards.
- Creation, selection, and analytics should not be simultaneous full-width modes. Use list-detail or list-drawer composition.
- Developer tools may preserve monospace payloads, but raw requests must be secondary previews behind a guided operator task.

## Milestone 1 evidence: shell and access states

Capture files:

- `.playwright-mcp/admin-audit-2026-07-11/31-not-found.png`
- `.playwright-mcp/admin-audit-2026-07-11/32-login.png`

| Surface | Health | Evidence-backed finding | Required direction |
| --- | --- | --- | --- |
| Not found | Poor | A huge decorative `404` and three recommendation cards turn a simple recovery state into another card inventory. | Compact error heading, attempted path, and two recovery actions; command-palette help remains inline. |
| Login | Poor | The login surface uses the stale `Reactor Admin` identity while the product shell uses Reactor; demo and development access appear as equal public actions. | Unify Reactor identity and visually separate environment-only access from the production sign-in contract. |
| Dynamic session detail | Blocked | The current feed exposes no session detail links and `/sessions` fails, so a valid `:sessionId`/`:userId` state could not be reached from live UI evidence. | Repair the session collection contract, then capture populated, empty, loading, forbidden, and failed detail states. |
| MCP server detail | Blocked | No MCP registrations exist in the connected backend, so a valid `:name` detail route is unavailable. | Capture and redesign after a safe test registration exists; do not fabricate a detail-only state. |

The first census is complete for every reachable static route. Dynamic detail and authorization-state evidence remain explicitly open and cannot be marked complete from empty fixtures.

## Milestone 3 iteration: document release handoff

After evidence:

- `.playwright-mcp/admin-audit-2026-07-11/36-documents-handoff-after.png`
- `.playwright-mcp/admin-audit-2026-07-11/37-documents-search-after.png`

The ingestion and search-result handoffs no longer render five equal stat cards or four competing workflow buttons. Both now use a compact definition row, one explicit next-step link, and a collapsed related-stage disclosure. At the 989 x 812 audit viewport, both handoffs have zero nested stat cards, zero narrow vertical-text nodes, and no document overflow. This closes the handoff subsection only; the document page header workflow toolbar, candidate review form, and remaining tabs stay open in the release-workflow milestone.

## Milestone 3 iteration: release evidence hierarchy

After evidence: `.playwright-mcp/admin-audit-2026-07-11/41-release-evidence-flat-sections-after.png`

The release evidence view now uses open, separated sections instead of a stack of bordered cards. Repeated evidence fields and recommendation facts use two readable columns with row dividers; gate readiness is a single vertical operations checklist rather than a three-column card grid. Cockpit status components retain their semantic labels but render as a restrained status dot and text, so none of the 35 status instances has a pill background or rounded container. Related report identifiers now render through the shared human-label boundary while preserving the raw identifier for accessibility and traceability. At 1280px the view has no horizontal overflow, no pill-shaped cockpit statuses, and no fresh console warnings or errors. Raw backend values inside detailed evidence remain an explicit follow-up for the report presenter layer; this iteration closes structure and hierarchy, not full evidence copy normalization.

## Milestone 3 iteration: RAG lifecycle scan path

After evidence: `.playwright-mcp/admin-audit-2026-07-11/42-rag-lifecycle-rows-after.png`

The RAG lifecycle check no longer renders a bordered disclosure containing four card-like status rows and three competing header actions. Its expanded state is now a flat ordered scan path: stage, semantic status dot, and explanation share one row, with feedback and LangSmith handoffs demoted to quiet text links below the evidence. The inactive zero-candidate button is absent instead of occupying the primary heading. The populated candidate action remains available when work exists. Browser QA at 1280px showed the complete first-view sequence without horizontal overflow or console errors. The page-level release navigation buttons, insight bar, answer-contract workflow, policy editor, and quick-search surface remain open for later RAG-page passes.

## Milestone 3 iteration: cited-answer contract hierarchy

After evidence: `.playwright-mcp/admin-audit-2026-07-11/43-rag-answer-contract-rows-after.png`

The cited-answer contract no longer uses a four-column workflow card grid, a second four-card operations queue, and three summary cards as simultaneous primary surfaces. The seven release stages now form one scanable route list with human Korean status labels. Contract summaries and evidence retain their full data but use divided rows; the detailed operations queue is a collapsed disclosure because it duplicates the visible stage status. The redundant internal release backlink was removed while the page-level workflow navigation remains available. Focused and affected tests preserve every route, release-step number, evidence field, handoff, and promotion action contract. The current 1280px browser render has no fresh console errors; policy editor, runtime probe, quick search, and document handoff are still separate follow-up surfaces.

## Milestone 3 iteration: feedback promotion scan path

After evidence: `.playwright-mcp/admin-audit-2026-07-11/44-feedback-promotion-rows-after.png`

The feedback promotion surface now presents its seven release stages as one vertical operational sequence with localized status dots. The duplicate five-item boundary chain and four-item handoff queue remain available as disclosures instead of competing card inventories, and both internal release-backlink buttons were removed because the page header already owns adjacent-stage navigation. Opening the boundary disclosure was exercised in the in-app browser and preserved the route. Focused/affected tests confirm all stage paths, handoff evidence, LangSmith coverage, readiness commands, and report links remain available. At 1280px the visible workflow has no pill-shaped status containers, no horizontal overflow, and no fresh console errors. The page header action density, scalar stats/readiness section, release evidence body, filters, and table detail state remain open for later Feedback passes.

## Milestone 3 iteration: eval regression and LangSmith entry

After evidence: `.playwright-mcp/admin-audit-2026-07-11/45-evals-regression-rows-after.png`

The Evals entry no longer opens with four raised scalar cards followed by a bordered LangSmith dashboard. Totals, completion, pass rate, and score now share a compact 64px definition row. Regression suite, dataset sync, and readiness are a three-row scan path with localized semantic status dots. Product-boundary coverage and the five-stage live-smoke chain are collapsed disclosures, while persisted-eval dataset sync remains the primary operation below them. The internal release backlink was removed because the page header owns stage navigation. Browser QA at 1280px verified the first viewport and disclosure interaction with no fresh console errors. Deep sync evidence, handoff/remediation panels, trial table, empty/loading states, and narrow viewport still require later Evals passes.

## Milestone 3 iteration: LangSmith evidence disclosure

After evidence: `.playwright-mcp/admin-audit-2026-07-11/46-evals-sync-evidence-disclosures-after.png`

The persisted-eval sync task is now the only expanded LangSmith operation surface. Dataset/example evidence, unblock handoff, feedback-promotion coverage, and the raw readiness regeneration command remain available as flat disclosures instead of four simultaneous technical panels. Evidence definitions and handoff facts use two readable columns with row dividers when expanded; the command no longer dominates the default operator view. Browser QA at 1280px exercised the readiness-command disclosure, confirmed no horizontal overflow, and found no console warnings or errors beyond development-runtime informational messages. The trial table, populated result inspector, empty/loading states, and narrow viewport remain open for later Evals passes.

## Milestone 3 iteration: eval run history

After evidence: `.playwright-mcp/admin-audit-2026-07-11/47-evals-run-history-after.png`

The live Evals route now closes with a named run-history section instead of an unlabeled generic table. Raw full-length run IDs are reduced to stable eight-character operator labels while the source identifier remains available through the tooltip contract. Separate total/pass columns are combined into one semantic result row with a restrained status dot; cost and start time are declared secondary fields and move into the shared row-detail expander at 900px and below. Loading uses a four-row table skeleton, an API failure now exposes a retry action, and the zero-run state explains what will appear after the first regression execution. Desktop Browser QA at 1280px confirmed the populated table, zero horizontal overflow, the existing disclosure interaction, and no warning/error logs. The installed in-app browser did not expose a viewport override, so the 560px row-expander path was verified in the focused rendered-component test rather than claimed as browser evidence; true narrow browser capture remains open before the Evals route can be considered fully closed.

## Milestone 11 iteration: evaluation evidence containment

The current evaluation page retained the intended three-step operating sequence but a CSS inheritance gap could allow disclosure bodies with grid layouts to escape their closed state. Product-boundary, live-smoke, synchronization evidence, blocking handoff, feedback-coverage, and command disclosures now explicitly hide every non-summary child until opened. This keeps SDK fields, environment keys, report paths, command strings, raw action IDs, case/example IDs, and provenance out of the normal evaluation path.

The three release steps now render as one divided sequence rather than equal-width workflow cards. Expanded product-boundary items and pending actions also lose framed-card treatment; normal action states remain quiet text and semantic color. Korean copy now says `점검 자료 묶음`, `출시 판단 상태`, `필요한 설정`, `반영 근거`, and `문제 해결` instead of gate/SDK/env/case/provenance jargon. The page header no longer repeats generic release navigation owned by the LNB. Focused Evals and design-contract tests validate the closed technical boundary, existing sync behavior, narrow table contract, and removed header backlink. Live Browser QA at 1280px confirmed the one-column sequence, zero browser-default blue links, zero horizontal overflow, and no open technical disclosure in the default state. At 390px, the navigation condenses to icon controls, the summary and workflow rows remain readable, the visible table fields collapse to four essential columns, and neither the document nor the main workspace overflows horizontally.

## Milestone 12 iteration: unavailable capability truth state

The live `/sessions` route was not a data-load failure: its server capability manifest does not include the required session endpoint, so the route correctly stopped before requesting data. The old fallback nevertheless rendered a large dashed empty-state panel with a generic message, a default document icon, and raw endpoint paths in a development disclosure. The shared route boundary now presents a compact open notice that explains the server-side limitation in plain Korean and provides one status-page path forward. Endpoint paths and detection detail survive only in a closed developer disclosure; normal users never see the manifest terminology. This removes the nested panel, default empty illustration, and false retry implication for every capability-unavailable route, while keeping permission-denied states distinct.

The same 390px live pass revealed a responsive shell defect: a persisted desktop LNB preference could expose the mobile off-canvas rail immediately after a viewport change, leaving too little visible workspace. Mobile open/closed state is now ephemeral and separate from the desktop preference. The route opens with the rail translated fully off-screen; the header menu deliberately opens the 260px overlay with a backdrop, and that backdrop closes it again. The narrow viewport retains a 390px main workspace, 358px notice width, and zero document overflow.

## Milestone 13 iteration: document candidate review ownership

The live Documents ingestion page showed a release-step toolbar, policy seed action, refresh action, five tabs, candidate summary, framed review collection, filters, and table at once. The workflow toolbar and unrelated policy seed action now leave the review tab; release progression is owned by the LNB, while policy seeding appears only during policy editing. Candidate refresh moved beside the visible candidate count so it is contextual rather than global.

The candidate queue itself is now an open divided table section rather than another rounded panel around a table. At 1280px the review flow reads state totals → candidate list → filters → table. At 390px all three state totals stay readable in equal columns, filters stack, capture time hides, no navigation rail is open by default, and neither the document nor the workspace overflows. Opening a pending row preserves the review drawer, its approve/exclude actions, and its answer text while candidate/run identifiers remain hidden in a closed `개발자용 후보 정보` disclosure.

## Milestone 4 iteration: dashboard priority queue

Before evidence: `.playwright-mcp/admin-audit-2026-07-11/08.png`

After evidence: `.playwright-mcp/admin-audit-2026-07-11/48-dashboard-priority-queue-after.png`

The Today dashboard no longer renders three equally weighted cards when only one category has active work. Clear approval and response-filter categories are omitted from the active queue, leaving one full-width issue row with count, the three highest-priority findings, and direct navigation to the issue workspace. Missing Korean translations for the known Atlassian/Swagger MCP and runtime tool-policy findings were added, so the queue no longer exposes implementation keys such as `mcpServers.knownServerAtlassian` or `toolPolicyPage.signals.runtimeEnforcement`. Browser QA at 1280px confirmed one active row, no horizontal overflow, no warning/error logs, and successful queue navigation to `/issues`. The health strip, release summary, three status cards, cost panel, and infrastructure/activity sections remain open; this iteration closes only the primary work-queue hierarchy.

## Milestone 4 iteration: dashboard status hierarchy

After evidence: `.playwright-mcp/admin-audit-2026-07-11/49-dashboard-status-rows-after.png`

The dashboard health surface now states the actual platform readiness condition and remediation once, with its evidence timestamp, instead of repeating critical, warning, MCP, and grounding values as colored chips. Previously missing `dashboard.readiness.*` Korean resources were added, eliminating another raw-key path. The three raised status cards and their fabricated deterministic sparklines were removed; safety, infrastructure, and quality now use a flat three-row definition table with nine comparable facts. The loading contract uses one table skeleton rather than three card placeholders. Browser QA at 1280px confirmed no raw readiness keys, no horizontal overflow, no warning/error logs, and successful opening of the operational-status modal. The installed browser still lacks a viewport override, so a true narrow browser capture remains open alongside the cost and infrastructure/activity passes.

## Milestone 4 iteration: dashboard cost and infrastructure

After evidence: `.playwright-mcp/admin-audit-2026-07-11/50-dashboard-cost-infra-after.png`

The monthly cost widget is now a single open navigation row with amount and month-over-month delta rather than a `CostCard` nested inside another rounded panel. A cost increase above the threshold remains an inline warning sentence instead of a badge. MCP connections and recent activity share an open two-column section without card shells or a decorative vertical divider; known server names use product casing and raw `PASS`/`DISCONNECTED` enums are localized. The previously blank activity half now states explicitly when there are no recent operating events. Browser QA at 1280px confirmed zero horizontal overflow, no warning/error logs, and successful cost-row navigation to `/usage`. Narrow browser capture remains open because the installed browser still does not expose viewport emulation.

## Milestone 4 iteration: dashboard release handoff

After evidence: `.playwright-mcp/admin-audit-2026-07-11/51-dashboard-release-summary-after.png`

The release summary no longer uses a raised rounded card, decorative rocket, status badge, and primary button simultaneously. It now presents one flat handoff header with a semantic status dot and quiet cockpit link, followed by a four-column evidence row. The source counts, recommended tag, missing-state behavior, and `/release#release-cockpit` route remain intact. Browser QA at 1280px confirmed a transparent zero-radius container, zero horizontal overflow, no warning/error logs, and successful cockpit navigation. Together with the priority queue, readiness sentence, status table, cost row, and infrastructure section, the standard populated Dashboard body now follows one consistent open-section grammar; developer-only modals, loading/error states, and true narrow browser evidence remain open.

## Milestone 4 iteration: platform health recovery

Before evidence: `.playwright-mcp/admin-audit-2026-07-11/09.png`

After evidence: `.playwright-mcp/admin-audit-2026-07-11/52-health-route-recovered-after.png`

The platform-health route previously replaced the entire workspace with the error boundary when the backend omitted `services`; the response contract now treats optional health facets explicitly and the view normalizes an absent service list to a fail-closed empty state. Three generic statistic cards and the unrelated release-workflow backlink were removed. Operators now see a flat status summary, one comparable metric row, localized service rows when available, and a collapsed raw-JSON disclosure for diagnosis. Browser QA at 1280px exercised that disclosure, confirmed the recovered route and title, found no horizontal overflow or fresh warning/error logs in a clean tab, and verified that the empty service state explains its remediation. True narrow browser evidence remains open because the installed in-app browser does not expose viewport emulation.

## Milestone 4 iteration: issue queue before topology

Before evidence: `.playwright-mcp/admin-audit-2026-07-11/53-issues-before.png`

After evidence: `.playwright-mcp/admin-audit-2026-07-11/54-issues-list-first-after.png`, `.playwright-mcp/admin-audit-2026-07-11/55-issues-detail-after.png`, `.playwright-mcp/admin-audit-2026-07-11/56-issues-topology-secondary-after.png`

The Issues route now opens with the prioritized operator queue instead of a 480px animated topology canvas. Severity totals are a flat four-value filter row, critical and warning findings are readable divided rows, and expanding a finding reveals its summary, evidence, and quiet text actions without a nested card or decorative left rail. The topology remains available as an explicit secondary disclosure; its heavy module and data query are both deferred until the operator opens it. Missing topology, MCP-security, output-guard, navigation, and next-step translations were added with regression coverage, eliminating all raw `*Page.*` and `nav.*` keys from the live default, detail, and topology states. The global PageHeader stack breakpoint moved from 1280px to 960px, keeping ordinary laptop headers on one row and removing the empty action band across internal pages. Browser QA at 1280px verified the default queue, inline detail, topology disclosure, zero horizontal overflow, a clean fresh console, and no framework overlay. True narrow browser capture remains open because the installed in-app browser does not expose viewport emulation; the new queue, detail, disclosure, and header rules include CSS collapse paths for later narrow verification.

## Milestone 4 iteration: compact approvals queue

Before evidence: `.playwright-mcp/admin-audit-2026-07-11/57-approvals-before.png`

After evidence: `.playwright-mcp/admin-audit-2026-07-11/58-approvals-empty-after.png`

The empty Approvals route no longer repeats a healthy zero state across a bordered readiness panel, four StatCards, a PASS badge, a readiness strip, a nested attention empty panel, quick filters, and a second queue empty panel. Healthy readiness is now one semantic sentence with three inline facts; detailed typed checks appear only behind a disclosure when the aggregate becomes WARN or FAIL. The empty queue is a single left-aligned state and suppresses the irrelevant status selector, quick filters, attention section, policy CTA, and release-workflow backlink. Populated queues retain status filtering, severity-ordered attention rows, the approval table, detail workspace, and approve/reject dialogs; the attention cards became divided operator rows and the detail close control now uses the shared icon family. Browser QA at 1280px verified the empty queue, refresh interaction, zero raw keys, zero horizontal overflow, a clean fresh console, and no framework overlay. Populated attention/filter/detail paths are covered by component tests; live populated browser evidence and true narrow capture remain open for a later state-fixture QA pass.

## Milestone 5 iteration: single-action persona collection

Before evidence: `.playwright-mcp/admin-audit-2026-07-11/59-personas-before.png`

After evidence: `.playwright-mcp/admin-audit-2026-07-11/60-personas-empty-after.png`

The empty Personas route no longer repeats `0` across two large StatCards or offers the same creation action in both the PageHeader and EmptyState. Empty collections expose one left-aligned creation path with distinct instructional copy; the sample persona moved from a permanently visible dashed panel into a compact disclosure with the shared chevron icon. Total and active counts remain available as a flat definition summary only after personas exist, while the populated DataTable, bulk actions, inline rename, detail tabs, playground, and edit/delete paths are preserved. The detail close glyph now uses the shared icon family. Browser QA at 1280px verified exactly one creation button, the example disclosure, create-modal open/cancel, zero raw keys, zero horizontal overflow, a clean fresh console, and no framework overlay. Populated list/detail visual evidence and true narrow capture remain open for the later state-fixture QA pass.

## Milestone 5 iteration: prompt template collection

Before evidence: `.playwright-mcp/admin-audit-2026-07-11/61-prompt-studio-before.png`

After evidence: `.playwright-mcp/admin-audit-2026-07-11/62-prompt-studio-empty-after.png`

The empty Prompt Studio route no longer constructs a two-column master/detail workspace before any master record exists. Its duplicate detail placeholder, permanently expanded tutorial panel, and unrelated release-stage backlink were removed. Operators now get one left-aligned collection state, one creation action, and an optional example disclosure; the split list/detail layout appears only after templates exist and the detail pane only after an explicit selection. Browser QA at 1280px verified one creation button, the collapsed/open example, create-modal open/cancel and return to the same empty state, zero raw keys, zero horizontal overflow, and no warning/error console entries. Populated list/detail visual evidence and true narrow capture remain open for the later state-fixture QA pass.

## System milestone: graphite palette, feedback surfaces, and responsive roles

Before evidence: user screenshots of the amber focus rail and blue Provider smoke handoff; `.playwright-mcp/admin-audit-2026-07-11/63-reactor-universe-before.png`

After evidence: `.playwright-mcp/admin-audit-2026-07-11/66-reactor-universe-palette-after.png`, `.playwright-mcp/admin-audit-2026-07-11/67-provider-handoff-palette-after.png`

The primitive palette now uses neutral graphite base/elevated surfaces (`#111318`, `#171A20`, `#1D2129`, `#242933`), neutral high-contrast labels, restrained amber brand actions, and muted semantic status colors. Feedback and note containers consume semantic surface tokens instead of large blue/yellow fills. Decorative 2–4px vertical status rails were removed from shared tables, issues, focus hints, pipeline/waterfall views, info/stat cards, input guard, traces, MCP, release operations, chat stream events, and eval recommendations; a structural test prevents their return. Desktop Browser QA confirmed the new computed palette, zero decorative rails and horizontal overflow on Reactor Universe, and a neutral Provider handoff surface with a 1px boundary and no console warnings/errors. The in-app browser accepted the viewport API call but continued reporting a 1280px document viewport, so tablet/mobile browser evidence is explicitly still open; responsive gutter, touch-target, panel, and data-row roles are tokenized for the later device pass.

## Milestone 5 iteration: Reactor Universe directory

Before evidence: `.playwright-mcp/admin-audit-2026-07-11/63-reactor-universe-before.png`

After evidence: `.playwright-mcp/admin-audit-2026-07-11/66-reactor-universe-palette-after.png`

The empty Reactor Universe route no longer renders a centered empty state followed by a boxed three-card tutorial and separate example card. It now offers one left-aligned creation action and a compact optional disclosure. Populated agents use a divided directory row with localized status and execution-mode labels rather than a card grid, keyword pills, and raw mode enums; loading follows the table shape. Browser QA exercised the guide disclosure and create-modal open/cancel return path with zero raw keys, overflow, framework overlays, or console errors. Populated live data evidence and tablet/mobile captures remain open.

## Milestone 6 iteration: safety policy navigation and ordered pipeline

The Safety Rules entry no longer stacks two equivalent full-width tab bars or repeats release-workflow navigation inside the embedded editor. At desktop width, the three policy families form a compact vertical local navigation with a quiet structural divider; below 800px they return to a horizontally scrollable scope selector. Input Guard stages are now ordered divided rows with ordinals, descriptions, and one state switch instead of raised cards and connector ornament. Selecting a stage preserves the side-inspector flow, while class names, runtime overrides, raw configuration keys, and type strings move behind technical disclosures; the current `sensitivityLevel` field is localized as “탐지 민감도” with operator-facing Korean guidance. Browser QA at 1512px exercised the output-policy round trip and selected-stage inspector, confirmed vertical policy navigation, localized default content, and zero page overflow. Tablet QA at 800px confirmed the horizontal policy scope and three-column stage row without page overflow. Mobile QA at 390px confirmed a single-column editor, horizontally scrollable local tabs, stacked stage controls, zero page overflow, and 44×40px switch hit areas.

## Milestone 7 iteration: fail-close release decision entry

The live `/release#release-cockpit` payload reported an aggregate `passed` state while `warningReviewRequired` remained true. The decision header now derives an effective fail-close state and displays `warning 검토 필요` instead of a misleading green pass. The backend-authored English next action is translated into one concrete Korean operator instruction, and the version-specific v1.1 subtitle is now release-neutral. The long readiness shell pipeline, tag recommendation inventory, warning review commands, and local verification commands are collapsed disclosures; the top-level view description is plain supporting text instead of another bordered note panel. Warning review fields now say `검토 필요` or `검토 완료` rather than incorrectly rendering “검토 완료: 예” when review is still pending. Report links use the shared human-label boundary while retaining raw IDs for accessible traceability. Desktop in-app Browser QA at 1280px verified the conditional status, localized action, collapsed disclosures, and warning-disclosure interaction with no relevant console warnings/errors. Playwright fallback at 390px was used because the in-app browser viewport control is unreliable; it verified a single-column summary/decision layout, zero page overflow, hidden closed-detail content, and an expanded warning command view that wraps without page-level clipping.

## Milestone 7 iteration: product boundary and evidence ownership

The release product-boundary view now has one owner for workflow navigation: the LNB. The repeated shortcut inventory was removed, while the boundary itself presents one localized capability summary and six ordered release gates. Raw capability IDs, report IDs, flow keys, and per-gate evidence remain available only through technical disclosures. A selector regression that accidentally hid the always-visible boundary container was found during live QA; collapsed-content rules now explicitly target `details`, with a static regression test guarding that distinction.

The Evidence tab is now a flat status index instead of eight simultaneous technical panels. Warning, readiness, LangSmith, RAG, feedback, live smoke, and provider evidence are collapsed by default; raw UUIDs, JSON, SDK contracts, API paths, and shell commands appear only after an operator opens the relevant row. The readiness row shows required/missing report counts in its summary and keeps the copy action beside the expanded command, preventing an ambiguous icon-only control from dominating the closed row. Desktop and narrow browser evidence, disclosure interaction, overflow, console, focused/affected tests, lint, and build are recorded in the milestone verification.

## Milestone 7 iteration: integration smoke action and evidence inspector

The `/integrations#release-smoke` execution area no longer presents Slack and A2A as two independent cards. Both side-effecting operations are flat rows with the target, current state, effect, and explicit action aligned in one scan path; their typed confirmation and readiness-refresh behavior remain unchanged. Slack, A2A, and Provider evidence now form three collapsed status disclosures instead of several hundred lines of always-visible protocol fields. Duplicate release backlinks inside each evidence header were removed because the page header and LNB already own workflow navigation.

Opening an evidence row reveals a two-column divided definition inspector on desktop and a single-column inspector at 390px. Remediation is a continuation of that inspector rather than a nested alert card. The long readiness command is closed by default and exposes its route, command, and copy action only after expansion. Four control-plane StatCards were replaced by one compact definition row. Playwright fallback was used because the in-app Browser execution bridge was not exposed in this continuation; desktop 1440px and mobile 390px checks verified disclosure interaction, zero page overflow, zero framework overlays, and clean warning/error logs. Focused component tests retain live smoke confirmation, aggregation, report, remediation, and evidence contracts.

## Milestone 7 iteration: provider smoke and model detail ownership

The `/models#provider-smoke` entry now exposes one configured-target operation row instead of a handoff callout, bordered operation panel, three workflow cards, two technical grids, remediation card, and a permanently visible shell command. Current provider/model, live-smoke state, side-effect notice, and run/refresh actions remain visible. Gate identity, reports, environment, provider usage, checks, remediation, and readiness command live in one collapsed Provider evidence inspector with two divided columns on desktop and one on mobile.

Backend states and contract identifiers such as `missing`, `live_smoke`, `backend_provider_integration`, and `required_env` are translated at the view-model boundary before display. Provider identity in the registry is ordinary data text rather than a decorative badge. The model drawer keeps provider context but removes both duplicate release links, leaving the page header and LNB as the only release workflow owners. Playwright fallback at 1440px and 390px verified the collapsed and expanded smoke states, model-row-to-drawer interaction, zero duplicate workflow links in the drawer, no horizontal overflow or framework overlay, and no warning/error logs. Focused and affected model-registry tests cover evidence preservation, live execution, remediation, responsive contracts, pricing, capabilities, and drawer behavior.

## Milestone 8 iteration: Today action hierarchy

The root route now has a visible “오늘” page title and a concise purpose statement instead of opening with two unexplained utility buttons. Response-quality and operational-signal analysis remain available as contextual header utilities. The previous screen-reader-only duplicate heading was removed, leaving exactly one `h1` in the rendered document.

When actionable signals exist, “지금 처리할 작업” now appears before release and health summaries, so the first operational decision is not displaced by a healthy release aggregate. The existing queue, release facts, status comparison, cost, infrastructure, and activity contracts remain intact. Playwright fallback at 1440px and 390px verified the heading, action-first DOM order, modal entry, header-control sizing, zero row/page overflow, no framework overlay, and clean warning/error logs. Focused structure and component tests guard the heading and priority order alongside the queue, health bar, and status summary.

## Milestone 8 iteration: trace contract and linear inspector

The live trace endpoint returns `status`, `durationMs`, and `createdAt`, while the old view assumed `success`, `totalDurationMs`, and `time`; completed runs consequently rendered as errors with `NaNm NaNs`. The API adapter now normalizes current and legacy shapes, drops rows without trace IDs, and fail-closes malformed numeric fields. Korean filter/status labels were completed, opaque `run_*` values became compact operator IDs, four StatCards became one divided summary row, and release-workflow actions were removed from the analysis header.

The live trace-detail endpoint currently returns ordered run events rather than span objects. Those events now normalize into safe “실행 시작/완료/실패” trace steps while legacy spans remain supported. Opening a row no longer crashes the route. The drawer removed its cramped two-column mini-map and nested section cards; summary, span tree, timeline, and selected detail now use one full-width divided flow with compact trace ID and full accessible source ID. Playwright fallback at 1440px and 390px verified list and drawer states, exact success labels, no `NaN` or translation keys, no error boundary, zero page/row overflow, and clean warning/error logs. The full trace test lane covers both API contracts, malformed values, statistics, table, tree, timeline, and drawer structure.

## Milestone 9 iteration: scheduled operations hierarchy

The Scheduler route now treats unattended execution as an operator decision rather than a readiness dashboard. One localized trust state and a compact fact row lead into a collapsed evidence disclosure, followed by the only immediately actionable intervention queue and a flat job table. Raw schedule expressions and backend enums were removed from the primary list; readable schedules, semantic dots, and localized outcomes replace them while technical syntax remains available in labeled detail.

The create/edit drawer moved to the tokenized wide role and reduced its default content from nearly 2,000px to the identity, schedule, instruction, blocker review, and sticky actions needed to save safely. Runtime overrides, failure handling, notification settings, and non-blocking recommendations are closed disclosures. Desktop and 390px in-app browser QA verified the populated table, form, schedule help, row expansion, zero page overflow, no raw state/implementation terms, and no default-blue links. Focused tests, changed-source lint, and production build cover the route contract.

## Milestone 9 iteration: URL-addressable failed-request recovery

The Debug Replay route now has source-controlled populated browser evidence rather than only a 503 recovery state. Three representative failures prove localized model-timeout, tool-failure, and safety-policy paths. Selecting a record writes the `capture` query parameter, preserving recovery context across refresh and handoff, while the Chat Inspector link still prefills without executing.

The selected review is an open divided surface rather than another bordered card. Operator copy uses “실패 요청 재현” and “당시 입력”; circuit-breaker jargon, guard codes, capture IDs, anonymous hashes, model/tool identifiers, and original error messages remain localized or closed in developer information. Desktop and 390px in-app browser QA verified selection, URL state, safe prefill, zero overflow, no raw identifiers/codes, and no default-blue links. Focused feature and handler tests now assert real translations instead of resource-key fallbacks.

## Milestone 9 iteration: guarded diagnostic data delivery

The Metrics Ingestion route now validates JSON syntax and object/array shape on every edit instead of waiting for a side-effecting submit. An accessible inline state reports the number of ready records, malformed input marks the editor invalid, and no API request is possible until the payload is valid.

Because this expert tool bypasses automatic collection and writes directly to operational data, the operator must separately confirm that the payload contains sample-only information. Scenario changes, payload edits, sample restoration, and successful sends clear that confirmation. The nested payload panel became an open divided section; endpoint, permission, and raw-response contracts remain closed. Desktop and 390px in-app browser QA covered invalid input, restoration, confirmation, successful delivery, scalar results, zero overflow, and no raw UI tokens or default-blue links. Focused tests now use real translations and all five browser POST shapes have source-controlled handlers.

## Milestone 8 iteration: latency contract and analysis hierarchy

The live latency endpoints return `bucket`, `averageMs`, `p50Ms`, `p95Ms`, `p99Ms`, and `count`, while the former adapter expected `time`, `avgMs`, and unsuffixed percentile keys. The mismatch rendered valid zero-millisecond samples as `NaNs` and an invalid `NaN:NaN` chart axis. The adapter now reconciles current and legacy shapes, rejects invalid timestamps, fail-closes non-finite numbers, preserves sample count, and marks whether a real P95 series exists instead of inventing one.

The page now has one URL-addressable scope selector for latency, conversation quality, and tools; the nested latency/conversation tab bar and duplicate release backlink were removed. Three raised StatCards became a four-fact divided summary, zero samples use one intentional empty state, and an API outage uses a distinct retryable error state. Live Playwright fallback at 1440px and 390px verified two real zero-millisecond samples, average-only chart disclosure, one tablist, no `NaN`, no release link, no StatCards, two-column narrow summary, zero horizontal overflow, and clean warning/error logs. Focused API, component, and route tests cover current/legacy contracts, malformed data, populated/empty/error states, and URL selection.

## Milestone 8 iteration: session overview contract and workspace shell

Backend source and live traffic were inspected together. Reactor’s `/api/admin/sessions/overview` intentionally aggregates the latest tenant runs into `period`, `days`, `totalSessions`, `statusCounts`, and `uniqueUsers`; the admin view was the defective side because it assumed an obsolete six-card contract with `changes`, trend, channel, persona, trust, feedback, and recent-session arrays. The admin adapter now normalizes the actual compact contract, fail-closes malformed numbers and collections, and keeps the richer legacy fields only when a backend genuinely supplies them.

The generic route crash, six StatCards, speculative empty chart/card/list grids, duplicate hidden page title, and oversized loading dashboard were removed. `/sessions`, `/sessions/feed`, and `/sessions/users` now share one visible PageHeader and URL-addressable workspace navigation; child feed/user components no longer own duplicate breadcrumbs. The overview shows four backend-backed facts, localized period controls, direct session/user review actions, retryable transport failure, and only renders richer sections when data exists. Dead `OverviewStatCards`, retired dashboard/error selectors, and unused oversized skeleton variants were deleted. Live Playwright fallback at 1440px and 390px verified the real `2 sessions / 1 user / 2 completed` response, one `h1`, no error boundary, no StatCards or empty grids, 2×2 narrow summary, one-column actions, correct active navigation, and zero overflow.

## Milestone 10 iteration: cross-route human-label boundary

A current live census rechecked the dashboard, issues, approvals, safety policy, release cockpit, and runtime settings together. Model-facing tool IDs such as `jira_create_issue`, `web_search`, and `confluence_write` now pass through one shared operator-label presenter; lists, issue titles, dialogs, and queue actions show Korean task names while the canonical ID remains available only as secondary title evidence. Dashboard activity metrics use the same translated metric labels as the operational inspector instead of exposing `api.requests.total`, `mcp.tool_calls.total`, or token counter keys.

Input Guard now maps the backend's kebab-case stage identifiers to the established Korean stage and description resources, with a legacy translation fallback for older fixtures. Runtime settings replace the known English `Enable response caching` description with `답변 재사용 사용 여부` and keep the raw setting key out of the table. `ReleaseReportLink` owns a tokenized link style globally, removing the five browser-default blue links from the live release cockpit.

Desktop Browser QA across the affected routes found no raw tool IDs, raw stage translation keys, raw metric identifiers, browser-default links, `NaN`, or page overflow. The runtime settings route was additionally checked at 390px with no document overflow or clipped main content. Focused and affected tests cover the shared tool presenter, approval queue, issue synthesis, dashboard activity, Input Guard stages, release report links, and settings labels.

## Milestone 10 iteration: integration recovery and project connections

The live integration route still contained four StatCards followed by nested InfoCards and a three-column runbook inside the endpoint recovery console. The recovery surface now uses one divided fact row, one prioritized recovery row per failing endpoint, collapsed technical evidence, and a closed linear runbook. The primary text removes manifest, probe, upstream, backend, and proxy jargon; raw paths and server response details remain available only in technical information.

The same 390px capture exposed a separate project-connection card whose title collapsed into one-character vertical text. Project connections now use a flat status list with human names (`Reactor 서버`, `Atlassian 연결`, `Swagger 연결`), localized state text, one contextual registry action, and collapsed server details. Duplicate release-stage links, InfoCards, and status badges were removed. Desktop and 390px Browser QA found zero StatCards/InfoCards/badges in both sections, zero repeated release links, zero narrow long-text nodes, and no page overflow. Focused and affected integration tests cover the new recovery and project-connection contracts.

## Milestone 10 iteration: feedback review ledger and evidence boundary

The feedback route now keeps routine triage separate from release diagnostics. Known domain and intent identifiers are translated into Korean operator language while canonical values remain available only as non-visible traceability metadata. Rating, review state, and evaluation lifecycle use quiet semantic dots and text instead of three competing badges. The duplicate release-stage header navigation was removed because the LNB owns that workflow.

The collapsed statistics disclosure now holds both the ordinary feedback totals and Slack follow-up rate as flat definition rows. The prior six metric tiles and three framed empty category panels are gone; an expanded review is one summary, three unframed category lists, then the click-rate evidence. At narrow width, the table deliberately reduces to the question column and places rating, review state, and evaluation state on one supporting line. This prevents the prior failure where the question collapsed into one-character vertical text beside several fixed status columns. Release evidence remains complete but is collapsed by default, so case IDs, SDK contracts, report paths, environment requirements, and commands do not fill the ordinary inbox. The selected-feedback drawer now opens on a Korean task title and readable response text; IDs, raw action names, case IDs, command lines, file paths, and JSON metadata live only in the closed `세부 근거 보기` disclosures. It also drops duplicate release-stage links and uses the shared Lucide close icon plus quiet status dots. Feedback detail and evidence links use a tokenized neutral link treatment instead of browser-default blue. Desktop Browser QA at 1280px confirmed the closed inbox, expanded flat statistics, raw-key absence, zero default-blue links, zero table pills, and zero overflow. Browser QA at 390px confirmed one question column, visible supporting status text, 244px readable question cells, and no document overflow; the in-app browser's raster capture did not reattach after the temporary viewport override, so the narrow evidence is recorded as DOM measurement rather than a screenshot. Focused tests cover human labels, narrow column ownership, flat statistics, evidence disclosure behavior, technical-detail containment, bulk review, evaluation closure rules, and detail actions.

## Milestone 11 iteration: document-search operator workspace

The `/rag-cache?tab=rag` default is now a focused operator workspace instead of a release-flow diagram. It starts with two decision facts—searchable documents and answers awaiting review—and provides three contextual actions: manage documents, test an answer, or open the review list. Collection policy is an independent URL-addressable tab, so a policy form does not compete with the ordinary search and answer-test task.

The deleted lifecycle rail, release-handoff shortcuts, repeated workflow cards, and their corresponding component, test, CSS selectors, and Korean translation keys were removed. The release LNB still links to RAG, but now targets the retained `#rag-answer-contract` entry point rather than the deleted lifecycle anchor. Normal answer results render `참고 1` and `참고 문서 1`; raw citation IDs, source labels, run IDs, contract states, and expected-document identifiers remain inside the closed `개발자용 결과 정보` disclosure. The same containment applies to direct document-search evidence.

Desktop mock-browser QA at 1280px exercised answer testing with a grounded response and verified the updated release LNB target, readable citations, closed technical evidence, no browser-default blue links, and no horizontal overflow. The current in-app-browser viewport override does not change `window.innerWidth`, so narrow-browser evidence remains a responsive CSS and focused-test contract for this iteration rather than a claimed mobile pass. The local Reactor backend reported healthy and ready, but unauthenticated admin data endpoints returned `403`; this iteration therefore does not claim a real-backend admin workflow pass. Focused RAG, release-navigation, and token-contract tests cover the default workspace, isolated policy tab, citation containment, and removed lifecycle surface.

## Milestone 11 iteration: answer-review evidence boundary

The selected answer review is now a decision drawer rather than a release-evidence console. Its open surface contains only the review state, channel and captured time, a concise decision cue, the user question, and the proposed answer. When release follow-ups exist, they are presented as a short, divided list of plain-language checks with semantic dots. The drawer no longer repeats release navigation, renders raw action names as primary copy, or turns each action into a bordered card, step badge, or link collection.

Candidate and run identifiers, source-document IDs, action IDs, dataset and case references, report paths, diagnostics paths, environment requirements, commands, and runbooks are retained only inside the closed `개발자용 확인 정보` disclosure. The component-level regression tests prove that the primary decision surface contains no release link and that technical values appear only after the operator opens that disclosure.

Mock-browser QA at `1280×720` opened a pending candidate from `/rag-cache?tab=candidates`, verified the question-and-answer decision path, then opened the technical disclosure and confirmed candidate/run identifiers appear there. Narrow QA at `390×844` verified the drawer becomes a full-width document-order surface with wrapped text, stacked check rows, and no horizontal clipping. The only console messages were pre-existing MSW service-worker version and mock-listener warnings; no application runtime error or framework overlay appeared. This is mock-data evidence only; unauthenticated live admin data endpoints remain outside the claim.

## Milestone 12 iteration: approval queue decision boundary

The populated `/approvals` queue previously exposed backend state (`PENDING`), a raw run ID, a minute counter that had grown into seven digits, and approve/reject controls inside every table row. That made a fast scan feel like a developer ledger and invited an irreversible decision without first opening the request.

The queue now shows a Korean decision state with a semantic dot and a readable elapsed age. Its table is deliberately limited to tool, state, and request time; choosing a row opens the decision detail, where approval and rejection live. Run ID, timeout, and idempotency key remain available only in the closed `개발자용 확인 정보` disclosure. The readiness diagnostics use one divided list instead of a nested strip, while stale-request explanation stays next to the selected request.

Mock-browser QA at desktop width verified the reduced table and selected detail boundary. At `390×844`, selecting a row automatically moves the stacked detail into view, preserves visible approval/rejection controls, and keeps technical evidence closed until requested. Focused approval, operations, API, token-contract, TypeScript, and i18n checks cover the queue, selected detail, disclosure, and narrow-screen movement. This is mock-data evidence only; it does not claim a live backend approval decision pass.

## Milestone 13 iteration: integration overview ownership

The default `/integrations` screen mixed connection status, release-stage navigation, report IDs, environment-variable names, setup commands, workflow links, endpoint recovery, and live-test controls in one first viewport. It made the ordinary question—what is connected and what needs attention—harder to answer than the technical evidence itself.

The release-stage header navigation has been removed because the LNB already owns it. `연결 현황` now stops after the compact connection summary, the one actionable recovery row, and project connection status. Reports, environment setup, commands, gate evidence, and workflow links render only in the URL-addressable `상세 진단` view; side-effecting smoke operations stay in `실제 시험`. The smoke-operation state now uses a quiet semantic dot and text instead of a status pill.

Mock-browser QA verified desktop overview, `상세 진단` navigation, desktop live-test presentation, and the 390px overview/live-test layouts. The default overview keeps `smoke_run` and `LANGSMITH_API_KEY` out of the visible UI, while `상세 진단` deliberately reveals them. Console output contained only the pre-existing MSW worker-version and mock-listener warnings; this is mock-data evidence, not a live external smoke execution claim.

## Milestone 14 iteration: organization roster selection

The organization roster previously appended a second all-organization usage table directly beneath the selection list. That made one page compete between finding an organization and comparing its usage, even though the selected organization's URL-addressable operations workspace already owns usage, service targets, report periods, and downloads.

The roster now ends after the verified organization list. Choosing a row writes `tenantId` into the URL and opens the selected organization's facts and next action; the existing `조직별 운영 현황` workspace remains the only path to usage analysis. The unused client analytics fetch, query key, type, table presenter, and fixture/API coverage were removed with that duplicate surface rather than kept as unreachable client code.

Mock-browser QA at 1280px confirmed a readable five-column roster, no all-organization usage heading, no browser-default blue links, no decorative left rail, and no page overflow. At 390px, the narrowed roster preserved a 390px document width with no overflow; selecting Example Corp produced `/tenants?tab=admin&tenantId=tenant-1`, opened `선택한 조직 정보`, and kept usage analysis out of the roster. Focused component, page URL-state, API, and query-key tests cover the removed duplicate path and preserved selection-to-operations handoff.

## Milestone 15 iteration: external connection registry hierarchy

The external-tool registry still placed refresh, global settings, registration, summary filters, search, fleet-wide recovery, and emergency blocking before its connection table. A routine registry scan therefore looked like a dashboard plus an incident console instead of a read-and-select list.

The first view now keeps refresh and server registration in the header, then presents the flat status filters, search controls, and selectable connection ledger. Global settings, reconnect-all, and emergency blocking were consolidated into one closed `연결 작업` disclosure below the table. The status filter is also an open divided control rather than a filled rounded control group with selected-card shadow treatment.

Mock-browser QA at 1280px confirmed the global-settings action is absent from the header, maintenance is closed by default, the summary has transparent background and zero radius, and there are no browser-default blue links or document overflow. Opening `연결 작업` exposed the three retained fleet actions and kept the 1280px page within width. At 390px, the status filter measured 358px without internal or document overflow, the list reduced to readable server/state columns, and fleet maintenance remained closed by default. Focused registry, connection-detail, and fleet-action tests preserve the available operations and their confirmation path.

## Milestone 16 iteration: native optional-settings disclosure

The shared optional-section primitive used a custom button, text-triangle glyphs, and a `max-height: 0` body. Although it looked collapsed in some layouts, its controls remained in the browser's accessibility tree, so the response-test workspace announced every advanced runtime, graph, output, and budget control even while claiming that these were optional.

The primitive now uses native `details/summary`, a shared Lucide chevron, an open divided boundary, and an explicit closed-body selector. Advanced controls are neither visible nor announced until the disclosure opens. This removes the raw `▶/▼` product glyphs for every current primitive consumer without introducing a new card surface.

Mock-browser QA at 1280px confirmed the response-test workspace starts with the six advanced controls closed and absent from the accessibility snapshot; opening `전문 설정` reveals all six controls without overflow. At 390px, the closed workspace keeps a 390px document and main width with zero visible advanced controls or raw triangle text. Focused response-test and shared-primitive tests cover default-closed, default-open, toggle, generated/provided body IDs, and toggle notification contracts.

Release report and copy-control labels follow the same principle: visible labels name the destination or report, while the action verb is supplied once by the control's accessible label. A flat `feedback_promotion` report resolves to the reviewed-feedback label instead of surfacing its internal identifier.

## Milestone 17 iteration: shared control-icon and dead-surface boundary

Text glyphs made otherwise standard controls look improvised and varied by font: sort/export indicators used `▲/▼`, table expansion and pagination used `▸/▾/◀/▶`, row actions used `⋮`, and feedback change direction used text arrows. The unused `DetailMiniMap` also kept a sticky, decorative left-rail primitive exported even though no product route consumed it.

All production controls now use the shared Lucide icon set with token-owned size, alignment, and rotation. Saved views, export menus, table expansion, pagination, row actions, and feedback direction preserve their interaction and status semantics without relying on text characters. The unconsumed minimap component, stylesheet, test, and public export are removed rather than retained as dead UI inventory. A source-wide scan finds no remaining `▲`, `▼`, `▶`, `◀`, `▸`, `▾`, or `⋮` control glyphs in production source.

Focused shared-table, saved-view, session-detail/export, and feedback tests cover the changed control contracts. Mock-browser QA at 1280px and 390px confirmed no raw control glyphs and no document overflow on the feedback workflow; the saved-view behavior is also covered directly by its component contract because the mock feedback route returned no saved-view data during this browser pass. This iteration keeps data availability separate from the visual-control claim.

## Milestone 18 iteration: access-control contract recovery

The access-control workspace was showing a generic unavailable state even though its role area had a valid visual layout. The cause was not the screen layout or the Reactor router: the current backend source defines `GET /api/admin/rbac/roles` as raw role records with `role`, nullable `scope`, and `resource:action` permission strings, while the admin mock route returned already-normalized display objects. The client adapter then attempted to split a permission object and leaked a browser `TypeError` into the technical recovery detail.

The mock now emits the backend-shaped role contract, including the four current system roles. The adapter validates unknown JSON before mapping it, rejects malformed role arrays and malformed permission strings—including extra delimiters—with a Korean recovery error, and no longer allows a transport-shape error to masquerade as a zero-role state. The obsolete exported permission fixture was removed with the erroneous mock shape.

Permission labels for evaluation, organization management, and Slack are localized before the operator view. The role workspace renders readable Korean groups rather than `Unknown permission target` or raw resource keys; unknown values still take the established safe fallback path.

Mock-browser QA at 1280px confirmed four role rows, no unavailable alert, no unknown-permission label, and no document overflow. Switching through the real tab control to `구성원 권한` updated the URL to `?tab=members` and displayed the member search workflow. At 390px, the tab list and member-email field each measured 358px inside a 390px document, with no horizontal overflow or one-character vertical text. Focused API, role-manager, and route tests cover the raw contract, malformed payload recovery, human labels, and URL-addressable tab behavior. This validates the admin adapter and mock contract against the checked backend source; it does not claim an authenticated live-backend role mutation pass.

## Milestone 19 iteration: numeric adjustment control contract

The current retention-policy review was visually stable at desktop and narrow widths, but it exposed a shared primitive that still made operational forms feel improvised: `NumberInputStepper` drew its adjustment controls with `−` and `+` text glyphs, literal 24px and 28px dimensions, and a literal radius. Every consumer therefore inherited typeface-dependent symbols and an off-scale hit target, including retention, RAG policy, scheduler, and runtime-setting forms.

The primitive now uses the shared Lucide minus/plus icons and only the established control-height, control-radius, and icon-size tokens. Keyboard adjustment, clamping, input semantics, and localized accessible labels are unchanged, so this is a visual-system correction rather than a behavior change. The design system now makes the shared contract explicit and prohibits raw numeric-adjustment geometry and text symbols.

Browser QA rechecked the unchanged retention workflow at 1280px and 390px: five policy controls remain readable, the mobile document and main content both remain 390px wide, the tab strip is 358px and the widest numeric control is 288px, and no narrow vertical text or horizontal overflow appears. Focused primitive, retention, RAG-policy, scheduler, and runtime-setting tests cover the shared control in each affected product boundary.

## Milestone 20 iteration: AI role workspace contract recovery

The AI role workspace was not merely incomplete visually: its mock-admin route rendered only the shell because the capability manifest advertised `/api/admin/agent-specs` while the MSW handler registry supplied no handler for it. The frontend list type also expected a full `systemPrompt` that the current backend deliberately withholds from list and detail responses. That mismatch made a missing local mock look like a vague page failure and offered an empty answer-principles textarea while editing unrelated fields.

The admin now validates the complete current backend list contract before rendering: role name and routing fields, `systemPromptPreview`, prompt-presence indicator, execution flags, enabled state, and ISO timestamps. A malformed or incomplete response fails closed to the existing Korean recovery state instead of becoming an empty directory. The mock handler mirrors that contract and keeps the full answer principles available only through the separate audited endpoint. Updating an existing role no longer renders or submits an unseen answer-principles textarea; that protected value remains behind its explicit disclosure. Creating a new role still provides the optional answer-principles field.

The populated workspace now opens as a readable two-row directory at 1280px rather than a blank shell: two role rows, no unavailable alert, a selected-role inspector, and a single edit path. At 390px, the edit dialog is 374px inside a 390px document and main workspace, with no horizontal overflow, no visible narrow text, and no hidden answer-principles textarea. The new `--data-row-height-comfortable` role replaces the literal directory-row geometry so the two-line registry remains token-owned. Focused API, role-modal, role-workspace, system-prompt, mock-handler, capability, and token tests cover the response boundary and operator interactions. This proves the checked backend schema and local mock workflow; authenticated live-backend role mutation QA remains open.

## Milestone 21 iteration: navigation selection and unused visual boundary

The shared shell still made the selected navigation label read like a browser-style blue link, even though it was a current-location state. Its previous visual support also kept an unused animated circular gauge, count-up hook, pulsing sidebar-dot rules, bouncing scroll-chevron rule, and dormant glow/lift tokens in the production source tree. None had a route consumer, so retaining them made the design system look more speculative than the product.

The token layer now names the Reactor Mark foreground and the active-navigation surface, text, and icon roles. The header mark and selected LNB icon use the warm mark token; the selected item keeps a primary-text label and a quiet full-row surface, so it remains a location cue rather than a blue link or warning-colored state. The unused gauge, count-up utility, exports, tests, pulse/bounce keyframes, and unused visual tokens are removed. `DESIGN.md` now preserves the distinction: blue remains for action/focus, while the warm mark is only product identity and selected-navigation iconography.

Browser QA on `/issues` verified the populated operator queue at desktop and 390px: the selected LNB label resolves to primary text, the icon and product mark resolve to the token-owned warm foreground, there are zero decorative vertical rails, no alert state, no long narrow text, and no document overflow (`1280px` desktop and `390px` narrow). Focused token, LNB, and header tests passed (`56` assertions). `pnpm lint` exited successfully with the existing repository-wide `282` warnings unchanged; `pnpm build` passed with the existing chunk-size advisory. This iteration proves the shell contract and source cleanup, not a fully warning-free repository or a final design-completion claim.

## Milestone 22 iteration: login recovery and identity boundary

The login screen had two related operational defects. Public authentication calls bypassed the shared API-error boundary, so FastAPI `detail` payloads and proxy failures fell into an indistinguishable general server-error sentence. The login mark also used the blue action token instead of the warm Reactor identity token, breaking the product-mark rule already used by the header and selected navigation.

Public login, registration, and demo-login calls now normalize response and connection failures through the same safe `ApiError` / `NetworkError` contract used by authenticated calls. FastAPI string `detail` values are recognized without exposing them as product copy. A failed admin login service or persistence configuration now tells the operator, in Korean, to check the login server and its connection settings; ordinary credential failures remain credential guidance. The login mark consumes `--brand-mark-foreground`, while the blue login button remains the intentional primary-action surface.

## Milestone 23 iteration: conversation detail focus and isolated message presentation

The populated conversation-detail capture showed the actual operator task—reading the conversation—below a raised session-information card and a six-field runtime block filled entirely with dashes. The same generic `chat-bubble` classes were also shared with the response-test page, so global inspector styles leaked into the session transcript and forced short messages into needlessly narrow nested boxes.

The detail page now uses a compact divided context row, presents the transcript immediately afterward, and only renders runtime information when the backend actually supplies runtime evidence. File export, flagging, and deletion remain available but are grouped under a closed `추가 작업` disclosure; opening it exposes the existing actions without changing their confirmation or export behavior. Session transcript classes are scoped away from the response-test surface, channel labels use localized Lucide icons rather than emoji or raw channel codes, and the compact transcript height is named by product tokens so short conversations do not leave a full-screen empty region.

Mock-browser QA at 1280px and 390px verified the populated three-message detail, closed and opened secondary-action states, absence of placeholder runtime rows, no horizontal overflow, a 288px compact transcript list at narrow width, and no console warnings or errors. This is source-controlled mock evidence for the detail view; it does not claim authenticated live-backend session mutation coverage. Focused session-detail, message-list, message-bubble, control, and token tests cover the interaction, layout order, isolated classes, and token contract.

## Milestone 24 iteration: release-link and translation-gate hygiene

The release-workflow shortcut rendered two evidence links for the same RAG answer-contract destination. That duplicated an operator choice while also emitting a React duplicate-key warning. The redundant link and its stale translation are removed; the remaining “근거 답변” entry is the only evidence link for that target.

The i18n verifier also now counts exact, source-controlled locale-key literals in shared helpers that receive a translation function as an argument. This restores correct ownership for active labels such as session-user formatting without raising the stale-key threshold or treating unknown dynamic keys as verified. The final gate reports zero missing keys and 276 unused candidates—below the existing 300-key ceiling—so future cleanup can focus on actual candidates rather than verifier false positives.

Live local browser QA used the current `POST /api/auth/demo-login` response (`503`, user persistence unavailable) rather than a mocked visual state. At desktop and `390×844`, the alert gave the clear Korean recovery sentence, the warm product mark resolved to `rgb(231, 189, 111)`, the card stayed within the `390px` document (`358px` card, no horizontal overflow), and all login controls remained visible. Focused auth, API-error, login-page, and token tests passed (`115` assertions). The local backend still lacks the persistence configuration required for a successful administrator session, so this milestone proves fail-closed UI recovery and the real failure classification—not an authenticated live operations pass.
