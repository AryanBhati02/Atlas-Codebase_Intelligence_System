import { create } from "zustand";

interface PerfState {
  drawCalls: number;
  lastUpdatedAt: number;
  setDrawCalls: (calls: number) => void;

  enrichNodeCallsPerSec: number;
  enrichNodeAvgMs: number;
  getVisibleNodesCallsPerSec: number;
  getVisibleNodesAvgMs: number;
  getVisibleNodesLastResultCount: number;
  setEnrichNodeCallsPerSec: (v: number) => void;
  setEnrichNodeAvgMs: (v: number) => void;
  setGetVisibleNodesCallsPerSec: (v: number) => void;
  setGetVisibleNodesAvgMs: (v: number) => void;
  setGetVisibleNodesLastResultCount: (v: number) => void;
}

export const usePerfStore = create<PerfState>((set) => ({
  drawCalls: 0,
  lastUpdatedAt: 0,
  setDrawCalls: (calls) => set({ drawCalls: calls, lastUpdatedAt: performance.now() }),

  enrichNodeCallsPerSec: 0,
  enrichNodeAvgMs: 0,
  getVisibleNodesCallsPerSec: 0,
  getVisibleNodesAvgMs: 0,
  getVisibleNodesLastResultCount: 0,
  setEnrichNodeCallsPerSec: (v) => set({ enrichNodeCallsPerSec: v }),
  setEnrichNodeAvgMs: (v) => set({ enrichNodeAvgMs: v }),
  setGetVisibleNodesCallsPerSec: (v) => set({ getVisibleNodesCallsPerSec: v }),
  setGetVisibleNodesAvgMs: (v) => set({ getVisibleNodesAvgMs: v }),
  setGetVisibleNodesLastResultCount: (v) => set({ getVisibleNodesLastResultCount: v }),
}));
