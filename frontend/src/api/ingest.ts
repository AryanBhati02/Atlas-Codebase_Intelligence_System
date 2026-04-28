import { client } from "./client";
import type { IngestResponse } from "../types";

export async function ingestGitHub(url: string): Promise<IngestResponse> {
  const response = await client.post<IngestResponse>("/api/ingest/github", { url });
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
