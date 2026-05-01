---
slug: export-buttons-flat-cards
status: complete
completed: 2026-05-01
commit: 6dd46a1
---

# Summary

Three deliverables, one commit.

## 1. Export buttons render before "View Transcript"

`FileQueueItem.tsx` now exposes `ensureTranscriptLoaded()` — a single
async loader that:

- returns cached `{segments, metadata}` if already fetched,
- else hits `fetchTaskResult(taskId)`, populates state, returns the
  result,
- throws on failure (caught + surfaced via `transcriptError` state).

`handleToggleTranscript` and `<DownloadButtons onEnsureLoaded={...}>`
both call it — same fetch path, no duplication.

`DownloadButtons` is rendered unconditionally on complete rows.
`segments` may be `null` at render time; the click handler awaits
`onEnsureLoaded()` before invoking `downloadTranscript()`.

## 2. HTML shorter

- 4 buttons → `EXPORT_FORMATS.map()` over `[{format, label}, …]`.
- `gap-1` → `.queue-export-button` (CSS).
- `h-3 w-3` → `.queue-export-icon` (CSS).
- Inline `flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-border`
  on the transcript bar → `.queue-card-transcript-bar`.

## 3. Flat modern card

`@layer components .queue-card`:

- `box-shadow: none` (overrides shadcn Card's `shadow-sm`).
- `rounded-xl` → `rounded-lg`.
- Status colour moves from full border to **4px left accent strip**
  (`border-l-4` + `border-l-{tone}`).
- Hover bumps base border to `foreground/20` (no shadow lift).

| status     | accent          |
| ---------- | --------------- |
| pending    | `border`        |
| processing | `blue-500`      |
| complete   | `green-500`     |
| error      | `destructive`   |

## Verification

- `bun x tsc --noEmit -p tsconfig.app.json` — clean.
- `bun run test` — 130/130 pass.
- `bun run lint` (filtered to changed files) — no new errors.
  (Pre-existing warnings in `RegisterPage.tsx` etc. unrelated.)

## Files

- `frontend/src/components/transcript/DownloadButtons.tsx` — array map +
  async loader prop.
- `frontend/src/components/upload/FileQueueItem.tsx` — `ensureTranscriptLoaded`
  helper, unconditional `<DownloadButtons>` for complete rows.
- `frontend/src/index.css` — flat-card restyle, new button helper classes.
