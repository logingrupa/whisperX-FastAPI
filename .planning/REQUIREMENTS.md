# Requirements: WhisperX Frontend UI

**Defined:** 2026-01-27
**Core Value:** Users can easily upload audio, transcribe with speaker identification, and export results — without touching the command line or API directly.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Upload

- [ ] **UPLD-01**: User can drag-and-drop audio/video files onto upload zone
- [ ] **UPLD-02**: User can select files via file picker dialog
- [ ] **UPLD-03**: User can upload multiple files at once with queue display
- [ ] **UPLD-04**: System validates file format (MP3, WAV, MP4, MOV, M4A, FLAC, OGG)
- [ ] **UPLD-05**: System auto-detects language from filename pattern (A03=Latvian, A04=Russian, A05=English)

### Progress

- [ ] **PROG-01**: User sees real-time progress via WebSocket (percentage, current stage)
- [ ] **PROG-02**: User sees which stage is active (Uploading, Queued, Transcribing, Aligning, Diarizing, Complete)
- [ ] **PROG-03**: User sees clear error messages when processing fails

### Transcript Viewer

- [ ] **VIEW-01**: User can view transcript with paragraph-level timestamps
- [ ] **VIEW-02**: User can see speaker labels (Speaker 1, Speaker 2, etc.)

### Downloads

- [ ] **DOWN-01**: User can download transcript as SRT file
- [ ] **DOWN-02**: User can download transcript as VTT file
- [ ] **DOWN-03**: User can download transcript as plain text file
- [ ] **DOWN-04**: User can download transcript as JSON with full metadata

### Language & Model

- [ ] **LANG-01**: User can select transcription language from dropdown
- [ ] **LANG-02**: User can select Whisper model size (tiny/base/small/medium/large)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Model Management

- **MODL-01**: User can view list of available/downloaded models
- **MODL-02**: User can download new models from UI
- **MODL-03**: User can see model download progress

### Advanced Viewer

- **ADVW-01**: User can see confidence scores per word/segment
- **ADVW-02**: User can click word to jump to audio position (click-to-play)

### Batch Processing

- **BTCH-01**: User can pause/resume batch queue
- **BTCH-02**: User can reorder items in queue
- **BTCH-03**: User can cancel individual items in queue

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Real-time live transcription | Different architecture, WhisperX optimized for batch processing |
| User authentication | Internal/trusted use, no multi-tenancy needed |
| Mobile app | Web-first, desktop/tablet focus |
| Audio/video editing | Transcription only, not an editor |
| Inline transcript editing | Complex state management (undo/redo, timestamp sync), export to editor instead |
| Video player with transcript sync | HTML5 video complexity, format issues |
| Custom vocabulary/dictionary | Requires API support investigation |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| UPLD-01 | — | Pending |
| UPLD-02 | — | Pending |
| UPLD-03 | — | Pending |
| UPLD-04 | — | Pending |
| UPLD-05 | — | Pending |
| PROG-01 | — | Pending |
| PROG-02 | — | Pending |
| PROG-03 | — | Pending |
| VIEW-01 | — | Pending |
| VIEW-02 | — | Pending |
| DOWN-01 | — | Pending |
| DOWN-02 | — | Pending |
| DOWN-03 | — | Pending |
| DOWN-04 | — | Pending |
| LANG-01 | — | Pending |
| LANG-02 | — | Pending |

**Coverage:**
- v1 requirements: 16 total
- Mapped to phases: 0
- Unmapped: 16 ⚠️

---
*Requirements defined: 2026-01-27*
*Last updated: 2026-01-27 after initial definition*
