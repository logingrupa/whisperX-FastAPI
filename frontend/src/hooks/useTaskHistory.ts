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
import { useEffect, useRef, useState } from 'react';
import {
  fetchAllTasks,
  type FetchAllTasksOptions,
  type TaskListItem,
  type BackendTaskStatus,
} from '@/lib/api/taskApi';
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
  /** Optional q/status/page filters (Plan 15-ux pagination). */
  query?: FetchAllTasksOptions;
  /**
   * Replace queue contents on every fetch instead of appending.
   * Used by paginated callers — without it, switching pages would
   * pile every slice on top of the previous one.
   */
  replaceOnFetch?: boolean;
  /** Inject a fresh queue snapshot (replaces all rows, no de-dup). */
  setHistoricTasks?: (items: FileQueueItem[]) => void;
}

/** Pagination metadata surfaced back to the caller (Plan 15-ux). */
export interface TaskHistoryMeta {
  total: number;
  page: number;
  pageSize: number;
  loading: boolean;
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
 *
 * `historicSortIndex` is the row's position in the server response
 * (server orders `created_at DESC`). It seeds `createdAt` so the upload
 * orchestrator's FIFO picker observes a consistent age ordering across
 * live + historic items — older index = newer task = larger `createdAt`.
 */
export function taskToQueueItem(
  task: TaskListItem,
  historicSortIndex: number = 0,
): FileQueueItem | null {
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
    // Server slice is DESC by created_at: index 0 = newest. Map to a
    // descending `createdAt` so newer rows sort first and live items
    // (Date.now()-stamped) always appear newer than historic ones.
    createdAt: -historicSortIndex,
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
    .map((task, index) => taskToQueueItem(task, index))
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
/** Successful fetch payload — tasks slice + pagination meta (Plan 15-ux). */
interface FetchedHistory {
  tasks: TaskListItem[];
  total: number;
  page: number;
  pageSize: number;
}

let inflightFetch: Promise<FetchedHistory | null> | null = null;
let inflightKey: string | null = null;

/** Stable key for the inflight cache — same query reuses the promise. */
function queryKey(opts: FetchAllTasksOptions | undefined): string {
  if (!opts) return ':default';
  return [
    opts.q ?? '',
    opts.status ?? '',
    opts.page ?? '',
    opts.pageSize ?? '',
  ].join(':');
}

async function getOrStartFetch(
  opts: FetchAllTasksOptions | undefined,
): Promise<FetchedHistory | null> {
  const key = queryKey(opts);
  if (inflightFetch !== null && inflightKey === key) return inflightFetch;
  const promise = (async (): Promise<FetchedHistory | null> => {
    try {
      const result = await fetchAllTasks(opts);
      if (!result.success) {
        // Non-401 errors are already typed; AuthRequired never reaches here
        // because apiClient throws + redirects. Log + continue (queue empty).
        console.warn('useTaskHistory: failed to fetch /task/all:', result.error.detail);
        return null;
      }
      return {
        tasks: result.data.tasks,
        total: result.data.total,
        page: result.data.page,
        pageSize: result.data.page_size,
      };
    } catch (err) {
      // AuthRequiredError already redirected via apiClient. Anything else
      // we swallow + log — uploads must keep working.
      console.warn('useTaskHistory: unexpected error fetching /task/all:', err);
      return null;
    }
  })();
  inflightFetch = promise;
  inflightKey = key;
  // Clear cache on failure so a later remount can retry.
  void promise.then(value => {
    if (value === null && inflightKey === key) {
      inflightFetch = null;
      inflightKey = null;
    }
  });
  return promise;
}

/** Test-only cache reset. Not exported as part of the public hook API. */
export function __resetTaskHistoryCacheForTests(): void {
  inflightFetch = null;
  inflightKey = null;
}

/**
 * Hook: fetch /task/all and seed the queue, re-fetching whenever the
 * supplied query changes (Plan 15-ux pagination).
 *
 * SRP: this hook owns the fetch + query state caching; the component
 * (QueueFilterBar / TranscribePage) owns the input UI.
 *
 * StrictMode-safe: the fetch is shared via a module-level inflight promise
 * keyed by the current query so both dev double-mounts await the same
 * result. Per-mount `cancelled` flag prevents the unmounted instance from
 * calling stale setters; the survivor seeds normally. Queue-layer dedupe
 * (taskId Set in addHistoricTasks) handles any redundant call.
 *
 * When ``replaceOnFetch`` is true (paginated mode) the previous slice is
 * cleared via ``setHistoricTasks`` before injecting the new one — flipping
 * to page 2 must REPLACE the visible queue rather than append.
 */
export function useTaskHistory({
  addHistoricTasks,
  resumeProcessingTask,
  query,
  replaceOnFetch,
  setHistoricTasks,
}: UseTaskHistoryOptions): TaskHistoryMeta {
  const [meta, setMeta] = useState<TaskHistoryMeta>({
    total: 0,
    page: query?.page ?? 1,
    pageSize: query?.pageSize ?? 50,
    loading: true,
  });

  // Refs hold the latest query + replace mode + setters so the effect can
  // read them without subscribing — dependency on the serialised key is
  // the ONLY thing that triggers re-fetch. Otherwise React's "new object
  // identity per render" would loop the effect → fetch → setMeta → render.
  const queryRef = useRef<FetchAllTasksOptions | undefined>(query);
  queryRef.current = query;
  const replaceOnFetchRef = useRef<boolean | undefined>(replaceOnFetch);
  replaceOnFetchRef.current = replaceOnFetch;
  const setHistoricTasksRef = useRef<typeof setHistoricTasks>(setHistoricTasks);
  setHistoricTasksRef.current = setHistoricTasks;
  const addHistoricTasksRef = useRef(addHistoricTasks);
  addHistoricTasksRef.current = addHistoricTasks;
  const resumeProcessingTaskRef = useRef(resumeProcessingTask);
  resumeProcessingTaskRef.current = resumeProcessingTask;

  // Stable serialised key for effect deps — primitives only, no new object
  // identity per render. This is the SOLE re-fetch trigger.
  const querySerialised = queryKey(query);

  useEffect(() => {
    let cancelled = false;
    setMeta(previous => ({ ...previous, loading: true }));
    // Each query mounts a fresh module-level fetch — invalidate the prior
    // cache so a new key forces a real round-trip rather than serving the
    // previous slice. The inflight promise itself dedupes concurrent
    // mounts of the SAME query (StrictMode safety).
    if (inflightKey !== querySerialised) {
      inflightFetch = null;
      inflightKey = null;
    }
    void (async () => {
      const fetched = await getOrStartFetch(queryRef.current);
      if (cancelled) return;
      if (fetched === null) {
        setMeta(previous => ({ ...previous, loading: false }));
        return;
      }
      setMeta({
        total: fetched.total,
        page: fetched.page,
        pageSize: fetched.pageSize,
        loading: false,
      });
      const historicItems = seedQueueFromTasks(fetched.tasks);

      // Replace mode: clear queue first, then inject. Append mode (default)
      // delegates to addHistoricTasks which de-dups by taskId.
      const useReplace =
        replaceOnFetchRef.current === true &&
        setHistoricTasksRef.current !== undefined;
      if (useReplace) {
        setHistoricTasksRef.current?.(historicItems);
      } else if (historicItems.length > 0) {
        addHistoricTasksRef.current(historicItems);
      }

      // Re-bind WS for the first historic item still in 'processing'.
      // Single-task-at-a-time invariant matches existing orchestration.
      const firstProcessing = historicItems.find(item => item.status === 'processing');
      if (!firstProcessing) return;
      if (!firstProcessing.taskId) return;
      resumeProcessingTaskRef.current(firstProcessing.id, firstProcessing.taskId);
    })();
    return () => {
      cancelled = true;
    };
    // querySerialised is the SOLE re-fetch trigger; refs absorb identity
    // churn from the parent so callbacks/replace-mode/setters can change
    // without firing a redundant fetch.
  }, [querySerialised]);

  return meta;
}
