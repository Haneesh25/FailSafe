import { useEffect, useRef, useState, useCallback } from 'react';

/**
 * Hook that connects to the FailSafe WebSocket endpoint and streams events.
 * Reconnects automatically on disconnect with exponential backoff.
 */
export default function useWebSocket(url) {
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const backoff = useRef(1000);

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        backoff.current = 1000;
      };

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          setEvents((prev) => {
            const next = [...prev, msg];
            // Keep at most 500 events in memory
            return next.length > 500 ? next.slice(-500) : next;
          });
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        // reconnect with backoff
        reconnectTimer.current = setTimeout(() => {
          backoff.current = Math.min(backoff.current * 1.5, 10000);
          connect();
        }, backoff.current);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      // if construction fails, retry after backoff
      reconnectTimer.current = setTimeout(() => {
        backoff.current = Math.min(backoff.current * 1.5, 10000);
        connect();
      }, backoff.current);
    }
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  const clearEvents = useCallback(() => setEvents([]), []);

  return { events, connected, clearEvents };
}
