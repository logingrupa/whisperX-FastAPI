/**
 * API client for task management
 */
import type { ApiResult } from '@/types/api';
import type { TaskResult } from '@/types/transcript';

/**
 * Fetch task result including transcript segments
 *
 * Retrieves full task details from GET /task/{identifier}.
 * Only call this for completed tasks - the result.segments array
 * will be null/undefined for tasks still in progress.
 *
 * @param taskId - The task identifier (UUID)
 * @returns Task result on success, error details on failure
 */
export async function fetchTaskResult(
  taskId: string
): Promise<ApiResult<TaskResult>> {
  try {
    const response = await fetch(`/task/${taskId}`);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
      return {
        success: false,
        error: {
          status: response.status,
          detail: errorData.detail || `HTTP ${response.status}`,
        },
      };
    }

    const data: TaskResult = await response.json();
    return { success: true, data };

  } catch (error) {
    // Network error or other failure
    return {
      success: false,
      error: {
        status: 0,
        detail: error instanceof Error ? error.message : 'Network error',
      },
    };
  }
}
