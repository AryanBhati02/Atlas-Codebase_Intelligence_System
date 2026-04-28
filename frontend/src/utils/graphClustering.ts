import type { Node, Edge, Viewport } from "reactflow";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AppNodeData {
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
}

export type AppNode = Node<AppNodeData>;

export interface ClusterNodeData {
  label: string;
  fileCount: number;
  children: AppNode[];
  expanded: boolean;
  language: string | null;
  avgComplexity: number;
  dirName: string;
}

export type ClusterNode = Node<ClusterNodeData, "clusterNode">;

/** Union of a plain file node and a directory cluster node. */
export type AnyNode = AppNode | ClusterNode;

export interface ClusteredGraph {
  /** Currently visible nodes: cluster headers (collapsed or open) + expanded children. */
  nodes: AnyNode[];
  /** Currently visible edges (inter-cluster or internal-when-expanded). */
  edges: Edge[];
  /** Lookup from original file-node id → that AppNode. */
  nodeMap: Map<string, AppNode>;
  /** Maps every file-node id → the cluster id it belongs to. */
  clusterOf: Map<string, string>;
  /** Set of cluster ids whose children are currently shown in the graph. */
  expandedClusters: Set<string>;
  /** All original file-level edges — never mutated. */
  originalEdges: Edge[];
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function getDirName(nodeId: string): string {
  const slash = nodeId.indexOf("/");
  return slash !== -1 ? nodeId.slice(0, slash) : "(root)";
}

function getMostCommonLanguage(nodes: AppNode[]): string | null {
  const counts = new Map<string, number>();
  for (const n of nodes) {
    const lang = n.data.language;
    if (lang) counts.set(lang, (counts.get(lang) ?? 0) + 1);
  }
  let best: string | null = null;
  let bestCount = 0;
  for (const [lang, count] of counts) {
    if (count > bestCount) { best = lang; bestCount = count; }
  }
  return best;
}

function getAvgComplexity(nodes: AppNode[]): number {
  if (nodes.length === 0) return 0;
  return nodes.reduce((acc, n) => acc + (n.data.complexity ?? 0), 0) / nodes.length;
}

/**
 * Recomputes which edges are visible given the current expand state.
 * - Internal edges (same cluster) are shown only when that cluster is expanded.
 * - Cross-cluster edges map each endpoint to the cluster node when collapsed,
 *   or to the actual file node when expanded — then deduplicated.
 * - Edges whose endpoints are not in visibleNodeIds are dropped (handles
 *   partial display, e.g. showing only top-50 clusters).
 */
function computeVisibleEdges(
  originalEdges: Edge[],
  clusterOf: Map<string, string>,
  expandedClusters: Set<string>,
  visibleNodeIds: Set<string>
): Edge[] {
  const edgeMap = new Map<string, Edge>();

  for (const edge of originalEdges) {
    const srcCluster = clusterOf.get(edge.source);
    const tgtCluster = clusterOf.get(edge.target);
    if (!srcCluster || !tgtCluster) continue;

    if (srcCluster === tgtCluster) {
      // Internal: only show when cluster is expanded and both children visible
      if (
        expandedClusters.has(srcCluster) &&
        visibleNodeIds.has(edge.source) &&
        visibleNodeIds.has(edge.target)
      ) {
        edgeMap.set(edge.id, { ...edge, type: "smoothstep" });
      }
      continue;
    }

    // Cross-cluster: map each end to visible representative
    const srcExpanded = expandedClusters.has(srcCluster);
    const tgtExpanded = expandedClusters.has(tgtCluster);
    const visibleSrc = srcExpanded && visibleNodeIds.has(edge.source) ? edge.source : srcCluster;
    const visibleTgt = tgtExpanded && visibleNodeIds.has(edge.target) ? edge.target : tgtCluster;

    if (
      visibleSrc === visibleTgt ||
      !visibleNodeIds.has(visibleSrc) ||
      !visibleNodeIds.has(visibleTgt)
    ) continue;

    const key = `${visibleSrc}=>${visibleTgt}`;
    if (!edgeMap.has(key)) {
      edgeMap.set(key, { id: key, source: visibleSrc, target: visibleTgt, type: "smoothstep" });
    }
  }

  return Array.from(edgeMap.values());
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Groups all file nodes by their first path segment and creates one ClusterNode
 * per directory. Returns a ClusteredGraph where all clusters are collapsed.
 */
export function clusterByDirectory(nodes: AppNode[], edges: Edge[]): ClusteredGraph {
  const dirMap = new Map<string, AppNode[]>();
  for (const node of nodes) {
    const dir = getDirName(node.id);
    if (!dirMap.has(dir)) dirMap.set(dir, []);
    dirMap.get(dir)!.push(node);
  }

  const nodeMap = new Map<string, AppNode>();
  for (const node of nodes) nodeMap.set(node.id, node);

  const clusterOf = new Map<string, string>();
  for (const [dir, children] of dirMap) {
    const clusterId = `cluster-${dir}`;
    for (const child of children) clusterOf.set(child.id, clusterId);
  }

  const clusterNodes: ClusterNode[] = [];
  let ci = 0;
  for (const [dir, children] of dirMap) {
    clusterNodes.push({
      id: `cluster-${dir}`,
      type: "clusterNode",
      position: { x: ci * 340, y: 0 },
      data: {
        label: dir,
        dirName: dir,
        fileCount: children.length,
        children,
        expanded: false,
        language: getMostCommonLanguage(children),
        avgComplexity: getAvgComplexity(children),
      },
    });
    ci++;
  }

  const expandedClusters = new Set<string>();
  const visibleNodeIds = new Set(clusterNodes.map((n) => n.id));
  const interClusterEdges = computeVisibleEdges(edges, clusterOf, expandedClusters, visibleNodeIds);

  return {
    nodes: clusterNodes,
    edges: interClusterEdges,
    nodeMap,
    clusterOf,
    expandedClusters,
    originalEdges: edges,
  };
}

/**
 * Expands a cluster: the cluster node stays (marked expanded=true) and its
 * children are inserted into the graph in a grid below the cluster node.
 * A new layout run is expected after this call.
 */
export function expandCluster(clusterId: string, graph: ClusteredGraph): ClusteredGraph {
  const clusterNode = graph.nodes.find((n) => n.id === clusterId) as ClusterNode | undefined;
  if (!clusterNode || clusterNode.type !== "clusterNode") return graph;

  const children = clusterNode.data.children;
  const cx = clusterNode.position.x;
  const cy = clusterNode.position.y;
  const cols = Math.max(1, Math.ceil(Math.sqrt(children.length)));

  const positionedChildren: AppNode[] = children.map((child, i) => ({
    ...child,
    position: {
      x: cx + (i % cols) * 220 - ((cols - 1) * 110),
      y: cy + 130 + Math.floor(i / cols) * 80,
    },
  }));

  // Mark cluster node as expanded (stays in graph as a group header)
  const updatedCluster: ClusterNode = {
    ...clusterNode,
    data: { ...clusterNode.data, expanded: true },
  };

  const newExpandedClusters = new Set(graph.expandedClusters);
  newExpandedClusters.add(clusterId);

  const otherNodes = graph.nodes.filter((n) => n.id !== clusterId);
  const newNodes: AnyNode[] = [...otherNodes, updatedCluster, ...positionedChildren];
  const visibleNodeIds = new Set(newNodes.map((n) => n.id));

  return {
    ...graph,
    nodes: newNodes,
    edges: computeVisibleEdges(graph.originalEdges, graph.clusterOf, newExpandedClusters, visibleNodeIds),
    expandedClusters: newExpandedClusters,
  };
}

/**
 * Collapses an expanded cluster: removes its children from the graph and
 * resets the cluster node to collapsed state.
 */
export function collapseCluster(clusterId: string, graph: ClusteredGraph): ClusteredGraph {
  const childrenIds = new Set<string>();
  for (const [nodeId, cId] of graph.clusterOf) {
    if (cId === clusterId) childrenIds.add(nodeId);
  }

  const clusterNode = graph.nodes.find((n) => n.id === clusterId) as ClusterNode | undefined;
  if (!clusterNode) return graph;

  const updatedCluster: ClusterNode = {
    ...clusterNode,
    data: { ...clusterNode.data, expanded: false },
  };

  const newExpandedClusters = new Set(graph.expandedClusters);
  newExpandedClusters.delete(clusterId);

  const otherNodes = graph.nodes.filter((n) => !childrenIds.has(n.id) && n.id !== clusterId);
  const newNodes: AnyNode[] = [...otherNodes, updatedCluster];
  const visibleNodeIds = new Set(newNodes.map((n) => n.id));

  return {
    ...graph,
    nodes: newNodes,
    edges: computeVisibleEdges(graph.originalEdges, graph.clusterOf, newExpandedClusters, visibleNodeIds),
    expandedClusters: newExpandedClusters,
  };
}

/**
 * Returns the subset of nodes that should be rendered in the DOM given
 * the current viewport and zoom level. Always returns ≤ 150 nodes.
 *
 * - Total ≤ 150: return all.
 * - Zoom < 0.25: cluster nodes only.
 * - Zoom < 0.6: nodes within viewport + 600 px padding.
 * - Zoom ≥ 0.6: nodes within viewport + 200 px padding.
 */
export function getVisibleNodes(
  nodes: AnyNode[],
  viewport: Viewport,
  zoom: number
): AnyNode[] {
  if (nodes.length <= 150) return nodes;

  if (zoom < 0.25) {
    return nodes.filter((n) => n.type === "clusterNode");
  }

  const padding = zoom < 0.6 ? 600 : 200;
  const sw = window.innerWidth;
  const sh = window.innerHeight;

  // Convert screen bounds → graph-space bounds
  const minX = (-padding - viewport.x) / zoom;
  const maxX = (sw + padding - viewport.x) / zoom;
  const minY = (-padding - viewport.y) / zoom;
  const maxY = (sh + padding - viewport.y) / zoom;

  return nodes.filter(({ position: { x, y } }) =>
    x >= minX && x <= maxX && y >= minY && y <= maxY
  );
}
