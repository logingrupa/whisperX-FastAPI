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
 * 2. API call to /speech-to-text (full pipeline: transcription + alignment + diarization)
 * 3. Get task ID -> connect WebSocket -> status: 'processing'
 * 4. Receive progress updates via WebSocket for all 5 stages
 * 5. Complete or error state
 */
import { useCallback, useRef, useEffect, useState } from 'react';
import { useFileQueue, type UseFileQueueReturn } from './useFileQueue';
import { useTaskProgress, type TaskProgressState, type TaskErrorState, type ConnectionState } from './useTaskProgress';
import { startTranscription } from '@/lib/api/transcriptionApi';
import { SIZE_THRESHOLD } from '@/lib/upload/constants';
import type { FileQueueItem } from '@/types/upload';
import { useTusUpload, isTusSupported } from '@/hooks/useTusUpload';

interface UseUploadOrchestrationReturn extends UseFileQueueReturn {
  /** Start processing a single file */
  handleStartFile: (id: string) => void;
  /** Start processing all ready files */
  handleStartAll: () => void;
  /** Retry a failed file */
  handleRetry: (id: string) => void;
  /** Cancel an in-progress upload */
  handleCancel: (id: string) => void;
  /** ID of the file currently in retry delay (null if none) */
  retryingFileId: string | null;
  /** WebSocket connection state */
  connectionState: ConnectionState;
  /** Manual reconnection trigger */
  reconnect: () => void;
  /**
   * Resume WS subscription for a historic item already in 'processing' state.
   * Sets the orchestrator's current refs so useTaskProgress connects to the
   * existing taskId (single-task-at-a-time invariant preserved).
   */
  resumeProcessingTask: (fileId: string, taskId: string) => void;
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
    updateFileUploadMetrics,
    setFileTaskId,
    completeFile,
    setFileError,
    isFileReady,
  } = fileQueue;

  const { startTusUpload } = useTusUpload();

  // Track current file being processed for WebSocket subscription
  const currentFileIdRef = useRef<string | null>(null);
  const currentTaskIdRef = useRef<string | null>(null);

  // Per-file abort functions for cancel support
  const abortControllerRef = useRef<Map<string, () => void>>(new Map());

  // Track which file is currently in retry delay (for UI indicator)
  const [retryingFileId, setRetryingFileId] = useState<string | null>(null);

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
  const { connectionState, reconnect } = useTaskProgress({
    taskId: currentTaskId,
    onProgress: handleProgress,
    onError: handleError,
    onComplete: handleComplete,
  });

  /**
   * Process a large file via TUS chunked upload.
   * TaskId is pre-generated and sent as metadata so WebSocket can subscribe immediately on success.
   *
   * Precondition (tiger-style boundary): item.file !== null. Caller is
   * processFile, which short-circuits historic items via isFileReady.
   */
  const processViaTus = useCallback((item: FileQueueItem) => {
    if (item.file === null) {
      console.warn('processViaTus called on historic item — ignoring:', item.id);
      return;
    }
    const liveFile = item.file;
    currentFileIdRef.current = item.id;
    updateFileStatus(item.id, 'uploading');
    updateFileProgress(item.id, 0, 'uploading');

    // Pre-generate task ID for WebSocket subscription
    const taskId = crypto.randomUUID();

    const metadata: Record<string, string> = {
      filename: liveFile.name,
      filetype: liveFile.type || 'application/octet-stream',
      language: item.selectedLanguage || 'auto',
      taskId: taskId,
    };

    const { abort } = startTusUpload(liveFile, metadata, {
      onProgress: (percentage, speed, eta) => {
        setRetryingFileId(null);
        updateFileProgress(item.id, percentage, 'uploading');
        updateFileUploadMetrics(item.id, speed, eta);
      },
      onSuccess: (returnedTaskId) => {
        setRetryingFileId(null);
        abortControllerRef.current.delete(item.id);
        // Store task ID and transition to processing
        setFileTaskId(item.id, returnedTaskId);
        currentTaskIdRef.current = returnedTaskId;
        updateFileStatus(item.id, 'processing');
        updateFileProgress(item.id, 100, 'uploading');
      },
      onError: (userMessage, technicalDetail, _isRetryable) => {
        setRetryingFileId(null);
        abortControllerRef.current.delete(item.id);
        setFileError(item.id, userMessage, technicalDetail);
        currentFileIdRef.current = null;
        currentTaskIdRef.current = null;
      },
      onRetrying: () => setRetryingFileId(item.id),
    });
    abortControllerRef.current.set(item.id, abort);
  }, [startTusUpload, updateFileStatus, updateFileProgress, updateFileUploadMetrics, setFileTaskId, setFileError]);

  /**
   * Process a single file: upload -> get task ID -> start WebSocket
   *
   * Tiger-style: isFileReady already excludes historic items (kind !== 'live'),
   * but defense-in-depth — narrow item.file to non-null before downstream
   * calls touch File-only properties (size, type, blob streaming).
   */
  const processFile = useCallback(async (item: FileQueueItem) => {
    // Validate file is ready (excludes historic items via kind check)
    if (!isFileReady(item)) {
      console.warn('File not ready:', item.id);
      return;
    }
    if (item.file === null) {
      console.warn('processFile called on item with null File — ignoring:', item.id);
      return;
    }
    const liveFile = item.file;

    // Route: large files via TUS, small files via direct upload
    if (liveFile.size >= SIZE_THRESHOLD && isTusSupported()) {
      processViaTus(item);
      return;
    }

    // Existing direct upload flow (unchanged)
    // Set as current processing file
    currentFileIdRef.current = item.id;

    // Update status to uploading
    updateFileStatus(item.id, 'uploading');
    updateFileProgress(item.id, 0, 'uploading');

    // Call transcription API
    const result = await startTranscription({
      file: liveFile,
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
  }, [isFileReady, processViaTus, updateFileStatus, updateFileProgress, setFileTaskId, setFileError]);

  /**
   * Cancel an in-progress TUS upload.
   * Calls abort (sends DELETE to server + clears localStorage) and resets file to pending.
   */
  const handleCancel = useCallback((id: string) => {
    const abort = abortControllerRef.current.get(id);
    if (abort) {
      abort();
      abortControllerRef.current.delete(id);
    }
    setRetryingFileId(null);
    updateFileStatus(id, 'pending');
    updateFileProgress(id, 0, 'uploading');
    updateFileUploadMetrics(id, '', '');
    // Clear processing refs if this was the active file
    if (currentFileIdRef.current === id) {
      currentFileIdRef.current = null;
      currentTaskIdRef.current = null;
    }
  }, [updateFileStatus, updateFileProgress, updateFileUploadMetrics]);

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
   * Pick the OLDEST ready file across the queue.
   *
   * Plan 15-ux invariant: display order is LIFO (newest live items first)
   * but processing order stays FIFO. The picker uses `createdAt` — NOT
   * array index — so flipping display order in `prependLiveFiles` cannot
   * break the upload sequence the user expects.
   */
  const findOldestReady = useCallback((items: FileQueueItem[]): FileQueueItem | undefined => {
    let oldest: FileQueueItem | undefined;
    for (const item of items) {
      if (!isFileReady(item)) continue;
      if (oldest === undefined || item.createdAt < oldest.createdAt) {
        oldest = item;
      }
    }
    return oldest;
  }, [isFileReady]);

  /**
   * Start processing all ready files (FIFO order by `createdAt`).
   * Note: For MVP, processes one file at a time.
   */
  const handleStartAll = useCallback(() => {
    const readyFile = findOldestReady(queue);
    if (readyFile) {
      processFile(readyFile);
    }
  }, [queue, findOldestReady, processFile]);

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

  /**
   * Resume WS subscription for a historic item that was already 'processing'
   * when the user refreshed. Single-task-at-a-time invariant: only the FIRST
   * resume call wins; subsequent calls while a task is active are no-ops.
   */
  const resumeProcessingTask = useCallback((fileId: string, taskId: string) => {
    if (currentFileIdRef.current !== null) return;
    if (!fileId || !taskId) return;
    currentFileIdRef.current = fileId;
    currentTaskIdRef.current = taskId;
  }, []);

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

    const nextReady = findOldestReady(queue);
    if (nextReady) {
      processFile(nextReady);
    }
  }, [queue, findOldestReady, processFile]);

  return {
    ...fileQueue,
    handleStartFile,
    handleStartAll,
    handleRetry,
    handleCancel,
    retryingFileId,
    connectionState,
    reconnect,
    resumeProcessingTask,
  };
}
