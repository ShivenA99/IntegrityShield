export function createLogStream(runId: string): WebSocket {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const base = `${protocol}://${window.location.host}`;
  return new WebSocket(`${base}/api/developer/logs/${runId}/stream`);
}
