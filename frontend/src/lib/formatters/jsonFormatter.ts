/**
 * JSON transcript formatter
 * Preserves all segment data with optional metadata
 */

import type { TranscriptSegment, TaskMetadata } from '@/types/transcript';

interface JsonTranscriptOutput {
  metadata?: TaskMetadata;
  segments: TranscriptSegment[];
}

/**
 * Format transcript segments as JSON with optional metadata
 *
 * Output structure:
 * {
 *   "metadata": { ... },  // optional
 *   "segments": [ ... ]
 * }
 */
export function formatTranscriptAsJson(
  segments: TranscriptSegment[],
  metadata?: TaskMetadata
): string {
  const output: JsonTranscriptOutput = { segments };

  if (metadata) {
    output.metadata = metadata;
  }

  return JSON.stringify(output, null, 2);
}
