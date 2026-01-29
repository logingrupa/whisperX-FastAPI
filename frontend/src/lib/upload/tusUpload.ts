/**
 * TUS upload wrapper around tus-js-client.
 *
 * Provides a factory function that creates a configured tus.Upload instance
 * with project-standard defaults (chunk size, retry, metadata).
 * The caller is responsible for calling `.start()` on the returned instance.
 *
 * This module has NO React dependency -- it is a pure library utility.
 */

import * as tus from 'tus-js-client';

import { TUS_CHUNK_SIZE, TUS_ENDPOINT, TUS_RETRY_DELAYS } from './constants';

/** Callbacks for upload lifecycle events. */
export interface TusUploadCallbacks {
  onProgress(bytesSent: number, bytesTotal: number): void;
  onSuccess(tusUrl: string): void;
  onError(error: Error): void;
}

/**
 * Create a configured TUS upload instance.
 *
 * @param file      - The file to upload.
 * @param metadata  - Key-value metadata sent via TUS Upload-Metadata header.
 * @param callbacks - Lifecycle callbacks for progress, success, and error.
 * @returns A tus.Upload instance. Call `.start()` to begin uploading.
 */
export function createTusUpload(
  file: File,
  metadata: Record<string, string>,
  callbacks: TusUploadCallbacks,
): tus.Upload {
  const upload = new tus.Upload(file, {
    endpoint: TUS_ENDPOINT,
    chunkSize: TUS_CHUNK_SIZE,
    retryDelays: TUS_RETRY_DELAYS,
    metadata,
    // Resume is Phase 9 scope -- disable fingerprint storage for now
    storeFingerprintForResuming: false,
    removeFingerprintOnSuccess: true,
    onProgress: callbacks.onProgress,
    onSuccess: () => {
      callbacks.onSuccess(upload.url ?? '');
    },
    onError: (error) => {
      callbacks.onError(error instanceof Error ? error : new Error(String(error)));
    },
  });

  return upload;
}

/** Check whether the current browser supports TUS uploads. */
export function isTusSupported(): boolean {
  return tus.isSupported;
}
