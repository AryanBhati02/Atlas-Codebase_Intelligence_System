





import React, { useMemo, useCallback, useRef, useState, useEffect, lazy, Suspense } from "react";
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
import { Layers } from "lucide-react";
import { useAppStore } from "../../store/appStore";
import { getFileContent, explainFile, getFunctionGraph } from "../../api/api";
import { GraphToolbar, type LayoutMode } from "../graph/GraphToolbar";
import { FunctionGraph } from "../graph/FunctionGraph";
import { GitTimeline } from "../graph/GitTimeline";

const Graph3DView = lazy(() =>
  import("./Graph3DView").then((m) => ({ default: m.Graph3DView }))
);


class Graph3DErrorBoundary extends React.Component<
  { children: React.ReactNode; onFallback: () => void },
  { hasError: boolean }
> {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(err: Error) { console.error("3D View crashed:", err); }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full gap-3">
          <p className="text-xs text-red-400/80">3D view encountered an error</p>
          <button
            onClick={() => { this.setState({ hasError: false }); this.props.onFallback(); }}
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

      { }
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
        { }
        <div
          className="inline-block mr-1.5 rounded-full"
          style={{
            width: 5,
            height: 5,
            backgroundColor: data.isDead ? "#475569" : color,
            boxShadow: data.isDead ? "none" : `0 0 6px ${color}50`,
          }}
        />
        <span style={{ opacity: data.isDimmed ? 0.5 : 1 }}>
          {data.label}
        </span>
        {data.isDead && (
          <span className="ml-1 text-[7px] uppercase tracking-widest font-semibold" style={{ color: "var(--text-muted)" }}>
            dead
          </span>
        )}
        {data.coveragePct !== null && (
          <span className={`ml-1 text-[7px] font-semibold ${getCoverageClass(data.coveragePct)}`}>
            {data.coveragePct}%
          </span>
        )}
        {data.commentCount > 0 && (
          <span className="ml-1 w-1.5 h-1.5 rounded-full bg-accent-purple/60 inline-block"
            title={`${data.commentCount} comment${data.commentCount > 1 ? 's' : ''}`}
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


function hexToRgb(hex: string): string {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result
    ? `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}`
    : "124, 110, 224";
}



function applyLayout(nodes: Node[], edges: Edge[], mode: LayoutMode): Node[] {
  const count = nodes.length;
  if (count === 0) return nodes;

  switch (mode) {
    case "hierarchical": {
      const inDegree = new Map<string, number>();
      nodes.forEach((n) => inDegree.set(n.id, 0));
      edges.forEach((e) => inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1));

      const sorted = [...nodes].sort(
        (a, b) => (inDegree.get(a.id) || 0) - (inDegree.get(b.id) || 0)
      );

      const cols = Math.max(Math.ceil(Math.sqrt(count) * 1.4), 3);
      return sorted.map((n, i) => ({
        ...n,
        position: {
          x: (i % cols) * 190,
          y: Math.floor(i / cols) * 120,
        },
      }));
    }

    case "radial": {
      const cx = 400, cy = 400;
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

    case "layered": {
      const groups: Record<string, Node[]> = {};
      nodes.forEach((n) => {
        const lang = n.data?.language || "Other";
        if (!groups[lang]) groups[lang] = [];
        groups[lang].push(n);
      });

      const result: Node[] = [];
      let yOffset = 0;
      Object.values(groups).forEach((group) => {
        group.forEach((n, i) => {
          result.push({ ...n, position: { x: i * 190, y: yOffset } });
        });
        yOffset += 130;
      });
      return result;
    }

    default: {

      const cols = Math.ceil(Math.sqrt(count));
      const seed = 42;
      return nodes.map((n, i) => {
        const jx = Math.sin(seed + i * 7.3) * 30;
        const jy = Math.cos(seed + i * 5.1) * 20;
        return {
          ...n,
          position: {
            x: (i % cols) * 190 + jx,
            y: Math.floor(i / cols) * 120 + jy,
          },
        };
      });
    }
  }
}



function getConnectedNodeIds(nodeId: string, edges: Edge[]): Set<string> {
  const connected = new Set<string>();
  connected.add(nodeId);
  edges.forEach((e) => {
    if (e.source === nodeId) connected.add(e.target);
    if (e.target === nodeId) connected.add(e.source);
  });
  return connected;
}



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
  } = useAppStore();

  const [heatmapOn, setHeatmapOn] = useState(false);
  const [layout, setLayout] = useState<LayoutMode>("force");
  const lastClickRef = useRef<{ id: string; time: number }>({ id: "", time: 0 });
  const { fitView } = useReactFlow();


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


  const { initialNodes, initialEdges } = useMemo(() => {
    if (!graphData) return { initialNodes: [], initialEdges: [] };

    let nodes: Node[] = graphData.nodes.map((n) => ({
      id: n.id,
      type: "custom",
      position: { x: 0, y: 0 },
      data: {
        label: n.label,
        language: n.language,
        complexity: n.complexity_score,
        selected: n.id === selectedFile,
        isDead: deadFilePaths.has(n.id),
        isDimmed: connectedIds ? !connectedIds.has(n.id) : false,
        heatmapOn,
        isHighlighted: highlightedFiles.has(n.id),
        coveragePct: showCoverage && coverageData?.coverage?.[n.id] != null
          ? coverageData.coverage[n.id]
          : null,
        commentCount: commentCounts[n.id] || 0,
      },
    }));

    const edges: Edge[] = graphData.edges
      .filter((e) => !(showDeadCode && deadFilePaths.has(e.target)))
      .map((e) => {
        const isConnected =
          selectedFile && (e.source === selectedFile || e.target === selectedFile);
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          animated: !!isConnected,
          style: {
            stroke: isConnected
              ? "rgba(246, 196, 69, 0.3)"
              : heatmapOn
                ? "rgba(245, 158, 11, 0.1)"
                : "rgba(124, 110, 224, 0.1)",
            strokeWidth: isConnected ? 2 : 1,
            opacity: connectedIds && !isConnected ? 0.2 : 1,
            transition: "all 0.5s ease",
          },
        };
      });

    nodes = applyLayout(nodes, edges, layout);
    return { initialNodes: nodes, initialEdges: edges };
  }, [graphData, selectedFile, deadFilePaths, connectedIds, heatmapOn, showDeadCode, layout, highlightedFiles, showCoverage, coverageData, commentCounts]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);


  useEffect(() => {
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        data: {
          ...n.data,
          selected: n.id === selectedFile,
          isDead: deadFilePaths.has(n.id),
          isDimmed: connectedIds ? !connectedIds.has(n.id) : false,
          heatmapOn,
          isHighlighted: highlightedFiles.has(n.id),
          coveragePct: showCoverage && coverageData?.coverage?.[n.id] != null
            ? coverageData.coverage[n.id]
            : null,
          commentCount: commentCounts[n.id] || 0,
        },
      }))
    );
  }, [selectedFile, setNodes, deadFilePaths, connectedIds, heatmapOn, highlightedFiles, showCoverage, coverageData, commentCounts]);


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
      } catch { }
      try {
        setAILoading(true);
        const ai = await explainFile(sessionId, node.id);
        setAIExplanation(ai.explanation, ai.source);
      } catch { }
      finally { setAILoading(false); }
    },
    [sessionId, setSelectedFile, setFileContent, setAIExplanation, setAILoading, setFunctionGraphData, setFunctionGraphLoading]
  );


  const onPaneClick = useCallback(() => {
    setSelectedFile(null);
  }, [setSelectedFile]);

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center"
        >
          <div className="w-16 h-16 rounded-2xl mx-auto mb-4 flex items-center justify-center"
            style={{
              background: "var(--gradient-brand-subtle)",
              border: "1px solid var(--accent-purple-border)",
            }}
          >
            <Layers className="w-6 h-6 text-accent-purple/50" />
          </div>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>No graph data available</p>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="relative w-full h-full flex flex-col" style={{ zIndex: 1 }}>
      <div className="relative flex-1 min-h-0 w-full">
        {/* Main Graph Area */}
        {show3DGraph ? (
          <Graph3DErrorBoundary onFallback={toggle3DGraph}>
            <Suspense fallback={
              <div className="flex items-center justify-center h-full">
                <div className="analyzing-spinner" />
              </div>
            }>
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
            defaultEdgeOptions={{
              type: "smoothstep",
              animated: false,
            }}
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

        { }
        <GraphToolbar
          heatmapOn={heatmapOn}
          onToggleHeatmap={() => setHeatmapOn(!heatmapOn)}
          layout={layout}
          onChangeLayout={setLayout}
          onFitView={() => fitView({ padding: 0.3, duration: 400 })}
        />

        { }
        {!show3DGraph && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="absolute bottom-3 left-3 z-10 flex items-center gap-2 px-2.5 py-1
          rounded-lg backdrop-blur-sm"
            style={{ background: "var(--bg-overlay)", border: "1px solid var(--border-subtle)" }}
          >
            <span className="text-[9px] font-medium" style={{ color: "var(--text-muted)" }}>
              {graphData.nodes.length} nodes · {graphData.edges.length} edges
            </span>
          </motion.div>
        )}

        { }
        <GitTimeline />
      </div>

      {/* Function Graph takes bottom space if open */}
      <FunctionGraph />
    </div>
  );
}


export function GraphView() {
  return (
    <ReactFlowProvider>
      <GraphViewInner />
    </ReactFlowProvider>
  );
}
