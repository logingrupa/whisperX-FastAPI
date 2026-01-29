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
   * Add files to the queue with detected language and default model
   */
  const addFiles = useCallback((files: File[]) => {
    const newItems: FileQueueItem[] = files.map(file => {
      const detectedLanguage = detectLanguageFromFilename(file.name);
      return {
        id: crypto.randomUUID(),
        file,
        detectedLanguage,
        // Pre-fill selectedLanguage if detected, empty string otherwise
        selectedLanguage: detectedLanguage ?? '',
        selectedModel: DEFAULT_MODEL,
        status: 'pending' as const,
      };
    });

    setQueue(previousQueue => [...previousQueue, ...newItems]);
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
   * Check if a file is ready to process (has language selected)
   */
  const isFileReady = useCallback((item: FileQueueItem): boolean => {
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
