import React, {
  useMemo,
  useCallback,
  useRef,
  useState,
  useEffect,
  lazy,
  Suspense,
} from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  type Node,
  type Edge,
  Handle,
  Position,
} from "reactflow";
import "reactflow/dist/style.css";
import { motion } from "framer-motion";
import { Layers, Loader2 } from "lucide-react";
import { useAppStore } from "../../store/appStore";
import { getFileContent, explainFile, getFunctionGraph } from "../../api/api";
import { GraphToolbar, type LayoutMode } from "../graph/GraphToolbar";
import { FunctionGraph } from "../graph/FunctionGraph";
import { GitTimeline } from "../graph/GitTimeline";
import { useGraphLayout } from "../../hooks/useGraphLayout";
import type { CoverageResponse } from "../../types";

const Graph3DView = lazy(() =>
  import("./Graph3DView").then((m) => ({ default: m.Graph3DView }))
);

// ---------------------------------------------------------------------------
// Error boundary for 3D view
// ---------------------------------------------------------------------------

class Graph3DErrorBoundary extends React.Component<
  { children: React.ReactNode; onFallback: () => void },
  { hasError: boolean }
> {
  state = { hasError: false };
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  componentDidCatch(err: Error) {
    console.error("3D View crashed:", err);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full gap-3">
          <p className="text-xs text-red-400/80">3D view encountered an error</p>
          <button
            onClick={() => {
              this.setState({ hasError: false });
              this.props.onFallback();
            }}
            className="px-3 py-1.5 rounded-lg text-[10px] font-medium transition-colors"
            style={{
              color: "var(--text-secondary)",
              background: "var(--bg-input)",
              border: "1px solid var(--border-light)",
            }}
          >
            Switch to 2D
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// ---------------------------------------------------------------------------
// Color helpers
// ---------------------------------------------------------------------------

const LANG_COLORS: Record<string, string> = {
  Python: "#3b82f6",
  JavaScript: "#f59e0b",
  TypeScript: "#38bdf8",
  Java: "#f97316",
  Go: "#06b6d4",
  Rust: "#ef4444",
  "C++": "#ec4899",
  C: "#94a3b8",
  HTML: "#f43f5e",
  CSS: "#8b5cf6",
  JSON: "#10b981",
  Markdown: "#6b7280",
  YAML: "#84cc16",
  Shell: "#22c55e",
  Ruby: "#ef4444",
  PHP: "#818cf8",
};

function getNodeColor(language: string | null): string {
  if (!language) return "#7c6ee0";
  return LANG_COLORS[language] || "#7c6ee0";
}

function getHeatmapColor(complexity: number): string {
  if (complexity < 0.3) return "#22c55e";
  if (complexity < 0.5) return "#84cc16";
  if (complexity < 0.7) return "#f59e0b";
  return "#ef4444";
}

function getCoverageClass(pct: number): string {
  if (pct >= 80) return "text-emerald-400";
  if (pct >= 50) return "text-amber-400";
  return "text-red-400";
}

function hexToRgb(hex: string): string {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result
    ? `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}`
    : "124, 110, 224";
}

// ---------------------------------------------------------------------------
// Sync radial layout (dagre doesn't support radial, keep this as fallback)
// ---------------------------------------------------------------------------

function applyRadialLayout(nodes: Node[]): Node[] {
  const cx = 400,
    cy = 400;
  return nodes.map((n, i) => {
    if (i === 0) return { ...n, position: { x: cx, y: cy } };
    const ring = Math.ceil(i / 8);
    const angle = ((i % 8) / 8) * Math.PI * 2 + ring * 0.4;
    const radius = ring * 150;
    return {
      ...n,
      position: {
        x: cx + Math.cos(angle) * radius,
        y: cy + Math.sin(angle) * radius,
      },
    };
  });
}

// ---------------------------------------------------------------------------
// Progressive node reveal — adds nodes in batches so the graph "builds in"
// Returns a cancel function to stop pending timeouts.
// ---------------------------------------------------------------------------

function scheduleProgressiveBuild(
  nodes: Node[],
  edges: Edge[],
  setNodes: (updater: (prev: Node[]) => Node[]) => void,
  setEdges: (edges: Edge[]) => void,
  onComplete: () => void,
  onBatchAdded: (loaded: number, total: number) => void
): () => void {
  const BATCH = 30;
  const DELAY = 60; // ms between batches
  const timers: ReturnType<typeof setTimeout>[] = [];
  const total = nodes.length;

  setEdges(edges);

  const batchCount = Math.ceil(total / BATCH);

  for (let b = 0; b < batchCount; b++) {
    const start = b * BATCH;
    const batch = nodes.slice(start, start + BATCH);
    const loaded = Math.min(start + BATCH, total);

    const t = setTimeout(() => {
      const invisible = batch.map((n) => ({
        ...n,
        style: { ...n.style, opacity: 0 },
      }));

      setNodes((prev) =>
        b === 0 ? invisible : [...prev, ...invisible]
      );

      requestAnimationFrame(() => {
        setNodes((prev) =>
          prev.map((n) => {
            if (invisible.some((iv) => iv.id === n.id)) {
              return {
                ...n,
                style: { opacity: 1, transition: "opacity 0.2s ease" },
              };
            }
            return n;
          })
        );
      });

      onBatchAdded(loaded, total);

      if (b === batchCount - 1) {
        onComplete();
      }
    }, b * DELAY);

    timers.push(t);
  }

  return () => timers.forEach(clearTimeout);
}

// ---------------------------------------------------------------------------
// Connected-node helper
// ---------------------------------------------------------------------------

function getConnectedNodeIds(nodeId: string, edges: Edge[]): Set<string> {
  const connected = new Set<string>([nodeId]);
  for (const e of edges) {
    if (e.source === nodeId) connected.add(e.target);
    if (e.target === nodeId) connected.add(e.source);
  }
  return connected;
}

// ---------------------------------------------------------------------------
// Custom node component
// ---------------------------------------------------------------------------

const CustomNode = React.memo(function CustomNode({
  data,
}: {
  data: {
    label: string;
    language: string | null;
    complexity: number;
    selected: boolean;
    isDead: boolean;
    isDimmed: boolean;
    heatmapOn: boolean;
    isHighlighted: boolean;
    coveragePct: number | null;
    commentCount: number;
  };
}) {
  const color = data.heatmapOn
    ? getHeatmapColor(data.complexity)
    : getNodeColor(data.language);

  const glowIntensity = data.selected ? 0.25 : data.isHighlighted ? 0.18 : 0.06;
  const glowSize = data.selected ? 40 : data.isHighlighted ? 28 : 12;

  return (
    <>
      <Handle
        type="target"
        position={Position.Top}
        style={{
          background: color,
          border: "none",
          width: 5,
          height: 5,
          opacity: data.isDimmed ? 0.3 : 0.7,
        }}
      />

      {data.selected && (
        <div
          style={{
            position: "absolute",
            inset: -20,
            borderRadius: "50%",
            background: `radial-gradient(circle, ${color}18 0%, transparent 70%)`,
            pointerEvents: "none",
            animation: "glow-pulse 3s ease-in-out infinite",
          }}
        />
      )}

      <div
        className={`graph-node ${data.selected ? "selected" : ""} ${data.isDead ? "dead-node" : ""} ${data.isDimmed ? "dimmed" : ""} ${data.isHighlighted ? "highlighted" : ""}`}
        style={{
          borderColor: data.isHighlighted
            ? "rgba(34, 211, 238, 0.3)"
            : data.selected
              ? `${color}80`
              : data.isDead
                ? "rgba(107, 114, 128, 0.15)"
                : `${color}18`,
          boxShadow: data.isDead
            ? "none"
            : `0 0 ${glowSize}px rgba(${hexToRgb(color)}, ${glowIntensity})`,
        }}
      >
        <div
          className="inline-block mr-1.5 rounded-full"
          style={{
            width: 5,
            height: 5,
            backgroundColor: data.isDead ? "#475569" : color,
            boxShadow: data.isDead ? "none" : `0 0 6px ${color}50`,
          }}
        />
        <span style={{ opacity: data.isDimmed ? 0.5 : 1 }}>{data.label}</span>
        {data.isDead && (
          <span
            className="ml-1 text-[7px] uppercase tracking-widest font-semibold"
            style={{ color: "var(--text-muted)" }}
          >
            dead
          </span>
        )}
        {data.coveragePct !== null && (
          <span
            className={`ml-1 text-[7px] font-semibold ${getCoverageClass(data.coveragePct)}`}
          >
            {data.coveragePct}%
          </span>
        )}
        {data.commentCount > 0 && (
          <span
            className="ml-1 w-1.5 h-1.5 rounded-full bg-accent-purple/60 inline-block"
            title={`${data.commentCount} comment${data.commentCount > 1 ? "s" : ""}`}
          />
        )}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        style={{
          background: color,
          border: "none",
          width: 5,
          height: 5,
          opacity: data.isDimmed ? 0.3 : 0.7,
        }}
      />
    </>
  );
});

const nodeTypes = { custom: CustomNode };

// ---------------------------------------------------------------------------
// Visual state snapshot — kept in a ref so async layout callbacks always read
// the freshest values without stale-closure issues.
// ---------------------------------------------------------------------------

interface VisualState {
  selectedFile: string | null;
  deadFilePaths: Set<string>;
  connectedIds: Set<string> | null;
  heatmapOn: boolean;
  highlightedFiles: Set<string>;
  showCoverage: boolean;
  coverageData: CoverageResponse | null;
  commentCounts: Record<string, number>;
  showDeadCode: boolean;
}

function enrichNode(node: Node, v: VisualState): Node {
  return {
    ...node,
    data: {
      ...node.data,
      selected: node.id === v.selectedFile,
      isDead: v.deadFilePaths.has(node.id),
      isDimmed: v.connectedIds ? !v.connectedIds.has(node.id) : false,
      heatmapOn: v.heatmapOn,
      isHighlighted: v.highlightedFiles.has(node.id),
      coveragePct:
        v.showCoverage && v.coverageData?.coverage?.[node.id] != null
          ? v.coverageData.coverage[node.id]
          : null,
      commentCount: v.commentCounts[node.id] || 0,
    },
  };
}

function styledEdge(edge: Edge, v: VisualState): Edge {
  const isConnected =
    v.selectedFile &&
    (edge.source === v.selectedFile || edge.target === v.selectedFile);
  const deadTarget = v.showDeadCode && v.deadFilePaths.has(edge.target);
  return {
    ...edge,
    type: "smoothstep",
    hidden: deadTarget,
    animated: !!isConnected,
    style: {
      stroke: isConnected
        ? "rgba(246, 196, 69, 0.3)"
        : v.heatmapOn
          ? "rgba(245, 158, 11, 0.1)"
          : "rgba(124, 110, 224, 0.1)",
      strokeWidth: isConnected ? 2 : 1,
      opacity: v.connectedIds && !isConnected ? 0.2 : 1,
      transition: "all 0.5s ease",
    },
  };
}

// ---------------------------------------------------------------------------
// Main graph component (inner — needs ReactFlowProvider above it)
// ---------------------------------------------------------------------------

function GraphViewInner() {
  const {
    graphData,
    selectedFile,
    sessionId,
    setSelectedFile,
    setFileContent,
    setAIExplanation,
    setAILoading,
    showDeadCode,
    deadCodeData,
    setFunctionGraphData,
    setFunctionGraphLoading,
    show3DGraph,
    toggle3DGraph,
    highlightedFiles,
    showCoverage,
    coverageData,
    commentCounts,
    isAnalyzing,
    analysisProgress,
  } = useAppStore();

  const [heatmapOn, setHeatmapOn] = useState(false);
  const [layout, setLayout] = useState<LayoutMode>("force");
  const [buildText, setBuildText] = useState<string | null>(null);

  const lastClickRef = useRef<{ id: string; time: number }>({ id: "", time: 0 });
  const cleanupRef = useRef<(() => void) | null>(null);

  const { fitView } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const { computeLayout, isComputing } = useGraphLayout();

  // -------------------------------------------------------------------------
  // Derived visual state
  // -------------------------------------------------------------------------

  const deadFilePaths = useMemo(() => {
    if (!showDeadCode || !deadCodeData) return new Set<string>();
    return new Set(deadCodeData.dead_files.map((d) => d.path));
  }, [showDeadCode, deadCodeData]);

  const connectedIds = useMemo(() => {
    if (!selectedFile || !graphData) return null;
    return getConnectedNodeIds(
      selectedFile,
      graphData.edges.map((e) => ({ id: e.id, source: e.source, target: e.target }))
    );
  }, [selectedFile, graphData]);

  // Keep a mutable ref to the latest visual state so async callbacks are never stale.
  const visualRef = useRef<VisualState>({
    selectedFile,
    deadFilePaths,
    connectedIds,
    heatmapOn,
    highlightedFiles,
    showCoverage,
    coverageData: coverageData ?? null,
    commentCounts,
    showDeadCode,
  });
  visualRef.current = {
    selectedFile,
    deadFilePaths,
    connectedIds,
    heatmapOn,
    highlightedFiles,
    showCoverage,
    coverageData: coverageData ?? null,
    commentCounts,
    showDeadCode,
  };

  // -------------------------------------------------------------------------
  // Structural raw data (no positions, no visual state) — triggers layout
  // -------------------------------------------------------------------------

  const rawNodes = useMemo((): Node[] => {
    if (!graphData) return [];
    return graphData.nodes.map((n) => ({
      id: n.id,
      type: "custom",
      position: { x: 0, y: 0 },
      data: {
        label: n.label,
        language: n.language,
        complexity: n.complexity_score,
        // Visual fields will be applied in layout callback via visualRef
        selected: false,
        isDead: false,
        isDimmed: false,
        heatmapOn: false,
        isHighlighted: false,
        coveragePct: null,
        commentCount: 0,
      },
    }));
  }, [graphData]);

  const rawEdges = useMemo((): Edge[] => {
    if (!graphData) return [];
    return graphData.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
    }));
  }, [graphData]);

  // -------------------------------------------------------------------------
  // Layout effect — re-runs only when graph structure or layout mode changes
  // -------------------------------------------------------------------------

  useEffect(() => {
    // Cancel any previous progressive build
    if (cleanupRef.current) {
      cleanupRef.current();
      cleanupRef.current = null;
    }
    setBuildText(null);

    if (rawNodes.length === 0) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const v = visualRef.current;

    function applyAndBuild(positioned: Node[]) {
      const enriched = positioned.map((n) => enrichNode(n, v));
      const processedEdges = rawEdges.map((e) => styledEdge(e, v));

      const cancel = scheduleProgressiveBuild(
        enriched,
        processedEdges,
        setNodes,
        setEdges,
        () => {
          setBuildText(null);
          setTimeout(() => fitView({ padding: 0.3, duration: 400 }), 50);
        },
        (loaded, total) => {
          if (loaded < total) {
            setBuildText(`Loading: ${loaded} / ${total} nodes`);
          }
        }
      );
      cleanupRef.current = cancel;
    }

    if (layout === "radial") {
      applyAndBuild(applyRadialLayout(rawNodes));
      return;
    }

    const direction = layout === "layered" ? "LR" : "TB";

    computeLayout(rawNodes, rawEdges, direction)
      .then(({ nodes: positioned }) => {
        applyAndBuild(positioned);
      })
      .catch((err: Error) => {
        const msg = err.message;
        if (!msg.includes("Superseded") && !msg.includes("unmounted")) {
          console.error("[GraphLayout]", msg);
        }
      });

    return () => {
      if (cleanupRef.current) {
        cleanupRef.current();
        cleanupRef.current = null;
      }
    };
  }, [rawNodes, rawEdges, layout, computeLayout, fitView, setNodes, setEdges]);

  // -------------------------------------------------------------------------
  // Visual effect — fast updates that must not re-trigger layout
  // -------------------------------------------------------------------------

  useEffect(() => {
    if (nodes.length === 0) return;
    const v = visualRef.current;
    setNodes((nds) => nds.map((n) => enrichNode(n, v)));
    setEdges((eds) => eds.map((e) => styledEdge(e, v)));
  }, [
    selectedFile,
    deadFilePaths,
    connectedIds,
    heatmapOn,
    highlightedFiles,
    showCoverage,
    coverageData,
    commentCounts,
    showDeadCode,
    setNodes,
    setEdges,
    // nodes.length intentionally excluded — we read from state via updater fn
  ]);

  // -------------------------------------------------------------------------
  // Command palette events
  // -------------------------------------------------------------------------

  useEffect(() => {
    const onToggleHeatmap = () => setHeatmapOn((v) => !v);
    const onFitView = () => fitView({ padding: 0.3, duration: 400 });
    const onChangeLayout = (e: Event) => {
      const detail = (e as CustomEvent).detail as LayoutMode;
      if (detail) setLayout(detail);
    };
    const onToggleDeadCode = () => {
      window.dispatchEvent(new CustomEvent("cmd:dead-code-toggle-internal"));
    };
    const onFocusNode = (e: Event) => {
      const nodeId = (e as CustomEvent).detail as string;
      if (nodeId) {
        setSelectedFile(nodeId);
        setTimeout(() => fitView({ padding: 0.3, duration: 400 }), 100);
      }
    };

    window.addEventListener("cmd:toggle-heatmap", onToggleHeatmap);
    window.addEventListener("cmd:fit-view", onFitView);
    window.addEventListener("cmd:change-layout", onChangeLayout);
    window.addEventListener("cmd:toggle-dead-code", onToggleDeadCode);
    window.addEventListener("cmd:focus-node", onFocusNode);

    return () => {
      window.removeEventListener("cmd:toggle-heatmap", onToggleHeatmap);
      window.removeEventListener("cmd:fit-view", onFitView);
      window.removeEventListener("cmd:change-layout", onChangeLayout);
      window.removeEventListener("cmd:toggle-dead-code", onToggleDeadCode);
      window.removeEventListener("cmd:focus-node", onFocusNode);
    };
  }, [fitView, setSelectedFile]);

  // -------------------------------------------------------------------------
  // Node interaction
  // -------------------------------------------------------------------------

  const onNodeClick = useCallback(
    async (_: React.MouseEvent, node: Node) => {
      if (!sessionId) return;
      const now = Date.now();

      if (
        lastClickRef.current.id === node.id &&
        now - lastClickRef.current.time < 400
      ) {
        setFunctionGraphLoading(true);
        try {
          const fg = await getFunctionGraph(sessionId, node.id);
          setFunctionGraphData(fg, node.id);
        } catch {
          setFunctionGraphLoading(false);
        }
        lastClickRef.current = { id: "", time: 0 };
        return;
      }

      lastClickRef.current = { id: node.id, time: now };

      setSelectedFile(node.id);
      try {
        const content = await getFileContent(sessionId, node.id);
        setFileContent(content);
      } catch {
        /* ignore */
      }
      try {
        setAILoading(true);
        const ai = await explainFile(sessionId, node.id);
        setAIExplanation(ai.explanation, ai.source);
      } catch {
        /* ignore */
      } finally {
        setAILoading(false);
      }
    },
    [
      sessionId,
      setSelectedFile,
      setFileContent,
      setAIExplanation,
      setAILoading,
      setFunctionGraphData,
      setFunctionGraphLoading,
    ]
  );

  const onPaneClick = useCallback(() => {
    setSelectedFile(null);
  }, [setSelectedFile]);

  // -------------------------------------------------------------------------
  // Empty state
  // -------------------------------------------------------------------------

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center"
        >
          <div
            className="w-16 h-16 rounded-2xl mx-auto mb-4 flex items-center justify-center"
            style={{
              background: "var(--gradient-brand-subtle)",
              border: "1px solid var(--accent-purple-border)",
            }}
          >
            <Layers className="w-6 h-6 text-accent-purple/50" />
          </div>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            No graph data available
          </p>
        </motion.div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="relative w-full h-full flex flex-col" style={{ zIndex: 1 }}>
      <div className="relative flex-1 min-h-0 w-full">
        {/* Computing layout overlay */}
        {isComputing && (
          <div
            className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-2 backdrop-blur-sm"
            style={{ background: "var(--bg-base)60" }}
          >
            <Loader2
              className="w-6 h-6 animate-spin"
              style={{ color: "var(--accent-purple)" }}
            />
            <p className="text-[11px] font-medium" style={{ color: "var(--text-secondary)" }}>
              Computing layout…
            </p>
          </div>
        )}

        {/* Progressive build counter */}
        {buildText && !isComputing && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="absolute top-3 left-1/2 -translate-x-1/2 z-20 px-3 py-1 rounded-full text-[10px] font-medium"
            style={{
              background: "var(--bg-overlay)",
              border: "1px solid var(--border-subtle)",
              color: "var(--text-secondary)",
            }}
          >
            {buildText}
          </motion.div>
        )}

        {/* Analysis file-parse counter (shown during re-analysis) */}
        {isAnalyzing &&
          analysisProgress?.stage === "parsing" &&
          analysisProgress.total > 0 && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="absolute top-3 left-1/2 -translate-x-1/2 z-20 px-3 py-1 rounded-full text-[10px] font-medium"
              style={{
                background: "var(--bg-overlay)",
                border: "1px solid var(--border-subtle)",
                color: "var(--accent-cyan)",
              }}
            >
              Parsing: {analysisProgress.current} of {analysisProgress.total} files
            </motion.div>
          )}

        {/* Main graph area */}
        {show3DGraph ? (
          <Graph3DErrorBoundary onFallback={toggle3DGraph}>
            <Suspense
              fallback={
                <div className="flex items-center justify-center h-full">
                  <div className="analyzing-spinner" />
                </div>
              }
            >
              <Graph3DView />
            </Suspense>
          </Graph3DErrorBoundary>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            minZoom={0.1}
            maxZoom={2.5}
            proOptions={{ hideAttribution: true }}
            defaultEdgeOptions={{ type: "smoothstep", animated: false }}
            nodesDraggable={!isComputing}
            nodesConnectable={false}
            elementsSelectable={!isComputing}
          >
            <Background color="rgba(124, 110, 224, 0.02)" gap={24} />
            <Controls showInteractive={false} style={{ marginBottom: 36 }} />
            <MiniMap
              nodeColor={(n) => {
                if (n.data?.isDead) return "#374151";
                if (heatmapOn) return getHeatmapColor(n.data?.complexity || 0);
                return getNodeColor(n.data?.language);
              }}
              maskColor="var(--minimap-mask)"
              style={{ borderRadius: 10 }}
            />
          </ReactFlow>
        )}

        <GraphToolbar
          heatmapOn={heatmapOn}
          onToggleHeatmap={() => setHeatmapOn(!heatmapOn)}
          layout={layout}
          onChangeLayout={setLayout}
          onFitView={() => fitView({ padding: 0.3, duration: 400 })}
        />

        {!show3DGraph && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="absolute bottom-3 left-3 z-10 flex items-center gap-2 px-2.5 py-1
              rounded-lg backdrop-blur-sm"
            style={{
              background: "var(--bg-overlay)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            <span
              className="text-[9px] font-medium"
              style={{ color: "var(--text-muted)" }}
            >
              {graphData.nodes.length} nodes · {graphData.edges.length} edges
            </span>
          </motion.div>
        )}

        <GitTimeline />
      </div>

      <FunctionGraph />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public export — wraps inner component with ReactFlowProvider
// ---------------------------------------------------------------------------

export function GraphView() {
  return (
    <ReactFlowProvider>
      <GraphViewInner />
    </ReactFlowProvider>
  );
}
