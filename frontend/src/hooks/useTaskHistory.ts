/**
 * useTaskHistory — mount-time fetch of GET /task/all + queue seeding.
 *
 * SRP: this hook does ONE job — pull historic tasks for the signed-in
 * user and inject them into the queue as historic FileQueueItem rows.
 * It does NOT own queue state, does NOT trigger uploads, does NOT
 * subscribe to WebSocket — those belong to useFileQueue and
 * useUploadOrchestration.
 *
 * DRY: single fetch site (taskApi.fetchAllTasks). Caller composes via
 * dependency-injected setters from useUploadOrchestration.
 *
 * Tiger-style: assert at boundaries — taskId must be non-empty before
 * we ever consider seeding it. A row without taskId would be unusable
 * (no WS subscription, no transcript fetch).
 *
 * Failure mode: history is a read-only nice-to-have; non-401 errors
 * log + swallow so a flaky GET never blocks fresh uploads. AuthRequired
 * is propagated implicitly — apiClient already redirects.
 */
import { useEffect, useRef } from 'react';
import { fetchAllTasks, type TaskListItem, type BackendTaskStatus } from '@/lib/api/taskApi';
import { DEFAULT_MODEL } from '@/lib/whisperModels';
import type {
  FileQueueItem,
  FileQueueItemStatus,
  LanguageCode,
} from '@/types/upload';

interface UseTaskHistoryOptions {
  /** Inject historic items into the queue (from useUploadOrchestration). */
  addHistoricTasks: (items: FileQueueItem[]) => void;
  /** Re-bind WS for an item already mid-processing on the server. */
  resumeProcessingTask: (fileId: string, taskId: string) => void;
}

/**
 * Map backend task status to frontend queue status.
 *
 * No nested-if: a flat lookup with a defensive default keeps the
 * intent obvious and grep-friendly.
 */
function mapBackendStatus(status: string): FileQueueItemStatus {
  if (status === 'completed') return 'complete';
  if (status === 'failed') return 'error';
  if (status === 'processing') return 'processing';
  // Unknown server states (queued, etc) collapse to processing — UI shows
  // a spinner; backend remains source of truth.
  return 'processing';
}

/**
 * Convert a backend task summary to a historic FileQueueItem.
 *
 * Self-explanatory naming over abbreviations: `taskToQueueItem`.
 */
export function taskToQueueItem(task: TaskListItem): FileQueueItem | null {
  // Tiger-style boundary: identifier MUST be non-empty for the row to be
  // useful (taskId drives WS, transcript fetch, retries).
  if (!task.identifier || task.identifier.length === 0) {
    return null;
  }
  const status = mapBackendStatus(task.status as BackendTaskStatus | string);
  return {
    id: crypto.randomUUID(),
    kind: 'historic',
    file: null,
    fileName: task.file_name ?? '(unnamed task)',
    fileSize: 0,
    detectedLanguage: null,
    selectedLanguage: (task.language as LanguageCode | null) ?? '',
    selectedModel: DEFAULT_MODEL,
    status,
    taskId: task.identifier,
    errorMessage: task.error ?? undefined,
    progressPercentage: status === 'complete' ? 100 : undefined,
    progressStage: status === 'complete' ? 'complete' : undefined,
  };
}

/**
 * Build the seed list from a fetched task array.
 *
 * Pure helper — DRY (callers in tests can use this without re-implementing
 * the mapping). Filters out malformed rows whose identifier failed the
 * boundary assertion.
 */
export function seedQueueFromTasks(tasks: TaskListItem[]): FileQueueItem[] {
  return tasks
    .map(taskToQueueItem)
    .filter((item): item is FileQueueItem => item !== null);
}

/**
 * Hook: on mount, fetch /task/all and seed the queue.
 *
 * Returns void — caller composes side-effect via injected setters.
 * Idempotent: a `hasRunRef` guards against React StrictMode double-mount
 * in development from issuing two seeds.
 */
export function useTaskHistory({
  addHistoricTasks,
  resumeProcessingTask,
}: UseTaskHistoryOptions): void {
  const hasRunRef = useRef(false);

  useEffect(() => {
    if (hasRunRef.current) return;
    hasRunRef.current = true;

    let cancelled = false;
    (async () => {
      try {
        const result = await fetchAllTasks();
        if (cancelled) return;
        if (!result.success) {
          // Non-401 errors are already typed; AuthRequired never reaches here
          // because apiClient throws + redirects. Log + continue (queue empty).
          console.warn('useTaskHistory: failed to fetch /task/all:', result.error.detail);
          return;
        }
        const historicItems = seedQueueFromTasks(result.data);
        if (historicItems.length === 0) return;
        addHistoricTasks(historicItems);

        // Re-bind WS for the first historic item still in 'processing'.
        // Single-task-at-a-time invariant matches existing orchestration.
        const firstProcessing = historicItems.find(item => item.status === 'processing');
        if (!firstProcessing) return;
        if (!firstProcessing.taskId) return;
        resumeProcessingTask(firstProcessing.id, firstProcessing.taskId);
      } catch (err) {
        // AuthRequiredError already redirected via apiClient. Anything else
        // we swallow + log — uploads must keep working.
        console.warn('useTaskHistory: unexpected error fetching /task/all:', err);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [addHistoricTasks, resumeProcessingTask]);
}
