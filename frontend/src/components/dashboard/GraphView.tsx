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
  type Viewport,
  Handle,
  Position,
} from "reactflow";
import "reactflow/dist/style.css";
import { motion, AnimatePresence } from "framer-motion";
import { Layers, Loader2, Search, X, Navigation } from "lucide-react";
import { useAppStore } from "../../store/appStore";
import { getFileContent, explainFile, getFunctionGraph } from "../../api/api";
import { GraphToolbar, type LayoutMode } from "../graph/GraphToolbar";
import { FunctionGraph } from "../graph/FunctionGraph";
import { GitTimeline } from "../graph/GitTimeline";
import { useGraphLayout } from "../../hooks/useGraphLayout";
import { ClusterNodeComponent } from "./ClusterNode";
import {
  clusterByDirectory,
  expandCluster,
  collapseCluster,
  getVisibleNodes,
  type AppNode,
  type AppNodeData,
  type AnyNode,
  type ClusterNode,
  type ClusteredGraph,
} from "../../utils/graphClustering";
import { createProfiler } from "../../lib/perfProfiler";
import type { CoverageResponse } from "../../types";

export const enrichNodeProfiler = createProfiler("enrichNode");

const Graph3DView = lazy(() =>
  import("./Graph3DView").then((m) => ({ default: m.Graph3DView }))
);

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
    ? `${parseInt(result[1] ?? "7c", 16)}, ${parseInt(result[2] ?? "6e", 16)}, ${parseInt(result[3] ?? "e0", 16)}`
    : "124, 110, 224";
}

function applyRadialLayout(nodes: Node[]): Node[] {
  const cx = 400, cy = 400;
  return nodes.map((n, i) => {
    if (i === 0) return { ...n, position: { x: cx, y: cy } };
    const ring = Math.ceil(i / 8);
    const angle = ((i % 8) / 8) * Math.PI * 2 + ring * 0.4;
    const radius = ring * 150;
    return { ...n, position: { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius } };
  });
}

function scheduleProgressiveBuild(
  nodes: Node[],
  edges: Edge[],
  setNodes: (updater: (prev: Node[]) => Node[]) => void,
  setEdges: (edges: Edge[]) => void,
  onComplete: () => void,
  onBatchAdded: (loaded: number, total: number) => void
): () => void {
  const BATCH = 30;
  const DELAY = 60;
  const timers: ReturnType<typeof setTimeout>[] = [];
  const total = nodes.length;

  setEdges(edges);

  const batchCount = Math.ceil(total / BATCH);

  for (let b = 0; b < batchCount; b++) {
    const start = b * BATCH;
    const batch = nodes.slice(start, start + BATCH);
    const loaded = Math.min(start + BATCH, total);

    const t = setTimeout(() => {
      const invisible = batch.map((n) => ({ ...n, style: { ...n.style, opacity: 0 } }));
      setNodes((prev) => (b === 0 ? invisible : [...prev, ...invisible]));

      requestAnimationFrame(() => {
        setNodes((prev) =>
          prev.map((n) => {
            if (invisible.some((iv) => iv.id === n.id)) {
              return { ...n, style: { opacity: 1, transition: "opacity 0.2s ease" } };
            }
            return n;
          })
        );
      });

      onBatchAdded(loaded, total);
      if (b === batchCount - 1) onComplete();
    }, b * DELAY);

    timers.push(t);
  }

  return () => timers.forEach(clearTimeout);
}

function getConnectedNodeIds(nodeId: string, edges: Edge[]): Set<string> {
  const connected = new Set<string>([nodeId]);
  for (const e of edges) {
    if (e.source === nodeId) connected.add(e.target);
    if (e.target === nodeId) connected.add(e.source);
  }
  return connected;
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
        style={{ background: color, border: "none", width: 5, height: 5, opacity: data.isDimmed ? 0.3 : 0.7 }}
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
            ? "rgba(34, 211, 238, 0.5)"
            : data.selected
              ? `${color}99`
              : data.isDead
                ? "rgba(107, 114, 128, 0.15)"
                : `${color}44`,
          boxShadow: data.isDead
            ? "none"
            : `0 0 ${glowSize}px rgba(${hexToRgb(color)}, ${glowIntensity}), 0 1px 4px rgba(0,0,0,0.15)`,
          outline: data.isHighlighted ? "1.5px solid rgba(34, 211, 238, 0.4)" : "none",
          outlineOffset: 2,
        }}
      >
        <div
          className="inline-block mr-1.5 rounded-full"
          style={{
            width: 5, height: 5,
            backgroundColor: data.isDead ? "#475569" : color,
            boxShadow: data.isDead ? "none" : `0 0 6px ${color}50`,
          }}
        />
        <span style={{ opacity: data.isDimmed ? 0.4 : 1 }}>{data.label}</span>
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
          <span
            className="ml-1 w-1.5 h-1.5 rounded-full bg-accent-purple/60 inline-block"
            title={`${data.commentCount} comment${data.commentCount > 1 ? "s" : ""}`}
          />
        )}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        style={{ background: color, border: "none", width: 5, height: 5, opacity: data.isDimmed ? 0.3 : 0.7 }}
      />
    </>
  );
});

const nodeTypes = {
  custom: CustomNode,
  clusterNode: ClusterNodeComponent,
};

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
  searchMatchIds: Set<string>;
}

function enrichNode(node: Node, v: VisualState): Node {
  return enrichNodeProfiler.measure(() => {
    const hasSearch = v.searchMatchIds.size > 0;
    return {
      ...node,
      data: {
        ...node.data,
        selected: node.id === v.selectedFile,
        isDead: v.deadFilePaths.has(node.id),
        isDimmed: hasSearch
          ? !v.searchMatchIds.has(node.id)
          : v.connectedIds
            ? !v.connectedIds.has(node.id)
            : false,
        heatmapOn: v.heatmapOn,
        isHighlighted: hasSearch
          ? v.searchMatchIds.has(node.id)
          : v.highlightedFiles.has(node.id),
        coveragePct:
          v.showCoverage && v.coverageData?.coverage?.[node.id] != null
            ? v.coverageData.coverage[node.id]
            : null,
        commentCount: v.commentCounts[node.id] || 0,
      },
    };
  });
}

function styledEdge(edge: Edge, v: VisualState): Edge {
  const isConnected =
    v.selectedFile &&
    (edge.source === v.selectedFile || edge.target === v.selectedFile);
  const deadTarget = v.showDeadCode && v.deadFilePaths.has(edge.target);
  // Dim non-connected edges when a file is selected, but floor at 0.3 so they
  // remain perceptible.  The stroke itself already carries alpha; combining a
  // low-alpha stroke with a low opacity previously yielded ~4% effective alpha
  // on dark backgrounds, making edges render as completely invisible.
  const dimmed = v.connectedIds && !isConnected && v.searchMatchIds.size === 0;
  return {
    ...edge,
    type: "smoothstep",
    hidden: !!deadTarget,
    animated: !!isConnected,
    style: {
      stroke: isConnected
        ? "var(--edge-stroke-active)"
        : "var(--edge-stroke)",
      strokeWidth: isConnected ? 2 : 1,
      // Minimum opacity 0.3 — never fully invisible.
      opacity: dimmed ? 0.3 : 1,
      transition: "all 0.5s ease",
    },
  };
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
    isAnalyzing,
    analysisProgress,
    isChatPanelOpen,
    toggleChatPanel,
  } = useAppStore();

  const [heatmapOn, setHeatmapOn] = useState(false);
  const [layout, setLayout] = useState<LayoutMode>("force");
  const [buildText, setBuildText] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [matchingNodeIds, setMatchingNodeIds] = useState<Set<string>>(new Set());

  const lastClickRef = useRef<{ id: string; time: number }>({ id: "", time: 0 });
  const cleanupRef = useRef<(() => void) | null>(null);
  const allNodesRef = useRef<AnyNode[]>([]);
  const allEdgesRef = useRef<Edge[]>([]);
  const clusteredGraphRef = useRef<ClusteredGraph | null>(null);
  const viewportRef = useRef<Viewport>({ x: 0, y: 0, zoom: 1 });
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const viewportTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { fitView, setCenter } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const { computeLayout, isComputing } = useGraphLayout();

  const showToast = useCallback((message: string) => {
    setToast(message);
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToast(null), 5000);
  }, []);

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
    searchMatchIds: matchingNodeIds,
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
    searchMatchIds: matchingNodeIds,
  };

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

  const runLayoutAndBuild = useCallback(
    (displayNodes: AnyNode[], displayEdges: Edge[]) => {
      if (cleanupRef.current) {
        cleanupRef.current();
        cleanupRef.current = null;
      }
      setBuildText(null);

      const v = visualRef.current;

      function applyAndBuild(positioned: AnyNode[]) {
        allNodesRef.current = positioned;
        allEdgesRef.current = displayEdges;

        const viewport = viewportRef.current;
        const visible = getVisibleNodes(positioned, viewport, viewport.zoom);

        const enriched = visible.map((n) =>
          n.type === "clusterNode" ? n : enrichNode(n as Node, v)
        );
        const processedEdges = displayEdges.map((e) => styledEdge(e, v));

        const cancel = scheduleProgressiveBuild(
          enriched as Node[],
          processedEdges,
          setNodes,
          setEdges,
          () => {
            setBuildText(null);
            setTimeout(() => fitView({ padding: 0.3, duration: 400 }), 50);
          },
          (loaded, total) => {
            if (loaded < total) setBuildText(`Loading: ${loaded} / ${total} nodes`);
          }
        );
        cleanupRef.current = cancel;
      }

      computeLayout(displayNodes as Node[], displayEdges, layout)
        .then(({ nodes: positioned }) => applyAndBuild(positioned as AnyNode[]))
        .catch((err: Error) => {
          const msg = err.message;
          if (!msg.includes("Superseded") && !msg.includes("unmounted")) {
            console.error("[GraphLayout]", msg);
          }
        });
    },
    
    [layout, computeLayout, fitView, setNodes, setEdges]
  );

  useEffect(() => {
    if (cleanupRef.current) {
      cleanupRef.current();
      cleanupRef.current = null;
    }
    setBuildText(null);

    if (rawNodes.length === 0) {
      setNodes([]);
      setEdges([]);
      clusteredGraphRef.current = null;
      allNodesRef.current = [];
      allEdgesRef.current = [];
      return;
    }

    if (rawNodes.length <= 150) {
      
      clusteredGraphRef.current = null;
      runLayoutAndBuild(rawNodes as AnyNode[], rawEdges);
    } else if (rawNodes.length <= 600) {
      
      const clustered = clusterByDirectory(rawNodes as AppNode[], rawEdges);
      clusteredGraphRef.current = clustered;
      showToast(
        `Showing ${clustered.nodes.length} directory clusters — click any to expand.`
      );
      runLayoutAndBuild(clustered.nodes, clustered.edges);
    } else {
      
      const clustered = clusterByDirectory(rawNodes as AppNode[], rawEdges);
      const sorted = [...clustered.nodes].sort(
        (a, b) =>
          ((b as ClusterNode).data?.fileCount ?? 0) -
          ((a as ClusterNode).data?.fileCount ?? 0)
      );
      const top50 = sorted.slice(0, 50) as ClusterNode[];
      const top50Ids = new Set(top50.map((n) => n.id));
      const filteredEdges = clustered.edges.filter(
        (e) => top50Ids.has(e.source) && top50Ids.has(e.target)
      );
      clusteredGraphRef.current = { ...clustered, nodes: top50, edges: filteredEdges };
      showToast(
        `${rawNodes.length} files detected — showing 50 largest directory clusters.`
      );
      runLayoutAndBuild(top50, filteredEdges);
    }

    return () => {
      if (cleanupRef.current) {
        cleanupRef.current();
        cleanupRef.current = null;
      }
    };
  }, [rawNodes, rawEdges, runLayoutAndBuild, setNodes, setEdges, showToast]);

  useEffect(() => {
    const handler = (e: Event) => {
      const clusterId = (e as CustomEvent<string>).detail;
      const graph = clusteredGraphRef.current;
      if (!graph) return;

      const isExpanded = graph.expandedClusters.has(clusterId);
      const clusterBefore = graph.nodes.find((n) => n.id === clusterId) as
        | ClusterNode
        | undefined;
      const dirName = clusterBefore?.data.dirName ?? clusterId;
      const newGraph = isExpanded
        ? collapseCluster(clusterId, graph)
        : expandCluster(clusterId, graph);

      clusteredGraphRef.current = newGraph;

      const activeNodes = newGraph.nodes.filter((n) => {
        if (n.type === "clusterNode") return true;
        const parentClusterId = newGraph.clusterOf.get(n.id);
        if (!parentClusterId) return true;
        const parentCluster = newGraph.nodes.find((c) => c.id === parentClusterId);
        if (!parentCluster || parentCluster.type !== "clusterNode") return true;
        return (parentCluster as ClusterNode).data.expanded &&
          (parentCluster as ClusterNode).data.children.length <= 100;
      });

      runLayoutAndBuild(activeNodes, newGraph.edges);

      if (isExpanded) {
        showToast(`Collapsed "${dirName}"`);
      } else {
        const subClusterPrefix = `${clusterId}/`;
        const subClusters = newGraph.nodes.filter(
          (n) => n.type === "clusterNode" && n.id.startsWith(subClusterPrefix)
        );
        if (subClusters.length > 0) {
          showToast(
            `Expanded "${dirName}" — ${subClusters.length} sub-directories (click to drill deeper)`
          );
        } else {
          showToast(
            `Expanded "${dirName}" — ${clusterBefore?.data.fileCount ?? 0} files`
          );
        }
      }
    };

    window.addEventListener("cluster:toggle", handler);
    return () => window.removeEventListener("cluster:toggle", handler);
  }, [setNodes, setEdges, showToast, runLayoutAndBuild]);

  const onMove = useCallback(
    (_evt: MouseEvent | TouchEvent | null, viewport: Viewport) => {
      viewportRef.current = viewport;
      if (allNodesRef.current.length <= 150) return;

      if (viewportTimerRef.current) clearTimeout(viewportTimerRef.current);
      viewportTimerRef.current = setTimeout(() => {
        const allNodes = allNodesRef.current;
        if (allNodes.length <= 150) return;

        const visible = getVisibleNodes(allNodes, viewport, viewport.zoom);
        const visibleIds = new Set(visible.map((n) => n.id));
        const v = visualRef.current;

        const enriched = visible.map((n) =>
          n.type === "clusterNode" ? n : enrichNode(n as Node, v)
        );
        setNodes(enriched as Node[]);

        // Keep the edge list in sync with the culled node list.
        // ReactFlow silently drops any edge whose source or target is absent
        // from the current nodes array, so we must filter to only edges whose
        // both endpoints are present in the current visible set.
        const culledEdges = allEdgesRef.current.filter(
          (e) => visibleIds.has(e.source) && visibleIds.has(e.target)
        );
        setEdges(culledEdges.map((e) => styledEdge(e, v)));
      }, 100);
    },
    [setNodes, setEdges]
  );

  useEffect(() => {
    if (nodes.length === 0) return;
    const v = visualRef.current;
    setNodes((nds) =>
      nds.map((n) => (n.type === "clusterNode" ? n : enrichNode(n, v)))
    );
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
    matchingNodeIds,
    setNodes,
    setEdges,
    
  ]);

  const handleSearchChange = useCallback((value: string) => {
    setSearchInput(value);
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      if (!value.trim()) {
        setMatchingNodeIds(new Set());
        return;
      }
      const q = value.toLowerCase();
      const matches = new Set<string>();
      for (const n of allNodesRef.current) {
        if (n.type === "clusterNode") continue;
        const label = ((n.data as AppNodeData).label ?? n.id).toLowerCase();
        if (label.includes(q)) matches.add(n.id);
      }
      setMatchingNodeIds(matches);
    }, 200);
  }, []);

  const clearSearch = useCallback(() => {
    setSearchInput("");
    setMatchingNodeIds(new Set());
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
  }, []);

  const jumpToFirstMatch = useCallback(() => {
    const first = [...matchingNodeIds][0];
    if (!first) return;

    const graph = clusteredGraphRef.current;
    if (graph) {
      const clusterId = graph.clusterOf.get(first);
      
      if (clusterId && !graph.expandedClusters.has(clusterId)) {
        window.dispatchEvent(
          new CustomEvent("cluster:toggle", { detail: clusterId })
        );
      }
    }

    requestAnimationFrame(() => {
      const node = allNodesRef.current.find((n) => n.id === first);
      if (node) {
        setCenter(node.position.x + 100, node.position.y + 30, {
          zoom: 1.5,
          duration: 600,
        });
      }
    });
  }, [matchingNodeIds, setCenter]);

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

  const onNodeClick = useCallback(
    async (_: React.MouseEvent, node: Node) => {
      
      if (node.type === "clusterNode") return;
      if (!sessionId) return;

      const now = Date.now();

      if (lastClickRef.current.id === node.id && now - lastClickRef.current.time < 400) {
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

      if (!isChatPanelOpen) {
        toggleChatPanel();
      }

      setSelectedFile(node.id);
      try {
        const content = await getFileContent(sessionId, node.id);
        setFileContent(content);
      } catch {  }
      try {
        setAILoading(true);
        const ai = await explainFile(sessionId, node.id);
        setAIExplanation(ai.explanation, ai.source);
      } catch {  } finally {
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
      isChatPanelOpen,
      toggleChatPanel,
    ]
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

  const isClustered = clusteredGraphRef.current !== null;
  const totalFiles = graphData.nodes.length;

  return (
    <div className="relative w-full h-full flex flex-col" style={{ zIndex: 1 }}>
      <div className="relative flex-1 min-h-0 w-full">

        {}
        {isComputing && (
          <div
            className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-2 backdrop-blur-sm"
            style={{ background: "var(--bg-base)60" }}
          >
            <Loader2 className="w-6 h-6 animate-spin" style={{ color: "var(--accent-purple)" }} />
            <p className="text-[11px] font-medium" style={{ color: "var(--text-secondary)" }}>
              Computing layout…
            </p>
          </div>
        )}

        {}
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

        {}
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

        {}
        {!show3DGraph && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
            className="absolute top-3 left-3 z-20 flex items-center gap-2"
          >
            <div
              className="flex items-center gap-1.5 px-2 py-1 rounded-xl"
              style={{
                background: "var(--bg-overlay)",
                border: "1px solid var(--border-subtle)",
                backdropFilter: "blur(12px)",
              }}
            >
              <Search className="w-3 h-3 flex-shrink-0" style={{ color: "var(--text-muted)" }} />
              <input
                type="text"
                value={searchInput}
                onChange={(e) => handleSearchChange(e.target.value)}
                placeholder="Search nodes…"
                className="bg-transparent outline-none w-36 text-[10px] font-medium"
                style={{ color: "var(--text-primary)", caretColor: "var(--accent-purple)" }}
              />
              {searchInput && (
                <button
                  onClick={clearSearch}
                  className="flex-shrink-0 opacity-50 hover:opacity-100 transition-opacity"
                >
                  <X className="w-3 h-3" style={{ color: "var(--text-muted)" }} />
                </button>
              )}
            </div>

            {}
            <AnimatePresence>
              {searchInput && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  className="flex items-center gap-1.5 px-2 py-1 rounded-xl"
                  style={{
                    background: "var(--bg-overlay)",
                    border: "1px solid var(--border-subtle)",
                    backdropFilter: "blur(12px)",
                  }}
                >
                  {matchingNodeIds.size > 0 ? (
                    <>
                      <span className="text-[10px] font-medium" style={{ color: "var(--accent-cyan)" }}>
                        {matchingNodeIds.size} match{matchingNodeIds.size !== 1 ? "es" : ""}
                      </span>
                      <button
                        onClick={jumpToFirstMatch}
                        className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[9px] font-semibold transition-all hover:scale-105"
                        style={{
                          background: "rgba(34, 211, 238, 0.12)",
                          border: "1px solid rgba(34, 211, 238, 0.2)",
                          color: "var(--accent-cyan)",
                        }}
                        title="Center on first match (auto-expands clusters)"
                      >
                        <Navigation className="w-2.5 h-2.5" />
                        Jump
                      </button>
                    </>
                  ) : (
                    <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                      No matches
                    </span>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        )}

        {}
        <AnimatePresence>
          {toast && (
            <motion.div
              key="toast"
              initial={{ opacity: 0, y: 10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.95 }}
              transition={{ duration: 0.2 }}
              className="absolute bottom-20 left-1/2 -translate-x-1/2 z-30 px-4 py-2
                rounded-full text-[10px] font-medium max-w-xs text-center"
              style={{
                background: "var(--bg-overlay)",
                border: "1px solid var(--border-subtle)",
                color: "var(--text-secondary)",
                backdropFilter: "blur(16px)",
                boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
              }}
            >
              {toast}
            </motion.div>
          )}
        </AnimatePresence>

        {}
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
            onMove={onMove}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            minZoom={0.05}
            maxZoom={2}
            proOptions={{ hideAttribution: true }}
            defaultEdgeOptions={{ type: "smoothstep", animated: false }}
            nodesDraggable={nodes.length < 200 && !isComputing}
            nodesConnectable={false}
            elementsSelectable={!isComputing}
            onlyRenderVisibleElements
          >
            <Background color="rgba(124, 110, 224, 0.02)" gap={24} />
            <Controls showInteractive={false} style={{ marginBottom: 36 }} />
            <MiniMap
              nodeColor={(n) => {
                if (n.type === "clusterNode") return "#7c6ee0";
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

        {}
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
            <span className="text-[9px] font-medium" style={{ color: "var(--text-muted)" }}>
              {totalFiles} files
            </span>
            {isClustered && (
              <>
                <span style={{ color: "var(--border-subtle)" }}>·</span>
                <span className="text-[9px] font-medium" style={{ color: "var(--accent-purple)" }}>
                  clustered
                </span>
              </>
            )}
            <span style={{ color: "var(--border-subtle)" }}>·</span>
            <span className="text-[9px] font-medium" style={{ color: "var(--text-muted)" }}>
              {nodes.length} rendered
            </span>
            <span style={{ color: "var(--border-subtle)" }}>·</span>
            <span className="text-[9px] font-medium" style={{ color: "var(--text-muted)" }}>
              {graphData.edges.length} edges
            </span>
            {matchingNodeIds.size > 0 && (
              <>
                <span style={{ color: "var(--border-subtle)" }}>·</span>
                <span className="text-[9px] font-medium" style={{ color: "var(--accent-cyan)" }}>
                  {matchingNodeIds.size} matched
                </span>
              </>
            )}
          </motion.div>
        )}

        <GitTimeline />
      </div>

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
