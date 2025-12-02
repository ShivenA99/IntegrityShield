export function extractErrorMessage(error: unknown): string {
  if (typeof error === "string") return error;
  if (error && typeof error === "object") {
    const maybeResponse = error as { response?: { data?: unknown; status?: number } };
    if (maybeResponse.response?.data) {
      const data = maybeResponse.response.data as { error?: string; message?: string };
      return data.error ?? data.message ?? JSON.stringify(data);
    }
    if ("message" in maybeResponse && typeof (maybeResponse as any).message === "string") {
      return (maybeResponse as any).message;
    }
  }
  return "Unexpected error";
}
