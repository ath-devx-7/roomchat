import { useCallback, useEffect, useRef } from "react";

/**
 * Application close codes. These MUST stay in sync with rooms/consumers.py
 * (CLOSE_ROOM_FULL / CLOSE_NOT_AUTHENTICATED / CLOSE_ROOM_NOT_FOUND / CLOSE_BANNED).
 *
 * ChatConsumer.reject() accepts the handshake *before* closing with one of these,
 * specifically so the browser reports the real code instead of the 1006 it gives for
 * a refused handshake. A code in this table means "do not reconnect" — retrying a
 * full, missing or banned room just loops forever.
 */
export const FATAL_CLOSE_CODES = {
  4001: "This room is full.",
  4003: "You must be signed in to join a room.",
  4004: "This room no longer exists.",
  4005: "You have been removed from this room.",
};

const RECONNECT_DELAY_MS = 3000;

/**
 * Opens a WebSocket to `path` and keeps it open.
 *
 * @param path      e.g. "/ws/notifications/" — null disables the socket entirely
 * @param onMessage called with each parsed frame
 * @param onFatal   called with (message, code) when the server closes with a fatal code
 * @returns send(payload) — serialises and sends, returns false if the socket isn't open
 */
export function useSocket(path, { onMessage, onFatal } = {}) {
  const socketRef = useRef(null);
  const timerRef = useRef(null);
  // Effects must not re-run (and so reopen the socket) just because a parent
  // re-rendered and handed us new callback identities.
  const handlers = useRef({ onMessage, onFatal });
  handlers.current = { onMessage, onFatal };

  useEffect(() => {
    if (!path) return undefined;

    // React 19 StrictMode mounts, unmounts and remounts every effect in development.
    // `cancelled` makes the discarded pass close its socket and abandon its retry
    // timer, so a component never ends up with two live sockets.
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
      const socket = new WebSocket(`${scheme}//${window.location.host}${path}`);
      socketRef.current = socket;

      socket.onmessage = (event) => {
        let data;
        try {
          data = JSON.parse(event.data);
        } catch {
          console.warn("[ws] dropped unparseable frame", event.data);
          return;
        }
        if (!cancelled) handlers.current.onMessage?.(data);
      };

      socket.onclose = (event) => {
        socketRef.current = null;
        if (cancelled) return;

        const fatal = FATAL_CLOSE_CODES[event.code];
        if (fatal) {
          handlers.current.onFatal?.(fatal, event.code);
          return; // deliberately no reconnect
        }
        timerRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
      };

      socket.onerror = () => {
        // onclose always follows, and that is where reconnect/fatal is decided.
        console.warn("[ws] socket error", path);
      };
    };

    connect();

    return () => {
      cancelled = true;
      clearTimeout(timerRef.current);
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
        socket.close();
      }
    };
  }, [path]);

  return useCallback((payload) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify(payload));
    return true;
  }, []);
}
