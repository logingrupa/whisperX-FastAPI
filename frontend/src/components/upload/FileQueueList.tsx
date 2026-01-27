import { Trash2, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
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

      {/* Queue items */}
      <ScrollArea className="max-h-[60vh]">
        <div className="space-y-2 pr-4">
          {queue.map(item => (
            <FileQueueItem
              key={item.id}
              item={item}
              onRemove={onRemoveFile}
              onUpdateSettings={onUpdateSettings}
              onStart={onStartFile}
            />
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
