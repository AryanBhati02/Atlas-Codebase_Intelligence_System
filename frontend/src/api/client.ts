/**
 * Configured Axios instance for all Atlas API calls.
 *
 * Features:
 *  - baseURL from VITE_API_URL env var
 *  - 30 s timeout
 *  - Request interceptor: attach X-Session-Id header
 *  - Response interceptors:
 *      401 → clear settings cache, open settings modal
 *      422 → log validation details
 *      5xx → toast + one automatic retry after 2 s
 *      network error → toast "Cannot reach backend"
 *
 * Circular-dep note:
 *  sessionStore does NOT import from api/, so we can import it statically.
 *  settingsStore and uiStore import from api.ts which imports from client.ts,
 *  so those are loaded via dynamic import() inside the response interceptor only.
 */

import axios from "axios";
import type { AxiosError, InternalAxiosRequestConfig } from "axios";
import { useSessionStore } from "../store/sessionStore";

// Augment Axios config to carry a typed retry counter
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

// ---------------------------------------------------------------------------
// Request interceptor — attach session id
// ---------------------------------------------------------------------------

client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const sessionId = useSessionStore.getState().sessionId;
  if (sessionId) {
    config.headers.set("X-Session-Id", sessionId);
  }
  return config;
});

// ---------------------------------------------------------------------------
// Response interceptors
// ---------------------------------------------------------------------------

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
      // Dynamic import breaks the settingsStore → api.ts → client.ts cycle
      try {
        const [{ useSettingsStore }, { useUiStore }] = await Promise.all([
          import("../store/settingsStore"),
          import("../store/uiStore"),
        ]);
        useSettingsStore.getState().clearApiKeys();
        useUiStore.getState().setSettingsPanelOpen(true);
      } catch {
        // Stores not yet available — ignore
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
