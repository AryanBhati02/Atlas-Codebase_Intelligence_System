import { create } from "zustand";
import type {
  DeadCodeResponse,
  FunctionGraphResponse,
  TimelineResponse,
  CommitEntry,
  CommitDiffResponse,
  CoverageResponse,
} from "../types";

export interface GraphState {
  // Dead code analysis
  deadCodeData: DeadCodeResponse | null;
  showDeadCode: boolean;
  isDeadCodeLoading: boolean;

  // Function call graph
  functionGraphData: FunctionGraphResponse | null;
  functionGraphFile: string | null;
  showFunctionGraph: boolean;
  isFunctionGraphLoading: boolean;

  // Git timeline
  timelineData: TimelineResponse | null;
  isTimelineLoading: boolean;
  selectedCommit: CommitEntry | null;
  commitDiff: CommitDiffResponse | null;
  isCommitDiffLoading: boolean;

  // Coverage
  coverageData: CoverageResponse | null;
  isCoverageLoading: boolean;
  showCoverage: boolean;
  highlightedFiles: Set<string>;

  // Actions
  setDeadCodeData: (data: DeadCodeResponse | null) => void;
  toggleDeadCode: () => void;
  setDeadCodeLoading: (loading: boolean) => void;

  setFunctionGraphData: (
    data: FunctionGraphResponse | null,
    file: string | null
  ) => void;
  toggleFunctionGraph: () => void;
  setFunctionGraphLoading: (loading: boolean) => void;

  setTimelineData: (data: TimelineResponse | null) => void;
  setTimelineLoading: (loading: boolean) => void;
  setSelectedCommit: (commit: CommitEntry | null) => void;
  setCommitDiff: (diff: CommitDiffResponse | null) => void;
  setCommitDiffLoading: (loading: boolean) => void;

  setCoverageData: (data: CoverageResponse | null) => void;
  setCoverageLoading: (loading: boolean) => void;
  toggleCoverage: () => void;
  setHighlightedFiles: (files: Set<string>) => void;
}

export const useGraphStore = create<GraphState>((set) => ({
  deadCodeData: null,
  showDeadCode: false,
  isDeadCodeLoading: false,

  functionGraphData: null,
  functionGraphFile: null,
  showFunctionGraph: false,
  isFunctionGraphLoading: false,

  timelineData: null,
  isTimelineLoading: false,
  selectedCommit: null,
  commitDiff: null,
  isCommitDiffLoading: false,

  coverageData: null,
  isCoverageLoading: false,
  showCoverage: false,
  highlightedFiles: new Set<string>(),

  setDeadCodeData: (data) => set({ deadCodeData: data, isDeadCodeLoading: false }),
  toggleDeadCode: () => set((s) => ({ showDeadCode: !s.showDeadCode })),
  setDeadCodeLoading: (loading) => set({ isDeadCodeLoading: loading }),

  setFunctionGraphData: (data, file) =>
    set({
      functionGraphData: data,
      functionGraphFile: file,
      showFunctionGraph: !!data,
      isFunctionGraphLoading: false,
    }),
  toggleFunctionGraph: () => set((s) => ({ showFunctionGraph: !s.showFunctionGraph })),
  setFunctionGraphLoading: (loading) => set({ isFunctionGraphLoading: loading }),

  setTimelineData: (data) => set({ timelineData: data, isTimelineLoading: false }),
  setTimelineLoading: (loading) => set({ isTimelineLoading: loading }),
  setSelectedCommit: (commit) => set({ selectedCommit: commit }),
  setCommitDiff: (diff) =>
    set({
      commitDiff: diff,
      isCommitDiffLoading: false,
      highlightedFiles: diff
        ? new Set(diff.files.map((f) => f.path))
        : new Set<string>(),
    }),
  setCommitDiffLoading: (loading) => set({ isCommitDiffLoading: loading }),

  setCoverageData: (data) => set({ coverageData: data, isCoverageLoading: false }),
  setCoverageLoading: (loading) => set({ isCoverageLoading: loading }),
  toggleCoverage: () => set((s) => ({ showCoverage: !s.showCoverage })),
  setHighlightedFiles: (files) => set({ highlightedFiles: files }),
}));
