import { Trash2, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { FileQueueItem } from './FileQueueItem';
import type { FileQueueItem as FileQueueItemType, LanguageCode, WhisperModel } from '@/types/upload';

interface FileQueueListProps {
  queue: FileQueueItemType[];
  onRemoveFile: (id: string) => void;
  onUpdateSettings: (
    id: string,
    updates: { selectedLanguage?: LanguageCode | ''; selectedModel?: WhisperModel }
  ) => void;
  onClearPending: () => void;
  onStartAll?: () => void;
  onStartFile?: (id: string) => void;
  onRetry?: (id: string) => void;
  onCancel?: (id: string) => void;
  retryingFileId?: string | null;
  pendingCount: number;
  readyCount: number;
}

/**
 * File queue list with batch actions
 *
 * Features:
 * - Scrollable list of queue items
 * - "Clear queue" button to remove all pending
 * - "Start all" button to begin processing ready files
 * - Per CONTEXT.md: FIFO order, sequential processing
 */
export function FileQueueList({
  queue,
  onRemoveFile,
  onUpdateSettings,
  onClearPending,
  onStartAll,
  onStartFile,
  onRetry,
  onCancel,
  retryingFileId,
  pendingCount,
  readyCount,
}: FileQueueListProps) {
  if (queue.length === 0) {
    return null;
  }

  return (
    <div className="space-y-4">
      {/* Header with counts and actions */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          {pendingCount} file{pendingCount !== 1 ? 's' : ''} in queue
          {readyCount > 0 && readyCount < pendingCount && (
            <span className="ml-1">
              ({readyCount} ready)
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Clear queue button */}
          {pendingCount > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={onClearPending}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Clear queue
            </Button>
          )}
          {/* Start all button */}
          {onStartAll && readyCount > 0 && (
            <Button
              size="sm"
              onClick={onStartAll}
            >
              <Play className="mr-2 h-4 w-4" />
              Start all ({readyCount})
            </Button>
          )}
        </div>
      </div>

      {/*
       * Queue items render inline in normal document flow.
       *
       * Plan 15-ux fix: the previous Radix `<ScrollArea max-h-[60vh]>`
       * wrapper was the root cause of the View Transcript overlap bug —
       * Radix injects a `display: table` Viewport child whose layout
       * does not reflow when a sibling Collapsible expands inside, so
       * the transcript drew over the next card. The page itself
       * scrolls, so a list-level ScrollArea was unnecessary anyway.
       */}
      <div className="flex flex-col gap-2">
        {queue.map(item => (
          <FileQueueItem
            key={item.id}
            item={item}
            onRemove={onRemoveFile}
            onUpdateSettings={onUpdateSettings}
            onStart={onStartFile}
            onRetry={onRetry}
            onCancel={onCancel}
            isRetrying={retryingFileId === item.id}
          />
        ))}
      </div>
    </div>
  );
}
