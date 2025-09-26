import axios from "axios";

const client = axios.create({
  baseURL: "/api/enhancement"
});

export async function fetchEnhancedPdfs(runId: string) {
  const response = await client.get(`/${runId}`);
  return response.data;
}

export async function downloadEnhancedPdf(runId: string, method: string) {
  const response = await client.get(`/${runId}/${method}`, { responseType: "blob" });
  return response.data as Blob;
}
