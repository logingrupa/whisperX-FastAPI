/**
 * Upload constants for TUS chunked upload and file size routing.
 *
 * These values are shared between the TUS upload wrapper and the
 * orchestration hook that routes files to the correct upload path.
 */

/** Files >= 80 MB use TUS chunked upload; smaller files use direct POST. */
export const SIZE_THRESHOLD = 80 * 1024 * 1024;

/** 50 MB per chunk -- safe margin under Cloudflare's 100 MB request body limit. */
export const TUS_CHUNK_SIZE = 50 * 1024 * 1024;

/** TUS endpoint matching tuspyserver router mount from Phase 7. */
export const TUS_ENDPOINT = '/uploads/files/';

/** Retry delays (ms) for transient upload failures. */
export const TUS_RETRY_DELAYS = [0, 1000, 3000, 5000];
