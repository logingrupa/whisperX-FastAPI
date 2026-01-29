/**
 * Upload speed and ETA calculation with exponential moving average smoothing.
 *
 * Converts raw (bytesSent, bytesTotal) progress callbacks from tus-js-client
 * into human-readable speed and ETA values suitable for UI display.
 */

/** Metrics snapshot returned on each progress update. */
export interface UploadMetrics {
  percentage: number;
  speedBytesPerSecond: number;
  speedFormatted: string;
  etaSeconds: number;
  etaFormatted: string;
}

/** Format bytes-per-second as a human-readable speed string. */
export function formatSpeed(bytesPerSecond: number): string {
  if (bytesPerSecond <= 0) return '-- MB/s';
  const mbps = bytesPerSecond / (1024 * 1024);
  return mbps >= 100
    ? `${Math.round(mbps)} MB/s`
    : `${mbps.toFixed(1)} MB/s`;
}

/** Format seconds as a human-readable ETA string. */
export function formatEta(seconds: number): string {
  if (seconds <= 0 || !Number.isFinite(seconds)) return 'Calculating...';
  if (seconds < 60) return '< 1m';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

const INITIAL_METRICS: UploadMetrics = {
  percentage: 0,
  speedBytesPerSecond: 0,
  speedFormatted: '-- MB/s',
  etaSeconds: 0,
  etaFormatted: 'Calculating...',
};

/** Minimum interval (ms) between metric recalculations to avoid jitter. */
const MIN_UPDATE_INTERVAL_MS = 500;

/**
 * Tracks upload speed using exponential moving average (EMA) smoothing.
 *
 * Usage:
 * ```ts
 * const tracker = new UploadSpeedTracker();
 * // In onProgress callback:
 * const metrics = tracker.update(bytesSent, bytesTotal);
 * ```
 */
export class UploadSpeedTracker {
  private lastTimestamp = 0;
  private lastBytes = 0;
  private smoothedSpeed = 0;
  private lastMetrics: UploadMetrics = { ...INITIAL_METRICS };

  /** EMA smoothing factor -- higher = more weight to recent samples. */
  private readonly alpha = 0.3;

  /**
   * Update metrics with the latest progress values.
   *
   * Returns cached metrics if called more frequently than MIN_UPDATE_INTERVAL_MS
   * to prevent jittery display updates.
   */
  update(bytesSent: number, bytesTotal: number): UploadMetrics {
    const now = Date.now();
    const percentage = bytesTotal > 0
      ? Math.round((bytesSent / bytesTotal) * 100)
      : 0;

    // First data point -- need two points to calculate speed
    if (this.lastTimestamp === 0) {
      this.lastTimestamp = now;
      this.lastBytes = bytesSent;
      this.lastMetrics = { ...INITIAL_METRICS, percentage };
      return this.lastMetrics;
    }

    const elapsedMs = now - this.lastTimestamp;
    if (elapsedMs < MIN_UPDATE_INTERVAL_MS) {
      // Return cached metrics with updated percentage only
      this.lastMetrics = { ...this.lastMetrics, percentage };
      return this.lastMetrics;
    }

    const elapsedSec = elapsedMs / 1000;
    const bytesDelta = bytesSent - this.lastBytes;
    const instantSpeed = bytesDelta / elapsedSec;

    // EMA: weight recent sample by alpha, prior average by (1 - alpha)
    this.smoothedSpeed = this.smoothedSpeed === 0
      ? instantSpeed
      : this.alpha * instantSpeed + (1 - this.alpha) * this.smoothedSpeed;

    const remaining = bytesTotal - bytesSent;
    const etaSeconds = this.smoothedSpeed > 0 ? remaining / this.smoothedSpeed : 0;

    this.lastTimestamp = now;
    this.lastBytes = bytesSent;

    this.lastMetrics = {
      percentage,
      speedBytesPerSecond: this.smoothedSpeed,
      speedFormatted: formatSpeed(this.smoothedSpeed),
      etaSeconds,
      etaFormatted: formatEta(etaSeconds),
    };

    return this.lastMetrics;
  }

  /** Reset all state -- call between files. */
  reset(): void {
    this.lastTimestamp = 0;
    this.lastBytes = 0;
    this.smoothedSpeed = 0;
    this.lastMetrics = { ...INITIAL_METRICS };
  }
}
