/**
 * API client for transcription service
 */
import type { LanguageCode, WhisperModel } from '@/types/upload';
import type { TranscriptionResponse, ApiResult } from '@/types/api';

interface StartTranscriptionParams {
  /** File to transcribe */
  file: File;
  /** Language code (e.g., 'en', 'lv', 'ru') */
  language: LanguageCode;
  /** Whisper model size */
  model: WhisperModel;
}

/**
 * Start transcription for a file
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
  params: StartTranscriptionParams
): Promise<ApiResult<TranscriptionResponse>> {
  const { file, language, model } = params;

  // Build FormData with file
  const formData = new FormData();
  formData.append('file', file);

  // Build query params for model settings
  const queryParams = new URLSearchParams({
    language,
    model,
  });

  try {
    const response = await fetch(`/speech-to-text?${queryParams}`, {
      method: 'POST',
      body: formData,
      // Note: Don't set Content-Type header - browser sets it with boundary
    });

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

    const data: TranscriptionResponse = await response.json();
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
