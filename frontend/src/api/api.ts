import axios from "axios";
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

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000/api";

export const client = axios.create({
  baseURL: API_BASE,
  timeout: 180_000,
});


export async function analyzeSession(
  sessionId: string
): Promise<AnalyzeResponse> {
  const res = await client.post<AnalyzeResponse>(`/analyze/${sessionId}`);
  return res.data;
}







export function analyzeWithProgress(
  sessionId: string,
  onProgress: (stage: string, current: number, total: number) => void
): { promise: Promise<AnalyzeResponse>; abort: () => void } {
  let aborted = false;

  const promise = new Promise<AnalyzeResponse>(async (resolve, reject) => {
    try {

      console.log("[Analysis] Starting analysis for", sessionId);
      const startRes = await client.post(`/analyze/start/${sessionId}`);
      console.log("[Analysis] Start response:", startRes.data);

      if (aborted) { reject(new Error("Aborted")); return; }


      let consecutiveErrors = 0;
      const MAX_RETRIES = 3;

      while (!aborted) {
        await new Promise((r) => setTimeout(r, 500));
        if (aborted) break;

        try {
          const { data: prog } = await client.get<{
            stage: string;
            current: number;
            total: number;
            done: boolean;
            error: string | null;
          }>(`/analyze/progress/${sessionId}`);

          consecutiveErrors = 0;
          onProgress(prog.stage, prog.current, prog.total);

          if (prog.error) {
            console.error("[Analysis] Backend error:", prog.error);
            reject(new Error(prog.error));
            return;
          }

          if (prog.done) {
            console.log("[Analysis] Done, fetching results...");

            const res = await client.post<AnalyzeResponse>(`/analyze/${sessionId}`);
            console.log("[Analysis] Results fetched:", res.data.total_files, "files");
            resolve(res.data);
            return;
          }
        } catch (pollErr) {
          consecutiveErrors++;
          console.warn(`[Analysis] Poll error (${consecutiveErrors}/${MAX_RETRIES}):`, pollErr);
          if (consecutiveErrors >= MAX_RETRIES) {
            reject(new Error("Lost connection to analysis server."));
            return;
          }

          await new Promise((r) => setTimeout(r, 1000));
        }
      }
      if (aborted) reject(new Error("Aborted"));
    } catch (err) {
      console.error("[Analysis] Fatal error:", err);
      reject(err);
    }
  });

  return { promise, abort: () => { aborted = true; } };
}

export async function getGraph(sessionId: string): Promise<GraphData> {
  const res = await client.get<GraphData>(`/analyze/graph/${sessionId}`);
  return res.data;
}


export async function getFileContent(
  sessionId: string,
  path: string
): Promise<FileContentResponse> {
  const res = await client.get<FileContentResponse>(
    `/files/content/${sessionId}`,
    { params: { path } }
  );
  return res.data;
}


export async function explainFile(
  sessionId: string,
  filePath: string
): Promise<AIExplainResponse> {
  const res = await client.post<AIExplainResponse>("/ai/explain", {
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
  const res = await client.post<AIAnalyzeCodeResponse>("/ai/analyze-code", {
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
  const res = await client.post<BeginnerGuideResponse>("/ai/beginner-guide", {
    session_id: sessionId,
  });
  return res.data;
}


export async function askQuestion(
  sessionId: string,
  question: string
): Promise<QAResponse> {
  const res = await client.post<QAResponse>("/ai/qa", {
    session_id: sessionId,
    question,
  });
  return res.data;
}



export async function getSettings(): Promise<SettingsResponse> {
  const res = await client.get<SettingsResponse>("/settings");
  return res.data;
}

export async function getAIStatus(): Promise<AIStatusResponse> {
  const res = await client.get<AIStatusResponse>("/settings/status");
  return res.data;
}

export async function updateProviderKey(
  provider: string,
  key: string
): Promise<KeyUpdateResponse> {
  const res = await client.post<KeyUpdateResponse>("/settings/keys", {
    provider,
    key,
  });
  return res.data;
}

export async function testProvider(
  provider: string
): Promise<TestProviderResponse> {
  const res = await client.post<TestProviderResponse>("/settings/test", {
    provider,
  });
  return res.data;
}

export async function setPreferLocal(
  preferLocal: boolean
): Promise<{ prefer_local: boolean; active_provider: string }> {
  const res = await client.post("/settings/prefer", {
    prefer_local: preferLocal,
  });
  return res.data;
}

export async function clearAICache(
  sessionId?: string
): Promise<ClearCacheResponse> {
  const res = await client.post<ClearCacheResponse>("/settings/clear-cache", {
    session_id: sessionId || null,
  });
  return res.data;
}

export async function getOllamaModels(): Promise<{
  models: { name: string; size: string; modified_at: string }[];
  reachable: boolean;
}> {
  const res = await client.get("/settings/ollama-models");
  return res.data;
}

export async function selectModel(model: string): Promise<{ model: string; status: string }> {
  const res = await client.post("/settings/select-model", { model });
  return res.data;
}


export async function getDeadCode(
  sessionId: string
): Promise<DeadCodeResponse> {
  const res = await client.get<DeadCodeResponse>(
    `/analysis/dead-code/${sessionId}`
  );
  return res.data;
}


export async function getFunctionGraph(
  sessionId: string,
  filePath: string
): Promise<FunctionGraphResponse> {
  const res = await client.get<FunctionGraphResponse>(
    `/analysis/function-graph/${sessionId}`,
    { params: { file: filePath } }
  );
  return res.data;
}


export async function generateReadme(
  sessionId: string
): Promise<ReadmeResponse> {
  const res = await client.post<ReadmeResponse>("/ai/advanced/readme", {
    session_id: sessionId,
  });
  return res.data;
}


export async function getRefactorSuggestions(
  sessionId: string,
  filePath: string
): Promise<RefactorResponse> {
  const res = await client.post<RefactorResponse>("/ai/advanced/refactor", {
    session_id: sessionId,
    file_path: filePath,
  });
  return res.data;
}


export async function runSecurityScan(
  sessionId: string
): Promise<SecurityScanResponse> {
  const res = await client.post<SecurityScanResponse>("/ai/advanced/security", {
    session_id: sessionId,
  });
  return res.data;
}


export async function generatePRReview(
  sessionId: string,
  filePaths: string[] = []
): Promise<PRReviewResponse> {
  const res = await client.post<PRReviewResponse>("/ai/advanced/pr-review", {
    session_id: sessionId,
    file_paths: filePaths,
  });
  return res.data;
}


export async function getGitTimeline(
  sessionId: string
): Promise<TimelineResponse> {
  const res = await client.get<TimelineResponse>(`/git/timeline/${sessionId}`);
  return res.data;
}

export async function getCommitDiff(
  sessionId: string,
  commitHash: string
): Promise<CommitDiffResponse> {
  const res = await client.get<CommitDiffResponse>(
    `/git/diff/${sessionId}?commit=${commitHash}`
  );
  return res.data;
}

export async function getCoverage(
  sessionId: string
): Promise<CoverageResponse> {
  const res = await client.get<CoverageResponse>(`/git/coverage/${sessionId}`);
  return res.data;
}


export async function postComment(
  sessionId: string,
  targetType: string,
  targetId: string,
  message: string,
  author?: string,
  parentId?: string,
): Promise<Comment> {
  const res = await client.post<Comment>("/comments", {
    session_id: sessionId,
    target_type: targetType,
    target_id: targetId,
    message,
    author: author || "Anonymous",
    parent_id: parentId || null,
  });
  return res.data;
}

export async function getComments(
  sessionId: string,
  targetId?: string,
): Promise<Comment[]> {
  const params = targetId ? `?target_id=${encodeURIComponent(targetId)}` : "";
  const res = await client.get<Comment[]>(`/comments/${sessionId}${params}`);
  return res.data;
}

export async function getCommentCounts(
  sessionId: string,
): Promise<CommentCountsResponse> {
  const res = await client.get<CommentCountsResponse>(`/comments/${sessionId}/counts`);
  return res.data;
}

export async function resolveComment(
  sessionId: string,
  commentId: string,
): Promise<Comment> {
  const res = await client.patch<Comment>(`/comments/${sessionId}/resolve/${commentId}`);
  return res.data;
}

export async function deleteComment(
  sessionId: string,
  commentId: string,
): Promise<void> {
  await client.delete(`/comments/${sessionId}/${commentId}`);
}

export async function getShareToken(
  sessionId: string,
): Promise<ShareTokenResponse> {
  const res = await client.get<ShareTokenResponse>(`/comments/${sessionId}/share`);
  return res.data;
}
