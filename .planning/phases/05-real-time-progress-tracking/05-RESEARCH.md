# Phase 5: Real-Time Progress Tracking - Research

**Researched:** 2026-01-27
**Domain:** React WebSocket hooks, progress UI components, reconnection strategies
**Confidence:** HIGH

## Summary

This phase implements the frontend WebSocket client for displaying real-time transcription progress. The backend WebSocket infrastructure was completed in Phase 1, including the `/ws/tasks/{task_id}` endpoint, heartbeat mechanism (30s interval), progress emission at stages (queued, transcribing, aligning, diarizing, complete), and a polling fallback endpoint (`GET /tasks/{task_id}/progress`).

The frontend implementation requires: (1) a custom WebSocket hook with reconnection and exponential backoff, (2) progress display components using shadcn/ui Progress and Badge, (3) smooth CSS animations for progress updates, (4) error handling with toast notifications and inline error states.

The standard approach uses **react-use-websocket** for WebSocket management (handles reconnection, message queueing, connection state), shadcn/ui **Progress** component for the progress bar, and custom **Badge** color variants for per-stage indicators. The project already has shadcn/ui installed with all required components (Button, Badge, Card, Tooltip, Sonner), plus lucide-react for icons.

**Primary recommendation:** Use react-use-websocket with custom reconnection configuration (5 attempts, exponential backoff), shadcn/ui Progress component with CSS transition for smooth animation, and extend the existing Badge component with stage-specific color variants (blue/yellow/green/red per CONTEXT.md).

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| [react-use-websocket](https://github.com/robtaussig/react-use-websocket) | ^4.x | WebSocket connection management | De facto standard React WebSocket hook, handles reconnection, message queueing, connection state, 1.2K+ GitHub stars |
| [shadcn/ui Progress](https://ui.shadcn.com/docs/components/progress) | latest (installed) | Progress bar display | User decision: "shadcn/ui + Radix components only" |
| [shadcn/ui Badge](https://ui.shadcn.com/docs/components/badge) | latest (installed) | Stage indicator badges | Already installed in Phase 4, supports custom color variants |
| [Sonner](https://sonner.emilkowal.ski) | ^2.0.7 (installed) | Toast notifications | Already installed in Phase 4, official shadcn/ui toast solution |
| [lucide-react](https://lucide.dev) | ^0.563.0 (installed) | Icons (Loader2 for spinner) | Already installed with shadcn/ui |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Loader2 (lucide-react) | installed | Animated spinner | Use with `animate-spin` Tailwind class during processing |
| CheckCircle2 (lucide-react) | installed | Success icon | Display when status is 'complete' |
| AlertCircle (lucide-react) | installed | Error icon | Display when status is 'error' |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| react-use-websocket | Native WebSocket API | Native requires manual reconnection, message queueing, state tracking |
| react-use-websocket | Socket.IO | Socket.IO is heavier, backend uses native WebSocket not Socket.IO |
| Custom hook | @gamestdio/websocket | react-use-websocket has better React integration, more features |

**Installation:**
```bash
# From frontend/ directory
bun add react-use-websocket
bunx shadcn@latest add progress
```

## Architecture Patterns

### Recommended Project Structure
```
frontend/src/
├── components/
│   ├── ui/
│   │   └── progress.tsx          # shadcn/ui progress (to be added)
│   └── upload/
│       ├── FileQueueItem.tsx     # Modify to show progress
│       └── ProgressIndicator.tsx # New: Progress bar + stage badge
├── hooks/
│   ├── useFileQueue.ts          # Existing: Add progress tracking
│   └── useTaskProgress.ts       # New: WebSocket progress subscription
├── types/
│   └── upload.ts                # Extend with ProgressStage enum
└── lib/
    └── progressStages.ts        # Stage definitions, colors, labels
```

### Pattern 1: WebSocket Hook with Reconnection
**What:** Custom hook wrapping react-use-websocket with project-specific configuration for reconnection and state sync.
**When to use:** For all WebSocket connections to the backend.
**Example:**
```typescript
// Source: react-use-websocket docs + Phase 5 CONTEXT.md decisions
import useWebSocket, { ReadyState } from 'react-use-websocket';

interface UseTaskProgressOptions {
  taskId: string;
  onProgress?: (percentage: number, stage: string) => void;
  onError?: (errorCode: string, userMessage: string) => void;
  onComplete?: () => void;
}

export function useTaskProgress({ taskId, onProgress, onError, onComplete }: UseTaskProgressOptions) {
  const socketUrl = `/ws/tasks/${taskId}`;

  const { lastJsonMessage, readyState, getWebSocket } = useWebSocket(socketUrl, {
    shouldReconnect: (closeEvent) => {
      // Don't reconnect on normal closure or if task is complete
      return closeEvent.code !== 1000;
    },
    reconnectAttempts: 5,
    reconnectInterval: (attemptNumber) =>
      Math.min(1000 * Math.pow(2, attemptNumber), 30000), // Exponential backoff, max 30s
    onOpen: () => {
      // Fetch current state on reconnect to sync missed updates
      fetchCurrentProgress(taskId);
    },
    onMessage: (event) => {
      const message = JSON.parse(event.data);
      if (message.type === 'progress') {
        onProgress?.(message.percentage, message.stage);
      } else if (message.type === 'error') {
        onError?.(message.error_code, message.user_message);
      }
    },
  });

  const connectionState = {
    isConnected: readyState === ReadyState.OPEN,
    isConnecting: readyState === ReadyState.CONNECTING,
    isReconnecting: readyState === ReadyState.CONNECTING && /* after disconnect */,
    isClosed: readyState === ReadyState.CLOSED,
  };

  return { connectionState, lastJsonMessage, getWebSocket };
}
```

### Pattern 2: Progress Bar with Smooth Animation
**What:** Progress bar that animates smoothly between percentage updates using CSS transitions.
**When to use:** For the file progress display (per CONTEXT.md: "Smooth animation between percentage updates").
**Example:**
```typescript
// Source: shadcn/ui Progress + CSS transitions research
import { Progress } from '@/components/ui/progress';

interface FileProgressProps {
  percentage: number;
  stage: ProgressStage;
}

// CSS in globals.css or component:
// .progress-indicator [data-slot="indicator"] {
//   transition: width 500ms ease-out;
// }

export function FileProgress({ percentage, stage }: FileProgressProps) {
  return (
    <div className="flex items-center gap-2">
      <Progress
        value={percentage}
        className="flex-1 progress-indicator"
      />
      <span className="text-sm text-muted-foreground w-10 text-right">
        {percentage}%
      </span>
    </div>
  );
}
```

### Pattern 3: Stage Badge with Per-Stage Colors
**What:** Badge component showing current stage with color coded by stage type.
**When to use:** Per CONTEXT.md: "Different badge color per stage (Upload=blue, Processing=yellow, Complete=green, Error=red)".
**Example:**
```typescript
// Source: shadcn/ui Badge + CONTEXT.md decisions
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

type ProgressStage = 'uploading' | 'queued' | 'transcribing' | 'aligning' | 'diarizing' | 'complete' | 'error';

const STAGE_CONFIG: Record<ProgressStage, { label: string; color: string; step: number }> = {
  uploading: { label: 'Uploading', color: 'bg-blue-500 text-white', step: 1 },
  queued: { label: 'Queued', color: 'bg-blue-500 text-white', step: 1 },
  transcribing: { label: 'Converting Speech', color: 'bg-yellow-500 text-black', step: 2 },
  aligning: { label: 'Syncing Timing', color: 'bg-yellow-500 text-black', step: 3 },
  diarizing: { label: 'Identifying Speakers', color: 'bg-yellow-500 text-black', step: 4 },
  complete: { label: 'Done', color: 'bg-green-500 text-white', step: 5 },
  error: { label: 'Error', color: 'bg-red-500 text-white', step: 0 },
};

export function StageBadge({ stage }: { stage: ProgressStage }) {
  const config = STAGE_CONFIG[stage];
  const totalSteps = 5;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge className={cn('border-transparent', config.color)}>
          {config.label} {stage !== 'error' && stage !== 'complete' && `(${config.step}/${totalSteps})`}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>
        <p>Steps: Uploading → Converting Speech → Syncing Timing → Identifying Speakers → Done</p>
      </TooltipContent>
    </Tooltip>
  );
}
```

### Pattern 4: Connection Status Indicator
**What:** Subtle indicator showing reconnection state per CONTEXT.md decisions.
**When to use:** "Subtle 'Reconnecting...' indicator during connection loss, after 5 failed attempts escalate to visible warning".
**Example:**
```typescript
// Source: CONTEXT.md decisions
import { Loader2, WifiOff } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ConnectionStatusProps {
  isConnected: boolean;
  reconnectAttempt: number;
  maxAttempts: number;
  onManualReconnect: () => void;
}

export function ConnectionStatus({
  isConnected,
  reconnectAttempt,
  maxAttempts,
  onManualReconnect
}: ConnectionStatusProps) {
  if (isConnected) return null;

  // Subtle indicator for first 5 attempts
  if (reconnectAttempt < maxAttempts) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground text-sm">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span>Reconnecting...</span>
      </div>
    );
  }

  // Escalated warning after max attempts
  return (
    <div className="flex items-center gap-2 bg-amber-100 text-amber-800 px-3 py-2 rounded-md">
      <WifiOff className="h-4 w-4" />
      <span>Connection lost</span>
      <Button variant="outline" size="sm" onClick={onManualReconnect}>
        Reconnect
      </Button>
    </div>
  );
}
```

### Anti-Patterns to Avoid
- **Creating new WebSocket per file:** Use a single connection per task, not per file. Backend is task-keyed.
- **Ignoring reconnection state:** Always track reconnection and fetch missed updates on reconnect.
- **Using setInterval for progress polling:** Use WebSocket as primary, polling only as fallback after WebSocket fails.
- **Animating with requestAnimationFrame:** Use CSS transitions for progress bar, simpler and more performant.
- **Showing raw error codes to users:** Per CONTEXT.md: "User-friendly error messages with 'Show details' to reveal technical info".

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| WebSocket reconnection | Custom reconnection logic | react-use-websocket | Handles exponential backoff, message queueing, connection state |
| Progress bar | Custom div with width | shadcn/ui Progress | Accessible, handles edge cases, Radix primitives |
| Toast notifications | Custom toast system | Sonner | Already installed, handles stacking, ARIA, animations |
| Spinner animation | Custom CSS keyframes | Tailwind animate-spin + Loader2 | lucide-react already installed |

**Key insight:** react-use-websocket handles the complex parts (reconnection, queueing, state management) while exposing a simple hook API. Don't reinvent the wheel.

## Common Pitfalls

### Pitfall 1: Missing State Sync on Reconnect
**What goes wrong:** After reconnection, UI shows stale progress because missed updates weren't fetched.
**Why it happens:** WebSocket reconnects but only receives new messages, not missed ones.
**How to avoid:** Per CONTEXT.md: "On reconnect, fetch missed updates from backend to sync current state." Use the polling endpoint `GET /tasks/{task_id}/progress` in the onOpen callback.
**Warning signs:** Progress jumps suddenly after reconnection, or shows wrong stage.

### Pitfall 2: Multiple WebSocket Connections
**What goes wrong:** Multiple components create separate WebSocket connections for the same task.
**Why it happens:** Each file item creates its own useWebSocket instance.
**How to avoid:** Use `share: true` option in react-use-websocket OR manage connections at the queue level, passing state down to file items.
**Warning signs:** Duplicate messages, memory growth, console showing multiple connections.

### Pitfall 3: Progress Bar Jumping
**What goes wrong:** Progress bar snaps instantly between values instead of animating smoothly.
**Why it happens:** Missing CSS transition on the progress indicator.
**How to avoid:** Add `transition: width 500ms ease-out` to the progress indicator element. Target with `[data-slot="indicator"]` selector for shadcn/ui Progress.
**Warning signs:** Janky, instant progress updates.

### Pitfall 4: Stale Closure in WebSocket Callbacks
**What goes wrong:** Callbacks in useWebSocket config reference stale state values.
**Why it happens:** React closures capture state at render time.
**How to avoid:** Use refs for values that need to be fresh, or use useCallback with proper dependencies.
**Warning signs:** Progress handler uses old state values.

### Pitfall 5: Not Handling Heartbeats
**What goes wrong:** UI reacts to heartbeat messages as if they were progress updates.
**Why it happens:** Message handler doesn't filter by message type.
**How to avoid:** Always check `message.type` before processing. Ignore `heartbeat` type messages.
**Warning signs:** Progress resets or fluctuates every 30 seconds.

### Pitfall 6: Error Toast Behind Dialog
**What goes wrong:** Error toast appears but can't be clicked because a dialog is open.
**Why it happens:** Known Sonner issue (#2401): toast renders behind dialog backdrop.
**How to avoid:** Don't show toasts while dialogs are open, OR close dialog before showing toast.
**Warning signs:** Toast visible but not clickable.

## Code Examples

Verified patterns from official sources:

### react-use-websocket Basic Usage
```typescript
// Source: https://github.com/robtaussig/react-use-websocket
import useWebSocket, { ReadyState } from 'react-use-websocket';

function TaskProgressTracker({ taskId }: { taskId: string }) {
  const { lastJsonMessage, readyState } = useWebSocket(
    `ws://localhost:8000/ws/tasks/${taskId}`,
    {
      shouldReconnect: () => true,
      reconnectAttempts: 5,
      reconnectInterval: (attemptNumber) =>
        Math.min(1000 * Math.pow(2, attemptNumber), 30000),
    }
  );

  const connectionStatus = {
    [ReadyState.CONNECTING]: 'Connecting',
    [ReadyState.OPEN]: 'Connected',
    [ReadyState.CLOSING]: 'Closing',
    [ReadyState.CLOSED]: 'Disconnected',
    [ReadyState.UNINSTANTIATED]: 'Uninstantiated',
  }[readyState];

  return (
    <div>
      <span>Status: {connectionStatus}</span>
      {lastJsonMessage && <span>Progress: {lastJsonMessage.percentage}%</span>}
    </div>
  );
}
```

### shadcn/ui Progress with Animation
```typescript
// Source: https://ui.shadcn.com/docs/components/progress + CSS transitions
import { Progress } from '@/components/ui/progress';

// In CSS:
// .animated-progress [data-slot="indicator"] {
//   transition: transform 500ms ease-out;
// }

export function AnimatedProgress({ value }: { value: number }) {
  return (
    <Progress
      value={value}
      className="animated-progress h-2"
    />
  );
}
```

### Sonner Toast with Retry Action
```typescript
// Source: https://ui.shadcn.com/docs/components/sonner
import { toast } from 'sonner';

function showErrorWithRetry(
  userMessage: string,
  technicalDetail: string | null,
  onRetry: () => void
) {
  toast.error(userMessage, {
    description: technicalDetail ? 'Click "Show details" for more info' : undefined,
    action: {
      label: 'Retry',
      onClick: onRetry,
    },
  });
}
```

### Backend Message Schemas Reference
```typescript
// Source: Phase 1 app/schemas/websocket_schemas.py
interface ProgressMessage {
  type: 'progress';
  task_id: string;
  stage: 'uploading' | 'queued' | 'transcribing' | 'aligning' | 'diarizing' | 'complete';
  percentage: number; // 0-100
  message: string | null;
  timestamp: string; // ISO 8601
}

interface ErrorMessage {
  type: 'error';
  task_id: string;
  error_code: string;
  user_message: string;
  technical_detail: string | null;
  timestamp: string; // ISO 8601
}

interface HeartbeatMessage {
  type: 'heartbeat';
  timestamp: string; // ISO 8601
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Socket.IO everywhere | Native WebSocket + react-use-websocket | 2024+ | Simpler stack, less overhead |
| Manual reconnection logic | react-use-websocket built-in | 2023+ | Less boilerplate, battle-tested |
| setInterval polling | WebSocket with polling fallback | Standard pattern | Better real-time UX |
| Custom progress bars | shadcn/ui Progress + CSS transitions | 2024+ | Accessible, consistent styling |

**Deprecated/outdated:**
- Socket.IO for simple WebSocket needs: Overkill when backend uses native WebSocket
- Manual WebSocket management in React: react-use-websocket handles lifecycle correctly

## Open Questions

Things that couldn't be fully resolved:

1. **WebSocket URL scheme (ws vs wss)**
   - What we know: Development uses ws://, production likely needs wss://
   - What's unclear: How proxy configuration affects URL
   - Recommendation: Use relative URL (`/ws/tasks/${taskId}`) and let browser determine scheme based on page protocol

2. **Reconnection during active transcription**
   - What we know: Backend keeps processing even if client disconnects
   - What's unclear: Whether backend tracks which updates were sent
   - Recommendation: Use polling endpoint on reconnect to get current state, don't worry about missed intermediate updates

3. **Multiple files processing simultaneously**
   - What we know: Each file gets its own task_id
   - What's unclear: Performance impact of many concurrent WebSocket connections
   - Recommendation: Start with one connection per active task, optimize if needed

## Sources

### Primary (HIGH confidence)
- [react-use-websocket GitHub](https://github.com/robtaussig/react-use-websocket) - WebSocket hook API, reconnection config
- [shadcn/ui Progress docs](https://ui.shadcn.com/docs/components/progress) - Progress component installation and usage
- [shadcn/ui Badge docs](https://ui.shadcn.com/docs/components/badge) - Badge variants and customization
- [shadcn/ui Sonner docs](https://ui.shadcn.com/docs/components/sonner) - Toast notifications with actions
- [Lucide React icons](https://lucide.dev/guide/packages/lucide-react) - Loader2, CheckCircle2 icons

### Secondary (MEDIUM confidence)
- [OneUptime WebSocket React Guide](https://oneuptime.com/blog/post/2026-01-15-websockets-react-real-time-applications/view) - Reconnection patterns, custom hooks
- [Ably WebSocket React Tutorial](https://ably.com/blog/websockets-react-tutorial) - State management patterns
- [DEV.to Exponential Backoff](https://dev.to/hexshift/robust-websocket-reconnection-strategies-in-javascript-with-exponential-backoff-40n1) - Backoff formula patterns

### Tertiary (LOW confidence)
- Community articles on CSS progress bar animations - Animation timing patterns
- GitHub issues on Sonner/dialog interaction - Known issues to avoid

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - react-use-websocket and shadcn/ui are well-documented, existing project already uses shadcn/ui
- Architecture: HIGH - Patterns verified from official docs and match Phase 1 backend implementation
- Pitfalls: MEDIUM - Some from community sources, some from Phase 1 integration analysis

**Research date:** 2026-01-27
**Valid until:** 2026-02-27 (30 days - stable ecosystem)

---

## Existing Codebase Integration Notes

### Phase 1 Backend Infrastructure (Complete)

The backend provides:
- **WebSocket endpoint:** `ws://host/ws/tasks/{task_id}` (app/api/websocket_api.py)
- **Heartbeat:** Every 30 seconds, type: "heartbeat"
- **Progress messages:** type: "progress" with stage, percentage, message, timestamp
- **Error messages:** type: "error" with error_code, user_message, technical_detail
- **Polling fallback:** `GET /tasks/{identifier}/progress` returns TaskProgress
- **Stages:** queued (0%), transcribing (10%), aligning (40%), diarizing (60%, 80%), complete (100%)

### Phase 4 Frontend Components (Complete)

Already implemented:
- FileQueueItem.tsx - Individual file display (needs progress integration)
- FileQueueList.tsx - Queue container
- useFileQueue.ts - Queue state management (has updateFileStatus)
- Types in types/upload.ts - FileQueueItemStatus includes 'processing'
- shadcn/ui components: Button, Badge, Card, Tooltip, Sonner, ScrollArea
- TooltipProvider and Toaster already in main.tsx

### Key Integration Points

1. **Extend FileQueueItem** to show:
   - Progress bar when status is 'processing' or 'uploading'
   - Stage badge with step counter
   - Spinner icon during processing
   - Success checkmark when complete
   - Error state with retry button

2. **Extend useFileQueue** with:
   - Progress percentage per file
   - Current stage per file
   - Task ID mapping (file ID -> backend task ID)

3. **Add useTaskProgress hook** for:
   - WebSocket connection to backend
   - Reconnection with exponential backoff
   - Polling fallback on max retries

4. **Extend types/upload.ts** with:
   - ProgressStage type matching backend
   - Progress-related fields in FileQueueItem
