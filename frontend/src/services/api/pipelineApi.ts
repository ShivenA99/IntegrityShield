import axios from "axios";
import type { PipelineConfigPayload, PipelineRunSummary } from "@services/types/pipeline";

const client = axios.create({
  baseURL: "/api/pipeline"
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

export async function startPipeline(formData: FormData) {
  const response = await client.post("/start", formData, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return response.data as { run_id: string };
}

export async function getPipelineStatus(runId: string) {
  const response = await client.get<PipelineRunSummary>(`/${runId}/status`);
  return response.data;
}

export async function resumePipeline(runId: string, stage: string) {
  const response = await client.post(`/${runId}/resume/${stage}`);
  return response.data;
}

export async function deletePipelineRun(runId: string) {
  await client.delete(`/${runId}`);
}

export async function listRuns(params: { q?: string; status?: string[]; includeDeleted?: boolean; sortBy?: string; sortDir?: "asc" | "desc"; limit?: number; offset?: number }) {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.status && params.status.length) search.set("status", params.status.join(","));
  if (params.includeDeleted) search.set("include_deleted", String(params.includeDeleted));
  if (params.sortBy) search.set("sort_by", params.sortBy);
  if (params.sortDir) search.set("sort_dir", params.sortDir);
  if (typeof params.limit === "number") search.set("limit", String(params.limit));
  if (typeof params.offset === "number") search.set("offset", String(params.offset));
  const response = await client.get(`/runs?${search.toString()}`);
  return response.data as { runs: any[]; count: number; offset: number; limit: number };
}

export async function softDeleteRun(runId: string) {
  const response = await client.post(`/${runId}/soft_delete`);
  return response.data as { run_id: string; deleted: boolean };
}

export async function forkRun(payload: { source_run_id: string; target_stages?: string[] }) {
  const response = await client.post(`/fork`, payload);
  return response.data as { run_id: string; forked_from: string; status: string };
}

export async function rerunRun(payload: { source_run_id: string; target_stages?: string[] }) {
  const response = await client.post(`/rerun`, payload);
  return response.data as { run_id: string; rerun_from: string; status: string; mode: string };
}
