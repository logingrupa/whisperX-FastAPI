import { Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranscriptDownload, type ExportFormat } from '@/hooks/useTranscriptDownload';
import type { TranscriptSegment, TaskMetadata } from '@/types/transcript';

interface DownloadButtonsProps {
  /** Already-fetched transcript segments, or null if not yet loaded. */
  segments: TranscriptSegment[] | null;
  /** Base filename without extension. */
  filename: string;
  /** Optional metadata used for JSON export. */
  metadata?: TaskMetadata;
  /**
   * Lazy loader. Called when a download is requested before `segments` is
   * present. Must return the loaded segments + metadata, or throw on
   * failure. Caller is responsible for caching the result so subsequent
   * calls re-use it.
   */
  onEnsureLoaded?: () => Promise<{
    segments: TranscriptSegment[];
    metadata?: TaskMetadata;
  }>;
}

const EXPORT_FORMATS: ReadonlyArray<{ format: ExportFormat; label: string }> = [
  { format: 'srt', label: 'SRT' },
  { format: 'vtt', label: 'VTT' },
  { format: 'txt', label: 'TXT' },
  { format: 'json', label: 'JSON' },
];

/**
 * Download format buttons for transcript export
 *
 * Renders SRT/VTT/TXT/JSON download triggers. Visible the moment a queue
 * row completes — clicking lazily fetches the transcript via
 * `onEnsureLoaded` if needed, then triggers download.
 */
export function DownloadButtons({
  segments,
  filename,
  metadata,
  onEnsureLoaded,
}: DownloadButtonsProps) {
  const { downloadTranscript } = useTranscriptDownload();

  const handleDownload = async (format: ExportFormat) => {
    let segs = segments;
    let meta = metadata;

    if (!segs) {
      if (!onEnsureLoaded) return;
      const loaded = await onEnsureLoaded();
      segs = loaded.segments;
      meta = loaded.metadata ?? meta;
    }

    downloadTranscript({ segments: segs, filename, format, metadata: meta });
  };

  return (
    <div className="queue-export-actions">
      {EXPORT_FORMATS.map(({ format, label }) => (
        <Button
          key={format}
          variant="outline"
          size="sm"
          onClick={() => handleDownload(format)}
          className="queue-export-button"
        >
          <Download className="queue-export-icon" />
          {label}
        </Button>
      ))}
    </div>
  );
}
