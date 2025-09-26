const KEY = "fairtestai.pipeline.recentRuns";

export function saveRecentRun(runId: string) {
  const entries = loadRecentRuns();
  const next = [runId, ...entries.filter((entry) => entry !== runId)].slice(0, 5);
  window.localStorage.setItem(KEY, JSON.stringify(next));
}

export function loadRecentRuns(): string[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as string[]) : [];
  } catch (error) {
    console.warn("Failed to load recent runs", error);
    return [];
  }
}
