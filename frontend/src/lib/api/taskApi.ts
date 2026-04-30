/**
 * API client for task management — refactored Phase 14 to use apiClient.
 *
 * Public surface (return shape) is preserved: ApiResult<TaskResult>.
 * Internal transport swapped from raw fetch to apiClient (UI-11).
 * apiClient supplies: credentials:'include', X-CSRF-Token, 401-redirect, 429-typed.
 */
import type { ApiResult } from '@/types/api';
import type { TaskResult } from '@/types/transcript';
import {
  apiClient,
  ApiClientError,
  AuthRequiredError,
  RateLimitError,
} from '@/lib/apiClient';

/**
 * Backend task status string (snake_case from app.domain.entities.task).
 * Mirrors the three terminal/non-terminal states emitted by TaskMapper.to_summary.
 */
export type BackendTaskStatus = 'processing' | 'completed' | 'failed';

/**
 * Single item from GET /task/all — mirrors TaskSummaryResponse on the backend
 * (app/api/schemas/task_schemas.py::TaskSummaryResponse).
 *
 * Field names are snake_case because the backend does NOT configure an
 * alias_generator on the Pydantic model — what FastAPI serializes is what
 * the wire carries.
 */
export interface TaskListItem {
  identifier: string;
  status: BackendTaskStatus | string;
  task_type: string;
  file_name: string | null;
  url: string | null;
  audio_duration: number | null;
  language: string | null;
  error: string | null;
  duration: number | null;
  start_time: string | null;
  end_time: string | null;
}

/** Wire shape of GET /task/all (Plan 15-ux: pagination envelope). */
interface TaskListResponseWire {
  tasks: TaskListItem[];
  total?: number;
  page?: number;
  page_size?: number;
}

/**
 * Paginated response envelope returned to callers (Plan 15-ux).
 *
 * Wraps the previous bare-array shape so consumers can render
 * "Page N of M" without a second round-trip. Field names mirror
 * the backend wire contract (snake_case, no alias_generator).
 */
export interface TaskListResponseV2 {
  tasks: TaskListItem[];
  total: number;
  page: number;
  page_size: number;
}

/**
 * Optional filter / pagination args for fetchAllTasks (Plan 15-ux).
 *
 * Omitted fields are not appended to the URL — backend defaults apply
 * (page=1, page_size=50, no filters). Caller does not need to know the
 * server defaults.
 */
export interface FetchAllTasksOptions {
  /** Case-insensitive substring match against file_name. */
  q?: string;
  /** Exact-match status (processing|completed|failed). */
  status?: string;
  /** 1-indexed page number. */
  page?: number;
  /** Items per page (1..200). */
  pageSize?: number;
}

/**
 * Build the URL for GET /task/all with the supplied options.
 *
 * SRP: pure builder — DRY-friendly, easily unit-tested. Empty / undefined
 * values are dropped so the wire URL stays minimal.
 */
function buildTaskListUrl(opts: FetchAllTasksOptions | undefined): string {
  const params = new URLSearchParams();
  if (opts?.q && opts.q.length > 0) params.set('q', opts.q);
  if (opts?.status && opts.status.length > 0) params.set('status', opts.status);
  if (opts?.page !== undefined) params.set('page', String(opts.page));
  if (opts?.pageSize !== undefined) params.set('page_size', String(opts.pageSize));
  const query = params.toString();
  return query.length === 0 ? '/task/all' : `/task/all?${query}`;
}

/**
 * Fetch tasks for the authenticated user (Plan 15-ux paginated).
 *
 * Backend: GET /task/all (auth-scoped per Phase 13 — user only sees own rows).
 *
 * Single fetch site for the queue (DRY). Returns the full envelope so
 * callers can render pagination + totals without a second request.
 *
 * Tiger-style boundary assertion: response.tasks must be an array. A
 * malformed payload would silently produce an empty queue otherwise.
 *
 * @param opts Optional q/status/page/pageSize filters.
 * @returns TaskListResponseV2 envelope on success, error details on failure.
 */
export async function fetchAllTasks(
  opts?: FetchAllTasksOptions,
): Promise<ApiResult<TaskListResponseV2>> {
  try {
    const url = buildTaskListUrl(opts);
    const data = await apiClient.get<TaskListResponseWire>(url);
    if (!data || !Array.isArray(data.tasks)) {
      return {
        success: false,
        error: { status: 0, detail: 'Malformed /task/all response — tasks not an array' },
      };
    }
    // Defensive defaults — backwards compatible with any older mock that
    // returns only { tasks: [] }. Production backend always sets these.
    const total = typeof data.total === 'number' ? data.total : data.tasks.length;
    const page = typeof data.page === 'number' ? data.page : 1;
    const pageSize = typeof data.page_size === 'number' ? data.page_size : data.tasks.length;
    return {
      success: true,
      data: { tasks: data.tasks, total, page, page_size: pageSize },
    };
  } catch (err) {
    if (err instanceof AuthRequiredError) {
      // apiClient already redirected — propagate so caller's catch flows
      throw err;
    }
    if (err instanceof RateLimitError) {
      return {
        success: false,
        error: { status: 429, detail: `Rate limited; retry in ${err.retryAfterSeconds}s` },
      };
    }
    if (err instanceof ApiClientError) {
      return { success: false, error: { status: err.status, detail: err.message } };
    }
    return {
      success: false,
      error: { status: 0, detail: err instanceof Error ? err.message : 'Network error' },
    };
  }
}

/**
 * Fetch task result including transcript segments.
 *
 * Retrieves full task details from GET /task/{identifier}.
 * Only call this for completed tasks — the result.segments array
 * will be null/undefined for tasks still in progress.
 *
 * @param taskId - The task identifier (UUID)
 * @returns Task result on success, error details on failure
 */
export async function fetchTaskResult(
  taskId: string,
): Promise<ApiResult<TaskResult>> {
  try {
    const data = await apiClient.get<TaskResult>(`/task/${taskId}`);
    return { success: true, data };
  } catch (err) {
    if (err instanceof AuthRequiredError) {
      // apiClient already redirected the page — propagate so the catch flows
      throw err;
    }
    if (err instanceof RateLimitError) {
      return {
        success: false,
        error: {
          status: 429,
          detail: `Rate limited; retry in ${err.retryAfterSeconds}s`,
        },
      };
    }
    if (err instanceof ApiClientError) {
      return {
        success: false,
        error: { status: err.status, detail: err.message },
      };
    }
    return {
      success: false,
      error: {
        status: 0,
        detail: err instanceof Error ? err.message : 'Network error',
      },
    };
  }
}
