import { create } from "zustand";
import type {
  FileReference,
  QAHistoryEntry,
  ReadmeResponse,
  RefactorResponse,
  SecurityScanResponse,
  PRReviewResponse,
  AIProvider,
} from "../types";

export interface AiState {
  
  aiExplanation: string | null;

  aiAnalysis: string | null;
  aiSource: string | null;
  isAILoading: boolean;
  isAIStreaming: boolean;

  currentProvider: AIProvider | null;
  streamingContent: string;

  beginnerGuide: string | null;
  beginnerTopFiles: { path: string; complexity_score: number }[];
  beginnerSource: string | null;
  isBeginnerLoading: boolean;

  qaHistory: QAHistoryEntry[];
  isQALoading: boolean;

  readmeData: ReadmeResponse | null;
  isReadmeLoading: boolean;
  refactorData: RefactorResponse | null;
  isRefactorLoading: boolean;
  securityData: SecurityScanResponse | null;
  isSecurityLoading: boolean;
  prReviewData: PRReviewResponse | null;
  isPRReviewLoading: boolean;

  clearFileAI: () => void;
  setAIExplanation: (explanation: string | null, source?: string) => void;
  setAIAnalysis: (analysis: string | null, source?: string) => void;
  appendAIAnalysis: (chunk: string) => void;
  setAILoading: (loading: boolean) => void;
  setAIStreaming: (streaming: boolean) => void;
  setCurrentProvider: (provider: AIProvider | null) => void;

  setBeginnerGuide: (
    guide: string,
    topFiles: { path: string; complexity_score: number }[],
    source: string
  ) => void;
  setBeginnerLoading: (loading: boolean) => void;

  addQAEntry: (
    question: string,
    answer: string,
    refs: FileReference[],
    source: string
  ) => void;
  setQALoading: (loading: boolean) => void;

  setReadmeData: (data: ReadmeResponse | null) => void;
  setReadmeLoading: (loading: boolean) => void;
  setRefactorData: (data: RefactorResponse | null) => void;
  setRefactorLoading: (loading: boolean) => void;
  setSecurityData: (data: SecurityScanResponse | null) => void;
  setSecurityLoading: (loading: boolean) => void;
  setPRReviewData: (data: PRReviewResponse | null) => void;
  setPRReviewLoading: (loading: boolean) => void;
}

export const useAiStore = create<AiState>((set) => ({
  aiExplanation: null,
  aiAnalysis: null,
  aiSource: null,
  isAILoading: false,
  isAIStreaming: false,
  currentProvider: null,
  streamingContent: "",

  beginnerGuide: null,
  beginnerTopFiles: [],
  beginnerSource: null,
  isBeginnerLoading: false,

  qaHistory: [],
  isQALoading: false,

  readmeData: null,
  isReadmeLoading: false,
  refactorData: null,
  isRefactorLoading: false,
  securityData: null,
  isSecurityLoading: false,
  prReviewData: null,
  isPRReviewLoading: false,

  clearFileAI: () =>
    set({ aiExplanation: null, aiAnalysis: null, aiSource: null }),

  setAIExplanation: (explanation, source) =>
    set({ aiExplanation: explanation, aiSource: source ?? null }),

  setAIAnalysis: (analysis, source) =>
    set({ aiAnalysis: analysis, aiSource: source ?? null, isAIStreaming: false }),

  appendAIAnalysis: (chunk) =>
    set((s) => ({ aiAnalysis: (s.aiAnalysis ?? "") + chunk })),

  setAILoading: (loading) => set({ isAILoading: loading }),
  setAIStreaming: (streaming) => set({ isAIStreaming: streaming }),
  setCurrentProvider: (provider) => set({ currentProvider: provider }),

  setBeginnerGuide: (guide, topFiles, source) =>
    set({
      beginnerGuide: guide,
      beginnerTopFiles: topFiles,
      beginnerSource: source,
      isBeginnerLoading: false,
    }),
  setBeginnerLoading: (loading) => set({ isBeginnerLoading: loading }),

  addQAEntry: (question, answer, refs, source) =>
    set((s) => ({
      qaHistory: [
        ...s.qaHistory,
        { question, answer, referenced_files: refs, source, timestamp: Date.now() },
      ],
      isQALoading: false,
    })),
  setQALoading: (loading) => set({ isQALoading: loading }),

  setReadmeData: (data) => set({ readmeData: data, isReadmeLoading: false }),
  setReadmeLoading: (loading) => set({ isReadmeLoading: loading }),
  setRefactorData: (data) => set({ refactorData: data, isRefactorLoading: false }),
  setRefactorLoading: (loading) => set({ isRefactorLoading: loading }),
  setSecurityData: (data) => set({ securityData: data, isSecurityLoading: false }),
  setSecurityLoading: (loading) => set({ isSecurityLoading: loading }),
  setPRReviewData: (data) => set({ prReviewData: data, isPRReviewLoading: false }),
  setPRReviewLoading: (loading) => set({ isPRReviewLoading: loading }),
}));
