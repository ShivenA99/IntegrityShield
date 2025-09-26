import axios from "axios";
import type { LogEntry, PerformanceMetricRecord } from "@services/types/developer";

const client = axios.create({
  baseURL: "/api/developer"
});

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
