/**
 * TUS upload error classifier.
 *
 * Maps tus-js-client DetailedError instances to user-friendly messages
 * with technical detail for logging.  Pure module -- no React imports,
 * no side effects.
 */

/** Classified upload error with user-facing and technical information. */
export interface ClassifiedUploadError {
  /** Human-readable message safe to show in the UI. */
  userMessage: string;
  /** Technical detail including HTTP status and response body for logging. */
  technicalDetail: string;
  /** Whether the error is potentially recoverable with a retry. */
  isRetryable: boolean;
}

/**
 * Shape of tus-js-client DetailedError -- used for duck-typing the
 * error argument so we do not need a runtime import of tus-js-client.
 */
interface TusDetailedErrorLike {
  originalResponse?: {
    getStatus(): number;
    getBody(): string;
  } | null;
  message?: string;
}

/**
 * Try to extract a human-readable message from the server body.
 *
 * Handles the three shapes our backend emits (see ``apiClient.parseErrorBody``):
 *   1. ``{ "error": { "message": "...", "code": "..." } }`` (ApplicationError.to_dict)
 *   2. ``{ "detail": { "message": "..." } }``               (HTTPException dict)
 *   3. ``{ "detail": "..." }``                              (HTTPException string)
 *
 * Returns ``null`` when nothing useful is available so the caller falls
 * back to the status-based generic message.
 */
function extractServerMessage(rawBody: string): string | null {
  if (!rawBody) return null;
  try {
    const parsed = JSON.parse(rawBody) as unknown;
    if (parsed === null || typeof parsed !== 'object') return null;
    const obj = parsed as Record<string, unknown>;

    const err = obj.error;
    if (err !== null && typeof err === 'object') {
      const e = err as Record<string, unknown>;
      const msg = e.user_message ?? e.message;
      if (typeof msg === 'string' && msg.length > 0) return msg;
    }

    const detail = obj.detail;
    if (detail !== null && typeof detail === 'object') {
      const d = detail as Record<string, unknown>;
      const msg = d.user_message ?? d.message;
      if (typeof msg === 'string' && msg.length > 0) return msg;
    }

    if (typeof detail === 'string' && detail.length > 0) return detail;
  } catch {
    // Not JSON — server probably returned plain text or HTML; ignore.
  }
  return null;
}

/** Classify a TUS upload error into a user-friendly representation. */
export function classifyUploadError(error: Error): ClassifiedUploadError {
  const detail = error as unknown as TusDetailedErrorLike;
  const status = detail.originalResponse?.getStatus() ?? 0;
  const body = detail.originalResponse?.getBody() ?? '';
  const technicalDetail = `HTTP ${status} — ${body || error.message}`;
  const serverMessage = extractServerMessage(body);

  if (status === 0 || !detail.originalResponse) {
    return {
      userMessage: 'Network connection lost. Check your internet and try again.',
      technicalDetail,
      isRetryable: true,
    };
  }

  if (status === 413) {
    return {
      userMessage: serverMessage ?? 'File exceeds the maximum upload size.',
      technicalDetail,
      isRetryable: false,
    };
  }

  if (status === 410) {
    return {
      userMessage:
        serverMessage ?? 'Upload session expired. Please start the upload again.',
      technicalDetail,
      isRetryable: true,
    };
  }

  if (status === 403) {
    return {
      userMessage:
        serverMessage ?? 'Upload not permitted. The server rejected this request.',
      technicalDetail,
      isRetryable: false,
    };
  }

  if (status === 415) {
    return {
      userMessage: serverMessage ?? 'File type not supported by the server.',
      technicalDetail,
      isRetryable: false,
    };
  }

  // 4xx other than the handled ones — prefer the server's own message
  // (this is where the "Invalid file extension … Allowed: …" string lands
  // when the streaming validator rejects an unknown extension).
  if (status >= 400 && status < 500) {
    return {
      userMessage: serverMessage ?? 'Upload rejected by the server.',
      technicalDetail,
      isRetryable: false,
    };
  }

  // Cloudflare-specific 5xx (520-524) before general 5xx
  if (status >= 520 && status <= 524) {
    return {
      userMessage: 'Server connection issue. Please try again.',
      technicalDetail,
      isRetryable: true,
    };
  }

  if (status >= 500 && status < 600) {
    return {
      userMessage: 'Server error occurred. Please try again in a moment.',
      technicalDetail,
      isRetryable: true,
    };
  }

  // Fallback for any unclassified status
  return {
    userMessage: serverMessage ?? 'Upload failed. Please try again.',
    technicalDetail,
    isRetryable: true,
  };
}
