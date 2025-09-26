import axios from "axios";
import type { QuestionListResponse } from "@services/types/questions";

const client = axios.create({
  baseURL: "/api/questions"
});

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
  payload: { substring_mappings: any[]; model?: string }
) {
  const response = await client.post(`/${runId}/${questionId}/validate`, payload);
  return response.data;
}

export async function fetchQuestionHistory(runId: string, questionId: number) {
  const response = await client.get(`/${runId}/${questionId}/history`);
  return response.data;
}
