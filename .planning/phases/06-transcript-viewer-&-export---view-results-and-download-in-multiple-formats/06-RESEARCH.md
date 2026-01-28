# Phase 6: Transcript Viewer & Export - Research

**Researched:** 2026-01-28
**Domain:** Transcript display and export (SRT/VTT/TXT/JSON)
**Confidence:** HIGH

## Summary

This phase adds transcript viewing and multi-format download capabilities to the WhisperX frontend. Users can view transcription results with paragraph timestamps and speaker labels, then download in SRT, VTT, plain text, or JSON formats.

The existing codebase already has the backend result structure in place. Tasks complete with a `result` field containing `segments` with `start`, `end`, `text`, and `speaker` fields. The frontend needs to:
1. Fetch completed task results via the existing `/task/{identifier}` endpoint
2. Display transcript with timestamps and speaker labels
3. Generate subtitle formats client-side (no backend changes needed)

**Primary recommendation:** Generate SRT/VTT client-side from the segments array. Use a TranscriptViewer component that expands from the FileQueueItem when complete. Download as Blobs with proper MIME types.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Native Blob API | N/A | File generation and download | Built-in, no dependencies needed for simple format generation |
| shadcn/ui Collapsible | Latest | Expand/collapse transcript view | Matches existing UI component pattern |
| shadcn/ui ScrollArea | Latest | Scrollable transcript content | Already installed in codebase |
| shadcn/ui Button | Latest | Download buttons | Already installed in codebase |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| lucide-react | Installed | Download/expand icons | Already in codebase |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Client-side generation | Backend endpoints | Adds unnecessary API complexity; formats are simple text |
| srt/webvtt-py libraries | Native string formatting | Libraries are Python-only; client-side is more efficient |
| file-saver library | Native Blob/download | No need for library; native API is sufficient |

**Installation:**
```bash
# shadcn/ui Collapsible (manual setup per project convention)
# No additional packages needed - use existing UI components
```

## Architecture Patterns

### Recommended Project Structure
```
frontend/src/
├── types/
│   └── transcript.ts        # TranscriptSegment, TranscriptResult types
├── lib/
│   └── formatters/
│       ├── srtFormatter.ts  # formatTranscriptAsSrt()
│       ├── vttFormatter.ts  # formatTranscriptAsVtt()
│       ├── txtFormatter.ts  # formatTranscriptAsTxt()
│       └── index.ts         # Export all formatters
├── hooks/
│   └── useTranscriptDownload.ts  # Download logic, blob creation
└── components/
    └── transcript/
        ├── TranscriptViewer.tsx     # Main viewer with segments
        ├── TranscriptSegment.tsx    # Single segment with speaker/timestamp
        └── DownloadButtons.tsx      # Download format buttons
```

### Pattern 1: Client-Side Format Generation
**What:** Generate subtitle formats (SRT/VTT) in the browser from segment data
**When to use:** When source data is already available client-side (completed transcripts)
**Example:**
```typescript
// Source: Standard SRT format specification
function formatTimestamp(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.round((seconds % 1) * 1000);
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')},${ms.toString().padStart(3, '0')}`;
}

function formatAsSrt(segments: TranscriptSegment[]): string {
  return segments.map((segment, index) =>
    `${index + 1}\n${formatTimestamp(segment.start)} --> ${formatTimestamp(segment.end)}\n${segment.speaker ? `[${segment.speaker}] ` : ''}${segment.text}\n`
  ).join('\n');
}
```

### Pattern 2: Blob Download Pattern
**What:** Create downloadable files from strings without server round-trip
**When to use:** For text-based file formats generated client-side
**Example:**
```typescript
// Source: MDN Blob API documentation
function downloadAsFile(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url); // Clean up to prevent memory leak
}
```

### Pattern 3: Collapsible Result View
**What:** Expand transcript details from completed queue item
**When to use:** To show full transcript without navigating away from upload queue
**Example:**
```typescript
// Use shadcn/ui Collapsible pattern
<Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
  <CollapsibleTrigger asChild>
    <Button variant="ghost" size="sm">
      {isExpanded ? <ChevronUp /> : <ChevronDown />}
      View Transcript
    </Button>
  </CollapsibleTrigger>
  <CollapsibleContent>
    <TranscriptViewer segments={result.segments} />
  </CollapsibleContent>
</Collapsible>
```

### Anti-Patterns to Avoid
- **Creating backend export endpoints:** Unnecessary complexity when formats are simple text transformations
- **Downloading JSON from API then re-downloading formatted:** Double network calls; transform client-side
- **Opening new window/tab for download:** Use Blob URL with download attribute instead
- **Not revoking Blob URLs:** Memory leak; always call URL.revokeObjectURL()

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Timestamp formatting | Custom parsing | Dedicated formatter function | Edge cases with milliseconds, padding |
| ScrollArea | Custom overflow styling | shadcn/ui ScrollArea | Already installed, consistent styling |
| Collapsible | Custom expand/collapse | shadcn/ui Collapsible | Accessibility, keyboard nav, animation |
| Text encoding | Assume UTF-8 | Blob with charset | Non-ASCII characters need proper encoding |

**Key insight:** Subtitle formats are well-defined with specific timestamp syntax. Use consistent formatter functions rather than inline string interpolation.

## Common Pitfalls

### Pitfall 1: SRT vs VTT Timestamp Differences
**What goes wrong:** Using comma for milliseconds in VTT (should be period) or vice versa in SRT
**Why it happens:** Formats look similar but have different separators
**How to avoid:** Create separate formatter functions for each format
**Warning signs:** Players show "invalid subtitle" errors

SRT: `00:01:23,456 --> 00:01:25,789`
VTT: `00:01:23.456 --> 00:01:25.789`

### Pitfall 2: Missing WEBVTT Header
**What goes wrong:** VTT files don't parse because header is missing
**Why it happens:** Assuming VTT is just SRT with different timestamps
**How to avoid:** Always include `WEBVTT` header and blank line at top
**Warning signs:** Browser HTML5 track element ignores the file

### Pitfall 3: Unicode in Downloads
**What goes wrong:** Non-ASCII characters (Latvian, Russian) appear corrupted
**Why it happens:** Not specifying UTF-8 encoding in Blob
**How to avoid:** Always use `new Blob([content], { type: 'text/plain; charset=utf-8' })`
**Warning signs:** Latvian characters (a, c, n) or Cyrillic appear as ???

### Pitfall 4: Memory Leaks from Blob URLs
**What goes wrong:** Browser memory grows with each download
**Why it happens:** Blob URLs not revoked after download completes
**How to avoid:** Call `URL.revokeObjectURL(url)` after link click
**Warning signs:** Browser becomes sluggish after many downloads

### Pitfall 5: Fetching Result Before Complete
**What goes wrong:** Null or undefined segments array
**Why it happens:** Trying to view transcript before status is 'completed'
**How to avoid:** Only enable view/download when file status is 'complete'
**Warning signs:** TypeError: Cannot read properties of undefined

## Code Examples

Verified patterns from official sources:

### SRT Format Generation
```typescript
// Source: SubRip format specification (Wikipedia)
interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
  speaker?: string;
}

function formatSrtTimestamp(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.round((seconds % 1) * 1000);
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')},${String(ms).padStart(3, '0')}`;
}

export function formatTranscriptAsSrt(segments: TranscriptSegment[]): string {
  return segments
    .map((segment, index) => {
      const prefix = segment.speaker ? `[${segment.speaker}] ` : '';
      return `${index + 1}\n${formatSrtTimestamp(segment.start)} --> ${formatSrtTimestamp(segment.end)}\n${prefix}${segment.text}`;
    })
    .join('\n\n');
}
```

### VTT Format Generation
```typescript
// Source: W3C WebVTT specification
function formatVttTimestamp(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.round((seconds % 1) * 1000);
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
}

export function formatTranscriptAsVtt(segments: TranscriptSegment[]): string {
  const header = 'WEBVTT\n\n';
  const cues = segments
    .map((segment) => {
      const prefix = segment.speaker ? `<v ${segment.speaker}>` : '';
      return `${formatVttTimestamp(segment.start)} --> ${formatVttTimestamp(segment.end)}\n${prefix}${segment.text}`;
    })
    .join('\n\n');
  return header + cues;
}
```

### Download Hook
```typescript
// Source: MDN Blob API + React patterns
export function useTranscriptDownload() {
  const downloadFile = useCallback((
    content: string,
    filename: string,
    mimeType: string
  ) => {
    const blob = new Blob([content], { type: `${mimeType}; charset=utf-8` });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, []);

  return { downloadFile };
}
```

### Fetching Task Result
```typescript
// Source: Existing app/api/task_api.py endpoint
interface TaskResult {
  status: string;
  result: {
    segments: TranscriptSegment[];
  };
  metadata: {
    file_name: string;
    language: string;
    audio_duration: number;
  };
  error: string | null;
}

export async function fetchTaskResult(taskId: string): Promise<ApiResult<TaskResult>> {
  try {
    const response = await fetch(`/task/${taskId}`);
    if (!response.ok) {
      return { success: false, error: { status: response.status, detail: 'Failed to fetch result' } };
    }
    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    return { success: false, error: { status: 0, detail: 'Network error' } };
  }
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Server-side file generation | Client-side Blob API | 2020+ | No server round-trip, faster downloads |
| window.open for downloads | Anchor element + download attribute | 2015+ | Better UX, proper filename support |
| data: URLs | Blob URLs | 2012+ | Better memory management, larger files |

**Deprecated/outdated:**
- `execCommand('SaveAs')`: Non-standard, IE-only
- Flash-based file savers: Flash is dead
- Backend file generation for simple text formats: Unnecessary complexity

## Open Questions

Things that couldn't be fully resolved:

1. **Segment grouping for transcript display**
   - What we know: Backend returns flat segment array with speaker per segment
   - What's unclear: Should segments be grouped by speaker for display? Or show each as-is?
   - Recommendation: Display as-is with speaker label; grouping is complex and may not match user expectations

2. **Maximum transcript length handling**
   - What we know: Very long transcripts (hours) could have thousands of segments
   - What's unclear: Should we virtualize the segment list? What's the performance threshold?
   - Recommendation: Start with simple ScrollArea; optimize if issues found in testing

## Sources

### Primary (HIGH confidence)
- [W3C WebVTT Specification](https://www.w3.org/TR/webvtt1/) - VTT format details
- [SubRip Wikipedia](https://en.wikipedia.org/wiki/SubRip) - SRT format specification
- [MDN Blob API](https://developer.mozilla.org/en-US/docs/Web/API/Blob) - File download pattern
- Existing codebase: `app/schemas/core_schemas.py` - Segment structure
- Existing codebase: `app/api/task_api.py` - Result endpoint

### Secondary (MEDIUM confidence)
- [shadcn/ui Accordion](https://ui.shadcn.com/docs/components/accordion) - Collapsible pattern
- [PyPI srt](https://pypi.org/project/srt/) - SRT format reference (Python library docs)
- [PyPI webvtt-py](https://pypi.org/project/webvtt-py/) - VTT format reference

### Tertiary (LOW confidence)
- N/A - All critical patterns verified with official sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Using native APIs and existing codebase patterns
- Architecture: HIGH - Direct client-side approach, no backend changes
- Format specifications: HIGH - W3C and Wikipedia specifications are authoritative
- Pitfalls: HIGH - Based on format specifications and common issues

**Research date:** 2026-01-28
**Valid until:** 2026-03-28 (60 days - stable formats, no fast-moving dependencies)
