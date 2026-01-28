/**
 * Plain text transcript formatter
 * Produces readable text files with optional timestamps
 */

import type { TranscriptSegment } from '@/types/transcript';

/**
 * Format seconds as readable timestamp: HH:MM:SS
 */
function formatTimestamp(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  return (
    String(hours).padStart(2, '0') +
    ':' +
    String(minutes).padStart(2, '0') +
    ':' +
    String(secs).padStart(2, '0')
  );
}

/**
 * Format transcript segments as plain text
 *
 * Output formats:
 * - With speaker: "[SPEAKER_00]: Hello world"
 * - Without speaker: "Hello world"
 * - With timestamps: "[00:00:01] [SPEAKER_00]: Hello world"
 */
export function formatTranscriptAsTxt(
  segments: TranscriptSegment[],
  includeTimestamps: boolean = false
): string {
  return segments
    .map((segment) => {
      const parts: string[] = [];

      if (includeTimestamps) {
        parts.push(`[${formatTimestamp(segment.start)}]`);
      }

      if (segment.speaker) {
        parts.push(`[${segment.speaker}]:`);
      }

      parts.push(segment.text);

      return parts.join(' ');
    })
    .join('\n');
}
