import type { LanguageCode } from '@/types/upload';

/**
 * Filename patterns that indicate language
 * Based on user requirement: A03=Latvian, A04=Russian, A05=English
 */
const LANGUAGE_PATTERNS: Record<string, LanguageCode> = {
  'A03': 'lv',
  'A04': 'ru',
  'A05': 'en',
};

/**
 * Detect language from filename pattern
 * Looks for A03, A04, A05 patterns anywhere in the filename (case-insensitive)
 *
 * @param filename - The filename to analyze
 * @returns Detected language code or null if no pattern found
 *
 * @example
 * detectLanguageFromFilename('interview_A03_final.mp3') // 'lv' (Latvian)
 * detectLanguageFromFilename('A04_recording.wav') // 'ru' (Russian)
 * detectLanguageFromFilename('meeting.mp3') // null
 */
export function detectLanguageFromFilename(filename: string): LanguageCode | null {
  // Match A03, A04, or A05 anywhere in filename (case-insensitive)
  const match = filename.match(/A0[345]/i);

  if (match) {
    const pattern = match[0].toUpperCase();
    return LANGUAGE_PATTERNS[pattern] ?? null;
  }

  return null;
}
