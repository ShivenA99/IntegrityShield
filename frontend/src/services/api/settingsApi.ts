import axios from "axios";
import type { SettingsPayload } from "@services/types/settings";

const client = axios.create({
  baseURL: "/api/settings"
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

export async function fetchSettings() {
  const response = await client.get<SettingsPayload>("/");
  return response.data;
}

export async function updateSettings(payload: SettingsPayload) {
  const response = await client.put<SettingsPayload>("/", payload);
  return response.data;
}
