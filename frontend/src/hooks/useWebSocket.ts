/**
 * WebSocket hook -- connects to the AgentTown server and dispatches
 * incoming messages to the Zustand game store.
 *
 * Features:
 * - Auto-reconnect with exponential backoff (1s -> 2s -> 4s ... max 30s)
 * - Clean disconnect on unmount
 * - Exposes connect / disconnect / sendMessage for imperative control
 * - Uses the Vite dev-server proxy (/ws) so it works in both dev and prod
 */

import { useCallback, useEffect, useRef } from 'react';
import { useGameStore } from '@/stores/gameStore';
import type { ServerMessage } from '@/types/game';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Base delay for reconnect backoff (ms). */
const BASE_RECONNECT_DELAY = 1000;

/** Maximum reconnect delay (ms). */
const MAX_RECONNECT_DELAY = 30_000;

/** How long to wait for WebSocket open before considering it failed (ms). */
const CONNECT_TIMEOUT = 10_000;

// ---------------------------------------------------------------------------
// Build the WebSocket URL
// ---------------------------------------------------------------------------

function getWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}/ws`;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface UseWebSocketReturn {
  /** Initiate a WebSocket connection. Safe to call if already connected. */
  connect: () => void;
  /** Close the WebSocket. Stops auto-reconnect. */
  disconnect: () => void;
  /** Send a JSON message to the server. No-op if not connected. */
  sendMessage: (data: Record<string, unknown>) => void;
}

export function useWebSocket(): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);
  // When true, we should NOT auto-reconnect (user called disconnect).
  const intentionalCloseRef = useRef(false);
  const connectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const setConnectionStatus = useGameStore((s) => s.setConnectionStatus);
  const updateFromMessage = useGameStore((s) => s.updateFromMessage);

  // -- helpers --------------------------------------------------------------

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (connectTimeoutRef.current !== null) {
      clearTimeout(connectTimeoutRef.current);
      connectTimeoutRef.current = null;
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (intentionalCloseRef.current) return;

    const delay = Math.min(
      BASE_RECONNECT_DELAY * Math.pow(2, attemptRef.current),
      MAX_RECONNECT_DELAY,
    );
    attemptRef.current += 1;

    reconnectTimerRef.current = setTimeout(() => {
      reconnectTimerRef.current = null;
      // eslint-disable-next-line @typescript-eslint/no-use-before-define
      connect();
    }, delay);
  }, []); // connect is stable via ref pattern below

  // -- connect --------------------------------------------------------------

  const connect = useCallback(() => {
    // If we already have an open or connecting socket, do nothing.
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    clearTimers();
    intentionalCloseRef.current = false;
    setConnectionStatus('connecting');

    const url = getWsUrl();
    const ws = new WebSocket(url);
    wsRef.current = ws;

    // Timeout: if the socket does not open within CONNECT_TIMEOUT, close it
    // so the onclose handler can schedule a reconnect.
    connectTimeoutRef.current = setTimeout(() => {
      connectTimeoutRef.current = null;
      if (ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    }, CONNECT_TIMEOUT);

    ws.onopen = () => {
      if (connectTimeoutRef.current !== null) {
        clearTimeout(connectTimeoutRef.current);
        connectTimeoutRef.current = null;
      }
      attemptRef.current = 0; // reset backoff on successful connect
      setConnectionStatus('connected');
    };

    ws.onmessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data) as ServerMessage;
        updateFromMessage(msg);
      } catch {
        // Ignore unparseable messages
        console.warn('[WS] Failed to parse message:', event.data);
      }
    };

    ws.onerror = () => {
      // The browser fires onerror right before onclose, so we let onclose
      // handle reconnection logic. Just update status here.
      setConnectionStatus('error');
    };

    ws.onclose = () => {
      wsRef.current = null;
      if (connectTimeoutRef.current !== null) {
        clearTimeout(connectTimeoutRef.current);
        connectTimeoutRef.current = null;
      }

      if (!intentionalCloseRef.current) {
        setConnectionStatus('disconnected');
        scheduleReconnect();
      } else {
        setConnectionStatus('disconnected');
      }
    };
  }, [clearTimers, scheduleReconnect, setConnectionStatus, updateFromMessage]);

  // -- disconnect -----------------------------------------------------------

  const disconnect = useCallback(() => {
    intentionalCloseRef.current = true;
    clearTimers();
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnectionStatus('disconnected');
  }, [clearTimers, setConnectionStatus]);

  // -- sendMessage ----------------------------------------------------------

  const sendMessage = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  // -- auto-connect on mount, clean up on unmount ---------------------------

  useEffect(() => {
    connect();
    return () => {
      // On unmount, disconnect cleanly (no auto-reconnect)
      intentionalCloseRef.current = true;
      clearTimers();
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
    // Only run on mount/unmount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { connect, disconnect, sendMessage };
}
