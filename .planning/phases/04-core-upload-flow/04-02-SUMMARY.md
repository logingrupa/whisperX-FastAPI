---
phase: 04-core-upload-flow
plan: 02
subsystem: ui
tags: [typescript, types, language-detection, whisper-models]

# Dependency graph
requires:
  - phase: 03-build-integration-spa-serving
    provides: frontend build system with path aliases
provides:
  - FileQueueItem type for queue state management
  - LanguageCode type with 16 supported languages
  - WhisperModel type with 6 model sizes
  - detectLanguageFromFilename function for A03/A04/A05 patterns
  - CORE_LANGUAGES and OTHER_LANGUAGES constants
  - WHISPER_MODELS configuration with large-v3 default
affects: [04-03-upload-components, 04-04-file-queue]

# Tech tracking
tech-stack:
  added: []
  patterns: [type-first-design, utility-functions-in-lib]

key-files:
  created:
    - frontend/src/types/upload.ts
    - frontend/src/lib/languages.ts
    - frontend/src/lib/languageDetection.ts
    - frontend/src/lib/whisperModels.ts
  modified: []

key-decisions:
  - "16 languages total: 3 core (lv, ru, en) + 13 common European/Asian languages"
  - "A03/A04/A05 pattern detection is case-insensitive"
  - "large-v3 as default model (user preference for accuracy)"

patterns-established:
  - "Types in frontend/src/types/, utilities in frontend/src/lib/"
  - "Constants exported as readonly arrays with typed interfaces"

# Metrics
duration: 2min
completed: 2026-01-27
---

# Phase 04 Plan 02: Upload Types & Language Detection Summary

**TypeScript types for file queue items, language detection from A03/A04/A05 filename patterns, and Whisper model configuration with large-v3 default**

## Performance

- **Duration:** 2 min
- **Started:** 2026-01-27T14:35:51Z
- **Completed:** 2026-01-27T14:38:20Z
- **Tasks:** 3
- **Files created:** 4

## Accomplishments
- FileQueueItem interface with full queue state modeling (id, file, detected/selected language, model, status)
- Language detection extracts A03/A04/A05 patterns from filenames (case-insensitive)
- 16 languages: Latvian, Russian, English (core 3) plus 13 common languages
- All 6 Whisper models configured with large-v3 as default

## Task Commits

Each task was committed atomically:

1. **Task 1: Create upload types** - `749332b` (feat)
2. **Task 2: Create language detection and constants** - `1289f7f` (feat)
3. **Task 3: Create Whisper model constants** - `cc101b6` (feat)

## Files Created
- `frontend/src/types/upload.ts` - Type definitions for FileQueueItem, WhisperModel, LanguageCode, FileQueueItemStatus, Language, WhisperModelInfo
- `frontend/src/lib/languages.ts` - CORE_LANGUAGES (3), OTHER_LANGUAGES (13), ALL_LANGUAGES, LANGUAGE_BY_CODE lookup, getLanguageName()
- `frontend/src/lib/languageDetection.ts` - detectLanguageFromFilename() with A03/A04/A05 pattern matching
- `frontend/src/lib/whisperModels.ts` - WHISPER_MODELS (6 sizes), DEFAULT_MODEL (large-v3), getModelInfo()

## Decisions Made
- Used ASCII-safe nativeName values (e.g., "Latvieski" instead of "Latviesu") to avoid encoding issues
- Pattern detection regex `/A0[345]/i` matches anywhere in filename, case-insensitive
- LanguageCode is union type (not string) for type safety across components

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Type definitions ready for use by upload components
- Language detection ready for FileQueueItem initialization
- Model constants ready for ModelSelect dropdown component
- Build verified passing with all new files

---
*Phase: 04-core-upload-flow*
*Completed: 2026-01-27*
