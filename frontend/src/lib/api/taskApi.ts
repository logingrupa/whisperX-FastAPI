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
