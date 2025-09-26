import { useCallback, useEffect, useState } from "react";

import { fetchLogs, fetchMetrics } from "@services/api/developerApi";
import { createLogStream } from "@services/api/websocketService";
import type { LogEntry, PerformanceMetricRecord } from "@services/types/developer";

interface DeveloperState {
  logs: LogEntry[];
  metrics: PerformanceMetricRecord[];
  isStreaming: boolean;
}

export function useDeveloperTools(runId: string | null) {
  const [state, setState] = useState<DeveloperState>({ logs: [], metrics: [], isStreaming: false });

  useEffect(() => {
    if (!runId) return;

    let socket: WebSocket | null = null;
    let cancelled = false;

    async function bootstrap() {
      try {
        const [logsResponse, metricsResponse] = await Promise.all([
          fetchLogs(runId),
          fetchMetrics(runId),
        ]);
        if (cancelled) return;
        setState((current) => ({
          ...current,
          logs: logsResponse.logs,
          metrics: metricsResponse.metrics,
        }));
      } catch (error) {
        console.warn("Failed to load developer data", error);
      }

      socket = createLogStream(runId);
      socket.onopen = () => setState((current) => ({ ...current, isStreaming: true }));
      socket.onclose = () => setState((current) => ({ ...current, isStreaming: false }));
      socket.onerror = () => setState((current) => ({ ...current, isStreaming: false }));
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as LogEntry;
          setState((current) => ({ ...current, logs: [payload, ...current.logs].slice(0, 200) }));
        } catch (err) {
          console.error("Failed to parse log stream payload", err);
        }
      };
    }

    bootstrap();

    return () => {
      cancelled = true;
      socket?.close();
    };
  }, [runId]);

  const refreshMetrics = useCallback(async () => {
    if (!runId) return;
    try {
      const metricsResponse = await fetchMetrics(runId);
      setState((current) => ({ ...current, metrics: metricsResponse.metrics }));
    } catch (error) {
      console.warn("Failed to refresh metrics", error);
    }
  }, [runId]);

  return { ...state, refreshMetrics };
}
