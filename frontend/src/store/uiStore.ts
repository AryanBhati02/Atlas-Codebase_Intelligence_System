import { create } from "zustand";
import type { AIStatusResponse, Comment } from "../types";

export interface RecentRepo {
  name: string;
  url: string;
  sourceType: "github" | "zip" | "folder";
  lastOpened: number;
}

export interface UiState {
  
  isChatPanelOpen: boolean;
  showIngestModal: boolean;
  settingsPanelOpen: boolean;
  show3DGraph: boolean;

  recentRepos: RecentRepo[];

  aiStatus: AIStatusResponse | null;

  comments: Comment[];
  commentCounts: Record<string, number>;
  isCommentsLoading: boolean;

  toggleChatPanel: () => void;
  setShowIngestModal: (show: boolean) => void;
  addRecentRepo: (repo: RecentRepo) => void;
  toggleSettings: () => void;
  setSettingsPanelOpen: (open: boolean) => void;
  setAIStatus: (status: AIStatusResponse) => void;
  toggle3DGraph: () => void;

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
  } catch {
    
  }
  return true;
}

function getRecentRepos(): RecentRepo[] {
  try {
    const stored = localStorage.getItem("ci-recent-repos");
    if (stored) return JSON.parse(stored) as RecentRepo[];
  } catch {
    
  }
  return [];
}

export const useUiStore = create<UiState>((set) => ({
  isChatPanelOpen: getStoredChatPanel(),
  showIngestModal: false,
  settingsPanelOpen: false,
  show3DGraph: false,
  recentRepos: getRecentRepos(),
  aiStatus: null,
  comments: [],
  commentCounts: {},
  isCommentsLoading: false,

  toggleChatPanel: () =>
    set((s) => {
      const next = !s.isChatPanelOpen;
      try {
        localStorage.setItem("ci-chat-panel", String(next));
      } catch {
        
      }
      return { isChatPanelOpen: next };
    }),

  setShowIngestModal: (show) => set({ showIngestModal: show }),

  addRecentRepo: (repo) =>
    set((s) => {
      const filtered = s.recentRepos.filter((r) => r.url !== repo.url);
      const updated = [repo, ...filtered].slice(0, 10);
      try {
        localStorage.setItem("ci-recent-repos", JSON.stringify(updated));
      } catch {
        
      }
      return { recentRepos: updated };
    }),

  toggleSettings: () => set((s) => ({ settingsPanelOpen: !s.settingsPanelOpen })),
  setSettingsPanelOpen: (open) => set({ settingsPanelOpen: open }),
  setAIStatus: (status) => set({ aiStatus: status }),
  toggle3DGraph: () => set((s) => ({ show3DGraph: !s.show3DGraph })),

  setComments: (comments) => set({ comments, isCommentsLoading: false }),

  addComment: (comment) =>
    set((s) => ({
      comments: [comment, ...s.comments],
      commentCounts: {
        ...s.commentCounts,
        [comment.target_id]: (s.commentCounts[comment.target_id] ?? 0) + 1,
      },
    })),

  removeComment: (commentId) =>
    set((s) => {
      const removed = s.comments.find((c) => c.id === commentId);
      return {
        comments: s.comments.filter((c) => c.id !== commentId),
        commentCounts: removed
          ? {
              ...s.commentCounts,
              [removed.target_id]: Math.max(
                (s.commentCounts[removed.target_id] ?? 1) - 1,
                0
              ),
            }
          : s.commentCounts,
      };
    }),

  updateComment: (comment) =>
    set((s) => ({
      comments: s.comments.map((c) => (c.id === comment.id ? comment : c)),
    })),

  setCommentCounts: (counts) => set({ commentCounts: counts }),
  setCommentsLoading: (loading) => set({ isCommentsLoading: loading }),
}));
