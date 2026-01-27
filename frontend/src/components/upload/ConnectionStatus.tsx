import { Loader2, WifiOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { ConnectionState } from '@/hooks/useTaskProgress';

interface ConnectionStatusProps {
  connectionState: ConnectionState;
  onReconnect: () => void;
}

/**
 * Connection status indicator showing WebSocket state
 *
 * Per CONTEXT.md:
 * - Subtle "Reconnecting..." indicator during connection loss, auto-reconnect in background
 * - After 5 failed attempts (~30 seconds), escalate to visible warning
 * - Show manual "Reconnect" button after max attempts
 */
export function ConnectionStatus({
  connectionState,
  onReconnect,
}: ConnectionStatusProps) {
  const { isConnected, isReconnecting, maxAttemptsReached, reconnectAttempt } =
    connectionState;

  // Don't show anything when connected
  if (isConnected) {
    return null;
  }

  // Subtle indicator during reconnection attempts (first 5 attempts)
  if (isReconnecting && !maxAttemptsReached) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground text-sm py-2">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span>Reconnecting... (attempt {reconnectAttempt}/{5})</span>
      </div>
    );
  }

  // Escalated warning after max attempts reached
  if (maxAttemptsReached) {
    return (
      <div className="flex items-center gap-2 bg-amber-100 text-amber-800 px-3 py-2 rounded-md">
        <WifiOff className="h-4 w-4 shrink-0" />
        <span className="flex-1">Connection lost. Progress updates may be missed.</span>
        <Button
          variant="outline"
          size="sm"
          onClick={onReconnect}
          className="shrink-0"
        >
          Reconnect
        </Button>
      </div>
    );
  }

  // Not connected but not yet trying to reconnect (initial connection)
  return null;
}
