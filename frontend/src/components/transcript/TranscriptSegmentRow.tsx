import { Badge } from '@/components/ui/badge';
import type { TranscriptSegment } from '@/types/transcript';

interface TranscriptSegmentRowProps {
  segment: TranscriptSegment;
  index: number;
}

/**
 * Format seconds to MM:SS or HH:MM:SS for display
 */
function formatTimestamp(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }
  return `${minutes}:${String(secs).padStart(2, '0')}`;
}

/**
 * Format speaker label for display
 * Converts "SPEAKER_00" to "Speaker 1", "SPEAKER_01" to "Speaker 2", etc.
 */
function formatSpeakerLabel(speaker: string | null): string | null {
  if (!speaker) return null;

  // Handle "SPEAKER_XX" format from diarization
  const match = speaker.match(/SPEAKER_(\d+)/i);
  if (match) {
    const speakerNumber = parseInt(match[1], 10) + 1;
    return `Speaker ${speakerNumber}`;
  }

  // Return as-is if different format
  return speaker;
}

/**
 * Single transcript segment with timestamp and speaker label
 */
export function TranscriptSegmentRow({ segment, index }: TranscriptSegmentRowProps) {
  const speakerLabel = formatSpeakerLabel(segment.speaker);

  return (
    <div className="flex gap-3 py-2 border-b border-border last:border-b-0">
      {/* Timestamp */}
      <div className="shrink-0 w-20 text-xs text-muted-foreground font-mono">
        {formatTimestamp(segment.start)}
      </div>

      {/* Speaker badge (if present) */}
      <div className="shrink-0 w-24">
        {speakerLabel && (
          <Badge variant="outline" className="text-xs">
            {speakerLabel}
          </Badge>
        )}
      </div>

      {/* Text content */}
      <div className="flex-1 text-sm">
        {segment.text}
      </div>
    </div>
  );
}
