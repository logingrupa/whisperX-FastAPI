import { useCallback, useEffect, useRef, useState } from 'react';
import useWebSocket, { ReadyState } from 'react-use-websocket';
import type { ProgressStage, WebSocketMessage, ProgressMessage, ErrorMessage } from '@/types/websocket';

/** Maximum reconnection attempts before giving up */
const MAX_RECONNECT_ATTEMPTS = 5;

/** Connection state for UI display */
export interface ConnectionState {
  isConnected: boolean;
  isConnecting: boolean;
  isReconnecting: boolean;
  reconnectAttempt: number;
  maxAttemptsReached: boolean;
}

/** Progress state from WebSocket */
export interface TaskProgressState {
  percentage: number;
  stage: ProgressStage;
  message: string | null;
}

/** Error state from WebSocket */
export interface TaskErrorState {
  errorCode: string;
  userMessage: string;
  technicalDetail: string | null;
}

interface UseTaskProgressOptions {
  /** Task ID to subscribe to */
  taskId: string | null;
  /** Called on progress update */
  onProgress?: (taskId: string, progress: TaskProgressState) => void;
  /** Called on error */
  onError?: (taskId: string, error: TaskErrorState) => void;
  /** Called when task completes */
  onComplete?: (taskId: string) => void;
}

/**
 * Hook for tracking task progress via WebSocket
 *
 * Features:
 * - Connects to /ws/tasks/{taskId} when taskId is provided
 * - Reconnects with exponential backoff (up to 5 attempts)
 * - Fetches current state on reconnect via polling endpoint
 * - Filters heartbeat messages
 * - Provides connection state for UI display
 */
export function useTaskProgress({
  taskId,
  onProgress,
  onError,
  onComplete,
}: UseTaskProgressOptions) {
  const [connectionState, setConnectionState] = useState<ConnectionState>({
    isConnected: false,
    isConnecting: false,
    isReconnecting: false,
    reconnectAttempt: 0,
    maxAttemptsReached: false,
  });

  // Track if we were previously connected (for reconnection detection)
  const wasConnectedRef = useRef(false);
  const reconnectAttemptRef = useRef(0);

  // Build WebSocket URL - null disables connection
  const socketUrl = taskId ? `/ws/tasks/${taskId}` : null;

  // Use refs for callbacks to avoid stale closure issues
  const onProgressRef = useRef(onProgress);
  const onErrorRef = useRef(onError);
  const onCompleteRef = useRef(onComplete);

  useEffect(() => {
    onProgressRef.current = onProgress;
    onErrorRef.current = onError;
    onCompleteRef.current = onComplete;
  }, [onProgress, onError, onComplete]);

  /**
   * Fetch current progress state from polling endpoint
   * Used to sync state on reconnect (get missed updates)
   */
  const syncProgressFromPolling = useCallback(async (taskIdToSync: string) => {
    try {
      const response = await fetch(`/tasks/${taskIdToSync}/progress`);
      if (response.ok) {
        const data = await response.json();
        if (data.stage && data.percentage !== undefined) {
          onProgressRef.current?.(taskIdToSync, {
            percentage: data.percentage,
            stage: data.stage,
            message: data.message || null,
          });
          if (data.stage === 'complete') {
            onCompleteRef.current?.(taskIdToSync);
          }
        }
      }
    } catch (error) {
      console.error('Failed to sync progress from polling endpoint:', error);
    }
  }, []);

  const { readyState, getWebSocket } = useWebSocket(
    socketUrl,
    {
      shouldReconnect: (closeEvent) => {
        // Don't reconnect on normal closure (code 1000) or if task is complete
        if (closeEvent.code === 1000) return false;
        // Don't reconnect if max attempts reached
        if (reconnectAttemptRef.current >= MAX_RECONNECT_ATTEMPTS) return false;
        reconnectAttemptRef.current += 1;
        return true;
      },
      reconnectAttempts: MAX_RECONNECT_ATTEMPTS,
      reconnectInterval: (attemptNumber) => {
        // Exponential backoff: 1s, 2s, 4s, 8s, 16s (capped at 30s)
        return Math.min(1000 * Math.pow(2, attemptNumber), 30000);
      },
      onOpen: () => {
        wasConnectedRef.current = true;
        reconnectAttemptRef.current = 0;

        // Always sync progress on connect (initial or reconnect)
        // Backend may have emitted updates before WebSocket connected
        if (taskId) {
          syncProgressFromPolling(taskId);
        }
      },
      onClose: () => {
        // Will trigger reconnection logic via shouldReconnect
      },
      onMessage: (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);

          // Filter out heartbeat messages - just ignore them
          if (message.type === 'heartbeat') {
            return;
          }

          if (message.type === 'progress') {
            const progressMessage = message as ProgressMessage;
            onProgressRef.current?.(progressMessage.task_id, {
              percentage: progressMessage.percentage,
              stage: progressMessage.stage,
              message: progressMessage.message,
            });

            if (progressMessage.stage === 'complete') {
              onCompleteRef.current?.(progressMessage.task_id);
            }
          } else if (message.type === 'error') {
            const errorMessage = message as ErrorMessage;
            onErrorRef.current?.(errorMessage.task_id, {
              errorCode: errorMessage.error_code,
              userMessage: errorMessage.user_message,
              technicalDetail: errorMessage.technical_detail,
            });
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      },
    },
    // Only connect when taskId is provided
    taskId !== null
  );

  // Update connection state based on readyState
  useEffect(() => {
    const isConnected = readyState === ReadyState.OPEN;
    const isConnecting = readyState === ReadyState.CONNECTING;
    const isReconnecting = isConnecting && wasConnectedRef.current;
    const maxAttemptsReached = reconnectAttemptRef.current >= MAX_RECONNECT_ATTEMPTS;

    setConnectionState({
      isConnected,
      isConnecting,
      isReconnecting,
      reconnectAttempt: reconnectAttemptRef.current,
      maxAttemptsReached,
    });
  }, [readyState]);

  /**
   * Manually trigger reconnection (after max attempts)
   */
  const reconnect = useCallback(() => {
    reconnectAttemptRef.current = 0;
    wasConnectedRef.current = false;
    const ws = getWebSocket();
    if (ws) {
      ws.close();
    }
    // WebSocket will auto-reconnect since we reset the counter
  }, [getWebSocket]);

  return {
    connectionState,
    reconnect,
  };
}
