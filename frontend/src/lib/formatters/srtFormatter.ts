/**
 * SRT (SubRip) format transcript formatter
 * Produces .srt subtitle files compatible with video players
 */

import type { TranscriptSegment } from '@/types/transcript';

/**
 * Format seconds as SRT timestamp: HH:MM:SS,mmm
 * SRT spec uses comma for milliseconds separator
 */
export function formatSrtTimestamp(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  const milliseconds = Math.round((seconds - Math.floor(seconds)) * 1000);

  return (
    String(hours).padStart(2, '0') +
    ':' +
    String(minutes).padStart(2, '0') +
    ':' +
    String(secs).padStart(2, '0') +
    ',' +
    String(milliseconds).padStart(3, '0')
  );
}

/**
 * Format transcript segments as SRT subtitle format
 *
 * Output format per entry:
 * 1
 * 00:00:01,500 --> 00:00:03,200
 * [SPEAKER_00] Hello world
 *
 * (blank line between entries)
 */
export function formatTranscriptAsSrt(segments: TranscriptSegment[]): string {
  return segments
    .map((segment, index) => {
      const startTimestamp = formatSrtTimestamp(segment.start);
      const endTimestamp = formatSrtTimestamp(segment.end);
      const speakerPrefix = segment.speaker ? `[${segment.speaker}] ` : '';

      return `${index + 1}\n${startTimestamp} --> ${endTimestamp}\n${speakerPrefix}${segment.text}`;
    })
    .join('\n\n');
}
