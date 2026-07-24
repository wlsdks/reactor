# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Persona Playground**: SSE streaming chat UI for testing personas directly in the admin panel.
  Send messages, see real-time streamed responses, and observe tool executions inline.
- **PersonaInfoTab**: Inline edit/view form for all persona fields — icon, name, description,
  system prompt, response guideline, welcome message, isDefault, and isActive toggles.
  Includes resolved system prompt preview (collapsible).
- **Split-layout PersonaManager**: Rewritten from flat table + modal to split-layout with
  DataTable (left) and tabbed detail panel (right) with Info and Playground tabs.
- Extended `PersonaResponse`, `CreatePersonaRequest`, `UpdatePersonaRequest` types with
  `description`, `responseGuideline`, `welcomeMessage`, `icon`, and `isActive` fields.
- `streamPersonaChat()` API function — SSE streaming via raw fetch + ReadableStream,
  with token/tool_start/tool_end/done/error event parsing.
- i18n: 20 new persona keys in both `en.json` and `ko.json`.

### UX
- Auto-edit mode after persona creation (no extra clicks to configure).
- Unsaved changes protection — `window.confirm` on persona switch or tab switch while editing.
- Playground session preserved across tab switches (Info ↔ Playground).
- Enter to send, Shift+Enter for newline with placeholder hint.
- Clear button properly disabled when conversation is empty.
- Empty assistant bubble removed on API error (no ghost messages).
- Stream lifecycle safety: `finally` block ensures UI never stuck in streaming state.
- Abort on unmount prevents state updates on unmounted components.
- CSS scoped to `.persona-detail-tabs` to avoid collision with other feature tabs.
