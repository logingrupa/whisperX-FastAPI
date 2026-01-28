import { Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranscriptDownload } from '@/hooks/useTranscriptDownload';
import type { TranscriptSegment, TaskMetadata } from '@/types/transcript';

interface DownloadButtonsProps {
  segments: TranscriptSegment[];
  filename: string; // Base filename without extension
  metadata?: TaskMetadata;
}

/**
 * Download format buttons for transcript export
 *
 * Provides buttons for downloading transcript in SRT, VTT, TXT, and JSON formats.
 * Uses useTranscriptDownload hook for blob generation and download.
 */
export function DownloadButtons({
  segments,
  filename,
  metadata
}: DownloadButtonsProps) {
  const { downloadTranscript } = useTranscriptDownload();

  const handleDownload = (format: 'srt' | 'vtt' | 'txt' | 'json') => {
    downloadTranscript({
      segments,
      filename,
      format,
      metadata,
    });
  };

  return (
    <div className="flex flex-wrap gap-2">
      <Button
        variant="outline"
        size="sm"
        onClick={() => handleDownload('srt')}
        className="gap-1"
      >
        <Download className="h-3 w-3" />
        SRT
      </Button>

      <Button
        variant="outline"
        size="sm"
        onClick={() => handleDownload('vtt')}
        className="gap-1"
      >
        <Download className="h-3 w-3" />
        VTT
      </Button>

      <Button
        variant="outline"
        size="sm"
        onClick={() => handleDownload('txt')}
        className="gap-1"
      >
        <Download className="h-3 w-3" />
        TXT
      </Button>

      <Button
        variant="outline"
        size="sm"
        onClick={() => handleDownload('json')}
        className="gap-1"
      >
        <Download className="h-3 w-3" />
        JSON
      </Button>
    </div>
  );
}
