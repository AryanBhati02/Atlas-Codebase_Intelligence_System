
export { useSessionStore } from "./sessionStore";
export { useGraphStore } from "./graphStore";
export { useAiStore } from "./aiStore";
export { useUiStore } from "./uiStore";
export { useSettingsStore } from "./settingsStore";
export type { RecentRepo } from "./uiStore";
export type { ThemeMode } from "./themeStore";

import { useSessionStore } from "./sessionStore";
import { useGraphStore } from "./graphStore";
import { useAiStore } from "./aiStore";
import { useUiStore } from "./uiStore";

export function getAppState() {
  return {
    ...useSessionStore.getState(),
    ...useGraphStore.getState(),
    ...useAiStore.getState(),
    ...useUiStore.getState(),
    setSelectedFile: (path: string | null) => {
      useSessionStore.getState().setSelectedFile(path);
    },
  };
}

export function useAppStore() {
  const session = useSessionStore();
  const graph = useGraphStore();
  const ai = useAiStore();
  const ui = useUiStore();

  return {
    
    sessionId: session.sessionId,
    status: session.status,
    progress: session.progress,
    repoUrl: session.repoUrl,
    repoName: session.repoName,
    files: session.files,
    totalFiles: session.totalFiles,
    sourceType: session.sourceType,
    ingestedAt: session.ingestedAt,
    isAnalyzed: session.isAnalyzed,
    parsedFiles: session.parsedFiles,
    graphData: session.graphData,
    selectedFile: session.selectedFile,
    fileContent: session.fileContent,
    isLoading: session.isLoading,
    isAnalyzing: session.isAnalyzing,
    analysisProgress: session.analysisProgress,
    error: session.error,
    setSession: session.setSession,
    setSessionAndLoading: session.setSessionAndLoading,
    setLoading: session.setLoading,
    setError: session.setError,
    reset: session.reset,
    setAnalyzing: session.setAnalyzing,
    setAnalysisProgress: session.setAnalysisProgress,
    setAnalysisResult: session.setAnalysisResult,
    setFileContent: session.setFileContent,
    
    setSelectedFile: (path: string | null) => {
      session.setSelectedFile(path);
    },

    deadCodeData: graph.deadCodeData,
    showDeadCode: graph.showDeadCode,
    isDeadCodeLoading: graph.isDeadCodeLoading,
    functionGraphData: graph.functionGraphData,
    functionGraphFile: graph.functionGraphFile,
    showFunctionGraph: graph.showFunctionGraph,
    isFunctionGraphLoading: graph.isFunctionGraphLoading,
    timelineData: graph.timelineData,
    isTimelineLoading: graph.isTimelineLoading,
    selectedCommit: graph.selectedCommit,
    commitDiff: graph.commitDiff,
    isCommitDiffLoading: graph.isCommitDiffLoading,
    coverageData: graph.coverageData,
    isCoverageLoading: graph.isCoverageLoading,
    showCoverage: graph.showCoverage,
    highlightedFiles: graph.highlightedFiles,
    setDeadCodeData: graph.setDeadCodeData,
    toggleDeadCode: graph.toggleDeadCode,
    setDeadCodeLoading: graph.setDeadCodeLoading,
    setFunctionGraphData: graph.setFunctionGraphData,
    toggleFunctionGraph: graph.toggleFunctionGraph,
    setFunctionGraphLoading: graph.setFunctionGraphLoading,
    setTimelineData: graph.setTimelineData,
    setTimelineLoading: graph.setTimelineLoading,
    setSelectedCommit: graph.setSelectedCommit,
    setCommitDiff: graph.setCommitDiff,
    setCommitDiffLoading: graph.setCommitDiffLoading,
    setCoverageData: graph.setCoverageData,
    setCoverageLoading: graph.setCoverageLoading,
    toggleCoverage: graph.toggleCoverage,
    setHighlightedFiles: graph.setHighlightedFiles,

    aiExplanation: ai.aiExplanation,
    aiAnalysis: ai.aiAnalysis,
    aiSource: ai.aiSource,
    isAILoading: ai.isAILoading,
    isAIStreaming: ai.isAIStreaming,
    currentProvider: ai.currentProvider,
    beginnerGuide: ai.beginnerGuide,
    beginnerTopFiles: ai.beginnerTopFiles,
    beginnerSource: ai.beginnerSource,
    isBeginnerLoading: ai.isBeginnerLoading,
    qaHistory: ai.qaHistory,
    isQALoading: ai.isQALoading,
    readmeData: ai.readmeData,
    isReadmeLoading: ai.isReadmeLoading,
    refactorData: ai.refactorData,
    isRefactorLoading: ai.isRefactorLoading,
    securityData: ai.securityData,
    isSecurityLoading: ai.isSecurityLoading,
    prReviewData: ai.prReviewData,
    isPRReviewLoading: ai.isPRReviewLoading,
    clearFileAI: ai.clearFileAI,
    setAIExplanation: ai.setAIExplanation,
    setAIAnalysis: ai.setAIAnalysis,
    appendAIAnalysis: ai.appendAIAnalysis,
    setAILoading: ai.setAILoading,
    setAIStreaming: ai.setAIStreaming,
    setBeginnerGuide: ai.setBeginnerGuide,
    setBeginnerLoading: ai.setBeginnerLoading,
    addQAEntry: ai.addQAEntry,
    setQALoading: ai.setQALoading,
    setReadmeData: ai.setReadmeData,
    setReadmeLoading: ai.setReadmeLoading,
    setRefactorData: ai.setRefactorData,
    setRefactorLoading: ai.setRefactorLoading,
    setSecurityData: ai.setSecurityData,
    setSecurityLoading: ai.setSecurityLoading,
    setPRReviewData: ai.setPRReviewData,
    setPRReviewLoading: ai.setPRReviewLoading,

    isChatPanelOpen: ui.isChatPanelOpen,
    showIngestModal: ui.showIngestModal,
    settingsPanelOpen: ui.settingsPanelOpen,
    show3DGraph: ui.show3DGraph,
    recentRepos: ui.recentRepos,
    aiStatus: ui.aiStatus,
    comments: ui.comments,
    commentCounts: ui.commentCounts,
    isCommentsLoading: ui.isCommentsLoading,
    toggleChatPanel: ui.toggleChatPanel,
    setShowIngestModal: ui.setShowIngestModal,
    addRecentRepo: ui.addRecentRepo,
    toggleSettings: ui.toggleSettings,
    setSettingsPanelOpen: ui.setSettingsPanelOpen,
    setAIStatus: ui.setAIStatus,
    toggle3DGraph: ui.toggle3DGraph,
    setComments: ui.setComments,
    addComment: ui.addComment,
    removeComment: ui.removeComment,
    updateComment: ui.updateComment,
    setCommentCounts: ui.setCommentCounts,
    setCommentsLoading: ui.setCommentsLoading,
  };
}
