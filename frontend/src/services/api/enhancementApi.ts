import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

const client = axios.create({
  baseURL: `${API_BASE_URL}/enhancement`
});

export async function fetchEnhancedPdfs(runId: string) {
  const response = await client.get(`/${runId}`);
  return response.data;
}

export async function downloadEnhancedPdf(runId: string, method: string) {
  const response = await client.get(`/${runId}/${method}`, { responseType: "blob" });
  return response.data as Blob;
}
