/**
 * Transcript type definitions
 * Types for transcript data, segments, and task results
 */

/**
 * A single segment of transcribed speech.
 * Matches backend WhisperX segment output structure.
 */
export interface TranscriptSegment {
  /** Start time in seconds (e.g., 1.5) */
  start: number;
  /** End time in seconds */
  end: number;
  /** Transcribed text content */
  text: string;
  /** Speaker identifier from diarization (e.g., "SPEAKER_00", "SPEAKER_01"), null if no diarization */
  speaker: string | null;
}

/**
 * Metadata about a transcription task.
 * Used for JSON export and display purposes.
 */
export interface TaskMetadata {
  /** Original filename of the uploaded audio */
  fileName: string | null;
  /** Detected or specified language code (e.g., "en", "lv") */
  language: string | null;
  /** Total duration of the audio in seconds */
  audioDuration: number | null;
}

/**
 * Full task result from GET /task/{identifier} endpoint.
 * Matches backend TaskResponse schema from task_schemas.py.
 */
export interface TaskResult {
  /** Unique task identifier (UUID) */
  identifier: string;
  /** Current task status (e.g., "queued", "processing", "completed", "failed") */
  status: string;
  /** Type of task (e.g., "transcribe") */
  taskType: string;
  /** Original filename */
  fileName: string | null;
  /** URL if file was fetched from remote source */
  url: string | null;
  /** Audio duration in seconds */
  audioDuration: number | null;
  /** Language code used for transcription */
  language: string | null;
  /** Additional task parameters */
  taskParams: Record<string, unknown> | null;
  /** Transcription result containing segments */
  result: { segments: TranscriptSegment[] } | null;
  /** Error message if task failed */
  error: string | null;
  /** Task execution duration in seconds */
  duration: number | null;
  /** Task processing start time (ISO 8601) */
  startTime: string | null;
  /** Task processing end time (ISO 8601) */
  endTime: string | null;
  /** Task creation time (ISO 8601) */
  createdAt: string;
  /** Last update time (ISO 8601) */
  updatedAt: string;
}
