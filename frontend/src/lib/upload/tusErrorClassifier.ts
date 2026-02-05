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

/** Classify a TUS upload error into a user-friendly representation. */
export function classifyUploadError(error: Error): ClassifiedUploadError {
  const detail = error as unknown as TusDetailedErrorLike;
  const status = detail.originalResponse?.getStatus() ?? 0;
  const body = detail.originalResponse?.getBody() ?? '';
  const technicalDetail = `HTTP ${status} — ${body || error.message}`;

  if (status === 0 || !detail.originalResponse) {
    return {
      userMessage: 'Network connection lost. Check your internet and try again.',
      technicalDetail,
      isRetryable: true,
    };
  }

  if (status === 413) {
    return {
      userMessage: 'File exceeds the maximum upload size.',
      technicalDetail,
      isRetryable: false,
    };
  }

  if (status === 410) {
    return {
      userMessage: 'Upload session expired. Please start the upload again.',
      technicalDetail,
      isRetryable: true,
    };
  }

  if (status === 403) {
    return {
      userMessage: 'Upload not permitted. The server rejected this request.',
      technicalDetail,
      isRetryable: false,
    };
  }

  if (status === 415) {
    return {
      userMessage: 'File type not supported by the server.',
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
    userMessage: 'Upload failed. Please try again.',
    technicalDetail,
    isRetryable: true,
  };
}
