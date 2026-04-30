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

/** Wire shape of GET /task/all */
interface TaskListResponseWire {
  tasks: TaskListItem[];
}

/**
 * Fetch all tasks for the authenticated user.
 *
 * Backend: GET /task/all (auth-scoped per Phase 13 — user only sees own rows).
 *
 * Tiger-style boundary assertion: response.tasks must be an array. A
 * malformed payload would silently produce an empty queue otherwise.
 *
 * @returns Array of task summaries on success, error details on failure
 */
export async function fetchAllTasks(): Promise<ApiResult<TaskListItem[]>> {
  try {
    const data = await apiClient.get<TaskListResponseWire>('/task/all');
    if (!data || !Array.isArray(data.tasks)) {
      return {
        success: false,
        error: { status: 0, detail: 'Malformed /task/all response — tasks not an array' },
      };
    }
    return { success: true, data: data.tasks };
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
