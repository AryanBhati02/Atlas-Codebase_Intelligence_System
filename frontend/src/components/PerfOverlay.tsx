import { useState, useEffect } from "react";
import type { CSSProperties } from "react";
import { useSessionStore } from "../store/sessionStore";
import { usePerfStore } from "../stores/perfStore";
import { enrichNodeProfiler } from "./dashboard/GraphView";
import { visibleNodesProfiler } from "../utils/graphClustering";

// performance.memory is a non-standard V8 extension not in lib.dom.d.ts
interface MemoryInfo {
  readonly usedJSHeapSize: number;
  readonly jsHeapSizeLimit: number;
  readonly totalJSHeapSize: number;
}
interface PerformanceWithMemory extends Performance {
  readonly memory?: MemoryInfo;
}

// Teach TypeScript about the opt-in build flag (Vite custom env var)
declare global {
  interface ImportMetaEnv {
    readonly VITE_ENABLE_PERF?: string;
  }
}

interface Metrics {
  fps: number;
  rollingFps: number;
  frameTimeMs: number;
  heapUsedMB: number | null;
  heapLimitMB: number | null;
  nodeCount: number;
  edgeCount: number;
  drawCalls: number | null; // null = 3D canvas not active
  enrichNodeCallsPerSec: number;
  enrichNodeAvgMs: number;
  getVisibleNodesCallsPerSec: number;
  getVisibleNodesAvgMs: number;
  getVisibleNodesLastResultCount: number;
}

const INITIAL_METRICS: Metrics = {
  fps: 0,
  rollingFps: 0,
  frameTimeMs: 0,
  heapUsedMB: null,
  heapLimitMB: null,
  nodeCount: 0,
  edgeCount: 0,
  drawCalls: null,
  enrichNodeCallsPerSec: 0,
  enrichNodeAvgMs: 0,
  getVisibleNodesCallsPerSec: 0,
  getVisibleNodesAvgMs: 0,
  getVisibleNodesLastResultCount: 0,
};

const DISPLAY_INTERVAL_MS = 100; // throttle visible state to ~10 updates/sec
const STALENESS_MS = 500;        // treat 3D as inactive if no draw-call update in this window

function fpsColor(fps: number): string {
  if (fps >= 55) return "#4ade80";
  if (fps >= 30) return "#fbbf24";
  return "#f87171";
}

function heapColor(usedMB: number, limitMB: number): string {
  if (limitMB <= 0) return "#94a3b8";
  const ratio = usedMB / limitMB;
  if (ratio < 0.6) return "#4ade80";
  if (ratio < 0.85) return "#fbbf24";
  return "#f87171";
}

function avgMsColor(ms: number): string {
  if (ms < 0.5) return "#4ade80";
  if (ms < 2.0) return "#fbbf24";
  return "#f87171";
}

// Module-level style objects — defined once, no allocation on re-render
const containerStyle: CSSProperties = {
  position: "fixed",
  bottom: 12,
  right: 12,
  width: 220,
  padding: "8px 12px 10px",
  background: "rgba(0,0,0,0.75)",
  backdropFilter: "blur(6px)",
  border: "1px solid rgba(255,255,255,0.07)",
  borderRadius: 8,
  fontFamily: '"JetBrains Mono", monospace',
  fontSize: 11,
  lineHeight: 1.9,
  zIndex: 9999,
  pointerEvents: "none",
  fontVariantNumeric: "tabular-nums",
  color: "#e2e8f0",
};

const rowStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "baseline",
};

const labelStyle: CSSProperties = { color: "#64748b" };

const dimStyle: CSSProperties = { color: "#475569" };

const headerStyle: CSSProperties = {
  fontSize: 9,
  fontWeight: 600,
  letterSpacing: "0.12em",
  textTransform: "uppercase",
  color: "#475569",
  marginBottom: 3,
};

const dividerStyle: CSSProperties = {
  height: 1,
  background: "rgba(255,255,255,0.07)",
  margin: "3px 0 4px",
};

export function PerfOverlay() {
  const [visible, setVisible] = useState(false);
  const [metrics, setMetrics] = useState<Metrics>(INITIAL_METRICS);

  // Keyboard toggle — minimal: only a window keydown listener, zero other work
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.code === "KeyP" && e.shiftKey && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        setVisible((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Measurement loop — created only when visible, torn down immediately when hidden
  useEffect(() => {
    if (!visible) return;

    let rafId: number;
    let lastTs = performance.now();
    let lastDisplay = 0;
    const frameTs: number[] = []; // timestamps of frames within the rolling 1s window

    const tick = (now: number): void => {
      const raw = now - lastTs;
      lastTs = now;
      const delta = Math.max(raw, 0.1); // guard against sub-millisecond deltas on first frame

      // Maintain rolling 1-second window of frame timestamps
      frameTs.push(now);
      for (;;) {
        const oldest = frameTs[0];
        if (oldest === undefined || oldest >= now - 1000) break;
        frameTs.shift();
      }

      // Throttle the state update that causes React to re-render (~10×/sec)
      if (now - lastDisplay >= DISPLAY_INTERVAL_MS) {
        lastDisplay = now;

        const fps = Math.min(Math.round(1000 / delta), 9999);
        const rollingFps = frameTs.length;
        const frameTimeMs = Math.round(delta * 10) / 10;

        const perf = performance as PerformanceWithMemory;
        const mem = perf.memory;
        const heapUsedMB = mem != null
          ? Math.round((mem.usedJSHeapSize / 1_048_576) * 10) / 10
          : null;
        const heapLimitMB = mem != null
          ? Math.round(mem.jsHeapSizeLimit / 1_048_576)
          : null;

        // Imperative reads — no subscriptions, so these don't cause extra renders
        const { graphData } = useSessionStore.getState();
        const nodeCount = graphData?.nodes.length ?? 0;
        const edgeCount = graphData?.edges.length ?? 0;

        const perfState = usePerfStore.getState();
        const is3DActive = performance.now() - perfState.lastUpdatedAt < STALENESS_MS;
        const drawCalls = is3DActive ? perfState.drawCalls : null;

        // Pull profiler stats and flush to store for external consumers
        const enrichStats = enrichNodeProfiler.getStats();
        const visibleStats = visibleNodesProfiler.getStats();
        perfState.setEnrichNodeCallsPerSec(enrichStats.callsPerSec);
        perfState.setEnrichNodeAvgMs(enrichStats.avgMs);
        perfState.setGetVisibleNodesCallsPerSec(visibleStats.callsPerSec);
        perfState.setGetVisibleNodesAvgMs(visibleStats.avgMs);
        perfState.setGetVisibleNodesLastResultCount(visibleStats.lastCallCount);

        setMetrics({
          fps, rollingFps, frameTimeMs, heapUsedMB, heapLimitMB, nodeCount, edgeCount, drawCalls,
          enrichNodeCallsPerSec: enrichStats.callsPerSec,
          enrichNodeAvgMs: enrichStats.avgMs,
          getVisibleNodesCallsPerSec: visibleStats.callsPerSec,
          getVisibleNodesAvgMs: visibleStats.avgMs,
          getVisibleNodesLastResultCount: visibleStats.lastCallCount,
        });
      }

      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [visible]);

  // Zero DOM output (and zero rAF work above) when hidden
  if (!visible) return null;

  const {
    fps, rollingFps, frameTimeMs, heapUsedMB, heapLimitMB, nodeCount, edgeCount, drawCalls,
    enrichNodeCallsPerSec, enrichNodeAvgMs,
    getVisibleNodesCallsPerSec, getVisibleNodesLastResultCount,
  } = metrics;

  const fpsClr = fpsColor(rollingFps);
  const heapClr =
    heapUsedMB != null && heapLimitMB != null
      ? heapColor(heapUsedMB, heapLimitMB)
      : "#64748b";

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>Performance</div>

      <div style={rowStyle}>
        <span style={labelStyle}>FPS cur / avg</span>
        <span style={{ color: fpsClr, fontWeight: 600 }}>{fps} / {rollingFps}</span>
      </div>

      <div style={rowStyle}>
        <span style={labelStyle}>Frame time</span>
        <span>{frameTimeMs} ms</span>
      </div>

      <div style={rowStyle}>
        <span style={labelStyle}>JS heap</span>
        <span style={{ color: heapClr }}>
          {heapUsedMB != null ? `${heapUsedMB} / ${heapLimitMB ?? "—"} MB` : "—"}
        </span>
      </div>

      <div style={dividerStyle} />

      <div style={rowStyle}>
        <span style={labelStyle}>2D nodes</span>
        <span>{nodeCount}</span>
      </div>

      <div style={rowStyle}>
        <span style={labelStyle}>2D edges</span>
        <span>{edgeCount}</span>
      </div>

      <div style={rowStyle}>
        <span style={labelStyle}>3D draw calls</span>
        <span style={drawCalls != null ? undefined : dimStyle}>
          {drawCalls ?? "—"}
        </span>
      </div>

      <div style={rowStyle}>
        <span style={labelStyle}>enrichNode/s</span>
        <span>{enrichNodeCallsPerSec}</span>
      </div>

      <div style={rowStyle}>
        <span style={labelStyle}>enrichNode avg</span>
        <span style={{ color: avgMsColor(enrichNodeAvgMs) }}>
          {enrichNodeAvgMs.toFixed(2)} ms
        </span>
      </div>

      <div style={rowStyle}>
        <span style={labelStyle}>visibleNodes/s</span>
        <span>
          {getVisibleNodesCallsPerSec}{" "}
          <span style={dimStyle}>({getVisibleNodesLastResultCount})</span>
        </span>
      </div>
    </div>
  );
}
