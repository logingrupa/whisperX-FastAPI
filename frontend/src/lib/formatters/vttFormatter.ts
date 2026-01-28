/**
 * VTT (WebVTT) format transcript formatter
 * Produces .vtt subtitle files for HTML5 video
 */

import type { TranscriptSegment } from '@/types/transcript';

/**
 * Format seconds as VTT timestamp: HH:MM:SS.mmm
 * VTT spec uses period for milliseconds separator
 */
export function formatVttTimestamp(seconds: number): string {
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
    '.' +
    String(milliseconds).padStart(3, '0')
  );
}

/**
 * Format transcript segments as WebVTT subtitle format
 *
 * Output format:
 * WEBVTT
 *
 * 00:00:01.500 --> 00:00:03.200
 * <v SPEAKER_00>Hello world</v>
 *
 * (blank line between entries)
 */
export function formatTranscriptAsVtt(segments: TranscriptSegment[]): string {
  const header = 'WEBVTT\n\n';

  const cues = segments
    .map((segment) => {
      const startTimestamp = formatVttTimestamp(segment.start);
      const endTimestamp = formatVttTimestamp(segment.end);

      // VTT uses voice tags for speakers: <v SPEAKER_00>text</v>
      const text = segment.speaker
        ? `<v ${segment.speaker}>${segment.text}</v>`
        : segment.text;

      return `${startTimestamp} --> ${endTimestamp}\n${text}`;
    })
    .join('\n\n');

  return header + cues;
}
