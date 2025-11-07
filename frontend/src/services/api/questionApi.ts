import axios from "axios";
import type { QuestionListResponse } from "@services/types/questions";

const client = axios.create({
  baseURL: "/api/questions"
});

// Lightweight debug interceptor (dev only)
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
      console.debug(`[API] ${response.config.method?.toUpperCase()} ${response.config.url} ${response.status} ${dur}ms`,
        { data: response.data && JSON.stringify(response.data).slice(0, 500) });
      return response;
    },
    (error) => {
      const cfg = error.config || {};
      const meta = (cfg as any).metadata;
      const dur = meta ? Math.round(performance.now() - meta.start) : undefined;
      // eslint-disable-next-line no-console
      console.debug(`[API] ${cfg.method?.toUpperCase()} ${cfg.url} ERROR ${dur}ms`,
        { message: error?.response?.data || error.message });
      return Promise.reject(error);
    }
  );
}

export async function fetchQuestions(runId: string) {
  const response = await client.get<QuestionListResponse>(`/${runId}`);
  return response.data;
}

export async function updateQuestionManipulation(
  runId: string,
  questionId: number,
  payload: Record<string, unknown>
) {
  const response = await client.put(`/${runId}/${questionId}/manipulation`, payload);
  return response.data;
}

export async function testQuestion(runId: string, questionId: number, payload: Record<string, unknown>) {
  const response = await client.post(`/${runId}/${questionId}/test`, payload);
  return response.data;
}

export async function validateQuestion(
  runId: string,
  questionId: number,
  payload: { substring_mappings: any[]; model?: string; mapping_id?: string }
) {
  const response = await client.post(`/${runId}/${questionId}/validate`, payload);
  return response.data;
}

export async function autoGenerateMappings(
  runId: string,
  questionId: number,
  payload: { model?: string; force?: boolean } = {}
) {
  const response = await client.post(`/${runId}/${questionId}/auto_generate`, payload);
  return response.data;
}

export async function fetchQuestionHistory(runId: string, questionId: number) {
  const response = await client.get(`/${runId}/${questionId}/history`);
  return response.data;
}

export async function generateMappingsForAll(
  runId: string,
  payload: { k?: number; strategy?: string } = {}
) {
  const response = await client.post(`/${runId}/generate-mappings`, payload);
  return response.data;
}

export async function generateMappingsForQuestion(
  runId: string,
  questionId: number,
  payload: { k?: number; strategy?: string } = {}
) {
  const response = await client.post(`/${runId}/${questionId}/generate-mappings`, payload);
  return response.data;
}

export async function getGenerationStatus(runId: string) {
  const response = await client.get(`/${runId}/generation-status`);
  return response.data;
}

export async function getGenerationLogs(runId: string) {
  const response = await client.get(`/${runId}/generation-logs`);
  return response.data;
}