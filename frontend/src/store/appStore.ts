




import { create } from "zustand";
import type {
  FileEntry,
  ParsedFile,
  GraphData,
  FileContentResponse,
  QAHistoryEntry,
  FileReference,
  AIStatusResponse,
  DeadCodeResponse,
  FunctionGraphResponse,
  ReadmeResponse,
  RefactorResponse,
  SecurityScanResponse,
  PRReviewResponse,
  TimelineResponse,
  CommitDiffResponse,
  CoverageResponse,
  CommitEntry,
  Comment,
} from "../types";

export type { ThemeMode } from "./themeStore";

export interface RecentRepo {
  name: string;
  url: string;
  sourceType: "github" | "zip" | "folder";
  lastOpened: number;
}

interface AppState {

  isChatPanelOpen: boolean;
  showIngestModal: boolean;
  recentRepos: RecentRepo[];

  sessionId: string | null;
  repoName: string | null;
  files: FileEntry[];
  totalFiles: number;
  sourceType: string | null;
  ingestedAt: string | null;


  isAnalyzed: boolean;
  parsedFiles: ParsedFile[];
  graphData: GraphData | null;


  selectedFile: string | null;
  fileContent: FileContentResponse | null;


  aiExplanation: string | null;
  aiAnalysis: string | null;
  aiSource: string | null;
  isAILoading: boolean;


  beginnerGuide: string | null;
  beginnerTopFiles: { path: string; complexity_score: number }[];
  beginnerSource: string | null;
  isBeginnerLoading: boolean;


  qaHistory: QAHistoryEntry[];
  isQALoading: boolean;


  isLoading: boolean;
  isAnalyzing: boolean;
  error: string | null;


  settingsPanelOpen: boolean;
  aiStatus: AIStatusResponse | null;


  deadCodeData: DeadCodeResponse | null;
  showDeadCode: boolean;
  functionGraphData: FunctionGraphResponse | null;
  functionGraphFile: string | null;
  showFunctionGraph: boolean;
  isDeadCodeLoading: boolean;
  isFunctionGraphLoading: boolean;


  readmeData: ReadmeResponse | null;
  isReadmeLoading: boolean;
  refactorData: RefactorResponse | null;
  isRefactorLoading: boolean;
  securityData: SecurityScanResponse | null;
  isSecurityLoading: boolean;
  prReviewData: PRReviewResponse | null;
  isPRReviewLoading: boolean;


  show3DGraph: boolean;


  timelineData: TimelineResponse | null;
  isTimelineLoading: boolean;
  selectedCommit: CommitEntry | null;
  commitDiff: CommitDiffResponse | null;
  isCommitDiffLoading: boolean;
  coverageData: CoverageResponse | null;
  isCoverageLoading: boolean;
  showCoverage: boolean;
  highlightedFiles: Set<string>;


  comments: Comment[];
  commentCounts: Record<string, number>;
  isCommentsLoading: boolean;


  toggleChatPanel: () => void;
  setShowIngestModal: (show: boolean) => void;
  addRecentRepo: (repo: RecentRepo) => void;

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
  setAnalysisResult: (parsed: ParsedFile[], graph: GraphData) => void;


  setSelectedFile: (path: string | null) => void;
  setFileContent: (content: FileContentResponse | null) => void;


  setAIExplanation: (explanation: string | null, source?: string) => void;
  setAIAnalysis: (analysis: string | null, source?: string) => void;
  setAILoading: (loading: boolean) => void;


  setBeginnerGuide: (guide: string, topFiles: { path: string; complexity_score: number }[], source: string) => void;
  setBeginnerLoading: (loading: boolean) => void;


  addQAEntry: (question: string, answer: string, refs: FileReference[], source: string) => void;
  setQALoading: (loading: boolean) => void;


  toggleSettings: () => void;
  setSettingsPanelOpen: (open: boolean) => void;
  setAIStatus: (status: AIStatusResponse) => void;


  setDeadCodeData: (data: DeadCodeResponse | null) => void;
  toggleDeadCode: () => void;
  setDeadCodeLoading: (loading: boolean) => void;
  setFunctionGraphData: (data: FunctionGraphResponse | null, file: string | null) => void;
  toggleFunctionGraph: () => void;
  setFunctionGraphLoading: (loading: boolean) => void;


  setReadmeData: (data: ReadmeResponse | null) => void;
  setReadmeLoading: (loading: boolean) => void;
  setRefactorData: (data: RefactorResponse | null) => void;
  setRefactorLoading: (loading: boolean) => void;
  setSecurityData: (data: SecurityScanResponse | null) => void;
  setSecurityLoading: (loading: boolean) => void;
  setPRReviewData: (data: PRReviewResponse | null) => void;
  setPRReviewLoading: (loading: boolean) => void;
  toggle3DGraph: () => void;


  setTimelineData: (data: TimelineResponse | null) => void;
  setTimelineLoading: (loading: boolean) => void;
  setSelectedCommit: (commit: CommitEntry | null) => void;
  setCommitDiff: (diff: CommitDiffResponse | null) => void;
  setCommitDiffLoading: (loading: boolean) => void;
  setCoverageData: (data: CoverageResponse | null) => void;
  setCoverageLoading: (loading: boolean) => void;
  toggleCoverage: () => void;
  setHighlightedFiles: (files: Set<string>) => void;


  setComments: (comments: Comment[]) => void;
  addComment: (comment: Comment) => void;
  removeComment: (commentId: string) => void;
  updateComment: (comment: Comment) => void;
  setCommentCounts: (counts: Record<string, number>) => void;
  setCommentsLoading: (loading: boolean) => void;
}



function getStoredChatPanel(): boolean {
  try {
    const stored = localStorage.getItem("ci-chat-panel");
    if (stored === "false") return false;
  } catch { /* ignore */ }
  return true;
}

function getRecentRepos(): RecentRepo[] {
  try {
    const stored = localStorage.getItem("ci-recent-repos");
    if (stored) return JSON.parse(stored);
  } catch { /* ignore */ }
  return [];
}

const initialState = {

  isChatPanelOpen: getStoredChatPanel(),
  showIngestModal: false,
  recentRepos: getRecentRepos(),
  sessionId: null,
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
  aiExplanation: null,
  aiAnalysis: null,
  aiSource: null,
  isAILoading: false,
  beginnerGuide: null,
  beginnerTopFiles: [],
  beginnerSource: null,
  isBeginnerLoading: false,
  qaHistory: [],
  isQALoading: false,
  isLoading: false,
  isAnalyzing: false,
  error: null,
  settingsPanelOpen: false,
  aiStatus: null,
  deadCodeData: null,
  showDeadCode: false,
  functionGraphData: null,
  functionGraphFile: null,
  showFunctionGraph: false,
  isDeadCodeLoading: false,
  isFunctionGraphLoading: false,
  readmeData: null,
  isReadmeLoading: false,
  refactorData: null,
  isRefactorLoading: false,
  securityData: null,
  isSecurityLoading: false,
  prReviewData: null,
  isPRReviewLoading: false,
  show3DGraph: false,
  timelineData: null,
  isTimelineLoading: false,
  selectedCommit: null,
  commitDiff: null,
  isCommitDiffLoading: false,
  coverageData: null,
  isCoverageLoading: false,
  showCoverage: false,
  highlightedFiles: new Set<string>(),
  comments: [],
  commentCounts: {},
  isCommentsLoading: false,
};

export const useAppStore = create<AppState>((set) => ({
  ...initialState,



  toggleChatPanel: () =>
    set((state) => {
      const next = !state.isChatPanelOpen;
      try { localStorage.setItem("ci-chat-panel", String(next)); } catch { /* ignore */ }
      return { isChatPanelOpen: next };
    }),

  setShowIngestModal: (show) => set({ showIngestModal: show }),

  addRecentRepo: (repo) =>
    set((state) => {
      const filtered = state.recentRepos.filter((r) => r.url !== repo.url);
      const updated = [repo, ...filtered].slice(0, 10);
      try { localStorage.setItem("ci-recent-repos", JSON.stringify(updated)); } catch { /* ignore */ }
      return { recentRepos: updated };
    }),

  setSession: (data) =>
    set({
      sessionId: data.session_id,
      repoName: data.repo_name,
      files: data.files,
      totalFiles: data.total_files,
      sourceType: data.source_type,
      ingestedAt: data.ingested_at,
      error: null,
    }),

  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error, isLoading: false }),

  reset: () => set(initialState),

  setAnalyzing: (analyzing) => set({ isAnalyzing: analyzing }),
  setAnalysisResult: (parsed, graph) =>
    set({
      parsedFiles: parsed,
      graphData: graph,
      isAnalyzed: true,
      isAnalyzing: false,
    }),

  setSelectedFile: (path) =>
    set({
      selectedFile: path,
      fileContent: null,
      aiExplanation: null,
      aiAnalysis: null,
    }),

  setFileContent: (content) => set({ fileContent: content }),

  setAIExplanation: (explanation, source) =>
    set({ aiExplanation: explanation, aiSource: source || null }),
  setAIAnalysis: (analysis, source) =>
    set({ aiAnalysis: analysis, aiSource: source || null }),
  setAILoading: (loading) => set({ isAILoading: loading }),

  setBeginnerGuide: (guide, topFiles, source) =>
    set({
      beginnerGuide: guide,
      beginnerTopFiles: topFiles,
      beginnerSource: source,
      isBeginnerLoading: false,
    }),
  setBeginnerLoading: (loading) => set({ isBeginnerLoading: loading }),

  addQAEntry: (question, answer, refs, source) =>
    set((state) => ({
      qaHistory: [
        ...state.qaHistory,
        { question, answer, referenced_files: refs, source, timestamp: Date.now() },
      ],
      isQALoading: false,
    })),
  setQALoading: (loading) => set({ isQALoading: loading }),

  toggleSettings: () => set((state) => ({ settingsPanelOpen: !state.settingsPanelOpen })),
  setSettingsPanelOpen: (open) => set({ settingsPanelOpen: open }),
  setAIStatus: (status) => set({ aiStatus: status }),

  setDeadCodeData: (data) => set({ deadCodeData: data, isDeadCodeLoading: false }),
  toggleDeadCode: () => set((state) => ({ showDeadCode: !state.showDeadCode })),
  setDeadCodeLoading: (loading) => set({ isDeadCodeLoading: loading }),
  setFunctionGraphData: (data, file) => set({
    functionGraphData: data,
    functionGraphFile: file,
    showFunctionGraph: !!data,
    isFunctionGraphLoading: false,
  }),
  toggleFunctionGraph: () => set((state) => ({ showFunctionGraph: !state.showFunctionGraph })),
  setFunctionGraphLoading: (loading) => set({ isFunctionGraphLoading: loading }),

  setReadmeData: (data) => set({ readmeData: data, isReadmeLoading: false }),
  setReadmeLoading: (loading) => set({ isReadmeLoading: loading }),
  setRefactorData: (data) => set({ refactorData: data, isRefactorLoading: false }),
  setRefactorLoading: (loading) => set({ isRefactorLoading: loading }),
  setSecurityData: (data) => set({ securityData: data, isSecurityLoading: false }),
  setSecurityLoading: (loading) => set({ isSecurityLoading: loading }),
  setPRReviewData: (data) => set({ prReviewData: data, isPRReviewLoading: false }),
  setPRReviewLoading: (loading) => set({ isPRReviewLoading: loading }),
  toggle3DGraph: () => set((state) => ({ show3DGraph: !state.show3DGraph })),

  setTimelineData: (data) => set({ timelineData: data, isTimelineLoading: false }),
  setTimelineLoading: (loading) => set({ isTimelineLoading: loading }),
  setSelectedCommit: (commit) => set({ selectedCommit: commit }),
  setCommitDiff: (diff) => set({
    commitDiff: diff,
    isCommitDiffLoading: false,
    highlightedFiles: diff ? new Set(diff.files.map((f) => f.path)) : new Set<string>(),
  }),
  setCommitDiffLoading: (loading) => set({ isCommitDiffLoading: loading }),
  setCoverageData: (data) => set({ coverageData: data, isCoverageLoading: false }),
  setCoverageLoading: (loading) => set({ isCoverageLoading: loading }),
  toggleCoverage: () => set((state) => ({ showCoverage: !state.showCoverage })),
  setHighlightedFiles: (files) => set({ highlightedFiles: files }),

  setComments: (comments) => set({ comments, isCommentsLoading: false }),
  addComment: (comment) => set((state) => ({
    comments: [comment, ...state.comments],
    commentCounts: {
      ...state.commentCounts,
      [comment.target_id]: (state.commentCounts[comment.target_id] || 0) + 1,
    },
  })),
  removeComment: (commentId) => set((state) => {
    const removed = state.comments.find((c) => c.id === commentId);
    return {
      comments: state.comments.filter((c) => c.id !== commentId),
      commentCounts: removed
        ? {
          ...state.commentCounts,
          [removed.target_id]: Math.max((state.commentCounts[removed.target_id] || 1) - 1, 0),
        }
        : state.commentCounts,
    };
  }),
  updateComment: (comment) => set((state) => ({
    comments: state.comments.map((c) => c.id === comment.id ? comment : c),
  })),
  setCommentCounts: (counts) => set({ commentCounts: counts }),
  setCommentsLoading: (loading) => set({ isCommentsLoading: loading }),
}));
