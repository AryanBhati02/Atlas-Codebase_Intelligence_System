




import { client } from "./api";
import type { IngestResponse } from "../types";

export async function ingestGitHub(url: string): Promise<IngestResponse> {
  const response = await client.post<IngestResponse>("/ingest/github", { url });
  return response.data;
}

export async function ingestZip(file: File): Promise<IngestResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await client.post<IngestResponse>("/ingest/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}
