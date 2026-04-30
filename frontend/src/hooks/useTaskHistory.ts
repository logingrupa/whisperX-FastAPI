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
import { useEffect } from 'react';
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
 * Module-level inflight cache for the /task/all fetch.
 *
 * Why module-level (not useRef): React StrictMode mounts each effect twice
 * in dev — mount #1 runs, then unmounts, then mount #2 runs on the SAME
 * fiber. Refs persist across that cycle, so a `hasRunRef` set during mount
 * #1 would block mount #2 from ever seeing the result; mount #1's own
 * `cancelled` cleanup then suppresses its own callback. Net: queue stays
 * empty.
 *
 * A module-level promise sidesteps the lifecycle entirely: both mounts
 * await the SAME promise, only the survivor (mount #2) calls the
 * caller-supplied setters. Dedupe at the queue layer (addHistoricTasks
 * tracks taskIds in a Set) makes a redundant call harmless either way.
 *
 * Reset hooks (resetTaskHistoryCache) live in the test export below — see
 * the regression test that wraps the hook in <StrictMode>.
 */
let inflightFetch: Promise<TaskListItem[] | null> | null = null;

async function getOrStartFetch(): Promise<TaskListItem[] | null> {
  if (inflightFetch !== null) return inflightFetch;
  const promise = (async (): Promise<TaskListItem[] | null> => {
    try {
      const result = await fetchAllTasks();
      if (!result.success) {
        // Non-401 errors are already typed; AuthRequired never reaches here
        // because apiClient throws + redirects. Log + continue (queue empty).
        console.warn('useTaskHistory: failed to fetch /task/all:', result.error.detail);
        return null;
      }
      return result.data;
    } catch (err) {
      // AuthRequiredError already redirected via apiClient. Anything else
      // we swallow + log — uploads must keep working.
      console.warn('useTaskHistory: unexpected error fetching /task/all:', err);
      return null;
    }
  })();
  inflightFetch = promise;
  // Clear cache on failure so a later remount can retry.
  void promise.then(value => {
    if (value === null) inflightFetch = null;
  });
  return promise;
}

/** Test-only cache reset. Not exported as part of the public hook API. */
export function __resetTaskHistoryCacheForTests(): void {
  inflightFetch = null;
}

/**
 * Hook: on mount, fetch /task/all and seed the queue.
 *
 * Returns void — caller composes side-effect via injected setters.
 * StrictMode-safe: the fetch is shared via a module-level inflight promise
 * so both dev double-mounts await the same result. Per-mount `cancelled`
 * flag prevents the unmounted instance from calling stale setters; the
 * survivor seeds normally. Queue-layer dedupe (taskId Set in
 * addHistoricTasks) handles any redundant call.
 */
export function useTaskHistory({
  addHistoricTasks,
  resumeProcessingTask,
}: UseTaskHistoryOptions): void {
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const tasks = await getOrStartFetch();
      if (cancelled) return;
      if (tasks === null) return;
      const historicItems = seedQueueFromTasks(tasks);
      if (historicItems.length === 0) return;
      addHistoricTasks(historicItems);

      // Re-bind WS for the first historic item still in 'processing'.
      // Single-task-at-a-time invariant matches existing orchestration.
      const firstProcessing = historicItems.find(item => item.status === 'processing');
      if (!firstProcessing) return;
      if (!firstProcessing.taskId) return;
      resumeProcessingTask(firstProcessing.id, firstProcessing.taskId);
    })();
    return () => {
      cancelled = true;
    };
  }, [addHistoricTasks, resumeProcessingTask]);
}
