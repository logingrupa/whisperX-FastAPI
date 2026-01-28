/**
 * Hook for orchestrating file upload and transcription workflow
 *
 * Coordinates:
 * - File queue state (useFileQueue)
 * - API calls (startTranscription)
 * - WebSocket progress (useTaskProgress)
 *
 * Flow:
 * 1. User clicks Start -> status: 'uploading'
 * 2. API call to /service/transcribe
 * 3. Get task ID -> connect WebSocket -> status: 'processing'
 * 4. Receive progress updates via WebSocket
 * 5. Complete or error state
 */
import { useCallback, useRef, useEffect } from 'react';
import { useFileQueue, type UseFileQueueReturn } from './useFileQueue';
import { useTaskProgress, type TaskProgressState, type TaskErrorState } from './useTaskProgress';
import { startTranscription } from '@/lib/api/transcriptionApi';
import type { FileQueueItem } from '@/types/upload';

interface UseUploadOrchestrationReturn extends UseFileQueueReturn {
  /** Start processing a single file */
  handleStartFile: (id: string) => void;
  /** Start processing all ready files */
  handleStartAll: () => void;
  /** Retry a failed file */
  handleRetry: (id: string) => void;
}

/**
 * Orchestrates the upload -> transcribe -> progress flow
 */
export function useUploadOrchestration(): UseUploadOrchestrationReturn {
  const fileQueue = useFileQueue();
  const {
    queue,
    updateFileStatus,
    updateFileProgress,
    setFileTaskId,
    completeFile,
    setFileError,
    isFileReady,
  } = fileQueue;

  // Track current file being processed for WebSocket subscription
  const currentFileIdRef = useRef<string | null>(null);
  const currentTaskIdRef = useRef<string | null>(null);

  // Find the file item for current processing
  const currentFile = queue.find(item => item.id === currentFileIdRef.current);
  const currentTaskId = currentFile?.taskId ?? null;

  // Progress callback - update file progress from WebSocket
  const handleProgress = useCallback((_taskId: string, progress: TaskProgressState) => {
    const fileId = currentFileIdRef.current;
    if (!fileId) return;

    // Map WebSocket stage to our status
    if (progress.stage === 'uploading') {
      updateFileStatus(fileId, 'uploading');
    } else if (progress.stage !== 'complete') {
      updateFileStatus(fileId, 'processing');
    }

    updateFileProgress(fileId, progress.percentage, progress.stage);
  }, [updateFileStatus, updateFileProgress]);

  // Error callback - set file error from WebSocket
  const handleError = useCallback((_taskId: string, error: TaskErrorState) => {
    const fileId = currentFileIdRef.current;
    if (!fileId) return;

    setFileError(fileId, error.userMessage, error.technicalDetail ?? undefined);

    // Clear current processing
    currentFileIdRef.current = null;
    currentTaskIdRef.current = null;
  }, [setFileError]);

  // Complete callback - mark file as complete
  const handleComplete = useCallback((_taskId: string) => {
    const fileId = currentFileIdRef.current;
    if (!fileId) return;

    completeFile(fileId);

    // Clear current processing
    currentFileIdRef.current = null;
    currentTaskIdRef.current = null;
  }, [completeFile]);

  // WebSocket connection for current task
  useTaskProgress({
    taskId: currentTaskId,
    onProgress: handleProgress,
    onError: handleError,
    onComplete: handleComplete,
  });

  /**
   * Process a single file: upload -> get task ID -> start WebSocket
   */
  const processFile = useCallback(async (item: FileQueueItem) => {
    // Validate file is ready
    if (!isFileReady(item)) {
      console.warn('File not ready:', item.id);
      return;
    }

    // Set as current processing file
    currentFileIdRef.current = item.id;

    // Update status to uploading
    updateFileStatus(item.id, 'uploading');
    updateFileProgress(item.id, 0, 'uploading');

    // Call transcription API
    const result = await startTranscription({
      file: item.file,
      language: item.selectedLanguage as Exclude<typeof item.selectedLanguage, ''>,
      model: item.selectedModel,
    });

    if (!result.success) {
      // API error - set file error state
      setFileError(
        item.id,
        'Upload failed',
        result.error.detail
      );
      currentFileIdRef.current = null;
      return;
    }

    // Success - store task ID for WebSocket subscription
    const taskId = result.data.identifier;
    setFileTaskId(item.id, taskId);
    currentTaskIdRef.current = taskId;

    // Update status to processing (WebSocket will take over progress updates)
    updateFileStatus(item.id, 'processing');
    updateFileProgress(item.id, 5, 'queued');
  }, [isFileReady, updateFileStatus, updateFileProgress, setFileTaskId, setFileError]);

  /**
   * Start processing a single file by ID
   */
  const handleStartFile = useCallback((id: string) => {
    const item = queue.find(f => f.id === id);
    if (!item) {
      console.warn('File not found:', id);
      return;
    }
    processFile(item);
  }, [queue, processFile]);

  /**
   * Start processing all ready files (FIFO order)
   * Note: For MVP, processes one file at a time
   * Future: Could implement parallel processing
   */
  const handleStartAll = useCallback(() => {
    // Find first ready file
    const readyFile = queue.find(isFileReady);
    if (readyFile) {
      processFile(readyFile);
    }
  }, [queue, isFileReady, processFile]);

  /**
   * Retry a failed file (reset status and process again)
   */
  const handleRetry = useCallback((id: string) => {
    const item = queue.find(f => f.id === id);
    if (!item || item.status !== 'error') {
      console.warn('Cannot retry - file not in error state:', id);
      return;
    }

    // Reset to pending, then start
    updateFileStatus(id, 'pending');

    // Small delay to allow state update, then process
    setTimeout(() => {
      const updatedItem = queue.find(f => f.id === id);
      if (updatedItem && updatedItem.selectedLanguage) {
        processFile({
          ...updatedItem,
          status: 'pending',
          errorMessage: undefined,
          technicalDetail: undefined,
        });
      }
    }, 0);
  }, [queue, updateFileStatus, processFile]);

  // Auto-process next ready file when current completes
  useEffect(() => {
    // Only trigger when we're not currently processing
    if (currentFileIdRef.current !== null) return;

    // Check if there's a processing file that just completed
    const hasProcessingOrUploading = queue.some(
      item => item.status === 'uploading' || item.status === 'processing'
    );
    if (hasProcessingOrUploading) return;

    // Find next ready file (for "Start All" continuation)
    // Only auto-continue if we have files in non-pending states (meaning user started batch)
    const hasStartedFiles = queue.some(
      item => item.status === 'complete' || item.status === 'error'
    );
    if (!hasStartedFiles) return;

    const nextReady = queue.find(isFileReady);
    if (nextReady) {
      processFile(nextReady);
    }
  }, [queue, isFileReady, processFile]);

  return {
    ...fileQueue,
    handleStartFile,
    handleStartAll,
    handleRetry,
  };
}
