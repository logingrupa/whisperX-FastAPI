import { TranscriptSegmentRow } from './TranscriptSegmentRow';
import type { TranscriptSegment } from '@/types/transcript';

interface TranscriptViewerProps {
  segments: TranscriptSegment[];
  /**
   * Optional max-height. When omitted (default in queue rows) the viewer
   * grows inline so the queue card re-flows naturally — fixes the
   * absolute/clipping overlap bug where a fixed-height ScrollArea inside
   * a Collapsible bled over sibling cards.
   */
  maxHeight?: string;
}

/**
 * Inline transcript viewer with segments
 *
 * Renders segments in normal document flow so the parent card grows
 * with the content. The legacy `maxHeight` prop is preserved for
 * non-queue callers; when supplied it caps the rendered height with a
 * native `overflow-y: auto` (no Radix `display: table` interaction).
 */
export function TranscriptViewer({
  segments,
  maxHeight,
}: TranscriptViewerProps) {
  if (segments.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No transcript segments available
      </div>
    );
  }

  const containerStyle = maxHeight ? { maxHeight, overflowY: 'auto' as const } : undefined;

  return (
    <div className="rounded-md border" style={containerStyle}>
      <div className="p-3 sm:p-4">
        {/* Header row */}
        <div className="transcript-header">
          <div className="transcript-cell-time">Time</div>
          <div className="transcript-cell-speaker">Speaker</div>
          <div className="transcript-cell-text">Text</div>
        </div>

        {/* Segment rows */}
        {segments.map((segment, index) => (
          <TranscriptSegmentRow
            key={`${segment.start}-${index}`}
            segment={segment}
          />
        ))}
      </div>
    </div>
  );
}
