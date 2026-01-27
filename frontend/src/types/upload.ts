/**
 * Upload flow type definitions
 * Used by file queue, language detection, and model selection
 */

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

/** A file in the upload queue with its settings */
export interface FileQueueItem {
  /** Unique identifier for this queue item */
  id: string;
  /** The actual File object from the browser */
  file: File;
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
