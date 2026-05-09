import { create } from "zustand";
import {
  getSettings,
  getOllamaModels,
  selectModel as apiSelectModel,
  setPreferLocal as apiSetPreferLocal,
} from "../api/api";
import type { SettingsResponse } from "../types";

export interface OllamaModelInfo {
  name: string;
  size: string;
  modified_at: string;
}

interface DraftState {
  selectedModel: string;
  preferLocal: boolean;
}

interface SettingsStoreState {
  settings: SettingsResponse | null;
  ollamaModels: OllamaModelInfo[];
  isLoadingModels: boolean;
  ollamaReachable: boolean;

  draft: DraftState;
  committed: DraftState;
  isDirty: boolean;

  isApplying: boolean;
  applyError: string | null;

  loadSettings: () => Promise<void>;
  loadOllamaModels: () => Promise<void>;
  initDraft: (settings: SettingsResponse) => void;
  updateDraft: (partial: Partial<DraftState>) => void;
  applyDraft: () => Promise<boolean>;
  cancelDraft: () => void;
  
  clearApiKeys: () => void;
}

const DEFAULT_DRAFT: DraftState = {
  selectedModel: "phi3:mini",
  preferLocal: true,
};

export const useSettingsStore = create<SettingsStoreState>((set, get) => ({
  settings: null,
  ollamaModels: [],
  isLoadingModels: false,
  ollamaReachable: false,

  draft: { ...DEFAULT_DRAFT },
  committed: { ...DEFAULT_DRAFT },
  isDirty: false,

  isApplying: false,
  applyError: null,

  loadSettings: async () => {
    try {
      const data = await getSettings();
      set({ settings: data });
      get().initDraft(data);
    } catch {
      
    }
  },

  loadOllamaModels: async () => {
    set({ isLoadingModels: true });
    try {
      const data = await getOllamaModels();
      set({
        ollamaModels: data.models,
        ollamaReachable: data.reachable,
        isLoadingModels: false,
      });
    } catch {
      set({ ollamaModels: [], ollamaReachable: false, isLoadingModels: false });
    }
  },

  initDraft: (settings: SettingsResponse) => {
    const ollamaProvider = settings.providers.find((p) => p.name === "ollama");
    const model = ollamaProvider?.model ?? "phi3:mini";
    const committed: DraftState = {
      selectedModel: model,
      preferLocal: settings.prefer_local,
    };
    set({ draft: { ...committed }, committed: { ...committed }, isDirty: false });
  },

  updateDraft: (partial: Partial<DraftState>) => {
    const newDraft = { ...get().draft, ...partial };
    const committed = get().committed;
    const isDirty =
      newDraft.selectedModel !== committed.selectedModel ||
      newDraft.preferLocal !== committed.preferLocal;
    set({ draft: newDraft, isDirty });
  },

  applyDraft: async () => {
    const { draft, committed } = get();
    set({ isApplying: true, applyError: null });

    try {
      if (draft.selectedModel !== committed.selectedModel) {
        await apiSelectModel(draft.selectedModel);
      }
      if (draft.preferLocal !== committed.preferLocal) {
        await apiSetPreferLocal(draft.preferLocal);
      }

      set({ committed: { ...draft }, isDirty: false, isApplying: false });
      await get().loadSettings();
      return true;
    } catch (e: unknown) {
      set({
        isApplying: false,
        applyError:
          e instanceof Error ? e.message : "Failed to apply settings",
      });
      return false;
    }
  },

  cancelDraft: () => {
    const committed = get().committed;
    set({ draft: { ...committed }, isDirty: false, applyError: null });
  },

  clearApiKeys: () => {
    
    set({ settings: null });
  },
}));
