/**
 * WebSocket message types matching backend app/schemas/websocket_schemas.py
 */

/** Progress stages matching backend ProgressStage enum */
export type ProgressStage =
  | 'uploading'
  | 'queued'
  | 'transcribing'
  | 'aligning'
  | 'diarizing'
  | 'complete';

/** Progress update from WebSocket */
export interface ProgressMessage {
  type: 'progress';
  task_id: string;
  stage: ProgressStage;
  percentage: number;
  message: string | null;
  timestamp: string;
}

/** Error message from WebSocket */
export interface ErrorMessage {
  type: 'error';
  task_id: string;
  error_code: string;
  user_message: string;
  technical_detail: string | null;
  timestamp: string;
}

/** Heartbeat message from WebSocket */
export interface HeartbeatMessage {
  type: 'heartbeat';
  timestamp: string;
}

/** Union of all WebSocket message types */
export type WebSocketMessage = ProgressMessage | ErrorMessage | HeartbeatMessage;
