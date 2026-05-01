---
slug: export-buttons-flat-cards
created: 2026-05-01
status: complete
---

# Quick Task — Export buttons visible + flat card redesign

## Goal

1. SRT/VTT/TXT/JSON download buttons visible on completed queue rows BEFORE
   clicking "View Transcript". Click triggers lazy fetch then download.
2. Move repeated Tailwind utility soup off `<Button>` JSX into a CSS class —
   shorten source markup. Loop format array (DRY) instead of 4 button copies.
3. Modernize but flatten the queue card visual — drop `shadow-sm`, swap
   status border for left accent strip, tighten radii, add hover lift via
   border-only (no shadow).

## Files

- `frontend/src/components/upload/FileQueueItem.tsx` — extract `ensureTranscriptLoaded`,
  always render `DownloadButtons` for complete items, pass loader.
- `frontend/src/components/transcript/DownloadButtons.tsx` — array-driven map,
  accept async `onBeforeDownload` loader, drop `gap-1` JSX class.
- `frontend/src/index.css` — flat-card restyle, `.queue-export-button` class.
- `frontend/src/components/upload/FileQueueItem.test.tsx` — update tests if any.

## Acceptance

- Complete row shows 4 download buttons with chevron toggle on the same line.
- Clicking a download button on a row whose transcript hasn't been loaded:
  fetches once, then triggers the download. Subsequent clicks reuse cache.
- Clicking "View Transcript" still works as before; uses same loader (single
  source of truth — no duplicate fetch path).
- DownloadButtons JSX renders 4 buttons via `.map()` — no copy/paste blocks.
- Card has no drop-shadow; status indicated via 4px left border accent.
