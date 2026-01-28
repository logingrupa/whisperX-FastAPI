/**
 * Hook for downloading transcripts in various formats
 * Creates blob files and triggers browser download
 */

import { useCallback } from 'react';
import type { TranscriptSegment, TaskMetadata } from '@/types/transcript';
import {
  formatTranscriptAsSrt,
  formatTranscriptAsVtt,
  formatTranscriptAsTxt,
  formatTranscriptAsJson,
} from '@/lib/formatters';

/** Supported export formats */
export type ExportFormat = 'srt' | 'vtt' | 'txt' | 'json';

/** Options for downloading a transcript */
export interface DownloadOptions {
  /** Transcript segments to export */
  segments: TranscriptSegment[];
  /** Base filename without extension */
  filename: string;
  /** Export format */
  format: ExportFormat;
  /** Optional metadata (used for JSON format) */
  metadata?: TaskMetadata;
}

/**
 * Hook that provides transcript download functionality
 *
 * Creates blob files with UTF-8 encoding for proper handling
 * of non-ASCII characters (Latvian, Russian, etc.)
 */
export function useTranscriptDownload() {
  const downloadTranscript = useCallback((options: DownloadOptions) => {
    const { segments, filename, format, metadata } = options;

    // Generate content based on format
    let content: string;
    let mimeType: string;
    let extension: string;

    switch (format) {
      case 'srt':
        content = formatTranscriptAsSrt(segments);
        mimeType = 'text/plain';
        extension = 'srt';
        break;
      case 'vtt':
        content = formatTranscriptAsVtt(segments);
        mimeType = 'text/vtt';
        extension = 'vtt';
        break;
      case 'txt':
        content = formatTranscriptAsTxt(segments);
        mimeType = 'text/plain';
        extension = 'txt';
        break;
      case 'json':
        content = formatTranscriptAsJson(segments, metadata);
        mimeType = 'application/json';
        extension = 'json';
        break;
    }

    // Create blob with UTF-8 encoding for international characters
    const blob = new Blob([content], { type: `${mimeType}; charset=utf-8` });
    const url = URL.createObjectURL(blob);

    // Create temporary anchor element and trigger download
    const link = document.createElement('a');
    link.href = url;
    link.download = `${filename}.${extension}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    // Revoke blob URL to prevent memory leak
    URL.revokeObjectURL(url);
  }, []);

  return { downloadTranscript };
}
