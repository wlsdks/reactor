# PRD — UI Redesign: Retro Terminal Aesthetic

**Status:** Draft
**Date:** 2026-03-05

---

## 1. Overview

This document defines the full UI/UX redesign of **Reactor Admin** to adopt the retro terminal (DOS/CRT) aesthetic from the **legacy retro admin dashboard** reference project.

The current UI uses a modern dark-blue SPA shell (sidebar + header layout). The redesign replaces the entire visual layer with a monospace terminal aesthetic while keeping all existing routing, data, and feature logic intact.

---

## 2. Goals

- Apply the retro terminal design language consistently across all 19 pages
- Replace current CSS token system with the retro palette
- Replace current sans-serif font stack with **IBM Plex Mono**
- Replace sidebar navigation with a top horizontal tab bar
- Preserve all existing features, API integration, auth flow, and workspace mode logic
- Maintain full i18n (ko) support

---

## 3. Design System

### 3.1 Color Palette

| Token | Value | Usage |
|---|---|---|
| `--retro-bg` | `#000000` | Root, header, footer, panel headers |
| `--retro-surface` | `#111827` | Panel backgrounds, cards |
| `--retro-elevated` | `#1F2937` | Nested panels, inputs, inactive buttons |
| `--retro-border` | `#374151` | All borders, dividers, table rows |
| `--retro-border-light` | `#4B5563` | Light borders, hover backgrounds |
| `--retro-gold` | `#E8D4A2` | **Primary brand accent** — active nav, highlights, INFO, values |
| `--retro-gold-hover` | `#D4C18E` | Hover state for gold elements |
| `--retro-white` | `#FFFFFF` | Primary text, data values |
| `--retro-gray-400` | `#9CA3AF` | Secondary labels, inactive text |
| `--retro-gray-500` | `#6B7280` | Muted text, hints, timestamps |
| `--retro-green` | `#22C55E` | RUNNING / OK (process/service status) |
| `--retro-yellow` | `#FBBF24` | WARNING / CAUTION |
| `--retro-red` | `#F87171` | ERROR / DANGER / DOWN |
| `--retro-blue` | `#60A5FA` | DEBUG / INFO / links |

### 3.2 Typography

- **Font family**: `'IBM Plex Mono', 'Courier New', monospace` — applied globally
- All UI text renders in monospace — labels, values, buttons, headers
- Font sizes follow Tailwind scale (`text-xs`, `text-sm`, `text-base`)
- No weight heavier than 500 (medium)

### 3.3 Spacing

| Context | Value |
|---|---|
| Panel header | `px-3 py-1` |
| Panel content | `p-3`, `space-y-3` |
| Page sections | `space-y-4` |
| Table cells | `py-1` compact / `py-2` standard |
| Grid gap | `gap-4` standard / `gap-2` compact |

### 3.4 Border Radius

- **0px** — No rounded corners. All panels, buttons, inputs use sharp edges (retro terminal feel).

---

## 4. Layout Architecture

### 4.1 Shell Layout (replaces AdminLayout + Sidebar)

```
┌──────────────────────────────────────────────────────────┐
│ HEADER                                                   │
│  [Logo 64×64]  C:\REACTOR>  ADMIN CONTROL PANEL     │
│                                          DATE   HH:MM:SS │
├──────────────────────────────────────────────────────────┤
│ NAV BAR  [DASH] [PERS] [PRMT] [MCP] [SCHD] [APPR] ...  │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  MAIN CONTENT  (p-4, space-y-4, pb-12)                  │
│                                                          │
├──────────────────────────────────────────────────────────┤
│ FOOTER (fixed)  [F1] Help | [F2] Refresh | [F10] Exit   │
│                                           STATUS: READY  │
└──────────────────────────────────────────────────────────┘
```

**Header:**
- `bg-black border-b border-gray-700`
- Logo (64×64, mix-blend-mode: lighten)
- Brand text: `C:\REACTOR>` in `#E8D4A2`
- Subtitle: "ADMIN CONTROL PANEL" in `text-gray-400`
- Right side: Date (gray-400) + Time (gold, live HH:MM:SS)
- Workspace mode toggle: `[MANAGER] [DEVELOPER]` button group (same nav button style)
- Language toggle: `[KO] [EN]`

**Nav Bar:**
- `bg-black border-t border-gray-700`
- Horizontal scrollable tab row: `flex gap-1 px-4 py-2 overflow-x-auto`
- Button: `px-3 py-1 font-mono text-sm`
- Active: `bg-[#E8D4A2] text-black`
- Inactive: `bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white`
- Transition: `transition-colors`
- Developer-only items hidden in Manager mode (same audience logic)

**Nav Labels (abbreviated for terminal feel):**

| Route | Label |
|---|---|
| `/` | DASH |
| `/personas` | PERS |
| `/prompts` | PRMT |
| `/mcp-servers` | MCP |
| `/scheduler` | SCHD |
| `/approvals` | APPR |
| `/sessions` | SESS |
| `/feedback` | FDBK |
| `/output-guard` | OGRD |
| `/tool-policy` | TPOL |
| `/documents` | DOCS |
| `/intents` | INTN |
| `/audit` | AUDT |
| `/prompt-lab` | PLAB |
| `/platform-admin` | PLTF |
| `/tenant-admin` | TNNT |
| `/metrics-ingestion` | MTRX |
| `/chat-inspector` | CHAT |
| `/integrations` | INTG |

**Footer:**
- `fixed bottom-0 left-0 right-0 border-t border-gray-700 bg-gray-900 px-4 py-2`
- Left: `[F1] Help | [F2] Refresh | [F10] Exit` in `text-gray-500 text-xs`
- Right: `STATUS: READY` in `text-[#E8D4A2] text-xs`

---

## 5. Common Component Patterns

### 5.1 Page Header (ASCII Banner)

Every page starts with an ASCII banner:

```
╔═══════════════════════════════════════════════════════════════════════════╗
║                            PAGE TITLE IN CAPS                            ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

- `<pre>` tag, `text-[#E8D4A2] text-xs leading-tight font-mono`

### 5.2 Panel / Card

```tsx
<div className="border border-gray-700 bg-gray-900">
  <div className="border-b border-gray-700 bg-black px-3 py-1">
    <span className="text-[#E8D4A2] font-mono text-xs">█ PANEL TITLE</span>
  </div>
  <div className="p-3 font-mono text-xs space-y-2">
    {/* content */}
  </div>
</div>
```

### 5.3 Stat Box

```tsx
<div className="border border-gray-700 bg-black p-3 text-center">
  <div className="text-gray-500 text-xs mb-1">LABEL</div>
  <div className="text-[#E8D4A2] text-2xl">VALUE</div>
</div>
```

4-column grid for page-level stats: `grid grid-cols-4 gap-4`

### 5.4 Data Table

```tsx
<table className="w-full font-mono text-xs">
  <thead>
    <tr className="border-b border-gray-700">
      <th className="text-left text-gray-500 pb-2">COLUMN</th>
    </tr>
  </thead>
  <tbody>
    <tr className="border-b border-gray-800 hover:bg-gray-800 transition-colors cursor-pointer">
      <td className="py-1 text-white">value</td>
    </tr>
  </tbody>
</table>
```

### 5.5 Status Badge

```
[ACTIVE]   → text-[#E8D4A2]
[RUNNING]  → text-green-400
[WARN]     → text-yellow-400
[ERROR]    → text-red-400
[DOWN]     → text-red-400
[INFO]     → text-[#E8D4A2]
[DEBUG]    → text-blue-400
[INACTIVE] → text-gray-400
```

Rendered as: `<span className="text-[#E8D4A2]">[ACTIVE]</span>`

### 5.6 Progress Bar

```tsx
const renderBar = (value: number, width = 20) => {
  const filled = Math.round((value / 100) * width)
  return (
    <span className="font-mono">
      [
      <span className="text-[#E8D4A2]">{'█'.repeat(filled)}</span>
      <span className="text-gray-700">{'░'.repeat(width - filled)}</span>
      ]
    </span>
  )
}
```

### 5.7 Button Variants

| Variant | Classes |
|---|---|
| Primary | `px-3 py-1 bg-[#E8D4A2] text-black hover:bg-[#D4C18E] transition-colors font-mono text-xs` |
| Secondary | `px-3 py-1 bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white transition-colors font-mono text-xs` |
| Danger | `px-3 py-1 bg-red-400 text-black hover:bg-red-300 transition-colors font-mono text-xs` |
| Info | `px-3 py-1 bg-blue-400 text-black hover:bg-blue-300 transition-colors font-mono text-xs` |

All buttons use bracket notation in labels: `[SAVE]`, `[DELETE]`, `[REFRESH]`

### 5.8 Input / Textarea

```
bg-black border border-gray-700 text-white text-xs font-mono
focus:outline-none focus:border-[#E8D4A2]
placeholder:text-gray-600
px-2 py-1
```

### 5.9 Key-Value Row

```tsx
<div className="flex">
  <span className="text-gray-500 w-36 shrink-0">LABEL:</span>
  <span className="text-white">{value}</span>
</div>
```

### 5.10 Section Divider

```tsx
<div className="border-t border-gray-700 pt-3 mt-3" />
```

### 5.11 Empty State

```tsx
<div className="text-center text-gray-500 font-mono text-xs py-8">
  [ NO DATA AVAILABLE ]
</div>
```

### 5.12 Loading State

```tsx
<div className="text-center text-[#E8D4A2] font-mono text-xs py-8">
  [ LOADING... ]
</div>
```

### 5.13 Error Alert

```tsx
<div className="border border-red-400 bg-red-400/10 px-3 py-2 text-red-400 font-mono text-xs">
  [ERROR] {message}
</div>
```

### 5.14 Warning Alert

```tsx
<div className="border border-yellow-400 bg-yellow-400/10 px-3 py-2 text-yellow-400 font-mono text-xs">
  [WARN] {message}
</div>
```

### 5.15 Confirm Dialog

```tsx
<div className="border border-gray-700 bg-gray-900 p-4 font-mono text-xs">
  <div className="text-[#E8D4A2] mb-3">█ CONFIRM ACTION</div>
  <div className="text-gray-300 mb-4">{message}</div>
  <div className="flex gap-2">
    <button className="...danger">  [CONFIRM] </button>
    <button className="...secondary"> [CANCEL] </button>
  </div>
</div>
```

---

## 6. Page-Level Specifications

### 6.1 Dashboard (`/`)

**ASCII Banner:** `OPERATIONS DASHBOARD`

**Stats Row (4 cols):**
- MCP SERVERS (total count)
- CONNECTED (count)
- METRICS TRACKED (count)
- RAG STATUS (ENABLED / DISABLED)

**Two-column grid (responsive → single on mobile):**

**Left panel — MCP STATUS:**
- Panel header: `█ MCP SERVER STATUS`
- Table: STATUS | COUNT
- Status cells color-coded

**Right panel — KNOWLEDGE SEARCH:**
- Panel header: `█ KNOWLEDGE SEARCH`
- Key-value: RAG enabled / disabled with gold/red badge
- recharts PieChart (dark theme, gold fill)

**Developer mode only — bottom panels:**
- `█ OPERATIONAL SIGNALS` — table of metric name, meter count, measurements
- Advanced filter: `█ METRIC FILTER` — comma-separated input

---

### 6.2 Personas (`/personas`)

**ASCII Banner:** `PERSONA CONFIGURATION`

**Stats Row (4 cols):** TOTAL | ACTIVE | DEFAULT | LAST MODIFIED

**Two-column layout:**

**Left — `█ PERSONA LIST`:**
- Table: NAME | STATUS | UPDATED | [DELETE]
- Active row highlighted with gold border-left
- `[NEW PERSONA]` button above table

**Right — `█ PERSONA DETAIL`:**
- Header shows persona name + icon
- Tab bar: `[INFO]` `[PLAYGROUND]`

**INFO Tab:**
- Key-value fields with inline edit
- `[EDIT]` / `[SAVE]` / `[CANCEL]` buttons
- Fields: Name, Icon (emoji picker row), System Prompt, Response Guideline, Welcome Message
- `[SET DEFAULT]` toggle
- Resolved Prompt collapsible section

**PLAYGROUND Tab:**
- Chat area: messages list (monospace, role-labeled)
- User message: `> USER: {text}`
- Assistant: `> {icon}: {text}` with streaming cursor `█`
- Tool indicator: `[ USING TOOLS: tool1, tool2 ]` in gold
- Input bar at bottom: textarea + `[SEND]` / `[STOP]` / `[CLEAR]`

---

### 6.3 Prompt Templates (`/prompts`)

**ASCII Banner:** `PROMPT TEMPLATE MANAGER`

**Two-column layout:**

**Left — `█ TEMPLATES`:**
- Table: NAME | VERSIONS | ACTIVE VER | UPDATED
- `[NEW TEMPLATE]` button
- Selected row highlighted

**Right — `█ TEMPLATE DETAIL`:**
- Template name + description
- Version list: `█ VERSIONS` table — VERSION | STATUS | UPDATED | ACTIONS
- Status badges: `[DRAFT]` `[ACTIVE]` `[ARCHIVED]`
- `[NEW VERSION]` button
- Selected version content: code block display
- Actions: `[ACTIVATE]` `[ARCHIVE]`

---

### 6.4 MCP Servers (`/mcp-servers`)

**ASCII Banner:** `MCP SERVER MANAGEMENT`

**Warning banner:**
```
[INFO] MCP registration and credentials are managed centrally from admin.
```

**Two-column layout:**

**Left — `█ SERVER LIST`:**
- Table: NAME | TRANSPORT | TOOLS | STATUS | ACTIONS
- Status: `[CONNECTED]` / `[DISCONNECTED]`
- Actions: `[CONNECT]` / `[DISCONNECT]` / `[DELETE]`
- `[REGISTER SERVER]` button

**Right — `█ SERVER DETAIL`:**
- Name, transport, version key-values
- Tools list as tags: `[tool_name]` in gray
- `█ ACCESS POLICY` section
- Allowed lists: Jira / Confluence / Bitbucket (textarea inputs)
- `[SAVE POLICY]` / `[RESET POLICY]` buttons

---

### 6.5 Scheduler (`/scheduler`)

**ASCII Banner:** `SCHEDULER — JOB MANAGEMENT`

**Stats Row (4 cols):** TOTAL JOBS | ENABLED | LAST RUN | SUCCESS RATE

**Two-column layout:**

**Left — `█ SCHEDULED JOBS`:**
- Table: NAME | TYPE | CRON | STATUS | LAST RUN
- Status badge: `[ENABLED]` / `[DISABLED]`
- Actions: `[TRIGGER]` `[DRY RUN]` `[EDIT]` `[DELETE]`
- `[NEW JOB]` button

**Right — `█ JOB DETAIL`:**
- Job info key-values
- `█ EXECUTION HISTORY` table: TIME | STATUS | DURATION | RESULT
- Last result in code block

**New/Edit Job — inline panel (replace detail):**
- Form fields: Name, Type (AGENT/MCP_TOOL), Cron, Timezone, Enabled toggle
- Conditional fields per type
- `[SAVE]` / `[CANCEL]`

---

### 6.6 Approvals (`/approvals`)

**ASCII Banner:** `APPROVAL QUEUE`

**Stats Row (4 cols):** PENDING | APPROVED | REJECTED | TOTAL

**Two-column layout:**

**Left — `█ APPROVAL REQUESTS`:**
- Filter: `[ALL]` `[PENDING]` `[APPROVED]` `[REJECTED]`
- Table: TOOL | RUN ID | STATUS | REQUESTED AT
- Status badge color-coded

**Right — `█ REQUEST DETAIL`:**
- Key-values: Tool, User (anonymised), Run ID, Status, Requested At
- Arguments in code block
- Actions: `[APPROVE]` `[REJECT]`
- Reject reason textarea (shown on reject)

---

### 6.7 Sessions (`/sessions`)

**ASCII Banner:** `SESSION DIAGNOSTICS`

**Stats Row (4 cols):** TOTAL SESSIONS | TOTAL MESSAGES | AVG MESSAGES | BUSIEST

**Two-column layout:**

**Left — `█ SESSION LIST`:**
- Table: SESSION ID (truncated) | MESSAGES | LAST ACTIVITY | PREVIEW
- `[DELETE]` per row

**Right — `█ SESSION DETAIL`:**
- Session ID + message count
- `[EXPORT JSON]` `[EXPORT MD]` buttons
- Message list: role-labeled, monospace, chronological
- `[ LOAD {n} OLDER MESSAGES ]` button at top

---

### 6.8 Feedback (`/feedback`)

**ASCII Banner:** `FEEDBACK MANAGEMENT`

**Stats Row (4 cols):** TOTAL | THUMBS UP | THUMBS DOWN | RATIO

**Two-column layout:**

**Left — `█ FEEDBACK LIST`:**
- Filter: `[ALL]` `[👍 UP]` `[👎 DOWN]`
- Table: RATING | COMMENT | DATE | [DELETE]
- Rating badge: `[UP]` in gold / `[DOWN]` in red
- `[EXPORT JSON]` / `[REFRESH]` buttons

**Right — `█ FEEDBACK DETAIL`:**
- Rating, comment, metadata
- Query / Response in code blocks
- `█ SUBMIT TEST FEEDBACK` sub-panel (collapsible)
  - Form: Rating toggle, Query, Response, Comment, Tags, Run ID

---

### 6.9 Output Guard (`/output-guard`)

**ASCII Banner:** `OUTPUT GUARD — SAFETY RULES`

**Two-column layout:**

**Left — `█ RULE LIST`:**
- Table: NAME | TYPE | STATUS | UPDATED
- `[NEW RULE]` button

**Right — `█ RULE DETAIL`:**
- Name, type, status, pattern/config
- Config in code block
- `[EDIT]` `[DELETE]` buttons

---

### 6.10 Tool Policy (`/tool-policy`)

**ASCII Banner:** `TOOL POLICY CONFIGURATION`

**Two-column layout:**

**Left — `█ POLICY EDITOR`:**
- Form fields with terminal-style inputs
- Config enabled / Dynamic enabled toggles (checkbox with label)
- Write tool names (textarea)
- Deny write channels (textarea)
- Deny message template (input)
- Channel-based rules (JSON textarea)
- `[SAVE POLICY]` `[RESET TO DEFAULTS]` buttons

**Right — `█ EFFECTIVE POLICY`:**
- Code block: current effective policy JSON
- `█ STORED POLICY`: code block
- `[REFRESH]` button

---

### 6.11 Documents (`/documents`)

**ASCII Banner:** `DOCUMENT PIPELINE`

**Two-column layout:**

**Left — `█ DOCUMENT LIST`:**
- Table: NAME | TYPE | STATUS | INGESTED
- `[UPLOAD]` / `[DELETE]` buttons

**Right — `█ RAG CANDIDATES`:**
- Filter: channel, status
- Table: ID | CHANNEL | STATUS | PREVIEW
- `[INGEST]` / `[REJECT]` actions
- `█ RAG POLICY` section: code block

---

### 6.12 Intents (`/intents`)

**ASCII Banner:** `INTENT CLASSIFICATION`

**Two-column layout:**

**Left — `█ INTENT LIST`:**
- Table: NAME | PATTERN COUNT | STATUS | UPDATED
- `[NEW INTENT]` button

**Right — `█ INTENT DETAIL`:**
- Name, description key-values
- Pattern list as monospace code
- `[EDIT]` `[DELETE]`

---

### 6.13 Audit Log (`/audit`)

**ASCII Banner:** `AUDIT LOG — COMPLIANCE INSPECTOR`

**Stats Row (4 cols):** TOTAL EVENTS | CATEGORIES | ACTORS | LAST EVENT

**Full-width layout:**

**Filter bar:**
- Category input + Action input + `[APPLY]` `[RESET]` buttons

**`█ AUDIT EVENTS` table:**
- Columns: TIMESTAMP | CATEGORY | ACTION | ACTOR | RESOURCE | DETAIL
- Click row for detail panel (slide-in or inline expand)

**Selected row detail:**
```
[DETAIL]  {JSON payload in code block}
```

---

### 6.14 Prompt Lab (`/prompt-lab`)

**ASCII Banner:** `PROMPT LAB — EXPERIMENT CONSOLE`

**Two-column layout:**

**Left — `█ EXPERIMENTS`:**
- Filter: status dropdown + `[APPLY]`
- Table: NAME | STATUS | VERSION COUNT | UPDATED
- `[NEW EXPERIMENT]` button

**Right — `█ EXPERIMENT DETAIL`:**
- Name, description, status key-values
- Versions table: VERSION | STATUS | SCORE | UPDATED
- Selected version: prompt content in code block
- `[ACTIVATE]` `[ARCHIVE]` actions

---

### 6.15 Platform Admin (`/platform-admin`)

**ASCII Banner:** `PLATFORM ADMINISTRATION`

**Two-column layout:**

**Left:**
- `█ PLATFORM HEALTH` — key-values + code block
- `█ TENANT LIST` — table with SUSPEND/ACTIVATE actions + `[NEW TENANT]`

**Right:**
- `█ USER ROLE MANAGEMENT` — email input + role select + `[UPDATE ROLE]`
- `█ MODEL PRICING` — table + inline form
- `█ ALERT RULES` — table + form + `[DELETE]`
- `█ ACTIVE ALERTS` — table + `[RESOLVE]`

---

### 6.16 Tenant Admin (`/tenant-admin`)

**ASCII Banner:** `TENANT ANALYTICS`

**Scope bar (full-width):**
```
TENANT ID: [_____________]  FROM: [datetime]  TO: [datetime]  [LOAD]
```

**Two-column layout:**

**Left:**
- `█ OVERVIEW` — code block
- `█ USAGE` — code block
- `█ QUALITY` — code block
- `█ TOOLS` — code block

**Right:**
- `█ COST` — code block
- `█ SLO` — code block
- `█ QUOTA` — code block
- `█ TENANT ALERTS` — table
- `[EXPORT EXECUTIONS CSV]` `[EXPORT TOOLS CSV]`

---

### 6.17 Metrics Ingestion (`/metrics-ingestion`)

**ASCII Banner:** `METRICS INGESTION — API DEBUGGER`

**Warning banner:**
```
[WARN] Use this page to manually send operational metrics through API.
```

**Three-column grid (responsive):**
- `█ MCP HEALTH` — JSON textarea + `[SEND MCP HEALTH]`
- `█ TOOL CALL` — JSON textarea + `[SEND TOOL CALL]`
- `█ EVAL RESULT` — JSON textarea + `[SEND EVAL RESULT]`
- `█ EVAL RESULTS BATCH` — JSON textarea + `[SEND BATCH]`
- `█ MCP HEALTH BATCH` — JSON textarea + `[SEND MCP BATCH]`

**Response panel:**
- `█ LAST RESPONSE` — code block

---

### 6.18 Chat Inspector (`/chat-inspector`)

**ASCII Banner:** `CHAT API DIAGNOSTICS`

**Mode tabs:** `[ONE-SHOT]` `[STREAM]` `[FILE+CHAT]`

**Two-column layout:**

**Left — `█ REQUEST`:**
- Quick presets: `[HEALTH CHECK]` `[SUMMARY]` `[INCIDENT JSON]`
- Message textarea
- Advanced section (collapsible `[▼ ADVANCED OPTIONS]`):
  - Model, Persona ID, Template ID, System Prompt
  - Metadata JSON, Response Format, Schema
- `[RUN REQUEST]` button

**Right — `█ RESPONSE`:**
- Stream mode: live token output with monospace cursor
- Events list: `█ EVENTS (n)` — timestamp + event type + payload
- Response metadata: model, tools used
- Raw JSON in code block

---

### 6.19 Integrations (`/integrations`)

**ASCII Banner:** `INTEGRATION DIAGNOSTICS`

**Mode tabs:** `[SLACK COMMAND]` `[SLACK EVENT]` `[ERROR REPORT]`

**Two-column layout:**

**Left — `█ REQUEST`:**
- Preset: `[APPLY SAMPLE PAYLOAD]`
- Mode-specific fields (command text, event JSON, error stack)
- Advanced section (collapsible)
- `[SEND TEST]` button

**Right — `█ LAST RESPONSE`:**
- Status badge + code block response

---

### 6.20 Login Page (`/login`)

**Full-screen terminal login:**

```
┌──────────────────────────────────────┐
│  C:\REACTOR> LOGIN               │
├──────────────────────────────────────┤
│                                      │
│  [  REACTOR ADMIN  ]             │
│                                      │
│  EMAIL:    [________________]        │
│  PASSWORD: [________________]        │
│                                      │
│           [SIGN IN]                  │
│                                      │
│  [WARN] Admin access only            │
│                                      │
└──────────────────────────────────────┘
```

- `bg-black min-h-screen flex items-center justify-center font-mono`
- Card: `border border-gray-700 bg-gray-900 p-8 w-full max-w-sm`
- Error: `[ERROR] {message}` in red-400
- Loading: `[AUTHENTICATING...]` in gold

---

## 7. Responsive Strategy

| Breakpoint | Behaviour |
|---|---|
| Default (mobile) | Single column, nav scrolls horizontally |
| `md` (768px+) | Two-column grid activates for most pages |
| `lg` (1024px+) | Full layout, wider panels |

---

## 8. Shared Component Inventory (to rebuild)

| Current Component | Retro Replacement |
|---|---|
| `AdminLayout` + `Sidebar` | `RetroShell` — header + nav bar + content + footer |
| `DataTable` | `RetroTable` — monospace, border-gray-700, text-xs |
| `StatCard` | `RetroStatBox` — centered, text-2xl gold value |
| `StatusBadge` | `RetroStatus` — bracket notation `[STATUS]` |
| `LoadingSpinner` | `RetroLoading` — `[ LOADING... ]` text |
| `EmptyState` | `RetroEmpty` — `[ NO DATA ]` text |
| `ConfirmDialog` | `RetroConfirm` — bordered panel with buttons |
| Buttons | Retro button variants (primary/secondary/danger/info) |

---

## 9. Implementation Phases

### Phase 1 — Foundation
- New CSS token system (`--retro-*` palette)
- IBM Plex Mono font import
- `RetroShell` layout (header + horizontal nav + footer)
- Rebuild `shared/ui/` components with retro style
- Login page

### Phase 2 — Core Pages
- Dashboard
- Personas (including Playground)
- MCP Servers
- Sessions
- Audit Log

### Phase 3 — Config Pages
- Prompt Templates
- Scheduler
- Approvals
- Output Guard
- Tool Policy

### Phase 4 — Advanced Pages
- Documents
- Intents
- Feedback
- Prompt Lab
- Platform Admin
- Tenant Admin
- Metrics Ingestion
- Chat Inspector
- Integrations

---

## 10. Out of Scope

- Backend API changes
- Auth logic changes
- i18n key changes (labels will use t() keys as-is)
- Feature logic / data fetching (React Query hooks untouched)
- Route structure

---

## 11. Quality Gates

All phases must pass before merge:

```bash
pnpm lint
pnpm build
pnpm verify:admin-api
```
