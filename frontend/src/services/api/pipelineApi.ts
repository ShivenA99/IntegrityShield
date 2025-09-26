import axios from "axios";
import type { PipelineConfigPayload, PipelineRunSummary } from "@services/types/pipeline";

const client = axios.create({
  baseURL: "/api/pipeline"
});

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

export async function resumePipeline(runId: string, stageName: string, config?: Partial<PipelineConfigPayload>) {
  const response = await client.post(`/${runId}/resume/${stageName}`, config ?? {});
  return response.data;
}

export async function deletePipelineRun(runId: string) {
  await client.delete(`/${runId}`);
}
