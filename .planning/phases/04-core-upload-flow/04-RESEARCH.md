# Phase 4: Core Upload Flow - Research

**Researched:** 2026-01-27
**Domain:** React file upload UI with drag-and-drop, shadcn/ui components
**Confidence:** HIGH

## Summary

This phase implements a file upload interface with drag-and-drop functionality, file queue management, language auto-detection from filename patterns, and Whisper model selection. The research focused on three main domains: (1) drag-and-drop file upload in React, (2) shadcn/ui component library for UI elements, and (3) the Whisper model ecosystem for model selection options.

The standard approach uses **react-dropzone** for drag-and-drop file handling (the de facto standard in React), combined with **shadcn/ui components** (Button, Select, Badge, Card, Tooltip, Sonner toast) for the UI. The project already has Tailwind v4 and Vite configured with path aliases, but shadcn/ui needs to be initialized.

**Primary recommendation:** Use react-dropzone with `noClick: true` for full-page drop target, shadcn/ui components for all UI elements, and a simple useState-based file queue (no external state library needed for this scope).

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| [react-dropzone](https://github.com/react-dropzone/react-dropzone) | ^14.x | Drag-and-drop file handling | De facto standard for React file uploads, 10K+ GitHub stars, hooks-based API, handles all browser quirks |
| [shadcn/ui](https://ui.shadcn.com) | latest | UI component library | User decision: "shadcn/ui + Radix components only" |
| [sonner](https://sonner.emilkowal.ski) | ^1.x | Toast notifications | Official shadcn/ui toast solution (replaced deprecated toast component) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| lucide-react | ^0.x | Icons | Installed with shadcn/ui, use for X buttons, file icons |
| class-variance-authority | ^0.x | Component variants | Installed with shadcn/ui, already configured |
| clsx + tailwind-merge | latest | Class merging | Installed with shadcn/ui, use `cn()` utility |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| react-dropzone | Native HTML5 DnD | react-dropzone handles browser inconsistencies, especially Safari/IE edge cases |
| Zustand for queue | useState | File queue is local to upload page, no global state needed; useState is simpler |
| Custom dropzone | shadcn-dropzone community | Community component adds dependencies; react-dropzone + custom UI is more flexible |

**Installation:**
```bash
# From frontend/ directory
bun add react-dropzone
bunx shadcn@latest init
bunx shadcn@latest add button select badge card tooltip sonner scroll-area
```

## Architecture Patterns

### Recommended Project Structure
```
frontend/src/
├── components/
│   ├── ui/                      # shadcn/ui components (auto-generated)
│   │   ├── button.tsx
│   │   ├── select.tsx
│   │   ├── badge.tsx
│   │   ├── card.tsx
│   │   ├── tooltip.tsx
│   │   ├── sonner.tsx
│   │   └── scroll-area.tsx
│   └── upload/                  # Upload-specific components
│       ├── UploadDropzone.tsx   # Full-page drop target
│       ├── FileQueueList.tsx    # Queue display
│       ├── FileQueueItem.tsx    # Individual file in queue
│       ├── LanguageSelect.tsx   # Language dropdown
│       └── ModelSelect.tsx      # Whisper model dropdown
├── hooks/
│   └── useFileQueue.ts          # File queue state management
├── lib/
│   ├── utils.ts                 # cn() utility (shadcn/ui)
│   └── languageDetection.ts     # Filename pattern matching
├── types/
│   └── upload.ts                # FileQueueItem, Language, Model types
└── App.tsx
```

### Pattern 1: Full-Page Drop Target with noClick
**What:** Use react-dropzone with `noClick: true` to make the entire page a drop zone while keeping a separate "Select files" button.
**When to use:** When you want drag-and-drop anywhere on the page without click-to-open on the whole page.
**Example:**
```typescript
// Source: https://github.com/react-dropzone/react-dropzone
import { useDropzone } from 'react-dropzone';

function UploadDropzone({ onFilesAdded }: { onFilesAdded: (files: File[]) => void }) {
  const { getRootProps, getInputProps, open, isDragActive } = useDropzone({
    noClick: true,  // Disable click on root, use button instead
    accept: {
      'audio/*': ['.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac'],
      'video/*': ['.mp4', '.webm', '.mov', '.avi', '.mkv'],
    },
    onDrop: (acceptedFiles, fileRejections) => {
      if (fileRejections.length > 0) {
        toast.error('Some files were rejected. Only audio/video files are allowed.');
      }
      if (acceptedFiles.length > 0) {
        onFilesAdded(acceptedFiles);
      }
    },
  });

  return (
    <div {...getRootProps()} className="min-h-screen relative">
      <input {...getInputProps()} />

      {/* Drag overlay */}
      {isDragActive && (
        <div className="fixed inset-0 bg-primary/10 z-50 flex items-center justify-center">
          <p className="text-2xl font-medium">Drop files here</p>
        </div>
      )}

      {/* Always-visible button */}
      <Button onClick={open}>Select files</Button>

      {/* Rest of page content */}
    </div>
  );
}
```

### Pattern 2: File Queue with Per-File Settings
**What:** Each file in queue has its own language and model settings.
**When to use:** User decision: "Per-file language setting" and "Per-file model selection".
**Example:**
```typescript
// Source: Phase 4 context decisions
interface FileQueueItem {
  id: string;
  file: File;
  detectedLanguage: string | null;
  selectedLanguage: string;
  selectedModel: WhisperModel;
  status: 'pending' | 'processing' | 'complete' | 'error';
}

function useFileQueue() {
  const [queue, setQueue] = useState<FileQueueItem[]>([]);

  const addFiles = (files: File[]) => {
    const newItems = files.map(file => ({
      id: crypto.randomUUID(),
      file,
      detectedLanguage: detectLanguageFromFilename(file.name),
      selectedLanguage: detectLanguageFromFilename(file.name) || '',
      selectedModel: 'large-v3' as WhisperModel,
      status: 'pending' as const,
    }));
    setQueue(prev => [...prev, ...newItems]);
  };

  const removeFile = (id: string) => {
    setQueue(prev => prev.filter(item => item.id !== id));
  };

  const clearQueue = () => {
    setQueue(prev => prev.filter(item => item.status === 'processing'));
  };

  const updateFileSettings = (id: string, updates: Partial<FileQueueItem>) => {
    setQueue(prev => prev.map(item =>
      item.id === id ? { ...item, ...updates } : item
    ));
  };

  return { queue, addFiles, removeFile, clearQueue, updateFileSettings };
}
```

### Pattern 3: Language Detection from Filename
**What:** Extract language code from filename pattern (A03=Latvian, A04=Russian, A05=English).
**When to use:** User-specified requirement for auto-detection.
**Example:**
```typescript
// Source: Phase 4 context - detection pattern
const LANGUAGE_PATTERNS: Record<string, string> = {
  'A03': 'lv', // Latvian
  'A04': 'ru', // Russian
  'A05': 'en', // English
};

function detectLanguageFromFilename(filename: string): string | null {
  // Match patterns like "A03", "A04", "A05" anywhere in filename
  const match = filename.match(/A0[345]/i);
  if (match) {
    return LANGUAGE_PATTERNS[match[0].toUpperCase()] || null;
  }
  return null;
}
```

### Anti-Patterns to Avoid
- **Wrapping each Tooltip individually with TooltipProvider:** Causes performance issues. Place one TooltipProvider at root layout level.
- **Using `getRootProps()` without passing custom props through it:** Your custom props get overridden. Always pass props through: `getRootProps({ onClick: handler })`.
- **Validating file types only client-side:** Always validate on server too. Users can bypass client validation.
- **Using `<label>` as dropzone root with react-dropzone:** Opens file dialog twice. Use `<div>` or set `noClick: true`.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Drag-and-drop file handling | Custom DnD with HTML5 events | react-dropzone | Browser inconsistencies (Safari, IE), DataTransfer quirks, accessibility |
| Toast notifications | Custom toast system | Sonner (via shadcn/ui) | Animation, stacking, ARIA, auto-dismiss timing |
| Select dropdowns | Custom select with `<div>` | shadcn/ui Select (Radix) | Keyboard navigation, focus management, portal rendering |
| Tooltips | Title attribute or custom | shadcn/ui Tooltip (Radix) | Proper positioning, delay handling, accessibility |
| File type icons | Custom icon mapping | lucide-react icons | Comprehensive icon set, consistent styling |

**Key insight:** Browser file handling has many edge cases (MIME type detection varies by OS, DataTransfer behaves differently during drag vs drop). react-dropzone abstracts these issues.

## Common Pitfalls

### Pitfall 1: MIME Type Unreliability
**What goes wrong:** File type detection varies by platform. CSV is `text/plain` on macOS but `application/vnd.ms-excel` on Windows.
**Why it happens:** Browsers use OS-level MIME type associations, which differ.
**How to avoid:** Use both MIME type wildcards AND file extensions in `accept`:
```typescript
accept: {
  'audio/*': ['.mp3', '.wav', '.m4a'],
  'video/*': ['.mp4', '.webm', '.mov'],
}
```
**Warning signs:** Files rejected on some platforms but not others.

### Pitfall 2: Missing Rejection Handling
**What goes wrong:** Users drop invalid files, nothing happens, no feedback.
**Why it happens:** Only handling `acceptedFiles`, ignoring `fileRejections` in onDrop.
**How to avoid:** Always handle both:
```typescript
onDrop: (acceptedFiles, fileRejections) => {
  if (fileRejections.length > 0) {
    toast.error(`${fileRejections.length} file(s) rejected. Only audio/video allowed.`);
  }
  // process acceptedFiles
}
```
**Warning signs:** Users complaining "upload doesn't work" when dropping wrong file types.

### Pitfall 3: Double File Dialog
**What goes wrong:** File picker opens twice when clicking dropzone.
**Why it happens:** Using `<label>` as root element, or having nested clickable elements.
**How to avoid:** Use `noClick: true` and a separate button with `open()` function.
**Warning signs:** Two file dialogs appearing on click.

### Pitfall 4: Tooltip Performance
**What goes wrong:** Tooltips are slow to appear, laggy UI.
**Why it happens:** Wrapping each tooltip with its own `<TooltipProvider>`.
**How to avoid:** Single `<TooltipProvider>` at app root level.
**Warning signs:** Noticeable delay before tooltips show, especially with many tooltips.

### Pitfall 5: Queue State During Processing
**What goes wrong:** User removes file that's currently processing, causing errors.
**Why it happens:** Remove button doesn't check status before removing.
**How to avoid:** User decision: "Files can only be removed before processing starts." Disable remove button when status !== 'pending'.
**Warning signs:** Console errors, orphaned upload requests.

## Code Examples

Verified patterns from official sources:

### shadcn/ui Select with Grouped Items
```typescript
// Source: https://ui.shadcn.com/docs/components/select
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

function LanguageSelect({ value, onValueChange }: {
  value: string;
  onValueChange: (value: string) => void
}) {
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger className="w-[140px]">
        <SelectValue placeholder="Select language" />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          <SelectLabel>Primary</SelectLabel>
          <SelectItem value="lv">Latvian</SelectItem>
          <SelectItem value="ru">Russian</SelectItem>
          <SelectItem value="en">English</SelectItem>
        </SelectGroup>
        <SelectGroup>
          <SelectLabel>Other</SelectLabel>
          <SelectItem value="de">German</SelectItem>
          <SelectItem value="fr">French</SelectItem>
          <SelectItem value="es">Spanish</SelectItem>
          {/* ... more languages */}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}
```

### shadcn/ui Badge with Tooltip
```typescript
// Source: https://ui.shadcn.com/docs/components/badge, tooltip
import { Badge } from "@/components/ui/badge"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

function DetectedLanguageBadge({ language }: { language: string }) {
  const languageNames: Record<string, string> = {
    lv: 'Latvian',
    ru: 'Russian',
    en: 'English',
  };

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="secondary">
          {languageNames[language] || language}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>
        <p>Detected from filename pattern</p>
      </TooltipContent>
    </Tooltip>
  );
}
```

### Sonner Toast for Rejections
```typescript
// Source: https://ui.shadcn.com/docs/components/sonner
import { toast } from "sonner"

// In onDrop callback
if (fileRejections.length > 0) {
  const rejectedNames = fileRejections.map(r => r.file.name).slice(0, 3);
  toast.error('Invalid files rejected', {
    description: `${rejectedNames.join(', ')}${fileRejections.length > 3 ? '...' : ''} - Only audio/video files allowed`,
  });
}
```

### Whisper Model Select
```typescript
// Source: https://github.com/openai/whisper (model specs)
type WhisperModel = 'tiny' | 'base' | 'small' | 'medium' | 'large-v3' | 'turbo';

const WHISPER_MODELS: { value: WhisperModel; label: string; description: string }[] = [
  { value: 'tiny', label: 'Tiny', description: '39M params, ~1GB VRAM, fastest' },
  { value: 'base', label: 'Base', description: '74M params, ~1GB VRAM' },
  { value: 'small', label: 'Small', description: '244M params, ~2GB VRAM' },
  { value: 'medium', label: 'Medium', description: '769M params, ~5GB VRAM' },
  { value: 'large-v3', label: 'Large v3', description: '1.5B params, ~10GB VRAM, most accurate' },
  { value: 'turbo', label: 'Turbo', description: '809M params, ~6GB VRAM, fast + accurate' },
];

function ModelSelect({ value, onValueChange }: {
  value: WhisperModel;
  onValueChange: (value: WhisperModel) => void;
}) {
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger className="w-[160px]">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {WHISPER_MODELS.map(model => (
          <SelectItem key={model.value} value={model.value}>
            {model.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| shadcn/ui Toast component | Sonner | 2024 | Toast component deprecated, Sonner is now official |
| @tailwind directives | @import "tailwindcss" | Tailwind v4 (2024) | CSS-first syntax, no postcss.config needed |
| react-beautiful-dnd | pragmatic-drag-and-drop or dnd-kit | 2023 | Atlassian stopped maintaining react-beautiful-dnd |
| Individual TooltipProviders | Single root TooltipProvider | 2024 | Performance improvement |

**Deprecated/outdated:**
- shadcn/ui Toast component: Replaced by Sonner
- @tailwind base/components/utilities: Use @import "tailwindcss" in Tailwind v4
- react-beautiful-dnd: Unmaintained, use hello-pangea/dnd fork or dnd-kit

## Open Questions

Things that couldn't be fully resolved:

1. **Large file handling limits**
   - What we know: react-dropzone handles file selection fine, but actual upload limits depend on backend
   - What's unclear: Max file size for transcription? Memory limits?
   - Recommendation: Add client-side file size validation, coordinate with backend team on limits

2. **Exact language list beyond core 3**
   - What we know: User wants "core 3 plus top 10-15 common languages"
   - What's unclear: Exact list of which 10-15 languages
   - Recommendation: Start with ISO 639-1 codes for most common: de, fr, es, it, pt, nl, pl, ja, ko, zh, ar, hi, tr

3. **Error states for language detection failures**
   - What we know: "Language required before processing (force user selection if detection fails)"
   - What's unclear: Exact UI for forcing selection
   - Recommendation: Disable "Start" button until language is selected; show warning badge

## Sources

### Primary (HIGH confidence)
- [shadcn/ui Sonner docs](https://ui.shadcn.com/docs/components/sonner) - Toast notification setup
- [shadcn/ui Select docs](https://ui.shadcn.com/docs/components/select) - Select component API
- [shadcn/ui Badge docs](https://ui.shadcn.com/docs/components/badge) - Badge variants
- [shadcn/ui Tooltip docs](https://ui.shadcn.com/docs/components/tooltip) - Tooltip provider pattern
- [shadcn/ui Button docs](https://ui.shadcn.com/docs/components/button) - Button variants/sizes
- [shadcn/ui Card docs](https://ui.shadcn.com/docs/components/card) - Card component structure
- [shadcn/ui Vite installation](https://ui.shadcn.com/docs/installation/vite) - Init and setup
- [react-dropzone GitHub](https://github.com/react-dropzone/react-dropzone) - useDropzone API, accept prop format
- [OpenAI Whisper GitHub](https://github.com/openai/whisper) - Model sizes and specs

### Secondary (MEDIUM confidence)
- [MDN accept attribute](https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/accept) - MIME type formats
- [Puck drag-and-drop comparison](https://puckeditor.com/blog/top-5-drag-and-drop-libraries-for-react) - Library comparison 2026
- [TooltipProvider performance issue](https://github.com/shadcn-ui/ui/issues/7166) - Single provider pattern

### Tertiary (LOW confidence)
- Various Medium/DEV.to articles on react-dropzone patterns - Community patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - shadcn/ui and react-dropzone are well-documented, official sources
- Architecture: HIGH - Patterns verified from official docs and user decisions
- Pitfalls: MEDIUM - Some from GitHub issues, some from community articles

**Research date:** 2026-01-27
**Valid until:** 2026-02-27 (30 days - stable ecosystem)
