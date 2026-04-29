/**
 * API client for transcription service — refactored Phase 14 to use apiClient.
 *
 * apiClient handles credentials/CSRF/401-redirect/429-typed (UI-11).
 * FormData body passed through unchanged — apiClient detects it and skips
 * Content-Type so the browser sets multipart boundary correctly.
 */
import type { LanguageCode, WhisperModel } from '@/types/upload';
import type { TranscriptionResponse, ApiResult } from '@/types/api';
import {
  apiClient,
  ApiClientError,
  AuthRequiredError,
  RateLimitError,
} from '@/lib/apiClient';

interface StartTranscriptionParams {
  /** File to transcribe */
  file: File;
  /** Language code (e.g., 'en', 'lv', 'ru') */
  language: LanguageCode;
  /** Whisper model size */
  model: WhisperModel;
}

/**
 * Start transcription for a file.
 *
 * Posts file to /speech-to-text endpoint and returns task ID.
 * This endpoint runs the full pipeline: transcription -> alignment -> diarization
 * emitting progress updates for all 5 stages.
 * The task ID is used to subscribe to WebSocket progress updates.
 *
 * @param params - File, language, and model parameters
 * @returns Task ID on success, error details on failure
 */
export async function startTranscription(
  params: StartTranscriptionParams,
): Promise<ApiResult<TranscriptionResponse>> {
  const { file, language, model } = params;

  const formData = new FormData();
  formData.append('file', file);
  const queryParams = new URLSearchParams({ language, model });

  try {
    const data = await apiClient.post<TranscriptionResponse>(
      `/speech-to-text?${queryParams.toString()}`,
      formData,
    );
    return { success: true, data };
  } catch (err) {
    if (err instanceof AuthRequiredError) {
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
