import { useState, useCallback } from 'react';
import type { FileQueueItem, FileQueueItemStatus, ProgressStage } from '@/types/upload';
import { detectLanguageFromFilename } from '@/lib/languageDetection';
import { DEFAULT_MODEL } from '@/lib/whisperModels';

/**
 * Hook for managing the file upload queue
 *
 * Handles:
 * - Adding files with auto-detected language and default model
 * - Removing individual files (only when pending)
 * - Clearing all pending files
 * - Updating file settings (language, model)
 * - Getting files ready to process (language selected)
 */
export function useFileQueue() {
  const [queue, setQueue] = useState<FileQueueItem[]>([]);

  /**
   * Add files to the queue with detected language and default model.
   *
   * Plan 15-ux: newly selected files PREPEND so the user sees the file
   * they just chose at the top of the list (LIFO display). Each item
   * carries `createdAt` so the upload orchestrator can still pick the
   * OLDEST ready item (FIFO upload) — display order is decoupled from
   * processing order on purpose.
   *
   * Tiger-style invariant: every new live item carries a strictly
   * monotonic `createdAt` so the FIFO picker has a deterministic
   * tie-breaker even when several files arrive in the same drop.
   */
  const prependLiveFiles = useCallback((files: File[]) => {
    const baseTime = Date.now();
    const newItems: FileQueueItem[] = files.map((file, index) => {
      const detectedLanguage = detectLanguageFromFilename(file.name);
      return {
        id: crypto.randomUUID(),
        kind: 'live' as const,
        file,
        fileName: file.name,
        fileSize: file.size,
        detectedLanguage,
        // Pre-fill selectedLanguage if detected, empty string otherwise
        selectedLanguage: detectedLanguage ?? '',
        selectedModel: DEFAULT_MODEL,
        status: 'pending' as const,
        createdAt: baseTime + index,
      };
    });

    // Prepend reversed so the file the user picked LAST in the OS dialog
    // ends up at the bottom of the new prepended block — within a single
    // drop, FIFO order across the new block is preserved (oldest first
    // among the new arrivals), and the whole block sits ABOVE the
    // existing queue.
    const prepended = [...newItems].reverse();
    setQueue(previousQueue => [...prepended, ...previousQueue]);
  }, []);

  /** Public alias — keeps the existing call sites + tests working. */
  const addFiles = prependLiveFiles;

  /**
   * Append historic items (seeded from GET /task/all on mount).
   *
   * SRP: this hook owns queue state — it does NOT fetch. The caller
   * (useTaskHistory) handles HTTP and produces ready-to-insert items.
   *
   * De-dup: items already in the queue (matched by taskId) are skipped
   * so a re-mount or accidental double-call cannot duplicate rows.
   */
  const addHistoricTasks = useCallback((historicItems: FileQueueItem[]) => {
    if (historicItems.length === 0) return;
    setQueue(previousQueue => {
      const existingTaskIds = new Set(
        previousQueue.map(item => item.taskId).filter((id): id is string => Boolean(id)),
      );
      const fresh = historicItems.filter(item => !item.taskId || !existingTaskIds.has(item.taskId));
      if (fresh.length === 0) return previousQueue;
      return [...fresh, ...previousQueue];
    });
  }, []);

  /**
   * Replace the historic portion of the queue with a fresh snapshot
   * (Plan 15-ux pagination — page N's slice fully replaces page N-1's).
   *
   * Live items (kind === 'live') are preserved untouched so an in-flight
   * upload mid-page-flip is never destroyed; only historic rows turn over.
   */
  const setHistoricTasks = useCallback((historicItems: FileQueueItem[]) => {
    setQueue(previousQueue => {
      const liveItems = previousQueue.filter(item => item.kind === 'live');
      return [...historicItems, ...liveItems];
    });
  }, []);

  /**
   * Remove a file from the queue (only if pending)
   * Per CONTEXT.md: "Files can only be removed before processing starts"
   */
  const removeFile = useCallback((id: string) => {
    setQueue(previousQueue =>
      previousQueue.filter(item => item.id !== id || item.status !== 'pending')
    );
  }, []);

  /**
   * Clear all pending files from the queue
   * Keeps files that are currently processing or completed
   */
  const clearPendingFiles = useCallback(() => {
    setQueue(previousQueue =>
      previousQueue.filter(item => item.status !== 'pending')
    );
  }, []);

  /**
   * Update settings for a specific file
   */
  const updateFileSettings = useCallback((
    id: string,
    updates: Partial<Pick<FileQueueItem, 'selectedLanguage' | 'selectedModel'>>
  ) => {
    setQueue(previousQueue =>
      previousQueue.map(item =>
        item.id === id ? { ...item, ...updates } : item
      )
    );
  }, []);

  /**
   * Update file status (for upload/processing flow)
   */
  const updateFileStatus = useCallback((
    id: string,
    status: FileQueueItemStatus,
    errorMessage?: string
  ) => {
    setQueue(previousQueue =>
      previousQueue.map(item =>
        item.id === id ? { ...item, status, errorMessage } : item
      )
    );
  }, []);

  /**
   * Update file progress from WebSocket
   */
  const updateFileProgress = useCallback((
    id: string,
    progressPercentage: number,
    progressStage: ProgressStage
  ) => {
    setQueue(previousQueue =>
      previousQueue.map(item =>
        item.id === id ? { ...item, progressPercentage, progressStage } : item
      )
    );
  }, []);

  /**
   * Update upload speed and ETA metrics for a file (during upload phase)
   */
  const updateFileUploadMetrics = useCallback((
    id: string,
    uploadSpeed: string,
    uploadEta: string
  ) => {
    setQueue(previousQueue =>
      previousQueue.map(item =>
        item.id === id ? { ...item, uploadSpeed, uploadEta } : item
      )
    );
  }, []);

  /**
   * Set backend task ID for a file (after upload starts)
   */
  const setFileTaskId = useCallback((id: string, taskId: string) => {
    setQueue(previousQueue =>
      previousQueue.map(item =>
        item.id === id ? { ...item, taskId } : item
      )
    );
  }, []);

  /**
   * Mark file as complete (reset progress display, set status)
   */
  const completeFile = useCallback((id: string) => {
    setQueue(previousQueue =>
      previousQueue.map(item =>
        item.id === id
          ? { ...item, status: 'complete' as const, progressStage: 'complete' as const }
          : item
      )
    );
  }, []);

  /**
   * Mark file as error with message
   */
  const setFileError = useCallback((
    id: string,
    errorMessage: string,
    technicalDetail?: string
  ) => {
    setQueue(previousQueue =>
      previousQueue.map(item =>
        item.id === id
          ? {
              ...item,
              status: 'error' as const,
              errorMessage,
              // Store technical detail for "Show details" feature
              technicalDetail,
            }
          : item
      )
    );
  }, []);

  /**
   * Check if a file is ready to process (has language selected).
   *
   * Tiger-style: historic items (kind === 'historic', file === null)
   * can NEVER be ready — uploading requires a File object. Early-return
   * keeps this branch flat (no nested-if).
   */
  const isFileReady = useCallback((item: FileQueueItem): boolean => {
    if (item.kind !== 'live') return false;
    return item.status === 'pending' && item.selectedLanguage !== '';
  }, []);

  /**
   * Get count of pending files
   */
  const pendingCount = queue.filter(item => item.status === 'pending').length;

  /**
   * Get count of files ready to process
   */
  const readyCount = queue.filter(isFileReady).length;

  /**
   * Check if any files are currently processing
   */
  const hasProcessingFiles = queue.some(
    item => item.status === 'uploading' || item.status === 'processing'
  );

  return {
    queue,
    addFiles,
    addHistoricTasks,
    setHistoricTasks,
    removeFile,
    clearPendingFiles,
    updateFileSettings,
    updateFileStatus,
    updateFileProgress,
    updateFileUploadMetrics,
    setFileTaskId,
    completeFile,
    setFileError,
    isFileReady,
    pendingCount,
    readyCount,
    hasProcessingFiles,
  };
}

export type UseFileQueueReturn = ReturnType<typeof useFileQueue>;
