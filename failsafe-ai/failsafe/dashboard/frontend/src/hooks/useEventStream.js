import { useEffect, useRef, useState, useCallback } from 'react';

/**
 * Hook that connects to the FailSafe SSE endpoint and streams events.
 * Reconnects automatically on disconnect with exponential backoff.
 */
export default function useEventStream(url) {
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const sourceRef = useRef(null);
  const reconnectTimer = useRef(null);
  const backoff = useRef(1000);

  const connect = useCallback(() => {
    if (sourceRef.current) return;

    try {
      const es = new EventSource(url);
      sourceRef.current = es;

      es.onopen = () => {
        setConnected(true);
        backoff.current = 1000;
      };

      es.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          setEvents((prev) => {
            const next = [...prev, msg];
            return next.length > 500 ? next.slice(-500) : next;
          });
        } catch {
          // ignore malformed messages
        }
      };

      es.onerror = () => {
        es.close();
        sourceRef.current = null;
        setConnected(false);
        reconnectTimer.current = setTimeout(() => {
          backoff.current = Math.min(backoff.current * 1.5, 10000);
          connect();
        }, backoff.current);
      };
    } catch {
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
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
    };
  }, [connect]);

  const clearEvents = useCallback(() => setEvents([]), []);

  return { events, connected, clearEvents };
}
