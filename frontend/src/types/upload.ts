/**
 * Upload flow type definitions
 * Used by file queue, language detection, and model selection
 */

import type { ProgressStage } from './websocket';

export type { ProgressStage } from './websocket';

/** Whisper model sizes available for transcription */
export type WhisperModel = 'tiny' | 'base' | 'small' | 'medium' | 'large-v3' | 'turbo';

/** ISO 639-1 language codes supported for transcription */
export type LanguageCode =
  | 'lv' | 'ru' | 'en'  // Core 3
  | 'de' | 'fr' | 'es' | 'it' | 'pt' | 'nl' | 'pl'  // European
  | 'ja' | 'ko' | 'zh'  // Asian
  | 'ar' | 'hi' | 'tr';  // Other common

/** Status of a file in the upload queue */
export type FileQueueItemStatus = 'pending' | 'uploading' | 'processing' | 'complete' | 'error';

/**
 * Discriminator for queue item origin.
 *
 * - 'live' — added by user this session via dropzone; has File object;
 *           may be uploaded / cancelled / removed before processing.
 * - 'historic' — seeded from GET /task/all on mount; File object is null;
 *                read-only for upload concerns; in-flight items still
 *                receive WebSocket progress updates via existing infra.
 */
export type FileQueueItemKind = 'live' | 'historic';

/** A file in the upload queue with its settings */
export interface FileQueueItem {
  /** Unique identifier for this queue item */
  id: string;
  /** Origin discriminator — historic items have file === null */
  kind: FileQueueItemKind;
  /**
   * The actual File object from the browser.
   * NULL for historic items seeded from /task/all (no File available
   * after page refresh — only metadata persists in DB).
   */
  file: File | null;
  /** Filename for display — sourced from File.name (live) or backend file_name (historic). */
  fileName: string;
  /** File size in bytes — sourced from File.size (live) or 0 for historic (size not persisted). */
  fileSize: number;
  /** Language detected from filename pattern (null if not detected) */
  detectedLanguage: LanguageCode | null;
  /** User-selected or auto-detected language for transcription */
  selectedLanguage: LanguageCode | '';
  /** User-selected Whisper model size */
  selectedModel: WhisperModel;
  /** Current status in the queue */
  status: FileQueueItemStatus;
  /** Error message if status is 'error' */
  errorMessage?: string;
  /** Technical error details for debugging (shown via "Show details") */
  technicalDetail?: string;
  /** Backend task ID for WebSocket subscription (set after upload starts) */
  taskId?: string;
  /** Current progress percentage (0-100) */
  progressPercentage?: number;
  /** Current processing stage */
  progressStage?: ProgressStage;
  /** Upload speed formatted (e.g., "12.3 MB/s") -- set during upload phase */
  uploadSpeed?: string;
  /** Estimated time remaining formatted (e.g., "2m 15s") -- set during upload phase */
  uploadEta?: string;
  /**
   * Insertion timestamp (ms since epoch).
   *
   * Plan 15-ux: display order is LIFO (newest live items prepend) so the
   * just-selected file is visible without scrolling. Upload semantics
   * stay FIFO — orchestration picks the OLDEST ready item by this stamp,
   * not by array order. Decoupling display order from processing order
   * keeps both invariants intact.
   */
  createdAt: number;
}

/** Language definition for display */
export interface Language {
  code: LanguageCode;
  name: string;
  nativeName: string;
}

/** Whisper model definition for display */
export interface WhisperModelInfo {
  value: WhisperModel;
  label: string;
  description: string;
}
