/**
 * API response types matching backend schemas
 */

/** Response from POST /speech-to-text (full pipeline transcription) */
export interface TranscriptionResponse {
  /** Task ID for WebSocket subscription */
  identifier: string;
  /** Status message (e.g., "Task queued") */
  message: string;
}

/** Standard API error response */
export interface ApiError {
  /** HTTP status code */
  status: number;
  /** Error detail from backend */
  detail: string;
}

/** Result type for API calls */
export type ApiResult<T> =
  | { success: true; data: T }
  | { success: false; error: ApiError };
