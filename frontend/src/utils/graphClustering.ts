import type { Node, Edge, Viewport } from "reactflow";
import { createProfiler } from "../lib/perfProfiler";

export const visibleNodesProfiler = createProfiler("getVisibleNodes");

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

export type AnyNode = AppNode | ClusterNode;

export interface ClusteredGraph {
    nodes: AnyNode[];
    edges: Edge[];
    nodeMap: Map<string, AppNode>;
    clusterOf: Map<string, string>;
    expandedClusters: Set<string>;
    originalEdges: Edge[];
}

function getDirName(nodeId: string): string {
  const slash = nodeId.indexOf("/");
  return slash !== -1 ? nodeId.slice(0, slash) : "(root)";
}

function getDirAtDepth(nodeId: string, depth: number): string {
  const parts = nodeId.split("/");
  if (parts.length === 1) return "(root)";
  if (depth >= parts.length) return nodeId;
  return parts.slice(0, depth).join("/");
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
      
      if (
        expandedClusters.has(srcCluster) &&
        visibleNodeIds.has(edge.source) &&
        visibleNodeIds.has(edge.target)
      ) {
        edgeMap.set(edge.id, { ...edge, type: "smoothstep" });
      }
      continue;
    }

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

export function subClusterChildren(
  parentClusterId: string,
  children: AppNode[],
  parentPosition: { x: number; y: number },
  depth: number
): { subClusters: ClusterNode[]; directFiles: AppNode[] } {
  
  const parentLabel = parentClusterId.replace(/^cluster-/, "");

  const groups = new Map<string, AppNode[]>();
  for (const child of children) {
    const dirPrefix = getDirAtDepth(child.id, depth);
    if (!groups.has(dirPrefix)) groups.set(dirPrefix, []);
    groups.get(dirPrefix)!.push(child);
  }

  const subClusterGroups: Array<{ dirPrefix: string; group: AppNode[] }> = [];
  const directFileNodes: AppNode[] = [];

  for (const [dirPrefix, group] of groups) {
    if (group.length > 1 && dirPrefix !== parentLabel) {
      subClusterGroups.push({ dirPrefix, group });
    } else {
      directFileNodes.push(...group);
    }
  }

  const subCols = Math.min(5, Math.max(1, Math.ceil(Math.sqrt(subClusterGroups.length))));
  const subRows = Math.ceil(subClusterGroups.length / subCols);

  const getSubClusterPosition = (index: number): { x: number; y: number } => ({
    x: parentPosition.x + (index % subCols) * 360 - ((subCols - 1) * 180),
    y: parentPosition.y + 180 + Math.floor(index / subCols) * 160,
  });

  const fileYStart = parentPosition.y + 180 + subRows * 160 + 60;
  const fileCols = Math.max(1, Math.ceil(Math.sqrt(directFileNodes.length)));

  const getDirectFilePosition = (index: number): { x: number; y: number } => ({
    x: parentPosition.x + (index % fileCols) * 220 - ((fileCols - 1) * 110),
    y: fileYStart + Math.floor(index / fileCols) * 80,
  });

  const subClusters: ClusterNode[] = subClusterGroups.map(({ dirPrefix, group }, i) => ({
    id: `cluster-${dirPrefix}`,
    type: "clusterNode" as const,
    position: getSubClusterPosition(i),
    data: {
      label: dirPrefix,
      dirName: dirPrefix,
      fileCount: group.length,
      children: group,
      expanded: false,
      language: getMostCommonLanguage(group),
      avgComplexity: getAvgComplexity(group),
    },
  }));

  const directFiles: AppNode[] = directFileNodes.map((child, i) => ({
    ...child,
    position: getDirectFilePosition(i),
  }));

  return { subClusters, directFiles };
}

export function expandCluster(clusterId: string, graph: ClusteredGraph): ClusteredGraph {
  const clusterNode = graph.nodes.find((n) => n.id === clusterId) as ClusterNode | undefined;
  if (!clusterNode || clusterNode.type !== "clusterNode") return graph;

  const children = clusterNode.data.children;
  const cx = clusterNode.position.x;
  const cy = clusterNode.position.y;

  const updatedCluster: ClusterNode = {
    ...clusterNode,
    data: { ...clusterNode.data, expanded: true },
  };

  const newExpandedClusters = new Set(graph.expandedClusters);
  newExpandedClusters.add(clusterId);

  let newNodes: AnyNode[];
  let newClusterOf = graph.clusterOf;

  if (children.length <= 100) {
    
    const cols = Math.max(1, Math.ceil(Math.sqrt(children.length)));
    const positionedChildren: AppNode[] = children.map((child, i) => ({
      ...child,
      position: {
        x: cx + (i % cols) * 220 - ((cols - 1) * 110),
        y: cy + 130 + Math.floor(i / cols) * 80,
      },
    }));
    const otherNodes = graph.nodes.filter((n) => n.id !== clusterId);
    newNodes = [...otherNodes, updatedCluster, ...positionedChildren];
  } else {
    
    const slashCount = (clusterNode.data.dirName.match(/\//g) ?? []).length;
    const depth = slashCount + 2;

    const { subClusters, directFiles } = subClusterChildren(
      clusterId,
      children,
      { x: cx, y: cy },
      depth
    );

    const updatedClusterOf = new Map(graph.clusterOf);
    for (const sub of subClusters) {
      for (const child of sub.data.children) {
        updatedClusterOf.set(child.id, sub.id);
      }
    }
    newClusterOf = updatedClusterOf;

    const otherNodes = graph.nodes.filter((n) => n.id !== clusterId);
    newNodes = [...otherNodes, updatedCluster, ...subClusters, ...directFiles];
  }

  const visibleNodeIds = new Set(newNodes.map((n) => n.id));

  return {
    ...graph,
    nodes: newNodes,
    edges: computeVisibleEdges(graph.originalEdges, newClusterOf, newExpandedClusters, visibleNodeIds),
    expandedClusters: newExpandedClusters,
    clusterOf: newClusterOf,
  };
}

export function collapseCluster(clusterId: string, graph: ClusteredGraph): ClusteredGraph {
  const clusterNode = graph.nodes.find((n) => n.id === clusterId) as ClusterNode | undefined;
  if (!clusterNode) return graph;

  const directChildIds = new Set<string>();
  for (const [nodeId, cId] of graph.clusterOf) {
    if (cId === clusterId) directChildIds.add(nodeId);
  }

  const subClusterPrefix = `${clusterId}/`; 
  const subClusterIds = new Set<string>();
  for (const node of graph.nodes) {
    if (node.type === "clusterNode" && node.id.startsWith(subClusterPrefix)) {
      subClusterIds.add(node.id);
    }
  }

  const newClusterOf = new Map(graph.clusterOf);
  const subClusterChildIds = new Set<string>();
  for (const [nodeId, cId] of graph.clusterOf) {
    if (subClusterIds.has(cId)) {
      subClusterChildIds.add(nodeId);
      newClusterOf.set(nodeId, clusterId);
    }
  }

  const updatedCluster: ClusterNode = {
    ...clusterNode,
    data: { ...clusterNode.data, expanded: false },
  };

  const newExpandedClusters = new Set(graph.expandedClusters);
  newExpandedClusters.delete(clusterId);
  
  for (const subId of subClusterIds) {
    newExpandedClusters.delete(subId);
  }

  const allRemovedIds = new Set([...directChildIds, ...subClusterIds, ...subClusterChildIds]);
  const otherNodes = graph.nodes.filter((n) => !allRemovedIds.has(n.id) && n.id !== clusterId);
  const newNodes: AnyNode[] = [...otherNodes, updatedCluster];
  const visibleNodeIds = new Set(newNodes.map((n) => n.id));

  return {
    ...graph,
    nodes: newNodes,
    edges: computeVisibleEdges(graph.originalEdges, newClusterOf, newExpandedClusters, visibleNodeIds),
    expandedClusters: newExpandedClusters,
    clusterOf: newClusterOf,
  };
}

export function getVisibleNodes(
  nodes: AnyNode[],
  viewport: Viewport,
  zoom: number
): AnyNode[] {
  const result = visibleNodesProfiler.measure(() => {
    if (nodes.length <= 150) return nodes;

    if (zoom < 0.25) {
      return nodes.filter((n) => n.type === "clusterNode");
    }

    const padding = zoom < 0.6 ? 600 : 200;
    const sw = window.innerWidth;
    const sh = window.innerHeight;

    const minX = (-padding - viewport.x) / zoom;
    const maxX = (sw + padding - viewport.x) / zoom;
    const minY = (-padding - viewport.y) / zoom;
    const maxY = (sh + padding - viewport.y) / zoom;

    const filtered = nodes.filter(({ position: { x, y } }) =>
      x >= minX && x <= maxX && y >= minY && y <= maxY
    );

    if (filtered.length <= 150) return filtered;

    const centerX = (sw / 2 - viewport.x) / zoom;
    const centerY = (sh / 2 - viewport.y) / zoom;

    const clusterNodes = filtered.filter((n) => n.type === "clusterNode");
    const fileNodes = filtered.filter((n) => n.type !== "clusterNode");

    const sortedFileNodes = fileNodes.slice().sort((a, b) => {
      const da = Math.hypot(a.position.x - centerX, a.position.y - centerY);
      const db = Math.hypot(b.position.x - centerX, b.position.y - centerY);
      return da - db;
    });

    const fileSlots = Math.max(0, 150 - clusterNodes.length);
    return [...clusterNodes, ...sortedFileNodes.slice(0, fileSlots)];
  });
  visibleNodesProfiler.setLastResultCount(result.length);
  return result;
}
