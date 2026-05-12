import axios from "axios";
import type { AxiosError, InternalAxiosRequestConfig } from "axios";
import { useSessionStore } from "../store/sessionStore";

declare module "axios" {
  interface InternalAxiosRequestConfig {
    _retryCount?: number;
  }
}

const BASE_URL =
  (import.meta.env.VITE_API_URL as string | undefined) ??
  (import.meta.env.VITE_API_BASE as string | undefined) ??
  "http://localhost:8000";

export const client = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
});

client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const sessionId = useSessionStore.getState().sessionId;
  if (sessionId) {
    config.headers.set("X-Session-Id", sessionId);
  }
  return config;
});

function dispatchToast(message: string): void {
  window.dispatchEvent(
    new CustomEvent("atlas:toast", { detail: { message } })
  );
}

const RETRY_DELAY_MS = 2_000;

client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const status = error.response?.status;
    const config = error.config;

    if (status === 401) {

      try {
        const [{ useSettingsStore }, { useUiStore }] = await Promise.all([
          import("../store/settingsStore"),
          import("../store/uiStore"),
        ]);
        useSettingsStore.getState().clearApiKeys();
        useUiStore.getState().setSettingsPanelOpen(true);
      } catch {

      }
      return Promise.reject(error);
    }

    if (status === 422) {
      console.error("[API] Validation error:", error.response?.data);
      return Promise.reject(error);
    }

    if (status !== undefined && status >= 500) {
      const retries = config?._retryCount ?? 0;
      if (retries < 1 && config) {
        config._retryCount = retries + 1;
        dispatchToast("Server error — retrying…");
        await new Promise<void>((r) => setTimeout(r, RETRY_DELAY_MS));
        return client.request(config);
      }
      dispatchToast("Server error — please try again.");
      return Promise.reject(error);
    }

    if (!error.response) {
      dispatchToast("Cannot reach backend — is it running?");
      return Promise.reject(error);
    }

    return Promise.reject(error);
  }
);
