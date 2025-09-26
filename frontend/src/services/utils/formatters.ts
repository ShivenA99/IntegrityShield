export function formatDuration(ms?: number | null): string {
  if (!ms && ms !== 0) return "—";
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds.toFixed(0)}s`;
}

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}
