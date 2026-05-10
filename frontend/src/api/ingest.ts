import { client } from "./client";
import type { IngestResponse } from "../types";

export async function ingestGitHub(url: string, signal?: AbortSignal): Promise<IngestResponse> {
  const response = await client.post<IngestResponse>(
    "/api/ingest/github",
    { url },
    {
      signal,
      timeout: 0,
    }
  );
  return response.data;
}

export async function ingestZip(file: File): Promise<IngestResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await client.post<IngestResponse>("/api/ingest/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function checkSession(sessionId: string): Promise<boolean> {
  try {
    await client.get(`/api/session/${sessionId}/status`);
    return true;
  } catch (err: unknown) {
    if (err && typeof err === "object" && "response" in err) {
      const axiosErr = err as { response?: { status?: number } };
      const status = axiosErr.response?.status;
      if (status === 404 || status === 410) return false;
    }
    return false;
  }
}
