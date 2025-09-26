import { useEffect, useRef, useState } from "react";

export function useWebSocket(urlFactory: () => WebSocket | null) {
  const [data, setData] = useState<unknown>(null);
  const [isConnected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const socket = urlFactory();
    if (!socket) return;
    socketRef.current = socket;

    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onerror = () => setConnected(false);
    socket.onmessage = (event) => {
      try {
        setData(JSON.parse(event.data));
      } catch (error) {
        console.error("Failed to parse websocket payload", error);
      }
    };

    return () => {
      socket.close();
    };
  }, [urlFactory]);

  return { socket: socketRef.current, data, isConnected };
}
