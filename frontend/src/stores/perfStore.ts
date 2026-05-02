import { create } from "zustand";

interface PerfState {
  drawCalls: number;
  lastUpdatedAt: number;
  setDrawCalls: (calls: number) => void;
}

export const usePerfStore = create<PerfState>((set) => ({
  drawCalls: 0,
  lastUpdatedAt: 0,
  setDrawCalls: (calls) => set({ drawCalls: calls, lastUpdatedAt: performance.now() }),
}));
