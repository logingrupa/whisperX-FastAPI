import { ScrollArea } from '@/components/ui/scroll-area';
import { TranscriptSegmentRow } from './TranscriptSegmentRow';
import type { TranscriptSegment } from '@/types/transcript';

interface TranscriptViewerProps {
  segments: TranscriptSegment[];
  maxHeight?: string; // Default: "300px"
}

/**
 * Scrollable transcript viewer with segments
 *
 * Displays all transcript segments in a scrollable container.
 * Uses shadcn/ui ScrollArea for consistent styling.
 */
export function TranscriptViewer({
  segments,
  maxHeight = "300px"
}: TranscriptViewerProps) {
  if (segments.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No transcript segments available
      </div>
    );
  }

  return (
    <ScrollArea className="rounded-md border" style={{ maxHeight }}>
      <div className="p-4">
        {/* Header row */}
        <div className="flex gap-3 pb-2 border-b border-border text-xs font-medium text-muted-foreground">
          <div className="shrink-0 w-20">Time</div>
          <div className="shrink-0 w-24">Speaker</div>
          <div className="flex-1">Text</div>
        </div>

        {/* Segment rows */}
        {segments.map((segment, index) => (
          <TranscriptSegmentRow
            key={`${segment.start}-${index}`}
            segment={segment}
            index={index}
          />
        ))}
      </div>
    </ScrollArea>
  );
}
