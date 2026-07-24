# Design System of Reactor Admin

## Operator workflow language

- A domain page leads with the operator's local task in three to five plain-language steps. It must not repeat the same state as a release flow, contract list, evidence queue, and status-card grid.
- Framework names, report keys, dataset identifiers, commands, and release evidence belong in a closed `details` disclosure titled `자세한 확인 정보` unless they are required to complete the current task.
- Status labels use user-facing Korean (`준비됨`, `확인 필요`, `검토됨`). Raw values such as `PASS`, `WARN`, `readiness`, `evidence`, and `handoff` are not primary interface copy.
- Empty states are compact, left-aligned operational messages with a reason and recovery path. Do not reserve a large card or viewport-height area for a decorative empty icon.
- Destructive or low-frequency maintenance controls stay in a collapsed disclosure below the everyday status and configuration controls.
- Shared collapsed content uses native `<details>` and `<summary>`, with the shared Lucide chevron and tokenized spacing. Its body must be removed from the visible and accessibility tree while closed; text triangles (`▶`, `▼`, `▸`) and card-like disclosure shells are prohibited.
- Controls use the shared Lucide icon set, never text glyphs such as `▲`, `▼`, `▶`, `◀`, `▸`, `▾`, `⋮`, `−`, or `+`. Increment/decrement controls consume the shared control-height and icon-size tokens. Remove unused navigation primitives—especially decorative side rails—instead of keeping them exported for a possible future use.
- External-notification destinations use one continuous collection surface: destination identity first, transport ID second, registration time last. Do not pair a small table with an always-empty detail card or repeat the same count in a separate metric tile.
- Adding a notification destination uses a shared drawer and explains when delivery begins. Removal stays inside the selected destination drawer, under a collapsed maintenance disclosure, and requires typed confirmation because it can silently stop operational alerts.
- A missing or unavailable notification API is an unavailable state, not an empty collection. Never swallow `404` or server failures into an empty list when doing so would imply that no destinations are configured.
- Credential-backed integration lists show the human connection name, workspace identity, and plain-language activity state. Secret fields never appear in list or detail responses, and row-level edit/delete icon clusters are replaced by a selected connection drawer.
- Connection removal is treated as an external capability outage: keep it under collapsed maintenance controls and require typed connection-name confirmation. API failure renders an unavailable state with retry and closed technical detail, never a raw error line.
- Multi-purpose integration workspaces use task navigation instead of stacking every tool in collapsible panels. Keep channel status, answer testing, activity review, and maintenance as distinct URL-addressable views; do not expose all forms and tables at once.
- Operator-facing AI outcomes and thresholds are translated into decisions people can act on. Raw enum values such as `AUTO`, `MATCH`, `MISS`, `WOULD_REPLY`, and engineering labels such as `Dry-run` stay out of primary UI; identifiers remain secondary evidence only.
- Review queues keep scanning and decision-making separate. The collection surface shows human status, subject, source, and time; full payloads, comments, approve/reject actions, run IDs, and record IDs belong in a selected-item drawer rather than row action clusters or always-visible code blocks.
- Approval queues use a compact readiness sentence and flat facts, never a metric-card grid. Show localized state and a human age (`분`/`시간`/`일`) in the queue; keep run IDs, timeouts, and idempotency keys inside closed `자세한 확인 정보`. On tablet and mobile, selecting a queue row must move the selected detail into view rather than leaving the decision below the fold.
- Integration landing views answer only two questions: what is connected, and what needs attention now. Report keys, environment-variable names, workflow step links, commands, and protocol evidence belong in the URL-addressable `상세 진단` view; side-effecting checks belong in `실제 시험`. Use a semantic dot plus text for an operation state, not a status badge or pill.
- A live AI response test shows one target, one next action, and a plain-language result. Provider internals, model identifiers, framework usage-source strings, release commands, and release-route link clusters stay out of the everyday result; unavailable release aggregation must not look like a passed or empty result.
- Release navigation is owned by the page shell. Feature panels must not repeat release stage cards, step arrows, or handoff link clusters already visible in the page header; show only the operational state needed for the current task.
- Primary search and create flows start with the question or content a non-technical operator understands. Ranking limits, similarity thresholds, metadata JSON, batch payloads, record IDs, and raw source objects are advanced or technical details and stay collapsed until requested.
- Collection tables optimize for scanning: use human titles, sources, excerpts, dates, and plain-language quality signals. Destructive row actions and raw identifiers belong in selection-driven detail surfaces; do not add permanent action columns when the row already opens a drawer.
- Policy editors are organized by the operator decision they change, not backend capability flags. Explain the consequence beside each control; configuration source, dynamic-mode flags, stored/effective diagnostics, and reset maintenance stay in collapsed technical or maintenance sections.
- Analytics choose a visualization that matches the data dimension. Categorical channel aggregates use comparison bars, not faux time-series areas; status totals form one compact summary rather than a grid of interchangeable stat cards.
- Version or policy comparisons keep each option as one readable row with a flat labeled fact list. Do not turn pass rate, score, latency, and error rate into a repeated metric-tile grid.

> Reactor Admin uses a dark-mode-native, semantic-token system: cool graphite surfaces, high-contrast labels, one restrained blue selection accent, a warm Reactor product mark, and separate warning semantics. Apple Dark Mode and Primer color-role guidance inform the base/elevated hierarchy; Reactor's product contracts determine the actual tokens and components.

## 1. Visual Theme & Atmosphere

Reactor Admin is a dark-mode-first operator console built for AI platform engineers and platform managers. The canvas is cool graphite rather than blue-black. Content depth uses four restrained luminance roles (`#101419` → `#171C23` → `#202731` → `#28313D`); large blue, yellow, green, or red panels are prohibited. Floating overlays may use a neutral shadow, but content hierarchy comes from spacing, typography, and surface luminance.

The type system is built on **Pretendard Variable** — a Korean-first humanist sans with native Latin support calibrated to the metrics of Inter. It is used with OpenType `ss01` enabled where available (Pretendard's Latin stylistic alternate, analogous to Linear's `cv01`) and ranges from weight 400 (reading) through **510 (signature emphasis weight)** to 600 (strong emphasis). The 510 weight is Linear's contribution to this system and Reactor preserves it — a subtle medium that carries UI labels, navigation, and buttons without the heaviness of true semibold. **IBM Plex Mono** (not Berkeley Mono) is the monospace companion, reserved for numeric values, IDs, codes, timestamps, and tokens per project convention.

The color story is graphite backgrounds and neutral labels (`#F2F5F9` / `#C8D0DA` / `#98A5B5` / `#758396`) — punctuated by **Reactor Blue** (`#7AA7FF`) for actions and focus, and a warm **Reactor Mark** (`#E7BD6F`) for product identity. Blue never serves as bare link text. Semantic green, amber, red, and mist blue are small status signals only: icon, dot, short label, or restrained boundary. They do not tint a whole information panel.

**Design direction:** *Quiet Authority* — clean, professional, no terminal cosplay, no ASCII art, no gradient neon, no futuristic sci-fi chrome. References cited in `CLAUDE.md` are the **Linear** and **Vercel** login pages. Admin density is earned through typographic hierarchy and surface stepping, not through visual noise.

**Key Characteristics:**
- Dark-mode-native on cool graphite: `#101419` root, `#171C23` surface, `#202731` elevated
- Pretendard Variable with `ss01` where available — clean Latin alternates consistent with Korean metrics
- **Signature weight 510** carries UI; 400 reads, 600 announces
- Mono-font (`IBM Plex Mono`) strictly for numeric values, IDs, tokens — not for prose
- Reactor Blue `#7AA7FF` (primary) / `#99BBFF` (hover) — actions, selection controls, and focus only
- Reactor Mark `#E7BD6F` — product mark and selected-navigation icon only; never a warning substitute
- Muted status palette: green `#5EBA8D`, warning `#D6A451`, error `#E07C7C`, info `#8CB8FF`
- Neutral translucent separators derived from `rgba(221, 228, 238, …)`; never chromatic chrome
- Depth via background luminance stacking — no drop shadows on dark surfaces
- Uppercase reserved for table headers, labels, and captions only — never body, never headings

## 2. Color Palette & Roles

### Background Surfaces (3-Level Stack)
- **Root Canvas** (`#101419`): application background.
- **Surface** (`#171C23`): content surface, sidebar, and header.
- **Elevated** (`#202731`): hover, selected rows, and secondary layers.
- **Overlay** (`#28313D`): popovers, dropdowns, and modals.
- **Input Well** (`#0D1116`): recessed input background.

### Text & Content (WCAG AA verified on `#0C1017`)
- **Primary Text** (`#F1F5F9`): Near-white slate with a cool undertone. Default text — never pure `#FFFFFF`.
- **Secondary Text** (`#CBD5E1`): Body text, descriptions, readable secondary content.
- **Muted Text** (`#94A3B8`): Labels, captions, metadata.
- **Dim Text** (`#8899AC`): Inactive, hint, placeholder. Meets WCAG AA ≥4.5:1 on root canvas.

### Brand & Accent
- **Reactor Blue** (`#7AA7FF`): Product selection color — primary actions, selection controls, and focus rings.
- **Reactor Blue Hover** (`#99BBFF`): Hover variant — brighter without reading as a status warning.
- **Blue Dim** (`rgb(122 167 255 / 0.10)`): Background wash for selected controls and compact operational affordances.
- **Blue Shadow** (`rgb(122 167 255 / 0.25)`): Focus ring / button glow, used sparingly.
- **Blue Subtle** (`rgb(122 167 255 / 0.05)`): Ambient accent for intentional Reactor graphics only.
- **Blue Border** (`rgb(122 167 255 / 0.24)`): Accent-tinted boundary for focused interactive controls.
- **Reactor Mark** (`#E7BD6F`): Product identity and selected-navigation icon. It is not a warning state and does not fill content panels.

### Status Colors
- **Green** (`#5EBA8D`): Healthy, active, success — service UP, policy PASS.
- **Amber** (`#D6A451`): Warning — degraded, retry, non-blocking alert.
- **Red** (`#E07C7C`): Error, fail, destructive confirmation.
- **Mist Blue** (`#8CB8FF`): Informational context, never a browser-default link substitute.

Each status color has matching `-dim` (12–15% alpha fill), `-tint` (background wash), and `-border` (30% alpha) tokens for pill / badge / callout composition.

### Border & Divider
- **Border Default** (`#1E2A3A`): Card edges, table lines, panel separation — solid slate that reads as structural, not decorative.
- **Border Light** (`#2A3A4E`): Emphasized borders — section headers, elevated card edges.
- **Blue Border** (`rgb(122 167 255 / 0.24)`): Accent-tinted for focused interactive surfaces.
- **Focus Ring** (`rgb(122 167 255 / 0.46)`): Keyboard focus — always present, never suppressed.

### Chart Palette
- `--chart-1` Blue (`#60A5FA`) — primary metric
- `--chart-2` Green (`#34D399`) — success / positive trend
- `--chart-3` Violet (`#A78BFA`) — secondary metric (the only color beyond status + accent)
- `--chart-4` Red (`#F87171`) — negative trend / error rate

### Overlay
- **Overlay Primary** (`rgba(0, 0, 0, 0.7)`): Modal / dialog backdrop. Slightly less opaque than Linear's `0.85` — the warmer canvas carries modal focus naturally.

### Reference basis

- [Apple Dark Mode](https://developer.apple.com/design/human-interface-guidelines/dark-mode): base/elevated dark surfaces, adaptive semantic labels, and high text contrast.
- [Primer color usage](https://primer.style/product/getting-started/foundations/color-usage/): product code consumes semantic roles instead of binding components to raw hues.

### Responsive role tokens

| Range | Workspace gutter | Panel padding | Compact control | Data row | Layout rule |
|---|---:|---:|---:|---:|---|
| Desktop `>1024px` | `32px` | `24px` | `36px` | `48px` | multi-column only when comparison benefits |
| Tablet `641–1024px` | `24px` | `20px` | `36px` | `52px` | side navigation collapses; master/detail stacks |
| Mobile `≤640px` | `16px` | `16px` | `40px` | `56px` | one reading column; actions wrap or become full-width |

The canonical values live in `src/styles/product-tokens.css`. Feature styles may collapse earlier for content fit, but they must consume the role tokens and must not reduce mobile touch targets below 40px. Every route milestone requires desktop plus tablet and mobile browser evidence; if the browser cannot apply the requested viewport, that state remains unverified rather than being inferred from CSS.

## 3. Typography Rules

### Font Family
- **Primary**: `'Pretendard Variable', 'Pretendard', -apple-system, system-ui, sans-serif`
- **Monospace**: `'IBM Plex Mono', 'Courier New', monospace`
- **OpenType Features**: `"ss01"` enabled where available (Pretendard's Latin stylistic alternate). Pretendard's metrics map closely to Inter, so Linear's type rhythm transfers naturally.

### Base Root
- `html { font-size: 16px }`. Density is controlled with role tokens, not by shrinking the browser root.

### Hierarchy (tokens from `src/index.css`)

| Role | Token | Font | Size | Weight | Line Height | Notes |
|------|-------|------|------|--------|-------------|-------|
| Page Heading | `--text-xl` | Pretendard | `clamp(1.25rem, 1.15rem + 0.25vw, 1.5rem)` (20–24px) | 510–600 | 1.3 | Page titles — one per screen |
| Section Heading | `--text-lg` | Pretendard | `clamp(1rem, 0.95rem + 0.15vw, 1.125rem)` (16–18px) | 510–600 | 1.4 | Panel headers |
| Section Title | `--text-md` | Pretendard | `0.9375rem` (15px) | 510 | 1.5 | Card / group titles |
| Body | `--text-sm` | Pretendard | `0.8125rem` (13px) | 400 | 1.55 | Default reading text |
| Body Emphasis | `--text-sm` | Pretendard | `0.8125rem` (13px) | 510 | 1.55 | Nav links, table cells |
| Secondary | `--text-xs` | Pretendard | `0.75rem` (12px) | 400–510 | 1.5 | Metadata, timestamps |
| Label / Caption | `--text-xxs` | Pretendard | `0.6875rem` (11px) | 510–600 | 1.4 | Table headers, badges — often UPPERCASE |
| Stat Numeric | `--text-data` | IBM Plex Mono | `1.75rem` (28px) | 500 | 1.1 | Large stat values — always mono |
| Body Numeric | inline | IBM Plex Mono | inherit | 400–500 | inherit | All inline IDs, tokens, numeric cells |

### Principles
- **510 is the signature weight** (adopted from Linear). Pretendard Variable supports continuous weight axis, so `font-weight: 510` renders precisely. It sits between 500 and 600 and carries every UI label, button, and nav item without feeling heavy.
- **Three-tier weight system**: 400 (read), 510 (UI / emphasize), 600 (announce). Never use 700+ — the canvas doesn't need shouting.
- **Mono for data**: IBM Plex Mono is strictly for numeric values, IDs, hashes, timestamps, code, tokens. Never for prose, never for headings, never for labels. Table cells containing numbers are mono; cells containing words are sans.
- **Uppercase is rare**: restricted to table headers (`<th>`), form labels, small-caps captions, and micro-labels (`--text-xxs`). Never uppercase a heading, a button label, or a sentence.
- **No letter-spacing gymnastics at typical sizes**: Pretendard's metrics are already calibrated. Display-size headings (>28px) may take a slight negative tracking (-0.02em), but the 14px root means display sizes are rare in admin UI.
- **OpenType `ss01`** when available — matches Linear's philosophy that stylistic-set features are identity, not decoration.

## 4. Component Stylings

### Buttons

**Primary Button** (`.btn-primary`)
- Background: `#7AA7FF` (Reactor Blue)
- Text: `#101419` (root canvas — inverted)
- Border: `1px solid #7AA7FF`
- Radius: `4px` (`--radius-sm`)
- Padding: `0.5rem calc(0.78rem + 0.14rem)`
- Font: Pretendard 12px weight 600
- Shadow: `0 1px 3px rgb(122 167 255 / 0.25)` (minimal blue focus signal)
- Hover: bg `#99BBFF`, `translateY(-1px)`, glow intensifies to `rgb(122 167 255 / 0.46)`
- Active: `translateY(0)`, lighter shadow
- Use: Submit, Save, confirm destructive primary actions — the loudest element on a screen

**Secondary Button** (`.btn-secondary`)
- Background: `#111820` (surface)
- Text: `#CBD5E1`
- Border: `1px solid #1E2A3A`
- Radius: `4px`
- Hover: background `#1C2636`, text `#F1F5F9`
- Use: Cancel, standard actions, secondary CTA

**Ghost / Icon Button**
- Background: transparent
- Text: `#94A3B8` default, `#F1F5F9` on hover
- Border: none
- Radius: `4px` (rectangular icon) or `50%` (circular icon)
- Hover: background `rgb(122 167 255 / 0.10)` (blue-dim)
- Use: Toolbar, close, contextual

**Danger Button**
- Background: `#F87171` (red)
- Text: `#0C1017`
- Border: `1px solid #F87171`
- Use: Destructive confirm in modal. Never as a top-of-screen primary — reserved for explicit destructive confirmation.

**Disabled state**: `opacity: 0.4; cursor: not-allowed` — applies uniformly. Never dim the label while keeping the button clickable.

### Cards & Containers
- Background: `#111820` (surface) — solid, not translucent (the 3-level stack replaces Linear's white-opacity stepping)
- Border: `1px solid #1E2A3A`
- Radius: `8px` (`--radius-md`) for standard cards, `12px` (`--radius-lg`) for featured panels
- Padding: `--panel-pad` = `20px` default
- Hover (interactive cards only): border shifts to `#2A3A4E`, background to `#151E2B`
- No drop shadow on dark — elevation communicates through surface step

### Inputs & Forms
- Background: `#0A0E14` (input well — one step darker than root)
- Text: `#F1F5F9`
- Border: `1px solid #1E2A3A`
- Radius: `4px`
- Padding: `0.5rem 0.78rem`
- Font: Pretendard 13px weight 400
- Focus: border `#7AA7FF`, box-shadow `0 0 0 2px rgb(122 167 255 / 0.46)` (focus ring)
- Invalid (with `aria-invalid`): border `#F87171`, ring `rgba(248, 113, 113, 0.3)`
- Placeholder: `#8899AC` (dim text, WCAG AA verified)

### Tables
- Row height: 40–44px
- Header: `#111820` bg, `UPPERCASE` 11px Pretendard weight 600, `#94A3B8` text, `scope="col"`, `aria-sort` where sortable
- Row border: `1px solid #1E2A3A` bottom-only
- Row hover: `#1C2636`
- Numeric cells: IBM Plex Mono, right-aligned
- Text cells: Pretendard, left-aligned
- Active sort column: Reactor Blue icon (`#7AA7FF`), `aria-sort="ascending" | "descending"`
- Pagination region: `aria-live="polite"`

### Badges & Pills
- **Default state expression**: a semantic dot plus a short Korean state label in a row or list. Status is not a visual object to frame repeatedly.
- **Pills and badges** are exceptions for a compact, independently actionable count or a state that cannot remain readable in a dense table. They must not be used for ordinary metadata, workflow steps, or every row in a collection.
- **Count badge**: only when the number changes the next action (for example, unresolved approvals). Do not repeat it beside a visible count in the same row.
- Status dots must include `aria-label` + `title` — never color alone.

### Navigation
- Sidebar: `#1D2025` background, `1px solid #2C3036` right border
- Nav item (default): Pretendard 13px weight 510, text `#D0CFCA`, 40px row, radius `8px`
- Nav item (hover): background `#292D33` across the complete row, text `#F1F0EB`; never leave an inset top/bottom gap inside the hit area
- Nav item (active): warm neutral surface, primary text, and the Reactor Mark icon token; **no left accent rail, blue link-like label, or decorative vertical line**
- Collapsed rail: exactly 48px wide with `4px + 40px + 4px`; icon boxes are square and optically centered with identical left/right whitespace
- Group header: normal-case 12px Pretendard weight 510, `#A7AAB0`; the entire 44px row owns hover and focus states
- Nav count badge: right-aligned, mono 11px, blue-dim bg

### Navigation anti-patterns — prohibited
- Decorative vertical rails on the sidebar edge or active navigation rows
- Active-state pseudo-elements that create a line, glow, gradient, or disconnected ornament
- Decorative vertical status rails (`border-left`/`border-inline-start` at 2px or more). Use a neutral full boundary, surface change, icon, dot, or text label instead.
- Large chromatic feedback panels. Feedback containers use `--surface-feedback`; status hue is restricted to an icon, label, or quiet full-boundary token.
- Icon-only rows whose icon box is wider than the available collapsed rail
- Hover color applied to an inner child while the clickable row keeps visible top/bottom gutters
- Large empty accordion groups that hide the current task's neighboring destinations
- Pills or bordered mini-badges for ordinary group metadata when plain text is sufficient
- Different horizontal padding rules between collapsed, expanded, hover, and active states
- Mobile menu visibility must be an ephemeral overlay state, separate from the persisted desktop rail preference. Resizing from a wide window must never reveal a menu over the content without an explicit mobile-menu action.

### Unavailable capability states

- A route blocked by the connected server's capability list is an operational state, not an empty collection and not an application error.
- Show the page title, one plain-language reason, and one meaningful path forward (normally the server-status page). Do not wrap this state in a dashed empty-state card, generic illustration, nested detail panel, or a retry control that cannot change the capability result.
- The default view must not expose endpoint paths, manifest mode names, environment keys, or raw errors. Developer-only connection evidence is a closed disclosure with semantic labels and tokenized type; its body must be explicitly hidden while closed.
- Treat permission-denied and unavailable capability states separately. A missing permission must say so; a missing server capability must not imply that the operator made a mistake.

### Icon and component geometry tokens

- Product mark: `--brand-mark-header` (40px), `--brand-mark-compact` (28px), `--brand-mark-login` (56px). Reactor uses a circular containment vessel with three control rods and a curved reactor core. Mascot imagery, electron-orbit ellipses, and React-like atomic marks are prohibited.
- Icons: `--icon-size-xs` (12px), `--icon-size-sm` (16px), `--icon-size-md` (20px), `--icon-size-lg` (24px), `--icon-size-xl` (32px).
- Numeric adjustment controls pair Lucide `Minus` and `Plus` with `--control-height-compact` or `--control-height-default`, `--control-radius`, and the shared icon-size tokens. Text symbols and raw pixel geometry are prohibited so every consuming form retains the same hit area and optical balance.
- Status dots use `--status-dot-size` (8px); feature CSS must not redefine dot geometry.
- Compact operational charts use `--chart-height-compact`; asynchronous operational workspaces use `--operations-loading-min-height` for stable loading geometry.
- Two-line directory rows use `--data-row-height-comfortable`; feature CSS must not introduce a literal comfortable-row height for a single registry.
- Square icon hit areas: `--icon-box-compact` (32px), `--icon-box-default` (40px), `--icon-box-large` (48px).
- Controls: `--control-height-compact` (32px), `--control-height-default` (40px), `--control-height-spacious` (44px).
- Overlay widths: `--overlay-panel-width` (440px) for reading details and `--overlay-panel-width-wide` (560px) for timelines, trees, or structured comparisons. Both collapse to the full viewport below the shared drawer breakpoint.
- Shell widths: `--sidebar-width-collapsed` (48px) and `--sidebar-width-expanded` (248px). Collapsed navigation keeps `4px + 40px + 4px` symmetric geometry.
- Repeated navigation, toolbar, status, and action geometry must consume these tokens. Feature CSS must not introduce a literal icon size or control height unless the design system first names the new role.
- Operational health summaries lead with one overall decision and an issue count; supporting metrics use an open fact row or status list. Equal-width metric tiles and vertical separators must not substitute for priority.
- Issue severity controls filter the current queue; healthy-service counts navigate to the dedicated status workspace and must be presented as a labeled destination, not as a fourth filter chip. Expanded issues form one continuous selected row and detail surface. Do not add a second inset card, amber perimeter, or duplicate links to the same remediation route.
- Visible copy uses plain Korean for the operator's task and outcome. Unavoidable technical terms keep their canonical spelling only beside a `HelpHint`: hover/focus shows a short explanation and click opens the same explanation in a centered, keyboard-trapped dialog. The trigger is the shared `!` icon; pages must not invent local tooltip glyphs or expose transport-layer terminology as body copy.
- Configuration identities such as answer roles use their authored name as the primary identity. Do not add emoji pickers, mascot avatars, or arbitrary decorative icons when they do not encode an operational distinction.

### Modals & Popovers
- Container: `#182030` (elevated) background, `1px solid #1E2A3A`, radius `12px`
- Backdrop: `rgba(0, 0, 0, 0.7)`
- Close button: ghost icon, top-right, `24px` hit target
- Content padding: `--space-6` (24px)
- Wrap content in `<SectionErrorBoundary>` (project rule)

### Skip Link & Focus
- Skip link: `#7AA7FF` bg, `#101419` text, Pretendard 13px weight 600, radius `4px`
- Hidden off-screen by default; visible on focus
- All interactive elements: visible focus ring (`2px solid` blue with `rgb(122 167 255 / 0.46)` shadow). Never `outline: none` without a replacement.

### Empty State
- Product collections and operational queues default to a left-aligned state within the reading column. A centered state is reserved for a genuinely full-canvas absence, never as filler inside a panel.
- Operational queues may use a compact left-aligned empty state beneath the queue heading. When the collection is empty, suppress zero-result filters, duplicate healthy/attention panels, and unrelated cross-workflow CTAs.
- Empty collection pages expose exactly one creation action. Keep it in the empty state; move it to the page header only after records exist. Do not repeat the zero count in StatCards, and place sample content in an optional disclosure instead of a permanently visible example panel.
- Master/detail pages do not render a separate detail placeholder while the master collection is empty. Introduce the split layout only after records exist, and render the detail pane only after an explicit selection.
- Optional `actionLabel` + `onAction` renders a `btn-secondary` CTA below the description
- Optional `example` slot renders a sample preview panel — `padding: var(--space-4)`, `background: var(--surface-2-alpha)`, `border: 1px dashed var(--border-subtle)`, `border-radius: var(--radius)`, `max-width: 480px`
- Use IBM Plex Mono inside the example panel for any code, cron expressions, regex patterns, or template skeletons (per §3 Typography)
- Optional `helpHref` + `helpLabel` renders a small dim text-link ("도움말 보기 →") opened in a new tab with `rel="noopener noreferrer"`
- Use the example slot on high-traffic empty pages (personas, safety rules, scheduler, prompt studio, reactor universe) to teach the expected shape of the data

### Readiness Summaries
- A healthy readiness result is one semantic status sentence plus only the scalar facts needed for scanning. Do not surround `PASS` with a badge, four stat cards, and a second readiness container.
- Render detailed readiness checks as a disclosure only when the aggregate is `WARN` or `FAIL`; keep remediation visible inside that disclosure and preserve the underlying typed checks for tests and accessibility.

### Responsive master/detail tables
- Opening a detail pane must not squeeze the unchanged desktop table until labels wrap one character per line. While a side detail is open, the master table keeps only the columns needed to identify and select a record; the detail pane owns identifiers, actors, targets, and secondary status facts.
- At mobile width, keep at most two identifying columns beside the shared row-details control. Move timestamps and secondary metadata into the accessible responsive expansion and the selected detail section.
- Mobile row-action menu cells may be suppressed when the complete action set remains available from the selected detail. Hidden data must remain reachable through the row-details control and must not disappear from the accessibility tree.
- Selected rows use a surface change. Do not add decorative left rails, bottom accent lines, or full-row outline boxes as persistent selection decoration.
- Service relationships are secondary context: default to a readable list and expose a static map only when it helps orientation. Do not use simulated physics, dragging, pulsing, orbiting, glowing, or flowing edges to encode status; the queue, semantic dot, and localized status text carry priority.

### Technical execution records
- Translate transport and observability terms into the operator's task language. Prefer `실행 기록`, `처리 단계`, `기록 번호`, and `느린 실행 기준`; keep canonical trace/span/P95 wording inside a shared `HelpHint` or raw-detail disclosure when it is still needed.
- A processing tree that already shows hierarchy, start position, duration, and result must not be followed by a second timeline containing the same rows. Add another visualization only when it answers a different operational question.
- Tree leaves use spacing, not disabled punctuation buttons. Expandable branches use the shared icon library and icon-size tokens; text glyphs such as `·`, `▸`, and `▾` are not product icons.
- Repeated healthy outcomes use a semantic dot plus text in dense tables. Reserve bordered status badges for states that require stronger attention or action.

### Prompt authoring workspace

- Prompt Studio is one linear operator workflow: choose an instruction set, review its basic information, edit or apply content, compare a proposed change, then inspect the change history. These tasks use one URL-addressable tab set; do not stack simultaneous collapsible panels for each task.
- `/prompts` is named `답변 지침`. Its collection shows only the name, purpose, and recent update; selecting a row opens the operational detail where editing, deletion, version changes, and technical identifiers live. Do not expose a delete button in every row or a release-flow backlink in this local workflow.
- The collection selection surface uses a neutral row change and an accessible selected state, never an amber rail, bordered card, or browser-default link treatment. The detail workspace is not rendered until the operator selects a template.
- Version and experiment states are operator language at the view boundary (`현재 사용 중`, `검토 전`, `이전 기록`, `진행 중`, `완료`, `중단됨`). Raw enums such as `ACTIVE`, `COMPLETED`, and confidence codes such as `HIGH` must not appear in the primary interface.
- Version history and comparison results are flat divided rows. Do not use one card per version, a winner trophy emoji, status pills on every row, or equal card grids for comparison metrics. A recommendation may use the shared icon library and one concise reason.
- Technical IDs belong in a closed `개발자용 프롬프트 정보` disclosure. Prompt content remains readable body text; monospace is reserved for authored code-like content or identifiers inside technical detail.
- A list or detail request failure uses one fail-closed recovery surface with retry and a closed technical reason. A raw transport error never becomes the primary toast, alert, or form-validation sentence.
- At narrow widths, master and detail stack in document order, controls keep the shared minimum hit area, and the task tabs may scroll horizontally without creating page-level overflow.

### Response quality comparison workspace

- The workspace answers one decision: which response approach should an operator keep or improve. Its list contains only comparison name, human status, approach count, and created time; response-template identifiers, version IDs, authors, raw report payloads, and runtime errors belong in the selected detail's closed developer disclosure.
- Experiment actions (start, stop, activate recommendation, delete) belong only in the selected detail. Do not repeat a delete action in every table row or link a comparison task directly into release navigation.
- Render comparison outcomes as localized semantic dots (`실행 대기`, `비교 중`, `결과 확인 가능`, `결과 확인 필요`, `중단됨`). Trials and version results are one divided list each, never status badges, metric-card grids, or unlabelled JSON blocks.
- Feedback analysis begins with four open facts and a divided list of repeated issues. Example inputs and raw job metadata remain in closed developer disclosures. At narrow widths each comparison row stacks its secondary measures below the approach identity.

### Answer role workspace

- The role list is a two-column selecting surface. Editing and deletion live only in the selected role detail; bulk activation remains a separate collection action. Do not repeat edit and delete controls in every row.
- Before a role is selected, a short role list stays within `--collection-compact-width` and explains that selection opens the operational detail. It must not stretch a two-column collection into an empty full-workspace table.
- A role detail opens with name and active state, then compact facts and readable role instructions. Internal role IDs and linked instruction IDs are closed developer information. If the detail cannot load, retain the role list and show a recoverable right-side state instead of an empty panel.
- The test conversation uses shared line icons for the assistant, operator, and tool activity. Emoji avatars, raw tool names, and transport errors are prohibited in the primary conversation; tool names and raw errors are closed developer information.

### Scheduled operations workspace

- The default scheduled-operations view answers three questions in order: is unattended execution trustworthy, which job needs intervention, and what jobs are configured. Do not place a fully expanded readiness checklist before the intervention queue and job list.
- Overall health is one semantic dot and sentence with a compact fact row. The evidence behind that decision is a closed disclosure. Repeated `PASS`, `WARN`, and `FAIL` badges or one card per check are prohibited.
- Job tables translate schedule rules into operator language such as `매일 09:00`, `6시간마다`, or `매주 월요일 08:00`. The canonical schedule expression belongs in a labeled developer disclosure, not the primary list column.
- Job lifecycle and last-run outcomes use a semantic dot plus localized text. Raw states such as `ENABLED`, `DISABLED`, `SUCCESS`, `FAILED`, or `RUNNING` must not appear in the operator path.
- The create/edit drawer uses the wide overlay role. Name, work type, schedule, and the work instruction are the primary path; runtime overrides and failure/notification settings are closed optional sections.
- Save review shows only blocking items by default. Non-blocking recommendations live in one disclosure; never render six validation cards beneath an already long form.
- Technical terms such as the schedule expression use the shared `HelpHint`: hover/focus explains the term and click opens the same explanation. Mobile retains the human schedule and job identity while secondary facts and actions move to the shared row expander.
- A selected job is the sole place for job mutation controls. The table remains an identifying, selectable list; never repeat edit, run, and delete buttons in every row.
- Job and execution detail lead with a compact open fact row and a plain-language outcome. Identifiers, schedule code, AI instructions, model and tool configuration, raw outputs, and connection messages belong in one closed `개발자용` disclosure. A failed history refresh shows a Korean recovery sentence first; the raw failure stays in that disclosure.
- A first scheduler-list failure replaces both the job and execution-history task surfaces with one recovery state; it never becomes a disabled selector or an empty collection. A later failed refresh retains only the verified list under one neutral revalidation row, not a colored alert. At the shared list-detail breakpoint, selecting a job or execution scrolls the stacked detail into view.

### Failed-request recovery workspace

- Recovery is a two-step handoff: select one failed request, then review the saved input before opening a separate response test. Selection and review use one master/detail workspace, not cards for error, prompt, model, tool, and action.
- Selected records are URL-addressable through the `capture` query parameter so refresh, handoff, and back/forward navigation preserve operator context.
- The primary list shows capture time, a safe input excerpt, and a localized failure reason. Raw error codes, capture IDs, anonymous hashes, model identifiers, tool identifiers, and original transport messages stay inside a closed developer disclosure.
- Opening a response test only prefills the input and must say explicitly that no model call runs automatically. A disabled recovery action uses visible explanatory text; do not rely on a native `title` tooltip.
- Use operator language such as `모델 응답 시간 초과` and `안전 정책에 따라 차단`. Avoid `MODEL_TIMEOUT`, `GUARD_BLOCKED`, circuit-breaker jargon, or the generic word `프롬프트` when `당시 입력` describes the task more clearly.
- At narrow widths, the request list precedes the selected review in document order. Limit the visible capture window, keep row excerpts truncated, and preserve zero page-level overflow; do not hide the selected review behind a side drawer.

### Diagnostic data delivery workspace

- Direct diagnostic ingestion is an expert operation with production side effects. The default order is choose a record type, review and validate the source data, explicitly confirm it is sample-only data, then send and review the result.
- Source JSON may remain visible because it is the authored input for this developer tool, but it must use the tokenized textarea, a shared `HelpHint`, live syntax/shape validation, and an accessible status message. Never wait until a side-effecting submit to reveal malformed JSON.
- A valid payload is not sufficient authorization to send. Keep the primary action disabled until the operator explicitly confirms the payload contains no real service information; changing the type, editing the payload, or restoring the sample clears that confirmation.
- The payload editor is an open divided section, not a nested panel. API paths, permission contracts, and raw responses stay inside closed developer disclosures.
- Success shows a human result sentence and only allowlisted scalar facts. Raw response objects remain closed. Failures use the shared resolved error language and never imply that data was recorded.
- Use `1단계`, `2단계` task labels rather than punctuation-led step ornaments. At narrow widths, controls and confirmation stack in document order and preserve zero page-level overflow.

### Breadcrumb
- Component: `Breadcrumb` from `shared/ui/Breadcrumb.tsx`. Always reuse instead of hand-rolling `<div className="breadcrumb">` chains.
- Structure: `<nav aria-label="breadcrumb">` ▸ `<ol class="breadcrumb__list">` ▸ `<li class="breadcrumb__item">` per segment. Items are `BreadcrumbItem[]` with `{ label, href?, mono? }`.
- Separator: default `/` (`.breadcrumb__separator`, `--text-dim`, `aria-hidden="true"`). Override with the `separator` prop (e.g. `›`).
- Current page: the last item — and any item whose `href` is omitted — renders as a `<span>` with `aria-current="page"`. Weight 510 (`--font-weight-emphasis`), color `--text-primary`.
- Ancestor segments: rendered as `<Link>` with weight 400, color `--text-muted`. Hover / focus-visible promotes to `--accent` (#7AA7FF); focus-visible adds a 2px blue outline. Transition is gated by `prefers-reduced-motion`.
- Mono slugs: pass `{ mono: true }` for ID / hash labels (session ID, job name, user ID). Renders in IBM Plex Mono with neutral letter-spacing — keeps slugs visually distinct from sentence labels (per §3 Typography "monospace for IDs").
- Truncation: any label longer than 32 chars receives `.breadcrumb__label--truncate` (max-width 32ch + ellipsis) and a native `title` tooltip with the full text. Prevents long resource IDs from breaking the page header rhythm.
- Spacing: `font-size: var(--text-sm)`, `gap: var(--space-2)` between segments, `margin-bottom: var(--space-5)` so following content stays on the 8px rhythm.

### Tooltip
- Component: `Tooltip` from `shared/ui/Tooltip.tsx`. Always reuse for short hover/focus hints — never reach for the native `title` attribute (poor styling, no keyboard support, no portal escape).
- API: `<Tooltip content={...} placement={...} delay={...} disabled={...}>{trigger}</Tooltip>`. Single child trigger only; the component clones it to inject refs, focus/hover handlers, and `aria-describedby`.
- Placement: `top` (default) | `right` | `bottom` | `left`. The floating panel is portalled to `document.body`, escapes `overflow:hidden` / `transform` parents, and clamps to the viewport with an 8px gutter so it never overflows.
- Delay: `200ms` default before opening on hover/focus. Set `delay={0}` for tight feedback (sort headers, resize handles); raise it for less-critical hints. No close delay — leave / blur hides immediately so the panel never lingers in front of the cursor.
- Style tokens (Stage H baseline):
  - Surface: `var(--bg-elevated)` + `1px solid var(--border-standard)` (matches popover stack — see Modals & Popovers above)
  - Padding: `var(--space-2) var(--space-3)` (8 × 12 px)
  - Radius: `var(--radius)` (6 px)
  - Typography: `12px / weight 510 / Pretendard Variable` — single-step smaller than body text so the tip reads as a footnote
  - Max-width: `240px`, `word-break: keep-all` so Korean labels never break mid-word
  - Shadow: `0 2px 8px rgba(0, 0, 0, 0.4)` — the only place we cast a real shadow. The contrast against the surface stack (which usually has none) signals "this is floating chrome, not a depth step".
  - Arrow: `8 × 8px` rotated diamond inheriting the surface + border tokens, anchored to the side opposite the placement keyword.
  - Z-index: `300` — above modals (`200`) so tooltips inside dialogs still float on top.
- Accessibility:
  - Renders `role="tooltip"` with a stable `useId()` value; the trigger receives `aria-describedby={tooltipId}` only while open. Existing `aria-describedby` on the trigger (e.g. form error messages) is preserved and concatenated, never overwritten.
  - Tab focus opens the tooltip; blur closes it. Hover-only triggers (decorative pills, status dots) still surface the description for screen readers via the trigger's existing `aria-label` because the panel itself is not focusable.
  - `Escape` closes the tooltip without bubbling further — local listener so it does not interfere with parent overlays sharing the same key.
  - Honours `prefers-reduced-motion: reduce` (CSS `@media`): the 120ms fade-in is dropped, and the tooltip appears in place.
- Mobile / coarse pointer (`@media (hover: none)`): hover does not fire, so a single tap on the trigger toggles the tooltip open. A second tap (or any interaction outside the trigger) closes it. This is the only departure from the desktop hover/focus model.
- Migration sites (Stage H): `DataTable` sortable headers (`정렬 변경`), `DataTable` column resize handles (`드래그해서 너비 조절`), `StatusBadge` icon-only variant (full status name), `OperationButton` `disabledReason` prop (caller-supplied reason when the action is unavailable). Disabled-button caveat: modern Chromium / WebKit / Gecko fire `mouseenter` on disabled `<button>` elements, so the wrapper-based pattern surfaces the reason on hover; focus does not arrive on a disabled button, so screen-reader users should still get an `aria-label` or visible inline note for parity.

## 5. Layout Principles

### Spacing System (4px grid)
- Base unit: 4px
- Scale: `--space-1` 4px, `--space-2` 8px, `--space-3` 12px, `--space-4` 16px, `--space-5` 20px, `--space-6` 24px, `--space-7` 28px, `--space-8` 32px, `--space-10` 40px, `--space-12` 48px
- Primary rhythm: 8px / 16px / 24px / 32px — multiples of 8 for structural gaps, 4 / 12 for micro-adjustments
- `--content-pad` = 24px (page gutter), `--panel-pad` = 20px (card interior), `--section-gap` = 16px (between stacked sections)

### Chrome Heights
- `--header-height`: 60px
- `--footer-height`: 34px
- Sidebar width: 240px expanded / 60px collapsed (icon-only)

### Grid & Container
- Admin pages use full viewport width — no marketing-style max-width containers
- Page headers keep title, description, and ordinary actions on one row while the content viewport is wider than 960px. Stack only at `<=960px`; do not create an empty action row at laptop widths.
- Stat card grids: `repeat(auto-fill, minmax(240px, 1fr))`, gap 16px
- Dashboard panels: 2-column (`1fr 1fr`) desktop, collapse to single column at <1024px
- Tables: full width of their containing panel, horizontal scroll on overflow (never squeeze)
- Actionable queues and prioritized rows precede relationship graphs or decorative system maps. Keep topology and other spatial diagnostics as an explicit secondary disclosure unless spatial navigation is the page's primary task.

### Border Radius Scale
- `--radius-sm` 4px — buttons, inputs, small controls
- `--radius` 6px — ambient default
- `--radius-md` 8px — cards, dropdowns
- `--radius-lg` 12px — modals, featured panels
- `--radius-full` 9999px — pills, chips, status dots

### Whitespace Philosophy
- **Darkness is space** (inherited from Linear). The root canvas is the ambient whitespace — no need for light dividers or generous margins to signal separation.
- **Readable density is the admin virtue**: Reactor pages prioritize scan speed, not maximum item count. Use rows, tables, and disclosure to keep primary decisions visible without compressing prose or surrounding every value with a card.
- **Policy editors use one navigation hierarchy at a time**: on desktop, policy families may use a compact vertical local navigation while editor modes remain horizontal; at ≤800px the family navigation becomes horizontally scrollable. Never stack two full-width tab bars when one is only a scope selector.
- **Ordered pipelines are divided rows, not diagrams**: show an explicit ordinal, human label, description, and one state control. Connector ornaments, raised stage cards, raw implementation keys, and always-visible class/type metadata are forbidden; technical metadata belongs in disclosure.
- **Release decisions fail close in the presentation layer**: a passed aggregate must still render as conditional when warning review remains required. The first viewport shows one effective decision, one human next action, and compact release facts; raw commands, report inventories, dependency details, and local verification scripts belong in explicit disclosures.
- **Release workflow ownership is singular**: the LNB owns the canonical stage inventory. A release scope or capability view may show its ordered gates, but must not repeat the complete workflow navigation beneath it.
- **Release evidence starts as an index**: default to flat status disclosures that name each evidence family and its state. Raw IDs, JSON, commands, SDK contracts, and verbose report fields appear only after an explicit open action.
- **Live smoke separates action from evidence**: external side-effect operations use one flat action row per target with the effect stated before the button. Slack, A2A, and provider contracts are collapsed status rows; expanded evidence uses at most two comparison columns on desktop and one on mobile, while remediation continues the same surface instead of creating a nested alert card.
- **Provider registry owns model selection, not release navigation**: the registry table and model drawer expose model identity, provider, pricing, capability, and alert context. Release-stage navigation stays in the page header/LNB; provider smoke shows one configured-target action row and one evidence disclosure, never a repeated three-step workflow grid.
- **Today is an action queue, not an unlabeled dashboard**: the root route has one visible `h1`, one purpose sentence, and contextual analysis utilities in the header. When attention items exist they precede release and status summaries; healthy summaries never push urgent work below the first operational decision.
- **Monitoring views normalize before they visualize**: API adapters reconcile supported backend response shapes and reject malformed identifiers or non-finite numbers before rendering. Missing latency/count data appears as a safe numeric zero or explicit empty state—never `NaN`, raw translation keys, or an invented success state.
- **Backend state is the UI contract, not fixture history**: before designing an operational surface, compare the live response with the backend route/schema. Preserve every operator-relevant field the backend actually emits, classify mismatches as backend, admin, or shared-contract defects, and render transport failure separately from a valid empty result. Delete adapters, components, styles, translations, and fixture-only fields once their owning contract is removed.
- **Session activity is an operational ledger**: the session feed exposes the backend-owned session, user, status, channel, thread, trace, and update-time fields in a single scan path. The user index exposes only backend-owned session count, last activity, and last session. Never add filter, sort, trust, message-count, persona, or feedback controls until the corresponding API accepts and applies those parameters; a client-side approximation over one paginated response is forbidden.
- **Session snapshots distinguish first failure from later revalidation**: an initial overview, session-feed, user-index, or user-session request failure replaces that task surface and its local controls with one `WorkspaceUnavailable` state. If a later refresh fails after a verified response, retain only that verified data beneath one neutral revalidation row; never replace it with a false empty collection or a second error panel.
- **Operational recovery lists lead with a short priority set**: show at most three actionable rows in the initial view. Keep the complete list behind one explicit “show all” control, and place endpoint paths, manifest state, and step-by-step technical guidance inside collapsed details. Never let an implementation-level diagnostic list dominate the first viewport.
- **Session detail explains the real run**: the first detail surface uses the current backend run contract—status, channel, timestamps, thread, trace, graph, profile, provider, model, lifecycle gates, token usage, and messages. Never derive duration, trust, persona, message count, cost, or timestamps from absent fixture-era fields. Runtime metadata is allowlisted into human labels; raw metadata objects stay out of the primary UI. Detail pages use one linear content flow and one visible heading, not a side mini-map beside short sections.
- **Audit history is a server-owned ledger**: category/action filters and offset pagination go directly to the audit API. Do not fetch a large snapshot and present client-only risk filters, readiness totals, or resource bundles as complete operational truth. The primary surface is one change table; humanized category/action labels replace raw enums, and raw detail is available only in a collapsed technical disclosure after a row is selected. Release navigation remains in the LNB instead of being repeated inside audit readiness cards.
- **Audit rows are for scanning, selected detail is for action**: a normal audit row uses compact human labels, a shortened stable resource reference, and semantic dot text for recovery state. Copy and rollback actions belong only in the selected detail; row action menus, status badges, raw field keys, and canonical resource identifiers do not compete in the ledger.
- **Audit detail preserves the selection flow on narrow screens**: below the list-detail breakpoint, selecting a ledger row scrolls the stacked detail into view. The selected record remains visible as context, but operators must never have to discover the recovery action below a full page of rows.
- **Analysis has one scope selector**: latency, conversation quality, and tool performance are sibling URL-addressable views under one tab bar. Never nest a second full-width tab bar inside an already selected analysis segment. A transport failure is a retryable error state; zero collected samples are an intentional empty state.
- **Monitoring drawers stay linear**: a narrow trace/session drawer uses one full-width summary → structure → timeline → selected-detail flow. Do not place a mini-map beside three short sections or wrap every section in another card; preserve full IDs in accessible metadata while displaying compact operator IDs.
- **Issue details answer the operator's next question**: lead with `현재 상황` and `해결 화면`. Backend evidence is secondary and remains collapsed under `기술 정보 보기`; primary copy never asks non-engineering operators to interpret the evidence contract directly.
- **Issue queues use one compact decision rail**: severity controls are compact filters, not equal-width metric tiles; a healthy-service count names its status destination. A selected issue remains one continuous row and detail surface with one primary resolution link. Do not repeat a remediation route, frame the detail in an inset card, or use warning color as a perimeter or separator.
- **Issue snapshots fail closed**: when the current diagnostic snapshot cannot load, replace the queue, severity totals, health destination, topology, and header refresh action with one `WorkspaceUnavailable` recovery state. Never retain a warning banner, raw transport message, guessed healthy count, or success toast that merely started a retry.
- **Platform status snapshots fail closed**: when both diagnostics and platform signals are unavailable, replace the complete status workspace and header refresh action with one `WorkspaceUnavailable` recovery state. Preserve neither a generic empty-state illustration nor a placeholder normal or outage decision; technical transport detail remains closed.
- **Execution record snapshots fail closed**: when the first trace request fails, replace filters, summary totals, table, and drawer with one `WorkspaceUnavailable` recovery state. A later refresh error may retain previously verified records only with one neutral revalidation row and no raw transport message. Never log a valid long-tail duration distribution as an application error during render.
- **Audit snapshots fail closed**: when the first audit request fails, replace sync counts, filters, ledger, and selected inspector with one `WorkspaceUnavailable` recovery state. A later filter or refresh error may retain the last verified ledger only with one neutral revalidation row. Shared refresh controls never claim success merely because a new request started.
- **Disclosure selectors name their element**: collapsed-content CSS must target `details.<class>:not([open])`; never attach the same hidden-content rule to a shared class that can also appear on a `div` or other always-visible container.
- **Creation forms reveal complexity in task order**: first show the name and the minimum instructions required to create a valid object. Optional notes, greetings, shared-template links, and lifecycle switches stay in one clearly labeled disclosure. A valid empty collection and a failed fetch are mutually exclusive states; never show onboarding guidance beneath a transport error.
- **Section isolation**: panels separate via background + border, not margin. Inter-section gap is `--section-gap` (16px) — smaller than marketing norms.

## 6. Depth & Elevation

| Level | Treatment | Use |
|-------|-----------|-----|
| Flat (L0) | `#101419` bg, no shadow, no border | Page background / canvas |
| Surface (L1) | `#171C23` bg + `1px solid #2A323D` | Cards, sidebar, header, default panels |
| Surface Raised (L1b) | `#202731` bg + `1px solid #2A323D` | Active / selected card, emphasized panel |
| Elevated (L2) | `#28313D` bg + `1px solid #2A323D` | Popovers, dropdowns, tooltips |
| Modal (L3) | `#28313D` bg + `1px solid #2A323D` + `rgba(0,0,0,0.7)` backdrop | Dialogs, command palette |
| Focus | `box-shadow: 0 0 0 2px rgb(122 167 255 / 0.46)` + border shift to `#7AA7FF` | Keyboard focus on any interactive element |
| Hover | Background shift (surface → `#252E3A`) | Rows, cards, nav items |
| Active (press) | `transform: translateY(0)` from hover's `translateY(-1px)`, shadow compresses | Primary buttons only |

**Shadow Philosophy (inherited from Linear):** drop shadows on dark surfaces are nearly invisible and create visual noise. Reactor communicates elevation through background luminance stepping (`#101419` → `#171C23` → `#202731` → `#28313D`) and structural borders, not through cast shadows. The only exceptions are (1) the primary button's subtle blue focus signal `0 1px 3px rgb(122 167 255 / 0.25)` — which is a brand signal, not a depth signal — and (2) the modal backdrop overlay.

### Elevation Shadows (H-8)

Floating overlay surfaces that escape the canvas (tooltips, dropdowns, drawers, modals) need a faint cast shadow so the edge stays legible against an arbitrary background. Use these tokens — never raw `rgba(0,0,0, …)` — so the scale stays consistent.

| Token | Value | Usage |
|---|---|---|
| `--shadow-sm` | `0 2px 8px rgba(0, 0, 0, 0.4)` | Tooltip, chart tooltip, small popover, react-flow controls |
| `--shadow-md` | `0 8px 24px rgba(0, 0, 0, 0.4)` | Dropdown, context menu, hovering panel, mini-map |
| `--shadow-lg` | `0 24px 48px rgba(0, 0, 0, 0.4)` | Modal, command palette, full-screen overlay, onboarding tour |

### Z-Index Tier (Stage N N-10)

7-tier stack to keep overlapping surfaces consistent. Use these tokens — never a raw integer — so future siblings slot into the right band without z-index wars.

| Token | Value | Usage |
|---|---|---|
| `--z-base` | `1` | Local stacking baseline (default flow) |
| `--z-sticky` | `100` | Sticky headers, sidenav rail, footer |
| `--z-dropdown` | `200` | Menu / select / filter popovers anchored to triggers |
| `--z-overlay` | `1000` | Drawer backdrops, generic full-bleed overlays |
| `--z-modal` | `1100` | Modal dialogs + their backdrops |
| `--z-popover` | `1200` | Tooltips and context menus that must float above modals |
| `--z-toast` | `9999` | Toasts, network banners, skip-link reveal — top of viewport |

Brand-tinted glows continue to use the accent-prefixed family (`--accent-shadow`, `--accent-shadow-sm`) — do not mix elevation shadows with accent glows. Decorative status-dot halos and slider-thumb micro-shadows stay raw because they are colour signals, not elevation.

## 7. Do's and Don'ts

### Do
- Use Pretendard Variable with `ss01` where the rendering path supports it — consistent with Linear's stylistic-set philosophy
- Use **weight 510** as the default UI emphasis weight — labels, nav, buttons, table headers
- Use IBM Plex Mono **only** for numeric values, IDs, timestamps, codes, tokens
- Build on the 3-level surface stack: `#101419` root → `#171C23` surface → `#202731` elevated
- Use `#F1F5F9` for primary text — never pure `#FFFFFF`, which is harsh on the dark canvas
- Reserve **Reactor Blue** (`#7AA7FF` / `#99BBFF`) for CTAs, active states, focus rings — never decorative
- Use cool graphite borders (`#2A323D`, `#3A4553`) — they read as structural on the dark canvas
- Use status colors **only** for status — green for healthy, red for error, yellow for warn, blue for info
- Communicate elevation through background luminance, not drop shadows
- Include visible focus rings on every interactive element (blue, 2px)
- Pair every color-coded status with a text label or `aria-label` (never color alone)
- Reuse `--space-*`, `--radius-*`, `--text-*` tokens — never hardcode values in component CSS
- Use `<SectionErrorBoundary>` around every page and large modal

### Don't
- Don't use pure white (`#FFFFFF`) for text — `#F1F5F9` is the ceiling
- Don't use solid colored backgrounds for secondary buttons — surface + border is the system
- Don't apply Reactor Blue decoratively (no blue borders on non-interactive cards, no blue dividers)
- Don't use Pretendard weights above 600 — 510 emphasizes, 600 announces, higher is shouting
- Don't use IBM Plex Mono for prose, headings, or button labels — it is strictly a data font
- Don't UPPERCASE headings, buttons, or body — uppercase is reserved for table headers, labels, micro-captions
- Don't use drop shadows for elevation on dark — step the background instead
- Don't introduce a second selection color — Reactor Blue is the only chrome accent; semantic colors communicate state, not navigation
- Don't use terminal / sci-fi flourishes: ASCII art, `>` prompt decorations, `:: DELIMITED ::` section headers, or monospace page titles.
- Don't use gradient / neon styling anywhere — it reads as "AI tool" and violates Quiet Authority direction
- Don't rely on color alone for status — always pair with text or `aria-label`
- Don't suppress focus rings with `outline: none` unless replaced with a visible equivalent
- Don't call `dangerouslySetInnerHTML` — a security rule, not just a style rule
- Don't hardcode hex colors in component CSS — reference tokens
- Don't turn scalar values into a grid of equal cards by default. Use a compact summary row or table metadata; reserve cards for independent objects.
- Don't animate or lift non-interactive cards on hover. A hover response promises an action and is reserved for clickable rows or controls.
- Don't force operator labels to uppercase in component code. Preserve authored casing; uppercase is an explicit table-header or micro-caption style only.
- Don't make empty states fill the viewport. A shared empty state is compact, names what is absent, and offers at most one primary recovery or creation action.
- Don't expose class names, camelCase/snake_case configuration keys, backend type strings, or untranslated backend descriptions as the primary label. Humanize/localize them and keep the original identifier in an optional technical disclosure.
- Don't echo backend-authored English remediation sentences or full shell pipelines into the primary decision surface. Present a localized operator action and preserve the exact source value only where copying or audit traceability requires it.

## 8. Responsive Behavior

Admin UI is **desktop-led and fully adaptive**. The typical operator workstation is ≥1440px, while tablet and mobile remain required operating surfaces for on-call inspection and safe, scoped changes. Every route milestone must define and verify its desktop, tablet, and mobile behavior; unavailable browser emulation is recorded as missing evidence, never as an exemption.

### Breakpoints
| Name | Width | Key Changes |
|------|-------|-------------|
| Mobile | <768px | Sidebar collapses to drawer; single-column layouts; local navigation scrolls horizontally; row metadata stacks without horizontal page overflow |
| Tablet | 768–1024px | Sidebar icon-only by default; 2-column panel grids collapse to single column |
| Desktop Small | 1024–1440px | Full sidebar, 2-column dashboard grids, standard table density |
| Desktop | 1440–1920px | Primary target — full layout |
| Desktop Large | >1920px | Constrain data tables at ~1600px max-width for readability; fill excess with padding, not with stretched content |

### Touch Targets
- Minimum `40 × 40px` hit area on interactive elements (buttons, nav, icons)
- Form controls with `padding: 0.5rem 0.78rem` meet this at the root-14px scale
- Icon buttons in toolbars may be smaller (32px) only when they share a toolbar context with larger anchors

### Collapsing Strategy
- Sidebar: expanded (240px) → icon-only (60px) at <1024px → drawer at <768px
- Stat card grids: 4-col → 2-col at <1024px → 1-col at <768px
- Dashboard 2-column panels: side-by-side → stacked at <1024px
- Tables: horizontal scroll within panel — never visually squeeze columns

### Data Visualization
- Charts maintain aspect ratio; legends collapse from side to below at <1024px
- Sparklines (inline in table cells) never drop below 80px width
- Time-series charts must display most-recent-on-right (audit doc flags `/usage` as a known violation of this rule — this DESIGN.md formalizes the convention)

## 9. Agent Prompt Guide

### Quick Color Reference
- Primary CTA: Reactor Blue (`#7AA7FF`), hover (`#99BBFF`)
- Page background: Root (`#101419`)
- Surface (cards, panels, sidebar, header): `#171C23`
- Elevated (popovers, modals, dropdowns): `#28313D`
- Hover surface: `#252E3A`
- Heading text: Primary (`#F1F5F9`)
- Body text: Secondary (`#CBD5E1`)
- Muted text: Muted (`#94A3B8`)
- Dim / hint text: Dim (`#8899AC`)
- Border default: `#1E2A3A`
- Border emphasized: `#2A3A4E`
- Focus ring: `rgb(122 167 255 / 0.46)`, 2px
- Status: green `#5EBA8D`, amber `#D6A451`, red `#E07C7C`, blue `#8CB8FF`

### Quick Typography Reference
- UI font: `'Pretendard Variable'`, fallback system sans
- Data font: `'IBM Plex Mono'`, fallback monospace
- Weights: 400 (read), **510 (UI signature)**, 600 (announce)
- Root size: 14px (`html { font-size: 14px }`)
- Stat numeric: `--text-data` (28px), mono, weight 500
- Body: `--text-sm` (13px), Pretendard
- Label: `--text-xs` (13px) or `--text-xxs` (12px) for secondary metadata only; preserve authored casing

### Example Component Prompts
- "Create a compact metric summary only when the value supports an operator decision. Preserve the authored label casing, use IBM Plex Mono for the value, and place related metrics in one segmented summary row. Use a card only when the metric is independently actionable; non-interactive metrics have no hover lift or shadow."
- "Design a primary button. Background `#7AA7FF`, text `#101419`, 12px Pretendard weight 600, radius 4px, padding 0.5rem 0.92rem, shadow `0 1px 3px rgb(122 167 255 / 0.25)`. Hover: background `#99BBFF`, translateY(-1px), shadow strengthens to `rgb(122 167 255 / 0.46)`. Disabled: opacity 0.4, cursor not-allowed. Must include `disabled={isSubmitting}` per project rule."
- "Build a data table. Header row `#111820` bg with UPPERCASE 11px Pretendard weight 600 color `#94A3B8`, `scope='col'` and `aria-sort` on sortable columns. Body row: 13px Pretendard weight 400 text cells, IBM Plex Mono weight 400 for numeric cells (right-aligned), `1px solid #1E2A3A` bottom border. Row hover: `#1C2636`. Pagination region `aria-live='polite'`."
- "Create a sidebar nav item whose full row is the hit and hover area. Use symmetric horizontal padding and a quiet background shift for hover/active state. Never add a left accent rail or decorative vertical line; the collapsed icon remains optically centered with equal side space."
- "Design a status pill for service health. Use `--green-tint` background + `--green-border` 1px border + `#34D399` text + 11px Pretendard weight 510, radius 9999px, padding 2px 8px. Include leading 6px dot and `aria-label='Service healthy'`. Never use color alone — pair with 'Healthy' text."
- "Build a modal. Container `#182030` bg, `1px solid #1E2A3A`, radius 12px, padding 24px. Backdrop `rgba(0, 0, 0, 0.7)`. Title 18px Pretendard weight 600 `#F1F5F9`. Close icon top-right, ghost button, 24px hit target. Wrap content in `<SectionErrorBoundary>`. Primary action bottom-right uses primary button spec; secondary (Cancel) uses secondary spec, left of primary."

### Iteration Guide
1. Always specify `font-weight: 510` for UI text (labels, nav, buttons) unless deliberately reading (400) or announcing (600)
2. Always use IBM Plex Mono for numeric values, IDs, tokens, timestamps — never for prose
3. Always reference CSS variables (`var(--bg-surface)`, `var(--text-primary)`) — never hardcode hex
4. The 3-level surface stack (`#101419` → `#171C23` → `#202731`) replaces shadow-based elevation — always step the background, never cast a shadow
5. Reactor Blue is the only chromatic accent for chrome — status colors express state, not navigation
6. Every interactive element needs a visible focus ring (blue, 2px) — do not suppress it
7. UPPERCASE is reserved for table headers, labels, and micro-captions — never headings, buttons, or body
8. Every page wraps in `<SectionErrorBoundary name="page-name">` (project rule)
9. All user-facing strings use `t('key')` — both `en.json` and `ko.json` updated in the same change (project rule)
10. All list API calls include `searchParams: { limit: 200 }` (project rule)

---

## Audit Reference

This DESIGN.md codifies the correct end-state and is the authoritative reference for correcting known deviations. Notable items it explicitly addresses:

- **`/traces` terminal-cosplay header** (`> TRACE :: 실행 트레이스` + `// ...` comment) — violates §1 Quiet Authority and §7 "no terminal cosplay" rule. Must become a standard page heading + description.
- **Date / numeric formatting inconsistency across pages** — §3 requires IBM Plex Mono for all numerics and timestamps; a shared `formatters` utility should enforce `YYYY-MM-DD HH:mm` mono rendering.
- **Raw JSON dumps on `/health` and `/tenants`** — resolved: both routes now map backend contracts into named diagnostics, metrics, comparison lists, progress indicators, and tables without exposing transport keys.
- **`/usage` time-series chart with reversed X-axis** — violates §8 Data Visualization convention (most-recent-on-right).
- **Inconsistent empty-state treatments across pages** — §4 and the shared `EmptyState` component define the single correct pattern.
- **Mixed border treatments (semi-transparent white vs solid slate)** — §2 and §7 mandate solid slate (`#1E2A3A`) borders; any `rgba(255,255,255,*)` borders are legacy and should migrate.

This DESIGN.md is the reference spec. The audit doc is the migration backlog.

## 10. Semantic Color Tokens (F-9)

Intent-based opt-in tokens layered on top of the existing palette in `src/index.css`.
Existing palette tokens (`--green`, `--yellow`, `--red`, `--blue`, `--accent` and their
`-dim`, `-tint`, `-border` variants) remain canonical. Prefer the semantic
aliases below when writing new components so hue can evolve independently of intent.

Each intent ships a triplet — the base color (`--color-<intent>`), a translucent fill
(`--color-<intent>-dim`), and a 30 % alpha border (`--color-<intent>-border`) — plus an
even fainter background wash (`--color-<intent>-muted`, ~6 % alpha) where the original
tokens did not already provide one.

| Token family | Intent | Underlying hue | Typical use |
|---|---|---|---|
| `--color-success` | Healthy, completed, positive outcome | Green `#5EBA8D` | Trace SUCCESS pill, eval PASS, service UP |
| `--color-warning` | Degraded, retry, soft alert | Amber `#D6A451` | Latency degraded, partial outage, dry-run |
| `--color-error` | Failure, destructive, blocked | Red `#E07C7C` | Trace ERROR pill, eval FAIL, guard BLOCK |
| `--color-info` | Neutral information, primary metric | Mist Blue `#8CB8FF` | Info banner, info chip, link affordance |
| `--color-pending` | Waiting on review or human action | Violet `#A78BFA` | RAG cache PENDING badge, draft awaiting approval |
| `--color-attention` | Review attention, opt-in highlight | Amber `#D6A451` | Spotlight chip, "review me" callouts |
| `--color-processing` | In-flight, streaming, running | Sky-cyan `#38BDF8` | Live trace stream, async job RUNNING |
| `--color-neutral` | No-status, archived, inactive | Slate `#94A3B8` | Disabled, archived, "—" placeholder |

Companion CSS classes (`.badge-success`, `.badge-warning`, `.badge-error`, `.badge-info`,
`.badge-pending`, `.badge-processing`, `.badge-attention`, `.badge-neutral`) are defined in
`src/shared/ui/shared-components.css` and pair the triplets onto the standard `.badge`
shape. Migrate StatusBadge entries and inline pills incrementally — there is no big-bang
rename of the legacy `.badge-green` / `.badge-yellow` / `.badge-red` / `.badge-gray` classes.

Initial proof-of-concept migrations: `StatusBadge` now maps `SUCCESS` → `badge-success`,
`PENDING` / `PENDING_REVIEW` → `badge-pending`, and `ERROR` → `badge-error`.

### Colorblind-Safe Icon Prefix (WCAG 2.1 SC 1.4.1)

Every `StatusBadge` ships an inline 12 × 12 SVG glyph before the label so the
intent stays parseable for users with color-vision deficiency, in greyscale
print, and on monochrome terminals. Color is **never** the sole differentiator
for a status. Icons use `currentColor` so they inherit the badge's intent text
color and stay in lock-step with the palette.

| Intent | Icon | Glyph |
|---|---|---|
| `success` | `CheckIcon` | ✓ check |
| `warning` | `WarningIcon` | ⚠ triangle with bang |
| `error` / `failed` | `XIcon` | ✕ x |
| `info` | `InfoIcon` | ℹ circled i |
| `pending` | `HourglassIcon` | ⧖ hourglass |
| `processing` / `running` | `ProcessingIcon` | ⟳ rotating arrow (static — no animation by default) |
| `attention` | `StarIcon` | ★ star |
| `neutral` | `DotIcon` | • dot |

Source: `src/shared/ui/icons/StatusIcons.tsx`. The mapping from status string to
intent lives next to the color map in `StatusBadge.tsx` so adding a new status
always touches both. Two opt-out props are available:

- `iconOnly` — square 16 × 16 cell with the icon centred and the label exposed
  via `aria-label` only. Use in dense table cells where a full pill would wrap.
- `hideIcon` — legacy text-only fallback. Avoid in new code; prefer the default
  with-icon rendering for accessibility parity.

## 11. Chart Palette & Colorblind Safety

Recharts SVG attributes (`stroke`, `fill`) cannot resolve CSS custom properties
directly, so chart colors live alongside the components in
`src/shared/ui/ChartConfig.ts` as literal hex values that mirror the
`--chart-*` and `--color-*` tokens in `src/index.css`. Every recharts site
must consume that module rather than hardcoding hex or pulling from the
legacy `chartColors` helper.

### Categorical Palette (Wong / Tol-inspired, dark-canvas tuned)

| Index | Hex | Role | Token alias |
|---|---|---|---|
| 0 | `#60A5FA` | Blue   | `--chart-1` / `--color-info` |
| 1 | `#34D399` | Emerald | `--chart-2` / `--color-success` |
| 2 | `#D6A451` | Amber  | warning / `--color-attention` |
| 3 | `#A78BFA` | Violet | `--chart-3` / `--color-pending` |
| 4 | `#F87171` | Rose   | `--chart-4` / `--color-error` |
| 5 | `#38BDF8` | Sky    | `--color-processing` |
| 6 | `#F59E0B` | Orange | secondary warm |
| 7 | `#94A3B8` | Slate  | `--color-neutral` |

Ordering is intentional: red (`#F87171`, idx 4) and green (`#34D399`, idx 1)
are non-adjacent so deuteranopic / protanopic readers can distinguish them
when consecutive series are assigned. Use `paletteColor(i)` (modulo-bounded)
rather than indexing the array directly.

### Sequential Palette (ordered scales)

`CHART_SEQUENCE` walks `#1E2A3A → #3B5572 → #60A5FA → #A6CCFB → #E0EFFF`
along the blue-luminance axis so heatmaps and gradient legends remain
parseable in greyscale.

### CB-Safe Stroke / Marker Rotation Rule

Color alone is never the sole differentiator on a multi-series chart. Pair
every palette assignment with a redundant non-color cue rotated by series
index:

- **Stroke dash** (`strokeDashFor(i)`): `solid → 4 2 → 6 3 → 2 2 → 8 4 2 4`,
  cycling every 5 series. Index 0 stays solid so the primary metric reads
  cleanly; subsequent series receive subtle dash patterns that survive a
  greyscale screenshot.
- **Marker shape** (`markerShapeFor(i)`): `circle → square → triangle → diamond → cross`
  for scatter charts and large line markers.

`getLineSeriesProps(i)` and `getAreaSeriesProps(i)` bundle the palette color
+ dash rotation + sensible stroke width / dot sizes — call them inside any
`<Line>` / `<Area>` series rather than spelling the props out.

### Axis & Grid Defaults

Spread `CHART_AXIS_STYLE` onto `<XAxis>` / `<YAxis>` and `CHART_GRID_STYLE`
onto `<CartesianGrid>` so every chart shares the same `--text-muted` tick
fill and `--border-subtle` 3-3 dashed grid. This replaces the per-component
`{ fill: chartColors.muted, fontSize: 11 }` boilerplate that previously
drifted across pages.

### Tooltip

Always pass `<ChartTooltip />` to `recharts <Tooltip content={...} />` —
the shared component renders on `--bg-elevated` with `--border-standard`
and uses IBM Plex Mono for numeric values per §3 typography rules.

### Chart Type Coverage

The same palette + axis/grid presets apply across every chart type. Pick the
palette index by the slice / series semantic, not by render order:

- **Line / Area (single series)** — `getLineSeriesProps(i)` / `getAreaSeriesProps(i)`.
  Index 0 (mist blue) is the conventional pick for a primary trend; amber is
  reserved for a warning threshold or review state.
- **Line / Area (multi-series)** — assign indices that are non-adjacent on the
  CB-safe scale (e.g. success → 1 emerald, failure → 4 rose; never 1 + 2 next
  to each other). The dash rotation in `strokeDashFor(i)` provides the
  redundant non-color cue for greyscale parsing.
- **Bar (single category)** — set `fill={paletteColor(i)}` directly. For an
  approval-rate / cost bar, idx 0 (mist blue) identifies the measured value;
  use idx 2 only when the bar represents a warning or review state.
- **Pie / Donut** — assign one palette index per slice via `<Cell fill={...}>`,
  starting from idx 0 and skipping to non-adjacent indices for high-contrast
  pairs. Channel-style donuts may map known categories to fixed indices (e.g.
  web → 0, slack → 1, teams → 3, discord → 4) and fall back to `paletteColor(i)`
  by entry index for unknown categories.
- **Stacked Area** — same as multi-series Area: assign palette indices per
  stack with non-adjacent CB-safe spacing and let the dash rotation carry
  greyscale parsing. The gradient `<stop>` colors must mirror the stroke index
  exactly (`paletteColor(i)`) — never hardcode the hex.

When in doubt, default to the order: **0 (mist blue)** for the primary metric,
**1 (emerald)** for "good / success", **4 (rose)** for "error / failure",
**2 (amber)** for "warning / review", **3 (violet)** for "pending", with
**5–7** held in reserve for tertiary categories.

## 12. Operational analytics

- Analytics pages lead with the operator's question (`응답 속도`, `대화 안정성`, `도구 안정성`), not implementation terms such as endpoint, percentile, trace, outcome, or timeout.
- A four-value summary must establish hierarchy: one primary decision metric may use `--surface-feedback`; supporting facts use the standard panel surface. Do not render four identical `StatCard` tiles when the values describe one operational state.
- Percentiles and other unavoidable statistical terms stay out of the primary label. Use plain Korean labels and the shared `HelpHint` for the precise definition.
- Summary groups use `--surface-panel-*`, `--workspace-section-gap`, typography, and responsive breakpoints from the token system. Never add decorative separators or inline raw dimensions.
- Empty charts should collapse into an explanatory `EmptyState` where possible. A large bordered rectangle containing only “데이터 없음” is not an acceptable finished state.
- A zero-valued series is not a trend. Replace an all-zero cost or usage chart with a short contextual explanation so the next actionable ledger remains in the first viewport.
- Long opaque identifiers are implementation evidence, not primary labels. Show a stable, shortened human label in lists and preserve the canonical identifier only in a detail or copy surface when an operator needs it.
- **Usage reporting keeps people and models legible**: `/usage` uses one cost anchor, bare supporting facts, a chronological trend, then two ledgers. Compact anonymous-user references and localized model/provider names are primary; canonical identifiers belong only in a tooltip or selected technical detail. Its route capability gate names the same cost, daily, and model endpoints that the first view requests; a runtime failure remains a ledger-specific recovery state and never erases the successful data beside it.

## 12.1 Operational workflows

- A page-local workflow uses consecutive `1 → 2 → 3` numbering. Do not reuse global release-stage numbers inside local steps when that produces repeated or backwards sequences such as `5 → 5 → 1`.
- Lead with the operator's decision and action (`대표 사례 점검`, `결과 보관`, `출시 판단 갱신`). Vendor names, report keys, environment variables, SDK contracts, and artifact paths belong in help or a collapsed developer disclosure.
- Do not place a row of shortcut links above a workflow when the same destinations already exist in the workflow, adjacent-step navigation, or remediation details.
- Workflow steps may share one open row when sequence matters, but must not use decorative vertical rails, boxed number badges, or a separate status pill on every step. Use spacing, consecutive numbering, and a small semantic status marker.
- On review-queue pages, the queue, filters, and current error or empty state come before downstream release handoffs. External sync, report aggregation, and developer evidence belong after the ledger or in collapsed details; they must never push the review task below the first viewport.

### 12.2 Integration operations

- Connection overviews use plain service names and Korean states. Raw transport states such as `PASS`, `FAIL`, `WARN`, and `DISABLED`, and protocol labels such as `A2A` or `Provider`, do not lead an operator-facing summary.
- A manual integration test leads with the message, event, or task the operator is about to send. Release links, environment variable names, endpoint metadata, and evidence contracts belong in one collapsed technical disclosure after the test action.
- Page-local integration sequences use consecutive numbering even when their destinations belong to different global release stages. Global stage navigation may remain in the page header but must not distort the local reading order.
- Endpoint recovery uses one compact fact row followed by prioritized recovery rows. Do not use scalar StatCards, InfoCard grids, repeated status badges, or a three-card runbook; endpoint paths and server details stay in collapsed technical information.
- Project connection status is a flat list with one dot, human name, explanation, and contextual registry action. It never repeats release-workflow links, and narrow layouts must keep project names horizontal rather than collapsing into vertical text.

### 12.3 Release decisions

- A release page must distinguish `data unavailable` from `release evidence missing`. When the backend request fails and no previously verified result exists, fail closed: show a retryable connection state and do not render guessed tags, version changes, gates, or missing-evidence summaries.
- The primary release surface answers three questions in plain Korean: can we release now, what must be fixed first, and what version tag would be created. Raw report names, environment variables, commands, SDK contracts, and evidence keys stay in collapsed technical disclosures.
- Release summaries use open spacing and hierarchy, not vertical divider walls or equal statistic tiles. Page-local feature flows use consecutive numbering; global release navigation remains separate.
- `출시 판단`, `기능 흐름`, `상세 확인 자료` are separate operator tasks. Only the decision view repeats the verdict and version summary; workflow and evidence views begin directly with their own content.
- The complete linked gate inventory belongs only to `기능 흐름`. `출시 판단` keeps the verdict, first corrective action, and compact version facts; it must not repeat the workflow list below that decision.
- Version-change enums are localized (`기능 추가`, `오류 수정`, `대규모 변경`). Warning report names, raw statuses, source keys, commands, and environment variables appear only after an operator opens technical details.
- A gate row announces its state once. Do not combine an icon-only badge, a state badge, and repeated status text for the same result.

### 12.4 Operational health states

- Never turn missing or failed diagnostic data into a confirmed outage. Use a neutral `확인 필요` state until a returned diagnostic explicitly reports a warning or failure.
- Summary copy must follow the same evidence boundary: do not claim that no action is needed when the underlying checks are unavailable or empty.
- Section-level load failures use a compact, left-aligned explanation with a retry action. Avoid large decorative empty-state illustrations for operational data that may return on the next request.
- Plain-language copy distinguishes server failure from an admin-session, permission, or connection problem. Technical endpoint names and raw error details belong in optional diagnostic disclosure, not the primary status message.
- A page-level data failure owns one recovery surface. Suppress secondary diagnostic banners that describe the same unavailable backend, and never concatenate a friendly message with a raw transport error in the primary copy.
- A retry action reports success only after fresh data is returned. Starting a request is not a successful refresh; pending state belongs on the action itself.
- Never render zero-valued operational summaries, readiness checks, troubleshooting panels, or empty collections from an unavailable first response. Without a successful snapshot, one page-level recovery surface replaces the complete data workspace.
- Recovery guidance stays collapsed and uses operator steps first. Raw endpoint names, transport errors, and cross-console implementation guidance do not lead the error state.
- Use the shared `WorkspaceUnavailable` primitive for page-level first-load failures. It owns the open layout, one retry action, optional status destination, collapsed operator steps, technical detail, and the single-column mobile contract; do not fork page-local copies.

### 12.5 Response testing workspaces

- The question, primary run action, and answer precede optional execution settings in DOM and visual order. Operators should not cross a configuration wall before they can state what they want to test.
- Keep the answer role, model, and reusable answer form in one compact settings surface. Runtime, graph profile, token budget, cost budget, and raw payloads remain collapsed until explicitly requested.
- When several selectors fail for the same reason, render one recovery explanation and one retry action. Do not repeat a red bordered error box inside every field.
- Permission failures are account-state problems, not server outages. Say that administrator access is needed, preserve successful selectors, and label unavailable values without inventing defaults.
- The question composer, settings surface, and unavailable values use product surface, control-height, spacing, radius, and type tokens. Do not introduce route-local raw dimensions or browser-default controls.

### 12.6 Developer diagnostic senders

- Developer-only tools still lead with the task in plain language: choose a verification record, review the sample, then send it. Protocol acronyms and transport paths do not define the primary hierarchy.
- Raw JSON is allowed only inside the explicitly labeled payload editor or a collapsed raw-response disclosure. Endpoint paths, permissions, and transport metadata stay in one collapsed developer-detail section.
- A successful write leads with a human confirmation and a small allowlisted result summary. Unknown response keys and nested objects remain in the collapsed raw response so snake_case fields cannot leak into the primary result.
- Permission failures are presented as account access problems; malformed JSON is presented as an input-format problem. Neither state may be generalized into a server outage.
- One main payload surface is sufficient. Do not wrap the warning, type selector, editor, submit action, and result in separate nested cards.

### 12.7 Failure replay workspaces

- A failed-request list must distinguish a successful empty response from an unavailable response. Query failures use `WorkspaceUnavailable`; never render them as “no failures”.
- The local sequence is `request selection → input review → response test`. A global release backlink does not belong inside this developer workflow when the same release route already exists in navigation.
- List rows lead with the captured request and a localized failure reason. Capture IDs, user hashes, raw error codes/messages, model IDs, and tool names are developer evidence and remain in one collapsed technical disclosure.
- Replaying never starts a request directly from the ledger. The primary action opens the response-testing workspace with a prefilled input and explicitly states that execution still requires operator confirmation.
- The list/review split uses shared workspace, surface, control, typography, spacing, and responsive tokens. At tablet width it becomes one column; at mobile width record metadata stacks without horizontal overflow.

### 12.8 AI role configuration

- Operator-facing language describes the job as `AI 역할 구성`: which questions a role handles, which connected functions it may use, and how it answers. `Universe`, `sub-agent`, `multi-agent`, `routing`, `orchestration`, and raw runtime modes do not lead the page or form.
- A role directory must distinguish a verified empty list from an unavailable list. Query failures use `WorkspaceUnavailable`, suppress create actions, and never claim that no roles are registered.
- Empty onboarding is left-aligned and task-oriented. Use one create action plus a collapsed three-step explanation; do not add a decorative empty-state icon, sample code block, or duplicate header action.
- Directory rows lead with role name and responsibility. Selection keywords and answer mode use plain Korean; tool counts are supporting facts. Canonical tool names and professional instructions stay in the edit surface.
- The role directory is read-and-select. Enable, stop, edit, and delete controls appear only after selecting a role; do not attach an icon-action cluster to every directory row. Selected role facts remain open while identifiers and backend-only configuration stay in a closed developer disclosure.
- Answer principles are readable Korean-first body text even when line breaks are preserved. Do not render them as terminal-like preformatted or monospace blocks; raw prompt data and access records remain secondary to the operator decision.
- Create, enable/disable, edit, and delete failures use the shared localized API-error treatment. A successful list does not justify hiding mutation failures.

### 12.9 Operational policy settings

- The page is `운영 정책`, split into `서비스 설정` and `데이터 보관 기간`. `runtime`, `backend`, cache internals, file formats, and raw retention field names do not define the primary navigation or explanation.
- Each policy tab owns its query boundary. An unavailable response uses `WorkspaceUnavailable`, hides mutation and maintenance actions, and never renders default values or an empty list as if they came from the server.
- Service-setting rows lead with the backend description and a human-readable value. Raw keys, value types, JSON payloads, and secret handling belong in a collapsed developer disclosure inside the edit dialog.
- Boolean values use `사용 / 사용 안 함`; structured values use a neutral summary. Do not expose `true`, `false`, raw JSON, or a separate type column in the primary ledger.
- Data-retention labels describe the stored product record (`대화 내용`, `관리자 변경 기록`, `중단된 작업의 재개 정보`), not implementation nouns such as metric or checkpoint.
- Validation is inline text with semantic color and an icon, not a success/error badge. Reset confirmation uses localized operator language, never an English sentinel such as `RESET`.

### 12.10 Safety policy workspace

- The primary safety sequence is `요청 검사 → 답변 보호 → 도구 실행 권한`. Terms such as input guard, output guard, fail-close, pipeline, coverage, runtime, endpoint, and raw policy contracts belong in contextual help or collapsed developer details, not primary navigation.
- The three safety areas share one horizontal workspace navigation. Do not add a decorative vertical divider or a second LNB inside the page; nested task tabs may remain only when they describe a real subtask.
- The workspace shell owns the selected area name and explanation. An embedded safety area must not repeat a page header or another area title; its first visible element is either a real subtask tab set or a compact action/context row.
- Answer-protection ledgers use readable action text and one semantic dot with localized state. Edit and delete actions belong in the selected rule detail, not in every table row; normal state does not use badges, capsules, or action-button clusters.
- Request-check rule ledgers follow the same contract: one `검토` action per row opens the selected rule, while edit, deletion, activation, expressions, categories, and identifiers remain in that detail. The primary ledger shows the Korean handling outcome, human explanation, priority, and localized state only; regex, internal category codes, and identifiers are specialist information inside a closed technical disclosure.
- Request-check change records map backend action values to Korean work descriptions and product targets. Their filter labels, table cells, and relative times never expose action codes such as `RULE_UPDATE` or `BLOCK`; unknown backend values fail safely to a localized unknown label instead of leaking raw protocol values.
- Answer-protection simulations use one localized decision state (`문제 없음`, `확인 필요`, or `차단됨`) and a compact definition list. Applied and invalid rules are flat rows, never badge/tag stacks or nested cards. The selected-rule panel keeps the operator explanation, state, and timestamps open; backend rule IDs, expressions, and parser details live only in a closed technical disclosure.
- Tool-access readiness is one open summary with a localized decision state and flat definition rows. Do not wrap ordinary counts in StatCards, render raw `WARN`/`PASS`, or place a metric-card grid inside another panel.
- Tool-access editing is one flat configuration surface. Tool and channel identifiers appear only where they must be edited and each has a `HelpHint`; channel-specific JSON exceptions, stored-versus-applied diffs, raw policy values, and runtime mode flags stay behind closed disclosures. Save and refresh belong to the active workflow, while resetting a stored policy is collapsed maintenance.
- Access control uses an open role list, flat permission groups, and a two-column comparison only when two roles are selected. Role, resource, and action identifiers must resolve to Korean operator text with an explicit unknown fallback; no role-color pills, permission badges, decorative legends, or raw backend identifiers belong in the primary workspace. Member identity facts wrap as a flat definition list without vertical separators, and failed role changes expose backend detail only in a closed technical disclosure.
- Each area owns its verified data boundary. When the first request fails, render `WorkspaceUnavailable`, hide counts, mutation controls, simulations, and editors, and never represent missing data as zero.
- Recovery starts with retry, account access, and the shared status screen. Raw error text may appear only inside collapsed technical details; internal API paths and backend runbooks do not belong in the default error state.
- Successful answer-protection summaries use one compact definition list rather than a grid of metric cards. Release-workflow backlinks are omitted from the embedded safety workspace so policy review stays focused on the current task.
- Desktop and narrow layouts keep the same information order, allow the workspace tabs to scroll horizontally when needed, and must not introduce horizontal page overflow.

### 12.11 Access control workspace

- The page owns one `접근 제어` header before the URL-addressable `역할별 권한 / 구성원 권한` tabs. Embedded panels do not repeat the page title or release-workflow navigation.
- A failed role request is not an empty role list. Initial loading hides role selectors; initial errors use `WorkspaceUnavailable`; only a verified empty response may show the no-role state.
- Role selection uses a compact segmented control with medium radii, not pills, glow, role-color fills, or raw role IDs. The selected state uses the shared note surface and text contrast.
- Role detail favors plain headings, descriptions, and grouped permission lists. Do not use decorative initial tiles, gradient fills, top accent bars, badge clusters, uppercase group labels, or nested cards for every permission group.
- Permission comparison uses Lucide icons and localized permission names. Do not use text symbols such as checkmarks, stars, or crosses as visible status decoration.
- Member lookup uses tokenized input/select controls and product language (`구성원`, `관리 범위`). Not-found is a verified search result; transport or authorization failure is a fail-closed recovery state with raw detail collapsed.
- At narrow widths, lookup controls stack in task order, actions span the available width, and the page must not overflow horizontally.

### 12.12 Organization management workspace

- The `/tenants` workspace owns one `조직 관리` page header and description before URL-addressable `조직 목록 / 조직별 운영 현황` tabs. Embedded list and operations panels must not repeat another page header.
- A failed organization-list request is not an empty organization. Hide create, destructive, analytics, and selection controls until the roster is verified; use one fail-closed recovery surface with retry, status navigation, and collapsed technical detail.
- Primary copy uses `조직`, `이용 요금제`, `조직 주소`, `사용 한도`, and `서비스 목표`. Do not expose `X-Tenant-Id`, `slug`, raw enum values, or backend-only status keys as primary labels.
- The internal organization identifier remains available only as `조직 식별값`, with contextual help explaining that it is normally populated from the roster. The main workflow remains list selection followed by a period check and `운영 현황 확인`.
- The roster answers only which organization to inspect. Do not append a second all-organization usage table below it; usage, service targets, and downloads belong in the selected organization's URL-addressable operations workspace.
- Download actions stay hidden until an operator has requested a verified operations report. Do not fill the initial state with disabled CSV controls.
- Unknown plan, organization, or service-target values render a localized safe fallback instead of backend IDs or enum strings.
- Narrow layouts preserve the same task order, stack range controls and actions to full width, and must not introduce horizontal page overflow.

### 12.13 Conversation records workspace

- `/sessions`, `/sessions/feed`, and `/sessions/users` are one `대화 기록` workspace. Every route keeps the same page title and uses URL-addressable `운영 개요 / 대화 목록 / 사용자별 보기` navigation; route-specific context belongs in the description, not a replacement title.
- Failed overview, conversation, user, or detail requests never render `0건`, `0명`, empty charts, or not-found conclusions. Use `WorkspaceUnavailable` with retry, status navigation, and collapsed technical detail; only verified empty responses use empty states.
- Search controls use the shared Lucide icon set. Do not use emoji or text glyphs for search and clear actions.
- Primary conversation and user tables lead with recent content, user, human status, and time. Session, trace, thread, run, and last-session identifiers do not belong in list columns or visible tooltips; retain them only in the detail/developer boundary when operationally necessary.
- Unknown backend status values render the localized unknown state. Do not echo raw enums or construct untranslated dynamic keys.
- Status in dense tables is plain text, not a pill or badge. Download controls remain secondary table actions.
- Detail headers and breadcrumbs describe `선택한 대화` rather than exposing the route identifier. Detail transport failures fail closed and keep raw error text in recovery detail.
- At narrow widths, workspace navigation remains horizontally available, search and recovery actions stack in task order, and the page must not overflow horizontally.

### 12.14 External tool connection workspace

- `/mcp-servers` is `외부 도구 연결`: the operator verifies whether an AI connection is available, whether it may be used, and what recovery action is needed. `MCP`, transport identifiers, preflight, backend status, and protocol details do not define the primary hierarchy.
- Server-list and security-policy requests form one verified boundary. If either request fails, use `WorkspaceUnavailable`, hide counts and mutation controls, and never represent an unavailable inventory or policy as zero, empty, or allow-all.
- Unknown connection and transport values use localized review states. Raw enum values, snake_case identifiers, server IDs, tenant IDs, and snapshot hashes never appear in the default surface; identifiers remain in one collapsed developer disclosure on detail.
- Connection state in dense rows is plain text with one semantic dot, not a badge. The summary is a compact filter control, not a row of metric cards, and bulk recovery/destructive actions receive their own labeled task row.
- The default connection registry shows the status filters, search, and selectable rows only. Global policy, fleet-wide recovery, and emergency blocking live together in one closed `연결 작업` disclosure below the list; they must not compete with registration or row inspection in the page header or first viewport.
- The connection list is a read-and-select ledger. Individual connection, disconnection, and AI-use changes live in the selected connection detail; do not put mutation buttons or toggle controls in every table row. The list may show one plain `사용 가능 / 사용 중지` state with a semantic dot.
- A recent connection failure begins with a Korean recovery sentence. Raw transport errors and additional connection configuration stay in closed technical disclosures; target, authentication method, and request timeout are the only connection facts that remain open.
- Only show data the backend contract can verify. Do not render a tool-count column or an empty tool inventory when the MCP server response does not provide those fields. Mock handlers must mirror the real backend response shape so browser QA cannot certify invented data.
- Search uses the shared Lucide icon language and searches verified connection names. Toggle controls have connection-specific accessible labels; dangerous fleet actions stay visibly separate from ordinary connection recovery.
- Primary detail copy uses `실행 상태`, `연결 점검`, `별도 인증 없음`, seconds, and plain access-scope labels. Raw `healthy`, `none`, `PASS`, `preview`, function markers, and backend-only keys do not appear in the default reading path.
- At narrow widths, status filters fit without clipped labels, actions stack, and low-priority transport/permission columns move into the DataTable row expander. The document must not overflow horizontally.

### 12.15 Document search and cache workspace

- `/rag-cache` is `문서 검색·캐시`. Its task navigation is `저장된 답변 / 답변 검토 / 문서 검색 / 수집 기준 / 운영 분석`; `RAG`, vector store, semantic cache, embeddings, and release-report vocabulary do not define the primary hierarchy.
- Unknown first-load data is `상태 확인 필요`, never `시스템 정상`. A healthy summary requires returned cache and document-search policy evidence.
- The document-search tab starts with one open summary: search-ready document count, answers awaiting review, and only the three direct actions needed to manage documents, test an answer, or open the review queue. Do not use numbered process rails, boxed number badges, status pills, or duplicate stage navigation.
- Collection rules are their own `수집 기준` tab. Do not keep a full policy form beneath answer testing or document search just because the data shares a backend domain.
- The overview refresh belongs beside the operation summary, not in a page-header toolbar. Release navigation stays in the LNB; document and answer actions stay within the workspace.
- The candidate queue is empty only after a verified empty response. A missing route, unavailable store, authorization failure, or transport failure renders `WorkspaceUnavailable` with retry, status navigation, and collapsed technical detail; it never renders zero counts, filters, or `후보 없음`.
- Search results show readable content and source readiness first. Result IDs, source URIs, citation identifiers, and hashes remain in one closed `개발자용 검색 근거` disclosure.
- A selected answer-review drawer starts with review state, channel, capture time, a one-sentence decision cue, the user question, and the proposed answer. Optional operating checks use a flat divided list; candidate IDs, run IDs, action IDs, evidence paths, and runbooks stay in one closed `개발자용 확인 정보` disclosure. It must not repeat release navigation or render action state as cards, numbered stages, or status pills.
- Raw status enums, report keys, data-set names, commands, provider/runtime fields, and source identifiers remain in collapsed developer details. Narrow layouts preserve task order and must not overflow horizontally.

### 12.15.1 Answer-role collection states

- `/personas` uses one creation action: it appears in the page header only when the verified collection has rows, and in the empty-state introduction only when the verified collection is empty. Do not duplicate the action or reintroduce a generic empty-state icon.
- A failed role-list request is never an empty role collection. Hide stale counts, rows, detail panels, and mutation controls; render `WorkspaceUnavailable` with retry, status navigation, and collapsed technical detail instead.

### 12.15.2 Response-test error boundary

- `/chat-inspector` presents one Korean recovery sentence for request and response failures. Raw error codes, HTTP text, backend store/configuration names, and server messages never appear in the primary alert.
- If an operator needs diagnosis, retain those fields only in one closed `기술 정보` disclosure below the user-facing error. The collapsed state must be meaningful without opening it.
- The execution settings are a quiet right-hand context rail, not a rounded dashboard card inside another workspace. Use whitespace and the existing form/divider rhythm to separate it from the question-and-answer task.
- Answer text and streamed answer text use ordinary reading typography, never a code block. Model identifiers, raw tool names, response payloads, and stream events remain inside one closed `개발자용 확인 정보` disclosure; a compact Korean event label and semantic dot may summarize a record after the operator opens it.

### 12.16 AI model operations workspace

- `/models` owns one `AI 모델 운영` header above `모델 목록 / 가격 설정 / 비용 알림`. Embedded tabs do not create competing page titles or repeat global release-stage navigation.
- The model ledger and default-model summary precede any live response test. Operators choose what the product uses before reviewing release evidence or running diagnostics.
- Primary language is `모델`, `모델 제공 방식`, `실제 응답 시험`, `사용량`, and `출시 상태`. `Provider smoke`, `Live smoke`, `Readiness`, raw report names, environment variables, and commands belong in collapsed developer details.
- Default-model state is supporting text, not a badge. Dense model tables keep status as text and reserve pills for exceptional states.
- Desktop and narrow layouts preserve the same order: model summary, model ledger, then optional response test. The page must not overflow horizontally.

### 12.17 Platform health workspace

- `/health` is an operator decision surface: one summary, dependency diagnostics, processing signals, then recovery actions. It does not repeat nested status cards or expose raw diagnostic payloads by default.
- The summary is derived fail-close from detailed dependency sections. `SKIPPED` or unconfigured dependencies count as attention even when an optimistic summary endpoint reports `OK`; empty evidence remains unknown.
- Summary progress counts connected dependency sections, not only emitted leaf checks, so `1/3 정상` cannot be misrepresented as `1/1 통과` when two dependencies are unconfigured.
- Rates are rendered as labeled percentages and durations include units. Technical framework names stay behind `HelpHint`; primary labels explain the operator meaning in Korean.
- A retained numeric field without live instrumentation is not a zero. The backend contract exposes explicit availability for pipeline and cache signals; the UI renders a concise unavailable state instead of invented or placeholder metrics. Mock payloads must match this contract exactly.
- Unrecognized diagnostic names, check keys, and backend detail strings never become primary copy. Render a Korean fallback and a safe recovery sentence; raw server data stays out of this screen by default.
- Desktop and narrow layouts preserve the order summary → dependencies → processing → actions, with no horizontal page overflow.

### 12.18 Feedback review workspace

- `/feedback` is an operator inbox for understanding a reported answer, deciding its review state, and promoting representative failures into evaluation coverage. The default view must not compete with the release cockpit or expose its complete evidence inventory.
- Domain and intent values cross a human-label boundary before rendering. Known backend identifiers use Korean task language; canonical identifiers may remain only as non-visible traceability metadata such as `title` or inside a developer disclosure.
- Rating, review state, and evaluation lifecycle are plain text with one semantic dot in the dense desktop ledger. Do not render three adjacent pills or badges for ordinary row state.
- Summary statistics and Slack follow-up rates live inside the collapsed `통계` disclosure as flat definition rows. Negative-category groups are unframed lists, not a metric-card grid.
- At narrow widths, the ledger becomes one readable question column. Rating, review state, and evaluation lifecycle move into a supporting metadata line below the question; low-priority columns must not squeeze the question into vertical text or require page-level horizontal scrolling.
- Release-gate evidence, case identifiers, SDK contracts, report paths, commands, and environment requirements stay collapsed by default. Opening the disclosure preserves the complete diagnostic contract without dominating routine feedback triage.
- The page header owns refresh, export, and saved views only. Release-stage navigation remains in the LNB; do not repeat adjacent-stage backlinks in the header or evidence panels.
- A selected feedback drawer starts with `선택한 의견`, human-readable rating/review state, and readable question/answer text. Feedback IDs, run IDs, evaluation case IDs, report paths, commands, and JSON metadata belong in a collapsed `세부 근거 보기` disclosure; do not render them as the default drawer title, code block, tag, or workflow link inventory.
- Feedback links use tokenized text, underline, hover, and focus colors. Browser-default blue links are forbidden in both the primary review path and expanded evidence.
- The primary follow-up is `대표 점검 사례로 추가 → 결과 저장 확인 → 의견 완료 처리`; terms such as promotion, eval case, regression, source run, and vendor names belong in closed technical evidence. Selected rows use only a neutral surface shift and neutral separator, never an amber perimeter or warning-like horizontal line.

### 12.19 Evaluation and external-record workspace

- `/evals` starts with the task sequence `대표 사례 점검 → 사례 보관 → 출시 판단 갱신`. The sequence is a single divided list with semantic status dots, not three equal workflow cards or a duplicate release navigation bar.
- `평가 사례 보관` is the primary operation. Its dataset name, enabled-case count, save action, and readiness refresh stay in one task area; secondary live-smoke, product-boundary, blocking, feedback-coverage, report, command, and SDK details remain closed until an operator explicitly opens them.
- Primary copy uses `점검 자료 묶음`, `저장 방식`, `확인 기록`, `필요한 설정`, `반영 근거`, and `문제 해결`. Raw gate identifiers, SDK names, environment keys, case/example identifiers, report paths, command strings, and protocol field names remain in the opened technical boundary only.
- Secondary release-stage numbers never leak into the local live-check list. A local sequence either uses consecutive local numbers or no numbers; state is conveyed with one semantic dot and text.
- Full-width disclosure summaries and long form controls keep a quiet neutral keyboard focus boundary. Do not use an amber perimeter or horizontal line that can be mistaken for a warning or section decoration.
- The evaluation run ledger, saved-case roster, and release-readiness snapshot form one verified data boundary. If any initial request fails, show one `WorkspaceUnavailable` recovery state and hide all counts, readiness states, save actions, and empty-list conclusions; a failed request is never `0건`, `미연결`, or an otherwise inferred release result.

### 12.20 Knowledge candidate review workspace

- `/documents?tab=ingestion` is an operator review queue. Its default sequence is `상태 요약 → 검토할 질문과 답변 → 선택한 후보의 검토`. Do not let a release-step toolbar, policy seeding, or general-page refresh compete with that queue.
- The LNB owns release progression. Candidate refresh belongs beside the candidate count; policy seeding belongs only while the policy tab is active.
- The candidate collection is an open table section with divider boundaries, not a rounded surface around an already framed table. Filter controls sit between the section explanation and the table, with no extra card shell.
- At narrow widths, all three state totals remain visible as equal readable columns, filters stack before the table, and low-priority capture-time columns are hidden. Page-level horizontal scrolling is forbidden.
- A selected candidate drawer begins with review status, plain-language next decision, question, answer, and optional review note. Candidate/run identifiers and capture metadata stay inside a closed `개발자용 후보 정보` disclosure.
- Expanded technical areas use divided rows rather than card grids or nested alert boxes. Normal action state is text with a semantic dot; no status pill, capsule, or browser-default blue link belongs in the primary evaluation path.
- The LNB owns release-stage navigation. The evaluation header and in-panel handoffs must not repeat generic release-backlink inventories.

### 12.21 Access-control data boundary

- `/access-control` adapts the backend role wire contract (`role`, optional `scope`, and `resource:action` permission strings) before it reaches the operator view. Mock handlers emit that same raw contract; they must not bypass the adapter with display-ready role objects.
- A malformed role record or permission string is an unavailable operating state, not an empty role list. The primary recovery sentence is Korean and actionable; implementation details remain in the existing closed technical disclosure.
- Permission resources cross the human-label boundary before rendering. An unrecognized resource receives a safe Korean fallback, never an English `Unknown …` label or raw backend identifier in the primary workspace.

## 13. Motion Policy

All transitions and animations must respect `prefers-reduced-motion: reduce` (WCAG 2.3.3).

### Motion Tokens (H-9)

Reactor's transitions follow a 3-step duration scale and three named easings. Use the tokens — never raw `0.15s ease` strings — so hover / focus / dropdown timings stay coherent and the reduced-motion safety net stays the only clamp surface.

| Token | Value | Usage |
|---|---|---|
| `--duration-fast` | `120ms` | Hover state, focus rings, opacity, color-only changes |
| `--duration-base` | `200ms` | Default transitions, dropdowns, accordions, transforms |
| `--duration-slow` | `320ms` | Drawers, modals, page-level transitions |
| `--ease-standard` | `cubic-bezier(0.4, 0, 0.2, 1)` | Most state changes (Material "standard") |
| `--ease-out` | `cubic-bezier(0, 0, 0.2, 1)` | Element exits / decelerations |
| `--ease-in` | `cubic-bezier(0.4, 0, 1, 1)` | Element enters / accelerations |

Reduced-motion still wins: the global `@media (prefers-reduced-motion: reduce)` block clamps `transition-duration` and `animation-duration` to `0.001ms !important`, so tokenised values are automatically neutralised when the user opts out.


**Global safety net.** `src/index.css` ships a single global `@media (prefers-reduced-motion: reduce)` block that clamps `transition-duration` and `animation-duration` to `0.001ms`, forces `animation-iteration-count: 1`, and sets `scroll-behavior: auto` on every element. This guarantees that any future stylesheet shipping naive transitions/animations is automatically tamed without per-file boilerplate.

**Targeted per-file overrides.** When a stylesheet uses `transform` decoratively as part of motion (e.g. spinner rotation, palette enter zoom, hover translateX, skeleton shimmer sweep), it MUST also append a per-file `@media (prefers-reduced-motion: reduce)` block that explicitly resets `transform`, `animation`, and `transition` for the affected selectors. The global rule only neutralises *durations* — it does not strip transforms, so motion via `transform: translateX/scale/rotate` keyframes still needs an opt-out per surface.

**State vs motion.** `transform` used as a static state indicator (e.g. a rotated chevron showing "open" vs "closed", or `translateY(-50%)` centring) MUST be preserved under reduced motion. Only the *transition* into that state should be removed. New components MUST not rely on motion to convey state — motion is a polish layer only.

**Audit gate.** `src/shared/lib/__tests__/reducedMotion.test.ts` enforces (a) the global block lives in `src/index.css` and (b) every CSS file containing `transition:` or `animation:` also contains a `prefers-reduced-motion` block. CI fails if a new stylesheet ships motion without a guard.
