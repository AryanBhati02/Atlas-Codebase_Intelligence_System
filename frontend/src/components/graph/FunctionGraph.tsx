
import React, { useMemo, useCallback, useEffect } from "react";
import { ErrorBoundary } from "../ErrorBoundary";
import { motion, AnimatePresence } from "framer-motion";
import ReactFlow, {
  Background,
  Controls,
  type Node,
  type Edge,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
} from "reactflow";
import {
  X,
  GitBranch,
  ExternalLink,
  Loader2,
} from "lucide-react";
import { useAppStore } from "../../store/appStore";
import { useGraphStore } from "../../store/graphStore";

function FunctionNodeComponent({
  data,
}: {
  data: {
    name: string;
    complexity: number;
    is_exported: boolean;
    line_count: number;
    is_dead: boolean;
  };
}) {
  const complexityColor =
    data.complexity > 0.6
      ? "#ef4444"
      : data.complexity > 0.3
        ? "#f59e0b"
        : "#22c55e";

  return (
    <>
      <Handle
        type="target"
        position={Position.Top}
        style={{ background: complexityColor, border: "none", width: 5, height: 5 }}
      />
      <div
        className={`fn-graph-node ${data.is_dead ? "fn-dead" : ""}`}
        style={{
          borderColor: `${complexityColor}40`,
          boxShadow: `0 0 12px ${complexityColor}15`,
        }}
      >
        <div className="flex items-center gap-1.5">
          <div
            className="w-1.5 h-1.5 rounded-full shrink-0"
            style={{ backgroundColor: complexityColor }}
          />
          <span className="text-[10px] font-medium truncate max-w-[120px]" style={{ color: "var(--text-primary)" }}>
            {data.name}
          </span>
          {data.is_exported && (
            <ExternalLink className="w-2.5 h-2.5 text-accent-cyan shrink-0" />
          )}
        </div>
        <div className="text-[8px] mt-0.5" style={{ color: "var(--text-muted)" }}>
          {data.line_count} lines
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        style={{ background: complexityColor, border: "none", width: 5, height: 5 }}
      />
    </>
  );
}

const nodeTypes = { functionNode: FunctionNodeComponent };

export function FunctionGraph() {
  const {
    functionGraphData,
    functionGraphFile,
    showFunctionGraph,
    isFunctionGraphLoading,
    deadCodeData,
    showDeadCode,
  } = useAppStore();

  // Use the store directly so close only flips the visibility flag —
  // it does NOT wipe functionGraphData/functionGraphFile, which would
  // cause the ErrorBoundary or AnimatePresence teardown to run with
  // null data and potentially crash the parent graph view.
  const toggleFunctionGraph = useGraphStore((s) => s.toggleFunctionGraph);

  const deadFunctionNames = useMemo(() => {
    if (!showDeadCode || !deadCodeData || !functionGraphFile) return new Set<string>();
    return new Set(
      deadCodeData.dead_functions
        .filter((df) => df.path === functionGraphFile)
        .map((df) => df.name)
    );
  }, [showDeadCode, deadCodeData, functionGraphFile]);

  const { rfNodes, rfEdges } = useMemo(() => {
    if (!functionGraphData || functionGraphData.nodes.length === 0) {
      return { rfNodes: [], rfEdges: [] };
    }

    const cols = Math.max(Math.ceil(Math.sqrt(functionGraphData.nodes.length)), 1);
    const xGap = 180;
    const yGap = 100;

    const nodes: Node[] = functionGraphData.nodes.map((n, i) => ({
      id: n.id,
      type: "functionNode",
      position: {
        x: (i % cols) * xGap + 40,
        y: Math.floor(i / cols) * yGap + 40,
      },
      data: {
        name: n.name,
        complexity: n.complexity,
        is_exported: n.is_exported,
        line_count: n.line_count,
        is_dead: deadFunctionNames.has(n.name),
        start_line: n.start_line,
      },
    }));

    const nodeIdSet = new Set(nodes.map((n) => n.id));

    const edges: Edge[] = functionGraphData.edges
      .map((e) => ({
        id: e.id,
        source: e.source_fn,
        target: e.target_fn,
        animated: !e.is_cross_file,
        style: {
          stroke: e.is_cross_file
            ? "rgba(139, 92, 246, 0.35)"
            : "rgba(124, 110, 224, 0.3)",
          strokeWidth: Math.min(e.call_count, 3),
          strokeDasharray: e.is_cross_file ? "5 3" : undefined,
        },
        label: e.call_count > 1 ? `×${e.call_count}` : undefined,
        labelStyle: { fill: "#64748b", fontSize: 9 },
        labelBgStyle: { fill: "#0e0e18", opacity: 0.8 },
      }))
      .filter((e) => nodeIdSet.has(e.source) && nodeIdSet.has(e.target));

    return { rfNodes: nodes, rfEdges: edges };
  }, [functionGraphData, deadFunctionNames]);

  const [nodes, setNodes, onNodesChange] = useNodesState(rfNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(rfEdges);

  useEffect(() => { setNodes(rfNodes); }, [rfNodes, setNodes]);
  useEffect(() => { setEdges(rfEdges); }, [rfEdges, setEdges]);

  // Close only hides the panel — keeps functionGraphData intact so the
  // next open is instant and so the AnimatePresence exit animation runs
  // without accessing null state.
  const handleClose = useCallback(() => {
    try {
      toggleFunctionGraph();
    } catch (err) {
      console.error("[FunctionGraph] close error:", err);
    }
  }, [toggleFunctionGraph]);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const startLine = node.data?.start_line;
      if (startLine && typeof startLine === "number") {

        window.dispatchEvent(
          new CustomEvent("scroll-to-line", { detail: { line: startLine } })
        );
      }
    },
    []
  );

  // On error boundary reset, just hide the panel — same safe approach.
  const handleBoundaryReset = useCallback(() => {
    try {
      toggleFunctionGraph();
    } catch (err) {
      console.error("[FunctionGraph] boundary reset error:", err);
    }
  }, [toggleFunctionGraph]);

  return (
    <AnimatePresence>
      {showFunctionGraph && (
        <motion.div
          initial={{ y: "100%", opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: "100%", opacity: 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
          className="fn-graph-panel"
        >
          {/* ErrorBoundary is inside the conditional so its full-height
              fallback renders only within the FunctionGraph panel, not
              as a sibling overlay that covers the main 2D ReactFlow graph. */}
          <ErrorBoundary onReset={handleBoundaryReset}>
            <div className="flex items-center justify-between px-4 py-2.5
              border-b shrink-0" style={{ borderColor: "var(--border-subtle)" }}>
              <div className="flex items-center gap-2">
                <GitBranch className="w-3.5 h-3.5 text-accent-purple" />
                <span className="text-[11px] font-semibold" style={{ color: "var(--text-primary)" }}>
                  Function Graph
                </span>
                {functionGraphFile && (
                  <span className="text-[10px] font-mono truncate max-w-[200px]" style={{ color: "var(--text-muted)" }}>
                    {functionGraphFile}
                  </span>
                )}
                {functionGraphData && (
                  <span className="text-[9px] ml-1" style={{ color: "var(--text-muted)" }}>
                    {functionGraphData.nodes.length} functions · {functionGraphData.edges.length} calls
                  </span>
                )}
              </div>
              <button
                onClick={handleClose}
                className="p-1 rounded-md transition-colors"
                style={{ color: "var(--text-muted)" }}
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="flex-1 min-h-0">
              {isFunctionGraphLoading ? (
                <div className="flex items-center justify-center h-full gap-2">
                  <Loader2 className="w-4 h-4 text-accent-purple animate-spin" />
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>Building function graph…</span>
                </div>
              ) : rfNodes.length === 0 ? (
                <div className="flex items-center justify-center h-full">
                  <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                    No functions found in this file
                  </span>
                </div>
              ) : (
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  onNodeClick={onNodeClick}
                  nodeTypes={nodeTypes}
                  fitView
                  fitViewOptions={{ padding: 0.4 }}
                  minZoom={0.3}
                  maxZoom={2.5}
                  proOptions={{ hideAttribution: true }}
                >
                  <Background
                    color="rgba(139, 92, 246, 0.03)"
                    gap={16}
                  />
                  <Controls
                    showInteractive={false}
                    position="bottom-right"
                  />
                </ReactFlow>
              )}
            </div>
          </ErrorBoundary>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
