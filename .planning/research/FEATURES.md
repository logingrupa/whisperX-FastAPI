# Feature Research: Transcription Workbench UI

**Domain:** Speech-to-text transcription web application (React frontend for WhisperX API)
**Researched:** 2026-01-27
**Confidence:** MEDIUM-HIGH (based on comprehensive competitive analysis)

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete or unusable.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **File Upload (Drag & Drop)** | Every modern transcription tool supports this - users don't want file dialogs | LOW | Standard HTML5 drag-drop API. Support common formats: MP3, WAV, MP4, MOV, M4A, FLAC, OGG |
| **Multi-File Upload** | Users often batch process recordings from meetings/interviews | LOW | Extend single-file UI with queue display |
| **Progress Indicator** | Transcription takes time; users need feedback that something is happening | MEDIUM | Must show per-file progress. WebSocket recommended for real-time updates |
| **Transcript Viewer with Timestamps** | Core deliverable - users need to see results with time references | MEDIUM | Paragraph-level timestamps minimum. Display speaker labels if available |
| **Speaker Labels/Diarization** | Expected for multi-speaker recordings (meetings, interviews, podcasts) | LOW (API provides) | Display "Speaker 1", "Speaker 2" etc. Allow manual renaming |
| **Export to SRT/VTT** | Universal subtitle formats needed for video editing workflows | LOW | SRT most widely supported; VTT for web. Both are simple text formats |
| **Export to Plain Text** | Basic format for copy/paste into documents | LOW | Strip timestamps, just clean text |
| **Language Selection** | Users need to specify or verify audio language | LOW | Dropdown with common languages. Show auto-detected language from API |
| **Basic Error Handling** | Clear messages when files fail or processing errors occur | MEDIUM | Don't erase user selections on error. Show actionable error messages |
| **Responsive Layout** | Must work on desktop and tablet at minimum | MEDIUM | Standard CSS responsive design |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable for WhisperX-specific workflow.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Auto Language Detection from Filename** | Project-specific: A03=Latvian, A04=Russian, A05=English saves manual selection for known workflows | LOW | Regex pattern matching on filenames. Show detected language, allow override |
| **Model Management UI** | Unique to self-hosted Whisper: download, switch, and monitor model status | MEDIUM | Not offered by SaaS tools (Otter, Rev). Key differentiator for power users |
| **Model Size Selector** | Let users trade accuracy vs speed (tiny/base/small/medium/large) | LOW | Dropdown with model names + expected accuracy/speed notes |
| **Real-Time WebSocket Progress** | Granular progress (not just spinning wheel) builds trust during long transcriptions | MEDIUM | WhisperX API must support progress callbacks. Show percentage + ETA |
| **Word-Level Timestamps with Click-to-Play** | Click any word to jump to that point in audio - premium editing feature | HIGH | Requires word-level timestamps from API + audio player sync. Descript/Rev have this |
| **Batch Processing Queue** | Process multiple files with queue management (pause, reorder, cancel) | MEDIUM | Goes beyond basic multi-upload to full job management |
| **JSON Export with Full Metadata** | Developer/researcher export with all available data (confidence, timestamps, speakers) | LOW | Serialize full API response. Useful for NVivo, ATLAS.ti integration |
| **Custom Dictionary/Vocabulary** | Improve accuracy for domain-specific terms, names, acronyms | HIGH | Requires WhisperX API support. Sonix/Trint offer this |
| **Confidence Scores Display** | Show per-word confidence to flag potential errors for review | MEDIUM | Sonix does this well. Helps prioritize manual review effort |
| **Dark Mode** | Developer preference, reduces eye strain for long editing sessions | LOW | CSS variables for theme switching |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems. Deliberately NOT building these.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Real-Time Live Transcription** | "Otter does it!" | Requires streaming audio + different Whisper mode. Complex, different use case. WhisperX optimized for batch, not real-time | Focus on fast batch processing. Real-time is v2+ if demand proven |
| **In-App Audio/Video Recording** | "Record directly in browser" | Browser recording quality varies. MediaRecorder API has format issues. Users have better recording tools | Accept file uploads only. Recording is a separate concern |
| **Inline Transcript Editing** | "Let me fix mistakes in place" | Complex state management, undo/redo, sync with timestamps. Major engineering effort | Export to text editor. Consider v2 with Slate.js or ProseMirror |
| **User Accounts & Authentication** | "Save my transcripts" | Adds backend complexity, data storage, privacy concerns. Not needed for local tool | Session-based storage. Export files for persistence |
| **Automatic Meeting Bot Join** | "Join my Zoom like Otter" | Requires separate bot infrastructure, calendar integration. Completely different product | Users record meetings, then upload |
| **AI Summarization/Chat** | "Ask questions about transcript" | Requires LLM integration, adds latency, scope creep. Otter/Descript territory | Clean transcript export. Users can paste into ChatGPT |
| **Video Player with Transcript Sync** | "Watch video while reading" | Video handling complex. HTML5 video has format issues. Large files strain browser | Audio player only for click-to-play. Video editing in dedicated tools |
| **Multi-Language in Same File** | "My interview switches between English and Spanish" | Whisper struggles with code-switching. Unreliable results | Transcribe as primary language. Note limitation in docs |
| **Human Transcription Fallback** | "Send to human if accuracy low" | Requires marketplace/contractor management. Different business model | Export to Rev/GoTranscript for human review if needed |

## Feature Dependencies

```
[Drag-Drop Upload]
    |
    v
[Progress Indicator] ----requires----> [WebSocket Connection]
    |
    v
[Transcript Viewer]
    |-- requires --> [Speaker Labels] (from API)
    |-- requires --> [Timestamps] (from API)
    |-- enhances --> [Click-to-Play] --> requires --> [Audio Player]
    |
    v
[Export (SRT/VTT/TXT/JSON)]

[Model Management]
    |-- requires --> [Model Download Progress]
    |-- enhances --> [Model Size Selector]

[Auto Language from Filename]
    |-- enhances --> [Language Selection]
    |-- independent of other features

[Batch Queue]
    |-- extends --> [Multi-File Upload]
    |-- requires --> [Progress Indicator]
```

### Dependency Notes

- **Progress Indicator requires WebSocket:** HTTP polling is insufficient for long transcriptions. WebSocket provides real-time updates without hammering the server
- **Click-to-Play requires Audio Player + Word Timestamps:** This is the most complex feature chain. Needs API to return word-level timing and frontend audio synchronization
- **Export requires Transcript Viewer:** User must see results before exporting (or export all from batch queue)
- **Model Management is independent:** Can be built as separate admin panel, not blocking core transcription flow

## MVP Definition

### Launch With (v1)

Minimum viable product - what's needed to validate the concept.

- [x] **Drag-drop file upload** - core interaction pattern
- [x] **Single and multi-file support** - handle common batch workflows
- [x] **Progress indicator via WebSocket** - trust-building feedback during processing
- [x] **Language selection with auto-detection from filename** - project-specific differentiator (A03/A04/A05 pattern)
- [x] **Transcript viewer with speaker labels and timestamps** - core deliverable
- [x] **Export to SRT, VTT, TXT, JSON** - cover common export needs
- [x] **Model selection dropdown** - let users choose accuracy/speed tradeoff
- [x] **Basic error handling** - graceful failures with clear messages

### Add After Validation (v1.x)

Features to add once core is working and users provide feedback.

- [ ] **Model download manager** - when users want to add new models
- [ ] **Click-to-play word navigation** - when users do heavy editing
- [ ] **Batch queue management** - when users process large volumes
- [ ] **Confidence score display** - when accuracy review is priority
- [ ] **Dark mode** - when requested

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] **Inline transcript editing** - significant engineering effort, needs clear demand
- [ ] **Custom vocabulary/dictionary** - requires API support investigation
- [ ] **Real-time streaming transcription** - different architecture, different use case
- [ ] **Audio waveform visualization** - nice-to-have for pro editing

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Drag-drop upload | HIGH | LOW | **P1** |
| Progress indicator (WebSocket) | HIGH | MEDIUM | **P1** |
| Transcript viewer + timestamps | HIGH | MEDIUM | **P1** |
| Speaker labels display | HIGH | LOW | **P1** |
| Export SRT/VTT/TXT/JSON | HIGH | LOW | **P1** |
| Language selection | HIGH | LOW | **P1** |
| Auto-language from filename | MEDIUM | LOW | **P1** |
| Model selection | MEDIUM | LOW | **P1** |
| Multi-file upload | MEDIUM | LOW | **P1** |
| Error handling | HIGH | MEDIUM | **P1** |
| Model download manager | MEDIUM | MEDIUM | **P2** |
| Click-to-play | MEDIUM | HIGH | **P2** |
| Batch queue management | MEDIUM | MEDIUM | **P2** |
| Confidence scores | LOW | MEDIUM | **P2** |
| Dark mode | LOW | LOW | **P3** |
| Inline editing | HIGH | HIGH | **P3** |

**Priority key:**
- P1: Must have for launch (core transcription workflow)
- P2: Should have, add when possible (power user features)
- P3: Nice to have, future consideration (scope creep risk)

## Competitor Feature Analysis

| Feature | Otter.ai | Descript | Rev.com | Sonix | Our Approach |
|---------|----------|----------|---------|-------|--------------|
| File upload | Yes | Yes | Yes | Yes | Yes (drag-drop + multi-file) |
| Real-time transcription | Yes (live) | No | No | No | No (batch focus) |
| Speaker diarization | Yes | Yes | Yes | Yes | Yes (WhisperX provides) |
| Word-level timestamps | Yes | Yes | Yes | Yes | Yes (P2 click-to-play) |
| Inline editing | Yes | Yes (text=video) | Yes | Yes | No (export to editor) |
| SRT/VTT export | Yes | Yes | Yes | Yes | Yes |
| Model selection | N/A (cloud) | N/A | N/A | N/A | **Yes (differentiator)** |
| Custom vocabulary | Yes | Yes | No | Yes | No (v2+) |
| Confidence scores | No | No | No | Yes | P2 |
| Price | $10-20/mo | $12-24/mo | $0.25/min | $10/hr | Free (self-hosted) |

**Our competitive position:** We trade cloud convenience for local control. Users who want model selection, privacy (no cloud upload), and no per-minute costs will choose us. We don't compete on real-time or collaboration features.

## UX Patterns to Follow

Based on competitive analysis, these patterns are proven:

1. **Clean dashboard on login** (Otter) - Recent transcriptions prominent, clear "Upload" CTA
2. **Minimal learning curve** (Otter) - Drag file, see progress, get result
3. **Timestamps at paragraph level** (Rev) - Clickable to jump to audio position
4. **Speaker labels with color coding** - Visual distinction between speakers
5. **Progress with percentage + ETA** - Not just spinner, actual feedback
6. **Export button always visible** - Don't bury export in menus
7. **State indicators** (Syncfusion pattern) - Inactive/Listening/Processing/Complete states clearly shown

## UX Anti-Patterns to Avoid

1. **Don't erase form data on errors** - If one file fails, don't clear the queue
2. **Don't hide navigation in hamburger** - Key actions visible, not buried
3. **Don't require account creation** - Tool should work immediately
4. **Don't show raw API errors** - Translate to human-readable messages
5. **Don't auto-play audio** - Let users initiate playback
6. **Don't use confusing state labels** - "Processing" not "Syncing" or jargon

## Sources

### Transcription Software Reviews & Comparisons
- [Reduct.video: 8 Best Transcription Software](https://reduct.video/blog/transcription-software-for-video/)
- [Sonix: Trint vs Rev vs Sonix Comparison](https://sonix.ai/resources/trint-vs-rev-vs-sonix/)
- [Cybernews: Otter AI Review 2026](https://cybernews.com/ai-tools/otter-ai-review/)
- [All About AI: Descript AI Review](https://www.allaboutai.com/ai-reviews/descript-ai/)

### Feature-Specific Research
- [AssemblyAI: Speaker Diarization Guide](https://www.assemblyai.com/blog/what-is-speaker-diarization-and-how-does-it-work)
- [Sonix: VTT to SRT Conversion](https://sonix.ai/resources/how-to-convert-vtt-to-srt/)
- [Rev: Transcript Editor Guide](https://www.rev.com/blog/rev-transcript-editor-guide)
- [ElevenLabs: Audio to Text with Word Timestamps](https://elevenlabs.io/audio-to-text)

### Progress & State Indicators
- [GitHub: Whisper Progress Bar Discussion](https://github.com/openai/whisper/discussions/850)
- [GitHub: Easy Whisper UI](https://github.com/mehtabmahir/easy-whisper-ui/releases)
- [Syncfusion: SpeechToText Control](https://www.syncfusion.com/javascript-ui-controls/js-speech-to-text)

### Language Detection
- [AssemblyAI: Automatic Language Detection](https://www.assemblyai.com/automatic-language-detection)
- [Speechmatics: Language Identification](https://docs.speechmatics.com/speech-to-text/batch/language-identification)
- [Google Cloud: Speech-to-Text Multiple Languages](https://cloud.google.com/speech-to-text/v2/docs/multiple-languages)

### Model Management UX
- [GitHub: Open-Whispr Model Management](https://github.com/HeroTools/open-whispr)
- [GitHub: WhisperScript Discussion](https://github.com/openai/whisper/discussions/1028)

### UX Anti-Patterns
- [UI Patterns: User Interface Anti-Patterns](https://ui-patterns.com/blog/User-Interface-AntiPatterns)
- [IdeaPeel: 11 Common UI/UX Design Mistakes](https://www.ideapeel.com/blogs/ui-ux-design-mistakes-how-to-fix-them)

---
*Feature research for: WhisperX Transcription Workbench UI*
*Researched: 2026-01-27*
*Confidence: MEDIUM-HIGH*
