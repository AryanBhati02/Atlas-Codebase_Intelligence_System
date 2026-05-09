
export { client } from "./client";

import { client } from "./client";
import type {
  AnalyzeResponse,
  GraphData,
  FileContentResponse,
  AIExplainResponse,
  AIAnalyzeCodeResponse,
  BeginnerGuideResponse,
  QAResponse,
  SettingsResponse,
  AIStatusResponse,
  KeyUpdateResponse,
  TestProviderResponse,
  ClearCacheResponse,
  DeadCodeResponse,
  FunctionGraphResponse,
  ReadmeResponse,
  RefactorResponse,
  SecurityScanResponse,
  PRReviewResponse,
  TimelineResponse,
  CommitDiffResponse,
  CoverageResponse,
  Comment,
  CommentCountsResponse,
  ShareTokenResponse,
} from "../types";

export async function analyzeSession(
  sessionId: string
): Promise<AnalyzeResponse> {
  const res = await client.post<AnalyzeResponse>(`/api/analyze/${sessionId}`);
  return res.data;
}

export interface CancellableAnalysis {
  promise: Promise<AnalyzeResponse>;
  abort: () => void;
}

export function analyzeWithProgress(
  sessionId: string,
  onProgress: (stage: string, current: number, total: number) => void
): CancellableAnalysis {
  let aborted = false;

  const ANALYSIS_TIMEOUT_MS = 120_000;

  const promise = new Promise<AnalyzeResponse>((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      if (!aborted) {
        aborted = true;
        reject(new Error("Clone timed out — try again."));
      }
    }, ANALYSIS_TIMEOUT_MS);

    void (async () => {
      try {
        await client.post(`/api/analyze/start/${sessionId}`);

        if (aborted) {
          clearTimeout(timeoutId);
          reject(new Error("Aborted"));
          return;
        }

        let consecutiveErrors = 0;
        const MAX_CONSECUTIVE_ERRORS = 3;

        while (!aborted) {
          await new Promise<void>((r) => setTimeout(r, 500));
          if (aborted) break;

          try {
            const { data: prog } = await client.get<{
              stage: string;
              current: number;
              total: number;
              done: boolean;
              error: string | null;
            }>(`/api/analyze/progress/${sessionId}`);

            consecutiveErrors = 0;
            onProgress(prog.stage, prog.current, prog.total);

            if (prog.error) {
              clearTimeout(timeoutId);
              reject(new Error(prog.error));
              return;
            }

            if (prog.done) {
              clearTimeout(timeoutId);
              const res = await client.post<AnalyzeResponse>(
                `/api/analyze/${sessionId}`
              );
              resolve(res.data);
              return;
            }
          } catch (pollErr: unknown) {
            consecutiveErrors++;
            if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
              clearTimeout(timeoutId);
              reject(new Error("Lost connection to analysis server."));
              return;
            }
            await new Promise<void>((r) => setTimeout(r, 1_000));
          }
        }

        if (aborted) {
          clearTimeout(timeoutId);
          reject(new Error("Aborted"));
        }
      } catch (err: unknown) {
        clearTimeout(timeoutId);
        reject(err);
      }
    })();
  });

  return { promise, abort: () => { aborted = true; } };
}


export async function getGraph(sessionId: string): Promise<GraphData> {
  const res = await client.get<GraphData>(`/api/analyze/graph/${sessionId}`);
  return res.data;
}

export interface CancellableFileContent {
  promise: Promise<FileContentResponse>;
  cancel: () => void;
}

export function getFileContentCancellable(
  sessionId: string,
  path: string
): CancellableFileContent {
  const controller = new AbortController();
  const promise = client
    .get<FileContentResponse>(`/api/files/content/${sessionId}`, {
      params: { path },
      signal: controller.signal,
    })
    .then((r) => r.data);
  return { promise, cancel: () => controller.abort() };
}

export async function getFileContent(
  sessionId: string,
  path: string
): Promise<FileContentResponse> {
  const res = await client.get<FileContentResponse>(
    `/api/files/content/${sessionId}`,
    { params: { path } }
  );
  return res.data;
}

export interface CancellableRequest<T> {
  promise: Promise<T>;
  cancel: () => void;
}

function cancellable<T>(
  requestFn: (signal: AbortSignal) => Promise<T>
): CancellableRequest<T> {
  const controller = new AbortController();
  return {
    promise: requestFn(controller.signal),
    cancel: () => controller.abort(),
  };
}

export function explainFileCancellable(
  sessionId: string,
  filePath: string
): CancellableRequest<AIExplainResponse> {
  return cancellable((signal) =>
    client
      .post<AIExplainResponse>(
        "/api/ai/explain",
        { session_id: sessionId, file_path: filePath },
        { signal }
      )
      .then((r) => r.data)
  );
}

export async function explainFile(
  sessionId: string,
  filePath: string
): Promise<AIExplainResponse> {
  const res = await client.post<AIExplainResponse>("/api/ai/explain", {
    session_id: sessionId,
    file_path: filePath,
  });
  return res.data;
}

export async function analyzeCode(
  sessionId: string,
  filePath: string,
  code: string,
  startLine: number = 0,
  endLine: number = 0
): Promise<AIAnalyzeCodeResponse> {
  const res = await client.post<AIAnalyzeCodeResponse>("/api/ai/analyze-code", {
    session_id: sessionId,
    file_path: filePath,
    code,
    start_line: startLine,
    end_line: endLine,
  });
  return res.data;
}

export async function getBeginnerGuide(
  sessionId: string
): Promise<BeginnerGuideResponse> {
  const res = await client.post<BeginnerGuideResponse>("/api/ai/beginner-guide", {
    session_id: sessionId,
  });
  return res.data;
}

export function askQuestionCancellable(
  sessionId: string,
  question: string
): CancellableRequest<QAResponse> {
  return cancellable((signal) =>
    client
      .post<QAResponse>("/api/ai/qa", { session_id: sessionId, question }, { signal })
      .then((r) => r.data)
  );
}

export async function askQuestion(
  sessionId: string,
  question: string
): Promise<QAResponse> {
  const res = await client.post<QAResponse>("/api/ai/qa", {
    session_id: sessionId,
    question,
  });
  return res.data;
}

export async function getSettings(): Promise<SettingsResponse> {
  const res = await client.get<SettingsResponse>("/api/settings");
  return res.data;
}

export async function getAIStatus(): Promise<AIStatusResponse> {
  const res = await client.get<AIStatusResponse>("/api/settings/status");
  return res.data;
}

export async function updateProviderKey(
  provider: string,
  key: string
): Promise<KeyUpdateResponse> {
  const res = await client.post<KeyUpdateResponse>("/api/settings/keys", {
    provider,
    key,
  });
  return res.data;
}

export async function testProvider(
  provider: string
): Promise<TestProviderResponse> {
  const res = await client.post<TestProviderResponse>("/api/settings/test", {
    provider,
  });
  return res.data;
}

export async function setPreferLocal(
  preferLocal: boolean
): Promise<{ prefer_local: boolean; active_provider: string }> {
  const res = await client.post<{ prefer_local: boolean; active_provider: string }>(
    "/api/settings/prefer",
    { prefer_local: preferLocal }
  );
  return res.data;
}

export async function clearAICache(
  sessionId?: string
): Promise<ClearCacheResponse> {
  const res = await client.post<ClearCacheResponse>("/api/settings/clear-cache", {
    session_id: sessionId ?? null,
  });
  return res.data;
}

export async function getOllamaModels(): Promise<{
  models: { name: string; size: string; modified_at: string }[];
  reachable: boolean;
}> {
  const res = await client.get<{
    models: { name: string; size: string; modified_at: string }[];
    reachable: boolean;
  }>("/api/settings/ollama-models");
  return res.data;
}

export async function selectModel(
  model: string
): Promise<{ model: string; status: string }> {
  const res = await client.post<{ model: string; status: string }>(
    "/api/settings/select-model",
    { model }
  );
  return res.data;
}

export async function getDeadCode(
  sessionId: string
): Promise<DeadCodeResponse> {
  const res = await client.get<DeadCodeResponse>(
    `/api/analysis/dead-code/${sessionId}`
  );
  return res.data;
}

export async function getFunctionGraph(
  sessionId: string,
  filePath: string
): Promise<FunctionGraphResponse> {
  const res = await client.get<FunctionGraphResponse>(
    `/api/analysis/function-graph/${sessionId}`,
    { params: { file: filePath } }
  );
  return res.data;
}

export function generateReadmeCancellable(
  sessionId: string
): CancellableRequest<ReadmeResponse> {
  return cancellable((signal) =>
    client
      .post<ReadmeResponse>("/api/ai/advanced/readme", { session_id: sessionId }, { signal })
      .then((r) => r.data)
  );
}

export async function generateReadme(
  sessionId: string
): Promise<ReadmeResponse> {
  const res = await client.post<ReadmeResponse>("/api/ai/advanced/readme", {
    session_id: sessionId,
  });
  return res.data;
}

export function getRefactorSuggestionsCancellable(
  sessionId: string,
  filePath: string
): CancellableRequest<RefactorResponse> {
  return cancellable((signal) =>
    client
      .post<RefactorResponse>(
        "/api/ai/advanced/refactor",
        { session_id: sessionId, file_path: filePath },
        { signal }
      )
      .then((r) => r.data)
  );
}

export async function getRefactorSuggestions(
  sessionId: string,
  filePath: string
): Promise<RefactorResponse> {
  const res = await client.post<RefactorResponse>("/api/ai/advanced/refactor", {
    session_id: sessionId,
    file_path: filePath,
  });
  return res.data;
}

export function runSecurityScanCancellable(
  sessionId: string
): CancellableRequest<SecurityScanResponse> {
  return cancellable((signal) =>
    client
      .post<SecurityScanResponse>(
        "/api/ai/advanced/security",
        { session_id: sessionId },
        { signal }
      )
      .then((r) => r.data)
  );
}

export async function runSecurityScan(
  sessionId: string
): Promise<SecurityScanResponse> {
  const res = await client.post<SecurityScanResponse>("/api/ai/advanced/security", {
    session_id: sessionId,
  });
  return res.data;
}

export async function generatePRReview(
  sessionId: string,
  filePaths: string[] = []
): Promise<PRReviewResponse> {
  const res = await client.post<PRReviewResponse>("/api/ai/advanced/pr-review", {
    session_id: sessionId,
    file_paths: filePaths,
  });
  return res.data;
}

export async function getGitTimeline(
  sessionId: string
): Promise<TimelineResponse> {
  const res = await client.get<TimelineResponse>(`/api/git/timeline/${sessionId}`);
  return res.data;
}

export async function getCommitDiff(
  sessionId: string,
  commitHash: string
): Promise<CommitDiffResponse> {
  const res = await client.get<CommitDiffResponse>(
    `/api/git/diff/${sessionId}?commit=${commitHash}`
  );
  return res.data;
}

export async function getCoverage(
  sessionId: string
): Promise<CoverageResponse> {
  const res = await client.get<CoverageResponse>(`/api/git/coverage/${sessionId}`);
  return res.data;
}

export async function postComment(
  sessionId: string,
  targetType: string,
  targetId: string,
  message: string,
  author?: string,
  parentId?: string
): Promise<Comment> {
  const res = await client.post<Comment>("/api/comments", {
    session_id: sessionId,
    target_type: targetType,
    target_id: targetId,
    message,
    author: author ?? "Anonymous",
    parent_id: parentId ?? null,
  });
  return res.data;
}

export async function getComments(
  sessionId: string,
  targetId?: string
): Promise<Comment[]> {
  const params = targetId
    ? `?target_id=${encodeURIComponent(targetId)}`
    : "";
  const res = await client.get<Comment[]>(`/api/comments/${sessionId}${params}`);
  return res.data;
}

export async function getCommentCounts(
  sessionId: string
): Promise<CommentCountsResponse> {
  const res = await client.get<CommentCountsResponse>(
    `/api/comments/${sessionId}/counts`
  );
  return res.data;
}

export async function resolveComment(
  sessionId: string,
  commentId: string
): Promise<Comment> {
  const res = await client.patch<Comment>(
    `/api/comments/${sessionId}/resolve/${commentId}`
  );
  return res.data;
}

export async function deleteComment(
  sessionId: string,
  commentId: string
): Promise<void> {
  await client.delete(`/api/comments/${sessionId}/${commentId}`);
}

export async function getShareToken(
  sessionId: string
): Promise<ShareTokenResponse> {
  const res = await client.get<ShareTokenResponse>(
    `/api/comments/${sessionId}/share`
  );
  return res.data;
}
