import { create } from "zustand";
import type {
  FileEntry,
  ParsedFile,
  GraphData,
  FileContentResponse,
  SessionStatus,
} from "../types";

export interface SessionState {
  // Identity
  sessionId: string | null;
  status: SessionStatus;
  progress: number;
  repoUrl: string | null;
  repoName: string | null;

  // Ingested data
  files: FileEntry[];
  totalFiles: number;
  sourceType: string | null;
  ingestedAt: string | null;

  // Analysis results
  isAnalyzed: boolean;
  parsedFiles: ParsedFile[];
  graphData: GraphData | null;

  // File viewer
  selectedFile: string | null;
  fileContent: FileContentResponse | null;

  // Async state
  isLoading: boolean;
  isAnalyzing: boolean;
  analysisProgress: { stage: string; current: number; total: number } | null;
  error: string | null;

  // Actions
  setSession: (data: {
    session_id: string;
    repo_name: string;
    files: FileEntry[];
    total_files: number;
    source_type: string;
    ingested_at: string;
  }) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
  setAnalyzing: (analyzing: boolean) => void;
  setAnalysisProgress: (
    progress: { stage: string; current: number; total: number } | null
  ) => void;
  setAnalysisResult: (parsed: ParsedFile[], graph: GraphData) => void;
  setSelectedFile: (path: string | null) => void;
  setFileContent: (content: FileContentResponse | null) => void;
}

const initialState: Omit<
  SessionState,
  | "setSession"
  | "setLoading"
  | "setError"
  | "reset"
  | "setAnalyzing"
  | "setAnalysisProgress"
  | "setAnalysisResult"
  | "setSelectedFile"
  | "setFileContent"
> = {
  sessionId: null,
  status: "queued",
  progress: 0,
  repoUrl: null,
  repoName: null,
  files: [],
  totalFiles: 0,
  sourceType: null,
  ingestedAt: null,
  isAnalyzed: false,
  parsedFiles: [],
  graphData: null,
  selectedFile: null,
  fileContent: null,
  isLoading: false,
  isAnalyzing: false,
  analysisProgress: null,
  error: null,
};

export const useSessionStore = create<SessionState>((set) => ({
  ...initialState,

  setSession: (data) =>
    set({
      sessionId: data.session_id,
      repoName: data.repo_name,
      repoUrl: data.repo_name,
      files: data.files,
      totalFiles: data.total_files,
      sourceType: data.source_type,
      ingestedAt: data.ingested_at,
      status: "parsing",
      error: null,
    }),

  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error, isLoading: false }),

  reset: () => set(initialState),

  setAnalyzing: (analyzing) => set({ isAnalyzing: analyzing }),
  setAnalysisProgress: (progress) => set({ analysisProgress: progress }),
  setAnalysisResult: (parsed, graph) =>
    set({
      parsedFiles: parsed,
      graphData: graph,
      isAnalyzed: true,
      isAnalyzing: false,
      analysisProgress: null,
      status: "done",
      progress: 100,
    }),

  setSelectedFile: (path) => {
    set({ selectedFile: path, fileContent: null });
    // Clear AI state for the previous file — import lazily to avoid circular dep
    import("./aiStore").then(({ useAiStore }) => {
      useAiStore.getState().clearFileAI();
    }).catch(() => undefined);
  },

  setFileContent: (content) => set({ fileContent: content }),
}));
