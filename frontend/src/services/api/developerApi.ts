import axios from "axios";
import type { LogEntry, PerformanceMetricRecord } from "@services/types/developer";

const client = axios.create({
  baseURL: "/api/developer"
});

const isDev = typeof globalThis !== "undefined" && (globalThis as any).importMeta?.env?.DEV;
if (isDev) {
  client.interceptors.request.use((config) => {
    (config as any).metadata = { start: performance.now() };
    return config;
  });
  client.interceptors.response.use(
    (response) => {
      const meta = (response.config as any).metadata;
      const dur = meta ? Math.round(performance.now() - meta.start) : undefined;
      // eslint-disable-next-line no-console
      console.debug(`[API] ${response.config.method?.toUpperCase()} ${response.config.url} ${response.status} ${dur}ms`);
      return response;
    },
    (error) => {
      const cfg = error.config || {};
      const meta = (cfg as any).metadata;
      const dur = meta ? Math.round(performance.now() - meta.start) : undefined;
      // eslint-disable-next-line no-console
      console.debug(`[API] ${cfg.method?.toUpperCase()} ${cfg.url} ERROR ${dur}ms`, { message: error?.message });
      return Promise.reject(error);
    }
  );
}

export async function fetchLogs(runId: string) {
  const response = await client.get<{ run_id: string; logs: LogEntry[] }>(`/${runId}/logs`);
  return response.data;
}

export async function fetchMetrics(runId: string) {
  const response = await client.get<{ run_id: string; metrics: PerformanceMetricRecord[] }>(`/${runId}/metrics`);
  return response.data;
}

export async function fetchStructuredData(runId: string) {
  const response = await client.get<{ run_id: string; data: Record<string, unknown> }>(`/${runId}/structured-data`);
  return response.data;
}

export async function fetchSystemHealth() {
  const response = await client.get(`/system/health`);
  return response.data as Record<string, unknown>;
}
